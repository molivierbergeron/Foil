"""Vérification croisée : les modèles notés contre un anémomètre RÉEL.

Pourquoi cette piste existe
---------------------------
La vérité du pipeline principal est la médiane hour-0 des modèles eux-mêmes.
Elle capture le synoptique, mais elle note chaque modèle contre la moyenne de
ses semblables — ce qui flatte les chiffres et, mesure faite, réordonne le
classement. Contre l'observation réelle de Lac Saint-Pierre sur la saison
2026 (19 640 paires), GFS passe 5e → 1er, HRDPS 6e → 2e, ICON 1er → 4e, et
l'erreur typique passe de ~1,2 nds à ~4,4 nds.

Ce module accumule donc, en parallèle et sans rien changer au modèle en
service, des paires « ce que le modèle prévoyait / ce que l'anémomètre a
mesuré » au point de la station. Trois usages :

1. Un classement des modèles indépendant des modèles.
2. La détection de dérive d'un fournisseur : si un centre change de version,
   ça se voit contre une mesure, alors que reports/derive.md ne peut pas le
   voir (son étalon bouge avec les modèles).
3. Une base comparable le jour où l'anémomètre du lac existera.

Ce que ce module ne fait PAS
----------------------------
Il n'écrit jamais dans data/poids_modeles.json, ne touche ni à verite.py ni
au recalibrage, et ne produit aucun verdict. Les biais mesurés ici sont ceux
de Lac Saint-Pierre, pas ceux du Lac Maskinongé : les transplanter serait
faux. Voir le commentaire de config.STATION_CROISEE.

Usage
-----
    python3 verification_croisee.py --rattraper 2024-05-01 2026-08-20
    python3 verification_croisee.py --rapport
    python3 verification_croisee.py --quotidien      # appelé par le cron
"""

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config
from openmeteo_client import appel
from telecharge import composantes_uv

DOSSIER = Path(config.DOSSIER_VERIF_CROISEE)
PAGE = 10000            # maximum accepté par l'API OGC d'ECCC
NOEUDS_PAR_KMH = 0.539957


# ------------------------------------------------------- observations ECCC

def observations(debut: str, fin: str) -> pd.DataFrame:
    """Vent horaire mesuré à la station, en nœuds et degrés météo.

    Unités de la source : vitesse en km/h entière, direction en DIZAINES de
    degrés (19 = 190°). La direction vaut 0 quand le vent est calme — c'est
    une absence de direction, pas un vent du nord : elle devient NaN.
    """
    lignes, offset = [], 0
    while True:
        donnees = appel(config.URL_CLIMATE_HOURLY, {
            "CLIMATE_IDENTIFIER": config.STATION_CROISEE["id"],
            "datetime": f"{debut} 00:00:00/{fin} 23:00:00",
            "limit": PAGE, "offset": offset, "f": "json", "sortby": "LOCAL_DATE",
        })
        traits = donnees.get("features", [])
        for trait in traits:
            p = trait["properties"]
            lignes.append({"time": p["UTC_DATE"],
                           "vitesse_kmh": p.get("WIND_SPEED"),
                           "direction_dizaines": p.get("WIND_DIRECTION")})
        if len(traits) < PAGE:
            break
        offset += PAGE

    if not lignes:
        return pd.DataFrame(columns=["time", "obs_vent", "obs_direction",
                                     "obs_u", "obs_v"])
    df = pd.DataFrame(lignes)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates("time").sort_values("time")
    df["obs_vent"] = df["vitesse_kmh"].astype("Float64").astype(float) * NOEUDS_PAR_KMH
    direction = df["direction_dizaines"].astype("Float64").astype(float) * 10.0
    df["obs_direction"] = direction.where(df["obs_vent"] > 0)
    u, v = composantes_uv(df["obs_vent"], df["obs_direction"])
    df["obs_u"], df["obs_v"] = u, v
    return df[["time", "obs_vent", "obs_direction", "obs_u", "obs_v"]].dropna(
        subset=["obs_vent"])


# ------------------------------------------- prévisions au point station

