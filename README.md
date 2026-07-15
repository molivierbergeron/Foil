# Foil — Prévisions de vent calibrées, Lac Maskinongé

Pipeline qui améliore les prévisions de vent locales pour le foiling
(catamaran UFO) au Lac Maskinongé, Québec (46.3123° N, -73.3638° O), en
mesurant l'erreur historique de chaque modèle météo à ce spot précis et en
corrigeant les prévisions en conséquence.

**Ce que le système répond** — deux horizons de décision :

1. **Planification (J-4 à J-2)** : « ça vaut-tu la peine de monter au chalet
   cette fin de semaine ? » — verdict par jour, avec la fiabilité mesurée à
   cet horizon (jamais un GO sec).
2. **Exécution (J-1, jour même)** : « je sors ce matin ou cet après-midi ? »
   — verdict par bloc (matin / après-midi / soirée).

## État du projet

| Phase | État |
|---|---|
| 1. Backtest 2024–2026, rapport, poids calibrés | ✅ Livrée et validée — voir `reports/rapport_backtest.md` |
| 2. Boucle d'apprentissage continue (GitHub Actions) | ✅ Livrée — jobs quotidien et hebdomadaire, testés en local |
| 3. Dashboard public (GitHub Pages) | À venir |
| 4. Station Ecowitt au lac (`TRUTH_SOURCE="station"`) | À venir |
| 5. Correction apprise avancée (MOS) | À venir |
| 6. Alertes (`alertes.py`, placeholder) | Non implémentée — consommera les verdicts existants ; seuils de confiance, horaires et canaux (ntfy) à décider ensemble. |

## Exécuter la phase 1

```bash
pip install requests pandas matplotlib pyarrow
python3 telecharge.py     # télécharge + met en cache (data/raw) + normalise (data/processed)
python3 rapport.py        # backtest complet -> reports/rapport_backtest.md + data/poids_modeles.json
python3 tests/test_fenetre.py && python3 tests/test_verite.py
```

`data/raw/` est un cache : un appel réussi n'est jamais refait. Il n'est pas
commité (reproductible) ; `data/processed/*.parquet` et `data/poids_modeles.json`
le sont.

## Sources de données (validées par appels réels le 2026-07-15)

Tout vient d'Open-Meteo (gratuit, sans clé, CC BY 4.0, usage non commercial) :

- **Previous Runs API** — ce que chaque modèle prévoyait 24 h / 48 h / 96 h
  d'avance (`wind_*_previous_day1/2/4`). Archives depuis janvier 2024.
- **Historical Forecast API** — séries continues « hour-0 » par modèle
  (l'analyse la plus fraîche de chaque modèle).
- **Forecast API** — prévisions courantes (dashboard, phase 3).

### Couverture d'archives par modèle (vérifiée, pas supposée)

| Modèle (identifiant Open-Meteo) | 24 h | 48 h | 96 h | Rafales archivées | Vent 80 m hour-0 |
|---|---|---|---|---|---|
| `gem_global` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `gem_regional` (portée 84 h) | ✓ | ✓ | — | ✓ (24/48 h) | ✓ |
| `gem_hrdps_continental` (portée 48 h) | ✓ | — | — | ✓ (24 h) | ✓ |
| `ecmwf_ifs025` | ✓ | ✓ | ✓ | **✗ nulle part** | ✗ |
| `gfs_global` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `icon_global` | ✓ | ✓ | ✓ | ✓ | ✓ |

Repli rafales ECMWF : ratio médian rafales/vent moyen appris par modèle sur
les séries hour-0, stocké dans `data/poids_modeles.json`
(`ratio_rafales_defaut` sert pour ECMWF).

`boundary_layer_height` n'est archivée pour **aucun** modèle (Historical
Forecast) — le diagnostic de découplage utilise des proxys disponibles
partout : cisaillement vent 80 m / vent 10 m, rayonnement, nébulosité,
gradient thermique 80 m − 2 m.

## Vérité terrain

`TRUTH_SOURCE = "median_hour0"` (config.py) : médiane multi-modèles des
séries hour-0, direction médiane en composantes vectorielles. Un modèle n'est
jamais vérifié contre sa propre analyse seule (erreurs corrélées). Limite :
c'est une vérité de modèles — elle capture le synoptique, pas l'écart
grille-vs-lac. La phase 4 la remplacera par l'anémomètre au bord du lac
(`TRUTH_SOURCE = "station"`), sans autre changement de code.

Inventaire des stations réelles (~40 km) : une seule station horaire active,
**Lac Saint-Pierre** (701LP0N, 37 km SE, sur l'eau, 1994→aujourd'hui) —
vérité secondaire possible pour le régime synoptique. Détails dans le rapport.

