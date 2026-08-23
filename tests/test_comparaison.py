"""Tests du générateur de la vue « modèles vs réalité » (comparaison.py).

Sans réseau : les scores croisés sont simulés. Ce qui est vérifié, c'est que
les deux notations sont bien mises en regard, que les rangs sont calculés
indépendamment de chaque côté, et que le JSON produit est lisible tel quel par
le navigateur (pas de NaN, qui n'est pas du JSON valide).

Exécution : python3 tests/test_comparaison.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import comparaison
import verification_croisee

echecs = []


def verifier(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  ÉCHEC {message}")
        echecs.append(message)


class ScoresSimules:
    """Remplace la lecture des partitions par des scores fabriqués."""

    def __init__(self, lignes, jours=112, paires=18256):
        self.lignes = lignes
        self.jours, self.paires = jours, paires

    def __enter__(self):
        self.sauve = (verification_croisee.charger, verification_croisee.scores)
        dates = pd.date_range("2026-05-01", periods=self.jours, freq="D").date
        cadre = pd.DataFrame({"date_locale": list(dates) * 200})[:self.paires]
        verification_croisee.charger = lambda: cadre
        table = pd.DataFrame(self.lignes)
        verification_croisee.scores = lambda df, heures_de_jour=True: table
        return self

    def __exit__(self, *_):
        verification_croisee.charger, verification_croisee.scores = self.sauve


def test_rangs_independants():
    print("\nRangs calculés séparément pour chaque étalon")
    # GFS est le meilleur contre la mesure ; ICON est le meilleur contre le
    # consensus (c'est ce que dit poids_modeles.json en production).
    lignes = [
        {"modele": "gfs_global", "horizon": "24h", "n": 3273,
         "biais_nds": -1.25, "rmse_nds": 4.40, "correlation": 0.70},
        {"modele": "icon_global", "horizon": "24h", "n": 3273,
         "biais_nds": -2.69, "rmse_nds": 5.03, "correlation": 0.70},
    ]
    with ScoresSimules(lignes):
        d = comparaison.construire()

    h24 = {e["modele"]: e for e in d["horizons"]["24h"]}
    verifier(h24["gfs_global"]["reel"]["rang"] == 1,
             "GFS est 1er contre la vraie mesure")
    verifier(h24["icon_global"]["reel"]["rang"] == 2,
             "ICON est 2e contre la vraie mesure")
    verifier(h24["icon_global"]["officiel"]["rang"]
             < h24["gfs_global"]["officiel"]["rang"],
             "ICON devance GFS contre le consensus (rangs bien indépendants)")
    verifier(h24["gfs_global"]["officiel"]["poids"] is not None,
             "le poids en service est repris pour comparaison")


def test_modeles_sans_mesure():
    print("\nModèles pas encore mesurés")
    with ScoresSimules([]):
        d = comparaison.construire()
    h24 = d["horizons"]["24h"]
    verifier(len(h24) > 0, "les modèles restent listés sans données croisées")
    verifier(all(e["reel"] is None for e in h24),
             "la colonne « vraie mesure » est nulle, pas inventée")
    verifier(all(e["officiel"] is not None for e in h24),
             "la colonne « consensus » reste remplie")
    verifier(d["periode"] is not None,
             "la période est renseignée dès qu'il y a des lignes")


def test_json_serialisable():
    print("\nJSON réellement lisible par le navigateur")
    lignes = [{"modele": "gfs_global", "horizon": "24h", "n": 12,
               # Échantillon trop mince : scores() renvoie NaN. NaN n'est PAS
               # du JSON valide — JSON.parse() échouerait côté navigateur.
               "biais_nds": -1.25, "rmse_nds": 4.40, "correlation": float("nan")}]
    with ScoresSimules(lignes):
        d = comparaison.construire()
    texte = json.dumps(d, ensure_ascii=False, allow_nan=False)
    verifier("NaN" not in texte, "aucun NaN dans la sortie")
    rejoue = json.loads(texte)
    entree = next(e for e in rejoue["horizons"]["24h"] if e["modele"] == "gfs_global")
    verifier(entree["reel"]["correlation"] is None,
             "une corrélation indéfinie devient null")


def test_versions_et_actif():
    print("\nHistorique des versions")
    with ScoresSimules([]):
        d = comparaison.construire()
    verifier(len(d["versions"]) >= 1, "au moins une version est publiée")
    verifier(d["modele_actif"] is not None,
             "la version active est nommée (elle est affichée en pied de page)")
    verifier(all("version" in v and "origine" in v for v in d["versions"]),
             "chaque version porte son identifiant et son origine")


def test_hors_portee():
    print("\nModèle hors portée à une échéance")
    with ScoresSimules([]):
        d = comparaison.construire()
    h96 = {e["modele"] for e in d["horizons"]["96h"]}
    verifier("gem_hrdps_continental" not in h96,
             "HRDPS (portée 48 h) n'apparaît pas à l'échéance 96 h")


if __name__ == "__main__":
    test_rangs_independants()
    test_modeles_sans_mesure()
    test_json_serialisable()
    test_versions_et_actif()
    test_hors_portee()

    print()
    if echecs:
        print(f"{len(echecs)} ÉCHEC(S)")
        raise SystemExit(1)
    print("Tous les tests de comparaison passent.")
