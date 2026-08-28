"""Construit un modèle CANDIDAT pondéré par la compétence mesurée au réel.

L'idée en une phrase
--------------------
Le modèle en service pondère chaque modèle par son écart au consensus des
modèles. Mesuré contre un vrai anémomètre (Lac Saint-Pierre, 3 saisons,
171 701 paires), ce classement est presque inversé : GFS et HRDPS, les deux
plus justes face à la réalité, reçoivent les poids les plus faibles.

Ce module fabrique une variante qui ne change qu'UNE chose : les poids.

    biais    <- inchangés, repris du modèle actif
    poids    <- recalculés ∝ 1/RMSE², RMSE mesuré contre l'anémomètre

Pourquoi ne garder QUE les poids
--------------------------------
Lac Saint-Pierre est un plan d'eau bien plus ouvert que le Maskinongé : les
six modèles y sous-estiment tous de 1 à 3 nds. Ce biais est celui du SITE et
ne se transplante pas — le recopier fausserait tout. Ce qui se transporte
raisonnablement, c'est la compétence relative : quel modèle suit le mieux le
passage réel des systèmes. D'où : biais locaux, poids réels.

Le candidat n'entre JAMAIS en service tout seul. Il est archivé et publié à
côté de l'actif (docs/poids_candidat.json), affiché dans la vue d'essai, et
ne calcule aucun verdict tant qu'un `versions.py --activer` explicite ne le
promeut pas.

    python3 candidat.py            # construit, archive et publie le candidat
"""

import json
from datetime import date
from pathlib import Path

import config
import verification_croisee
import versions

# En dessous, l'échantillon est trop mince pour qu'un RMSE mesuré porte une
# décision de pondération : le modèle garde alors le poids que l'actif lui
# donne, plutôt que d'hériter d'un chiffre bruyant.
N_MIN_POIDS = 500


def poids_par_competence(scores, horizon: str) -> dict:
    """Poids ∝ 1/RMSE² à partir des RMSE mesurés contre l'anémomètre.

    Même formule que le modèle en service (backtest.calculer_poids) : seule
    la source du RMSE change. Les deux jeux de poids restent donc comparables
    terme à terme, ce qui est le but de la vue d'essai.
    """
    lignes = scores[(scores["horizon"] == horizon) & (scores["n"] >= N_MIN_POIDS)]
    if lignes.empty:
        return {}
    inverses = {r["modele"]: 1.0 / (r["rmse_nds"] ** 2)
                for _, r in lignes.iterrows() if r["rmse_nds"] > 0}
    total = sum(inverses.values())
    return {m: v / total for m, v in inverses.items()} if total else {}


def construire() -> tuple[dict, dict]:
    """Retourne (poids candidat, métriques ayant servi à le construire)."""
    croise = verification_croisee.charger()
    if croise.empty:
        raise RuntimeError(
            "Aucune donnée de vérification croisée. Lancer d'abord "
            "« Rattrapage vérification croisée » (onglet Actions) ou "
            "python3 verification_croisee.py --rattraper …")
    scores = verification_croisee.scores(croise)

    actif = versions.charger_poids(versions.actif())
    candidat = json.loads(json.dumps(actif))   # copie profonde
    candidat.pop("version_modele", None)       # l'archive reste nue

    remplaces, conserves = [], []
    for horizon in config.HORIZONS:
        nouveaux = poids_par_competence(scores, horizon)
        for modele, infos in candidat.get("modeles", {}).items():
            bloc = infos.get("horizons", {}).get(horizon)
            if bloc is None:
                continue
            if modele in nouveaux:
                bloc["poids"] = round(nouveaux[modele], 4)
                ligne = scores[(scores["modele"] == modele)
                               & (scores["horizon"] == horizon)].iloc[0]
                # Traçabilité : d'où vient ce poids, et contre quoi il a été
                # mesuré. Sans ça, un poids « venu d'ailleurs » est indéfendable.
                bloc["rmse_reel_nds"] = round(float(ligne["rmse_nds"]), 2)
                bloc["n_reel"] = int(ligne["n"])
                remplaces.append(f"{modele}/{horizon}")
            else:
                conserves.append(f"{modele}/{horizon}")

    station = config.STATION_CROISEE
    candidat["genere_le"] = date.today().isoformat()
    candidat["origine_poids"] = {
        "methode": "1/RMSE² mesuré contre observation réelle",
        "station": f"{station['nom']} ({station['id']})",
        "distance_km": station["distance_km"],
        "periode": f"{croise['date_locale'].min()} à {croise['date_locale'].max()}",
        "n_paires": int(len(croise)),
        "biais": "inchangés — repris du modèle actif (les biais du site de "
                 "mesure ne se transplantent pas au lac)",
    }
    metriques = {
        "poids_remplaces": remplaces,
        "poids_conserves": conserves,
        "n_min_poids": N_MIN_POIDS,
    }
    return candidat, metriques


def principal() -> int:
    candidat, metriques = construire()
    croise = verification_croisee.charger()
    version = versions.enregistrer(
        candidat, origine="competence-reelle",
        donnees_jusqu_au=str(croise["date_locale"].max()),
        n_apparie=int(len(croise)),
        metriques=metriques,
        notes="Poids recalculés sur la compétence mesurée contre l'anémomètre "
              "de Lac Saint-Pierre ; biais locaux inchangés. À l'essai, hors "
              "service.",
        role="candidat")
    print(f"Candidat : {version}  (actif inchangé : {versions.actif()})")
    print(f"  poids remplacés : {len(metriques['poids_remplaces'])}")
    print(f"  poids conservés : {len(metriques['poids_conserves'])} "
          f"(échantillon < {N_MIN_POIDS})")
    print(f"  publié dans {versions.COPIE_CANDIDAT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
