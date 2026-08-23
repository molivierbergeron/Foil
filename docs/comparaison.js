/* Vue « les modèles vs la réalité ».
 *
 * Lit comparaison.json (produit par comparaison.py, régénéré chaque jour par
 * le cron) et affiche, pour chaque échéance, chaque modèle noté DEUX fois :
 * contre l'anémomètre de Lac Saint-Pierre, et contre le consensus des modèles
 * qui sert à calculer les poids en service.
 *
 * Aucune dépendance : le dossier docs/ doit rester copiable tel quel.
 */
"use strict";

const VERSION_UI = "1.2.0";

function el(balise, classe, texte) {
  const n = document.createElement(balise);
  if (classe) n.className = classe;
  if (texte !== undefined) n.textContent = texte;
  return n;
}

/* Virgule décimale : la page est en français, et les chiffres y sont lus,
   pas copiés dans un tableur. */
function nombre(v, decimales = 2) {
  return v === null || v === undefined ? "—" : v.toFixed(decimales).replace(".", ",");
}

function signe(v, decimales = 2) {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(decimales).replace(".", ",");
}

/* Une carte par modèle plutôt qu'un tableau : le fait à voir est le CONTRASTE
   entre les deux notations, et sur un téléphone un tableau à sept colonnes
   pousse la seconde hors écran — il faudrait scroller pour voir précisément
   ce que la page existe pour montrer. Les deux colonnes de la carte tiennent
   côte à côte à 430 px. */
function colonneScore(titre, classe, lignes) {
  const col = el("div", `colonne-score ${classe}`);
  col.appendChild(el("span", "titre-score", titre));
  for (const [libelle, valeur, mod] of lignes) {
    const ligne = el("p", "ligne-score");
    ligne.appendChild(el("span", "libelle-score", libelle));
    ligne.appendChild(el("span", `valeur-score${mod ? " " + mod : ""}`, valeur));
    col.appendChild(ligne);
  }
  return col;
}

function carteModele(e, bornes) {
  const carte = el("div", "carte carte-modele");
  const entete = el("div", "entete-modele");
  entete.appendChild(el("span", `pastille m-${e.modele}`));
  entete.appendChild(el("span", "nom-modele", e.nom));
  carte.appendChild(entete);

  /* Barre relative aux AUTRES modèles de la même échéance, pas à zéro : à
     24 h tous tiennent entre 4,4 et 5,3 nds, donc une barre partant de zéro
     les rendrait tous identiques et ne montrerait rien. Ici le meilleur reste
     un court trait, le pire remplit la ligne. */
  if (e.reel && bornes.etendue > 0) {
    const barreErreur = el("div", "barre");
    const remplie = el("span", "barre-remplie");
    const part = 12 + ((e.reel.rmse - bornes.min) / bornes.etendue) * 88;
    remplie.style.width = `${part}%`;
    barreErreur.appendChild(remplie);
    carte.appendChild(barreErreur);
  }

  const duo = el("div", "duo-scores");
  duo.appendChild(e.reel
    ? colonneScore("Contre la vraie mesure", "score-reel", [
        ["rang", `${e.reel.rang}ᵉ`, "gros"],
        ["erreur typique", `${nombre(e.reel.rmse)} nds`],
        ["biais", `${signe(e.reel.biais)} nds`],
        ["corrélation", e.reel.correlation == null ? "—" : nombre(e.reel.correlation)],
      ])
    : colonneScore("Contre la vraie mesure", "score-reel",
                   [["", "pas encore mesuré", "vide"]]));
  duo.appendChild(e.officiel
    ? colonneScore("Contre le consensus", "score-consensus", [
        ["rang", `${e.officiel.rang}ᵉ`, "gros"],
        ["erreur typique", `${nombre(e.officiel.rmse)} nds`],
        ["biais", `${signe(e.officiel.biais)} nds`],
        ["poids reçu", e.officiel.poids == null ? "—"
          : `${Math.round(e.officiel.poids * 100)} %`, "gras"],
      ])
    : colonneScore("Contre le consensus", "score-consensus",
                   [["", "hors portée à cette échéance", "vide"]]));
  carte.appendChild(duo);

  /* Le désaccord entre les deux étalons est le fait à retenir, mais il touche
     la majorité des modèles : une pastille d'alerte sur deux cartes sur trois
     n'alerterait de rien. On dit donc ce que l'écart SIGNIFIE, en une ligne
     sobre, et on ne colore que les cas francs. */
  if (e.reel && e.officiel) {
    const ecart = e.officiel.rang - e.reel.rang;
    if (Math.abs(ecart) >= 2) {
      const sens = ecart > 0 ? "sous-estime" : "surestime";
      const rangs = Math.abs(ecart) === 1 ? "1 rang" : `${Math.abs(ecart)} rangs`;
      const note = el("p", `note-ecart${Math.abs(ecart) >= 3 ? " fort" : ""}`,
                      `Le consensus le ${sens} de ${rangs}.`);
      carte.appendChild(note);
    }
  }
  return carte;
}

