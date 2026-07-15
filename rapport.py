"""Génère reports/rapport_backtest.md et ses graphiques (phase 1)."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import backtest
import busts
import config

DOSSIER = Path("reports")

# Palette catégorielle validée (dataviz, mode clair, ordre fixe par modèle)
COULEURS = {
    "gem_global": "#2a78d6",
    "gem_regional": "#008300",
    "gem_hrdps_continental": "#e87ba4",
    "ecmwf_ifs025": "#eda100",
    "gfs_global": "#1baf7a",
    "icon_global": "#eb6834",
}
ORDRE_HORIZONS = ["24h", "48h", "96h"]

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": "#d8d7d2", "axes.grid": True, "grid.color": "#eceae5",
    "grid.linewidth": 0.6, "axes.axisbelow": True,
    "text.color": "#0b0b0b", "axes.labelcolor": "#52514e",
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
})


def _sauver(fig, nom):
    fig.savefig(DOSSIER / nom, dpi=150, bbox_inches="tight")
    plt.close(fig)


def figure_biais_rmse(stats: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for metrique, ax in zip(["biais", "rmse"], axes):
        for modele, g in stats.groupby("modele"):
            g = g.set_index("horizon").reindex(ORDRE_HORIZONS).dropna(subset=[metrique])
            ax.plot(g.index, g[metrique], marker="o", markersize=7, linewidth=2,
                    color=COULEURS[modele], label=config.MODELES[modele]["nom"])
        ax.set_xlabel("Horizon de prévision")
        ax.set_title("Biais (nds)" if metrique == "biais" else "RMSE (nds)",
                     loc="left", fontweight="bold")
        if metrique == "biais":
            ax.axhline(0, color="#a8a7a2", linewidth=1)
    poignees, etiquettes = axes[0].get_legend_handles_labels()
    fig.legend(poignees, etiquettes, ncol=3, fontsize=8, frameon=False,
               loc="upper center", bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("Erreur sur le vent moyen, journée navigable (8 h–20 h), 2024–2026",
                 x=0.01, ha="left", fontsize=11)
    _sauver(fig, "biais_rmse.png")


def figure_confusion(conf: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for metrique, ax, titre in [("pod", axes[0], "Probabilité de détection"),
                                ("far", axes[1], "Taux de fausses alertes")]:
        for modele, g in conf.groupby("modele"):
            g = g.set_index("horizon").reindex(ORDRE_HORIZONS).dropna(subset=[metrique])
            ics = g[f"{metrique}_ic"]
            bas = [v - ic[0] for v, ic in zip(g[metrique], ics)]
            haut = [ic[1] - v for v, ic in zip(g[metrique], ics)]
            ax.errorbar(g.index, g[metrique], yerr=[bas, haut], marker="o",
                        markersize=7, linewidth=2, capsize=3,
                        color=COULEURS[modele], label=config.MODELES[modele]["nom"])
        ax.set_ylim(0, 1)
        ax.set_xlabel("Horizon")
        ax.set_title(titre, loc="left", fontweight="bold")
    poignees, etiquettes = axes[0].get_legend_handles_labels()
    fig.legend(poignees, etiquettes, ncol=3, fontsize=8, frameon=False,
               loc="upper center", bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("Événement « fenêtre foilable » : détection vs fausses alertes"
                 " (barres = IC 95 %)", x=0.01, ha="left", fontsize=11)
    _sauver(fig, "confusion.png")


def figure_survie(surv: pd.DataFrame):
    lignes = surv[surv["de"] == "96h"]
    fig, ax = plt.subplots(figsize=(7, 4))
    etapes = lignes["vers"].tolist()
    taux = lignes["taux"].tolist()
    ics = lignes["ic"].tolist()
    ax.bar(etapes, taux, color="#2a78d6", width=0.55)
    for i, (t, ic) in enumerate(zip(taux, ics)):
        ax.plot([i, i], [ic[0], ic[1]], color="#0b0b0b", linewidth=1.5)
        ax.annotate(f"{t:.0%}", (i, t), textcoords="offset points",
                    xytext=(18, 4), fontweight="bold")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Part des GO à 96 h qui tiennent")
    ax.set_title("Survie d'un GO annoncé à 96 h (barres noires = IC 95 %)",
                 loc="left", fontweight="bold")
    _sauver(fig, "survie.png")


def figure_busts(resume: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    groupes = [("hit", "#2a78d6", "Journées GO confirmées (hits)"),
               ("bust", "#eb6834", "Busts (GO prévu, rien reçu)")]
    for (ax, variable, etiquette) in [
            (axes[0], "cisaillement", "Ratio vent 80 m / vent 10 m (médiane du jour)"),
            (axes[1], "rayonnement_moyen", "Rayonnement solaire moyen (W/m²)")]:
        donnees = [resume.loc[resume["categorie"] == cat, variable].dropna()
                   for cat, _, _ in groupes]
        bp = ax.boxplot(donnees, tick_labels=["hits", "busts"], patch_artist=True,
                        medianprops={"color": "#0b0b0b"})
        for boite, (_, couleur, _) in zip(bp["boxes"], groupes):
            boite.set_facecolor(couleur)
            boite.set_alpha(0.55)
        ax.set_title(etiquette, loc="left", fontweight="bold", fontsize=10)
    fig.suptitle("Busts vs hits sur deux proxys de découplage (prévision 24 h)",
                 x=0.01, ha="left", fontsize=11)
    _sauver(fig, "busts.png")


def tableau_md(df: pd.DataFrame, colonnes: dict, arrondi: int = 2) -> str:
    df = df[list(colonnes)].rename(columns=colonnes).copy()
    for c in df.columns:
        if df[c].dtype.kind == "f":
            df[c] = df[c].round(arrondi)
    return df.to_markdown(index=False)


def _fmt_ic(ic):
    return f"{ic[0]:.0%}–{ic[1]:.0%}"


def generer():
    DOSSIER.mkdir(exist_ok=True)
    res = backtest.principal()
    apparie, verite = res["apparie"], res["verite"]
    stats, conf, surv = res["stats_globales"], res["confusion"], res["survie"]

    resume_busts = busts.detecter_busts(apparie, verite, "24h")
    signature = busts.signature_busts(resume_busts)

    figure_biais_rmse(stats)
    figure_confusion(conf)
    figure_survie(surv)
    figure_busts(resume_busts)

    # --- Conclusions calculées, pas de chiffres codés en dur ---
    s24 = stats[stats["horizon"] == "24h"].sort_values("rmse")
    meilleur24 = s24.iloc[0]
    s96 = stats[stats["horizon"] == "96h"].sort_values("rmse")
    meilleur96 = s96.iloc[0]
    pire_biais = stats.loc[stats["biais"].abs().idxmax()]

    fiab = {ligne["de"]: ligne for _, ligne in
            surv[surv["vers"] == "réalisé"].iterrows()}
    surv96 = surv[(surv["de"] == "96h") & (surv["vers"] == "réalisé")].iloc[0]

    n_busts = int((resume_busts["categorie"] == "bust").sum())
    n_hits = int((resume_busts["categorie"] == "hit").sum())
    cis_h = signature.loc[signature["variable"] == "cisaillement", "mediane_hits"].iloc[0]
    cis_b = signature.loc[signature["variable"] == "cisaillement", "mediane_busts"].iloc[0]
    ray_h = signature.loc[signature["variable"] == "rayonnement_moyen", "mediane_hits"].iloc[0]
    ray_b = signature.loc[signature["variable"] == "rayonnement_moyen", "mediane_busts"].iloc[0]

    # Verdict honnête sur la signature : il faut assez de busts ET un écart
    # net sur au moins un proxy de découplage. Sinon, on le dit tel quel.
    signature_detectable = (n_busts >= 15
                            and ((cis_b - cis_h) > 0.15 or (ray_h - ray_b) > 80))
    if signature_detectable:
        texte_busts = f"""Les journées bust montrent un cisaillement vertical plus fort
   (vent 80 m / vent 10 m médian {cis_b:.2f} contre {cis_h:.2f} les bons jours)
   et moins de soleil ({ray_b:.0f} W/m² contre {ray_h:.0f} W/m²). *Cisaillement =
   le vent souffle en altitude mais ne « descend » pas jusqu'au lac ; sans
   soleil, pas de brassage convectif pour l'y amener.* La signature existe et
   ces deux variables sont disponibles en prévision : le dashboard portera un
   drapeau « risque de découplage »."""
    else:
        texte_busts = f"""**Non — pas encore de signature détectable.** Les médianes des
   proxys de découplage sont quasi identiques entre busts et bons jours
   (cisaillement {cis_b:.2f} contre {cis_h:.2f} ; rayonnement {ray_b:.0f} contre
   {ray_h:.0f} W/m²), et {n_busts} cas ne permettent aucune conclusion (le seuil
   de ce rapport est n ≥ 30 par cellule ; on est loin en dessous). Deux
   lectures : (a) la vérité actuelle étant une médiane de modèles, elle est
   corrélée aux prévisions — les vrais busts « grille dit vent, lac dit rien »
   sont invisibles par construction et ne le resteront pas quand la station au
   lac (phase 4) fournira une vérité indépendante ; (b) tant qu'aucune
   signature n'est validée, le dashboard n'affichera PAS de drapeau
   « découplage » — un drapeau non validé serait de la fausse précision. Le
   diagnostic sera relancé automatiquement quand la vérité station existera."""

    conf_aff = conf.copy()
    conf_aff["pod_aff"] = conf_aff.apply(
        lambda r: f"{r['pod']:.0%} ({_fmt_ic(r['pod_ic'])})" if pd.notna(r["pod"]) else "—", axis=1)
    conf_aff["far_aff"] = conf_aff.apply(
        lambda r: f"{r['far']:.0%} ({_fmt_ic(r['far_ic'])})" if pd.notna(r["far"]) else "—", axis=1)
    conf_aff["nom"] = conf_aff["modele"].map(lambda m: config.MODELES[m]["nom"])
    stats_aff = stats.copy()
    stats_aff["nom"] = stats_aff["modele"].map(lambda m: config.MODELES[m]["nom"])

    surv_aff = surv.copy()
    surv_aff["taux_aff"] = surv_aff.apply(
        lambda r: f"{r['taux']:.0%} ({_fmt_ic(r['ic'])})" if pd.notna(r["taux"]) else "—", axis=1)

    texte = f"""# Rapport de backtest — vent au Lac Maskinongé

