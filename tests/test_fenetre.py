"""Tests de la logique de fenêtres foilables (exécutés réellement).

Bande validée par l'utilisateur : 7–16 nds, zone marginale 5–7 nds.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
from fenetre import fenetres_du_jour  # noqa: E402

assert config.VENT_MIN_FOILABLE == 7.0 and config.VENT_MAX_FOILABLE == 16.0


def test_fenetre_simple():
    # 3 h dans la bande -> une fenêtre
    assert fenetres_du_jour([3, 3, 10, 12, 11, 3]) == [(2, 5)]


def test_trop_courte():
    # 1 h dans la bande -> pas de fenêtre
    assert fenetres_du_jour([3, 12, 3]) == []


def test_creux_marginal_tolere():
    # Creux à 6 nds entre deux heures en bande : la fenêtre tient
    assert fenetres_du_jour([10, 6, 12]) == [(0, 3)]


def test_deux_creux_consecutifs_coupent():
    # Deux marginales consécutives coupent ; chaque moitié doit se qualifier seule
    assert fenetres_du_jour([10, 11, 6, 6, 12, 13]) == [(0, 2), (4, 6)]
    assert fenetres_du_jour([10, 6, 6, 12, 13]) == [(3, 5)]


def test_sous_plancher_invalide():
    # Un pas sous 5 nds coupe net
    assert fenetres_du_jour([10, 4.5, 12]) == []
    assert fenetres_du_jour([10, 11, 4.5, 12, 13]) == [(0, 2), (3, 5)]


def test_surtoile_coupe():
    # > 16 nds (too much pour l'UFO) interrompt la fenêtre
    assert fenetres_du_jour([10, 20, 12]) == []


def test_marginales_bords_exclues():
    # Les marginales en tête/queue ne comptent pas et ne bornent pas la fenêtre
    assert fenetres_du_jour([6, 10, 11, 6]) == [(1, 3)]
    assert fenetres_du_jour([6, 10, 6]) == []


def test_nan_coupe():
    assert fenetres_du_jour([10, None, 12]) == []


def test_journee_calme():
    assert fenetres_du_jour([2, 3, 4, 4.9, 3, 2]) == []


if __name__ == "__main__":
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn()
            print(f"OK {nom}")
    print("Tous les tests fenêtre passent.")
