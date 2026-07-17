"""Client Open-Meteo : cache disque + retry avec backoff exponentiel.

Un appel réussi est mis en cache dans data/raw/ (JSON brut) et n'est jamais
refait. Le nom de fichier encode les paramètres de l'appel, donc tout
changement de requête déclenche un nouvel appel plutôt qu'un faux cache-hit.
"""

import hashlib
import json
import time
from pathlib import Path

import requests

import config

ENTETES = {"User-Agent": "foil-maskinonge (usage personnel non commercial)"}
PAUSE_ENTRE_APPELS = 1.5  # secondes, courtoisie API


def _chemin_cache(url: str, params: dict) -> Path:
    cle = json.dumps({"url": url, "params": params}, sort_keys=True)
    empreinte = hashlib.sha256(cle.encode()).hexdigest()[:16]
    # Préfixe lisible pour inspection manuelle du cache
    modele = str(params.get("models", "multi")).replace(",", "+")[:40]
    debut = params.get("start_date", "nodate")
    hote = url.split("//")[1].split(".")[0]
    nom = f"{hote}_{modele}_{debut}_{empreinte}.json"
    return Path(config.DOSSIER_RAW) / nom


def appel(url: str, params: dict, essais_max: int = 5) -> dict:
    """GET avec cache disque et retry sur 429/5xx (backoff exponentiel)."""
    cache = _chemin_cache(url, params)
    if cache.exists():
        with open(cache) as f:
            return json.load(f)

    cache.parent.mkdir(parents=True, exist_ok=True)
    delai = 2.0
    derniere_erreur: Exception | None = None
    for essai in range(essais_max):
        try:
            rep = requests.get(url, params=params, headers=ENTETES, timeout=120)
        except requests.exceptions.RequestException as exc:
            # Timeout / connexion coupée avant même une réponse HTTP : même
            # traitement que 429/5xx, sinon un simple aléa réseau tue le job.
            derniere_erreur = exc
            if essai == essais_max - 1:
                break
            time.sleep(delai)
            delai *= 2
            continue
        if rep.status_code == 200:
            donnees = rep.json()
            if "error" in donnees and donnees.get("error"):
                raise RuntimeError(f"Erreur API: {donnees.get('reason')}")
            with open(cache, "w") as f:
                json.dump(donnees, f)
            time.sleep(PAUSE_ENTRE_APPELS)
            return donnees
        if rep.status_code == 429 or rep.status_code >= 500:
            if essai == essais_max - 1:
                break
            time.sleep(delai)
            delai *= 2
            continue
        raise RuntimeError(f"HTTP {rep.status_code}: {rep.text[:300]}")
    if derniere_erreur is not None:
        raise RuntimeError(
            f"Échec après {essais_max} essais (réseau): {derniere_erreur}"
        ) from derniere_erreur
    raise RuntimeError(f"Échec après {essais_max} essais: HTTP {rep.status_code}")
