# HRRR (NOAA, 3 km) — mesuré, pas supposé

**Réponse courte : non.** Ajouté comme septième membre, HRRR ne fait pas
gagner 1 nd. Il ne fait rien gagner du tout : sur 2026 jamais vu, l'erreur
de l'ensemble passe de **3,779 nds à 3,793 nds** — une dégradation de
**0,014 nd**, statistiquement indiscernable de zéro et à trois ordres de
grandeur sous le seuil qui changerait une décision.

Le candidat à sept membres est quand même archivé et publié
(`v4-2026-08-28`, rôle **candidat**), parce que le protocole du projet est
d'archiver ce qu'on a essayé. Il n'est pas promu, et il ne devrait pas
l'être sur ces chiffres.

## Le protocole

Ce qui est jugé, c'est l'ensemble corrigé-pondéré que le système rend
réellement : chaque modèle débiaisé, puis moyenne pondérée ∝ 1/RMSE².

| | |
|---|---|
| Étalon | anémomètre de Lac Saint-Pierre (701LP0N), mesure horaire réelle |
| Entraînement (biais + poids) | saisons **2024 et 2025** — 4 399 heures, 368 jours |
| Test | saison **2026**, jamais vue à la calibration — 1 249 heures, 105 jours |
| Heures | navigables seulement (8 h–20 h locales) |
| Échéance | 24 h — la seule que HRRR archive (portée 48 h) |
| Appariement | heures où les **sept** modèles sont présents, pour que le 6 et le 7 membres soient jugés sur exactement les mêmes heures |
| Incertitude | bootstrap apparié **par jour** (4 000 tirages) — deux heures du même jour ne sont pas indépendantes |

## Le résultat

| Ensemble | RMSE 2026 (hors échantillon) |
|---|---:|
| Six membres (référence) | **3,779 nds** |
| Sept membres (+ HRRR) | **3,793 nds** |
| Écart | **+0,014 nd — HRRR dégrade** |

Bootstrap apparié par jour, sur le gain (six − sept) :

| | |
|---|---:|
| Gain médian | −0,015 nd |
| IC 95 % | **[−0,052 ; +0,023] nd** |
| P(gain > 0) | 0,23 |
| **P(gain > 1 nd)** | **0,000** |

L'intervalle contient zéro : on ne peut même pas affirmer que HRRR nuit. Ce
qu'on peut affirmer, et c'est ce qui compte, c'est que **tout l'intervalle
tient dans ±0,06 nd**. Le gain d'un nœud n'est pas « non prouvé faute de
données » : il est exclu par les données.

### Variantes, pour vérifier que le verdict ne tient pas à un réglage

| Variante | RMSE 2026 |
|---|---:|
| Six membres, poids ∝ 1/RMSE² | 3,779 |
| Sept membres, poids ∝ 1/RMSE² | 3,793 |
| Six membres, poids égaux | 3,815 |
| Sept membres, poids égaux | 3,830 |
| HRRR **à la place** de HRDPS | 3,884 |
| HRRR **seul**, débiaisé | 4,566 |

Le verdict tient dans les quatre configurations. Remplacer HRDPS par HRRR —
troquer une maille fine canadienne contre une maille fine américaine — est
la pire des options testées parmi les ensembles.

## Pourquoi ça ne marche pas — la vraie raison

L'hypothèse de départ était solide : maille 3 km contre 13-25 km, centre
indépendant (NOAA), donc des erreurs différentes de celles des globaux. Un
membre médiocre mais **décorrélé** améliore un ensemble ; c'est tout
l'intérêt d'ajouter un ingrédient.

Mesuré, HRRR n'est pas décorrélé. Corrélation de son erreur avec celle des
autres, sur 2026 :

| Avec l'erreur de | r |
|---|---:|
| ICON | 0,820 |
| ECMWF | 0,804 |
| GEM global | 0,773 |
| GEM régional | 0,744 |
| GFS | 0,716 |
| HRDPS | 0,643 |
| **l'ensemble des six** | **0,833** |

Quand l'ensemble se trompe, HRRR se trompe avec lui, dans le même sens, à
83 %. Il n'apporte pas une information neuve : il apporte une septième
copie de la même information, avec plus de bruit (c'est le membre le moins
corrélé à la mesure : r = 0,67 contre 0,72 pour GFS).

Ce n'est pas si surprenant après coup. À 24 h d'échéance, ce qui fait
l'erreur n'est pas la finesse de la grille, c'est le placement du système
synoptique — et HRRR est initialisé et forcé aux frontières par GFS. Sa
maille de 3 km lui donne un meilleur relief, pas de meilleures conditions
initiales.

