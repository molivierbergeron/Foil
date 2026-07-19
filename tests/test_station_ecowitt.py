"""Tests hors-ligne du module station Ecowitt (réponse API simulée).

Le format simulé suit la doc officielle d'Ecowitt ; la validation contre la
VRAIE API se fait avec `python3 station_ecowitt.py` dès que les clés existent
(voir docstring du module).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np  # noqa: E402

from station_ecowitt import _normaliser, MS_VERS_NOEUDS  # noqa: E402


def _reponse_simulee():
    # 2 h de mesures aux 5 min : vent 5 m/s du nord (350-10°), rafales 8 m/s
    epochs = [1750000000 + i * 300 for i in range(24)]
    directions = [350, 355, 0, 5, 10, 355] * 4
    return {
        "code": 0, "msg": "success",
        "data": {"wind": {
            "wind_speed": {"unit": "m/s",
                           "list": {str(e): "5.0" for e in epochs}},
            "wind_gust": {"unit": "m/s",
                          "list": {str(e): "8.0" for e in epochs}},
            "wind_direction": {"unit": "º",
                               "list": {str(e): str(d)
                                        for e, d in zip(epochs, directions)}},
        }},
    }


def test_normalisation_unites_et_heures():
    df = _normaliser(_reponse_simulee())
    assert len(df) == 2, f"attendu 2 heures, reçu {len(df)}"
    # 5 m/s -> ~9.7 nds ; rafale max 8 m/s -> ~15.6 nds
    assert abs(df["vent"].iloc[0] - 5 * MS_VERS_NOEUDS) < 0.01
    assert abs(df["rafales"].iloc[0] - 8 * MS_VERS_NOEUDS) < 0.01
    assert str(df.index.tz) == "UTC"


def test_direction_vectorielle_pres_du_nord():
    # Directions autour de 0° : la moyenne vectorielle doit rester au nord,
    # pas dériver vers 180° comme une moyenne en degrés bruts.
    df = _normaliser(_reponse_simulee())
    d = float(df["direction"].iloc[0])
    assert d < 15 or d > 345, f"direction {d}° devrait être ~0°"


def test_heure_incomplete_rejetee():
    rep = _reponse_simulee()
    # Ne garder que 4 mesures (20 min) dans la première heure -> rejetée
    liste = rep["data"]["wind"]["wind_speed"]["list"]
    for cle in list(liste)[4:12]:
        del liste[cle]
    df = _normaliser(rep)
    assert len(df) == 1


if __name__ == "__main__":
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn()
            print(f"OK {nom}")
    print("Tous les tests station passent.")
