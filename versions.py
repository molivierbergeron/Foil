"""Versionnage des modèles calibrés : historique, retour arrière, comparaison.

Un « modèle » ici, c'est un jeu de poids complet (biais par modèle × horizon,
poids ∝ 1/RMSE², corrections par secteur, ratios de rafales, fiabilité des GO)
— autrement dit un fichier poids_modeles.json. C'est lui qui transforme six
prévisions brutes en un verdict, donc c'est lui qu'il faut pouvoir archiver,
restaurer et comparer.

    data/modeles/registre.json          index + version active + activations
    data/modeles/<version>/poids.json   le jeu de poids figé
    data/poids_modeles.json             copie de travail = version active
    docs/poids_modeles.json             copie lue par le dashboard

data/poids_modeles.json n'est jamais supprimé ni déplacé : tout le code
existant continue de le lire. Le registre ajoute l'historique par-dessus.

Usage :
    python3 versions.py --lister
    python3 versions.py --comparer v2-2026-08-03 v3-2026-08-17
    python3 versions.py --activer v2-2026-08-03 --raison "v3 sur-prévoit en SO"
"""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import config

DOSSIER = Path("data/modeles")
REGISTRE = DOSSIER / "registre.json"
COPIE_DASHBOARD = Path("docs/poids_modeles.json")
SCHEMA_REGISTRE = 1


# ------------------------------------------------------------------ registre

