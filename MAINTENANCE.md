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

## Reproduire le backtest complet (local)

```bash
pip install -r requirements.txt
python3 telecharge.py   # ~10 min, cache dans data/raw/
python3 rapport.py      # backtest -> rapport + poids
python3 tests/test_fenetre.py && python3 tests/test_verite.py \
  && python3 tests/test_station_ecowitt.py && node tests/test_dashboard.js
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
