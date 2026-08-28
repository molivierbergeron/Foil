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

# Identifiant de la DÉFINITION de la vérité. À incrémenter dès que la
# composition de MODELES_VERITE change : les métriques calculées avant et
# après ne sont plus comparables, et l'archive append-only doit pouvoir dire
# laquelle des deux a servi pour chaque ligne.
VERITE_VERSION = "median_hour0/v1"

# --- Sources Open-Meteo (validées par appels réels, voir README) ---
URL_PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
URL_HISTORICAL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
URL_FORECAST = "https://api.open-meteo.com/v1/forecast"

# Horizons de vérification : étiquette -> suffixe Previous Runs
HORIZONS = {"24h": "previous_day1", "48h": "previous_day2", "96h": "previous_day4"}

# Modèles et couverture d'archives, VALIDÉES par appels réels le 2026-07-15
# (gfs_hrrr ajouté et validé de la même façon le 2026-08-28) :
# - horizons : quels previous_dayN sont archivés (portée de prévision du modèle)
# - rafales_previous : rafales archivées dans Previous Runs ?
# - rafales_hour0 / vent80_hour0 / temp80_hour0 : dispo dans Historical Forecast ?
#   (temp80 est un drapeau distinct de vent80 : HRRR archive le vent à 80 m
#    mais pas la température à 80 m — le gradient thermique lui est donc
#    indisponible, contrairement aux cinq autres modèles qui ont les deux.)
MODELES = {
    "gem_global": {
        "nom": "GEM global (Canada)",
        "horizons": ["24h", "48h", "96h"],
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
        "temp80_hour0": True,
    },
    "gem_regional": {
        "nom": "GEM régional (Canada)",
        "horizons": ["24h", "48h"],  # portée 84 h : pas de day4
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
        "temp80_hour0": True,
    },
    "gem_hrdps_continental": {
        "nom": "HRDPS (Canada, 2.5 km)",
        "horizons": ["24h"],  # portée 48 h : day1 seulement
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
        "temp80_hour0": True,
    },
    "gfs_hrrr": {
        "nom": "HRRR (États-Unis, 3 km)",
        "horizons": ["24h"],  # portée 48 h : day1 seulement, comme HRDPS
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
        # Seul modèle sans temperature_80m archivée (vérifié 2026-08-28) : il
        # ne participe donc pas au gradient thermique du diagnostic de busts.
        "temp80_hour0": False,
    },
    "ecmwf_ifs025": {
        "nom": "ECMWF IFS 0.25°",
        "horizons": ["24h", "48h", "96h"],
        # Rafales absentes des archives Previous Runs ET de Historical Forecast :
        # repli = ratio rafales/vent appris sur les autres modèles.
        "rafales_previous": False, "rafales_hour0": False, "vent80_hour0": False,
        "temp80_hour0": False,
    },
    "gfs_global": {
        "nom": "GFS (États-Unis)",
        "horizons": ["24h", "48h", "96h"],
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
        "temp80_hour0": True,
    },
    "icon_global": {
        "nom": "ICON (Allemagne)",
        "horizons": ["24h", "48h", "96h"],
        "rafales_previous": True, "rafales_hour0": True, "vent80_hour0": True,
        "temp80_hour0": True,
    },
}

# --- Membres de l'ensemble EN SERVICE ---
# Les modèles qui VOTENT dans le jeu de poids actif. Troisième liste
# volontairement distincte, pour la même raison que MODELES_VERITE :
#
#   MODELES         = ce qu'on télécharge, archive, note et affiche
#   MODELES_ENSEMBLE = ce qui calcule le verdict en service
#   MODELES_VERITE   = ce qui définit la cible (gelée)
#
# Sans cette séparation, ajouter une clé à MODELES ferait entrer le nouveau
# modèle dans les poids au recalibrage hebdomadaire suivant — donc en
# service, tout seul, un lundi matin, sans qu'aucune décision ait été prise
# ni qu'aucun test n'échoue. C'est précisément ce qu'un modèle à l'essai ne
# doit pas pouvoir faire : il entre par un `versions.py --activer` explicite,
# jamais par un cron.
#
# Pour promouvoir un modèle : l'ajouter ici, relancer un backtest complet,
# et comparer les versions avant d'activer.
MODELES_ENSEMBLE = (
    "gem_global",
    "gem_regional",
    "gem_hrdps_continental",
    "ecmwf_ifs025",
    "gfs_global",
    "icon_global",
)

