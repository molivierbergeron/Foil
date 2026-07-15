"""Job quotidien (GitHub Actions) : la boucle d'apprentissage continue.

1. Récupère, pour les jours J-9 à J-3 (archives Open-Meteo complètes à J-3),
   ce que chaque modèle prévoyait à 24/48/96 h et la vérité (médiane hour-0).
2. Apparie prévu-vs-réalisé et AJOUTE les lignes manquantes à la partition
   mensuelle data/verification/AAAA-MM.parquet. Append-only : on ne retire ni
   ne modifie jamais une ligne existante ; seuls les jours absents sont
   ajoutés, et seules les partitions du mois courant (et du mois précédent,
   pendant les 9 premiers jours du mois) sont touchées.
3. Écrase data/forecast.json (petit) : prévision courante 7 jours de chaque
   modèle + verdicts corrigés — seul fichier réécrit à chaque run.
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import config
import fenetre
from openmeteo_client import appel
from telecharge import composantes_uv, VARIABLES_HOUR0_BASE
from verite import construire_verite

DOSSIER_VERIF = Path("data/verification")
JOURS_RETARD = 3   # les archives sont complètes à J-3
JOURS_FENETRE = 9  # on regarde jusqu'à J-9 (rattrapage si un run a sauté)


def _telecharger_fenetre(debut: str, fin: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Previous Runs + hour-0 pour la petite fenêtre de rattrapage."""
    lignes_prev, lignes_h0 = [], []
    for modele, info in config.MODELES.items():
        variables = []
        for etiquette in info["horizons"]:
            suffixe = config.HORIZONS[etiquette]
            variables += [f"wind_speed_10m_{suffixe}", f"wind_direction_10m_{suffixe}"]
            if info["rafales_previous"]:
                variables.append(f"wind_gusts_10m_{suffixe}")
        donnees = appel(config.URL_PREVIOUS_RUNS, {
            "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
            "hourly": ",".join(variables), "models": modele,
            "wind_speed_unit": "kn", "timezone": "UTC",
            "start_date": debut, "end_date": fin,
        })
        temps = pd.to_datetime(donnees["hourly"]["time"]).tz_localize("UTC")
        h = donnees["hourly"]
        for etiquette in info["horizons"]:
            suffixe = config.HORIZONS[etiquette]
            lignes_prev.append(pd.DataFrame({
                "time": temps, "modele": modele, "horizon": etiquette,
                "vent": pd.array(h[f"wind_speed_10m_{suffixe}"], dtype="Float64"),
                "direction": pd.array(h[f"wind_direction_10m_{suffixe}"], dtype="Float64"),
                "rafales": pd.array(h.get(f"wind_gusts_10m_{suffixe}",
                                          [None] * len(temps)), dtype="Float64"),
            }))

        variables_h0 = list(VARIABLES_HOUR0_BASE)
        if info["rafales_hour0"]:
            variables_h0.append("wind_gusts_10m")
        if info["vent80_hour0"]:
            variables_h0.append("wind_speed_80m")
        donnees = appel(config.URL_HISTORICAL, {
            "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
            "hourly": ",".join(variables_h0), "models": modele,
            "wind_speed_unit": "kn", "timezone": "UTC",
            "start_date": debut, "end_date": fin,
        })
        temps = pd.to_datetime(donnees["hourly"]["time"]).tz_localize("UTC")
        h = donnees["hourly"]
        correspondance = {
            "wind_speed_10m": "vent", "wind_direction_10m": "direction",
            "wind_gusts_10m": "rafales", "wind_speed_80m": "vent80",
            "shortwave_radiation": "rayonnement", "cloud_cover": "nebulosite",
            "temperature_2m": "temp2m", "temperature_80m": "temp80",
        }
        bloc = {"time": temps, "modele": modele}
        for var, colonne in correspondance.items():
            bloc[colonne] = pd.array(h.get(var, [None] * len(temps)), dtype="Float64")
        lignes_h0.append(pd.DataFrame(bloc))

    prev = pd.concat(lignes_prev, ignore_index=True).dropna(subset=["vent"])
    h0 = pd.concat(lignes_h0, ignore_index=True).dropna(subset=["vent"])
    for df in (prev, h0):
        u, v = composantes_uv(df["vent"].astype(float), df["direction"].astype(float))
        df["u"], df["v"] = u, v
    return prev, h0


