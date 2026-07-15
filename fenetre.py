"""Détection des fenêtres foilables sur une série horaire de vent.

Définition (config.py) : ≥ 2 pas horaires dans la bande 9–25 nds, entre 8 h et
20 h locales, avec tolérance aux creux — un pas horaire intermédiaire dans la
zone marginale (7–9 nds) n'invalide pas la fenêtre, tant qu'il n'y en a pas
deux consécutifs et que le vent ne descend jamais sous 7 nds. Un pas > 25 nds
(surtoilé) interrompt la fenêtre au même titre qu'un pas < 7 nds.
"""

import pandas as pd

import config


def _dans_bande(v: float) -> bool:
    return config.VENT_MIN_FOILABLE <= v <= config.VENT_MAX_FOILABLE


def _marginal(v: float) -> bool:
    return config.VENT_MARGINAL <= v < config.VENT_MIN_FOILABLE


def fenetres_du_jour(vents: list[float]) -> list[tuple[int, int]]:
    """Fenêtres foilables dans une liste horaire (heures locales 8 h..19 h).

    Retourne les (index_debut, index_fin_exclusif) des fenêtres valides,
    bornées par des heures dans la bande (les marginales de tête/queue sont
    exclues). Les valeurs None/NaN interrompent toute fenêtre.
    """
    fenetres = []
    segment = []  # indices consécutifs où vent est bande ou marginal
    for i, v in enumerate(list(vents) + [None]):  # sentinelle de fin
        acceptable = v is not None and not pd.isna(v) and (_dans_bande(v) or _marginal(v))
        if acceptable:
            segment.append(i)
            continue
        if segment:
            fenetres.extend(_extraire(segment, vents))
            segment = []
    return fenetres


def _extraire(segment: list[int], vents) -> list[tuple[int, int]]:
    # Retire les marginales en tête et en queue : une fenêtre commence et
    # finit dans la bande.
    while segment and _marginal(vents[segment[0]]):
        segment = segment[1:]
    while segment and _marginal(vents[segment[-1]]):
        segment = segment[:-1]
    if not segment:
        return []
    # Deux marginales consécutives coupent le segment en deux fenêtres candidates.
    for j in range(len(segment) - 1):
        a, b = segment[j], segment[j + 1]
        if _marginal(vents[a]) and _marginal(vents[b]):
            return _extraire(segment[:j], vents) + _extraire(segment[j + 2:], vents)
    heures_bande = sum(1 for i in segment if _dans_bande(vents[i]))
    if heures_bande >= config.DUREE_MIN_FENETRE:
        return [(segment[0], segment[-1] + 1)]
    return []


def jour_foilable(serie_locale: pd.Series) -> bool:
    """True si la journée contient au moins une fenêtre foilable.

    `serie_locale` : vent (nds) indexé par heure locale tz-aware, un jour donné.
    """
    jour = serie_locale.between_time(f"{config.HEURE_DEBUT}:00",
                                     f"{config.HEURE_FIN - 1}:00")
    return len(fenetres_du_jour(jour.tolist())) > 0


def bloc_foilable(serie_locale: pd.Series, bloc: str) -> bool:
    """True si le bloc (matin/apres_midi/soiree) contient une fenêtre.

    La fenêtre est évaluée sur la journée complète ; le bloc est GO si une
    fenêtre le recouvre d'au moins une heure dans la bande.
    """
    debut_b, fin_b = config.BLOCS[bloc]
    jour = serie_locale.between_time(f"{config.HEURE_DEBUT}:00",
                                     f"{config.HEURE_FIN - 1}:00")
    vents = jour.tolist()
    heures = [t.hour for t in jour.index]
    for d, f in fenetres_du_jour(vents):
        for i in range(d, f):
            if debut_b <= heures[i] < fin_b and _dans_bande(vents[i]):
                return True
    return False
