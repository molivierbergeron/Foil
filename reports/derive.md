# Dérive des modèles — journal des recalibrages

Chaque semaine, des poids candidats sont calculés sur la fenêtre
glissante (saison courante pesant double) et comparés aux poids
courants sur les 60 derniers jours (validation temporelle, RMSE de
l'ensemble corrigé-pondéré, en nds). Ils ne sont appliqués que
s'ils font au moins aussi bien. Une dérive soudaine d'un modèle
(changement de version chez le fournisseur) se verra ici.

| Date | RMSE courant (24/48/96 h) | RMSE candidat | Décision |
|---|---|---|---|
| 2026-07-15 | 0.76/0.93/1.40 | 0.76/0.93/1.40 | **conservé** (candidat moins bon) |
| 2026-07-20 | 0.82/1.01/1.48 | 0.82/1.01/1.48 | **conservé** (candidat moins bon) |
| 2026-07-27 | 0.83/1.04/1.57 | 0.83/1.05/1.58 | **conservé** (candidat moins bon) |
| 2026-08-03 | 0.82/1.06/1.49 | 0.82/1.06/1.49 | **conservé** (candidat moins bon) |
| 2026-08-10 | 0.91/1.08/1.49 | 0.91/1.08/1.50 | **conservé** (candidat moins bon) |
| 2026-08-17 | 0.89/1.05/1.48 | 0.89/1.05/1.49 | **conservé** (candidat moins bon) |
