"""Tests de la logique de fenêtres foilables (exécutés réellement, phase 1)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fenetre import fenetres_du_jour  # noqa: E402


def test_fenetre_simple():
    # 3 h dans la bande -> une fenêtre
    assert fenetres_du_jour([5, 5, 10, 12, 11, 5]) == [(2, 5)]


def test_trop_courte():
    # 1 h dans la bande -> pas de fenêtre
    assert fenetres_du_jour([5, 12, 5]) == []


def test_creux_marginal_tolere():
    # Creux à 8 nds entre deux heures en bande : la fenêtre tient
    assert fenetres_du_jour([12, 8, 14]) == [(0, 3)]


def test_deux_creux_consecutifs_coupent():
    # Deux marginales consécutives coupent ; chaque moitié doit se qualifier seule
    assert fenetres_du_jour([12, 13, 8, 8, 14, 15]) == [(0, 2), (4, 6)]
    assert fenetres_du_jour([12, 8, 8, 14, 15]) == [(3, 5)]


def test_sous_7_invalide():
    # Un pas sous 7 nds coupe net
    assert fenetres_du_jour([12, 6.5, 14]) == []
    assert fenetres_du_jour([12, 13, 6.5, 14, 15]) == [(0, 2), (3, 5)]


def test_surtoile_coupe():
    # > 25 nds interrompt la fenêtre
    assert fenetres_du_jour([12, 30, 14]) == []


def test_marginales_bords_exclues():
    # Les marginales en tête/queue ne comptent pas et ne bornent pas la fenêtre
    assert fenetres_du_jour([8, 12, 13, 8]) == [(1, 3)]
    assert fenetres_du_jour([8, 12, 8]) == []


def test_nan_coupe():
    assert fenetres_du_jour([12, None, 14]) == []


def test_journee_calme():
    assert fenetres_du_jour([3, 4, 5, 6, 5, 4]) == []


if __name__ == "__main__":
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn()
            print(f"OK {nom}")
    print("Tous les tests fenêtre passent.")