_hors = [m for m in MODELES_ENSEMBLE if m not in MODELES]
if _hors:
    raise ValueError(
        f"MODELES_ENSEMBLE contient des modèles absents de MODELES : {_hors}. "
        "Un membre de l'ensemble doit être téléchargé, donc déclaré dans MODELES."
    )
del _hors


# --- Composition de la vérité terrain (GELÉE) ---
# Les six modèles dont la médiane hour-0 fait la vérité. Cette liste est
# volontairement SÉPARÉE de MODELES : ajouter un modèle de prévision ne doit
# jamais changer la vérité, sinon les lignes d'avant et d'après l'ajout ne
# sont plus comparables et les biais/RMSE publiés deviennent faux sans que
# rien ne le signale (l'archive data/verification/ est append-only).
#
# Pour ajouter un modèle À LA VÉRITÉ (décision lourde, rarement justifiée) :
# 1. l'ajouter ici, 2. incrémenter VERITE_VERSION, 3. relancer un backtest
# complet — les partitions existantes gardent l'estampille de l'ancienne
# vérité et restent lisibles telles quelles.
MODELES_VERITE = (
    "gem_global",
    "gem_regional",
    "gem_hrdps_continental",
    "ecmwf_ifs025",
    "gfs_global",
    "icon_global",
)

# Garde-fou : une faute de frappe dans MODELES_VERITE amputerait la vérité en
# silence (médiane sur 5 modèles au lieu de 6). On échoue à l'import.
_inconnus = [m for m in MODELES_VERITE if m not in MODELES]
if _inconnus:
    raise ValueError(
        f"MODELES_VERITE contient des modèles absents de MODELES : {_inconnus}. "
        "Un modèle de vérité doit être téléchargé, donc déclaré dans MODELES."
    )
del _inconnus


def modeles_telechargement() -> list[str]:
    """Modèles à télécharger : membres de prévision + membres de vérité.

    Aujourd'hui MODELES_VERITE ⊆ MODELES, mais l'union garde le pipeline
    correct si un modèle sortait un jour des membres de prévision tout en
    restant dans la vérité (sa série hour-0 resterait nécessaire).
    """
    return list(MODELES) + [m for m in MODELES_VERITE if m not in MODELES]


# Saisons couvertes par le backtest (début, fin incluse) — la saison courante
# s'arrête à J-3 pour laisser les archives se compléter.
SAISONS_BACKTEST = [
    ("2024-05-01", "2024-10-31"),
    ("2025-05-01", "2025-10-31"),
    ("2026-05-01", None),  # None = calculé à l'exécution (aujourd'hui - 3 jours)
]

# --- Vérification croisée sur observation réelle (piste parallèle) ---
# Un anémomètre officiel, à 38 km, sur l'eau, horaire, sans trou depuis 1994.
# Ce n'est PAS le lac : plan d'eau bien plus ouvert (vent médian de jour
# 9,2 nds contre ~5 au Maskinongé), donc les biais absolus mesurés là-bas ne
# se transplantent pas. Ce qui s'y mesure honnêtement, c'est la COMPÉTENCE
# relative des modèles — quel modèle suit le mieux le passage réel des
# systèmes — contre une vraie mesure et non contre un consensus de modèles.
#
# Étanchéité volontaire : cette piste n'alimente ni les poids, ni la vérité,
# ni les verdicts. Elle accumule, elle diagnostique, et elle deviendra
# comparable le jour où l'anémomètre du lac existera (phase 4).
STATION_CROISEE = {
    "id": "701LP0N",
    "nom": "Lac Saint-Pierre",
    "latitude": 46.195,
    "longitude": -72.896,
    "distance_km": 38,
}
URL_CLIMATE_HOURLY = "https://api.weather.gc.ca/collections/climate-hourly/items"
DOSSIER_VERIF_CROISEE = "data/verification_croisee"

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