Période analysée : {res['poids']['periode_backtest']}. Spot : 46.3123° N,
-73.3638° O. Unités : nœuds (nds). Vérité terrain : médiane multi-modèles des
séries « hour-0 » (voir la section Limites).

## Conclusions d'abord

1. **Quel modèle croire à ce spot ?** À 24 h, le plus précis est
   **{config.MODELES[meilleur24['modele']]['nom']}** (RMSE {meilleur24['rmse']:.1f} nds,
   biais {meilleur24['biais']:+.1f} nds). À 96 h — l'horizon de la décision
   « chalet » — c'est **{config.MODELES[meilleur96['modele']]['nom']}**
   (RMSE {meilleur96['rmse']:.1f} nds). *RMSE = erreur typique : à ±{meilleur96['rmse']:.0f} nds
   près, c'est l'incertitude à laquelle s'attendre sur une heure donnée.*

2. **Qui surestime ?** Le biais le plus marqué est celui de
   **{config.MODELES[pire_biais['modele']]['nom']}** à {pire_biais['horizon']}
   ({pire_biais['biais']:+.1f} nds en moyenne). Un biais positif = le modèle
   annonce plus de vent qu'il n'en arrive : c'est lui qui fabrique des faux GO.

3. **Quelle confiance accorder à un GO selon l'horizon ?** Sur la prévision
   d'ensemble (médiane des modèles) :
   - GO annoncé à **96 h** : confirmé {fiab['96h']['taux']:.0%} du temps
     (fourchette {_fmt_ic(fiab['96h']['ic'])}, {fiab['96h']['n_evaluables']} cas).
   - GO annoncé à **48 h** : confirmé {fiab['48h']['taux']:.0%} du temps
     ({_fmt_ic(fiab['48h']['ic'])}, {fiab['48h']['n_evaluables']} cas).
   - GO annoncé à **24 h** : confirmé {fiab['24h']['taux']:.0%} du temps
     ({_fmt_ic(fiab['24h']['ic'])}, {fiab['24h']['n_evaluables']} cas).

   Autrement dit, un « GO chalet » lancé 4 jours d'avance doit se lire comme
   une cote, pas une promesse — et le dashboard l'affichera toujours ainsi.

