/* Vue d'essai : le vent prévu par le modèle en service et par la proposition.
 *
 * Les deux jeux de poids sont appliqués aux MÊMES prévisions brutes, tirées en
 * direct d'Open-Meteo comme le dashboard. Toute différence affichée vient donc
 * uniquement de la calibration — jamais des données d'entrée, jamais de
 * l'heure de récupération.
 *
 * Cette page ne rend aucun verdict. Elle montre des nœuds, parce que c'est ce
 * qu'on peut confronter au lac.
 *
 * Aucune dépendance : docs/ doit rester copiable tel quel.
 */
"use strict";

const VERSION_UI = "1.4.0";

// Un modèle absent d'un jeu de poids ne vote simplement pas dans son
// ensemble (horizonPour renvoie null) : la page peut donc afficher côte à
// côte un actif à six membres et un candidat à sept.
const MODELES = ["gem_global", "gem_regional", "gem_hrdps_continental",
                 "gfs_hrrr", "ecmwf_ifs025", "gfs_global", "icon_global"];
const SECTEURS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
const JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const HEURE_DEBUT = 8, HEURE_FIN = 20;
// Seuil d'encadrement d'une heure. Mesuré sur les prévisions réelles, la
// repondération déplace le vent de ~0,15 nds en moyenne : un seuil à 1 nds
// n'aurait jamais rien encadré et la page aurait eu l'air cassée. À 0,5 on
// marque les heures où l'écart est au moins visible.
const SEUIL_ECART = 0.5;

function el(balise, classe, texte) {
  const n = document.createElement(balise);
  if (classe) n.className = classe;
  if (texte !== undefined) n.textContent = texte;
  return n;
}

const nb = (v, d = 1) =>
  v === null || v === undefined ? "—" : v.toFixed(d).replace(".", ",");

// ------------------------------------------------------------- corrections

function secteurDe(direction) {
  if (direction == null) return null;
  return SECTEURS[Math.floor(((direction + 22.5) % 360) / 45)];
}

function horizonPour(modele, decalageJour, poids) {
  const dispo = Object.keys(poids.modeles?.[modele]?.horizons ?? {});
  if (!dispo.length) return null;
  const souhaite = decalageJour <= 1 ? "24h" : decalageJour === 2 ? "48h" : "96h";
  if (dispo.includes(souhaite)) return souhaite;
  // Repli sur l'horizon archivé le plus long du modèle (ex. HRDPS -> 24h),
  // exactement comme le dashboard : sinon les deux vues divergeraient pour
  // une raison qui n'a rien à voir avec la calibration.
  return ["96h", "48h", "24h"].find((h) => dispo.includes(h));
}

/* Ensemble corrigé-pondéré d'un jeu de poids, pour une heure donnée.
   Même calcul que le dashboard : biais retiré par modèle (spécifique au
   secteur quand il existe), puis moyenne pondérée. */
function ensemble(brutParModele, dirParModele, decalage, poids) {
  let somme = 0, total = 0;
  for (const m of MODELES) {
    const brut = brutParModele[m], dir = dirParModele[m];
    if (brut == null) continue;
    const h = horizonPour(m, decalage, poids);
    if (h == null) continue;
    const infos = poids.modeles[m].horizons[h];
    const parSecteur = poids.modeles[m].biais_par_secteur?.[h]?.[secteurDe(dir)];
    const biais = parSecteur ? parSecteur.biais_nds : infos.biais_nds;
    somme += (brut - biais) * infos.poids;
    total += infos.poids;
  }
  return total > 0 ? somme / total : null;
}

// ------------------------------------------------------------------ rendu

function classeVent(v, sport) {
  if (v == null) return "vide";
  if (v > sport.vent_max) return "trop";
  if (v >= sport.vent_min) return "go";
  if (v >= sport.vent_marginal) return "marginal";
  return "";
}

