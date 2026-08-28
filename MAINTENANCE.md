# Guide de maintenance — pour continuer sans assistance

Ce document répond à : « le système roule tout seul, mais si quelque chose
brise ou si je veux avancer, je fais quoi ? »

## Ce qui roule tout seul (rien à faire)

| Quoi | Quand | Où vérifier |
|---|---|---|
| Archivage prévu-vs-réalisé | chaque jour 09:17 UTC | onglet Actions → « Vérification quotidienne » ; commits quotidiens dans `data/verification/` |
| Recalibrage des corrections | lundi 10:43 UTC | Actions → « Recalibrage hebdomadaire » ; une ligne s'ajoute à `reports/derive.md` |
| Publication du dashboard | à chaque commit touchant `docs/` | Actions → « Publier le dashboard » |
| Tests | à chaque commit touchant du code | Actions → « Tests » |
| Données affichées | à chaque ouverture de la page + chaque heure 6 h–22 h | le pied de page affiche l'heure de chargement |

Le dashboard reste juste même si les crons tombent : il va chercher les
prévisions en direct — seuls le recalibrage et l'historique dépendent des crons.

## Diagnostics rapides

- **La page affiche « Impossible de charger les prévisions »** : Open-Meteo
  est temporairement indisponible, ou son API a changé. Recharger ; si ça
  persiste des jours, comparer l'URL construite dans `docs/app.js`
  (fonction `demarrer`) avec https://open-meteo.com/en/docs.
- **Un workflow est rouge** : ouvrir le run dans Actions, lire la dernière
  erreur. Les erreurs réseau se réessaient toutes seules au run suivant —
  n'intervenir que si ça échoue plusieurs jours de suite.
- **Badge « workflows désactivés »** : GitHub coupe les crons après ~60 jours
  sans activité. Actions → le workflow → « Enable workflow ».
- **`reports/derive.md` montre « conservé » chaque semaine** : normal — le
  garde-fou refuse les poids qui ne s'améliorent pas. Un RMSE qui MONTE
  durablement (ex. 0,8 → 1,5) signalerait un changement de version chez un
  fournisseur de modèle : relancer alors `python3 rapport.py` pour requalifier.

## La vérification croisée (Lac Saint-Pierre)

Une piste de diagnostic qui tourne toute seule à côté du produit : chaque
jour, le cron ajoute à `data/verification_croisee/` ce que chaque modèle
prévoyait à 24/48/96 h et ce que l'anémomètre officiel de Lac Saint-Pierre a
réellement mesuré. Elle ne change ni les poids, ni les verdicts, ni la page.

```bash
python3 verification_croisee.py --rapport   # -> reports/verification_croisee.md
```

**Quoi surveiller.** Le classement des modèles et leur corrélation. Un modèle
dont le RMSE saute d'un coup (ex. 4,4 → 6,0) sans que les autres bougent
signale un changement de version chez le fournisseur — c'est le seul endroit
du système capable de le voir, parce que `reports/derive.md` compare les
modèles à un étalon qui bouge avec eux.

**Ce qu'il ne faut PAS en faire.** Recopier ces biais dans les poids. Lac
Saint-Pierre est un plan d'eau bien plus ouvert que le Maskinongé (vent
médian de jour 9,2 nds contre ~5) : les sept modèles y sous-estiment tous de
1 à 3 nds, et c'est le biais du site. Le classement se transporte
raisonnablement, les biais absolus non.

**Si l'API d'ECCC tombe.** Le job quotidien encapsule cette piste dans un
`try` et affiche « Vérification croisée ignorée ce run » : l'archivage
principal et `forecast.json` ne sont jamais bloqués, et la fenêtre de
rattrapage J-9 du lendemain récupère les jours manqués.

## « Le modèle s'est-il amélioré ? » — et comment revenir en arrière

Chaque backtest complet et chaque recalibrage appliqué archivent une version
du modèle dans `data/modeles/`. Trois commandes suffisent :

```bash
python3 versions.py --lister                 # qu'est-ce qui a tourné, et quand
python3 versions.py --comparer v2-… v3-…     # laquelle prévoit le mieux
python3 versions.py --activer v2-… --raison "v3 rate les journées de SO"
git add -A data/modeles data/poids_modeles.json docs/poids_modeles.json && git commit
```

**Le candidat en place.** `v4-2026-08-28` (`origine: hrrr`), l'ensemble à
sept membres, à l'essai et **non promu** : mesuré hors échantillon contre
l'anémomètre réel, il dégrade la prévision de 0,014 nd (`reports/hrrr.md`).
Le laisser tel quel est la bonne décision ; le reconstruire après quelques
mois de données de plus se fait avec `python3 candidat_hrrr.py`.

