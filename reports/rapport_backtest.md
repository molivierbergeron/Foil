# Rapport de backtest — vent au Lac Maskinongé

Période analysée : 2024-05-01 à 2026-07-12 (mai-octobre). Spot : 46.3123° N,
-73.3638° O. Unités : nœuds (nds). Vérité terrain : médiane multi-modèles des
séries « hour-0 » (voir la section Limites).

## L'essentiel en langage clair

- **Ton spot est un spot de vent léger.** Vent médian en journée :
  5 nds ; il faut monter au 90e percentile pour toucher
  8 nds. Avec la barre foilable à 7 nds :
  **2024 : 70 sur 184 ; 2025 : 84 sur 184 ; 2026 : 31 sur 73 jours foilables** — environ 4 jours sur 10. Le système
  ne cherche pas à prévoir le vent « en général », il cherche à attraper ces
  jours-là sans te faire monter au chalet pour rien.

- **Pris un par un, les modèles ne s'entendent pas du tout.** À 24 h
  d'échéance, au moins un modèle annonce une journée GO 318 fois —
  mais les six s'entendent seulement 70 fois. À la même heure, l'écart
  typique entre le modèle le plus optimiste et le plus pessimiste est de
  3 nds (et dépasse 5 nds un jour sur dix) —
  énorme quand le seuil GO/NO-GO est à 7 nds. C'est exactement pourquoi lire
  une seule app météo marche mal ici, et pourquoi la pondération multi-modèles
  de ce projet a une chance de faire mieux.

- **Chaque modèle a un caractère mesurable et stable.** Les GEM canadiens
  lisent systématiquement bas (-0.9 nds au consensus à 24 h) :
  quand ils disent GO, c'est fiable, mais ils ratent la majorité des vraies
  fenêtres. HRDPS lit haut (+1.0 nds) : il ne rate presque rien
  mais crie au loup 34% du temps. Ce sont ces biais-là, mesurés à
  ce spot précis, que `poids_modeles.json` corrige.

- **La distance d'échéance coûte cher.** Un GO annoncé 4 jours d'avance ne
  tient que 76% du temps ; à 24 h,
  93%. La décision « chalet » se prend donc sur une
  cote, jamais sur une certitude — et le dashboard l'affichera toujours
  comme telle.

## Conclusions d'abord

1. **Quel modèle croire à ce spot ?** À 24 h, le plus précis est
   **ICON (Allemagne)** (RMSE 1.2 nds,
   biais +0.1 nds). À 96 h — l'horizon de la décision
   « chalet » — c'est **GEM global (Canada)**
   (RMSE 2.1 nds). *RMSE = erreur typique : à ±2 nds
   près, c'est l'incertitude à laquelle s'attendre sur une heure donnée.*

2. **Qui surestime ?** Le biais le plus marqué est celui de
   **HRDPS (Canada, 2.5 km)** à 24h
   (+1.0 nds en moyenne). Un biais positif = le modèle
   annonce plus de vent qu'il n'en arrive : c'est lui qui fabrique des faux GO.

3. **Quelle confiance accorder à un GO selon l'horizon ?** Sur la prévision
   d'ensemble (médiane des modèles) :
   - GO annoncé à **96 h** : confirmé 76% du temps
     (fourchette 69%–82%, 161 cas).
   - GO annoncé à **48 h** : confirmé 91% du temps
     (85%–94%, 153 cas).
   - GO annoncé à **24 h** : confirmé 93% du temps
     (88%–96%, 176 cas).

   Autrement dit, un « GO chalet » lancé 4 jours d'avance doit se lire comme
   une cote, pas une promesse — et le dashboard l'affichera toujours ainsi.

4. **Les busts ont-ils une signature ?** Sur 172 journées GO à
   24 h, 9 ont été des busts complets (vent resté sous
   7 nds toute la journée). **Non — pas encore de signature détectable.** Les médianes des
   proxys de découplage sont quasi identiques entre busts et bons jours
   (cisaillement 1.69 contre 1.62 ; rayonnement 376 contre
   421 W/m²), et 9 cas ne permettent aucune conclusion (le seuil
   de ce rapport est n ≥ 30 par cellule ; on est loin en dessous). Deux
   lectures : (a) la vérité actuelle étant une médiane de modèles, elle est
   corrélée aux prévisions — les vrais busts « grille dit vent, lac dit rien »
   sont invisibles par construction et ne le resteront pas quand la station au
   lac (phase 4) fournira une vérité indépendante ; (b) tant qu'aucune
   signature n'est validée, le dashboard n'affichera PAS de drapeau
   « découplage » — un drapeau non validé serait de la fausse précision. Le
   diagnostic sera relancé automatiquement quand la vérité station existera.

