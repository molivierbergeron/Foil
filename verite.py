"""Vérité terrain : médiane multi-modèles des séries hour-0 (TRUTH_SOURCE).

Limite documentée : c'est une vérité de modèles, pas une observation. Elle
capture les erreurs synoptiques (le système météo qui n'arrive pas) mais pas
l'écart résiduel entre la grille des modèles et le vent réel au lac. La
médiane sur 6 modèles évite qu'un modèle soit vérifié contre sa propre
analyse (poids 1/6 dans la médiane, pas de corrélation dominante).

La direction est médianée en composantes vectorielles u/v (jamais en degrés
bruts) puis reconvertie en degrés pour l'affichage.

Phase 4 : TRUTH_SOURCE = "station" remplacera cette fonction par la station
Ecowitt au lac, sans changer le format de sortie.
"""

import numpy as np
import pandas as pd

import config


def construire_verite(hour0: pd.DataFrame) -> pd.DataFrame:
    """Agrège hour0 (format long, une ligne par modèle × heure) en vérité.

    Retourne un DataFrame indexé par time (UTC) avec :
    vent, rafales, direction, u, v, n_modeles + variables de découplage
    (vent80, rayonnement, nebulosite, temp2m, temp80 : médianes multi-modèles).
    """
    if config.TRUTH_SOURCE != "median_hour0":
        raise NotImplementedError(f"TRUTH_SOURCE={config.TRUTH_SOURCE} non branché (phase 4)")

    grp = hour0.groupby("time")
    verite = pd.DataFrame({
        "vent": grp["vent"].median(),
        "rafales": grp["rafales"].median(),
        "u": grp["u"].median(),
        "v": grp["v"].median(),
        "vent80": grp["vent80"].median(),
        "rayonnement": grp["rayonnement"].median(),
        "nebulosite": grp["nebulosite"].median(),
        "temp2m": grp["temp2m"].median(),
        "temp80": grp["temp80"].median(),
        "n_modeles": grp["vent"].count(),
    })
    verite["direction"] = (np.degrees(np.arctan2(-verite["u"], -verite["v"]))) % 360
    # Exiger au moins 3 modèles pour qu'une médiane soit une vérité crédible
    verite = verite[verite["n_modeles"] >= 3]
    return verite.sort_index()


def secteur(direction_deg: pd.Series) -> pd.Series:
    """Direction en degrés -> 8 secteurs (N, NE, ..., NO), pour la segmentation."""
    idx = ((direction_deg + 22.5) % 360 // 45).astype("Int64")
    return idx.map(dict(enumerate(config.SECTEURS)))
