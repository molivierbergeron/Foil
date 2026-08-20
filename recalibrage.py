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
import versions

JOURS_TEST = 60          # validation temporelle : les 60 derniers jours
POIDS_SAISON_COURANTE = 2.0


# Le chargement et les métriques d'ensemble vivent dans backtest.py : le
# versionnage (versions.py --comparer) évalue les mêmes quantités sur les
# mêmes données, il ne doit pas y avoir deux implémentations qui dérivent.
charger_apparie_complet = backtest.charger_apparie_complet
rmse_ensemble = backtest.rmse_ensemble


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

    nouvelle_version = None
    if applique:
        # Les poids livrés sont recalculés sur TOUTE la fenêtre (train + test)
        poids_final = construire_poids(apparie, hour0)
        # versions.enregistrer archive, active, et installe les deux copies
        # (data/poids_modeles.json et docs/poids_modeles.json). Si les chiffres
        # sont identiques à la version active, aucune version n'est créée.
        nouvelle_version = versions.enregistrer(
            poids_final,
            origine="recalibrage",
            donnees_jusqu_au=dates.max().date(),
            n_apparie=int(len(apparie)),
            metriques={
                "rmse_ensemble_courant": rmse_courant,
                "rmse_ensemble_candidat": rmse_candidat,
                "fenetre_test_jours": JOURS_TEST,
                "compare_a": versions.actif(),
            },
        )
    else:
        # Poids conservés : on republie quand même la copie dashboard, qui
        # peut avoir divergé (édition manuelle, retour arrière non propagé).
        versions.republier_actif()

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

    # La version est glissée dans la cellule « Décision » plutôt qu'en colonne
    # supplémentaire : le tableau existant a 4 colonnes et reste lisible.
    if applique:
        decision = f"appliqué → `{nouvelle_version}`"
    else:
        decision = f"**conservé** (candidat moins bon) — `{versions.actif()}` reste active"
    with open(chemin, "a") as f:
        f.write(f"| {datetime.now(timezone.utc).date().isoformat()} "
                f"| {fmt(rmse_courant)} | {fmt(rmse_candidat)} | {decision} |\n")

    print(f"RMSE ensemble courant  {rmse_courant}")
    print(f"RMSE ensemble candidat {rmse_candidat}")
    print(f"Décision : {decision}")
    print(f"Version active : {versions.actif()}")


if __name__ == "__main__":
    principal()
