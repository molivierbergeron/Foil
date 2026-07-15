"""Configuration centrale — Engin de prévisions locales calibrées, Lac Maskinongé.

Toutes les constantes du sport et des sources de données vivent ici.
Unités : nœuds (kn) partout pour le vent, degrés météo pour la direction
(direction D'OÙ vient le vent), heures locales America/Toronto pour les fenêtres.
"""

# --- Spot ---
LATITUDE = 46.3123
LONGITUDE = -73.3638
FUSEAU_LOCAL = "America/Toronto"

# --- Paramètres du sport (catamaran UFO, foil) ---
# Validés par l'utilisateur (2026-07-15) : « à partir de 7 kts c'est bon,
# 16+ c'est too much ». La zone marginale garde 2 nds sous la bande.
VENT_MIN_FOILABLE = 7.0   # nds, bas de la bande foilable
VENT_MAX_FOILABLE = 16.0  # nds, haut de la bande foilable
VENT_MARGINAL = 5.0       # nds, plancher de la zone marginale (5–7 nds)
DUREE_MIN_FENETRE = 2     # heures consécutives (pas horaires) dans la bande
HEURE_DEBUT = 8           # heure locale, début de la journée navigable
HEURE_FIN = 20            # heure locale, fin de la journée navigable (exclusif)
RATIO_RAFALEUX = 1.6      # rafales / vent moyen au-delà duquel c'est rafaleux
MOIS_SAISON = [5, 6, 7, 8, 9, 10]  # mai à octobre

# --- Vérité terrain ---
# "median_hour0" : médiane multi-modèles des séries hour-0 (défaut, phase 1).
# "station"      : station Ecowitt au lac (phase 4, non branchée).
TRUTH_SOURCE = "median_hour0"

# --- Sources Open-Meteo (validées par appels réels, voir README) ---
URL_PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
URL_HISTORICAL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
URL_FORECAST = "https://api.open-meteo.com/v1/forecast"

# Horizons de vérification : étiquette -> suffixe Previous Runs
HORIZONS = {"24h": "previous_day1", "48h": "previous_day2", "96h": "previous_day4"}

# Modèles et couverture d'archives, VALIDÉES par appels réels le 2026-07-15 :
# - horizons : quels previous_dayN sont archivés (portée de prévision du modèle)
# - rafales_previous : rafales archivées dans Previous Runs ?
# - rafales_hour0 / vent80_hour0 : dispo dans Historical Forecast ?
MODELES = {
    "gem_global": {
        "nom": "GEM global (Canada)",
        "horizons": ["24h", "48h", "96h"],
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
    },
    "gem_regional": {
        "nom": "GEM régional (Canada)",
        "horizons": ["24h", "48h"],  # portée 84 h : pas de day4
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
    },
    "gem_hrdps_continental": {
        "nom": "HRDPS (Canada, 2.5 km)",
        "horizons": ["24h"],  # portée 48 h : day1 seulement
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
    },
    "ecmwf_ifs025": {
        "nom": "ECMWF IFS 0.25°",
        "horizons": ["24h", "48h", "96h"],
        # Rafales absentes des archives Previous Runs ET de Historical Forecast :
        # repli = ratio rafales/vent appris sur les autres modèles.
        "rafales_previous": False, "rafales_hour0": False, "vent80_hour0": False,
    },
    "gfs_global": {
        "nom": "GFS (États-Unis)",
        "horizons": ["24h", "48h", "96h"],
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
    },
    "icon_global": {
        "nom": "ICON (Allemagne)",
        "horizons": ["24h", "48h", "96h"],
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
    },
}

# Saisons couvertes par le backtest (début, fin incluse) — la saison courante
# s'arrête à J-3 pour laisser les archives se compléter.
SAISONS_BACKTEST = [
    ("2024-05-01", "2024-10-31"),
    ("2025-05-01", "2025-10-31"),
    ("2026-05-01", None),  # None = calculé à l'exécution (aujourd'hui - 3 jours)
]

# --- Segmentation des rapports ---
SECTEURS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]  # 8 secteurs de 45°
N_MIN_SEGMENT = 30  # taille minimale d'échantillon pour conclure sur une cellule

# --- Blocs horaires (heures locales) pour le verdict d'exécution ---
# Découpage demandé par l'utilisateur (AM 8-11, midi 11-13, PM 14-18) ;
# midi étendu à 14 h pour ne pas laisser 13 h-14 h orphelin.
BLOCS = {"matin": (8, 11), "midi": (11, 14), "apres_midi": (14, 18)}

# --- Stockage ---
DOSSIER_RAW = "data/raw"
DOSSIER_PROCESSED = "data/processed"
FICHIER_POIDS = "data/poids_modeles.json"
