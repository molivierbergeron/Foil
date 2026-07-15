// Tests de la logique JS du dashboard (mêmes cas que tests/test_fenetre.py)
const { fenetresDuJour, secteurDe, horizonPour } = require("../docs/app.js");
const poids = require("../docs/poids_modeles.json");
const sport = poids.sport;

const egal = (a, b, nom) => {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${nom}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
  }
  console.log("OK", nom);
};

egal(fenetresDuJour([3, 3, 10, 12, 11, 3], sport), [[2, 5]], "fenetre_simple");
egal(fenetresDuJour([3, 12, 3], sport), [], "trop_courte");
egal(fenetresDuJour([10, 6, 12], sport), [[0, 3]], "creux_marginal_tolere");
egal(fenetresDuJour([10, 11, 6, 6, 12, 13], sport), [[0, 2], [4, 6]], "deux_creux_coupent");
egal(fenetresDuJour([10, 6, 6, 12, 13], sport), [[3, 5]], "deux_creux_coupent_2");
egal(fenetresDuJour([10, 4.5, 12], sport), [], "sous_plancher");
egal(fenetresDuJour([10, 20, 12], sport), [], "surtoile");
egal(fenetresDuJour([6, 10, 11, 6], sport), [[1, 3]], "marginales_bords");
egal(fenetresDuJour([10, null, 12], sport), [], "null_coupe");
egal(secteurDe(359), "N", "secteur_nord");
egal(secteurDe(337.4), "NO", "secteur_frontiere");
egal(horizonPour("gem_hrdps_continental", 3, poids), "24h", "horizon_repli_hrdps");
egal(horizonPour("gem_global", 3, poids), "96h", "horizon_96h");
egal(horizonPour("gem_regional", 4, poids), "48h", "horizon_repli_regional");
console.log("Tous les tests dashboard passent.");