def previsions(debut: str, fin: str) -> pd.DataFrame:
    """Ce que chaque modèle prévoyait à 24/48/96 h AU POINT DE LA STATION.

    Même point que l'observation : la comparaison ne contient donc aucun
    écart de localisation, contrairement à une vérification qui mélangerait
    prévision au lac et mesure à 38 km.
    """
    lignes = []
    for modele, info in config.MODELES.items():
        variables = []
        for etiquette in info["horizons"]:
            suffixe = config.HORIZONS[etiquette]
            variables += [f"wind_speed_10m_{suffixe}",
                          f"wind_direction_10m_{suffixe}"]
        donnees = appel(config.URL_PREVIOUS_RUNS, {
            "latitude": config.STATION_CROISEE["latitude"],
            "longitude": config.STATION_CROISEE["longitude"],
            "hourly": ",".join(variables), "models": modele,
            "wind_speed_unit": "kn", "timezone": "UTC",
            "start_date": debut, "end_date": fin,
        })
        temps = pd.to_datetime(donnees["hourly"]["time"], utc=True)
        heures = donnees["hourly"]
        for etiquette in info["horizons"]:
            suffixe = config.HORIZONS[etiquette]
            cle = f"wind_speed_10m_{suffixe}"
            if cle not in heures:
                continue
            lignes.append(pd.DataFrame({
                "time": temps, "modele": modele, "horizon": etiquette,
                "vent": pd.array(heures[cle], dtype="Float64"),
                "direction": pd.array(
                    heures.get(f"wind_direction_10m_{suffixe}",
                               [None] * len(temps)), dtype="Float64"),
            }))
    if not lignes:
        return pd.DataFrame(columns=["time", "modele", "horizon", "vent", "direction"])
    return pd.concat(lignes, ignore_index=True).dropna(subset=["vent"])


def apparier(prev: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    """Jointure stricte sur l'heure UTC : une ligne = un modèle × un horizon."""
    if prev.empty or obs.empty:
        return pd.DataFrame()
    df = prev.merge(obs, on="time", how="inner")
    df["station"] = config.STATION_CROISEE["id"]
    return df


# ------------------------------------------------------- archive mensuelle

def mettre_a_jour(debut: str, fin: str) -> int:
    """Ajoute les lignes manquantes aux partitions mensuelles. Append-only.

    Mêmes règles que data/verification/ : on n'enlève ni ne modifie jamais
    une ligne existante, l'historique Git est la piste d'audit.
    """
    df = apparier(previsions(debut, fin), observations(debut, fin))
    if df.empty:
        return 0

    DOSSIER.mkdir(parents=True, exist_ok=True)
    df["mois"] = df["time"].dt.strftime("%Y-%m")
    ajoutees = 0
    for mois, bloc in df.groupby("mois"):
        chemin = DOSSIER / f"{mois}.parquet"
        bloc = bloc.drop(columns=["mois"])
        if chemin.exists():
            existant = pd.read_parquet(chemin)
            cle = ["time", "modele", "horizon"]
            deja = existant.set_index(cle).index
            bloc = bloc[~bloc.set_index(cle).index.isin(deja)]
            if bloc.empty:
                continue
            resultat = pd.concat([existant, bloc], ignore_index=True)
        else:
            resultat = bloc
        resultat = resultat.sort_values(["time", "modele", "horizon"])
        resultat.to_parquet(chemin, index=False)
        ajoutees += len(bloc)
    return ajoutees


def charger() -> pd.DataFrame:
    """Toutes les partitions accumulées, restreintes aux mois de saison."""
    partitions = sorted(DOSSIER.glob("*.parquet"))
    if not partitions:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p) for p in partitions], ignore_index=True)
    locale = df["time"].dt.tz_convert(config.FUSEAU_LOCAL)
    df["heure_locale"] = locale.dt.hour
    df["date_locale"] = locale.dt.date
    return df[locale.dt.month.isin(config.MOIS_SAISON)]


# ------------------------------------------------------------------ scores

def scores(df: pd.DataFrame, heures_de_jour: bool = True) -> pd.DataFrame:
    """Biais, RMSE et corrélation par modèle × horizon, contre la mesure.

    heures_de_jour : restreint aux heures navigables (8 h–20 h locales). Le
    vent nocturne suit une autre dynamique et ne sert à aucune décision ; le
    garder dilue le diagnostic.
    """
    if df.empty:
        return pd.DataFrame()
    if heures_de_jour:
        df = df[(df["heure_locale"] >= config.HEURE_DEBUT)
                & (df["heure_locale"] < config.HEURE_FIN)]
    lignes = []
    for (modele, horizon), g in df.groupby(["modele", "horizon"]):
        erreur = g["vent"].astype(float) - g["obs_vent"].astype(float)
        # La corrélation demande de la variance des deux côtés ; une fenêtre
        # trop courte ou un vent constant la rendrait indéfinie.
        correlation = float("nan")
        if len(g) >= config.N_MIN_SEGMENT and g["vent"].std() > 0 and g["obs_vent"].std() > 0:
            correlation = float(np.corrcoef(g["vent"].astype(float),
                                            g["obs_vent"].astype(float))[0, 1])
        lignes.append({
            "modele": modele, "horizon": horizon, "n": len(g),
            "biais_nds": float(erreur.mean()),
            "rmse_nds": float(np.sqrt((erreur ** 2).mean())),
            "correlation": correlation,
        })
    return (pd.DataFrame(lignes)
            .sort_values(["horizon", "rmse_nds"])
            .reset_index(drop=True))


