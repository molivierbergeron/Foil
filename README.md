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
| 3. Dashboard public (GitHub Pages) | ✅ Livrée — `docs/`, publiée par `pages.yml` |
| 4. Station Ecowitt au lac (`TRUTH_SOURCE="station"`) | ✅ Prête à brancher — `station_ecowitt.py`, procédure dans `MAINTENANCE.md` (il ne manque que les clés API et l'anémomètre) |
| 5. Correction apprise avancée (MOS) | Squelette exécutable (`mos.py`) — dernier essai : pas de gain net, non intégré (voir `reports/mos_baseline.md`) |
| 6. Alertes (`alertes.py`, placeholder) | Non implémentée — consommera `data/forecast.json` ; seuils, horaires et canal (ntfy) à décider ensemble (docstring d'`alertes.py`). |

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
jamais vérifié contre sa propre analyse seule (erreurs corrélées).

**La composition de la vérité est gelée** dans `config.MODELES_VERITE`, une
liste distincte de `config.MODELES` (les membres de prévision). Cette
séparation est structurante : ajouter un modèle de prévision ne doit jamais
déplacer la cible. Sans elle, une simple clé de plus dans `MODELES` changerait
silencieusement la vérité, casserait la comparabilité de l'archive
append-only `data/verification/` et rendrait faux les biais/RMSE publiés sans
qu'aucun test n'échoue.

- Chaque ligne ajoutée à `data/verification/` porte `verite_version` et
  `verite_modeles` (composition réellement utilisée). Les lignes antérieures
  au versionnage n'ont pas ces colonnes — valeur nulle = vérité v1 non
  estampillée.
- Un modèle de vérité manquant fait **échouer** le backtest et le recalibrage
  (`strict=True` : la calibration serait fausse), mais seulement **avertir**
  le job quotidien (`strict=False` : un trou d'archive ponctuel chez un
  fournisseur ne doit pas tuer le job). Dans ce cas la ligne est estampillée
  avec les 5 modèles réellement utilisés, donc reste identifiable.
- Changer `MODELES_VERITE` impose d'incrémenter `config.VERITE_VERSION` et de
  relancer un backtest complet. Deux jeux de poids dont les blocs `verite`
  diffèrent ne sont pas comparables entre eux.

Limite :
c'est une vérité de modèles — elle capture le synoptique, pas l'écart
grille-vs-lac. La phase 4 la remplacera par l'anémomètre au bord du lac
(`TRUTH_SOURCE = "station"`), sans autre changement de code.

Inventaire des stations réelles (~40 km) : une seule station horaire active,
**Lac Saint-Pierre** (701LP0N, 37 km SE, sur l'eau, 1994→aujourd'hui) —
vérité secondaire possible pour le régime synoptique. Détails dans le rapport.

## Vérification croisée — les modèles notés contre un anémomètre réel

`verification_croisee.py` accumule, **en parallèle et sans rien changer au
modèle en service**, des paires « ce que le modèle prévoyait / ce que
l'anémomètre a mesuré » à **Lac Saint-Pierre** (701LP0N, 38 km SE, sur l'eau,
horaire). Les modèles sont interrogés *au point de la station*, donc la
comparaison ne contient aucun écart de localisation.

```bash
python3 verification_croisee.py --rattraper 2024-05-01 2026-08-20  # rétroactif
python3 verification_croisee.py --quotidien                        # appelé par le cron
python3 verification_croisee.py --rapport                          # reports/verification_croisee.md
```

**Pourquoi.** La vérité du pipeline principal est la médiane hour-0 des
modèles eux-mêmes : elle note chaque modèle contre la moyenne de ses
semblables. Mesuré sur trois saisons (2024–2026, **171 701 paires**,
heures navigables), l'écart est net — à 24 h :

| Modèle | RMSE vs **mesure réelle** | Rang | RMSE vs consensus | Rang |
|---|---:|---:|---:|---:|
| GFS | 4,08 | 1 | 1,59 | 5 |
| HRDPS | 4,13 | 2 | 2,10 | 6 |
| GEM régional | 4,44 | 3 | 1,46 | 3 |
| GEM global | 4,76 | 4 | 1,49 | 4 |
| ICON | 4,95 | 5 | 1,17 | 1 |
| ECMWF | 5,17 | 6 | 1,43 | 2 |

Le classement est presque inversé et l'erreur réelle est 3 à 4 fois plus
grande. Corollaire mesuré : à 24 h, l'écart entre le meilleur et le pire
modèle vaut 1,09 nds alors que le débiaisage n'en gagne que 0,18 — **choisir
et pondérer les modèles pèse plusieurs fois plus que corriger leurs biais.**
Le tableau complet, par échéance, est régénéré dans
`reports/verification_croisee.md`.

**Trois usages.** Un classement des modèles indépendant des modèles ; la
détection de dérive d'un fournisseur (`reports/derive.md` ne peut pas la
voir, son étalon bouge avec les modèles) ; et une base comparable le jour où
l'anémomètre du lac existera.

