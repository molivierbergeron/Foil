"""Diagnostic des busts : « gros vent prévu, rien reçu ».

Un bust = journée où la prévision d'ensemble annonçait une fenêtre foilable
(à un horizon donné) mais où la vérité n'a montré aucune fenêtre ET un vent
resté faible (max < 9 nds en journée). On cherche une signature de découplage
dans des variables que les modèles produisent aussi en prévision — donc
utilisables au moment du verdict :

- cisaillement : vent 80 m / vent 10 m (fort = la couche de surface décroche)
- rayonnement solaire et nébulosité (peu de soleil = pas de mélange convectif)
- gradient thermique temp80 - temp2m (positif = inversion, air stable)
- mois et heure (le découplage est saisonnier et diurne)

Limite documentée : la hauteur de couche limite (boundary_layer_height) n'est
archivée pour aucun modèle dans Historical Forecast (vérifié par appels réels)
— les proxys ci-dessus la remplacent.
"""

import numpy as np
import pandas as pd

import config
from backtest import jours_foilables, series_jour


def _resume_jour(verite: pd.DataFrame) -> pd.DataFrame:
    """Variables de découplage agrégées par journée locale (8–20 h)."""
    df = verite.reset_index()
    local = df["time"].dt.tz_convert(config.FUSEAU_LOCAL)
    df["date_locale"] = local.dt.date
    df["heure"] = local.dt.hour
    jour = df[(df["heure"] >= config.HEURE_DEBUT) & (df["heure"] < config.HEURE_FIN)]
    grp = jour.groupby("date_locale")
    resume = pd.DataFrame({
        "vent_max": grp["vent"].max(),
        "vent_moyen": grp["vent"].mean(),
        "cisaillement": grp.apply(
            lambda g: float((g["vent80"] / g["vent"].clip(lower=1)).median()),
            include_groups=False),
        "rayonnement_moyen": grp["rayonnement"].mean(),
        "nebulosite_moyenne": grp["nebulosite"].mean(),
        "inversion": grp.apply(
            lambda g: float((g["temp80"] - g["temp2m"]).median()),
            include_groups=False),
    })
    resume["mois"] = pd.to_datetime(resume.index.astype(str)).month
    return resume


def detecter_busts(apparie: pd.DataFrame, verite: pd.DataFrame,
                   horizon: str = "24h") -> pd.DataFrame:
    """Classe chaque journée : hit, bust (GO prévu, rien reçu), manque, calme."""
    ens = (apparie[apparie["horizon"] == horizon]
           .groupby("time")["vent"].median().reset_index())
    prevus = jours_foilables(series_jour(ens))
    verite_df = verite.reset_index()[["time", "vent"]]
    reels = jours_foilables(series_jour(verite_df))
    resume = _resume_jour(verite)

    commun = prevus.index.intersection(reels.index).intersection(resume.index)
    resume = resume.loc[commun].copy()
    p, r = prevus.loc[commun], reels.loc[commun]
    resume["prevu_go"] = p
    resume["reel_go"] = r
    # Bust strict : GO prévu, pas de fenêtre réelle ET vent réellement resté
    # sous la bande (pas un cas limite à 8.9 nds)
    resume["bust"] = p & ~r & (resume["vent_max"] < config.VENT_MIN_FOILABLE)
    resume["categorie"] = np.select(
        [p & r, resume["bust"], p & ~r, ~p & r],
        ["hit", "bust", "fausse_alerte_limite", "manque"], default="calme")
    return resume


def signature_busts(resume: pd.DataFrame) -> pd.DataFrame:
    """Compare les journées bust aux hits sur les variables de découplage."""
    variables = ["cisaillement", "rayonnement_moyen", "nebulosite_moyenne", "inversion"]
    lignes = []
    hits = resume[resume["categorie"] == "hit"]
    busts = resume[resume["categorie"] == "bust"]
    for v in variables:
        lignes.append({
            "variable": v,
            "mediane_hits": float(hits[v].median()) if len(hits) else float("nan"),
            "mediane_busts": float(busts[v].median()) if len(busts) else float("nan"),
            "n_hits": len(hits), "n_busts": len(busts),
        })
    return pd.DataFrame(lignes)