## Format de `data/poids_modeles.json` (schéma v1)

Consommable en JavaScript par le dashboard (phase 3) :

```jsonc
{
  "schema_version": 1,
  "genere_le": "2026-07-15",
  "truth_source": "median_hour0",
  "unites": "noeuds",
  "ratio_rafales_defaut": 1.5,          // repli rafales (ECMWF)
  "modeles": {
    "gem_global": {
      "horizons": {
        "24h": { "biais_nds": 0.4, "rmse_nds": 2.1, "poids": 0.21, "n": 12000 }
      },
      "biais_par_secteur": { "24h": { "SO": { "biais_nds": 0.9, "n": 800 } } },
      "ratio_rafales": 1.48
    }
  },
  "fiabilite_go_par_horizon": {          // le chiffre de la décision chalet
    "96h": { "taux_go_confirme": 0.55, "ic95": [0.4, 0.7], "n": 40 }
  },
  "confusion_par_modele": { "gem_global": { "24h": { "pod": 0.8, "far": 0.3 } } }
}
```

Corrections : `vent_corrigé = vent_prévu - biais_nds` (le biais du secteur
remplace le global quand il existe, n ≥ 30). Poids ∝ 1/RMSE², normalisés par
horizon parmi les modèles disponibles.

## Décisions prises

- **Direction du vent** : jamais moyennée en degrés bruts — composantes
  u = −V·sin(θ), v = −V·cos(θ) (convention météo) partout, reconversion en
  degrés seulement pour l'affichage.
- **DST** : tout est stocké en UTC ; conversion America/Toronto au moment de
  l'analyse (pandas gère les changements d'heure).
- **Segmentation** : aucune conclusion sur une cellule de moins de 30 points.
- **Fenêtre foilable** (bande validée par l'utilisateur le 2026-07-15 :
  « à partir de 7 kts c'est bon, 16+ c'est too much ») : ≥ 2 h dans la bande
  7–16 nds entre 8 h et 20 h, creux passagers 5–7 nds tolérés (pas deux
  consécutifs, jamais sous 5 nds), un pas > 16 nds coupe la fenêtre.
  Logique testée dans `tests/test_fenetre.py`.
- Petits échantillons : toutes les proportions sont accompagnées d'un
  intervalle de confiance de Wilson à 95 %.

## Phase 2 — la boucle d'apprentissage continue

Deux workflows GitHub Actions (minutes creuses volontairement, jamais :00) :

- **Quotidien** (`quotidien.yml`, 09:17 UTC) : exécute `job_quotidien.py` —
  récupère pour J-9 à J-3 (archives complètes à J-3) ce que chaque modèle
  prévoyait à 24/48/96 h et la vérité, apparie, et ajoute les lignes
  manquantes à la partition mensuelle `data/verification/AAAA-MM.parquet`.
  **Append-only** : le job ne complète que la partition du mois courant (et
  du mois précédent en début de mois, fenêtre de rattrapage) ; l'historique
  n'est jamais réécrit, jamais d'amend ni de force-push — l'historique Git
  est la piste d'audit de la dérive des modèles. Seul `data/forecast.json`
  (petit : verdicts 7 jours de l'ensemble corrigé) est écrasé à chaque run.
- **Hebdomadaire** (`recalibrage.yml`, lundi 10:43 UTC) : exécute
  `recalibrage.py` — recalcule les poids sur fenêtre glissante (saison
  courante pesant double). **Garde-fou** : les poids candidats, calculés sans
  voir les 60 derniers jours, ne sont appliqués que s'ils battent les poids
  courants sur ces 60 jours (RMSE de l'ensemble corrigé-pondéré). Sinon ils
  sont conservés. Chaque décision est journalisée dans `reports/derive.md`.

**Piège GitHub connu** : GitHub désactive les workflows planifiés après ~60
jours sans activité sur le repo. Réactivation : onglet Actions → le workflow
→ bouton « Enable workflow » (un commit quelconque réactive aussi). Les
commits quotidiens du job maintiennent normalement l'activité — le problème
ne survient que si le job est cassé longtemps.

**Anti-bloat** : partitions mensuelles ≈ 70 Ko/mois. Si le repo dépassait un
jour ~500 Mo, migrer les partitions froides vers GitHub Releases (documenté,
pas implémenté).

## Attribution

Données météo : [Open-Meteo.com](https://open-meteo.com) (CC BY 4.0).
Inventaire de stations : Environnement et Changement climatique Canada
(api.weather.gc.ca).
