"""Tests du modèle candidat (candidat.py).

Sans réseau : les scores croisés sont simulés. Ce qui est vérifié, c'est la
promesse du candidat — il ne change QUE les poids, il les tire des RMSE
mesurés au réel, et il n'entre jamais en service tout seul.

Exécution : python3 tests/test_candidat.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import candidat
import config
import verification_croisee
import versions

echecs = []


def verifier(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  ÉCHEC {message}")
        echecs.append(message)


def poids_actifs() -> dict:
    """Un modèle actif minimal : deux modèles, poids volontairement à l'envers
    de ce que la mesure réelle dira, pour que l'inversion soit visible."""
    return {
        "schema_version": 2, "genere_le": "2026-08-01",
        "periode_backtest": "2024-05-01 à 2026-07-31 (mai-octobre)",
        "truth_source": "median_hour0", "unites": "noeuds",
        "sport": {"vent_min": 7.0}, "ratio_rafales_defaut": 1.5,
        "modeles": {
            "gfs_global": {"nom": "GFS", "horizons": {
                "24h": {"biais_nds": 0.43, "rmse_nds": 1.59, "poids": 0.20, "n": 5000}}},
            "icon_global": {"nom": "ICON", "horizons": {
                "24h": {"biais_nds": 0.05, "rmse_nds": 1.17, "poids": 0.80, "n": 5000}}},
        },
        "fiabilite_go_par_horizon": {}, "confusion_par_modele": {},
    }


class Bac:
    """Registre jetable + scores croisés simulés."""

    def __init__(self, scores, n=6000):
        self.scores, self.n = scores, n

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sauve = (versions.DOSSIER, versions.REGISTRE, versions.COPIE_DASHBOARD,
                      versions.COPIE_CANDIDAT, config.FICHIER_POIDS,
                      verification_croisee.charger, verification_croisee.scores)
        versions.DOSSIER = self.tmp / "modeles"
        versions.REGISTRE = versions.DOSSIER / "registre.json"
        (self.tmp / "docs").mkdir()
        versions.COPIE_DASHBOARD = self.tmp / "docs" / "poids_modeles.json"
        versions.COPIE_CANDIDAT = self.tmp / "docs" / "poids_candidat.json"
        config.FICHIER_POIDS = str(self.tmp / "poids_modeles.json")

        dates = pd.date_range("2026-05-01", periods=100, freq="D").date
        cadre = pd.DataFrame({"date_locale": list(dates) * 200})[:self.n]
        verification_croisee.charger = lambda: cadre
        table = pd.DataFrame(self.scores)
        verification_croisee.scores = lambda df, heures_de_jour=True: table

        self.actif = versions.enregistrer(poids_actifs(), origine="test")
        return self

    def __exit__(self, *_):
        (versions.DOSSIER, versions.REGISTRE, versions.COPIE_DASHBOARD,
         versions.COPIE_CANDIDAT, config.FICHIER_POIDS,
         verification_croisee.charger, verification_croisee.scores) = self.sauve
        shutil.rmtree(self.tmp, ignore_errors=True)


# Au réel, GFS est nettement meilleur qu'ICON — l'inverse de ce que dit le
# modèle actif ci-dessus. C'est exactement le cas mesuré à Lac Saint-Pierre.
SCORES = [
    {"modele": "gfs_global", "horizon": "24h", "n": 5748,
     "biais_nds": -1.42, "rmse_nds": 4.08, "correlation": 0.72},
    {"modele": "icon_global", "horizon": "24h", "n": 5748,
     "biais_nds": -2.97, "rmse_nds": 4.95, "correlation": 0.71},
]


