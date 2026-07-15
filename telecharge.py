"""Téléchargement et normalisation des données de backtest (phase 1).

Produit :
- data/raw/          : réponses JSON brutes (cache, jamais re-téléchargé)
- data/processed/previsions.parquet : prévisions à 24/48/96 h (format long)
- data/processed/hour0.parquet      : séries hour-0 + variables de découplage

Toutes les heures sont stockées en UTC (tz-aware) ; la conversion en heure
locale (America/Toronto, DST inclus) se fait au moment de l'analyse.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config
from openmeteo_client import appel


def composantes_uv(vitesse, direction_deg):
    """Convention météo : u = -V*sin(θ), v = -V*cos(θ), θ = direction d'où vient le vent."""
    theta = np.radians(direction_deg)
    return -vitesse * np.sin(theta), -vitesse * np.cos(theta)


def saisons():
    for debut, fin in config.SAISONS_BACKTEST:
        if fin is None:
            fin = (date.today() - timedelta(days=3)).isoformat()
            if fin < debut:
                continue
        yield debut, fin


def _vers_serie_temps(donnees):
    return pd.to_datetime(donnees["hourly"]["time"]).tz_localize("UTC")


def telecharger_previous_runs() -> pd.DataFrame:
    lignes = []
    for modele, info in config.MODELES.items():
        variables = []
        for etiquette in info["horizons"]:
            suffixe = config.HORIZONS[etiquette]
            variables += [f"wind_speed_10m_{suffixe}", f"wind_direction_10m_{suffixe}"]
            if info["rafales_previous"]:
                variables.append(f"wind_gusts_10m_{suffixe}")
        for debut, fin in saisons():
            print(f"  Previous Runs {modele} {debut}..{fin}")
            donnees = appel(config.URL_PREVIOUS_RUNS, {
                "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
                "hourly": ",".join(variables), "models": modele,
                "wind_speed_unit": "kn", "timezone": "UTC",
                "start_date": debut, "end_date": fin,
            })
            temps = _vers_serie_temps(donnees)
            h = donnees["hourly"]
            for etiquette in info["horizons"]:
                suffixe = config.HORIZONS[etiquette]
                bloc = pd.DataFrame({
                    "time": temps, "modele": modele, "horizon": etiquette,
                    "vent": pd.array(h[f"wind_speed_10m_{suffixe}"], dtype="Float64"),
                    "direction": pd.array(h[f"wind_direction_10m_{suffixe}"], dtype="Float64"),
                    "rafales": pd.array(
                        h.get(f"wind_gusts_10m_{suffixe}", [None] * len(temps)),
                        dtype="Float64"),
                })
                lignes.append(bloc)
    df = pd.concat(lignes, ignore_index=True)
    df = df.dropna(subset=["vent"]).reset_index(drop=True)
    u, v = composantes_uv(df["vent"].astype(float), df["direction"].astype(float))
    df["u"], df["v"] = u, v
    return df


VARIABLES_HOUR0_BASE = ["wind_speed_10m", "wind_direction_10m",
                        "shortwave_radiation", "cloud_cover",
                        "temperature_2m", "temperature_80m"]


def telecharger_hour0() -> pd.DataFrame:
    lignes = []
    for modele, info in config.MODELES.items():
        variables = list(VARIABLES_HOUR0_BASE)
        if info["rafales_hour0"]:
            variables.append("wind_gusts_10m")
        if info["vent80_hour0"]:
            variables.append("wind_speed_80m")
        for debut, fin in saisons():
            print(f"  Historical (hour-0) {modele} {debut}..{fin}")
            donnees = appel(config.URL_HISTORICAL, {
                "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
                "hourly": ",".join(variables), "models": modele,
                "wind_speed_unit": "kn", "timezone": "UTC",
                "start_date": debut, "end_date": fin,
            })
            temps = _vers_serie_temps(donnees)
            h = donnees["hourly"]
            bloc = {"time": temps, "modele": modele}
            correspondance = {
                "wind_speed_10m": "vent", "wind_direction_10m": "direction",
                "wind_gusts_10m": "rafales", "wind_speed_80m": "vent80",
                "shortwave_radiation": "rayonnement", "cloud_cover": "nebulosite",
                "temperature_2m": "temp2m", "temperature_80m": "temp80",
            }
            for var, colonne in correspondance.items():
                bloc[colonne] = pd.array(h.get(var, [None] * len(temps)), dtype="Float64")
            lignes.append(pd.DataFrame(bloc))
    df = pd.concat(lignes, ignore_index=True)
    df = df.dropna(subset=["vent"]).reset_index(drop=True)
    u, v = composantes_uv(df["vent"].astype(float), df["direction"].astype(float))
    df["u"], df["v"] = u, v
    return df


def principal():
    from pathlib import Path
    Path(config.DOSSIER_PROCESSED).mkdir(parents=True, exist_ok=True)

    print("Téléchargement Previous Runs (prévisions 24/48/96 h)...")
    previsions = telecharger_previous_runs()
    previsions.to_parquet(f"{config.DOSSIER_PROCESSED}/previsions.parquet", index=False)
    print(f"  -> {len(previsions)} lignes")

    print("Téléchargement Historical Forecast (hour-0)...")
    hour0 = telecharger_hour0()
    hour0.to_parquet(f"{config.DOSSIER_PROCESSED}/hour0.parquet", index=False)
    print(f"  -> {len(hour0)} lignes")


if __name__ == "__main__":
    principal()
