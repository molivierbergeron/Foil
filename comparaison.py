"""Prépare docs/comparaison.json : les modèles vus côte à côte, deux étalons.

Cette vue existe pour répondre à une question que le dashboard principal ne
pose pas : « à qui ai-je affaire ? ». Elle met en regard, pour chaque modèle
et chaque horizon :

- ce qu'il vaut contre une VRAIE MESURE (anémomètre de Lac Saint-Pierre) ;
- ce qu'il vaut contre le CONSENSUS des modèles, l'étalon qui sert
  réellement à calculer les poids en service ;
- le poids qu'il reçoit aujourd'hui.

Les deux colonnes ne racontent pas la même histoire, et c'est tout l'intérêt :
un modèle peut être premier contre le consensus et quatrième contre la
réalité. Voir cet écart, c'est voir la limite du calibrage actuel.

Ce module ne modifie rien : il lit et publie un JSON. Le fichier est
régénéré par le cron quotidien et lu par docs/comparaison.js.

    python3 comparaison.py            # -> docs/comparaison.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import config
import verification_croisee
import versions

SORTIE = Path("docs/comparaison.json")
SCHEMA = 1


def _officiel(poids: dict, modele: str, horizon: str) -> dict | None:
    """Ce que le modèle en service dit de ce modèle, à cet horizon."""
    infos = poids.get("modeles", {}).get(modele, {}).get("horizons", {}).get(horizon)
    if infos is None:
        return None
    return {"biais": infos.get("biais_nds"), "rmse": infos.get("rmse_nds"),
            "poids": infos.get("poids"), "n": infos.get("n")}


def _rangs(entrees: list, cle: str) -> dict:
    """Rang par RMSE croissant (1 = le meilleur), en ignorant les absents."""
    valides = [e for e in entrees if e.get(cle) and e[cle].get("rmse") is not None]
    ordonnes = sorted(valides, key=lambda e: e[cle]["rmse"])
    return {e["modele"]: i + 1 for i, e in enumerate(ordonnes)}


def construire() -> dict:
    poids = json.loads(Path(config.FICHIER_POIDS).read_text())
    croise = verification_croisee.charger()
    scores = verification_croisee.scores(croise)

    horizons = {}
    for horizon in config.HORIZONS:
        entrees = []
        for modele, info in config.MODELES.items():
            officiel = _officiel(poids, modele, horizon)
            ligne = scores[(scores["modele"] == modele)
                           & (scores["horizon"] == horizon)] if not scores.empty else None
            reel = None
            if ligne is not None and not ligne.empty:
                r = ligne.iloc[0]
                # NaN n'est pas du JSON valide : la corrélation indéfinie
                # (échantillon trop mince) devient null, pas un chiffre.
                correlation = None if r["correlation"] != r["correlation"] else round(
                    float(r["correlation"]), 3)
                reel = {"biais": round(float(r["biais_nds"]), 2),
                        "rmse": round(float(r["rmse_nds"]), 2),
                        "correlation": correlation, "n": int(r["n"])}
            if officiel is None and reel is None:
                continue  # modèle sans portée à cet horizon (ex. HRDPS à 96 h)
            entrees.append({"modele": modele, "nom": info["nom"],
                            "reel": reel, "officiel": officiel})

        rangs_reels = _rangs(entrees, "reel")
        rangs_officiels = _rangs(entrees, "officiel")
        for e in entrees:
            if e["reel"]:
                e["reel"]["rang"] = rangs_reels.get(e["modele"])
            if e["officiel"]:
                e["officiel"]["rang"] = rangs_officiels.get(e["modele"])
        entrees.sort(key=lambda e: (e["reel"] or {}).get("rang")
                     or (e["officiel"] or {}).get("rang") or 99)
        horizons[horizon] = entrees

    registre = versions.registre()
    periode = None
    if not croise.empty:
        periode = {"debut": str(croise["date_locale"].min()),
                   "fin": str(croise["date_locale"].max()),
                   "jours": int(croise["date_locale"].nunique()),
                   "paires": int(len(croise))}

    return {
        "schema_version": SCHEMA,
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "station": {k: config.STATION_CROISEE[k]
                    for k in ("nom", "id", "distance_km")},
        "spot": {"latitude": config.LATITUDE, "longitude": config.LONGITUDE},
        "periode": periode,
        "horizons": horizons,
        "modele_actif": poids.get("version_modele"),
        "versions": [
            {"version": v["version"], "origine": v["origine"],
             "cree_le": v["cree_le"], "genere_le": v.get("genere_le"),
             "donnees_jusqu_au": v.get("donnees_jusqu_au"),
             "n_apparie": v.get("n_apparie"), "notes": v.get("notes", "")}
            for v in registre["versions"]
        ],
        "activations": registre["activations"][-10:],
    }


def principal() -> int:
    donnees = construire()
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps(donnees, indent=1, ensure_ascii=False) + "\n")
    periode = donnees["periode"]
    if periode:
        print(f"-> {SORTIE} ({periode['paires']:,} paires, "
              f"{periode['jours']} jours)".replace(",", " "))
    else:
        print(f"-> {SORTIE} (aucune donnée croisée accumulée pour l'instant)")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
