# MOS vs baseline — journal des essais (phase 5)

RMSE (nds) sur les 60 derniers jours, jamais vus à l'entraînement. Baseline = ensemble corrigé-pondéré en production. Prédicteurs MOS : vent/u/v de l'ensemble + cycle diurne. Vérité courante : median_hour0.

## 2026-07-19 (TRUTH_SOURCE=median_hour0)

| horizon   |   n_train |   n_test |   rmse_baseline |   rmse_mos |   gain_% |
|:----------|----------:|---------:|----------------:|-----------:|---------:|
| 24h       |      4596 |      720 |           0.934 |      0.988 |     -5.8 |
| 48h       |      4596 |      720 |           1.115 |      1.143 |     -2.5 |
| 96h       |      4596 |      720 |           1.622 |      1.567 |      3.4 |

**Verdict : Résultat mitigé : gain à 96h mais recul à 24h, 48h. Ne PAS intégrer globalement ; un MOS par horizon serait envisageable, mais pas sans confirmation sur plusieurs recalibrages — et surtout pas avant la vérité station, qui change la cible.**

