"""Tests du versionnage des modèles (versions.py) et de la vérité gelée.

Sans réseau : tout se joue sur des jeux de poids fabriqués, dans un dossier
temporaire. Exécution : python3 tests/test_versions.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import verite
import versions

echecs = []


def verifier(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  ÉCHEC {message}")
        echecs.append(message)


def poids_factices(genere_le="2026-01-01", biais=0.5, periode=None) -> dict:
    return {
        "schema_version": 2,
        "genere_le": genere_le,
        "periode_backtest": periode or "2024-05-01 à 2025-12-31 (mai-octobre)",
        "truth_source": "median_hour0",
        "verite": {"version": config.VERITE_VERSION,
                   "modeles": list(config.MODELES_VERITE)},
        "unites": "noeuds",
        "sport": {"vent_min": 7.0},
        "ratio_rafales_defaut": 1.5,
        "modeles": {
            "gem_global": {"nom": "GEM global", "horizons": {
                "24h": {"biais_nds": biais, "rmse_nds": 1.5, "poids": 0.5, "n": 100}}},
            "icon_global": {"nom": "ICON", "horizons": {
                "24h": {"biais_nds": -biais, "rmse_nds": 1.2, "poids": 0.5, "n": 100}}},
        },
        "fiabilite_go_par_horizon": {},
        "confusion_par_modele": {},
    }


class DossierTemporaire:
    """Redirige versions.py et config.FICHIER_POIDS vers un dossier jetable."""

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sauve = (versions.DOSSIER, versions.REGISTRE,
                      versions.COPIE_DASHBOARD, config.FICHIER_POIDS)
        versions.DOSSIER = self.tmp / "modeles"
        versions.REGISTRE = versions.DOSSIER / "registre.json"
        (self.tmp / "docs").mkdir()
        versions.COPIE_DASHBOARD = self.tmp / "docs" / "poids_modeles.json"
        config.FICHIER_POIDS = str(self.tmp / "poids_modeles.json")
        return self.tmp

    def __exit__(self, *_):
        (versions.DOSSIER, versions.REGISTRE,
         versions.COPIE_DASHBOARD, config.FICHIER_POIDS) = self.sauve
        shutil.rmtree(self.tmp, ignore_errors=True)


def test_enregistrer_et_publier():
    print("\nEnregistrement d'une version")
    with DossierTemporaire() as tmp:
        v = versions.enregistrer(poids_factices(), origine="test",
                                 donnees_jusqu_au="2025-12-31", n_apparie=42)
        verifier(v == "v1-2026-01-01", f"identifiant dérivé de genere_le ({v})")
        verifier(versions.actif() == v, "la version créée devient active")
        verifier((versions.DOSSIER / v / "poids.json").exists(),
                 "le jeu de poids est archivé")
        verifier(Path(config.FICHIER_POIDS).exists(),
                 "la copie de travail est installée")
        verifier(versions.COPIE_DASHBOARD.exists(),
                 "la copie dashboard est installée")
        verifier(versions.meta(v)["donnees_jusqu_au"] == "2025-12-31",
                 "la borne de calibration est mémorisée")
        verifier(versions.meta(v)["n_apparie"] == 42,
                 "la taille d'échantillon est mémorisée")
        del tmp


def test_pas_de_doublon():
    print("\nDeux enregistrements identiques ne créent qu'une version")
    with DossierTemporaire():
        v1 = versions.enregistrer(poids_factices(), origine="test")
        # Même contenu calibré, date de génération différente : c'est le même
        # modèle, il ne doit pas occuper une deuxième version.
        v2 = versions.enregistrer(poids_factices(genere_le="2026-02-02"),
                                  origine="test")
        verifier(v1 == v2, "contenu identique -> même version réutilisée")
        verifier(len(versions.registre()["versions"]) == 1,
                 "une seule version au registre")

        v3 = versions.enregistrer(poids_factices(genere_le="2026-03-03", biais=0.9),
                                  origine="test")
        verifier(v3 != v1, "contenu différent -> nouvelle version")
        verifier(len(versions.registre()["versions"]) == 2,
                 "deux versions au registre")


def test_retour_arriere():
    print("\nRetour arrière")
    with DossierTemporaire():
        v1 = versions.enregistrer(poids_factices(biais=0.5), origine="test")
        v2 = versions.enregistrer(poids_factices(genere_le="2026-02-02", biais=0.9),
                                  origine="test")
        verifier(versions.actif() == v2, "v2 active après création")

        versions.activer(v1, raison="v2 sur-prévoit")
        verifier(versions.actif() == v1, "v1 redevient active")

        publie = json.loads(Path(config.FICHIER_POIDS).read_text())
        verifier(publie["modeles"]["gem_global"]["horizons"]["24h"]["biais_nds"] == 0.5,
                 "la copie de travail contient bien les poids de v1")
        dashboard = json.loads(versions.COPIE_DASHBOARD.read_text())
        verifier(dashboard == publie, "la copie dashboard suit le retour arrière")

        verifier((versions.DOSSIER / v2 / "poids.json").exists(),
                 "v2 reste archivée (rien n'est détruit)")
        # La raison journalisée porte aussi la version remplacée, d'où le
        # test par inclusion : « v2 sur-prévoit — remplace v2-2026-02-02 ».
        raisons = [a["raison"] for a in versions.registre()["activations"]]
        verifier(any("v2 sur-prévoit" in r for r in raisons),
                 "la bascule est journalisée avec sa raison")
        verifier(any(v2 in r for r in raisons if "v2 sur-prévoit" in r),
                 "et avec la version qu'elle remplace")


def test_version_inconnue():
    print("\nVersion inconnue")
    with DossierTemporaire():
        versions.enregistrer(poids_factices(), origine="test")
        try:
            versions.activer("v9-1999-01-01")
            verifier(False, "activer() doit refuser une version inconnue")
        except KeyError as exc:
            verifier("v9-1999-01-01" in str(exc),
                     "le message d'erreur nomme la version demandée")


def test_amorcage():
    print("\nAmorçage depuis un dépôt sans registre")
    with DossierTemporaire():
        Path(config.FICHIER_POIDS).write_text(json.dumps(
            poids_factices(genere_le="2026-07-15",
                           periode="2024-05-01 à 2026-07-12 (mai-octobre)")))
        reg = versions.registre()
        verifier(len(reg["versions"]) == 1,
                 "les poids en production sont importés comme v1")
        verifier(reg["versions"][0]["origine"] == "import-initial",
                 "l'origine dit que c'est un import")
        verifier(reg["versions"][0]["donnees_jusqu_au"] == "2026-07-12",
                 "la borne de calibration est déduite de periode_backtest")


def test_fenetre_hors_echantillon():
    print("\nChoix de la fenêtre d'évaluation")
    with DossierTemporaire():
        a = versions.enregistrer(poids_factices(), origine="test",
                                 donnees_jusqu_au="2026-05-01")
        b = versions.enregistrer(poids_factices(genere_le="2026-06-06", biais=0.9),
                                 origine="test", donnees_jusqu_au="2026-06-15")
        borne, avert = versions._fenetre_hors_echantillon(a, b)
        verifier(borne == "2026-06-15",
                 "la borne est la PLUS TARDIVE des deux calibrations")
        verifier(avert == [], "aucun avertissement quand les deux bornes sont connues")

        c = versions.enregistrer(poids_factices(genere_le="2026-07-07", biais=1.3),
                                 origine="test", donnees_jusqu_au=None)
        borne, avert = versions._fenetre_hors_echantillon(a, c)
        verifier(borne is None, "borne inconnue si une version ne la déclare pas")
        verifier(len(avert) == 1 and c in avert[0],
                 "un avertissement nomme la version en cause")


def test_verite_gelee():
    print("\nVérité gelée (P0)")
    verifier(set(config.MODELES_VERITE) <= set(config.MODELES),
             "MODELES_VERITE est inclus dans MODELES")
    verifier(len(config.MODELES_VERITE) == 6,
             "la vérité repose bien sur 6 modèles")

    # hour-0 factice : les 6 modèles de vérité + un modèle de prévision en plus
    heures = pd.date_range("2026-07-01", periods=6, freq="h", tz="UTC")
    lignes = []
    for modele in list(config.MODELES_VERITE) + ["gfs_hrrr"]:
        # Le modèle intrus annonce 100 nds : s'il entrait dans la médiane,
        # la vérité en serait visiblement tirée vers le haut.
        vent = 100.0 if modele == "gfs_hrrr" else 10.0
        lignes.append(pd.DataFrame({
            "time": heures, "modele": modele, "vent": vent, "direction": 180.0,
            "rafales": vent * 1.5, "vent80": vent, "rayonnement": 300.0,
            "nebulosite": 50.0, "temp2m": 20.0, "temp80": 19.0,
            "u": 0.0, "v": vent}))
    hour0 = pd.concat(lignes, ignore_index=True)

    v = verite.construire_verite(hour0)
    verifier(bool((v["vent"] == 10.0).all()),
             "un modèle de prévision hors vérité ne déplace pas la vérité")
    verifier(bool((v["n_modeles"] == 6).all()),
             "la médiane porte sur exactement 6 modèles")
    verifier(verite.composition_verite(hour0) == list(config.MODELES_VERITE),
             "composition_verite() liste les 6 modèles présents")

    # Modèle de vérité manquant : strict échoue, non-strict avertit et continue
    ampute = hour0[hour0["modele"] != "icon_global"]
    try:
        verite.construire_verite(ampute)
        verifier(False, "strict=True doit refuser une vérité amputée")
    except ValueError as exc:
        verifier("icon_global" in str(exc),
                 "le message nomme le modèle de vérité manquant")
    v2 = verite.construire_verite(ampute, strict=False)
    verifier(bool((v2["n_modeles"] == 5).all()),
             "strict=False continue sur 5 modèles (job quotidien)")
    verifier(verite.composition_verite(ampute) == [
        m for m in config.MODELES_VERITE if m != "icon_global"],
        "la composition réelle exclut le modèle manquant")


def test_crons_committent_tout_ce_qui_est_ecrit():
    """Les workflows stagent-ils tous les chemins que le code écrit ?

    Ce test existe parce que la classe de bug s'est déjà produite : le
    recalibrage écrivait docs/poids_modeles.json sans que le workflow le
    stage, donc le premier recalibrage appliqué aurait laissé au dashboard
    public des biais périmés pour toujours — sans aucun symptôme visible.
    Le versionnage ajoute data/modeles/, qui a exactement le même risque :
    le runner part d'un checkout neuf, donc un registre non commité est un
    registre reconstruit de zéro chaque semaine.
    """
    racine = Path(__file__).resolve().parent.parent
    attendus = {
        "recalibrage.yml": ["data/poids_modeles.json", "docs/poids_modeles.json",
                            "docs/poids_candidat.json", "docs/comparaison.json",
                            "data/modeles", "reports/derive.md"],
        "quotidien.yml": ["data/verification", "data/verification_croisee",
                          "data/forecast.json", "docs/comparaison.json"],
    }
    for fichier, chemins in attendus.items():
        texte = (racine / ".github/workflows" / fichier).read_text()
        lignes_add = [l for l in texte.splitlines() if "git add" in l]
        # La commande peut être coupée sur plusieurs lignes (\ en fin de ligne)
        bloc = texte[texte.index("git add"):] if lignes_add else ""
        for chemin in chemins:
            verifier(chemin in bloc.split("git diff")[0],
                     f"{fichier} stage {chemin}")


def test_empreinte():
    print("\nEmpreinte du contenu calibré")
    a = poids_factices(genere_le="2026-01-01")
    b = poids_factices(genere_le="2026-09-09")
    verifier(versions.empreinte(a) == versions.empreinte(b),
             "la date de génération ne change pas l'empreinte")
    verifier(versions.empreinte(a) != versions.empreinte(poids_factices(biais=0.9)),
             "un biais différent change l'empreinte")


if __name__ == "__main__":
    test_enregistrer_et_publier()
    test_pas_de_doublon()
    test_retour_arriere()
    test_version_inconnue()
    test_amorcage()
    test_fenetre_hors_echantillon()
    test_verite_gelee()
    test_crons_committent_tout_ce_qui_est_ecrit()
    test_empreinte()

    print()
    if echecs:
        print(f"{len(echecs)} ÉCHEC(S)")
        raise SystemExit(1)
    print("Tous les tests de versionnage passent.")