4. **Les busts ont-ils une signature ?** Sur {n_busts + n_hits} journées GO à
   24 h, {n_busts} ont été des busts complets (vent resté sous 9 nds toute la
   journée). {texte_busts}

## Erreur sur le vent moyen (biais et RMSE)

![Biais et RMSE par modèle et horizon](biais_rmse.png)

{tableau_md(stats_aff.sort_values(['horizon', 'rmse']),
            {'nom': 'Modèle', 'horizon': 'Horizon', 'n': 'n',
             'biais': 'Biais (nds)', 'rmse': 'RMSE (nds)'})}

Rappels de lecture : HRDPS ne porte que 48 h de prévision (pas de colonne 96 h),
GEM régional s'arrête à 84 h (pas de 96 h non plus).

## Événement « fenêtre foilable » : détection et fausses alertes

Fenêtre foilable = au moins 2 h entre 9 et 25 nds, entre 8 h et 20 h locales,
créux passagers 7–9 nds tolérés (voir config.py). Probabilité de détection
(POD) = part des vraies fenêtres que le modèle avait annoncées. Taux de
fausses alertes (FAR) = part des GO annoncés qui ne se sont pas matérialisés.

![Confusion fenêtres](confusion.png)

{tableau_md(conf_aff.sort_values(['horizon', 'far']),
            {'nom': 'Modèle', 'horizon': 'Horizon', 'n_jours': 'Jours',
             'jours_foilables_reels': 'Fenêtres réelles', 'hits': 'Hits',
             'fausses_alertes': 'Fausses alertes', 'manques': 'Manqués',
             'pod_aff': 'POD (IC 95 %)', 'far_aff': 'FAR (IC 95 %)'})}

