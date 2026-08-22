# Évaluation de nouvelles sources de données (2026-08-09)

Déclencheur : évaluation du portail **imeteo.ca** (André Plante) comme source
potentielle, et plus largement inventaire de ce qui pourrait s'ajouter aux six
modèles actuels.

Méthode : même règle que le reste du projet — **aucune couverture supposée**.
Chaque affirmation ci-dessous vient d'un appel réel effectué le 2026-08-09 au
point du spot (46.3123 N, -73.3638 O).

---

## 1. Verdict sur imeteo.ca

**imeteo.ca n'est pas une source de données — c'est un portail de liens et de
cartes.** L'inventaire complet de la page d'accueil (43 liens) donne :

| Catégorie | Contenu réel | Exploitable par Foil ? |
|---|---|---|
| Cartes de modèles, cartes LAM, cartes de vent | Images PNG générées à partir de **HRDPS / RDPS / GDPS / GFS / ECMWF** (mentions trouvées dans le code de la page `imeteomaps?windmaps`) | Non — images, pas de séries ponctuelles. Et ce sont **exactement les modèles déjà ingérés** via Open-Meteo. |
| Téléchargeur GRIB Saint-Laurent | Interpolation maison de **ECCC/SMC MSC Datamart** | Non — GRIB marin, redondant avec Open-Meteo |
| Prévisions d'ensemble Canada-US | Images EPSgram **NAEFS** hébergées chez `collaboration.cmc.ec.gc.ca` | Non directement, **mais le concept est la meilleure idée du lot** — voir P3 |
| Séries temporelles Google map / WMS | Application web maison (visualisation) | Non |
| Téphigrammes, dérivées de pression | Images | Non |
| Satellite, radar, MAPLE McGill, foudre | Images ECCC / NOAA / Blitzortung | Non (nowcast visuel, jour même) |
| **Stations météo privées** | Page de 3 liens : WunderMap, liste UQAM/meteocentre, une station au Lac des Deux Montagnes (85 km) | **La seule piste réellement intéressante** — voir P5 |
| Données historiques / normales | Liens vers climat.meteo.gc.ca | Non — déjà couvert |

