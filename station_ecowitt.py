"""Client Ecowitt.net — vérité terrain mesurée au lac (phase 4).

Quand l'anémomètre à ultrasons sera installé au bord du lac (chez le cousin),
ce module remplace la vérité « médiane de modèles » par du vent réellement
mesuré, sans autre changement de code : mettre TRUTH_SOURCE = "station" dans
config.py et fournir les clés via variables d'environnement (GitHub Secrets) :

    ECOWITT_APPLICATION_KEY   (compte Ecowitt -> API)
    ECOWITT_API_KEY
    ECOWITT_MAC               (adresse MAC de la passerelle, format AA:BB:...)

Dans les workflows GitHub Actions, ajouter au step concerné :
    env:
      ECOWITT_APPLICATION_KEY: ${{ secrets.ECOWITT_APPLICATION_KEY }}
      ECOWITT_API_KEY: ${{ secrets.ECOWITT_API_KEY }}
      ECOWITT_MAC: ${{ secrets.ECOWITT_MAC }}

IMPORTANT — validation au premier branchement : le format de réponse ci-
dessous suit la documentation officielle (api.ecowitt.net/api/v3/device/
history, structure data.wind.wind_speed.list = {epoch: valeur}), mais la
règle du projet exige un appel réel avant de s'y fier. Sans clé, impossible
ici : à la réception des clés, lancer `python3 station_ecowitt.py` (mode
autotest) qui appelle l'API sur les dernières 24 h et affiche ce qu'il
comprend. Ajuster _normaliser() si la structure diffère.

Rappels d'installation (voir README) : exposition maximale (quai/pointe),
hauteur du mât notée dans HAUTEUR_ANEMOMETRE_M pour correction future,
et le vent au rivage lit systématiquement plus bas que le milieu du lac —
biais constant, donc apprenable par la boucle de recalibrage.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

import config

URL_HISTORIQUE = "https://api.ecowitt.net/api/v3/device/history"
HAUTEUR_ANEMOMETRE_M = 3.0  # à ajuster à l'installation (correction future)
MS_VERS_NOEUDS = 1.9438445


def _cles():
    cles = {
        "application_key": os.environ.get("ECOWITT_APPLICATION_KEY"),
        "api_key": os.environ.get("ECOWITT_API_KEY"),
        "mac": os.environ.get("ECOWITT_MAC"),
    }
    manquantes = [k for k, v in cles.items() if not v]
    if manquantes:
        raise RuntimeError(
            f"Clés Ecowitt manquantes ({', '.join(manquantes)}) — "
            "définir les variables d'environnement / GitHub Secrets.")
    return cles


def _appel_brut(debut: datetime, fin: datetime, essais_max: int = 4) -> dict:
    params = {
        **_cles(),
        "start_date": debut.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": fin.strftime("%Y-%m-%d %H:%M:%S"),
        "call_back": "wind",
        "cycle_type": "5min",
        "wind_speed_unitid": 6,  # 6 = m/s selon la doc ; converti en nds ici
    }
    delai = 2.0
    for essai in range(essais_max):
        try:
            rep = requests.get(URL_HISTORIQUE, params=params, timeout=60)
        except requests.exceptions.RequestException:
            if essai == essais_max - 1:
                raise
            time.sleep(delai)
            delai *= 2
            continue
        if rep.status_code == 200:
            donnees = rep.json()
            if donnees.get("code") != 0:
                raise RuntimeError(f"Erreur API Ecowitt: {donnees.get('msg')}")
            return donnees
        if rep.status_code == 429 or rep.status_code >= 500:
            time.sleep(delai)
            delai *= 2
            continue
        raise RuntimeError(f"HTTP {rep.status_code}: {rep.text[:200]}")
    raise RuntimeError(f"Échec après {essais_max} essais")


def _serie(bloc: dict) -> pd.Series:
    """{'unit': ..., 'list': {epoch_str: valeur_str}} -> Series indexée UTC."""
    valeurs = bloc.get("list", {})
    s = pd.Series({int(k): float(v) for k, v in valeurs.items() if v not in (None, "", "-")})
    s.index = pd.to_datetime(s.index, unit="s", utc=True)
    return s.sort_index()


def _normaliser(donnees: dict) -> pd.DataFrame:
    """Réponse Ecowitt -> DataFrame horaire au format vérité du pipeline.

    Moyenne horaire du vent, max horaire des rafales, direction moyennée en
    composantes u/v (jamais en degrés bruts). Unités : nœuds.
    """
    vent_bloc = donnees["data"]["wind"]
    vitesse = _serie(vent_bloc["wind_speed"])
    rafales = _serie(vent_bloc.get("wind_gust", {"list": {}}))
    direction = _serie(vent_bloc.get("wind_direction", {"list": {}}))

    unite = str(vent_bloc["wind_speed"].get("unit", "m/s")).lower()
    facteur = {"m/s": MS_VERS_NOEUDS, "km/h": 0.539957,
               "mph": 0.868976, "knots": 1.0, "kn": 1.0}.get(unite)
    if facteur is None:
        raise RuntimeError(f"Unité Ecowitt inattendue: {unite} — vérifier wind_speed_unitid")
    vitesse, rafales = vitesse * facteur, rafales * facteur

    direction = direction.reindex(vitesse.index).interpolate(limit=2)
    theta = np.radians(direction)
    u = -vitesse * np.sin(theta)
    v = -vitesse * np.cos(theta)

    horaire = pd.DataFrame({
        "vent": vitesse.resample("1h").mean(),
        "rafales": rafales.resample("1h").max(),
        "u": u.resample("1h").mean(),
        "v": v.resample("1h").mean(),
        "n_mesures": vitesse.resample("1h").count(),
    })
    # Une heure avec moins de 6 mesures 5-min (30 min de données) est rejetée
    horaire = horaire[horaire["n_mesures"] >= 6].drop(columns=["n_mesures"])
    horaire["direction"] = (np.degrees(np.arctan2(-horaire["u"], -horaire["v"]))) % 360
    horaire.index.name = "time"
    return horaire


def verite_station(debut: datetime, fin: datetime) -> pd.DataFrame:
    """Vérité mesurée au lac, même format que verite.construire_verite().

    L'API Ecowitt limite l'historique par appel : on découpe par tranches de
    24 h. Les colonnes de découplage (vent80, rayonnement, ...) n'existent pas
    pour une station : absentes du résultat, les consommateurs les traitent
    comme optionnelles.
    """
    morceaux = []
    curseur = debut
    while curseur < fin:
        borne = min(curseur + timedelta(days=1), fin)
        morceaux.append(_normaliser(_appel_brut(curseur, borne)))
        curseur = borne
        time.sleep(1.0)  # courtoisie API
    if not morceaux:
        return pd.DataFrame(columns=["vent", "rafales", "u", "v", "direction"])
    return pd.concat(morceaux).sort_index()


def autotest():
    """À lancer à la réception des clés : valide le format de l'API en vrai."""
    fin = datetime.now(timezone.utc)
    debut = fin - timedelta(hours=24)
    print(f"Appel réel Ecowitt {debut:%Y-%m-%d %H:%M} -> {fin:%H:%M} UTC...")
    brut = _appel_brut(debut, fin)
    print("Réponse code:", brut.get("code"), "| clés data:", list(brut.get("data", {}).keys()))
    df = _normaliser(brut)
    print(df.tail(6).round(1).to_string())
    print(f"\nOK : {len(df)} heures normalisées. Format validé — "
          "TRUTH_SOURCE=\"station\" peut être activé dans config.py.")


if __name__ == "__main__":
    autotest()
