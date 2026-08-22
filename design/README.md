# design/ — exploration d'interface (hors production)

Maquettes de la refonte mobile. **Rien ici n'est branché sur `docs/`** : la
production reste `docs/index.html` + `docs/app.js` tant qu'une direction
n'est pas choisie.

| Fichier | Rôle |
|---|---|
| `Actuel.dc.html` | L'écran actuel recréé à l'identique depuis `docs/style.css` et `docs/app.js` — la référence contre laquelle comparer |
| `Main.dc.html` | Direction A — « Verdict » : une phrase répond, le reste se replie |
| `DirectionB.dc.html` | Direction B — « La bande » : les 7 jours en rubans contre la bande de foil |
| `DirectionC.dc.html` | Direction C — « Le fil » : énoncés datés, révisions et GO vérifiés |
| `canvas.json` | Mise en page du canevas (positions, notes) |

Données : la semaine réelle de `data/forecast.json` (aucun GO avant le
vendredi 28). Les valeurs horaires et les rafales sont des exemples
plausibles, cohérents avec les verdicts et les seuils de
`data/poids_modeles.json` (bande 7–16 nds, marginal 5, fenêtre ≥ 2 h,
blocs 8–11 / 11–14 / 14–18), pas des sorties du modèle.

Le fichier assemblé et publié (`foil-directions-mobile.html`, ~2 Mo) n'est pas
commité : il se régénère depuis les fichiers ci-dessus.
