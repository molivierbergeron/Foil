"""Phase 5 — correction apprise (MOS), version la plus simple qui se défende.

MOS (Model Output Statistics) : régression linéaire par horizon qui apprend
à corriger l'ensemble à partir de prédicteurs disponibles au moment de la
prévision. Prédicteurs volontairement minimaux et interprétables :

    vent_ensemble, u_ensemble, v_ensemble, heure locale (sin/cos), constante

Garde-fous non négociables (règles du projet) :
- Validation TEMPORELLE : entraînement sur le passé, test sur les
  JOURS_TEST derniers jours — jamais de fuite temporelle.
- Comparaison au baseline « ensemble corrigé-pondéré » (la méthode en
  production). Pas de gain mesuré = pas de complexité ajoutée : le script
  IMPRIME le verdict et journalise dans reports/mos_baseline.md, il ne
  remplace jamais les poids en production de lui-même.

À relancer quand la vérité station (phase 4) existera : c'est là que le MOS
a une vraie chance (l'écart grille-vs-lac est systématique, donc apprenable).
Numpy seulement — pas de scikit-learn tant que le linéaire n'a pas plafonné.
Usage : python3 mos.py
"""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config
import recalibrage

JOURS_TEST = 60


def _ensemble_par_heure(df: pd.DataFrame) -> pd.DataFrame:
    """Lignes appariées (long) -> une ligne par heure : médianes inter-modèles."""
    grp = df.groupby("time")
    ens = pd.DataFrame({
        "vent": grp["vent"].median(),
        "u": grp["u"].median(),
        "v": grp["v"].median(),
        "verite_vent": grp["verite_vent"].first(),
        "heure_locale": grp["heure_locale"].first(),
    }).dropna()
    return ens


def _matrice(ens: pd.DataFrame) -> np.ndarray:
    heures = ens["heure_locale"].astype(float)
    return np.column_stack([
        ens["vent"].astype(float),
        ens["u"].astype(float),
        ens["v"].astype(float),
        np.sin(2 * np.pi * heures / 24),
        np.cos(2 * np.pi * heures / 24),
        np.ones(len(ens)),
    ])


def evaluer() -> pd.DataFrame:
    apparie, _ = recalibrage.charger_apparie_complet()
    jour = apparie[(apparie["heure_locale"] >= config.HEURE_DEBUT)
                   & (apparie["heure_locale"] < config.HEURE_FIN)]
    dates = pd.to_datetime(jour["date_locale"].astype(str))
    coupure = dates.max() - pd.Timedelta(days=JOURS_TEST)

    import json
    with open(config.FICHIER_POIDS) as f:
        poids = json.load(f)

    lignes = []
    for horizon in config.HORIZONS:
        h = jour[jour["horizon"] == horizon]
        d = pd.to_datetime(h["date_locale"].astype(str))
        train, test = h[d <= coupure], h[d > coupure]
        if len(train) < 500 or len(test) < 100:
            continue

        ens_train, ens_test = _ensemble_par_heure(train), _ensemble_par_heure(test)
        X, y = _matrice(ens_train), ens_train["verite_vent"].astype(float).values
        coeffs, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = _matrice(ens_test) @ coeffs
        rmse_mos = float(np.sqrt(np.mean((pred - ens_test["verite_vent"]) ** 2)))

        rmse_base = recalibrage.rmse_ensemble(test, poids).get(horizon, float("nan"))
        lignes.append({
            "horizon": horizon, "n_train": len(ens_train), "n_test": len(ens_test),
            "rmse_baseline": round(rmse_base, 3), "rmse_mos": round(rmse_mos, 3),
            "gain_%": round(100 * (rmse_base - rmse_mos) / rmse_base, 1),
            "coeffs": [round(float(c), 4) for c in coeffs],
        })
    return pd.DataFrame(lignes)


def principal():
    resultats = evaluer()
    gagnants = (resultats[resultats["gain_%"] > 2]["horizon"].tolist()
                if len(resultats) else [])
    perdants = (resultats[resultats["gain_%"] < 0]["horizon"].tolist()
                if len(resultats) else [])
    if gagnants and not perdants:
        verdict = (f"Le MOS bat le baseline à {', '.join(gagnants)} — envisager "
                   "de l'intégrer au recalibrage (même garde-fou temporel).")
    elif gagnants:
        verdict = (f"Résultat mitigé : gain à {', '.join(gagnants)} mais recul à "
                   f"{', '.join(perdants)}. Ne PAS intégrer globalement ; un MOS "
                   "par horizon serait envisageable, mais pas sans confirmation "
                   "sur plusieurs recalibrages — et surtout pas avant la vérité "
                   "station, qui change la cible.")
    else:
        verdict = ("Pas de gain mesuré (> 2 %) : on garde l'ensemble "
                   "corrigé-pondéré, plus simple. À relancer quand la vérité "
                   "station existera.")

    chemin = Path("reports/mos_baseline.md")
    entete = not chemin.exists()
    with open(chemin, "a") as f:
        if entete:
            f.write("# MOS vs baseline — journal des essais (phase 5)\n\n"
                    "RMSE (nds) sur les 60 derniers jours, jamais vus à "
                    "l'entraînement. Baseline = ensemble corrigé-pondéré en "
                    "production. Prédicteurs MOS : vent/u/v de l'ensemble + "
                    "cycle diurne. Vérité courante : "
                    f"{config.TRUTH_SOURCE}.\n\n")
        f.write(f"## {datetime.now(timezone.utc).date().isoformat()} "
                f"(TRUTH_SOURCE={config.TRUTH_SOURCE})\n\n")
        f.write(resultats.drop(columns=["coeffs"]).to_markdown(index=False))
        f.write(f"\n\n**Verdict : {verdict}**\n\n")

    print(resultats.to_string())
    print("\n" + verdict)
    print(f"Journal : {chemin}")


if __name__ == "__main__":
    principal()
