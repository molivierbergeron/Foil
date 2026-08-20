"""Vérité terrain : médiane multi-modèles des séries hour-0 (TRUTH_SOURCE).

Limite documentée : c'est une vérité de modèles, pas une observation. Elle
capture les erreurs synoptiques (le système météo qui n'arrive pas) mais pas
l'écart résiduel entre la grille des modèles et le vent réel au lac. La
médiane sur 6 modèles évite qu'un modèle soit vérifié contre sa propre
analyse (poids 1/6 dans la médiane, pas de corrélation dominante).

La médiane porte sur config.MODELES_VERITE (composition gelée), JAMAIS sur
config.MODELES : ajouter un modèle de prévision ne doit pas déplacer la
cible. Voir le commentaire de MODELES_VERITE dans config.py.

La direction est médianée en composantes vectorielles u/v (jamais en degrés
bruts) puis reconvertie en degrés pour l'affichage.

Phase 4 : TRUTH_SOURCE = "station" remplacera cette fonction par la station
Ecowitt au lac, sans changer le format de sortie.
"""

import numpy as np
import pandas as pd

import config


def composition_verite(hour0: pd.DataFrame) -> list[str]:
    """Modèles de vérité réellement présents dans ces données, dans l'ordre.

    C'est cette liste — pas la liste théorique — qui est estampillée sur les
    lignes de data/verification/ : une vérité calculée sur 5 modèles au lieu
    de 6 (trou d'archive chez un fournisseur) doit rester identifiable.
    """
    presents = set(hour0["modele"].unique())
    return [m for m in config.MODELES_VERITE if m in presents]


def filtrer_modeles_verite(hour0: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    """Ne garde que les modèles qui composent la vérité (composition gelée).

    strict=True (backtest, recalibrage) : un modèle de vérité manquant est une
    erreur de configuration — toute la calibration serait fausse, on échoue.
    strict=False (job quotidien) : un trou d'archive ponctuel chez un
    fournisseur ne doit pas tuer le job ; on avertit, on continue, et l'appelant
    estampille la composition réelle via composition_verite().
    """
    manquants = [m for m in config.MODELES_VERITE
                 if m not in set(hour0["modele"].unique())]
    if manquants:
        message = (f"modèles de vérité absents des séries hour-0 : {manquants} "
                   f"(vérité {config.VERITE_VERSION}, "
                   f"{len(config.MODELES_VERITE)} modèles attendus)")
        if strict:
            raise ValueError(message.capitalize())
        print(f"ATTENTION : {message} — vérité calculée sur "
              f"{len(config.MODELES_VERITE) - len(manquants)} modèles")
    return hour0[hour0["modele"].isin(config.MODELES_VERITE)]


def construire_verite(hour0: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    """Agrège hour0 (format long, une ligne par modèle × heure) en vérité.

    Retourne un DataFrame indexé par time (UTC) avec :
    vent, rafales, direction, u, v, n_modeles + variables de découplage
    (vent80, rayonnement, nebulosite, temp2m, temp80 : médianes multi-modèles).

    Seules les lignes des modèles de config.MODELES_VERITE sont agrégées ;
    les modèles de prévision supplémentaires présents dans hour0 sont ignorés.
    """
    hour0 = filtrer_modeles_verite(hour0, strict=strict)
    if config.TRUTH_SOURCE == "station":
        # Phase 4 : vérité mesurée au lac (Ecowitt). On couvre la même plage
        # temporelle que les données hour-0 reçues, puis on garde les colonnes
        # de découplage du consensus de modèles (la station ne les mesure pas).
        import station_ecowitt
        debut = hour0["time"].min().to_pydatetime()
        fin = hour0["time"].max().to_pydatetime()
        station = station_ecowitt.verite_station(debut, fin)
        grp = hour0.groupby("time")
        complements = pd.DataFrame({
            "vent80": grp["vent80"].median(),
            "rayonnement": grp["rayonnement"].median(),
            "nebulosite": grp["nebulosite"].median(),
            "temp2m": grp["temp2m"].median(),
            "temp80": grp["temp80"].median(),
        })
        verite = station.join(complements, how="left")
        verite["n_modeles"] = 1
        return verite.sort_index()
    if config.TRUTH_SOURCE != "median_hour0":
        raise ValueError(f"TRUTH_SOURCE inconnu: {config.TRUTH_SOURCE}")

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
