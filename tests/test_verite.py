"""Tests vérité terrain et utilitaires circulaires."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from backtest import intervalle_wilson  # noqa: E402
from telecharge import composantes_uv  # noqa: E402
from verite import construire_verite, secteur  # noqa: E402


def test_composantes_uv_convention_meteo():
    # Vent du nord (0°) : souffle vers le sud -> v négatif, u nul
    u, v = composantes_uv(10.0, 0.0)
    assert abs(u) < 1e-9 and abs(v + 10) < 1e-9
    # Vent d'ouest (270°) : souffle vers l'est -> u positif
    u, v = composantes_uv(10.0, 270.0)
    assert abs(u - 10) < 1e-9 and abs(v) < 1e-9


def test_secteur_circularite():
    s = secteur(pd.Series([0.0, 359.0, 1.0, 45.0, 90.0, 225.0, 337.4, 337.6]))
    # Frontière N/NO à 337,5° : 337,4 -> NO, 337,6 -> N
    assert list(s) == ["N", "N", "N", "NE", "E", "SO", "NO", "N"]


def test_mediane_direction_pres_du_nord():
    # 3 modèles autour du nord (350°, 0°, 10°) : la médiane vectorielle doit
    # rester au nord, pas à 120° comme le ferait une moyenne en degrés bruts.
    temps = pd.to_datetime(["2025-06-01T12:00"] * 3).tz_localize("UTC")
    vents = [10.0, 10.0, 10.0]
    directions = [350.0, 0.0, 10.0]
    u, v = composantes_uv(np.array(vents), np.array(directions))
    hour0 = pd.DataFrame({
        # De vrais identifiants de modèles de vérité : depuis que la
        # composition est gelée (config.MODELES_VERITE), construire_verite
        # ignore tout modèle qui n'en fait pas partie.
        "time": temps, "modele": list(config.MODELES_VERITE[:3]), "vent": vents,
        "rafales": [14.0] * 3, "u": u, "v": v, "vent80": [12.0] * 3,
        "rayonnement": [500.0] * 3, "nebulosite": [20.0] * 3,
        "temp2m": [20.0] * 3, "temp80": [19.0] * 3,
    })
    # strict=False : ce cas de test ne fournit que 3 des 6 modèles de vérité.
    verite = construire_verite(hour0, strict=False)
    d = verite["direction"].iloc[0]
    assert d < 10 or d > 350, f"direction médiane {d}° devrait être ~0°"


def test_wilson():
    bas, haut = intervalle_wilson(5, 10)
    assert 0.2 < bas < 0.5 < haut < 0.8
    assert intervalle_wilson(0, 0) != intervalle_wilson(0, 1)


if __name__ == "__main__":
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn()
            print(f"OK {nom}")
    print("Tous les tests vérité passent.")