function bande(etiquette, classeJeton, heures, cle, sport, ecarts) {
  const ligne = el("div", "ligne-bande");
  const titre = el("div", "etiquette-bande");
  titre.appendChild(el("span", `jeton ${classeJeton}`));
  titre.appendChild(document.createTextNode(etiquette));
  ligne.appendChild(titre);

  const strip = el("div", "bande-heures");
  heures.forEach((h, i) => {
    const v = h[cle];
    const cell = el("div", `cellule ${classeVent(v, sport)}`
                    + (ecarts[i] ? " ecart" : ""));
    cell.appendChild(el("span", "ch", `${h.heure}h`));
    cell.appendChild(el("span", "cv", v == null ? "—" : v.toFixed(0)));
    // L'écart est écrit noir sur blanc sous la proposition : sans ça, deux
    // valeurs arrondies au nœud paraîtraient identiques alors qu'elles
    // diffèrent — et c'est justement l'écart qu'on vient observer.
    if (cle === "proposition" && v != null && h.service != null) {
      const d = v - h.service;
      cell.appendChild(el("span", "cd",
        Math.abs(d) < 0.05 ? "=" : (d > 0 ? "+" : "−") + nb(Math.abs(d))));
    }
    strip.appendChild(cell);
  });
  ligne.appendChild(strip);
  return ligne;
}

function rendreJour(date, heures, sport) {
  const bloc = el("div", "jour-essai");
  const d = new Date(`${date}T12:00:00`);
  const ecarts = heures.map((h) =>
    h.service != null && h.proposition != null
    && Math.abs(h.proposition - h.service) >= SEUIL_ECART);

  const entete = el("div", "titre-jour-essai");
  entete.appendChild(el("span", "nom-jour",
    `${JOURS[d.getDay()]} ${d.getDate()}`));
  const nDesaccords = ecarts.filter(Boolean).length;
  entete.appendChild(el("span", "compte-ecarts", nDesaccords
    ? `${nDesaccords} h de désaccord` : "les deux s'entendent"));
  bloc.appendChild(entete);

  bloc.appendChild(bande("En service", "jeton-service", heures,
                         "service", sport, ecarts));
  bloc.appendChild(bande("Proposition", "jeton-proposition", heures,
                         "proposition", sport, ecarts));

  const valides = heures.filter((h) => h.service != null && h.proposition != null);
  if (valides.length) {
    const moyen = valides.reduce((s, h) => s + (h.proposition - h.service), 0)
                  / valides.length;
    const pire = valides.reduce((a, h) =>
      Math.abs(h.proposition - h.service) > Math.abs(a.proposition - a.service)
        ? h : a);
    const sens = moyen >= 0 ? "plus" : "moins";
    bloc.appendChild(el("p", "note-jour",
      `La proposition annonce en moyenne ${nb(Math.abs(moyen))} nds de ${sens}. `
      + `Plus gros écart à ${pire.heure} h : ${nb(pire.service)} contre `
      + `${nb(pire.proposition)} nds.`));
  }
  return bloc;
}

function decrire(poids, cible) {
  const origine = poids.origine_poids;
  document.getElementById(cible).textContent = origine
    ? `Poids ∝ 1/RMSE² mesuré contre l'anémomètre de ${origine.station}, `
      + `sur ${origine.n_paires.toLocaleString("fr-CA")} paires `
      + `(${origine.periode}). Biais inchangés. Modèle ${poids.version_modele}.`
    : `Poids calibrés contre le consensus des modèles `
      + `(${poids.periode_backtest}). Modèle ${poids.version_modele}. `
      + `C'est ce qui calcule les verdicts de la page principale.`;
}

/* Ampleur réelle de l'écart sur la période affichée. Elle est CALCULÉE, pas
   affirmée : si un jour la repondération devenait franche, la phrase suivrait
   toute seule. */
function resumerEcart(parJour) {
  const ecarts = [];
  for (const heures of parJour.values()) {
    for (const h of heures) {
      if (h.service != null && h.proposition != null) {
        ecarts.push(h.proposition - h.service);
      }
    }
  }
  if (!ecarts.length) return "";
  const moyen = ecarts.reduce((s, e) => s + Math.abs(e), 0) / ecarts.length;
  const max = ecarts.reduce((a, e) => Math.abs(e) > Math.abs(a) ? e : a, 0);
  const jugeable = Math.abs(max) >= 1.5;
  return `Sur les ${ecarts.length} heures affichées, les deux modèles diffèrent `
    + `de ${nb(moyen, 2)} nds en moyenne, ${nb(Math.abs(max), 2)} nds au pire. `
    + (jugeable
       ? "Assez pour être tranché à l'oeil sur une bonne journée."
       : "C'est trop peu pour être jugé d'un coup d'oeil au lac : la "
         + "repondération déplace surtout des décimales. La différence se "
         + "verra sur des semaines de statistiques, pas sur une sortie.");
}

