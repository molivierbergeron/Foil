"""Construit le modèle CANDIDAT à SEPT membres : les six actuels + HRRR.

Pourquoi un septième modèle plutôt que d'autres poids
-----------------------------------------------------
Mesuré, entre deux jeux de poids sur les six mêmes modèles, l'écart de
prévision est de 0,31 nd médian et ne dépasse 1 nd que 4,6 % des heures : une
moyenne pondérée reste prisonnière de ses ingrédients. Déplacer une prévision
de 1 à 3 nds — le seuil où ça change une décision — demande de changer les
ingrédients. HRRR est le seul disponible : maille 3 km (contre 13-25 km pour
les globaux), centre indépendant (NOAA), et il couvre le lac.

Ce que fait ce module
---------------------
Exactement le backtest en service (mêmes biais, mêmes poids ∝ 1/RMSE², même
vérité gelée à six modèles), sur les sept membres au lieu de six. Une seule
chose change : la composition de l'ensemble.

    python3 candidat_hrrr.py      # construit, archive et publie le candidat

Le candidat n'entre JAMAIS en service tout seul : il est archivé et publié à
côté de l'actif (docs/poids_candidat.json), affiché dans la vue d'essai, et
ne calcule aucun verdict tant qu'un `versions.py --activer` explicite ne le
promeut pas. Le verdict qui justifierait cette promotion se mesure contre
l'anémomètre réel, pas ici : voir reports/hrrr.md.

La vérité terrain n'est PAS touchée. config.MODELES_VERITE reste gelée sur
les six modèles d'origine ; HRRR est un membre de prévision, jamais un
membre de la cible. C'est ce qui garde data/verification/ comparable.
"""

import backtest
import config
import versions

MODELE_AJOUTE = "gfs_hrrr"


def construire() -> tuple[dict, dict]:
    """Retourne (poids à sept membres, métriques de construction)."""
    if MODELE_AJOUTE not in config.MODELES:
        raise RuntimeError(f"{MODELE_AJOUTE} absent de config.MODELES")

    previsions, hour0, verite = backtest.charger()
    apparie = backtest.apparier(previsions, verite)
    if MODELE_AJOUTE not in set(apparie["modele"]):
        raise RuntimeError(
            f"{MODELE_AJOUTE} absent de data/processed/previsions.parquet — "
            "lancer d'abord python3 telecharge.py")

    periode = (f"{apparie['date_locale'].min()} à {apparie['date_locale'].max()}"
               " (mai-octobre)")
    poids = backtest.calculer_poids(
        backtest.biais_rmse(apparie),
        backtest.biais_segmente(apparie, "secteur"),
        backtest.confusion_fenetres(apparie, verite),
        backtest.survie_fenetres(apparie, verite),
        backtest.ratios_rafales(hour0),
        periode,
        # Le point de tout ce module : une composition d'ensemble différente
        # de config.MODELES_ENSEMBLE. C'est le SEUL endroit qui la surcharge,
        # et il produit un candidat — jamais l'actif.
        membres=tuple(config.MODELES))

    metriques = {
        "membres": sorted(poids["modeles"]),
        "membres_en_service": list(config.MODELES_ENSEMBLE),
        "membre_ajoute": MODELE_AJOUTE,
        "verite_inchangee": list(config.MODELES_VERITE),
    }
    return poids, metriques


def principal() -> int:
    poids, metriques = construire()
    previsions, _, verite = backtest.charger()
    apparie = backtest.apparier(previsions, verite)
    version = versions.enregistrer(
        poids, origine="hrrr",
        donnees_jusqu_au=apparie["date_locale"].max(),
        n_apparie=int(len(apparie)),
        metriques=metriques,
        notes="Ensemble à sept membres : les six modèles en service + HRRR "
              "(NOAA, 3 km, horizon 24 h). Vérité inchangée (six modèles). "
              "À l'essai, hors service — voir reports/hrrr.md pour le "
              "jugement hors échantillon contre l'anémomètre réel.",
        role="candidat")
    print(f"Candidat : {version}  (actif inchangé : {versions.actif()})")
    print(f"  membres : {len(metriques['membres'])} — "
          f"{', '.join(metriques['membres'])}")
    print(f"  publié dans {versions.COPIE_CANDIDAT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
