"""Backtest phase 1 : biais/RMSE, matrices de confusion, survie des fenêtres.

Produit les tables de métriques consommées par rapport.py et les poids
calibrés data/poids_modeles.json.
"""

import json
from datetime import date

import numpy as np
import pandas as pd

import config
import fenetre
from verite import construire_verite, secteur

BLOCS_HORAIRES = {"nuit": (0, 8), "matin": (8, 12), "apres_midi": (12, 17),
                  "soiree": (17, 20), "tard": (20, 24)}


# ---------------------------------------------------------------- chargement

def charger():
    previsions = pd.read_parquet(f"{config.DOSSIER_PROCESSED}/previsions.parquet")
    hour0 = pd.read_parquet(f"{config.DOSSIER_PROCESSED}/hour0.parquet")
    verite = construire_verite(hour0)
    return previsions, hour0, verite


def apparier(previsions: pd.DataFrame, verite: pd.DataFrame) -> pd.DataFrame:
    """Joint prévision et vérité sur l'heure UTC (pas d'ambiguïté DST en UTC)."""
    df = previsions.merge(
        verite[["vent", "u", "v", "direction", "rafales"]].add_prefix("verite_"),
        left_on="time", right_index=True, how="inner")
    temps_local = df["time"].dt.tz_convert(config.FUSEAU_LOCAL)
    df["heure_locale"] = temps_local.dt.hour
    df["date_locale"] = temps_local.dt.date
    df["mois"] = temps_local.dt.month
    df["secteur_verite"] = secteur(df["verite_direction"])
    df = df[df["mois"].isin(config.MOIS_SAISON)]
    return df


# ---------------------------------------------------------------- biais/RMSE

def _stats(g: pd.DataFrame) -> pd.Series:
    err = (g["vent"] - g["verite_vent"]).astype(float)
    return pd.Series({
        "n": len(g),
        "biais": err.mean(),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "biais_u": (g["u"] - g["verite_u"]).mean(),
        "biais_v": (g["v"] - g["verite_v"]).mean(),
    })


def biais_rmse(apparie: pd.DataFrame) -> pd.DataFrame:
    """Global par modèle × horizon, en journée navigable seulement (8–20 h)."""
    jour = apparie[(apparie["heure_locale"] >= config.HEURE_DEBUT)
                   & (apparie["heure_locale"] < config.HEURE_FIN)]
    return (jour.groupby(["modele", "horizon"])
            .apply(_stats, include_groups=False).reset_index())