function resumerPoids(service, proposition) {
  const lignes = [];
  for (const m of MODELES) {
    const a = service.modeles?.[m]?.horizons?.["24h"]?.poids;
    const b = proposition.modeles?.[m]?.horizons?.["24h"]?.poids;
    if (a == null || b == null) continue;
    const delta = Math.round(b * 100) - Math.round(a * 100);
    if (Math.abs(delta) >= 3) {
      lignes.push(`${service.modeles[m].nom} ${Math.round(a * 100)} % → `
                  + `${Math.round(b * 100)} %`);
    }
  }
  return lignes.length
    ? `Ce que la proposition change, à 24 h : ${lignes.join(" · ")}. `
      + `Les biais, eux, sont identiques dans les deux.`
    : "Les deux jeux de poids sont très proches : attends-toi à peu d'écart.";
}

// ------------------------------------------------------------------ départ

async function demarrer() {
  const etat = document.getElementById("etat");
  try {
    const [service, proposition] = await Promise.all([
      fetch("poids_modeles.json").then((r) => r.json()),
      fetch("poids_candidat.json").then((r) => {
        if (!r.ok) throw new Error("aucune proposition publiée pour l'instant");
        return r.json();
      }),
    ]);
    const sport = service.sport;

    const url = "https://api.open-meteo.com/v1/forecast"
      + `?latitude=${service.spot.latitude}&longitude=${service.spot.longitude}`
      + "&hourly=wind_speed_10m,wind_direction_10m"
      + `&models=${MODELES.join(",")}`
      + "&wind_speed_unit=kn&timezone=America%2FToronto&forecast_days=5";
    const rep = await fetch(url);
    if (!rep.ok) throw new Error(`Open-Meteo HTTP ${rep.status}`);
    const donnees = await rep.json();

    const temps = donnees.hourly.time;
    const aujourdhui = temps[0].slice(0, 10);
    const parJour = new Map();
    for (let i = 0; i < temps.length; i++) {
      const heure = Number(temps[i].slice(11, 13));
      if (heure < HEURE_DEBUT || heure >= HEURE_FIN) continue;
      const jour = temps[i].slice(0, 10);
      const decalage = Math.round(
        (new Date(`${jour}T12:00:00`) - new Date(`${aujourdhui}T12:00:00`))
        / 86400000);
      const bruts = {}, dirs = {};
      for (const m of MODELES) {
        bruts[m] = donnees.hourly[`wind_speed_10m_${m}`]?.[i] ?? null;
        dirs[m] = donnees.hourly[`wind_direction_10m_${m}`]?.[i] ?? null;
      }
      if (!parJour.has(jour)) parJour.set(jour, []);
      parJour.get(jour).push({
        heure,
        service: ensemble(bruts, dirs, decalage, service),
        proposition: ensemble(bruts, dirs, decalage, proposition),
      });
    }

    decrire(service, "desc-service");
    decrire(proposition, "desc-proposition");
    document.getElementById("seuil-ecart").textContent = nb(SEUIL_ECART);
    const resume = document.getElementById("resume");
    resume.appendChild(el("p", "resume-ecart", resumerEcart(parJour)));
    resume.appendChild(el("p", "resume-poids",
                          resumerPoids(service, proposition)));

    const conteneur = document.getElementById("bandes");
    for (const [jour, heures] of parJour) {
      conteneur.appendChild(rendreJour(jour, heures, sport));
    }

    const maintenant = new Date();
    document.getElementById("fraicheur-essai").textContent =
      `Prévisions tirées en direct le `
      + `${maintenant.toLocaleDateString("fr-CA")} à `
      + `${maintenant.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })}. `
      + `Les deux modèles voient exactement les mêmes données brutes.`;
    document.getElementById("versions").textContent =
      `Interface v${VERSION_UI} · en service ${service.version_modele} · `
      + `proposition ${proposition.version_modele}`;

    etat.hidden = true;
    for (const id of ["intro", "jours", "verdict-essai"]) {
      document.getElementById(id).hidden = false;
    }
  } catch (err) {
    etat.textContent = `Impossible d'afficher la comparaison (${err.message}).`;
  }
}

demarrer();