def rapport(df: pd.DataFrame | None = None) -> str:
    """Rapport lisible, avec le rappel des limites en tête."""
    df = charger() if df is None else df
    station = config.STATION_CROISEE
    entete = [
        f"# Vérification croisée — {station['nom']} ({station['id']})",
        "",
        f"Anémomètre officiel à {station['distance_km']} km du spot, sur "
        "l'eau, horaire. Les modèles sont interrogés AU POINT DE LA STATION : "
        "aucune erreur de localisation dans la comparaison.",
        "",
        "**À ne pas confondre avec le modèle en service.** Cette piste "
        "n'alimente ni les poids, ni les verdicts. Les biais ci-dessous sont "
        "ceux de Lac Saint-Pierre — plan d'eau bien plus ouvert que le "
        "Maskinongé — et ne se transplantent pas. Ce qui se transporte "
        "raisonnablement, c'est le classement et la corrélation.",
        "",
    ]
    if df.empty:
        return "\n".join(entete + ["_Aucune donnée accumulée pour l'instant._"])

    s = scores(df)
    entete += [
        f"Période : {df['date_locale'].min()} à {df['date_locale'].max()} "
        f"({df['date_locale'].nunique()} jours, {len(df):,} paires)".replace(",", " "),
        "", "Heures navigables seulement (8 h–20 h locales).", "",
    ]
    for horizon in config.HORIZONS:
        bloc = s[s["horizon"] == horizon]
        if bloc.empty:
            continue
        entete += [f"## Horizon {horizon}", "",
                   "| Rang | Modèle | Biais (nds) | RMSE (nds) | Corrélation | n |",
                   "|---:|---|---:|---:|---:|---:|"]
        for rang, (_, r) in enumerate(bloc.iterrows(), start=1):
            nom = config.MODELES.get(r["modele"], {}).get("nom", r["modele"])
            corr = "—" if pd.isna(r["correlation"]) else f"{r['correlation']:.2f}"
            entete.append(f"| {rang} | {nom} | {r['biais_nds']:+.2f} | "
                          f"{r['rmse_nds']:.2f} | {corr} | {int(r['n'])} |")
        entete.append("")
    return "\n".join(entete)


# --------------------------------------------------------------------- CLI

def _fenetre_quotidienne(aujourdhui: date | None = None) -> tuple[str, str]:
    """Même fenêtre de rattrapage que le job principal : J-9 à J-3."""
    aujourdhui = aujourdhui or datetime.now(timezone.utc).date()
    return ((aujourdhui - timedelta(days=9)).isoformat(),
            (aujourdhui - timedelta(days=3)).isoformat())


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--rattraper", nargs=2, metavar=("DEBUT", "FIN"),
                   help="remplir rétroactivement une période (AAAA-MM-JJ)")
    g.add_argument("--quotidien", action="store_true",
                   help="fenêtre J-9 à J-3, appelée par le cron")
    g.add_argument("--rapport", action="store_true",
                   help="écrire reports/verification_croisee.md")
    args = p.parse_args(argv)

    if args.rapport:
        chemin = Path("reports/verification_croisee.md")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(rapport() + "\n")
        print(f"-> {chemin}")
        return 0

    debut, fin = args.rattraper if args.rattraper else _fenetre_quotidienne()
    # Une saison à la fois : les fenêtres hors saison ne servent à rien au
    # diagnostic et alourdiraient l'archive pour rien.
    total = 0
    for annee in range(int(debut[:4]), int(fin[:4]) + 1):
        d = max(debut, f"{annee}-{config.MOIS_SAISON[0]:02d}-01")
        f = min(fin, f"{annee}-{config.MOIS_SAISON[-1]:02d}-31")
        if d > f:
            continue
        n = mettre_a_jour(d, f)
        total += n
        print(f"  {d} → {f} : {n} lignes ajoutées")
    print(f"Total : {total} lignes dans {DOSSIER}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
