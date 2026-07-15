"""Recalibrage hebdomadaire de data/poids_modeles.json (GitHub Actions).

Fenêtre glissante : tout l'historique apparié (backtest figé + partitions de
vérification accumulées), la saison courante pesant double dans le calcul des
biais/RMSE.

Garde-fou : les nouveaux poids ne sont appliqués que s'ils font au moins
aussi bien que les poids courants en validation temporelle — l'ensemble
corrigé-pondéré est évalué (RMSE) sur les 60 derniers jours, jamais vus par
le calcul des poids candidats. Sinon, poids conservés et noté.

Chaque exécution ajoute une ligne à reports/derive.md : la dérive d'un modèle
(changement de version chez le fournisseur) y devient visible.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest
import config

JOURS_TEST = 60          # validation temporelle : les 60 derniers jours
POIDS_SAISON_COURANTE = 2.0


def charger_apparie_complet() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backtest figé + partitions de vérification, dédupliqué."""
    previsions, hour0, verite = backtest.charger()
    apparie = backtest.apparier(previsions, verite)

    partitions = sorted(Path("data/verification").glob("*.parquet"))
    if partitions:
        verif = pd.concat([pd.read_parquet(p) for p in partitions], ignore_index=True)
        temps_local = verif["time"].dt.tz_convert(config.FUSEAU_LOCAL)
        verif["heure_locale"] = temps_local.dt.hour
        verif["date_locale"] = temps_local.dt.date
        verif["mois"] = temps_local.dt.month
        from verite import secteur
        verif["secteur_verite"] = secteur(verif["verite_direction"])
        verif = verif[verif["mois"].isin(config.MOIS_SAISON)]
        colonnes = [c for c in apparie.columns if c in verif.columns]
        apparie = (pd.concat([apparie[colonnes], verif[colonnes]], ignore_index=True)
                   .drop_duplicates(subset=["time", "modele", "horizon"]))
    return apparie, hour0


def _stats_ponderees(g: pd.DataFrame) -> pd.Series:
    err = (g["vent"] - g["verite_vent"]).astype(float)
    w = g["_poids_ligne"].astype(float)
    return pd.Series({
        "n": len(g),
        "biais": float((err * w).sum() / w.sum()),
        "rmse": float(np.sqrt((err ** 2 * w).sum() / w.sum())),
    })


def biais_rmse_ponderes(apparie: pd.DataFrame) -> pd.DataFrame:
    jour = apparie[(apparie["heure_locale"] >= config.HEURE_DEBUT)
                   & (apparie["heure_locale"] < config.HEURE_FIN)].copy()
    annee_courante = datetime.now(timezone.utc).year
    annees = pd.to_datetime(jour["date_locale"].astype(str)).dt.year
    jour["_poids_ligne"] = np.where(annees == annee_courante,
                                    POIDS_SAISON_COURANTE, 1.0)
    return (jour.groupby(["modele", "horizon"])
            .apply(_stats_ponderees, include_groups=False).reset_index())


def rmse_ensemble(test: pd.DataFrame, poids: dict) -> dict:
    """RMSE de l'ensemble corrigé-pondéré par horizon, selon un jeu de poids."""
    resultats = {}
    for horizon in config.HORIZONS:
        rows = test[test["horizon"] == horizon]
        if rows.empty:
            continue
        morceaux = []
        for modele, g in rows.groupby("modele"):
            info = poids["modeles"].get(modele, {}).get("horizons", {}).get(horizon)
            if info is None:
                continue
            g = g.copy()
            g["corrige"] = g["vent"].astype(float) - info["biais_nds"]
            g["w"] = info["poids"]
            morceaux.append(g[["time", "corrige", "w", "verite_vent"]])
        df = pd.concat(morceaux, ignore_index=True)
        agg = df.groupby("time").apply(
            lambda x: pd.Series({
                "ens": float((x["corrige"] * x["w"]).sum() / x["w"].sum()),
                "verite": float(x["verite_vent"].iloc[0])}),
            include_groups=False)
        resultats[horizon] = float(np.sqrt(((agg["ens"] - agg["verite"]) ** 2).mean()))
    return resultats


def construire_poids(apparie: pd.DataFrame, hour0: pd.DataFrame) -> dict:
    stats = biais_rmse_ponderes(apparie)
    stats_secteur = backtest.biais_segmente(apparie, "secteur")
    verite_df = (apparie[["time", "verite_vent"]].drop_duplicates("time")
                 .rename(columns={"verite_vent": "vent"}).set_index("time"))
    conf = backtest.confusion_fenetres(apparie, verite_df)
    surv = backtest.survie_fenetres(apparie, verite_df)
    ratios = backtest.ratios_rafales(hour0)
    periode = f"{apparie['date_locale'].min()} à {apparie['date_locale'].max()} (mai-octobre)"
    return backtest.calculer_poids(stats, stats_secteur, conf, surv, ratios, periode)


def principal():
    apparie, hour0 = charger_apparie_complet()
    dates = pd.to_datetime(apparie["date_locale"].astype(str))
    coupure = dates.max() - pd.Timedelta(days=JOURS_TEST)
    train, test = apparie[dates <= coupure], apparie[dates > coupure]

    with open(config.FICHIER_POIDS) as f:
        poids_courants = json.load(f)
    candidat_train = construire_poids(train, hour0)

    rmse_courant = rmse_ensemble(test, poids_courants)
    rmse_candidat = rmse_ensemble(test, candidat_train)
    moy_courant = float(np.mean(list(rmse_courant.values())))
    moy_candidat = float(np.mean(list(rmse_candidat.values())))
    applique = moy_candidat <= moy_courant

    if applique:
        # Les poids livrés sont recalculés sur TOUTE la fenêtre (train + test)
        poids_final = construire_poids(apparie, hour0)
        with open(config.FICHIER_POIDS, "w") as f:
            json.dump(poids_final, f, indent=2, ensure_ascii=False)

    chemin = Path("reports/derive.md")
    if not chemin.exists():
        chemin.write_text(
            "# Dérive des modèles — journal des recalibrages\n\n"
            "Chaque semaine, des poids candidats sont calculés sur la fenêtre\n"
            "glissante (saison courante pesant double) et comparés aux poids\n"
            "courants sur les 60 derniers jours (validation temporelle, RMSE de\n"
            "l'ensemble corrigé-pondéré, en nds). Ils ne sont appliqués que\n"
            "s'ils font au moins aussi bien. Une dérive soudaine d'un modèle\n"
            "(changement de version chez le fournisseur) se verra ici.\n\n"
            "| Date | RMSE courant (24/48/96 h) | RMSE candidat | Décision |\n"
            "|---|---|---|---|\n")

    def fmt(r):
        return "/".join(f"{r.get(h, float('nan')):.2f}" for h in config.HORIZONS)

    decision = "appliqué" if applique else "**conservé** (candidat moins bon)"
    with open(chemin, "a") as f:
        f.write(f"| {datetime.now(timezone.utc).date().isoformat()} "
                f"| {fmt(rmse_courant)} | {fmt(rmse_candidat)} | {decision} |\n")

    print(f"RMSE ensemble courant  {rmse_courant}")
    print(f"RMSE ensemble candidat {rmse_candidat}")
    print(f"Décision : {decision}")


if __name__ == "__main__":
    principal()