def mettre_a_jour_verification(aujourdhui: date | None = None) -> int:
    """Ajoute les jours manquants aux partitions mensuelles. Retourne le nb de lignes ajoutées."""
    aujourdhui = aujourdhui or datetime.now(timezone.utc).date()
    debut = (aujourdhui - timedelta(days=JOURS_FENETRE)).isoformat()
    fin = (aujourdhui - timedelta(days=JOURS_RETARD)).isoformat()

    prev, h0 = _telecharger_fenetre(debut, fin)
    verite = construire_verite(h0)
    apparie = prev.merge(
        verite.add_prefix("verite_"), left_on="time", right_index=True, how="inner")
    apparie = apparie.drop(columns=["verite_n_modeles"])

    DOSSIER_VERIF.mkdir(parents=True, exist_ok=True)
    apparie["mois"] = apparie["time"].dt.strftime("%Y-%m")
    ajoutees = 0
    for mois, bloc in apparie.groupby("mois"):
        chemin = DOSSIER_VERIF / f"{mois}.parquet"
        bloc = bloc.drop(columns=["mois"])
        if chemin.exists():
            existant = pd.read_parquet(chemin)
            cle = ["time", "modele", "horizon"]
            deja = existant.set_index(cle).index
            bloc = bloc[~bloc.set_index(cle).index.isin(deja)]
            if bloc.empty:
                continue
            resultat = pd.concat([existant, bloc], ignore_index=True)
        else:
            resultat = bloc
        resultat = resultat.sort_values(["time", "modele", "horizon"])
        resultat.to_parquet(chemin, index=False)
        ajoutees += len(bloc)
    return ajoutees


# ----------------------------------------------------- forecast.json (écrasé)

def _fenetres_par_jour(serie_locale: pd.Series) -> dict:
    """Verdict par date locale : GO/NO + blocs pour chaque jour prévu."""
    verdicts = {}
    jour = serie_locale.between_time(f"{config.HEURE_DEBUT}:00",
                                     f"{config.HEURE_FIN - 1}:00")
    for d, g in jour.groupby(jour.index.date):
        go = len(fenetre.fenetres_du_jour(g.tolist())) > 0
        blocs = {b: fenetre.bloc_foilable(serie_locale[serie_locale.index.date == d], b)
                 for b in config.BLOCS}
        verdicts[d.isoformat()] = {"go": go, "blocs": blocs}
    return verdicts


def generer_forecast_json() -> dict:
    with open(config.FICHIER_POIDS) as f:
        poids = json.load(f)

    modeles_series = {}
    for modele in config.MODELES:
        donnees = appel(config.URL_FORECAST, {
            "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
            "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
            "models": modele, "wind_speed_unit": "kn", "timezone": "UTC",
            "forecast_days": 7,
        })
        modeles_series[modele] = donnees["hourly"]

    # Ensemble corrigé : vent_corrigé = vent - biais(modèle, 24h), pondéré
    temps = pd.to_datetime(modeles_series["gem_global"]["time"]).tz_localize("UTC")
    colonnes = {}
    for modele, h in modeles_series.items():
        info = poids["modeles"].get(modele, {}).get("horizons", {}).get("24h")
        if info is None:
            continue
        s = pd.Series(pd.array(h["wind_speed_10m"], dtype="Float64"),
                      index=pd.to_datetime(h["time"]).tz_localize("UTC"))
        colonnes[modele] = (s.astype(float) - info["biais_nds"]).reindex(temps)
    ensemble = pd.DataFrame(colonnes).median(axis=1)
    ensemble.index = ensemble.index.tz_convert(config.FUSEAU_LOCAL)

    verdicts = _fenetres_par_jour(ensemble)
    return {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "spot": {"latitude": config.LATITUDE, "longitude": config.LONGITUDE},
        "unites": "noeuds",
        "verdicts_ensemble": verdicts,
        "fiabilite_go_par_horizon": poids.get("fiabilite_go_par_horizon", {}),
        "poids_version": poids.get("genere_le"),
    }


def principal():
    n = mettre_a_jour_verification()
    print(f"Vérification : {n} lignes ajoutées aux partitions mensuelles")
    fc = generer_forecast_json()
    with open("data/forecast.json", "w") as f:
        json.dump(fc, f, indent=1, ensure_ascii=False)
    print("data/forecast.json écrasé (verdicts:",
          sum(1 for v in fc["verdicts_ensemble"].values() if v["go"]), "GO /",
          len(fc["verdicts_ensemble"]), "jours)")


if __name__ == "__main__":
    principal()