## Erreur sur le vent moyen (biais et RMSE)

![Biais et RMSE par modèle et horizon](biais_rmse.png)

| Modèle                 | Horizon   |    n |   Biais (nds) |   RMSE (nds) |
|:-----------------------|:----------|-----:|--------------:|-------------:|
| ICON (Allemagne)       | 24h       | 5292 |          0.05 |         1.17 |
| ECMWF IFS 0.25°        | 24h       | 5292 |          0.54 |         1.43 |
| GEM régional (Canada)  | 24h       | 5149 |         -0.83 |         1.46 |
| GEM global (Canada)    | 24h       | 5292 |         -0.88 |         1.49 |
| GFS (États-Unis)       | 24h       | 5292 |          0.43 |         1.59 |
| HRDPS (Canada, 2.5 km) | 24h       | 5292 |          1.02 |         2.1  |
| ICON (Allemagne)       | 48h       | 5292 |          0.08 |         1.48 |
| ECMWF IFS 0.25°        | 48h       | 5292 |          0.5  |         1.65 |
| GEM régional (Canada)  | 48h       | 5287 |         -0.74 |         1.67 |
| GEM global (Canada)    | 48h       | 5160 |         -0.82 |         1.7  |
| GFS (États-Unis)       | 48h       | 5292 |          0.44 |         1.8  |
| GEM global (Canada)    | 96h       | 5232 |         -0.82 |         2.1  |
| ICON (Allemagne)       | 96h       | 5292 |         -0.06 |         2.12 |
| ECMWF IFS 0.25°        | 96h       | 5292 |          0.53 |         2.17 |
| GFS (États-Unis)       | 96h       | 5292 |          0.35 |         2.3  |

Rappels de lecture : HRDPS ne porte que 48 h de prévision (pas de colonne 96 h),
GEM régional s'arrête à 84 h (pas de 96 h non plus).

## Événement « fenêtre foilable » : détection et fausses alertes

Fenêtre foilable = au moins 2 h entre 7 et
16 nds, entre 8 h et 20 h locales, creux passagers
5–7 nds tolérés (voir config.py). Probabilité de détection
(POD) = part des vraies fenêtres que le modèle avait annoncées. Taux de
fausses alertes (FAR) = part des GO annoncés qui ne se sont pas matérialisés.

![Confusion fenêtres](confusion.png)

| Modèle                 | Horizon   |   Jours |   Fenêtres réelles |   Hits |   Fausses alertes |   Manqués | POD (IC 95 %)   | FAR (IC 95 %)   |
|:-----------------------|:----------|--------:|-------------------:|-------:|------------------:|----------:|:----------------|:----------------|
| GEM global (Canada)    | 24h       |     441 |                185 |     89 |                 2 |        96 | 48% (41%–55%)   | 2% (1%–8%)      |
| GEM régional (Canada)  | 24h       |     428 |                177 |     84 |                 4 |        93 | 47% (40%–55%)   | 5% (2%–11%)     |
| ICON (Allemagne)       | 24h       |     441 |                185 |    166 |                31 |        19 | 90% (85%–93%)   | 16% (11%–21%)   |
| ECMWF IFS 0.25°        | 24h       |     441 |                185 |    171 |                60 |        14 | 92% (88%–95%)   | 26% (21%–32%)   |
| GFS (États-Unis)       | 24h       |     441 |                185 |    170 |                73 |        15 | 92% (87%–95%)   | 30% (25%–36%)   |
| HRDPS (Canada, 2.5 km) | 24h       |     441 |                185 |    183 |                96 |         2 | 99% (96%–100%)  | 34% (29%–40%)   |
| GEM régional (Canada)  | 48h       |     440 |                184 |     87 |                10 |        97 | 47% (40%–54%)   | 10% (6%–18%)    |
| GEM global (Canada)    | 48h       |     430 |                179 |     74 |                12 |       105 | 41% (34%–49%)   | 14% (8%–23%)    |
| ICON (Allemagne)       | 48h       |     441 |                185 |    157 |                43 |        28 | 85% (79%–89%)   | 22% (16%–28%)   |
| ECMWF IFS 0.25°        | 48h       |     441 |                185 |    167 |                62 |        18 | 90% (85%–94%)   | 27% (22%–33%)   |
| GFS (États-Unis)       | 48h       |     441 |                185 |    162 |                76 |        23 | 88% (82%–92%)   | 32% (26%–38%)   |
| GEM global (Canada)    | 96h       |     436 |                183 |     68 |                21 |       115 | 37% (30%–44%)   | 24% (16%–33%)   |
| ICON (Allemagne)       | 96h       |     441 |                185 |    136 |                65 |        49 | 74% (67%–79%)   | 32% (26%–39%)   |
| ECMWF IFS 0.25°        | 96h       |     441 |                185 |    149 |                77 |        36 | 81% (74%–86%)   | 34% (28%–40%)   |
| GFS (États-Unis)       | 96h       |     441 |                185 |    141 |                99 |        44 | 76% (70%–82%)   | 41% (35%–48%)   |