**Ce que cette piste ne fait pas.** Elle n'écrit ni dans
`data/poids_modeles.json`, ni dans `data/verification/`, ne touche ni à
`verite.py` ni au recalibrage, et ne produit aucun verdict. L'étanchéité est
vérifiée par un test qui inspecte le code exécutable (docstrings exclues).

**La limite, dite franchement.** Lac Saint-Pierre n'est pas le Lac
Maskinongé : plan d'eau bien plus ouvert, vent médian de jour 9,2 nds contre
~5 au spot, et les six modèles y sous-estiment tous de 1 à 3 nds. **Ce biais
est celui du site, pas celui du lac, et ne se transplante pas.** Ce qui se
transporte raisonnablement, c'est le classement et la corrélation. Deux
réserves de plus : l'observation ECCC est un relevé horaire et non une
moyenne horaire comme les modèles (ça gonfle l'erreur de tout le monde sans
changer l'ordre), et elle est arrondie au km/h.

## Mettre un modèle à l'essai sans rien écraser

Le registre distingue deux rôles. **L'actif** calcule les verdicts du
dashboard. **Le candidat** est archivé et publié à côté, visible dans la vue
d'essai, et ne touche à aucun verdict tant qu'un `--activer` explicite ne le
promeut pas.

```bash
python3 candidat.py                        # construit et publie un candidat
python3 versions.py --activer v3-…         # le promeut (l'ancien reste archivé)
python3 versions.py --activer v2-…         # et se restaure de la même façon
```

`candidat.py` fabrique une variante qui ne change **qu'une chose** : les
poids, recalculés ∝ 1/RMSE² sur les RMSE mesurés contre l'anémomètre de Lac
Saint-Pierre. Les biais restent ceux du modèle actif — ceux du site de mesure
ne se transplantent pas (voir la section précédente). Chaque poids remplacé
porte son `rmse_reel_nds` et son `n_reel` : un poids venu d'ailleurs doit
pouvoir se justifier.

Sur 3 saisons, ça déplace nettement les poids à 24 h — HRDPS 8 % → 20 %,
GFS 15 % → 21 %, ICON 27 % → 14 %. **Mais sur la prévision, l'effet est
minuscule** : mesuré sur 60 heures réelles, l'écart entre les deux modèles
est de **0,15 nds en moyenne, 0,50 nds au pire**. C'est écrit sur la page
plutôt que caché : la repondération déplace des décimales, et si elle vaut
mieux, ça se verra sur des semaines de statistiques, pas sur une sortie.

### Les trois pages

| Page | Ce qu'elle montre |
|---|---|
| `index.html` | Le produit : verdicts GO/NO, calculés par l'**actif** seulement |
| `essai.html` | Le vent prévu par l'actif et le candidat, heure par heure, avec l'écart |
| `comparaison.html` | Ce que vaut chaque modèle face à un anémomètre, et l'historique des versions |

## Versionnage des modèles — historique, retour arrière, comparaison

Un « modèle », ici, c'est un **jeu de poids complet** : c'est lui qui
transforme six prévisions brutes en un verdict. Il est donc archivé,
restaurable et comparable.

```
data/modeles/registre.json          index + version active + journal des bascules
data/modeles/<version>/poids.json   le jeu de poids figé (contenu calibré nu)
data/poids_modeles.json             copie de travail = version active
docs/poids_modeles.json             copie lue par le dashboard
```

Les deux copies en service portent en plus un champ `version_modele` (affiché
en pied de dashboard) ; l'archive ne l'a pas, pour que son empreinte ne
dépende pas de son propre identifiant.

```bash
python3 versions.py --lister                       # historique + version active
python3 versions.py --comparer v2-… v3-…           # laquelle prévoit le mieux ?
python3 versions.py --activer v2-… --raison "…"    # retour arrière
```

- **Création automatique** : chaque backtest complet (`origine: backtest`) et
  chaque recalibrage hebdomadaire *appliqué* (`origine: recalibrage`) crée une
  version. Un recalibrage qui aboutit aux mêmes chiffres n'en crée pas
  (empreinte identique) — pas d'empilement de doublons.
- **Amorçage** : un dépôt sans registre importe `data/poids_modeles.json`
  comme `v1` (`origine: import-initial`), en déduisant sa borne de calibration
  de `periode_backtest`.
- **Retour arrière** : `--activer` réinstalle les deux copies et journalise la
  bascule avec sa raison. Rien n'est jamais supprimé ni réécrit — l'historique
  des activations reste lisible (« on est revenus à v2 le 20 août parce
  que… »). Il faut committer après.

### « Est-ce que le modèle d'aujourd'hui est meilleur qu'avant ? »

`--comparer A B` répond avec deux métriques, sur la même fenêtre :

| Métrique | Ce qu'elle dit |
|---|---|
| **RMSE de l'ensemble corrigé-pondéré**, par horizon | l'erreur typique en nœuds |
| **Taux de GO confirmé** + IC 95 % de Wilson, par horizon | ce que voit l'utilisateur : la part des GO annoncés qui se réalisent |

Les deux peuvent diverger — un RMSE qui s'améliore de 0,05 nds peut ne changer
aucun verdict GO/NO. C'est pour ça que les deux sont affichées.

**Le choix de la fenêtre est le point délicat, et il est automatique.** Chaque
version mémorise `donnees_jusqu_au`, le dernier jour ayant servi à la
calibrer. La comparaison démarre après la **plus tardive** des deux bornes :
sinon la version la plus récemment calibrée serait jugée sur ses propres
données d'entraînement et gagnerait d'office. `--jours N` et `--depuis DATE`
forcent une autre fenêtre, mais la sortie affiche alors explicitement que le
résultat **n'est pas** hors échantillon. Si la fenêtre est vide, l'outil le
dit au lieu d'inventer un verdict : il faut laisser passer des jours avant de
pouvoir départager deux versions.

Exemple de sortie réelle :

```
A = v1-2026-07-15
B = v2-2026-06-20
Fenêtre : 2026-07-12 → 2026-08-06 (8940 lignes, hors échantillon pour les deux versions)

horizon     RMSE A    RMSE B     écart           GO conf. A         GO conf. B
24h          1.066     1.067    +0.000   92% [67%-99%] n=13  92% [67%-99%] n=13
48h          1.238     1.237    -0.001   92% [65%-99%] n=12  92% [65%-99%] n=12
96h          1.777     1.779    +0.002   92% [67%-99%] n=13  92% [67%-99%] n=13

Match nul (écart moyen +0.001 nds, sous le bruit).
```

Le verdict reste prudent par construction : sous 200 lignes il refuse de
conclure, et sous 0,05 nds d'écart moyen il annonce un match nul plutôt qu'un
gagnant — à ce spot, l'écart entre modèles est de l'ordre de 3 nds, un
centième de nœud n'est pas un progrès.

## Format de `data/poids_modeles.json` (schéma v2)

Consommable en JavaScript par le dashboard (phase 3) :

```jsonc
{
  "schema_version": 2,                  // v2 : ajout du bloc "verite"
  "genere_le": "2026-07-15",
  "version_modele": "v3-2026-08-17",    // copies en service seulement, pas l'archive
  "truth_source": "median_hour0",
  "verite": {                           // contre quoi ces chiffres ont été mesurés
    "version": "median_hour0/v1",
    "modeles": ["gem_global", "gem_regional", "…"]
  },
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

## Phase 3 — le dashboard public

`docs/` est un site statique autonome (HTML/CSS/JS sans dépendance, chemins
relatifs) publié par GitHub Pages (`pages.yml`) — copiable tel quel par FTP
ailleurs plus tard. **Architecture de fraîcheur** : la page récupère les
prévisions brutes en direct chez Open-Meteo (CORS, sans clé) à chaque
ouverture, puis leur applique en JavaScript les corrections de
`docs/poids_modeles.json` (copie tenue à jour par le recalibrage
hebdomadaire). Les données affichées sont donc toujours au dernier run de
modèle, même si les crons ont du retard — le cron ne sert jamais à
l'affichage.

Détails d'implémentation :
- Les seuils du sport (bande 7–16, marginale, blocs, ratio rafaleux) sont lus
  dans la section `sport` de `poids_modeles.json` — jamais codés en dur en JS.
- La logique de fenêtres JS est testée contre les mêmes cas que la version
  Python : `node tests/test_dashboard.js`.
- Chaque verdict GO affiche sa cote mesurée (fourchette IC 95 % du backtest,
  par horizon). Aucun drapeau « découplage » tant que la phase 1 n'a pas
  trouvé de signature validée (voir rapport).
- Mention « modèles divisés » quand l'écart entre modèles dépasse 5 nds ;
  badge « rafaleux » si la majorité des heures en bande de la fenêtre dépasse
  le ratio 1,6.
- Mobile-first (iPhone Safari/Chrome), clair/sombre automatique, lecture
  seule, aucune authentification, aucune donnée personnelle.
- **Auto-rafraîchissement** : la page recharge les prévisions chaque heure
  entre 7 h et 17 h (heure de Montréal) tant qu'elle est ouverte, et dès
  qu'on revient sur l'onglet si les données ont plus de 30 min. Le graphique
  48 h grise les heures passées et marque « maintenant ».
- **Aujourd'hui / demain en heure par heure** : bande de cellules 8 h–20 h
  (aujourd'hui à partir de l'heure courante) avec vent, rafales et icône
  météo ; vert = bande de foil, ⚡ = risque d'orage (codes WMO 95/96/99).
- **Météo discrète** sous chaque verdict : icône, cumul de pluie du jour,
  drapeau orage bien visible (sécurité sur l'eau).
- **Indice de régularité des puffs** : facteur de rafales médian
  (rafales/vent) des heures en bande — < 1,35 « vent régulier »,
  1,35–1,6 « puffs modérés », > 1,6 « puffy ».

## Maintenance et suite

Tout ce qu'il faut pour opérer, diagnostiquer et continuer le projet sans
assistance est dans **`MAINTENANCE.md`** : quoi surveiller, comment brancher
la station (phase 4), relancer l'essai MOS (phase 5), activer les alertes
(phase 6), ou déménager le dashboard par FTP. Un workflow `tests.yml`
exécute les 4 suites de tests à chaque modification de code.

Le dashboard s'installe sur l'écran d'accueil iPhone (Partager → « Sur
l'écran d'accueil ») : icône et plein écran fournis par
`docs/manifest.webmanifest`.

## Attribution

Données météo : [Open-Meteo.com](https://open-meteo.com) (CC BY 4.0).
Inventaire de stations : Environnement et Changement climatique Canada
(api.weather.gc.ca).