**Le contrôle périodique.** Après un mois ou deux de données accumulées,
comparer la version active à celle d'avant : la fenêtre d'évaluation démarre
automatiquement après la dernière donnée ayant servi à calibrer l'une OU
l'autre, donc le résultat est honnête sans réglage manuel. Lire les deux
métriques, pas une seule — le RMSE (erreur en nœuds) peut bouger sans que le
taux de GO confirmé (ce que voit l'utilisateur) change d'un pouce.

Trois sorties possibles, toutes normales :
- « Match nul » : les deux versions se valent, garder l'active.
- « B est meilleure » : si B est l'ancienne, `--activer` la restaure.
- « Échantillon trop mince » ou « aucune donnée après la borne » : il faut
  simplement laisser passer des jours. L'outil refuse de trancher plutôt que
  d'inventer un gagnant sur 30 lignes.

**Après un retour arrière**, il faut committer : le dashboard lit la copie du
dépôt (`docs/poids_modeles.json`), pas le registre. Le recalibrage suivant
repart de la version active — s'il produit mieux, il créera une version
nouvelle par-dessus, sans jamais réécrire l'historique.

**Si le registre est perdu ou incohérent** : le supprimer (`rm -rf
data/modeles`) puis lancer `python3 versions.py --lister` le reconstruit à
partir de `data/poids_modeles.json` comme nouvelle `v1`. L'historique
antérieur est perdu, pas les poids en service.

## Reproduire le backtest complet (local)

```bash
pip install -r requirements.txt
python3 telecharge.py   # ~10 min, cache dans data/raw/
python3 rapport.py      # backtest -> rapport + poids
# les 9 suites, dans l'ordre de .github/workflows/tests.yml
for t in fenetre verite station_ecowitt openmeteo_client versions \
         verification_croisee comparaison candidat; do
  python3 tests/test_$t.py || break
done && node tests/test_dashboard.js
```

## Brancher la station Ecowitt (phase 4, prête)

1. Installer l'anémomètre : exposition maximale (bout de quai / pointe),
   loin des arbres et bâtiments ; noter la hauteur du mât dans
   `station_ecowitt.py` (`HAUTEUR_ANEMOMETRE_M`). Le vent au rivage lit
   plus bas que le milieu du lac — biais constant, la boucle l'apprendra.
2. Ajouter les GitHub Secrets (Settings → Secrets and variables → Actions) :
   `ECOWITT_APPLICATION_KEY`, `ECOWITT_API_KEY`, `ECOWITT_MAC`.
3. Valider le format de l'API en vrai (règle du projet) :
   `ECOWITT_APPLICATION_KEY=... ECOWITT_API_KEY=... ECOWITT_MAC=... python3 station_ecowitt.py`
   — ajuster `_normaliser()` si la structure diffère de la doc.
4. Mettre `TRUTH_SOURCE = "station"` dans `config.py`, exposer les trois
   secrets dans `quotidien.yml` et `recalibrage.yml` (bloc `env:` du step
   python, gabarit dans la docstring de `station_ecowitt.py`), pousser.
5. Laisser tourner ~1 mois puis relancer `python3 rapport.py` et
   `python3 mos.py` : les biais absolus et le diagnostic des busts seront
   requalifiés sur du vent réellement mesuré.

## Phase 5 (correction apprise) — état et prochaine étape

`python3 mos.py` exécute une régression MOS par horizon (numpy, validation
temporelle) et compare au baseline en production. Dernier essai
(2026-07-19, vérité = consensus de modèles) : recul à 24 h/48 h, gain de
3,4 % à 96 h — **pas intégré**, conformément au critère « pas de gain
mesuré = pas de complexité ». Journal : `reports/mos_baseline.md`.
Prochaine étape sensée : relancer après 1-2 mois de vérité station.

## Phase 6 (alertes) — quoi décider avant de coder

Lire la docstring d'`alertes.py` : canal ntfy pressenti, et la liste des
paramètres à trancher (seuils de confiance, horaires, anti-spam, topic).
`data/forecast.json` contient déjà tout ce qu'une alerte doit lire.

## Déménager le dashboard hors de GitHub Pages

`docs/` est autonome : copier son contenu tel quel par FTP (GoDaddy ou
autre). Seule dépendance externe : l'API publique d'Open-Meteo. Prévoir de
mettre à jour `docs/poids_modeles.json` après chaque recalibrage (ou pointer
un petit script FTP dans `recalibrage.yml`).
