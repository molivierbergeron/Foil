# VISION — Foil (prévisions de vent calibrées, Lac Maskinongé)

Audit du 2026-08-02, sur le commit `4b172d2` (état distant synchronisé).
Ce fichier est un instantané horodaté : il n'est jamais mis à jour après coup.

---

## 1. Vision produit

**Ce que ça fait.** Répondre à deux questions et une seule : « ça vaut-tu la
peine de monter au chalet cette fin de semaine ? » (verdict par jour, jusqu'à
4 jours d'avance) et « je sors ce matin ou cet après-midi ? » (heure par
heure, aujourd'hui et demain). Chaque GO est accompagné de sa fiabilité
réellement mesurée — « GO · 76 % » signifie que 76 % des GO annoncés à cette
échéance se sont historiquement confirmés à ce spot (`data/poids_modeles.json:686-704`).

**Ce que ça remplace.** Consulter trois apps météo qui se contredisent et se
faire avoir. Le backtest l'a mesuré : à 24 h d'échéance, au moins un des six
modèles annonce une journée GO 318 fois, mais les six ne s'entendent que 70
fois, avec un écart typique de 3 nds entre le plus optimiste et le plus
pessimiste (`reports/rapport_backtest.md`, section « L'essentiel en langage
clair »). Le produit remplace ce bruit par un consensus corrigé de l'erreur
historique de chaque modèle à ce lac précis — et remplace surtout les allers
au chalet pour rien : un GO à 4 jours ne tient que ~76 % du temps, et le
produit le dit au lieu de le cacher.

**Où ça s'arrête.** Ce n'est pas un site météo généraliste : une seule
question (GO/NO foil), un seul spot, 7 jours d'horizon maximum — c'est ce qui
permet la calibration fine. Il n'affiche jamais de certitude : toujours une
cote, par choix fondateur (« jamais un GO sec », `README.md:8-14`). Et il ne
demande rien à ses visiteurs : site statique public, aucune écriture
utilisateur, aucun compte, aucune donnée personnelle — c'est ce qui le rend
partageable au cousin par une simple URL et copiable par FTP n'importe où
(`README.md`, section Phase 3). (Un comptage de visites anonyme ne
franchirait pas cette frontière — c'est l'objet de la question 5.)

**État**
- **Statut : vivant** — le job quotidien a commité chaque jour sans
  interruption du 2026-07-17 au 2026-08-02 (`git log --oneline`, commits
  « Vérification quotidienne »), deux recalibrages hebdomadaires exécutés
  (2026-07-20, 2026-07-27, `reports/derive.md`).
- **Dernière modification** : code humain/assisté 2026-07-19 (`a1069f4`) ;
  dernier commit automatique 2026-08-02 10:59 UTC (`4b172d2`).
- **Stack réelle** : Python 3.11 (requests, pandas, pyarrow, matplotlib,
  tabulate — `requirements.txt`), JavaScript vanilla sans dépendance
  (`docs/app.js`, 660 lignes), 4 workflows GitHub Actions, GitHub Pages,
  stockage Parquet/JSON dans le repo (pas de base de données).
- **Dépendances externes et points de rupture** : Open-Meteo (3 endpoints
  sans clé, `config.py:36-38` + appels client `docs/app.js:522-530`) — un
  changement d'API casse l'affichage ET les crons ; GitHub Actions/Pages —
  les crons planifiés se désactivent après ~60 jours sans activité du repo
  (documenté `README.md:150-154`) ; Ecowitt préparé mais non branché
  (3 secrets attendus, `station_ecowitt.py:49-51`) ; ntfy prévu, non branché
  (`alertes.py`).
- **Coût récurrent : 0 $** — repo public (Actions et Pages gratuits pour les
  repos publics ; confiance ~95 %, politique GitHub non vérifiable depuis le
  repo), Open-Meteo gratuit non commercial.

---

## 2. Epics

### Epics socle

**S1 — Fiabilité.** Le cœur tient : 17 jours de crons sans trou (git log),
garde-fou de recalibrage exercé deux fois avec rejet des candidats plus
faibles (`reports/derive.md`), retry réseau ajouté après le seul crash
observé (`openmeteo_client.py:41-53`, commit `593e8c8`), et le dashboard
échoue bruyamment (message d'erreur explicite, `docs/app.js`, bloc catch de
`demarrer`). **Deux trous réels** : (a) `recalibrage.py:133-135` écrit
`docs/poids_modeles.json` mais `recalibrage.yml:32` ne stage que
`data/poids_modeles.json reports/derive.md` — le jour où un recalibrage sera
appliqué, le dashboard public gardera les anciens poids pour toujours
(invisible aujourd'hui : les deux fichiers sont identiques parce que tous les
candidats ont été rejetés) ; (b) un cron qui meurt ne se signale que dans
l'onglet Actions — la notification courriel par défaut de GitHub est non
vérifiable ici parce que c'est un réglage du compte du CPO, pas du repo.

**S2 — Coût.** 0 $ récurrent. Seul dérapage possible : le quota Open-Meteo
non commercial (~10 000 appels/jour affiché par le fournisseur ; confiance
~90 %) si l'URL circulait largement — chaque ouverture = 2 appels
(`docs/app.js:522-530`), les crons en font ~40/jour. À l'échelle
famille+cousin : marge de plusieurs ordres de grandeur. Rien à faire.

**S3 — Vitesse et friction.** Zéro geste entre l'intention et la réponse :
app installée sur l'écran d'accueil (`docs/index.html:9-11`), verdict visible
dès le chargement (2 fetchs parallèles), auto-rafraîchissement horaire 6 h–22 h
et re-rendu au retour d'onglet, y compris après restauration Safari
(`docs/app.js:27` et bloc `pageshow`). Rien à signaler.

**S4 — Analytics et observabilité.** Le point faible du produit. Personne ne
sait si le dashboard est consulté (aucun compteur, aucun log côté client), et
la précision réelle du système — pourtant recalculée chaque semaine — n'est
visible que dans `reports/derive.md`, pas sur la page que le CPO regarde. Le
diagnostic sans lire le code existe (`MAINTENANCE.md`, tableau de
surveillance), mais il faut aller le chercher.

**S5 — Dette technique.** 2 732 lignes au total (`wc -l`), zéro TODO/FIXME
(grep sur tout le repo), 5 suites de tests branchées en CI
(`.github/workflows/tests.yml`). Deux dettes réelles : la logique de
fenêtres foilables existe en double — Python (`fenetre.py:31-56`) et
JavaScript (`docs/app.js:31-56`) — tenue cohérente par des tests miroir
(`tests/test_dashboard.js`), mais une modification unilatérale ferait
diverger le verdict du backtest et celui de l'écran ; et
`station_ecowitt._normaliser` suit la doc Ecowitt sans avoir jamais vu une
vraie réponse (avertissement explicite `station_ecowitt.py:18-25`) — le mode
autotest existe pour ça.

### Epics produit

**P1 — La vérité vient du lac, pas de la grille**
- Objectif : calibrer les corrections sur du vent mesuré au bord du lac
  (anémomètre Ecowitt) au lieu du consensus des modèles entre eux — le seul
  moyen de voir les vrais busts « la grille dit du vent, le lac n'en reçoit
  pas », invisibles par construction aujourd'hui (`verite.py`, docstring).
- On saura que c'est atteint quand : `poids_modeles.json` affiche
  `"truth_source": "station"` et qu'un recalibrage hebdomadaire a tourné
  dessus sans intervention.

**P2 — Une cote qu'on peut prendre au mot**
- Objectif : que le « GO · 76 % » soit vérifiable en continu et conditionné
  au régime (secteur, saison, divergence des modèles) au lieu d'être une
  moyenne globale figée au backtest (`docs/app.js:264-268`).
- On saura que c'est atteint quand : le pied de page affiche la précision des
  30 derniers jours calculée par le pipeline (« ce mois-ci : 9 GO sur 11
  confirmés »), et que ce chiffre reste proche de la cote annoncée.

**P3 — Le verdict te trouve**
- Objectif : ne plus avoir à ouvrir la page — le téléphone vibre la veille
  d'une fenêtre foilable, et re-vibre si un GO annoncé tombe
  (`alertes.py`, placeholder assumé).
- On saura que c'est atteint quand : une session réussie aura commencé par
  une notification reçue, pas par une consultation.

---

## 3. Séquence par thème

**Maintenant.** À la fin de cette vague, le produit ne peut plus se tromper
en silence : un recalibrage appliqué atteint réellement le téléphone du CPO
(poids `docs/` commités), une panne de cron ouvre une issue au lieu d'être
découverte des semaines plus tard avec un trou dans l'historique, et on sait
enfin si la mention « modèles divisés » est un vrai signal ou du bruit à
retirer.

**Ensuite.** À la fin de cette vague, le produit rend des comptes et se
déplace vers l'utilisateur : la page affiche sa propre précision récente, la
cote s'ajuste au régime de vent, les alertes ntfy livrent le verdict la
veille, et — si l'anémomètre est acheté — la vérité de calibration devient le
lac lui-même, ce qui requalifie tout le reste.

**Un jour.** À la fin de cette vague, le produit est un instrument complet :
la correction apprise (MOS) re-testée contre le vent réel du lac là où elle a
une vraie chance, un bilan de saison auto-généré chaque novembre, la page
utilisable hors réseau au chalet, et une mesure d'usage qui dit si le cousin
s'en sert vraiment.

---

## 4. Items

| # | Item | Epic | Bénéfice concret | Effort | Sessions |
|---|------|------|------------------|--------|----------|
| 1 | Committer `docs/poids_modeles.json` au recalibrage | S1 | Le premier recalibrage appliqué corrige vraiment le dashboard au lieu d'y laisser de vieux biais pour toujours | XS | 0,25 |
| 2 | Rendre les échecs de crons bruyants | S1 | Une panne devient une issue GitHub le jour même, pas un trou d'historique découvert au mois d'après | M | 2 |
| 3 | Mesurer si « modèles divisés » prédit les busts | P2 | Soit une cote auto-ajustée les jours douteux, soit une mention retirée qui criait au loup | S | 1 |
| 4 | Afficher la précision glissante 30 jours sur la page | P2 | Décider de monter au chalet en voyant « 9 GO sur 11 confirmés ce mois-ci » au lieu d'un % figé de juillet | M | 2 |
| 5 | Basculer la vérité sur la station Ecowitt | P1 | Les busts réels deviennent observables ; les biais absolus cessent d'être flattés par une vérité corrélée | L | 4 |
| 6 | Conditionner la cote au secteur de vent | P2 | Un GO de nordet d'octobre cesse d'hériter de la fiabilité moyenne des sud-ouest d'été | M | 2 |
| 7 | Alertes ntfy (GO de demain, GO qui tombe) | P3 | Une fenêtre attrapée sans avoir pensé à consulter ; un aller au chalet annulé à temps | M | 2 |
| 8 | Relancer l'essai MOS sur la vérité station | P1 | Une décision ferme : intégrer la régression ou fermer la phase 5 — sur des chiffres, pas une intuition | XS | 0,25 |
| 9 | Cache hors-ligne (service worker) | S3 | Le verdict du matin reste lisible au bord de l'eau sans couverture cellulaire, avec son horodatage | M | 2 |
| 10 | Bilan de saison auto-généré (1er novembre) | P2 | La question « le système a-t-il valu la peine cette année ? » a une réponse chiffrée sans une heure de calcul manuel | M | 2 |
| 11 | Compteur de visites respectueux (GoatCounter) | S4 | Savoir si le cousin s'en sert avant d'investir une session de plus dans le partage | M | 2 |

**Total sessions estimées : 19,5**

---

**[1] Committer la copie `docs/` des poids au recalibrage**
- Constat : `recalibrage.py:133-135` écrit `docs/poids_modeles.json`, mais le
  step de commit ne stage que `data/poids_modeles.json reports/derive.md`
  (`.github/workflows/recalibrage.yml:32`). Aujourd'hui indolore (candidats
  toujours rejetés, fichiers identiques — vérifié par `diff`), faux dès le
  premier recalibrage appliqué.