def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empreinte(poids: dict) -> str:
    """Empreinte du CONTENU calibré, hors métadonnées de génération.

    Deux recalibrages qui aboutissent aux mêmes chiffres donnent la même
    empreinte même si genere_le diffère : inutile d'empiler des versions
    identiques semaine après semaine.
    """
    substance = {c: poids.get(c) for c in
                 ("modeles", "fiabilite_go_par_horizon", "confusion_par_modele",
                  "ratio_rafales_defaut", "sport", "truth_source", "verite")}
    brut = json.dumps(substance, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(brut.encode()).hexdigest()[:16]


def _borne_depuis_periode(poids: dict) -> str | None:
    """Dernier jour de calibration déduit de periode_backtest, si possible.

    Format produit par backtest.calculer_poids : « 2024-05-01 à 2026-07-12
    (mai-octobre) ». Sert à l'amorçage, pour qu'une version importée avant le
    versionnage puisse quand même servir de référence hors échantillon.
    """
    periode = poids.get("periode_backtest") or ""
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", periode)
    return dates[-1] if dates else None


def _registre_vide() -> dict:
    return {"schema_version": SCHEMA_REGISTRE, "actif": None,
            "versions": [], "activations": []}


def registre() -> dict:
    """Lit le registre, en l'amorçant depuis le fichier de poids courant.

    Amorçage : un dépôt qui tourne déjà a un data/poids_modeles.json sans
    version. On l'importe comme v1 plutôt que de le laisser hors historique.
    """
    if REGISTRE.exists():
        return json.loads(REGISTRE.read_text())

    reg = _registre_vide()
    courant = Path(config.FICHIER_POIDS)
    if courant.exists():
        poids = json.loads(courant.read_text())
        reg = _ajouter(reg, poids, origine="import-initial",
                       donnees_jusqu_au=_borne_depuis_periode(poids),
                       notes="Poids déjà en production, importés à la mise en "
                             "place du versionnage. Borne de calibration "
                             "déduite de periode_backtest.")
        _ecrire_registre(reg)
        # Réécrit les copies en service pour y apposer version_modele. Seul
        # moment où une lecture du registre écrit : on vient de le créer, et
        # sans ça le dashboard resterait sans version jusqu'au prochain
        # recalibrage (une semaine plus tard).
        _publier(reg["actif"])
    return reg


def _ecrire_registre(reg: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    REGISTRE.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")


def _prochain_id(reg: dict, poids: dict) -> str:
    numero = len(reg["versions"]) + 1
    jour = poids.get("genere_le") or datetime.now(timezone.utc).date().isoformat()
    return f"v{numero}-{jour}"


def _ajouter(reg: dict, poids: dict, origine: str, donnees_jusqu_au=None,
             n_apparie=None, metriques=None, notes="") -> dict:
    """Écrit une nouvelle version dans le registre et l'active. Modifie reg."""
    version = _prochain_id(reg, poids)
    dossier = DOSSIER / version
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "poids.json").write_text(
        json.dumps(poids, indent=2, ensure_ascii=False) + "\n")

    reg["versions"].append({
        "version": version,
        "cree_le": _maintenant(),
        "origine": origine,
        "empreinte": empreinte(poids),
        "genere_le": poids.get("genere_le"),
        "periode_backtest": poids.get("periode_backtest"),
        # Dernier jour de données ayant servi à CALIBRER cette version : c'est
        # lui qui définit ce qui est hors échantillon lors d'une comparaison.
        "donnees_jusqu_au": str(donnees_jusqu_au) if donnees_jusqu_au else None,
        "n_apparie": n_apparie,
        "verite": poids.get("verite", {"version": poids.get("truth_source")}),
        "modeles_prevision": sorted(poids.get("modeles", {})),
        "metriques_validation": metriques,
        "notes": notes,
    })
    reg["actif"] = version
    reg["activations"].append(
        {"version": version, "le": _maintenant(), "raison": f"création ({origine})"})
    return reg


def meta(version: str) -> dict:
    for v in registre()["versions"]:
        if v["version"] == version:
            return v
    connues = [v["version"] for v in registre()["versions"]]
    raise KeyError(f"Version inconnue : {version}. Connues : {connues}")


def charger_poids(version: str) -> dict:
    meta(version)  # valide l'existence, message d'erreur utile
    return json.loads((DOSSIER / version / "poids.json").read_text())


def actif() -> str | None:
    return registre()["actif"]


# -------------------------------------------------------- écriture / bascule

def _publier(version: str) -> None:
    """Installe une version archivée comme copie de travail + copie dashboard.

    Les copies publiées portent un champ `version_modele` que l'archive n'a
    pas : l'archive doit rester le contenu calibré nu (son empreinte ne doit
    pas dépendre de son propre identifiant), tandis que les copies en service
    doivent pouvoir dire quelle version tourne — jusque dans le dashboard.
    """
    poids = json.loads((DOSSIER / version / "poids.json").read_text())
    poids["version_modele"] = version
    texte = json.dumps(poids, indent=2, ensure_ascii=False) + "\n"
    Path(config.FICHIER_POIDS).write_text(texte)
    if COPIE_DASHBOARD.parent.exists():
        COPIE_DASHBOARD.write_text(texte)


def enregistrer(poids: dict, origine: str, donnees_jusqu_au=None,
                n_apparie=None, metriques=None, notes="") -> str:
    """Archive un jeu de poids comme nouvelle version, et l'active.

    Si son contenu calibré est identique à la version active, rien n'est créé :
    on retourne la version existante. Évite d'empiler des doublons.
    """
    reg = registre()
    if reg["actif"]:
        try:
            if empreinte(charger_poids(reg["actif"])) == empreinte(poids):
                return reg["actif"]
        except (KeyError, FileNotFoundError):
            pass  # registre incohérent : on enregistre quand même

    reg = _ajouter(reg, poids, origine, donnees_jusqu_au, n_apparie,
                   metriques, notes)
    _ecrire_registre(reg)
    _publier(reg["actif"])
    return reg["actif"]


def republier_actif() -> str | None:
    """Réinstalle les copies de travail depuis la version active, sans bascule.

    Sert au recalibrage quand les poids candidats sont refusés : la copie
    dashboard a pu diverger (retour arrière non propagé, édition manuelle) et
    doit rester le reflet exact de la version active.
    """
    version = actif()
    if version:
        _publier(version)
    return version


def activer(version: str, raison: str = "") -> str:
    """Retour arrière : réinstalle une version archivée comme version active.

    L'historique n'est jamais réécrit — la bascule est ajoutée au journal des
    activations, donc « on est revenus à v2 le 20 août » reste lisible.
    """
    meta(version)
    reg = registre()
    reg["actif"] = version
    reg["activations"].append(
        {"version": version, "le": _maintenant(), "raison": raison or "bascule manuelle"})
    _ecrire_registre(reg)
    _publier(version)
    return version


# ------------------------------------------------------------- comparaison

def _fenetre_hors_echantillon(a: str, b: str) -> tuple[str | None, list[str]]:
    """Premier jour strictement postérieur aux données de calibration des deux.

    Retourne (date ou None, avertissements). None = au moins une des deux
    versions ne dit pas jusqu'où elle a été calibrée : la comparaison reste
    possible mais ne peut pas être déclarée hors échantillon.
    """
    avertissements = []
    bornes = []
    for v in (a, b):
        borne = meta(v).get("donnees_jusqu_au")
        if borne is None:
            avertissements.append(
                f"{v} ne déclare pas jusqu'à quand elle a été calibrée "
                "(version importée avant le versionnage)")
        else:
            bornes.append(borne)
    if len(bornes) < 2:
        return None, avertissements
    return max(bornes), avertissements


def comparer(a: str, b: str, jours: int | None = None,
             depuis: str | None = None) -> dict:
    """Compare deux versions sur des données appariées communes.

    Par défaut la fenêtre d'évaluation commence après la dernière donnée ayant
    servi à calibrer l'une OU l'autre — sinon la version la plus récemment
    calibrée serait jugée sur ses propres données d'entraînement et gagnerait
    d'office. `--depuis` ou `--jours` forcent une autre fenêtre, au prix d'un
    avertissement explicite.
    """
    import pandas as pd

    import backtest

    apparie, _ = backtest.charger_apparie_complet()
    dates = pd.to_datetime(apparie["date_locale"].astype(str))

    auto_depuis, avertissements = _fenetre_hors_echantillon(a, b)
    hors_echantillon = False
    if depuis is not None:
        borne = pd.Timestamp(depuis)
        if auto_depuis is not None and borne <= pd.Timestamp(auto_depuis):
            avertissements.append(
                f"--depuis {depuis} recouvre les données de calibration "
                f"(jusqu'au {auto_depuis}) : ce n'est PAS une comparaison "
                "hors échantillon")
        else:
            hors_echantillon = auto_depuis is not None
    elif jours is not None:
        borne = dates.max() - pd.Timedelta(days=jours)
        if auto_depuis is not None and borne <= pd.Timestamp(auto_depuis):
            avertissements.append(
                f"la fenêtre de {jours} jours remonte avant la fin de la "
                f"calibration ({auto_depuis}) : ce n'est PAS une comparaison "
                "hors échantillon")
        else:
            hors_echantillon = auto_depuis is not None
    elif auto_depuis is not None:
        borne = pd.Timestamp(auto_depuis)
        hors_echantillon = True
    else:
        borne = dates.max() - pd.Timedelta(days=60)
        avertissements.append(
            "aucune borne hors échantillon connue : repli sur les 60 derniers "
            "jours, à lire comme une comparaison indicative")

    test = apparie[dates > borne]

    resultat = {
        "a": a, "b": b,
        "fenetre_debut": str(borne.date()),
        "fenetre_fin": str(dates.max().date()) if len(dates) else None,
        "n_lignes": int(len(test)),
        "hors_echantillon": hors_echantillon,
        "avertissements": avertissements,
        "rmse": {}, "taux_go": {},
    }
    if test.empty:
        avertissements.append(
            "aucune donnée après la borne : il faut laisser passer des jours "
            "avant de pouvoir départager ces deux versions")
        return resultat

    for etiquette, version in (("a", a), ("b", b)):
        poids = charger_poids(version)
        resultat["rmse"][etiquette] = backtest.rmse_ensemble(test, poids)
        resultat["taux_go"][etiquette] = backtest.taux_go_ensemble(test, poids)

    ecarts = {h: resultat["rmse"]["b"][h] - resultat["rmse"]["a"][h]
              for h in resultat["rmse"]["a"] if h in resultat["rmse"]["b"]}
    resultat["ecart_rmse"] = ecarts
    resultat["verdict"] = _verdict(ecarts, resultat["n_lignes"])
    return resultat


def _verdict(ecarts: dict, n: int) -> str:
    if not ecarts:
        return "Aucun horizon comparable."
    moyen = sum(ecarts.values()) / len(ecarts)
    if n < 200:
        return (f"Échantillon trop mince ({n} lignes) pour conclure — "
                f"écart moyen {moyen:+.3f} nds, à confirmer.")
    if abs(moyen) < 0.05:
        return f"Match nul (écart moyen {moyen:+.3f} nds, sous le bruit)."
    gagnant = "B" if moyen < 0 else "A"
    return (f"{gagnant} est meilleure : écart moyen {moyen:+.3f} nds "
            f"(négatif = B réduit l'erreur), sur {n} lignes.")


# --------------------------------------------------------------------- CLI

def _afficher_liste() -> None:
    reg = registre()
    if not reg["versions"]:
        print("Aucune version enregistrée.")
        return
    entete_borne = "calibré jusqu'au"
    print(f"{'':2} {'version':22} {'origine':16} {entete_borne:17} "
          f"{'n':>7}  empreinte")
    for v in reg["versions"]:
        marque = "->" if v["version"] == reg["actif"] else "  "
        print(f"{marque} {v['version']:22} {v['origine']:16} "
              f"{str(v.get('donnees_jusqu_au') or '—'):17} "
              f"{str(v.get('n_apparie') or '—'):>7}  {v['empreinte']}")
    print(f"\nVersion active : {reg['actif']}")
    if reg["activations"]:
        print("Dernières bascules :")
        for act in reg["activations"][-5:]:
            print(f"  {act['le'][:16]}  {act['version']:22} {act['raison']}")


def _afficher_comparaison(r: dict) -> None:
    print(f"\nA = {r['a']}\nB = {r['b']}")
    etiquette = ("hors échantillon pour les deux versions"
                 if r["hors_echantillon"] else "PAS garantie hors échantillon")
    print(f"Fenêtre : {r['fenetre_debut']} → {r['fenetre_fin']} "
          f"({r['n_lignes']} lignes, {etiquette})")
    for a in r["avertissements"]:
        print(f"  ⚠ {a}")
    if not r["rmse"]:
        return

    print(f"\n{'horizon':8} {'RMSE A':>9} {'RMSE B':>9} {'écart':>9}   "
          f"{'GO conf. A':>18} {'GO conf. B':>18}")
    for h in config.HORIZONS:
        if h not in r["rmse"]["a"] or h not in r["rmse"]["b"]:
            continue
        ga, gb = r["taux_go"]["a"].get(h, {}), r["taux_go"]["b"].get(h, {})

        def fmt_go(g):
            if not g or g["n_go"] == 0:
                return f"{'— (0 GO)':>18}"
            return f"{g['taux']:.0%} [{g['ic95'][0]:.0%}-{g['ic95'][1]:.0%}] n={g['n_go']:<3}"

        print(f"{h:8} {r['rmse']['a'][h]:9.3f} {r['rmse']['b'][h]:9.3f} "
              f"{r['ecart_rmse'][h]:+9.3f}   {fmt_go(ga):>18} {fmt_go(gb):>18}")
    print(f"\n{r['verdict']}")
    print("Rappel : le RMSE mesure l'erreur en nœuds, le taux de GO confirmé "
          "mesure ce que voit l'utilisateur. Les deux peuvent diverger.")


def principal(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--lister", action="store_true",
                   help="historique des versions et version active")
    g.add_argument("--activer", metavar="VERSION",
                   help="retour arrière : réinstalle une version archivée")
    g.add_argument("--comparer", nargs=2, metavar=("A", "B"),
                   help="compare deux versions sur les données accumulées")
    p.add_argument("--raison", default="", help="note associée à --activer")
    p.add_argument("--jours", type=int,
                   help="--comparer : forcer une fenêtre des N derniers jours")
    p.add_argument("--depuis", metavar="AAAA-MM-JJ",
                   help="--comparer : forcer une date de début de fenêtre")
    args = p.parse_args(argv)

    if args.lister:
        _afficher_liste()
    elif args.activer:
        v = activer(args.activer, args.raison)
        print(f"Version active : {v}")
        print(f"Réinstallée dans {config.FICHIER_POIDS}"
              + (f" et {COPIE_DASHBOARD}" if COPIE_DASHBOARD.exists() else ""))
        print("Pense à committer : le dashboard lit la copie du dépôt.")
    else:
        _afficher_comparaison(comparer(*args.comparer, jours=args.jours,
                                       depuis=args.depuis))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