def test_poids_suivent_la_mesure():
    print("\nLes poids suivent la compétence mesurée")
    with Bac(SCORES):
        c, _ = candidat.construire()
        gfs = c["modeles"]["gfs_global"]["horizons"]["24h"]["poids"]
        icon = c["modeles"]["icon_global"]["horizons"]["24h"]["poids"]
        verifier(gfs > icon,
                 f"GFS (RMSE réel 4,08) pèse plus qu'ICON (4,95) : "
                 f"{gfs:.0%} vs {icon:.0%}")
        verifier(abs(gfs + icon - 1.0) < 0.01, "les poids somment à 1")
        # 1/RMSE² : (1/4.08²) / (1/4.08² + 1/4.95²) ≈ 0,595
        verifier(abs(gfs - 0.595) < 0.01,
                 f"la formule est bien 1/RMSE² (attendu ~0,595, obtenu {gfs:.3f})")


def test_biais_inchanges():
    print("\nLes biais ne bougent pas")
    with Bac(SCORES):
        c, _ = candidat.construire()
        actif = poids_actifs()
        for m in ("gfs_global", "icon_global"):
            verifier(c["modeles"][m]["horizons"]["24h"]["biais_nds"]
                     == actif["modeles"][m]["horizons"]["24h"]["biais_nds"],
                     f"biais de {m} repris tel quel du modèle actif")
        verifier(c["modeles"]["gfs_global"]["horizons"]["24h"]["rmse_reel_nds"] == 4.08,
                 "le RMSE réel est tracé dans le jeu de poids")


def test_echantillon_trop_mince():
    print("\nÉchantillon trop mince")
    maigre = [dict(SCORES[0], n=10), dict(SCORES[1], n=10)]
    with Bac(maigre):
        c, metriques = candidat.construire()
        verifier(metriques["poids_remplaces"] == [],
                 "aucun poids remplacé sous le seuil d'échantillon")
        verifier(c["modeles"]["icon_global"]["horizons"]["24h"]["poids"] == 0.80,
                 "le poids de l'actif est conservé plutôt qu'un chiffre bruyant")


def test_candidat_nentre_pas_en_service():
    print("\nLe candidat ne prend jamais le service tout seul")
    with Bac(SCORES) as bac:
        version = candidat.principal.__wrapped__() if hasattr(
            candidat.principal, "__wrapped__") else candidat.principal()
        del version
        verifier(versions.actif() == bac.actif,
                 f"l'actif est inchangé ({bac.actif})")
        verifier(versions.candidat() is not None
                 and versions.candidat() != bac.actif,
                 "un candidat distinct est enregistré")
        verifier(versions.COPIE_CANDIDAT.exists(),
                 "le candidat est publié dans docs/poids_candidat.json")
        publie_actif = json.loads(versions.COPIE_DASHBOARD.read_text())
        verifier(publie_actif["modeles"]["icon_global"]["horizons"]["24h"]["poids"] == 0.80,
                 "la copie du dashboard porte toujours les poids de l'actif")

        # Promotion explicite : là seulement le candidat prend le service.
        promu = versions.candidat()
        versions.activer(promu, raison="essai concluant")
        verifier(versions.actif() == promu, "après --activer, le candidat est actif")
        verifier(versions.candidat() is None,
                 "il cesse d'être « à l'essai » une fois promu")
        verifier((versions.DOSSIER / bac.actif / "poids.json").exists(),
                 "l'ancien actif reste archivé, donc restaurable")


def test_sans_donnees_croisees():
    print("\nSans données croisées")
    with Bac([], n=0):
        verification_croisee.charger = lambda: pd.DataFrame()
        try:
            candidat.construire()
            verifier(False, "construire() doit refuser de fabriquer un candidat")
        except RuntimeError as exc:
            verifier("rattrapage" in str(exc).lower() or "Rattrapage" in str(exc),
                     "le message dit comment obtenir les données manquantes")


if __name__ == "__main__":
    test_poids_suivent_la_mesure()
    test_biais_inchanges()
    test_echantillon_trop_mince()
    test_candidat_nentre_pas_en_service()
    test_sans_donnees_croisees()

    print()
    if echecs:
        print(f"{len(echecs)} ÉCHEC(S)")
        raise SystemExit(1)
    print("Tous les tests du candidat passent.")