function blocHorizon(horizon, entrees) {
  const bloc = el("div", "bloc-horizon");
  bloc.appendChild(el("h3", null, `Échéance ${horizon}`));
  const erreurs = entrees.filter((e) => e.reel).map((e) => e.reel.rmse);
  const bornes = erreurs.length
    ? { min: Math.min(...erreurs), etendue: Math.max(...erreurs) - Math.min(...erreurs) }
    : { min: 0, etendue: 0 };
  const liste = el("div", "cartes");
  for (const e of entrees) liste.appendChild(carteModele(e, bornes));
  bloc.appendChild(liste);
  return bloc;
}

function resumeEcart(donnees) {
  const h24 = donnees.horizons["24h"] || [];
  const avecDeux = h24.filter((e) => e.reel && e.officiel);
  if (avecDeux.length < 2) {
    return "Le classement contre la vraie mesure apparaîtra ici dès que "
      + "quelques semaines d'observations seront accumulées.";
  }
  const parReel = [...avecDeux].sort((a, b) => a.reel.rang - b.reel.rang);
  const parOff = [...avecDeux].sort((a, b) => a.officiel.rang - b.officiel.rang);
  const meilleurReel = parReel[0];
  const meilleurOff = parOff[0];
  const erreurs = avecDeux.map((e) => e.reel.rmse);
  const ecartModeles = Math.max(...erreurs) - Math.min(...erreurs);

  let texte = `À 24 h, le modèle le plus juste contre la vraie mesure est `
    + `${meilleurReel.nom} (erreur ${nombre(meilleurReel.reel.rmse)} nds). `
    + `Contre le consensus, c'est ${meilleurOff.nom}`;
  texte += meilleurReel.modele === meilleurOff.modele
    ? " — les deux étalons sont d'accord."
    : `, qui n'arrive que ${meilleurOff.reel.rang}ᵉ contre la mesure.`;
  texte += ` Entre le meilleur et le pire modèle, l'écart d'erreur est de `
    + `${nombre(ecartModeles)} nds : c'est ce que vaut le fait de bien `
    + `pondérer les modèles.`;
  return texte;
}

function rendreVersions(donnees) {
  const liste = el("div", "cartes");
  for (const v of [...donnees.versions].reverse()) {
    const carte = el("div", "carte carte-version");
    const actif = v.version === donnees.modele_actif;
    const titre = el("h3", null, (actif ? "→ " : "") + v.version);
    if (actif) titre.classList.add("actif");
    carte.appendChild(titre);
    carte.appendChild(el("p", "aide", `Origine : ${v.origine}`));
    if (v.donnees_jusqu_au) {
      carte.appendChild(el("p", "aide",
        `Calibrée sur des données jusqu'au ${v.donnees_jusqu_au}`
        + (v.n_apparie ? ` (${v.n_apparie.toLocaleString("fr-CA")} lignes)` : "")));
    }
    carte.appendChild(el("p", "aide", `Créée le ${v.cree_le.slice(0, 10)}`));
    liste.appendChild(carte);
  }
  return liste;
}

async function demarrer() {
  const etat = document.getElementById("etat");
  try {
    const donnees = await (await fetch("comparaison.json")).json();

    document.getElementById("nom-station").textContent = donnees.station.nom;
    document.getElementById("distance-station").textContent =
      donnees.station.distance_km;
    document.getElementById("ecart-cle").textContent = resumeEcart(donnees);

    const conteneur = document.getElementById("horizons");
    for (const [horizon, entrees] of Object.entries(donnees.horizons)) {
      if (entrees.length) conteneur.appendChild(blocHorizon(horizon, entrees));
    }

    document.getElementById("texte-limites").textContent =
      `${donnees.station.nom} n'est pas le Lac Maskinongé : c'est un plan `
      + `d'eau bien plus ouvert, à ${donnees.station.distance_km} km, où le `
      + `vent est plus fort. Les biais mesurés là-bas sont ceux de ce `
      + `site-là et ne se transplantent pas au lac. Ce qui se transporte `
      + `raisonnablement, c'est le classement et la capacité à suivre le `
      + `passage réel des systèmes. Rien de cette page n'influence les `
      + `verdicts : c'est un banc d'essai, pas le moteur.`;

    document.getElementById("historique").appendChild(rendreVersions(donnees));

    const periode = donnees.periode;
    document.getElementById("fraicheur-comparaison").textContent = periode
      ? `Mesuré sur ${periode.debut} → ${periode.fin} `
        + `(${periode.jours} jours, ${periode.paires.toLocaleString("fr-CA")} `
        + `paires prévision/observation). Page générée le `
        + `${donnees.genere_le.slice(0, 10)}.`
      : `Aucune observation accumulée pour l'instant — le rattrapage `
        + `rétroactif n'a pas encore tourné. Les colonnes « vraie mesure » `
        + `se rempliront ensuite toutes seules, chaque jour.`;
    document.getElementById("versions").textContent =
      `Interface v${VERSION_UI} · modèle ${donnees.modele_actif ?? "non versionné"}`;

    etat.hidden = true;
    for (const id of ["explication", "tableaux", "limites", "historique"]) {
      document.getElementById(id).hidden = false;
    }
  } catch (err) {
    etat.textContent = `Impossible de charger la comparaison (${err.message}).`;
  }
}

demarrer();
