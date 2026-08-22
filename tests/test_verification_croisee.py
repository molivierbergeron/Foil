"""Tests de la vérification croisée (verification_croisee.py).

Sans réseau : les réponses d'ECCC et d'Open-Meteo sont simulées. Ce qui est
vérifié ici, ce sont les conversions d'unités (la source ECCC ne parle ni la
même unité ni la même convention que le reste du projet), l'appariement,
l'append-only, et surtout l'ÉTANCHÉITÉ : cette piste ne doit jamais toucher
au modèle en service.

Exécution : python3 tests/test_verification_croisee.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import verification_croisee as vc

echecs = []


def verifier(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  ÉCHEC {message}")
        echecs.append(message)


def _reponse_eccc(heures):
    """Imite la forme d'une réponse OGC d'api.weather.gc.ca."""
    return {"features": [
        {"properties": {"UTC_DATE": t, "WIND_SPEED": v, "WIND_DIRECTION": d}}
        for t, v, d in heures]}


def test_conversion_unites():
    print("\nConversion des unités ECCC")
    # 19 dizaines = 190° ; 36 dizaines = 360° (nord) ; 0 avec vent nul = calme
    heures = [("2026-07-01T12:00:00", 20, 19),
              ("2026-07-01T13:00:00", 37, 36),
              ("2026-07-01T14:00:00", 0, 0)]
    appels = []

    def faux_appel(url, params):
        appels.append((url, params))
        return _reponse_eccc(heures)

    vrai, vc.appel = vc.appel, faux_appel
    try:
        obs = vc.observations("2026-07-01", "2026-07-01")
    finally:
        vc.appel = vrai

    verifier(len(obs) == 3, "les trois heures sont retournées")
    verifier(abs(obs.iloc[0]["obs_vent"] - 20 * 0.539957) < 1e-6,
             "20 km/h -> 10,80 nds")
    verifier(obs.iloc[0]["obs_direction"] == 190.0,
             "19 dizaines -> 190 degrés")
    verifier(obs.iloc[1]["obs_direction"] == 360.0,
             "36 dizaines -> 360 degrés (nord)")
    verifier(pd.isna(obs.iloc[2]["obs_direction"]),
             "vent calme -> direction NaN, jamais 0 degré (= nord)")
    # Convention météo : vent du sud (190°) souffle vers le nord -> v positif
    verifier(obs.iloc[0]["obs_v"] > 0,
             "composante v cohérente avec la convention météo du projet")
    verifier(appels and appels[0][1]["CLIMATE_IDENTIFIER"] == config.STATION_CROISEE["id"],
             "la station interrogée est bien celle de la config")


def test_pagination():
    print("\nPagination de l'API ECCC")
    lots = []

    def faux_appel(url, params):
        lots.append(params["offset"])
        # Premier lot plein -> l'appelant doit redemander ; deuxième partiel.
        n = vc.PAGE if params["offset"] == 0 else 5
        depart = params["offset"]
        return _reponse_eccc([
            (f"2026-07-01T{i % 24:02d}:00:00", 10, 18) for i in range(depart, depart + n)])

    vrai, vc.appel = vc.appel, faux_appel
    try:
        vc.observations("2026-07-01", "2026-07-31")
    finally:
        vc.appel = vrai
    verifier(lots == [0, vc.PAGE],
             f"un lot plein déclenche la page suivante puis s'arrête ({lots})")


def test_appariement_et_scores():
    print("\nAppariement et scores")
    temps = pd.date_range("2026-07-01", periods=24, freq="h", tz="UTC")
    obs = pd.DataFrame({"time": temps, "obs_vent": [10.0] * 24,
                        "obs_direction": [180.0] * 24,
                        "obs_u": [0.0] * 24, "obs_v": [10.0] * 24})
    # « juste » colle à la mesure ; « haut » surestime de 2 nds partout
    prev = pd.concat([
        pd.DataFrame({"time": temps, "modele": "gem_global", "horizon": "24h",
                      "vent": [10.0] * 24, "direction": [180.0] * 24}),
        pd.DataFrame({"time": temps, "modele": "gfs_global", "horizon": "24h",
                      "vent": [12.0] * 24, "direction": [180.0] * 24}),
    ], ignore_index=True)

    apparie = vc.apparier(prev, obs)
    verifier(len(apparie) == 48, "une ligne par modèle × heure")
    verifier(apparie["station"].nunique() == 1, "la station est estampillée")

    locale = apparie["time"].dt.tz_convert(config.FUSEAU_LOCAL)
    apparie["heure_locale"] = locale.dt.hour
    s = vc.scores(apparie)
    par_modele = s.set_index("modele")
    verifier(abs(par_modele.loc["gem_global", "biais_nds"]) < 1e-9,
             "biais nul pour le modèle qui colle à la mesure")
    verifier(abs(par_modele.loc["gfs_global", "biais_nds"] - 2.0) < 1e-9,
             "biais +2 nds pour le modèle qui surestime")
    verifier(abs(par_modele.loc["gfs_global", "rmse_nds"] - 2.0) < 1e-9,
             "RMSE = 2 nds pour un décalage constant de 2 nds")
    verifier(s.iloc[0]["modele"] == "gem_global",
             "le classement met le meilleur RMSE en premier")
    verifier(bool(s["correlation"].isna().all()),
             "corrélation indéfinie (vent constant) -> NaN, pas un chiffre inventé")


def test_append_only():
    print("\nArchive append-only")
    tmp = Path(tempfile.mkdtemp())
    sauve_dossier, vrai_prev, vrai_obs = vc.DOSSIER, vc.previsions, vc.observations
    vc.DOSSIER = tmp / "croisee"
    temps = pd.date_range("2026-07-01", periods=3, freq="h", tz="UTC")

    def prevoit(vents):
        return lambda debut, fin: pd.DataFrame({
            "time": temps, "modele": "gem_global", "horizon": "24h",
            "vent": vents, "direction": [180.0] * 3})

    # apparier() n'est PAS simulée : le test exerce la vraie jointure.
    vc.observations = lambda debut, fin: pd.DataFrame({
        "time": temps, "obs_vent": [10.0] * 3, "obs_direction": [180.0] * 3,
        "obs_u": [0.0] * 3, "obs_v": [10.0] * 3})

    try:
        vc.previsions = prevoit([9.0, 9.0, 9.0])
        n1 = vc.mettre_a_jour("2026-07-01", "2026-07-01")
        verifier(n1 == 3, "premier passage : 3 lignes ajoutées")

        # Deuxième passage avec des valeurs DIFFÉRENTES sur les mêmes clés :
        # append-only signifie que les lignes existantes ne bougent pas.
        vc.previsions = prevoit([99.0, 99.0, 99.0])
        n2 = vc.mettre_a_jour("2026-07-01", "2026-07-01")
        verifier(n2 == 0, "deuxième passage : aucune ligne ajoutée")
        garde = pd.read_parquet(vc.DOSSIER / "2026-07.parquet")
        verifier(len(garde) == 3, "la partition contient toujours 3 lignes")
        verifier(bool((garde["vent"] == 9.0).all()),
                 "les valeurs d'origine sont intactes (jamais réécrites)")
    finally:
        vc.DOSSIER, vc.previsions, vc.observations = sauve_dossier, vrai_prev, vrai_obs
        shutil.rmtree(tmp, ignore_errors=True)


def _code_sans_prose(chemin: Path) -> str:
    """Source réduite au code exécutable : ni commentaires, ni docstrings.

    Sans ça, le test échouerait sur la docstring du module — qui mentionne
    data/poids_modeles.json précisément pour dire qu'elle n'y touche pas.
    C'est le code qui doit être étanche, pas la prose qui l'explique.
    """
    import ast
    arbre = ast.parse(chemin.read_text())
    for noeud in ast.walk(arbre):
        corps = getattr(noeud, "body", None)
        if not isinstance(corps, list) or not corps:
            continue
        premier = corps[0]
        if (isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant)
                and isinstance(premier.value.value, str)):
            corps.pop(0)
    return ast.unparse(arbre)


def test_etancheite():
    print("\nÉtanchéité : aucun effet sur le modèle en service")
    code = _code_sans_prose(Path(vc.__file__))
    for interdit in ["FICHIER_POIDS", "poids_modeles", "versions",
                     "construire_verite", "TRUTH_SOURCE", "MODELES_VERITE"]:
        verifier(interdit not in code,
                 f"le code de verification_croisee.py ne touche pas à {interdit}")
    verifier(str(vc.DOSSIER) == config.DOSSIER_VERIF_CROISEE,
             "elle écrit dans son propre dossier, séparé de data/verification")
    verifier(vc.DOSSIER != Path("data/verification"),
             "elle ne touche pas aux partitions du pipeline principal")


def test_fenetre_quotidienne():
    print("\nFenêtre du cron")
    import datetime as dt
    debut, fin = vc._fenetre_quotidienne(dt.date(2026, 8, 21))
    verifier((debut, fin) == ("2026-08-12", "2026-08-18"),
             "J-9 à J-3, comme le job principal (archives complètes à J-3)")


if __name__ == "__main__":
    test_conversion_unites()
    test_pagination()
    test_appariement_et_scores()
    test_append_only()
    test_etancheite()
    test_fenetre_quotidienne()

    print()
    if echecs:
        print(f"{len(echecs)} ÉCHEC(S)")
        raise SystemExit(1)
    print("Tous les tests de vérification croisée passent.")
