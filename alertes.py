"""Alertes (phase 6) — PLACEHOLDER VOLONTAIREMENT NON IMPLÉMENTÉ.

Décision de conception : les verdicts structurés existent déjà —
`data/forecast.json` (écrasé chaque matin par job_quotidien.py) contient
`verdicts_ensemble` (GO/NO par jour + blocs) et la fiabilité par horizon.
Une alerte n'est donc qu'un CONSOMMATEUR de ce fichier : rien du pipeline
n'a besoin de changer pour l'activer.

Canal pressenti : ntfy.sh — topic public partageable avec le cousin, zéro
compte, une requête HTTP suffit :

    requests.post("https://ntfy.sh/<topic-choisi>",
                  data="GO demain : fenêtre 11 h-16 h, vent 12 nds".encode(),
                  headers={"Title": "Vent Lac Maskinongé", "Tags": "wind_face"})

Paramètres à décider AVEC l'utilisateur avant d'implémenter (ne pas deviner) :
- seuil de confiance pour alerter (ex. GO à >= 76 % seulement ? inclure les
  GO à 3-4 jours pour la décision chalet ?)
- horaires d'envoi (la veille au soir ? le matin 6 h ? les deux ?)
- anti-spam : une seule alerte par fenêtre, pas de répétition quotidienne
- canaux : ntfy seul, ou courriel aussi ; nom du topic (public!)
- alertes négatives ? (« le GO d'hier est tombé à NO » — probablement oui,
  c'est le taux de survie qui fait la valeur du système)

Brancher ensuite dans quotidien.yml, après job_quotidien.py :
    - run: python alertes.py
"""

if __name__ == "__main__":
    raise SystemExit(
        "alertes.py est un placeholder (phase 6) — lire la docstring : "
        "les paramètres doivent être décidés avec l'utilisateur avant "
        "d'implémenter.")