- Bénéfice : le dashboard public applique les corrections courantes ; sans
  ça, il calculerait ses verdicts avec des biais périmés indéfiniment, sans
  aucun symptôme visible.
- Proposition : ajouter `docs/poids_modeles.json` à la ligne `git add` du
  workflow. Une ligne.
- Dépend de : rien
- Confiance que ça règle le constat : 98 %

**[2] Rendre les échecs de crons bruyants**
- Constat : `quotidien.yml` et `recalibrage.yml` n'ont aucun step `if:
  failure()` ; un échec n'est visible que dans l'onglet Actions. La
  notification courriel par défaut est un réglage du compte GitHub du CPO,
  non vérifiable ici.
- Bénéfice : un trou de données ou une dérive de l'API Open-Meteo se voit le
  jour même — le run cassé du 2026-07-16 (`593e8c8`) n'a été attrapé que
  parce que quelqu'un travaillait sur le repo ce soir-là.
- Proposition : step `if: failure()` dans les deux workflows qui crée une
  issue via `gh api` (le `GITHUB_TOKEN` du job suffit, permission
  `issues: write` à ajouter). Point d'entrée : bloc `steps` des deux
  fichiers.
- Dépend de : rien
- Confiance que ça règle le constat : 90 %

**[3] Mesurer si « modèles divisés » prédit les busts**
- Constat : le dashboard affiche « modèles divisés » dès 5 nds d'écart
  (`docs/app.js:24`, `:199`), mais aucune analyse ne prouve que ces jours-là
  sont moins fiables — le seuil de 5 nds vient du cahier des charges, pas des
  données. Les données pour trancher existent (`data/verification/2026-07.parquet`,
  9 000 lignes + `data/processed/`).
- Bénéfice : soit la cote baisse automatiquement les jours douteux (vraie
  information), soit on retire une mention qui apparaissait sur presque
  toutes les cartes lors des rendus de test — un avertissement permanent
  n'avertit de rien.
- Proposition : script d'analyse comparant le taux de survie des GO à forte
  vs faible divergence, sur le modèle de `busts.py`. Si écart > 15 points,
  câbler l'ajustement dans `confianceGo()` ; sinon retirer la mention.
- Dépend de : rien
- Confiance que ça règle le constat : 85 % (le n de jours divergents est
  peut-être trop petit pour conclure — le script le dira)

**[4] Afficher la précision glissante 30 jours sur la page**
- Constat : la précision courante est recalculée chaque semaine
  (`reports/derive.md`) mais la page publique affiche des cotes figées au
  backtest du 2026-07-15 (`data/poids_modeles.json:genere_le`) ; le pied de
  page renvoie à une période close (`docs/app.js`, bloc `recalibrage`).
- Bénéfice : la confiance dans le produit se maintient ou s'ajuste sur des
  faits frais — si le système se met à rater, ça se voit sur la page, pas
  dans un fichier de reports que personne n'ouvre.
- Proposition : `job_quotidien.py` calcule hits/GO des 30 derniers jours
  depuis les partitions et l'écrit dans un petit `docs/precision.json`
  commité par `quotidien.yml` ; `app.js` l'affiche en pied de page. Trois
  fichiers.
- Dépend de : rien
- Confiance que ça règle le constat : 90 %

**[5] Basculer la vérité sur la station Ecowitt**
- Constat : `TRUTH_SOURCE = "median_hour0"` (`config.py:28`) — la vérité est
  un consensus de modèles, corrélée aux prévisions qu'elle juge ; les busts
  réels sont invisibles par construction (6 seulement détectés sur 3 saisons,
  `reports/rapport_backtest.md`). Le module de bascule est livré et testé
  hors-ligne (`station_ecowitt.py`, `tests/test_station_ecowitt.py`), mais le
  format réel de l'API n'a jamais été vu (pas de clé) et l'anémomètre n'est
  pas acheté.
- Bénéfice : les cotes affichées cessent d'être flattées ; l'écart
  rivage-vs-grille devient une donnée mesurée ; le diagnostic de découplage
  (abandonné faute de signal, conclusion honnête du rapport) redevient
  possible.
- Proposition : acheter/installer l'anémomètre, ajouter les 3 secrets, lancer
  l'autotest `python3 station_ecowitt.py`, corriger `_normaliser()` si le
  format diffère, basculer `config.py:28`. Procédure complète :
  `MAINTENANCE.md`.
- Dépend de : décision d'achat (question 1, section 5)
- Confiance que ça règle le constat : 80 % (le format API réel est
  l'inconnue ; l'autotest est fait pour la lever)

**[6] Conditionner la cote au secteur de vent**
- Constat : `confianceGo()` retourne une fiabilité par horizon seulement
  (`docs/app.js:264-268`) alors que les biais par secteur existent déjà dans
  les poids (`biais_par_secteur`, appliqués aux nds mais pas à la cote) et
  que la garde n ≥ 30 est déjà dans le pipeline (`config.py`,
  `N_MIN_SEGMENT`).
- Bénéfice : un GO dans un régime rare cesse d'afficher une confiance
  empruntée aux régimes fréquents — c'est précisément le genre de GO qui coûte
  un aller au chalet pour rien.
- Proposition : étendre `calculer_poids()` (backtest.py) pour produire
  `fiabilite_go_par_horizon` par secteur quand n ≥ 30, lire la clé dans
  `confianceGo()`, valider par le diagramme de calibration. Trois fichiers.
- Dépend de : rien (mieux après 5 : plus de données par secteur)
- Confiance que ça règle le constat : 75 % (l'échantillon par secteur×horizon
  est peut-être trop mince cette saison — la garde n ≥ 30 protégera)

**[7] Alertes ntfy**
- Constat : `alertes.py:30-33` est un placeholder volontaire ; tout ce qu'une
  alerte doit lire existe déjà (`data/forecast.json`, réécrit chaque matin
  par `job_quotidien.py`).
- Bénéfice : le samedi venteux qu'on découvre le vendredi soir par vibration,
  pas par réflexe de consultation qu'on n'a pas eu ; et l'aller au chalet
  annulé à temps quand le GO de mercredi tombe le vendredi.
- Proposition : implémenter `alertes.py` (POST ntfy.sh, lecture de
  forecast.json, mémoire anti-spam dans un petit fichier d'état), l'appeler
  en fin de `quotidien.yml`. Deux fichiers, un appel externe nouveau.
- Dépend de : décisions de seuils/horaires/topic (question 2, section 5)
- Confiance que ça règle le constat : 90 %

**[8] Relancer l'essai MOS sur la vérité station**
- Constat : l'essai du 2026-07-19 conclut « recul à 24/48 h, +3,4 % à 96 h —
  non intégré » (`reports/mos_baseline.md`), sur la vérité-consensus qui
  laisse peu d'erreur systématique à apprendre.
- Bénéfice : fermer la phase 5 ou l'ouvrir pour de bon, sur des chiffres —
  une session d'exécution au lieu d'un doute permanent.
- Proposition : `python3 mos.py` après 1-2 mois de vérité station ; le
  journal et le verdict par horizon sont automatiques.
- Dépend de : 5
- Confiance que ça règle le constat : 95 % (le script tranche par
  construction)

**[9] Cache hors-ligne (service worker)**
- Constat : `docs/` est une PWA installable (`manifest.webmanifest`,
  `index.html:9-11`) mais sans service worker : sans réseau, la page affiche
  l'erreur de chargement (`docs/app.js`, bloc catch).
- Bénéfice : le verdict consulté à 7 h au chalet reste lisible à 10 h au bord
  de l'eau où le cellulaire ne passe pas — horodaté, jamais déguisé en frais.
- Proposition : `sw.js` en stale-while-revalidate sur les deux appels
  Open-Meteo + bandeau « données de X h » quand le réseau manque ;
  enregistrement dans `index.html`. Trois fichiers.
- Dépend de : rien
- Confiance que ça règle le constat : 85 %

**[10] Bilan de saison auto-généré**
- Constat : les données d'un bilan existent intégralement (partitions
  mensuelles + `reports/derive.md`) mais aucune synthèse annuelle n'est
  produite ; `rapport.py` est un outil de backtest ponctuel, pas un rituel.
- Bénéfice : le 1er novembre, la réponse à « combien de fenêtres cette
  saison, combien attrapées, combien de faux GO ? » existe sans une heure de
  pandas manuel — et l'écart année sur année documente la dérive des modèles.
- Proposition : script `bilan.py` sur le modèle de `rapport.py`, cron annuel
  (novembre), sortie `docs/bilan.html` liée depuis le pied de page. Trois
  fichiers et plus.
- Dépend de : rien (plus riche après 5)
- Confiance que ça règle le constat : 90 %

**[11] Compteur de visites respectueux**
- Constat : aucune mesure d'usage nulle part (grep « analytics|goatcounter|
  plausible » : rien) ; impossible de savoir si le partage au cousin a servi.
- Bénéfice : investir les prochaines sessions selon l'usage réel — ou
  apprendre que le produit n'a qu'un utilisateur et simplifier en
  conséquence.
- Proposition : balise GoatCounter (gratuit, sans cookie) dans
  `index.html`. Un fichier, mais une dépendance tierce nouvelle — d'où M
  selon la table, pas XS.
- Dépend de : accord vie privée (question 5, section 5)
- Confiance que ça règle le constat : 95 %

**Écarté**
- *Prévision probabiliste par membres d'ensembles (GEFS/IFS-ENS)* : L, gain
  non démontré face à la cote historique, et exige de valider une 4e API —
  pas avant que P2 plafonne.
- *Multi-spots* : aucun deuxième spot demandeur identifiable dans le repo ;
  de la structure sans usage.
- *Journal de sessions 1-clic* : franchirait la frontière « aucune écriture
  utilisateur » posée en Vision ; à re-débattre seulement si la station (item
  5) ne suffit pas à revalider les seuils.
- *Migration des partitions froides vers GitHub Releases* : ~70 Ko/mois
  (`MAINTENANCE.md`), le seuil de 500 Mo est à des années.

---

## 5. Décisions qui appartiennent au CPO

1. **L'anémomètre s'achète-t-il, et quand ?** Tout P1 (items 5, 8) et la
   moitié de la valeur analytique du produit attendent ce geste physique que
   le code ne peut pas faire.
2. **Alertes : quel seuil déclenche une vibration ?** GO ≥ 90 % seulement, ou
   aussi les GO à 76 % de 4 jours pour la décision chalet ? À quelle heure,
   sur quel nom de topic (public) ? — les quatre réponses bloquent l'item 7.
3. **Quel taux de faux GO est acceptable ?** Aujourd'hui ~24 % des GO à 96 h
   tombent. Si c'est trop, on durcit les seuils (moins de fenêtres
   annoncées) ; si c'est correct, la calibration actuelle suffit. Le code ne
   peut pas choisir ta tolérance au chalet raté.
4. **Le produit reste-t-il mono-spot ?** La réponse décide si « multi-spots »
   sort d'Écarté un jour — et si non, elle autorise des simplifications
   (config figée, pas d'abstraction de spot).
5. **Un compteur de visites tiers est-il acceptable sur un site familial ?**
   GoatCounter est sans cookie, mais c'est quand même un script externe sur
   une page qu'on a voulue à zéro dépendance. Ta ligne sur la vie privée
   tranche l'item 11.