def biais_segmente(apparie: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Segmentation (secteur/mois/tranche horaire) avec garde n >= 30."""
    df = apparie.copy()
    if dimension == "tranche":
        df["tranche"] = pd.cut(df["heure_locale"],
                               bins=[0, 8, 12, 17, 20, 24], right=False,
                               labels=["nuit", "matin", "apres_midi", "soiree", "tard"])
        cle = "tranche"
    elif dimension == "secteur":
        cle = "secteur_verite"
        df = df[(df["heure_locale"] >= config.HEURE_DEBUT)
                & (df["heure_locale"] < config.HEURE_FIN)]
    else:
        cle = "mois"
        df = df[(df["heure_locale"] >= config.HEURE_DEBUT)
                & (df["heure_locale"] < config.HEURE_FIN)]
    res = (df.groupby(["modele", "horizon", cle], observed=True)
           .apply(_stats, include_groups=False).reset_index())
    return res[res["n"] >= config.N_MIN_SEGMENT]


# ------------------------------------------------------- événement "fenêtre"

def series_jour(df: pd.DataFrame, colonne: str = "vent") -> pd.Series:
    """DataFrame (time UTC, colonne) -> Series indexée en heure locale."""
    s = df.set_index("time")[colonne].astype(float).sort_index()
    s.index = s.index.tz_convert(config.FUSEAU_LOCAL)
    return s


def jours_foilables(serie_locale: pd.Series) -> pd.Series:
    """Series bool indexée par date locale : la journée a-t-elle une fenêtre ?

    Une journée avec des heures manquantes dans 8–20 h est exclue (NaN coupe
    les fenêtres mais une journée trop trouée n'est pas jugeable).
    """
    jour = serie_locale.between_time(f"{config.HEURE_DEBUT}:00",
                                     f"{config.HEURE_FIN - 1}:00")
    resultats = {}
    for d, g in jour.groupby(jour.index.date):
        if len(g) < (config.HEURE_FIN - config.HEURE_DEBUT):
            continue  # journée incomplète (bord de saison, trou d'archive)
        resultats[d] = len(fenetre.fenetres_du_jour(g.tolist())) > 0
    return pd.Series(resultats)


def intervalle_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de confiance à 95 % sur une proportion (méthode de Wilson)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    marge = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return (max(0.0, centre - marge), min(1.0, centre + marge))


def confusion_fenetres(apparie: pd.DataFrame, verite: pd.DataFrame) -> pd.DataFrame:
    """POD et taux de fausses alertes par modèle × horizon, avec IC 95 %."""
    verite_df = verite.reset_index()[["time", "vent"]]
    reels = jours_foilables(series_jour(verite_df))
    lignes = []
    for (modele, horizon), g in apparie.groupby(["modele", "horizon"]):
        prevus = jours_foilables(series_jour(g))
        commun = prevus.index.intersection(reels.index)
        p, r = prevus.loc[commun], reels.loc[commun]
        hits = int((p & r).sum())
        fausses = int((p & ~r).sum())
        manques = int((~p & r).sum())
        vrais_neg = int((~p & ~r).sum())
        pod = hits / (hits + manques) if hits + manques else float("nan")
        far = fausses / (fausses + hits) if fausses + hits else float("nan")
        lignes.append({
            "modele": modele, "horizon": horizon, "n_jours": len(commun),
            "jours_foilables_reels": int(r.sum()),
            "hits": hits, "fausses_alertes": fausses,
            "manques": manques, "vrais_negatifs": vrais_neg,
            "pod": pod, "pod_ic": intervalle_wilson(hits, hits + manques),
            "far": far, "far_ic": intervalle_wilson(fausses, fausses + hits),
        })
    return pd.DataFrame(lignes)


def survie_fenetres(apparie: pd.DataFrame, verite: pd.DataFrame) -> pd.DataFrame:
    """Parmi les GO annoncés à 96 h : combien tiennent à 48 h, 24 h, en vrai ?

    Calculé sur la prévision d'ensemble (médiane multi-modèles corrigée du
    biais par modèle × horizon) — c'est elle qui rend le verdict du dashboard —
    puis par modèle individuel pour comparaison.
    """
    verite_df = verite.reset_index()[["time", "vent"]]
    reels = jours_foilables(series_jour(verite_df))

    go = {}
    for horizon in config.HORIZONS:
        ens = (apparie[apparie["horizon"] == horizon]
               .groupby("time")["vent"].median().reset_index())
        go[horizon] = jours_foilables(series_jour(ens))

    lignes = []
    base = go["96h"]
    idx = base.index.intersection(reels.index)
    go96 = base.loc[idx][base.loc[idx]].index
    n96 = len(go96)
    for cible, valeurs in [("48h", go["48h"]), ("24h", go["24h"]), ("réalisé", reels)]:
        communs = [d for d in go96 if d in valeurs.index]
        tiennent = int(sum(bool(valeurs.loc[d]) for d in communs))
        lignes.append({
            "de": "96h", "vers": cible, "n_go_96h": n96,
            "n_evaluables": len(communs), "tiennent": tiennent,
            "taux": tiennent / len(communs) if communs else float("nan"),
            "ic": intervalle_wilson(tiennent, len(communs)),
        })
    # Survie 48h -> réalisé et 24h -> réalisé (fiabilité d'un GO à cet horizon)
    for horizon in ["48h", "24h"]:
        s = go[horizon]
        idx = s.index.intersection(reels.index)
        gos = s.loc[idx][s.loc[idx]].index
        tiennent = int(sum(bool(reels.loc[d]) for d in gos))
        lignes.append({
            "de": horizon, "vers": "réalisé", "n_go_96h": None,
            "n_evaluables": len(gos), "tiennent": tiennent,
            "taux": tiennent / len(gos) if len(gos) else float("nan"),
            "ic": intervalle_wilson(tiennent, len(gos)),
        })
    return pd.DataFrame(lignes)


# ------------------------------------------------------------------- rafales

def ratios_rafales(hour0: pd.DataFrame) -> dict:
    """Ratio médian rafales/vent par modèle (repli pour ECMWF, phase 3).

    Calculé sur les heures à vent >= 9 nds (la bande foilable, là où le ratio
    sert) : sous ce seuil les ratios sont contaminés par le vent faible
    (ex. HRDPS plafonne rafales = vent moyen à bas régime).
    """
    ratios = {}
    for modele, g in hour0.groupby("modele"):
        g = g[(g["vent"].astype(float) >= config.VENT_MIN_FOILABLE)].dropna(subset=["rafales"])
        if len(g) >= config.N_MIN_SEGMENT:
            ratios[modele] = float((g["rafales"] / g["vent"]).median())
    if ratios:
        ratios["_defaut"] = float(np.median(list(ratios.values())))
    return ratios


# --------------------------------------------------------------------- poids

def calculer_poids(stats_globales: pd.DataFrame, stats_secteur: pd.DataFrame,
                   conf: pd.DataFrame, surv: pd.DataFrame, ratios: dict,
                   periode: str) -> dict:
    """Assemble data/poids_modeles.json (schéma documenté dans le README)."""
    modeles = {}
    for modele, g in stats_globales.groupby("modele"):
        entree = {"nom": config.MODELES[modele]["nom"], "horizons": {}}
        for _, ligne in g.iterrows():
            h = ligne["horizon"]
            poids_inv_mse = 1.0 / (ligne["rmse"] ** 2)
            entree["horizons"][h] = {
                "biais_nds": round(float(ligne["biais"]), 2),
                "rmse_nds": round(float(ligne["rmse"]), 2),
                "poids_brut": poids_inv_mse,
                "n": int(ligne["n"]),
            }
        sect = stats_secteur[stats_secteur["modele"] == modele]
        corrections = {}
        for _, ligne in sect.iterrows():
            corrections.setdefault(ligne["horizon"], {})[ligne["secteur_verite"]] = {
                "biais_nds": round(float(ligne["biais"]), 2), "n": int(ligne["n"])}
        if corrections:
            entree["biais_par_secteur"] = corrections
        if modele in ratios:
            entree["ratio_rafales"] = round(ratios[modele], 3)
        modeles[modele] = entree

    # Normaliser les poids par horizon (somme = 1 parmi les modèles présents)
    for h in config.HORIZONS:
        total = sum(m["horizons"][h]["poids_brut"]
                    for m in modeles.values() if h in m["horizons"])
        for m in modeles.values():
            if h in m["horizons"]:
                m["horizons"][h]["poids"] = round(m["horizons"][h].pop("poids_brut") / total, 4)

    fiabilite = {}
    for _, ligne in surv.iterrows():
        if ligne["vers"] == "réalisé":
            fiabilite[ligne["de"]] = {
                "taux_go_confirme": round(float(ligne["taux"]), 3),
                "ic95": [round(x, 3) for x in ligne["ic"]],
                "n": int(ligne["n_evaluables"]),
            }

    confusion = {}
    for _, ligne in conf.iterrows():
        confusion.setdefault(ligne["modele"], {})[ligne["horizon"]] = {
            "pod": None if pd.isna(ligne["pod"]) else round(float(ligne["pod"]), 3),
            "far": None if pd.isna(ligne["far"]) else round(float(ligne["far"]), 3),
            "pod_ic95": [round(x, 3) for x in ligne["pod_ic"]],
            "far_ic95": [round(x, 3) for x in ligne["far_ic"]],
        }

    return {
        "schema_version": 1,
        "genere_le": date.today().isoformat(),
        "periode_backtest": periode,
        "truth_source": config.TRUTH_SOURCE,
        "spot": {"latitude": config.LATITUDE, "longitude": config.LONGITUDE},
        "unites": "noeuds",
        "ratio_rafales_defaut": ratios.get("_defaut"),
        "modeles": modeles,
        "fiabilite_go_par_horizon": fiabilite,
        "confusion_par_modele": confusion,
    }


def principal():
    previsions, hour0, verite = charger()
    apparie = apparier(previsions, verite)
    periode = (f"{apparie['date_locale'].min()} à {apparie['date_locale'].max()}"
               " (mai-octobre)")

    stats_globales = biais_rmse(apparie)
    stats_secteur = biais_segmente(apparie, "secteur")
    stats_mois = biais_segmente(apparie, "mois")
    stats_tranche = biais_segmente(apparie, "tranche")
    conf = confusion_fenetres(apparie, verite)
    surv = survie_fenetres(apparie, verite)
    ratios = ratios_rafales(hour0)

    poids = calculer_poids(stats_globales, stats_secteur, conf, surv, ratios, periode)
    with open(config.FICHIER_POIDS, "w") as f:
        json.dump(poids, f, indent=2, ensure_ascii=False)

    return {"apparie": apparie, "verite": verite, "hour0": hour0,
            "stats_globales": stats_globales, "stats_secteur": stats_secteur,
            "stats_mois": stats_mois, "stats_tranche": stats_tranche,
            "confusion": conf, "survie": surv, "ratios": ratios, "poids": poids}


if __name__ == "__main__":
    res = principal()
    print(res["stats_globales"].to_string())
    print(res["confusion"].to_string())
    print(res["survie"].to_string())
    print("poids ->", config.FICHIER_POIDS)