**Conclusion : rien à brancher depuis imeteo.ca.** Le site est excellent comme
outil de lecture humaine (un coup d'œil radar/satellite avant de partir), pas
comme source machine. Sa valeur pour ce projet est indirecte : il rappelle
trois familles de données que Foil n'exploite pas encore — **les modèles à
haute résolution, les ensembles, et les observations réelles**. C'est là-dessus
que porte le reste de ce rapport.

---

## 2. Le vrai goulot d'étranglement n'est pas le nombre de modèles

Avant de recommander quoi que ce soit, un constat qui conditionne tout le
reste. La vérité terrain actuelle est la **médiane hour-0 des six mêmes
modèles** qui sont notés. Conséquence mesurable, visible dans
`reports/rapport_backtest.md` :

> **HRDPS (2.5 km) est le modèle le plus mal noté** — RMSE 2.10 nds, biais
> +1.02 nds — alors que c'est le **seul modèle assez fin pour voir le lac**.

Ce n'est probablement pas une erreur de HRDPS : c'est la métrique qui le
punit de s'écarter du consensus de cinq modèles globaux à 13–25 km, lesquels
ne résolvent ni le lac, ni la brise de lac, ni la rugosité locale. La
médiane multi-modèles récompense la conformité au synoptique, pas la justesse
locale.

**Conséquence directe sur cette évaluation :** ajouter des modèles globaux
supplémentaires ajoute surtout des membres à un consensus auto-référentiel.
Le gain marginal est faible et le risque est réel (voir §5). Le seul
ajout qui échappe à cette critique est celui d'une **observation réelle**, et
c'est justement ce qu'aucune source publique ne fournit ici (P5).

Cela ne veut pas dire « ne rien ajouter » — deux ajouts (P1, P2) restent
défendables même sous cette réserve, et un troisième (P3) répond à un besoin
produit que les modèles déterministes ne peuvent pas couvrir. Mais l'ordre de
priorité découle de ce constat.

---

## 3. Ce qui existe réellement — inventaire vérifié le 2026-08-09

### 3.1 Modèles disponibles au spot (Forecast API)

| Modèle | Vent 10 m | Rafales | Vent 80 m | Hauteur couche limite |
|---|---|---|---|---|
| `gfs_hrrr` (**3 km, NOAA**) | ✓ | ✓ | ✓ | **✓** |
| `ncep_nbm_conus` (blend statistique NOAA) | ✓ | ✓ | ✓ | ✗ |
| `ukmo_global_deterministic_10km` | ✓ | ✓ | ✗ | ✗ |
| `cma_grapes_global` | ✓ | ✓ | ✓ | ✗ |
| `meteofrance_arpege_world025` | ✓ | ✓ | ✓ | ✗ |
| `gem_seamless` (assemblage CMC) | ✓ | ✓ | ✓ | ✗ |
| `ecmwf_aifs025_single` (IA) | ✓ | ✗ | ✗ | ✗ |
| `gfs_global` (déjà utilisé) | ✓ | ✓ | ✓ | **✓** |
| `icon_eu`, `ukmo_ukv`, `knmi/dmi_harmonie` | — | — | — | hors domaine (Europe) |

**Fait notable : HRRR couvre le Lac Maskinongé.** Le domaine CONUS du modèle
convectif 3 km de la NOAA remonte assez au nord pour inclure la Lanaudière —
ce n'était pas acquis d'avance.

**Correction à apporter au README :** l'affirmation « `boundary_layer_height`
n'est archivée pour **aucun** modèle » n'est plus vraie. Elle est disponible
en hour-0 pour `gfs_hrrr` (au moins depuis 2025-01) et `gfs_global` (depuis
2025 ; absente en 2024-06). En revanche elle **n'existe pas** dans Previous
Runs (0/144 testé sur les deux modèles) : elle est donc utilisable comme
diagnostic côté vérité et en temps réel le jour même, **jamais** comme
prédicteur à 24/48/96 h.

### 3.2 Backtestabilité — Previous Runs (le critère qui décide)

Un modèle non archivé ne peut pas être calibré : il est inutilisable dans ce
projet. Nombre d'heures non nulles sur des fenêtres de 7 jours (max 168) :

| Modèle | 2024-06 | 2025-06 | 2026-06 | Rafales |
|---|---|---|---|---|
| `gfs_hrrr` | d1 = 168 | d1 = 168 | d1 = 168 | ✓ |
| `ncep_nbm_conus` | **0** | d1/d2/d4 = 168 | d1/d2/d4 = 168 | ✓ |
| `ukmo_global_deterministic_10km` | **0** | d1 = 21, d4 = 147 (**incohérent**) | d1 = 168, d2 = 139, d4 = **29** | ✓ |
| `cma_grapes_global` | 168 partout | 168 partout | 168 partout | ✓ |
| `meteofrance_arpege_world025` | — | — | d1 = 60, d2 = 36, d4 = 0 | partiel |
| `ecmwf_aifs025_single` | — | — | d1/d2/d4 = 168 | **✗** |

`gfs_hrrr` n'a que `previous_day1` : c'est attendu (portée 48 h), même
situation que HRDPS.

### 3.3 Séries hour-0 (Historical Forecast) — pour la vérité et le ratio rafales

| Modèle | 2024-05 | 2025-07 |
|---|---|---|
| `gfs_hrrr` | vent + rafales + 80 m ✓ (BLH ✗) | tout ✓ **y compris BLH** |
| `ncep_nbm_conus` | **✗ (rien)** | vent + rafales + 80 m ✓ |
| `ukmo_global_deterministic_10km` | vent + rafales ✓ (pas de 80 m) | idem |
| `cma_grapes_global` | tout ✓ | tout ✓ |
| `ecmwf_aifs025_single` | ✗ | vent seul (pas de rafales) |

### 3.4 Ensembles (Ensemble API, gratuit, sans clé)

| Système | Membres (vent) | Rafales par membre |
|---|---|---|
| `ecmwf_ifs025` | **51** | ✓ |
| `icon_global` | 40 | ✓ |
| `gfs025` / `gfs05` (GEFS) | 31 | ✓ |
| `gem_global_ensemble` (GEPS) | 21 | ✓ |
| `bom_access_global_ensemble` | 18 | ✓ |

- CORS : `Access-Control-Allow-Origin: *` → **appelable directement par le
  dashboard**, conforme à l'architecture de fraîcheur de la phase 3.
- Poids : 72 membres × 7 jours × 2 variables = **122 Ko** — acceptable en
  mobile.
- **Limite dure : pas d'archive.** `start_date` refusé avant ~2026-05
  (fenêtre glissante d'environ 92 jours). Impossible de backtester sur
  2024–2025 ; il faut **accumuler soi-même**, avec un amorçage immédiat
  possible sur mai–août 2026 (la saison en cours).

Exemple réel capté pendant l'évaluation (ECMWF + GEPS, h+24) :
**min 1,6 nds / médiane 5,3 / max 8,4**. La médiane dit NO-GO, une partie des
membres dit GO. C'est précisément le chiffre que le système ne sait pas
produire aujourd'hui.

### 3.5 Observations réelles — l'inventaire est décevant, et c'est confirmé

Interrogation de `api.weather.gc.ca` (SWOB temps réel, réseaux ECCC **et
partenaires**), toutes stations dans un rayon de 110 km :

| Distance | Station | Vent |
|---|---|---|
| **38,2 km** | LAC SAINT-PIERRE (701LP0N) | ✓ |
| 52,6 / 53,0 / 65,2 km | Trois-Rivières (×3) | ✓ |
| 55,0 km | Nicolet | ✓ |
| 55,8 km | Shawinigan | ✓ |
| 56,1 km | L'Assomption | ✓ |
| 64,9 km | Rivière La Pêche | ✓ |
| 79,1 km | Saint-Michel-des-Saints | ✓ |

**Aucune station à moins de 38 km** — l'inventaire du README est confirmé, y
compris en incluant les réseaux partenaires. La page « stations privées »
d'imeteo.ca ne change rien : elle pointe vers WunderMap et une liste UQAM,
sans station identifiée près de Saint-Gabriel-de-Brandon.

---

## 4. Recommandation — ordre de priorité

### P0 — Découpler « modèles de prévision » et « modèles de vérité » (prérequis)

**Ce n'est pas une source, c'est le verrou à lever avant d'en ajouter une.**

`verite.construire_verite()` prend la médiane de tout ce qui arrive dans
`hour0`, et `job_quotidien` remplit `hour0` en itérant sur `config.MODELES`.
**Ajouter une clé à `config.MODELES` change donc silencieusement la vérité
terrain** — ce qui :

1. casse la comparabilité de `data/verification/*.parquet`, qui est
   append-only : les lignes d'avant seraient vérifiées contre une médiane à 6
   modèles, celles d'après contre une médiane à 7 ou 9 ;
2. invalide les biais et RMSE publiés sans que rien ne le signale ;
3. contamine `fiabilite_go_par_horizon`, le chiffre affiché à l'utilisateur.

**Correctif :** introduire `MODELES_VERITE` (gelé sur les six actuels) séparé
de `MODELES` (membres de prévision, extensible), écrire la composition de la
vérité dans la partition de vérification, et incrémenter `schema_version`.
Coût : ~1 h. Sans ça, tout ajout de modèle est une régression silencieuse.

### P1 — `gfs_hrrr` (HRRR 3 km) — le meilleur rapport valeur/coût

**Pourquoi :** deuxième modèle à maille convective, et le seul autre membre
capable de résoudre le lac et les circulations locales. Il est aussi
**indépendant de la filière canadienne** : aujourd'hui la seule information
haute résolution du système vient de HRDPS, et elle est pondérée à 0,082 —
autrement dit le système est presque aveugle au local. HRRR donne un second
avis, produit par un centre différent, sur exactement la question qui décide
d'une sortie l'après-midi.

**Ce qui est vérifié :** `previous_day1` complet sur les trois saisons
(2024/2025/2026) avec rafales ; hour-0 complet depuis 2024-05 avec rafales et
vent 80 m ; BLH depuis 2025-01.

**Portée :** horizon 24 h uniquement — donc le verdict d'exécution
(matin/midi/après-midi), pas la décision chalet.

**Coût :** +2 appels/jour au job quotidien, +1 appel au dashboard. Aucun
changement d'architecture (il entre dans `MODELES` comme HRDPS, avec
`horizons: ["24h"]`).

**Test d'acceptation :** le RMSE de l'ensemble corrigé-pondéré à 24 h
s'améliore-t-il sur les 60 derniers jours ? Même garde-fou que le
recalibrage hebdomadaire. Si HRRR se fait pondérer à ~0,08 comme HRDPS, ce
sera l'indice que le problème est bien la vérité (§2), pas le modèle — c'est
une information en soi.

### P2 — `ncep_nbm_conus` (National Blend of Models) — le « MOS gratuit »

**Pourquoi :** NBM n'est pas un modèle physique, c'est un **blend
multi-modèles déjà post-traité statistiquement et débiaisé par la NOAA**,
avec calibration contre observations. C'est, en substance, ce que la phase 5
(`mos.py`) a essayé de construire maison et qui n'a pas rendu de gain net
(-5,8 % à 24 h). Utiliser un MOS national mature comme membre revient à
importer gratuitement un travail de post-traitement que ce projet n'a ni les
données ni le volume pour refaire.

**Ce qui est vérifié :** 24/48/96 h archivés avec rafales, **mais seulement à
partir de 2025** (rien en 2024-06) ; hour-0 idem. Donc ~2 saisons de
backtest au lieu de 3 — assez pour conclure avec les seuils du projet
(n ≥ 30 largement dépassé), pas assez pour la segmentation par secteur la
plus fine.

**Attention :** NBM inclut déjà GFS, HRRR et d'autres. Ses erreurs sont donc
**corrélées** aux membres existants ; le calcul de poids ∝ 1/RMSE² suppose
implicitement l'indépendance et **surpondérera** ce qui est compté deux
fois. À intégrer en le traitant comme un membre à part (ou en comparant NBM
seul contre l'ensemble pondéré, plutôt qu'en le versant dans le mélange).
C'est le point à trancher avant de coder.

### P3 — Ensembles (ECMWF 51 membres) — le seul ajout qui change le **produit**

**Pourquoi :** c'est la seule source qui répond à une question que six
modèles déterministes ne peuvent pas traiter. Aujourd'hui, un GO à 96 h
s'affiche avec « 76 % » — une moyenne historique, la même pour tous les
jours. Or la vraie question est : *ce samedi-ci*, est-ce un cas serré ou un
cas franc ? Un ensemble à 51 membres répond directement :
**P(vent ≥ 7 nds pendant ≥ 2 h)**, calculée sur les membres, jour par jour.
C'est le chiffre qui manque au cas d'usage n°1 du projet (« ça vaut-tu la
peine de monter au chalet ? »).

Bénéfice secondaire, mesurable : la dispersion inter-membres est un
**prédicteur de fiabilité** — les jours à faible dispersion méritent plus de
confiance que le taux moyen, les jours à forte dispersion moins. Ça
transforme un chiffre statique en une cote du jour.

**Le blocage, et pourquoi ça reste en P3 :** pas d'archive au-delà de ~92
jours. On ne peut pas backtester la calibration de ces probabilités sur
2024–2025 ; il faut faire tourner le système une saison pour la valider. La
règle du projet — ne rien afficher qui ne soit pas validé — impose donc :

1. **Étape A (immédiat, faible coût) :** le job quotidien enregistre chaque
   jour la distribution des membres (P(GO) et quantiles p10/p50/p90) dans une
   nouvelle partition. Amorçage possible tout de suite sur mai–août 2026.
   Rien n'est affiché.
2. **Étape B (après ~1 saison) :** courbe de fiabilité (les jours annoncés à
   70 % se réalisent-ils 70 % du temps ?) et recalibration si nécessaire.
3. **Étape C :** affichage, seulement si l'étape B valide.

### P4 — `ukmo_global_deterministic_10km` — bon candidat, archive pas prête

**Pourquoi :** cinquième centre indépendant (le Met Office est un des
meilleurs modèles globaux), 10 km — plus fin que GFS, ICON et ECMWF, à
24/48/96 h avec rafales.

**Pourquoi pas maintenant :** l'archive Previous Runs est incohérente
(0 en 2024, 21/168 en 2025 sur d1, 29/168 en 2026 sur d4). Elle est
manifestement en cours de constitution chez Open-Meteo. **Recommandation :
re-tester dans 6 à 12 mois** ; l'ajouter aujourd'hui donnerait des poids
calculés sur des échantillons troués — exactement ce que la règle
« n ≥ 30 par cellule » cherche à éviter.

### P5 — Observations réelles au lac — la plus grande valeur, hors de portée publique

C'est l'ajout qui débloquerait tout le reste (§2), et **aucune source
publique ne le fournit** : station officielle la plus proche à 38 km, réseaux
partenaires inclus. La **phase 4 (anémomètre Ecowitt au lac) reste donc la
bonne réponse** et devrait passer devant P2/P3/P4 en valeur scientifique —
elle est juste bloquée par du matériel, pas par du code (`station_ecowitt.py`
est prêt).

Deux compléments possibles en attendant, par ordre de sérieux :

1. **Lac Saint-Pierre (701LP0N, 38 km SE, sur l'eau, horaire, depuis 1994)**
   comme *vérité secondaire de régime synoptique* — déjà identifié dans le
   README. Utilité réelle : c'est une observation **réellement indépendante
   des modèles**, sur un plan d'eau. Trop loin pour arbitrer une fenêtre
   locale, mais suffisant pour répondre à une question qu'on ne peut pas
   poser aujourd'hui : *quand les modèles se plantent, se plantent-ils sur le
   synoptique ou sur le local ?* Coût faible (`api.weather.gc.ca`, sans clé),
   valeur diagnostique élevée.
2. **Stations privées (Wunderground / Ecowitt.net)** : à vérifier
   manuellement sur la carte, il n'existe pas d'inventaire programmable
   gratuit. Qualité très variable (anémomètres mal exposés, mâts à 3 m dans
   un jardin). À ne considérer que si une station se trouve **au bord du
   lac** — sinon le bruit d'exposition dépasse le signal recherché. À noter :
   l'Ecowitt de la phase 4 pourra elle-même publier sur ces réseaux.

---

## 5. Écartés, et pourquoi

| Source | Raison |
|---|---|
| `cma_grapes_global` | Archive complète sur 3 saisons — le seul écarté qui soit techniquement prêt. Mais la performance de GRAPES en Amérique du Nord est la plus faible des grands centres ; il finirait à un poids marginal tout en ajoutant un appel et un membre à la médiane de vérité. À reconsidérer seulement si P1/P2 déçoivent. |
| `meteofrance_arpege_world025` | Archive Previous Runs incomplète (60/36/0) — non calibrable. |
| `ecmwf_aifs025_single` | Pas de rafales (même trou qu'ECMWF IFS, qui coûte déjà un repli par ratio), pas de vent 80 m, hour-0 absent en 2024. Modèle IA intéressant à surveiller, pas prêt ici. |
| `gem_seamless` | Assemblage HRDPS→RDPS→GDPS par Open-Meteo : **redondant par construction** avec les trois membres GEM déjà présents, et introduirait une corrélation forte. |
| MSC Datamart / GeoMet en direct | Ce qu'imeteo.ca utilise. Donnerait HRDPS sur grille native et REPS (ensemble régional 2,5 km, absent d'Open-Meteo). Mais : parsing GRIB2, aucune archive des runs passés (donc **non backtestable**, ce qui est rédhibitoire ici), et une dépendance lourde pour un gain que l'interpolation Open-Meteo couvre déjà. Effort élevé, bénéfice faible. |
| Cartes / radar / satellite / foudre / téphigrammes (imeteo, ECCC, McGill, Blitzortung) | Images destinées à l'œil humain. Le risque d'orage est déjà couvert par les codes WMO 95/96/99 du dashboard. |
| NAEFS EPSgrams (imeteo) | Images PNG d'un ensemble ; l'Ensemble API d'Open-Meteo donne la même information en données (P3). |

---

## 6. Résumé exécutif

| # | Ajout | Bénéfice principal | Backtestable ? | Effort | Verdict |
|---|---|---|---|---|---|
| P0 | Séparer `MODELES` / `MODELES_VERITE` | Empêche une corruption silencieuse de l'archive | s.o. | ~1 h | **Prérequis** |
| P1 | `gfs_hrrr` (3 km) | Second avis haute résolution sur la décision du jour même | ✓ 3 saisons | faible | **Faire** |
| P2 | `ncep_nbm_conus` | Post-traitement statistique mature (« MOS gratuit ») | ✓ 2 saisons | faible + réflexion sur la corrélation | **Faire, après P1** |
| P3 | Ensembles (ECMWF 51 m.) | P(GO) par jour au lieu d'un taux moyen — répond au cas d'usage n°1 | ✗ (accumuler) | moyen | **Commencer à accumuler** |
| P4 | UKMO 10 km | 5ᵉ centre indépendant | ✗ archive trouée | faible | **Attendre 6-12 mois** |
| P5 | Station au lac (phase 4) + Lac Saint-Pierre | Lève la circularité de la vérité | ✓ | matériel | **La vraie priorité** |
| — | imeteo.ca | — | — | — | **Rien à brancher** |

Une remarque pour finir : P1 à P4 améliorent la mesure d'une erreur définie
par rapport à d'autres modèles. P5 change ce qu'on mesure. Si un seul choix
était possible, ce serait P5.
