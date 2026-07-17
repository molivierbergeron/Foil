"""Tests du client Open-Meteo : retry sur erreurs réseau (pas seulement HTTP)."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests  # noqa: E402

import config  # noqa: E402
import openmeteo_client  # noqa: E402


class _FausseReponse:
    status_code = 200

    def json(self):
        return {"hourly": {"time": []}}


def test_retry_sur_timeout_reseau():
    """Un ReadTimeout (pas de réponse HTTP du tout) doit être retenté, pas fatal.

    C'est le bug observé en prod : historical-forecast-api a timeout sans
    répondre, et l'appel plantait le job quotidien au lieu de réessayer.
    """
    appels = {"n": 0}

    def get_qui_timeout_puis_reussit(*a, **k):
        appels["n"] += 1
        if appels["n"] < 3:
            raise requests.exceptions.ReadTimeout("simulation timeout")
        return _FausseReponse()

    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(config, "DOSSIER_RAW", tmp), \
             patch.object(openmeteo_client.time, "sleep", lambda *_: None), \
             patch.object(requests, "get", get_qui_timeout_puis_reussit):
            donnees = openmeteo_client.appel("https://example.test/api", {"a": 1})

    assert donnees == {"hourly": {"time": []}}
    assert appels["n"] == 3


def test_echec_apres_essais_max_leve_erreur_explicite():
    def get_qui_timeout_toujours(*a, **k):
        raise requests.exceptions.ConnectTimeout("simulation")

    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(config, "DOSSIER_RAW", tmp), \
             patch.object(openmeteo_client.time, "sleep", lambda *_: None), \
             patch.object(requests, "get", get_qui_timeout_toujours):
            try:
                openmeteo_client.appel("https://example.test/api", {"a": 1}, essais_max=2)
                assert False, "aurait dû lever une exception"
            except RuntimeError as exc:
                assert "réseau" in str(exc)


if __name__ == "__main__":
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_"):
            fn()
            print(f"OK {nom}")
    print("Tous les tests openmeteo_client passent.")