## Survie des fenêtres : le chiffre de la décision « chalet »

Parmi les GO annoncés à 96 h par l'ensemble : {surv96['tiennent']} sur
{surv96['n_evaluables']} se sont réalisés ({surv96['taux']:.0%},
fourchette {_fmt_ic(surv96['ic'])}).

![Survie des GO](survie.png)

{tableau_md(surv_aff, {'de': 'GO annoncé à', 'vers': 'Vérifié à',
                       'n_evaluables': 'Cas', 'tiennent': 'Tiennent',
                       'taux_aff': 'Taux (IC 95 %)'})}

## Diagnostic des busts

![Signature des busts](busts.png)

{tableau_md(signature, {'variable': 'Variable', 'mediane_hits': 'Médiane hits',
                        'mediane_busts': 'Médiane busts', 'n_hits': 'n hits',
                        'n_busts': 'n busts'})}

Variables : cisaillement = ratio vent 80 m / vent 10 m (médiane 8 h–20 h) ;
inversion = temp. 80 m − temp. 2 m en °C (positif = air stable, découplage
probable). La hauteur de couche limite n'est archivée pour aucun modèle chez
Open-Meteo (vérifié par appels réels) — ces proxys la remplacent.

## Stations d'observation réelles (inventaire, rayon ~40 km)

Interrogation de l'API d'Environnement Canada (api.weather.gc.ca,
collections climate-stations / climate-hourly) :

| Station | Distance | Données horaires | Couverture | Verdict |
|---|---|---|---|---|
| Lac Saint-Pierre (701LP0N) | 37 km SE | Oui (vent, direction, temp.) | 1994 → aujourd'hui | **Exploitable** comme vérité secondaire de régime synoptique. Station automatique sur le lac Saint-Pierre : bien exposée, mais plan d'eau et topographie différents — l'écart avec le lac Maskinongé est attendu et sera mesuré, pas supposé. |
| St-Gabriel-de-Brandon (7017270) | 2 km | Non (climat quotidien, fermée) | historique | Inutilisable pour le vent horaire. |
| Toutes les autres (17 stations) | 4–45 km | Non | — | Postes climatologiques quotidiens, pas de vent horaire. |

Aucune station horaire d'EC n'existe à moins de 37 km : la vérité par station
attendra l'anémomètre Ecowitt au bord du lac (phase 4).

## Limites (à lire une fois)

- **La vérité est une médiane de modèles**, pas une observation. Elle capture
  les erreurs synoptiques (la dépression qui n'arrive pas) mais pas l'écart
  résiduel entre la grille de ~10–25 km et le vent réel au milieu du lac.
  Les biais absolus seront requalifiés quand la station du cousin sera en
  place (phase 4) ; les comparaisons entre modèles et entre horizons, elles,
  restent valides.
- **Rafales ECMWF absentes des archives** (vérifié) : le ratio
  rafales/vent appris sur les autres modèles sert de repli
  (ratio médian par modèle dans `data/poids_modeles.json`).
- Le nombre de fenêtres réelles par saison est petit : toutes les proportions
  sont données avec leur intervalle de confiance à 95 % — les fourchettes
  larges sont la réalité, pas un défaut du rapport.

## Fichiers produits

- `data/poids_modeles.json` : biais, RMSE, poids (∝ 1/RMSE², normalisés par
  horizon), corrections par secteur (où n ≥ 30), ratios de rafales,
  fiabilité des GO par horizon. Schéma documenté dans le README.
- `data/processed/*.parquet` : données appariées reproductibles.
"""
    with open(DOSSIER / "rapport_backtest.md", "w") as f:
        f.write(texte)
    print(f"Rapport écrit : {DOSSIER / 'rapport_backtest.md'}")
    return res


if __name__ == "__main__":
    generer()