### Le corollaire embêtant

L'analyse qui a motivé cette tâche disait : repondérer six modèles déplace
la prévision de 0,31 nd médian, trop peu pour changer une décision ; il faut
changer les ingrédients. Changer l'ingrédient déplace la prévision de
**0,20 nd médian** (moyenne 0,26 ; p95 0,70 ; plus de 1 nd sur **1,0 %** des
heures). C'est **moins** que la repondération.

Le raisonnement « une moyenne pondérée est prisonnière de ses ingrédients »
était juste. Ce qui était faux, c'est de croire que HRRR était un
ingrédient neuf. Un septième membre qui se trompe en même temps que les six
autres est, du point de vue de la moyenne, le même ingrédient.

## Rang de HRRR parmi les sept

Contre la mesure réelle, à 24 h, heures navigables, trois saisons
(11 571 paires nouvellement archivées) :

| Rang | Modèle | Biais (nds) | RMSE (nds) | Corrélation |
|---:|---|---:|---:|---:|
| 1 | GFS | −1,42 | 4,08 | 0,72 |
| 2 | HRDPS | −1,48 | 4,13 | 0,73 |
| 3 | GEM régional | −2,48 | 4,43 | 0,75 |
| 4 | **HRRR** | **−2,15** | **4,62** | **0,67** |
| 5 | GEM global | −2,79 | 4,75 | 0,72 |
| 6 | ICON | −2,97 | 4,95 | 0,71 |
| 7 | ECMWF | −3,30 | 5,17 | 0,71 |

HRRR est 4e sur 7 : honorable, jamais décisif. Son biais est meilleur que
celui de quatre modèles, mais le biais se corrige ; c'est la corrélation qui
ne se corrige pas, et là il est dernier.

## Ce que HRRR ne peut pas faire, de toute façon

Sa portée est de 48 h : il n'archive que `previous_day1`. Il ne touche donc
**jamais** à la décision de planification (« ça vaut-tu la peine de monter
au chalet cette fin de semaine ? », J-4 à J-2) — celle où la fiabilité est
la plus basse et où un gain aurait le plus de valeur. Il ne peut agir que
sur la veille et le jour même, là où le système est déjà le plus juste.

## Comparaison de versions (`versions.py --comparer`)

```
A = v2-2026-08-24  (actif, six membres)
B = v4-2026-08-28  (candidat, sept membres)
Fenêtre : 2026-08-21 → 2026-08-24 (1020 lignes, hors échantillon pour les deux)

horizon     RMSE A    RMSE B     écart
24h          0.534     0.531    -0.003
48h          0.731     0.729    -0.002
96h          1.131     1.107    -0.024

Match nul (écart moyen -0.010 nds, sous le bruit).
```

À lire avec prudence, et surtout **pas** comme une confirmation : la fenêtre
ne fait que quatre jours (le candidat est calibré jusqu'au 2026-07-12,
l'actif jusqu'au 2026-08-21), et l'étalon y est le consensus des modèles,
pas une mesure. Les écarts à 48 h et 96 h ne veulent rien dire du tout —
HRRR ne vote à aucune de ces deux échéances, les deux versions y sont
identiques à l'arrondi des poids près. Le chiffre qui décide est celui
d'en haut : 3,779 contre 3,793, contre un anémomètre.

## Recommandation

**Ne pas promouvoir.** Garder `v2-2026-08-24` actif.

HRRR reste téléchargé, archivé et affiché : il est dans `config.MODELES`,
le job quotidien l'accumule dans `data/verification/` et
`data/verification_croisee/`, et la page de comparaison le note comme les
six autres. Le coût est d'un appel d'API par jour, et le bénéfice est réel
même à zéro gain de prévision : un septième point de vue indépendant rend la
détection de dérive d'un fournisseur plus robuste.

Ce qui est clos, c'est l'idée qu'un membre de plus déplace la prévision. Il
faudrait, pour ça, une source dont les erreurs ne soient pas celles des
modèles — c'est-à-dire une **mesure**. L'anémomètre au lac (phase 4) reste
le seul levier qui n'a pas encore été essayé, et c'est maintenant le seul
qui reste.

---

Reproduire : `python3 candidat_hrrr.py` construit le candidat ;
`python3 verification_croisee.py --rapport` régénère le classement des sept
modèles contre la mesure.
