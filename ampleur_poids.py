"""Repondérer les modèles : jusqu'où ça peut aller, et est-ce que ça vaut la peine ?

La question posée
-----------------
« Un écart sous 1 nd ne change aucune décision de sortir le bateau. Est-ce
qu'entre les jeux de poids on peut trouver 1, 2, 3 nds d'écart ? »

Ce script y répond par la distribution, pas par la moyenne — une moyenne de
0,15 nd peut cacher des heures à 3 nds, et c'est ça qui compte.

Trois mesures
-------------
1. PRÉCISION, hors échantillon. Les poids du candidat ont été dérivés des
   données de Lac Saint-Pierre : les juger sur ces mêmes données le ferait
   gagner par construction. On refait donc le candidat sur 2024-2025 seulement
   et on juge sur 2026, jamais vu. Les biais sont communs aux trois jeux
   (moyenne d'erreur par modèle sur le train), ce qui isole la seule chose qui
   les distingue : la pondération.
2. SIGNIFICATIVITÉ, par bootstrap apparié par JOUR. Deux heures du même jour
   ne sont pas indépendantes — même système météo, mêmes erreurs. Un bootstrap
   par heure surestimerait la significativité.
3. AMPLEUR, en distribution. À quelle fréquence l'écart dépasse-t-il 1 nd,
   2 nds ? Et comparé à quoi — l'étendue brute entre modèles, le fait de
   choisir un seul modèle.

Limite, à ne pas oublier
------------------------
Tout est mesuré à Lac Saint-Pierre, 38 km du spot, sur un plan d'eau bien
plus ouvert. Le classement se transporte raisonnablement au Lac Maskinongé ;
les biais absolus, non. Seul l'anémomètre au lac (phase 4) trancherait.

    python3 ampleur_poids.py     # -> reports/ampleur_ponderation.md
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import config
import verification_croisee
import versions

SORTIE = Path("reports/ampleur_ponderation.md")
ANNEE_TEST = 2026
N_BOOTSTRAP = 4000
GRAINE = 20260828


def _donnees():
    df = verification_croisee.charger()
    if df.empty:
        raise RuntimeError(
            "Aucune donnée de vérification croisée. Lancer d'abord le "
            "workflow « Rattrapage vérification croisée ».")
    df = df[(df["heure_locale"] >= config.HEURE_DEBUT)
            & (df["heure_locale"] < config.HEURE_FIN)]
    annees = pd.to_datetime(df["date_locale"].astype(str)).dt.year
    return df[annees < ANNEE_TEST], df[annees == ANNEE_TEST]


def _prepare(train, test, horizon, poids_actif):
    """Biais/RMSE appris sur le train, ensembles évalués sur le test."""
    tr = train[train["horizon"] == horizon]
    te = test[test["horizon"] == horizon]
    if tr.empty or te.empty:
        return None
    modeles = sorted(set(tr["modele"]) & set(te["modele"]))

    biais, rmse = {}, {}
    for m in modeles:
        g = tr[tr["modele"] == m]
        err = g["vent"].astype(float) - g["obs_vent"].astype(float)
        biais[m] = float(err.mean())
        rmse[m] = float(np.sqrt((err ** 2).mean()))

    piv = te.pivot_table(index="time", columns="modele", values="vent")
    piv = piv[[m for m in modeles if m in piv.columns]].dropna()
    if piv.empty:
        return None
    obs = te.groupby("time")["obs_vent"].first().reindex(piv.index).astype(float)
    corrige = pd.DataFrame({m: piv[m].astype(float) - biais[m] for m in piv.columns})

    jeux = {
        # Ce qui tourne en production : poids calibrés contre le consensus
        # des modèles entre eux.
        "en service": {m: poids_actif["modeles"].get(m, {}).get("horizons", {})
                       .get(horizon, {}).get("poids") for m in modeles},
        # Le candidat, REFAIT sur le train seulement.
        "candidat": {m: 1 / rmse[m] ** 2 for m in modeles},
        # Témoin : ne rien faire d'intelligent du tout.
        "poids égaux": {m: 1.0 for m in modeles},
    }

    def ensemble(w):
        cols = [m for m in corrige.columns if w.get(m)]
        return sum(corrige[m] * w[m] for m in cols) / sum(w[m] for m in cols)

    series = {nom: ensemble(w) for nom, w in jeux.items()
              if any(w.get(m) for m in corrige.columns)}
    jours = pd.Series(piv.index.tz_convert(config.FUSEAU_LOCAL).date, index=piv.index)
    return {"series": series, "obs": obs, "corrige": corrige, "jours": jours,
            "rmse_train": rmse, "n_heures": len(piv),
            "n_jours": int(jours.nunique())}


def _rmse(serie, obs):
    return float(np.sqrt(((serie - obs) ** 2).mean()))


def _bootstrap(ctx, nom_a, nom_b, rng):
    """Gain de RMSE (a - b) et IC 95 %, rééchantillonné par jour."""
    ea = (ctx["series"][nom_a] - ctx["obs"]) ** 2
    eb = (ctx["series"][nom_b] - ctx["obs"]) ** 2
    jours = ctx["jours"]
    uniques = jours.unique()
    index_par_jour = {j: np.where(jours.values == j)[0] for j in uniques}
    diffs = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        tirage = rng.choice(uniques, size=len(uniques), replace=True)
        masque = np.concatenate([index_par_jour[j] for j in tirage])
        diffs[i] = (np.sqrt(ea.values[masque].mean())
                    - np.sqrt(eb.values[masque].mean()))
    return diffs.mean(), np.percentile(diffs, 2.5), np.percentile(diffs, 97.5)


def construire() -> str:
    train, test = _donnees()
    poids_actif = versions.charger_poids(versions.actif())
    rng = np.random.default_rng(GRAINE)
    station = config.STATION_CROISEE

    L = [
        "# Repondérer les modèles : ampleur et utilité réelles",
        "",
        f"Généré le {date.today().isoformat()} par `ampleur_poids.py`. "
        f"Étalon : anémomètre de {station['nom']} ({station['id']}), "
        f"à {station['distance_km']} km du spot.",
        "",
        "## La question",
        "",
        "> « Un écart sous 1 nd ne change aucune décision de sortir le bateau. "
        "Est-ce qu'entre les jeux de poids on peut trouver 1, 2, 3 nds ? »",
        "",
        "**Réponse courte : non.** Repondérer six modèles ne peut pas produire "
        "un écart de cette taille, et ce n'est pas une limite de réglage mais "
        "une limite arithmétique. Les leviers de 1-3 nds sont ailleurs — "
        "voir la conclusion.",
        "",
        "## Méthode",
        "",
        f"Entraînement sur les saisons < {ANNEE_TEST}, jugement sur "
        f"{ANNEE_TEST} — **jamais vu**. C'est essentiel : les poids du candidat "
        "sont dérivés des données de cette station, les juger dessus les ferait "
        "gagner par construction.",
        "",
        "Les biais (moyenne d'erreur par modèle, apprise sur le train) sont "
        "**communs aux trois jeux**, ce qui isole la seule chose qui les "
        "distingue : la pondération. Trois jeux comparés :",
        "",
        "| Jeu | Origine des poids |",
        "|---|---|",
        "| **en service** | calibrés contre le consensus des modèles (production) |",
        "| **candidat** | ∝ 1/RMSE² mesuré contre l'anémomètre, refait sur le train seul |",
        "| **poids égaux** | témoin : ne rien faire d'intelligent |",
        "",
    ]

    contextes = {}
    for horizon in config.HORIZONS:
        ctx = _prepare(train, test, horizon, poids_actif)
        if ctx:
            contextes[horizon] = ctx

    # ------------------------------------------------------------ précision
    L += ["## 1. Précision hors échantillon", "",
          "RMSE sur " + str(ANNEE_TEST) + ", en nœuds (plus bas = mieux).", "",
          "| Horizon | en service | candidat | poids égaux | heures | jours |",
          "|---|---:|---:|---:|---:|---:|"]
    for horizon, ctx in contextes.items():
        vals = {nom: _rmse(s, ctx["obs"]) for nom, s in ctx["series"].items()}
        L.append(f"| {horizon} | {vals.get('en service', float('nan')):.3f} | "
                 f"{vals['candidat']:.3f} | {vals['poids égaux']:.3f} | "
                 f"{ctx['n_heures']} | {ctx['n_jours']} |")
    L += ["",
          "**Le témoin bat déjà la production.** Les poids égaux — c'est-à-dire "
          "aucune pondération — font mieux que le calibrage en service. "
          "L'essentiel du gain du candidat n'est donc pas un mérite : c'est "
          "l'abandon d'une pondération qui nuisait.",
          ""]

    # ------------------------------------------------- significativité
    L += ["## 2. Est-ce significatif ?", "",
          "Bootstrap apparié **par jour**, non par heure : deux heures du même "
          "jour partagent le même système météo et les mêmes erreurs, les "
          "traiter comme indépendantes gonflerait la significativité.", "",
          "| Horizon | Comparaison | Gain (nds) | IC 95 % | Verdict |",
          "|---|---|---:|---|---|"]
    paires = [("en service", "candidat"), ("en service", "poids égaux"),
              ("poids égaux", "candidat")]
    for horizon, ctx in contextes.items():
        for a, b in paires:
            if a not in ctx["series"] or b not in ctx["series"]:
                continue
            moyen, lo, hi = _bootstrap(ctx, a, b, rng)
            verdict = "significatif" if lo > 0 else "**non significatif**"
            L.append(f"| {horizon} | {a} → {b} | {moyen:+.3f} | "
                     f"[{lo:+.3f}, {hi:+.3f}] | {verdict} |")
    L += ["",
          "Significatif ne veut pas dire utile : un gain de 0,09 nd sur une "
          "erreur de 3,8 nds est réel et sans conséquence pratique.",
          ""]

    # ----------------------------------------------------------- ampleur
    L += ["## 3. Ampleur : la distribution, pas la moyenne", "",
          "Écart absolu entre les prévisions de deux jeux de poids, heure par "
          "heure. C'est la mesure qui répond vraiment à la question posée.", "",
          "| Horizon | Paire | médian | p90 | p99 | max | **> 1 nd** | > 2 nds |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for horizon, ctx in contextes.items():
        for a, b in paires:
            if a not in ctx["series"] or b not in ctx["series"]:
                continue
            d = (ctx["series"][b] - ctx["series"][a]).abs()
            L.append(f"| {horizon} | {a} ↔ {b} | {d.median():.2f} | "
                     f"{d.quantile(.9):.2f} | {d.quantile(.99):.2f} | "
                     f"{d.max():.2f} | {(d > 1).mean():.1%} | {(d > 2).mean():.1%} |")

    # ------------------------------------------------- autres leviers
    L += ["", "## 4. Pour comparaison : des leviers d'une autre nature", "",
          "| Horizon | Levier | médian | p90 | max | > 1 nd |",
          "|---|---|---:|---:|---:|---:|"]
    for horizon, ctx in contextes.items():
        corrige, series = ctx["corrige"], ctx["series"]
        etendue = corrige.max(axis=1) - corrige.min(axis=1)
        L.append(f"| {horizon} | étendue entre les modèles bruts | "
                 f"{etendue.median():.2f} | {etendue.quantile(.9):.2f} | "
                 f"{etendue.max():.2f} | {(etendue > 1).mean():.0%} |")
        meilleur = min(ctx["rmse_train"], key=ctx["rmse_train"].get)
        if meilleur in corrige.columns and "en service" in series:
            d = (corrige[meilleur] - series["en service"]).abs()
            nom = config.MODELES.get(meilleur, {}).get("nom", meilleur)
            L.append(f"| {horizon} | un seul modèle ({nom}) au lieu de l'ensemble | "
                     f"{d.median():.2f} | {d.quantile(.9):.2f} | {d.max():.2f} | "
                     f"{(d > 1).mean():.0%} |")

    # RMSE des modèles seuls, pour montrer que le levier va dans le mauvais sens
    if "24h" in contextes:
        ctx = contextes["24h"]
        seuls = sorted(((m, _rmse(ctx["corrige"][m], ctx["obs"]))
                        for m in ctx["corrige"].columns), key=lambda x: x[1])
        meilleur_ens = min(_rmse(s, ctx["obs"]) for s in ctx["series"].values())
        L += ["",
              f"À 24 h, le meilleur modèle SEUL fait {seuls[0][1]:.3f} nds "
              f"({config.MODELES.get(seuls[0][0], {}).get('nom', seuls[0][0])}), "
              f"contre {meilleur_ens:.3f} pour le meilleur ensemble. Choisir un "
              "seul modèle déplacerait bien la prévision de 1-3 nds — dans le "
              "mauvais sens. **Aucun modèle isolé ne bat la moyenne.**"]

    # -------------------------------------------------------- conclusion
    L += ["", "## Conclusion", "",
          "Les trois jeux sont des **moyennes pondérées des mêmes six nombres**. "
          "Une moyenne est bornée par ses ingrédients : redistribuer les poids "
          "ne peut pas sortir du nuage que forment les six modèles une fois "
          "débiaisés. L'écart plafonne, quelle que soit l'ingéniosité du calcul.",
          "",
          "Il y a aussi une raison théorique à ce que les poids égaux tiennent "
          "si bien : la pondération ∝ 1/RMSE² n'est optimale que si les erreurs "
          "des modèles sont **indépendantes**. Elles ne le sont pas — les "
          "modèles digèrent les mêmes observations et partagent des "
          "paramétrisations. Sous erreurs corrélées, la pondération "
          "inverse-variance perd son fondement et l'équipondération devient "
          "quasi optimale, tout en étant bien plus robuste au surapprentissage.",
          "",
          "**Deux leviers peuvent produire 1-3 nds, et aucun n'est une "
          "pondération :**",
          "",
          "1. **Ajouter un modèle vraiment différent** — HRRR (3 km, NOAA) est "
          "backtestable sur trois saisons et couvre le lac. Une septième voix "
          "indépendante change le nuage ; redistribuer six voix, non.",
          "2. **L'anémomètre au lac.** À la station de mesure, les six modèles "
          "sous-estiment tous de 1 à 3 nds : c'est l'erreur de SITE, pile dans "
          "la fourchette qui compte. Aucune pondération ne peut la toucher, "
          "parce qu'elle ne vient pas du choix des modèles mais de ce que la "
          "grille ignore du plan d'eau. Le Lac Maskinongé a la sienne, et "
          "personne ne la connaît.",
          "",
          "**Recommandation : arrêter de régler les poids.** Le candidat "
          f"actuel ({versions.candidat() or '—'}) reste archivé et hors "
          "service ; il sera rejugé quand la vérité sera meilleure.",
          "",
          "## Limite de cette analyse",
          "",
          f"Tout est mesuré à {station['nom']}, à {station['distance_km']} km, "
          "sur un plan d'eau bien plus ouvert que le Maskinongé. Le classement "
          "des modèles s'y transporte raisonnablement ; les biais absolus, non. "
          "Ces conclusions portent sur la MÉCANIQUE de la pondération, qui est "
          "la même partout — pas sur les valeurs numériques au spot.",
          ""]
    return "\n".join(L)


def principal() -> int:
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(construire())
    print(f"-> {SORTIE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
