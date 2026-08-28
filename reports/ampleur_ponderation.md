# Repondérer les modèles : ampleur et utilité réelles

Généré le 2026-08-28 par `ampleur_poids.py`. Étalon : anémomètre de Lac Saint-Pierre (701LP0N), à 38 km du spot.

## La question

> « Un écart sous 1 nd ne change aucune décision de sortir le bateau. Est-ce qu'entre les jeux de poids on peut trouver 1, 2, 3 nds ? »

**Réponse courte : non.** Repondérer six modèles ne peut pas produire un écart de cette taille, et ce n'est pas une limite de réglage mais une limite arithmétique. Les leviers de 1-3 nds sont ailleurs — voir la conclusion.

## Méthode

Entraînement sur les saisons < 2026, jugement sur 2026 — **jamais vu**. C'est essentiel : les poids du candidat sont dérivés des données de cette station, les juger dessus les ferait gagner par construction.

Les biais (moyenne d'erreur par modèle, apprise sur le train) sont **communs aux trois jeux**, ce qui isole la seule chose qui les distingue : la pondération. Trois jeux comparés :

| Jeu | Origine des poids |
|---|---|
| **en service** | calibrés contre le consensus des modèles (production) |
| **candidat** | ∝ 1/RMSE² mesuré contre l'anémomètre, refait sur le train seul |
| **poids égaux** | témoin : ne rien faire d'intelligent |

## 1. Précision hors échantillon

RMSE sur 2026, en nœuds (plus bas = mieux).

| Horizon | en service | candidat | poids égaux | heures | jours |
|---|---:|---:|---:|---:|---:|
| 24h | 3.869 | 3.779 | 3.815 | 1249 | 105 |
| 48h | 4.220 | 4.194 | 4.207 | 1255 | 105 |
| 96h | 4.969 | 4.961 | 4.963 | 1332 | 111 |

**Le témoin bat déjà la production.** Les poids égaux — c'est-à-dire aucune pondération — font mieux que le calibrage en service. L'essentiel du gain du candidat n'est donc pas un mérite : c'est l'abandon d'une pondération qui nuisait.

## 2. Est-ce significatif ?

Bootstrap apparié **par jour**, non par heure : deux heures du même jour partagent le même système météo et les mêmes erreurs, les traiter comme indépendantes gonflerait la significativité.

| Horizon | Comparaison | Gain (nds) | IC 95 % | Verdict |
|---|---|---:|---|---|
| 24h | en service → candidat | +0.091 | [+0.049, +0.132] | significatif |
| 24h | en service → poids égaux | +0.054 | [+0.029, +0.080] | significatif |
| 24h | poids égaux → candidat | +0.037 | [+0.018, +0.054] | significatif |
| 48h | en service → candidat | +0.026 | [-0.000, +0.052] | **non significatif** |
| 48h | en service → poids égaux | +0.013 | [+0.002, +0.025] | significatif |
| 48h | poids égaux → candidat | +0.013 | [-0.004, +0.028] | **non significatif** |
| 96h | en service → candidat | +0.009 | [-0.021, +0.039] | **non significatif** |
| 96h | en service → poids égaux | +0.006 | [-0.013, +0.025] | **non significatif** |
| 96h | poids égaux → candidat | +0.002 | [-0.012, +0.018] | **non significatif** |

Significatif ne veut pas dire utile : un gain de 0,09 nd sur une erreur de 3,8 nds est réel et sans conséquence pratique.

## 3. Ampleur : la distribution, pas la moyenne

Écart absolu entre les prévisions de deux jeux de poids, heure par heure. C'est la mesure qui répond vraiment à la question posée.

| Horizon | Paire | médian | p90 | p99 | max | **> 1 nd** | > 2 nds |
|---|---|---:|---:|---:|---:|---:|---:|
| 24h | en service ↔ candidat | 0.31 | 0.76 | 1.29 | 2.29 | 4.6% | 0.1% |
| 24h | en service ↔ poids égaux | 0.19 | 0.48 | 0.85 | 1.46 | 0.4% | 0.0% |
| 24h | poids égaux ↔ candidat | 0.12 | 0.31 | 0.54 | 0.84 | 0.0% | 0.0% |
| 48h | en service ↔ candidat | 0.17 | 0.43 | 0.73 | 1.05 | 0.2% | 0.0% |
| 48h | en service ↔ poids égaux | 0.07 | 0.20 | 0.34 | 0.48 | 0.0% | 0.0% |
| 48h | poids égaux ↔ candidat | 0.10 | 0.25 | 0.45 | 0.59 | 0.0% | 0.0% |
| 96h | en service ↔ candidat | 0.16 | 0.39 | 0.61 | 0.89 | 0.0% | 0.0% |
| 96h | en service ↔ poids égaux | 0.09 | 0.23 | 0.41 | 0.55 | 0.0% | 0.0% |
| 96h | poids égaux ↔ candidat | 0.09 | 0.21 | 0.32 | 0.41 | 0.0% | 0.0% |

## 4. Pour comparaison : des leviers d'une autre nature

| Horizon | Levier | médian | p90 | max | > 1 nd |
|---|---|---:|---:|---:|---:|
| 24h | étendue entre les modèles bruts | 4.43 | 8.03 | 21.62 | 100% |
| 24h | un seul modèle (GFS (États-Unis)) au lieu de l'ensemble | 1.27 | 3.46 | 9.12 | 60% |
| 48h | étendue entre les modèles bruts | 4.24 | 7.63 | 16.71 | 99% |
| 48h | un seul modèle (GFS (États-Unis)) au lieu de l'ensemble | 1.41 | 4.01 | 10.25 | 62% |
| 96h | étendue entre les modèles bruts | 4.93 | 8.80 | 17.03 | 99% |
| 96h | un seul modèle (GFS (États-Unis)) au lieu de l'ensemble | 1.84 | 4.45 | 10.41 | 70% |

À 24 h, le meilleur modèle SEUL fait 4.011 nds (GEM régional (Canada)), contre 3.779 pour le meilleur ensemble. Choisir un seul modèle déplacerait bien la prévision de 1-3 nds — dans le mauvais sens. **Aucun modèle isolé ne bat la moyenne.**

## Conclusion

Les trois jeux sont des **moyennes pondérées des mêmes six nombres**. Une moyenne est bornée par ses ingrédients : redistribuer les poids ne peut pas sortir du nuage que forment les six modèles une fois débiaisés. L'écart plafonne, quelle que soit l'ingéniosité du calcul.

Il y a aussi une raison théorique à ce que les poids égaux tiennent si bien : la pondération ∝ 1/RMSE² n'est optimale que si les erreurs des modèles sont **indépendantes**. Elles ne le sont pas — les modèles digèrent les mêmes observations et partagent des paramétrisations. Sous erreurs corrélées, la pondération inverse-variance perd son fondement et l'équipondération devient quasi optimale, tout en étant bien plus robuste au surapprentissage.

**Deux leviers peuvent produire 1-3 nds, et aucun n'est une pondération :**

1. **Ajouter un modèle vraiment différent** — HRRR (3 km, NOAA) est backtestable sur trois saisons et couvre le lac. Une septième voix indépendante change le nuage ; redistribuer six voix, non.
2. **L'anémomètre au lac.** À la station de mesure, les six modèles sous-estiment tous de 1 à 3 nds : c'est l'erreur de SITE, pile dans la fourchette qui compte. Aucune pondération ne peut la toucher, parce qu'elle ne vient pas du choix des modèles mais de ce que la grille ignore du plan d'eau. Le Lac Maskinongé a la sienne, et personne ne la connaît.

**Recommandation : arrêter de régler les poids.** Le candidat actuel (v4-2026-08-28) reste archivé et hors service ; il sera rejugé quand la vérité sera meilleure.

## Limite de cette analyse

Tout est mesuré à Lac Saint-Pierre, à 38 km, sur un plan d'eau bien plus ouvert que le Maskinongé. Le classement des modèles s'y transporte raisonnablement ; les biais absolus, non. Ces conclusions portent sur la MÉCANIQUE de la pondération, qui est la même partout — pas sur les valeurs numériques au spot.