## Survie des fenêtres : le chiffre de la décision « chalet »

Parmi les GO annoncés à 96 h par l'ensemble : 122 sur
161 se sont réalisés (76%,
fourchette 69%–82%).

![Survie des GO](survie.png)

| GO annoncé à   | Vérifié à   |   Cas |   Tiennent | Taux (IC 95 %)   |
|:---------------|:------------|------:|-----------:|:-----------------|
| 96h            | 48h         |   161 |        117 | 73% (65%–79%)    |
| 96h            | 24h         |   161 |        124 | 77% (70%–83%)    |
| 96h            | réalisé     |   161 |        122 | 76% (69%–82%)    |
| 48h            | réalisé     |   153 |        139 | 91% (85%–94%)    |
| 24h            | réalisé     |   176 |        163 | 93% (88%–96%)    |

## Diagnostic des busts

![Signature des busts](busts.png)

| Variable           |   Médiane hits |   Médiane busts |   n hits |   n busts |
|:-------------------|---------------:|----------------:|---------:|----------:|
| cisaillement       |           1.62 |            1.69 |      163 |         9 |
| rayonnement_moyen  |         421.21 |          376.29 |      163 |         9 |
| nebulosite_moyenne |          38.88 |           69.83 |      163 |         9 |
| inversion          |          -1.1  |           -0.85 |      163 |         9 |

Variables : cisaillement = ratio vent 80 m / vent 10 m (médiane 8 h–20 h) ;
inversion = temp. 80 m − temp. 2 m en °C (positif = air stable, découplage
probable). La hauteur de couche limite n'est archivée pour aucun modèle chez
Open-Meteo (vérifié par appels réels) — ces proxys la remplacent.

## Stations d'observation réelles (inventaire, rayon ~40 km)

Interrogation de l'API d'Environnement Canada (api.weather.gc.ca,
collections climate-stations / climate-hourly) :

| Station | Distance | Données horaires | Couverture | Verdict |
|---|---|---|---|---|
| Lac Saint-Pierre (701LP0N) | 37 km SE | Oui (vent, direction, temp.) | 1994 → aujourd'hui | **Exploitable** comme vérité secondaire de régime synoptique. Station automatique sur le lac Saint-Pierre : bien exposée, mais plan d'eau et topographie différents — l'écart avec le lac Maskinongé est attendu et sera mesuré, pas supposé. |
| St-Gabriel-de-Brandon (7017270) | 2 km | Non (climat quotidien, fermée) | historique | Inutilisable pour le vent horaire. |
| Toutes les autres (17 stations) | 4–45 km | Non | — | Postes climatologiques quotidiens, pas de vent horaire. |

Aucune station horaire d'EC n'existe à moins de 37 km : la vérité par station
attendra l'anémomètre Ecowitt au bord du lac (phase 4).

## Limites (à lire une fois)

- **La vérité est une médiane de modèles**, pas une observation. Elle capture
  les erreurs synoptiques (la dépression qui n'arrive pas) mais pas l'écart
  résiduel entre la grille de ~10–25 km et le vent réel au milieu du lac.
  Les biais absolus seront requalifiés quand la station du cousin sera en
  place (phase 4) ; les comparaisons entre modèles et entre horizons, elles,
  restent valides.
- **Rafales ECMWF absentes des archives** (vérifié) : le ratio
  rafales/vent appris sur les autres modèles sert de repli
  (ratio médian par modèle dans `data/poids_modeles.json`).
- Le nombre de fenêtres réelles par saison est petit : toutes les proportions
  sont données avec leur intervalle de confiance à 95 % — les fourchettes
  larges sont la réalité, pas un défaut du rapport.

## Fichiers produits

- `data/poids_modeles.json` : biais, RMSE, poids (∝ 1/RMSE², normalisés par
  horizon), corrections par secteur (où n ≥ 30), ratios de rafales,
  fiabilité des GO par horizon. Schéma documenté dans le README.
- `data/processed/*.parquet` : données appariées reproductibles.
