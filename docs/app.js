/* Dashboard vent Lac Maskinongé.
 *
 * Architecture de fraîcheur : les prévisions brutes sont récupérées EN DIRECT
 * chez Open-Meteo à chaque ouverture (CORS, sans clé), puis re-rafraîchies
 * automatiquement toutes les heures entre 6 h et 22 h (heure de Montréal)
 * tant que la page est ouverte. Les corrections (biais/poids par modèle et
 * horizon) viennent de poids_modeles.json, recalibré chaque semaine par le
 * cron — le cron ne sert jamais à l'affichage. Tous les seuils du sport sont
 * lus dans poids_modeles.json (section sport).
 */
"use strict";

/* Version de l'INTERFACE (ce fichier + index.html + style.css). À incrémenter
 * à la main quand l'affichage change — mineur pour un ajustement, majeur pour
 * une refonte. Elle est volontairement indépendante de la version du MODÈLE
 * (les poids calibrés, affichés à côté en pied de page) : les deux évoluent
 * séparément, et quand quelque chose cloche il faut pouvoir dire lequel des
 * deux a bougé. Pas de numéro injecté au déploiement : docs/ doit rester
 * copiable tel quel par FTP, sans étape de build. */
const VERSION_UI = "1.5.0";

const MODELES = {
  gem_global: "GEM global",
  gem_regional: "GEM régional",
  gem_hrdps_continental: "HRDPS",
  ecmwf_ifs025: "ECMWF",
  gfs_global: "GFS",
  icon_global: "ICON",
};
const SECTEURS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
const JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const LIBELLES_BLOCS = { matin: "matin", midi: "midi", apres_midi: "après-midi" };
const SEUIL_DIVERGENCE = 5; // nds d'écart entre modèles = mention de divergence
// Direction jugée peu fiable (flèche pâle) sous ce vent, ou quand les modèles
// ne s'entendent pas : accord = longueur du vecteur moyen des directions
// unitaires des modèles (1 = tous pareils, 0 = directions opposées).
const VENT_DIRECTION_FIABLE = 4, ACCORD_DIRECTION_FIABLE = 0.8;

// Auto-rafraîchissement : chaque heure entre 6 h et 22 h (heure de Montréal)
const RAFRAICHIR_DE = 6, RAFRAICHIR_A = 22, RAFRAICHIR_MS = 60 * 60 * 1000;

// ---------------------------------------------------------------- fenêtres

function fenetresDuJour(vents, sport) {
  const dansBande = (v) => v != null && v >= sport.vent_min && v <= sport.vent_max;
  const marginal = (v) => v != null && v >= sport.vent_marginal && v < sport.vent_min;
  const fenetres = [];
  const extraire = (seg) => {
    while (seg.length && marginal(vents[seg[0]])) seg = seg.slice(1);
    while (seg.length && marginal(vents[seg[seg.length - 1]])) seg = seg.slice(0, -1);
    if (!seg.length) return;
    for (let j = 0; j < seg.length - 1; j++) {
      if (marginal(vents[seg[j]]) && marginal(vents[seg[j + 1]])) {
        extraire(seg.slice(0, j));
        extraire(seg.slice(j + 2));
        return;
      }
    }
    const bande = seg.filter((i) => dansBande(vents[i])).length;
    if (bande >= sport.duree_min_fenetre) fenetres.push([seg[0], seg[seg.length - 1] + 1]);
  };
  let seg = [];
  for (let i = 0; i <= vents.length; i++) {
    const v = i < vents.length ? vents[i] : null;
    if (dansBande(v) || marginal(v)) seg.push(i);
    else { extraire(seg); seg = []; }
  }
  return fenetres.sort((a, b) => a[0] - b[0]);
}

// ------------------------------------------------------------- corrections

function secteurDe(direction) {
  if (direction == null) return null;
  return SECTEURS[Math.floor(((direction + 22.5) % 360) / 45)];
}

function horizonPour(modele, decalageJour, poids) {
  const dispo = Object.keys(poids.modeles[modele]?.horizons ?? {});
  if (!dispo.length) return null;
  const souhaite = decalageJour <= 1 ? "24h" : decalageJour === 2 ? "48h" : "96h";
  if (dispo.includes(souhaite)) return souhaite;
  // Repli : l'horizon archivé le plus long du modèle (ex. HRDPS -> 24h)
  return ["96h", "48h", "24h"].find((h) => dispo.includes(h));
}

function corrige(modele, brut, direction, decalageJour, poids) {
  const h = horizonPour(modele, decalageJour, poids);
  if (h == null || brut == null) return null;
  const infos = poids.modeles[modele].horizons[h];
  const sect = secteurDe(direction);
  const parSecteur = poids.modeles[modele].biais_par_secteur?.[h]?.[sect];
  const biais = parSecteur ? parSecteur.biais_nds : infos.biais_nds;
  return { vent: brut - biais, poids: infos.poids, horizon: h };
}

// ------------------------------------------------------------------- météo

const CODES_ORAGE = [95, 96, 99];

// Tendance du ciel (code WMO -> catégorie) : 0-3 restent tels quels, le
// brouillard est à part, toute précipitation/orage compte comme « couvert »
// pour la tendance du ciel (le cumul de pluie donne le détail à côté).
const CIEL_TEXTES = { 0: "ensoleillé", 1: "généralement ensoleillé",
                      2: "partiellement nuageux", 3: "couvert" };

function categorieCiel(code) {
  if (code == null) return null;
  if (code <= 3) return code;
  if (code === 45 || code === 48) return "brouillard";
  return 3;
}

function iconeMeteo(code) {
  if (code == null) return "";
  if (CODES_ORAGE.includes(code)) return "⛈️";
  if (code === 0) return "☀️";
  if (code <= 2) return "🌤️";
  if (code === 3) return "☁️";
  if (code <= 48) return "🌫️";
  if (code <= 57) return "🌦️";
  if (code <= 67) return "🌧️";
  if (code <= 77) return "❄️";
  if (code <= 82) return "🌧️";
  if (code <= 86) return "❄️";
  return "⛈️";
}

function resumeMeteoJour(jour) {
  /* Résumé discret de la météo du jour (heures navigables) :
   * icône dominante, tendance du ciel (ensoleillé/nuageux/couvert/brumeux),
   * cumul de pluie, drapeau orage. */
  const codes = jour.map((h) => h.meteoCode).filter((c) => c != null);
  if (!codes.length) return null;
  const orage = codes.some((c) => CODES_ORAGE.includes(c));
  const pluie = jour.reduce((s, h) => s + (h.pluie ?? 0), 0);
  const probMax = Math.max(...jour.map((h) => h.probPluie ?? 0));
  // Icône du "pire" moment hors orage (le plus couvert/mouillé), pour ne pas
  // afficher soleil quand l'après-midi est sous la pluie.
  const dominant = Math.max(...codes.filter((c) => !CODES_ORAGE.includes(c)), 0);

  // Catégorie de ciel la plus fréquente sur les heures navigables
  const compte = {};
  for (const c of codes.map(categorieCiel)) compte[c] = (compte[c] ?? 0) + 1;
  const categorieDominante = Object.entries(compte).sort((a, b) => b[1] - a[1])[0][0];
  const cielTexte = categorieDominante === "brouillard"
    ? "brumeux" : CIEL_TEXTES[categorieDominante];

  let pluieTexte = null;
  if (pluie < 0.5) pluieTexte = probMax >= 40 ? `risque d'averses (${probMax} %)` : null;
  else if (pluie < 5) pluieTexte = `un peu de pluie (${pluie.toFixed(0)} mm)`;
  else if (pluie < 15) pluieTexte = `pluie (${pluie.toFixed(0)} mm)`;
  else pluieTexte = `grosse pluie (${pluie.toFixed(0)} mm)`;

  const texte = pluieTexte ? `${cielTexte}, ${pluieTexte}` : cielTexte;
  return { icone: iconeMeteo(orage ? 95 : dominant), texte, orage, pluie };
}

// --------------------------------------------------------------- ensemble

function construireHeures(donnees, meteo, poids) {
  /* Retourne une liste d'objets {t, jourISO, heure, decalage, parModele,
   * ensemble, rafales, direction, accordDirection, divergence, meteoCode,
   * pluie, probPluie}
   * en heure locale du spot. */
  const temps = donnees.hourly.time;
  const aujourdhui = temps[0].slice(0, 10);
  const ratioDefaut = poids.ratio_rafales_defaut ?? 1.6;
  const meteoParTemps = {};
  if (meteo?.hourly?.time) {
    meteo.hourly.time.forEach((t, i) => {
      meteoParTemps[t] = {
        meteoCode: meteo.hourly.weather_code?.[i],
        pluie: meteo.hourly.precipitation?.[i],
        probPluie: meteo.hourly.precipitation_probability?.[i],
      };
    });
  }
  const heures = [];
  for (let i = 0; i < temps.length; i++) {
    const jourISO = temps[i].slice(0, 10);
    const decalage = Math.round(
      (Date.parse(jourISO) - Date.parse(aujourdhui)) / 86400000);
    const parModele = {};
    let sw = 0, svent = 0, su = 0, sv = 0, sraf = 0, nraf = 0;
    let dx = 0, dy = 0, ndir = 0;
    const valeurs = [];
    for (const m of Object.keys(MODELES)) {
      const brut = donnees.hourly[`wind_speed_10m_${m}`]?.[i];
      const dir = donnees.hourly[`wind_direction_10m_${m}`]?.[i];
      const c = corrige(m, brut, dir, decalage, poids);
      if (c == null) continue;
      parModele[m] = c.vent;
      valeurs.push(c.vent);
      sw += c.poids; svent += c.vent * c.poids;
      if (dir != null) {
        const th = (dir * Math.PI) / 180;
        su += -c.vent * Math.sin(th) * c.poids;
        sv += -c.vent * Math.cos(th) * c.poids;
        dx += Math.sin(th); dy += Math.cos(th); ndir++;
      }
      let raf = donnees.hourly[`wind_gusts_10m_${m}`]?.[i];
      if (raf == null && brut != null) {
        const ratio = poids.modeles[m]?.ratio_rafales ?? ratioDefaut;
        raf = brut * ratio; // repli documenté (ECMWF sans rafales)
      }
      if (raf != null) { sraf += raf * c.poids; nraf += c.poids; }
    }
    const ensemble = sw > 0 ? svent / sw : null;
    heures.push({
      t: temps[i], jourISO, heure: Number(temps[i].slice(11, 13)), decalage,
      parModele, ensemble,
      rafales: nraf > 0 ? sraf / nraf : null,
      direction: sw > 0 ? ((Math.atan2(-su, -sv) * 180) / Math.PI + 360) % 360 : null,
      accordDirection: ndir > 0 ? Math.hypot(dx, dy) / ndir : null,
      divergence: valeurs.length >= 2 ? Math.max(...valeurs) - Math.min(...valeurs) : 0,
      ...(meteoParTemps[temps[i]] ?? {}),
    });
  }
  return heures;
}

function regulariteFenetres(jour, fenetres, sport) {
  /* Indice de régularité des puffs, à partir du facteur de rafales
   * (rafales / vent moyen) médian sur les heures en bande des fenêtres :
   * < 1.35 -> "régulier", 1.35..ratio_rafaleux -> "puffs modérés",
   * > ratio_rafaleux (1.6) -> "puffy". Proxy standard : plus les rafales
   * dépassent le vent moyen, plus le vent est irrégulier. */
  const dansBande = (v) => v != null && v >= sport.vent_min && v <= sport.vent_max;
  const ratios = [];
  for (const [d, f] of fenetres) {
    for (let i = d; i < f; i++) {
      const h = jour[i];
      if (dansBande(h.ensemble) && h.rafales != null) ratios.push(h.rafales / h.ensemble);
    }
  }
  if (!ratios.length) return null;
  ratios.sort((a, b) => a - b);
  const mediane = ratios[Math.floor(ratios.length / 2)];
  if (mediane > sport.ratio_rafaleux) return { niveau: "puffy", classe: "mauvais" };
  if (mediane > 1.35) return { niveau: "puffs modérés", classe: "moyen" };
  return { niveau: "vent régulier", classe: "bon" };
}

function analyseJour(heures, jourISO, sport) {
  const jour = heures.filter((h) => h.jourISO === jourISO
    && h.heure >= sport.heure_debut && h.heure < sport.heure_fin);
  const vents = jour.map((h) => h.ensemble);
  const fenetres = fenetresDuJour(vents, sport);
  const dansBande = (v) => v != null && v >= sport.vent_min && v <= sport.vent_max;
  const regularite = regulariteFenetres(jour, fenetres, sport);
  const heuresDivergentes = jour.filter((h) => h.divergence > SEUIL_DIVERGENCE).length;
  const max = Math.max(...vents.filter((v) => v != null), 0);
  const meteo = resumeMeteoJour(jour);

  // Blocs (matin/midi/après-midi) : GO si une fenêtre recouvre le bloc d'au
  // moins 1 h dans la bande + pics de vent et de rafales du bloc.
  const blocs = {};
  for (const [nom, [debutB, finB]] of Object.entries(sport.blocs)) {
    const dansBloc = jour.filter((h) => h.heure >= debutB && h.heure < finB);
    let go = false;
    for (const [d, f] of fenetres) {
      for (let i = d; i < f; i++) {
        const h = jour[i];
        if (h.heure >= debutB && h.heure < finB && dansBande(h.ensemble)) go = true;
      }
    }
    blocs[nom] = {
      go,
      vent: Math.max(...dansBloc.map((h) => h.ensemble ?? 0), 0),
      rafales: Math.max(...dansBloc.map((h) => h.rafales ?? 0), 0),
    };
  }
  return { jour, fenetres, regularite, heuresDivergentes, max, blocs, meteo };
}

// ---------------------------------------------------------------- verdicts

function confianceGo(decalage, poids) {
  /* % de confiance d'un GO à cet horizon : part des GO annoncés à cette
   * échéance qui se sont historiquement confirmés (backtest). */
  const h = decalage <= 1 ? "24h" : decalage === 2 ? "48h" : "96h";
  const fiab = poids.fiabilite_go_par_horizon?.[h];
  return fiab ? Math.round(fiab.taux_go_confirme * 100) : null;
}

function etiquetteFenetre(analyse, sport) {
  if (!analyse.fenetres.length) {
    return analyse.max >= sport.vent_marginal
      ? `vent max ${analyse.max.toFixed(0)} nds — sous le seuil de foil`
      : "petit temps";
  }
  const [d, f] = analyse.fenetres.reduce((a, b) => (b[1] - b[0] > a[1] - a[0] ? b : a));
  const debut = analyse.jour[d].heure, fin = analyse.jour[f - 1].heure + 1;
  const tranche = analyse.jour.slice(d, f);
  const vent = Math.max(...tranche.map((h) => h.ensemble));
  const raf = Math.max(...tranche.map((h) => h.rafales ?? 0));
  return `fenêtre ${debut} h–${fin} h · vent ${vent.toFixed(0)} nds`
    + (raf ? ` · rafales ${raf.toFixed(0)} nds` : "");
}

function fleche(direction) {
  if (direction == null) return "";
  // Direction d'où vient le vent -> flèche pointant où il va
  const fleches = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"];
  return fleches[Math.floor(((direction + 22.5) % 360) / 45)];
}

function directionFiable(h) {
  return h.direction != null && h.ensemble != null
    && h.ensemble >= VENT_DIRECTION_FIABLE
    && (h.accordDirection ?? 0) >= ACCORD_DIRECTION_FIABLE;
}

// Flèche orientée au degré près, pointant où va le vent (même convention que
// fleche()). Tracée vers le haut puis tournée de direction + 180°.
const TRACE_FLECHE = "M0,-8 L5.5,1.5 L1.7,0.4 L1.7,8 L-1.7,8 L-1.7,0.4 L-5.5,1.5 Z";

function flecheSVG(h, taille = 16) {
  if (h.direction == null) return "";
  const nom = secteurDe(h.direction);
  return `<svg class="fl${directionFiable(h) ? "" : " pale"}" width="${taille}" height="${taille}"`
    + ` viewBox="-10 -10 20 20" role="img" aria-label="vent de ${nom}"><title>${nom} ${Math.round(h.direction)}°</title>`
    + `<g transform="rotate(${Math.round(h.direction + 180) % 360})"><path d="${TRACE_FLECHE}"/></g></svg>`;
}

function heureMontreal() {
  const parts = new Intl.DateTimeFormat("fr-CA", {
    timeZone: "America/Toronto", hour: "numeric", hour12: false,
  }).formatToParts(new Date());
  const h = Number(parts.find((p) => p.type === "hour")?.value);
  return Number.isFinite(h) ? h % 24 : new Date().getHours();
}

function dateMontreal() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Toronto", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

// ----------------------------------------------------------------- rendu

function classeHeure(h, sport) {
  if (h.ensemble == null) return "vide";
  if (h.ensemble > sport.vent_max) return "trop";
  if (h.ensemble >= sport.vent_min) return "go";
  if (h.ensemble >= sport.vent_marginal) return "marginal";
  return "calme";
}

function bandeHoraire(analyse, sport, heureCourante) {
  /* Bande heure par heure (8 h–20 h) : vent, rafales, direction, météo, orage.
   * La journée complète est TOUJOURS affichée ; les heures déjà passées
   * (aujourd'hui seulement) sont grisées, jamais retirées. */
  const cellules = analyse.jour.map((h) => {
    const orage = CODES_ORAGE.includes(h.meteoCode);
    const passee = h.decalage === 0 && h.heure < heureCourante;
    return `<div class="cellule ${classeHeure(h, sport)}${orage ? " orage" : ""}${passee ? " passee" : ""}">
      <span class="ch">${h.heure} h</span>
      <span class="cv">${h.ensemble != null ? h.ensemble.toFixed(0) : "—"}</span>
      <span class="cr">${h.rafales != null ? `raf ${h.rafales.toFixed(0)}` : ""}</span>
      <span class="cd">${flecheSVG(h)}</span>
      <span class="cm">${orage ? "⚡" : iconeMeteo(h.meteoCode)}</span>
    </div>`;
  });
  return `<div class="bande-heures">${cellules.join("")}</div>`;
}

function directionMoyenne(hs) {
  /* Direction dominante d'un ensemble d'heures : moyenne vectorielle pondérée
   * par le vent (un souffle de 2 nds ne doit pas tirer la flèche). Fiable si
   * le vent moyen dépasse VENT_DIRECTION_FIABLE et que les heures concordent. */
  let u = 0, v = 0, n = 0, poidsTotal = 0, somme = 0;
  for (const h of hs) {
    if (h.direction == null || h.ensemble == null) continue;
    const th = (h.direction * Math.PI) / 180;
    u += Math.sin(th) * h.ensemble; v += Math.cos(th) * h.ensemble;
    poidsTotal += h.ensemble; somme += h.ensemble; n++;
  }
  if (!n || poidsTotal <= 0) return null;
  const direction = ((Math.atan2(u, v) * 180) / Math.PI + 360) % 360;
  const accord = Math.hypot(u, v) / poidsTotal;
  return { direction, ensemble: somme / n, accordDirection: accord };
}

function nomJour(decalage, jourISO) {
  if (decalage === 0) return "aujourd'hui";
  if (decalage === 1) return "demain";
  return JOURS[new Date(`${jourISO}T12:00`).getDay()];
}

function classeBloc(b, sport) {
  if (b.go) return "go";
  if (b.vent > sport.vent_max) return "trop";
  if (b.vent >= sport.vent_marginal) return "marginal";
  return "calme";
}

function rendreSemaine(heures, poids, sport) {
  /* Une rangée par jour : nom et date (+ météo, + % si GO), direction
   * dominante du jour, puis vent / puffs du matin, du midi, de l'après-midi. */
  const conteneur = document.getElementById("rangees-semaine");
  const jours = [...new Set(heures.map((h) => h.jourISO))].slice(0, 7);
  const tete = `<div class="tete"><span></span><span></span>${Object.keys(sport.blocs)
    .map((nom) => `<span>${nom === "apres_midi" ? "ap.-midi" : (LIBELLES_BLOCS[nom] ?? nom)}</span>`).join("")}</div>`;
  const rangees = [];
  for (const jourISO of jours) {
    const a = analyseJour(heures, jourISO, sport);
    if (!a.jour.length) continue;
    const decalage = a.jour[0].decalage;
    const go = a.fenetres.length > 0;
    const conf = go ? confianceGo(decalage, poids) : null;
    const d = new Date(`${jourISO}T12:00`);
    const [debutJ, finJ] = [Math.min(...Object.values(sport.blocs).map((b) => b[0])),
                            Math.max(...Object.values(sport.blocs).map((b) => b[1]))];
    const dir = directionMoyenne(a.jour.filter((h) => h.heure >= debutJ && h.heure < finJ));
    const meteo = a.meteo ? `${a.meteo.orage ? "⚡" : a.meteo.icone}` : "";
    const cases = Object.values(a.blocs).map((b) => {
      if (!(b.vent > 0)) return `<div class="case calme"><span class="v">—</span></div>`;
      // Rouge seulement là où on sortirait : sous la bande, le ratio rafales/vent
      // est presque toujours élevé et ne dit rien d'utile.
      const puffy = b.go && b.rafales / b.vent > sport.ratio_rafaleux;
      return `<div class="case ${classeBloc(b, sport)}"><span class="v">${b.vent.toFixed(0)}</span>`
        + `<span class="p${puffy ? " puffy" : ""}">/ ${b.rafales.toFixed(0)}</span></div>`;
    }).join("");
    rangees.push(`<div class="rangee">
      <div class="nom-jour"><strong>${nomJour(decalage, jourISO)}</strong>
        <small>${d.getDate()}/${d.getMonth() + 1}${meteo ? ` · ${meteo}` : ""}${conf != null ? ` <span class="conf">${conf} %</span>` : ""}</small></div>
      <div class="dir-jour${go ? " go" : ""}">${dir ? `${flecheSVG(dir, 20)}${secteurDe(dir.direction)}` : ""}</div>
      ${cases}</div>`);
  }
  conteneur.innerHTML = tete + rangees.join("");
}

function rendreExecution(heures, poids, sport) {
  const conteneur = document.getElementById("blocs-jours");
  conteneur.innerHTML = "";
  const heureCourante = heureMontreal();
  const jours = [...new Set(heures.map((h) => h.jourISO))].slice(0, 2);
  jours.forEach((jourISO, idx) => {
    const a = analyseJour(heures, jourISO, sport);
    if (!a.jour.length) return;
    const conf = a.fenetres.length ? confianceGo(idx, poids) : null;
    const meteo = a.meteo
      ? `<span class="meteo-jour">${a.meteo.icone} ${a.meteo.texte}</span>`
        + (a.meteo.orage ? `<span class="orage-badge">⚡ orages</span>` : "")
      : "";
    const div = document.createElement("div");
    div.className = "jour-blocs";
    div.innerHTML = `<div class="titre-jour">${idx === 0 ? "aujourd'hui" : "demain"} ${meteo}`
      + `${conf != null ? `<span class="conf">${conf} %</span>` : ""}</div>`
      + bandeHoraire(a, sport, heureCourante);
    conteneur.appendChild(div);
  });

  // Mention de divergence sur les 48 h affichées
  const avis = document.getElementById("divergence");
  avis.hidden = true;
  const h48 = heures.filter((h) => h.decalage <= 1);
  const divergentes = h48.filter(
    (h) => h.heure >= sport.heure_debut && h.heure < sport.heure_fin
      && h.divergence > SEUIL_DIVERGENCE);
  if (divergentes.length >= 2) {
    avis.hidden = false;
    avis.textContent = `⚠️ Modèles en désaccord (plus de ${SEUIL_DIVERGENCE} nds) pendant `
      + `${divergentes.length} h d'ici demain soir : verdict moins sûr.`;
  }
}

function nomCourt(h) {
  if (h.decalage === 0) return "auj.";
  if (h.decalage === 1) return "dem.";
  return `${JOURS[new Date(`${h.jourISO}T12:00`).getDay()].slice(0, 3)}.`;
}

function rendreGraphique(heures, sport) {
  /* Fenêtre du graphique : de (maintenant - 2 h) à la fin des prévisions
   * (7 jours) — on regarde devant, pas la nuit passée. Largeur fixe par
   * heure : le graphique défile horizontalement au doigt. */
  const heureCourante = heureMontreal();
  const h48 = heures.filter((h) => h.decalage >= 1
    || (h.decalage === 0 && h.heure >= Math.max(0, heureCourante - 2)));
  // Sous l'axe : une rangée de flèches de direction (une par heure), puis les heures.
  const PX_HEURE = 14, H = 300, mg = { g: 30, d: 8, h: 26, b: 52 };
  const L = mg.g + mg.d + Math.max(1, h48.length - 1) * PX_HEURE;
  const larg = L - mg.g - mg.d, haut = H - mg.h - mg.b;
  const maxY = Math.max(20, ...h48.map((h) => h.ensemble ?? 0),
                        ...h48.map((h) => h.rafales ?? 0),
                        ...h48.flatMap((h) => Object.values(h.parModele))) + 1;
  const x = (i) => mg.g + (i / (h48.length - 1)) * larg;
  const y = (v) => mg.h + haut - (v / maxY) * haut;

  const chemin = (points) => points
    .map((p, i) => (p == null ? null : `${i === 0 || points[i - 1] == null ? "M" : "L"}${x(i).toFixed(1)},${y(p).toFixed(1)}`))
    .filter(Boolean).join(" ");

  let svg = `<svg viewBox="0 0 ${L} ${H}" width="${L}" role="img" aria-label="Vent prévu sur 7 jours, par modèle et ensemble corrigé">`;
  // Chaque jour : fond alterné, trait plein à minuit, nom et date en haut.
  const debuts = h48.map((h, i) => (i === 0 || h.heure === 0 ? i : -1)).filter((i) => i >= 0);
  debuts.forEach((i0, k) => {
    const x0 = k === 0 ? 0 : x(i0) - PX_HEURE / 2;
    const x1 = k + 1 < debuts.length ? x(debuts[k + 1]) - PX_HEURE / 2 : L;
    if (k % 2 === 1) svg += `<rect x="${x0.toFixed(1)}" y="0" width="${(x1 - x0).toFixed(1)}" height="${H}" fill="var(--jour-alt)"/>`;
    if (k > 0) svg += `<line x1="${x0.toFixed(1)}" x2="${x0.toFixed(1)}" y1="0" y2="${H}" stroke="var(--texte-3)" stroke-width="1"/>`;
    const h0 = h48[i0], d = new Date(`${h0.jourISO}T12:00`);
    const nom = h0.decalage === 0 ? "AUJ" : h0.decalage === 1 ? "DEM" : JOURS[d.getDay()].slice(0, 3).toUpperCase();
    if (x1 - x0 > 60) {
      svg += `<text x="${(Math.max(x0, mg.g) + 6).toFixed(1)}" y="15" font-size="11" font-weight="700" letter-spacing="0.06em" fill="var(--texte)">${nom} `
        + `<tspan font-weight="400" fill="var(--texte-3)">${d.getDate()}/${d.getMonth() + 1}</tspan></text>`;
    }
  });
  // Nuits (hors heures de navigation) : légèrement assombries pour découper les jours.
  h48.forEach((h, i) => {
    if (h.heure >= sport.heure_debut && h.heure < sport.heure_fin) return;
    svg += `<rect x="${(x(i) - PX_HEURE / 2).toFixed(1)}" y="${mg.h}" width="${PX_HEURE}" height="${haut}" fill="var(--passe)"/>`;
  });
  svg += `<rect x="${mg.g}" y="${y(sport.vent_max)}" width="${larg}" height="${y(sport.vent_min) - y(sport.vent_max)}" fill="var(--bande)"/>`;

  // Repère « maintenant » + les 2 h passées grisées
  const iMaintenant = h48.findIndex((h) => h.decalage === 0 && h.heure === heureCourante);
  if (iMaintenant >= 0) {
    if (iMaintenant > 0) {
      svg += `<rect x="${mg.g}" y="${mg.h}" width="${x(iMaintenant) - mg.g}" height="${haut}" fill="var(--passe)"/>`;
    }
    svg += `<line x1="${x(iMaintenant)}" x2="${x(iMaintenant)}" y1="${mg.h}" y2="${H - mg.b}" stroke="var(--maintenant)" stroke-width="1.6"/>`
      + `<text x="${Math.min(x(iMaintenant) + 4, L - 70)}" y="${mg.h + 10}" font-size="10" fill="var(--maintenant)">maintenant</text>`;
  }

  for (const v of [0, 5, 10, 15, 20].filter((v) => v <= maxY)) {
    svg += `<line x1="${mg.g}" x2="${L - mg.d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--bordure)" stroke-width="0.7"/>`
      + `<text x="${mg.g - 5}" y="${y(v) + 3}" text-anchor="end" font-size="10" fill="var(--texte-3)">${v}</text>`;
  }
  const yFleches = H - mg.b + 16;
  h48.forEach((h, i) => {
    if (h.direction == null || h.heure % 2 !== 0
        || h.heure < sport.heure_debut - 2 || h.heure > sport.heure_fin) return;
    const couleur = classeHeure(h, sport) === "go" ? "var(--go)" : "var(--texte-2)";
    svg += `<g fill="${couleur}" opacity="${directionFiable(h) ? 1 : 0.35}" `
      + `transform="translate(${x(i).toFixed(1)},${yFleches}) scale(0.95) rotate(${Math.round(h.direction + 180) % 360})">`
      + `<path d="${TRACE_FLECHE}"/></g>`;
  });
  for (let i = 0; i < h48.length; i++) {
    if (h48[i].heure % 3 === 0) {
      svg += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="var(--texte-3)">${h48[i].heure} h</text>`;
    }
  }
  for (const m of Object.keys(MODELES)) {
    const points = h48.map((h) => h.parModele[m] ?? null);
    if (points.every((p) => p == null)) continue;
    svg += `<path d="${chemin(points)}" fill="none" stroke="var(--m-${m})" stroke-width="1.3" opacity="0.55"/>`;
  }
  svg += `<path d="${chemin(h48.map((h) => h.rafales))}" fill="none" stroke="var(--maintenant)" stroke-width="1.8" stroke-dasharray="6 4" opacity="0.9"/>`;
  svg += `<path d="${chemin(h48.map((h) => h.ensemble))}" fill="none" stroke="var(--ensemble)" stroke-width="3.2" stroke-linejoin="round"/>`;
  svg += `<g id="curseur" style="display:none"><line y1="${mg.h}" y2="${H - mg.b}" stroke="var(--texte-3)" stroke-width="1"/>`
    + `<circle r="4" fill="var(--ensemble)"/>`
    + `<rect width="214" height="20" rx="4" fill="var(--surface-carte)" stroke="var(--bordure)"/>`
    + `<text font-size="11" fill="var(--texte)"></text></g>`;
  svg += `</svg>`;
  const cadre = document.getElementById("graphique");
  cadre.innerHTML = svg;

  // Doigt / souris sur le graphique : overlay vent + rafales de l'ensemble
  const el = cadre.querySelector("svg");
  const curseur = el.querySelector("#curseur");
  const bouger = (ev) => {
    const rect = el.getBoundingClientRect();
    const cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
    const px = (cx / rect.width) * L;
    const i = Math.max(0, Math.min(h48.length - 1,
      Math.round(((px - mg.g) / larg) * (h48.length - 1))));
    const hh = h48[i];
    if (hh.ensemble == null) return;
    curseur.style.display = "";
    const ligne = curseur.querySelector("line");
    ligne.setAttribute("x1", x(i)); ligne.setAttribute("x2", x(i));
    const point = curseur.querySelector("circle");
    point.setAttribute("cx", x(i)); point.setAttribute("cy", y(hh.ensemble));
    const tx = Math.min(Math.max(x(i) - 107, mg.g), L - 222);
    const boite = curseur.querySelector("rect");
    boite.setAttribute("x", tx); boite.setAttribute("y", mg.h);
    const texte = curseur.querySelector("text");
    texte.setAttribute("x", tx + 7); texte.setAttribute("y", mg.h + 14);
    texte.textContent = `${nomCourt(hh)} ${hh.heure} h · `
      + `vent ${hh.ensemble.toFixed(1)}`
      + (hh.rafales != null ? ` · raf ${hh.rafales.toFixed(0)} nds` : " nds")
      + (hh.direction != null ? ` · ${secteurDe(hh.direction)} ${Math.round(hh.direction)}°` : "");
  };
  let luUneFois = false;
  const marquerLecture = () => {
    if (luUneFois) return;
    luUneFois = true;
    window.track?.("foil-chart-read", {});
  };
  el.addEventListener("mousemove", () => marquerLecture(), { once: true });
  el.addEventListener("touchstart", () => marquerLecture(), { once: true });

  el.addEventListener("mousemove", bouger);
  el.addEventListener("touchstart", bouger, { passive: true });
  el.addEventListener("touchmove", bouger, { passive: true });
  el.addEventListener("mouseleave", () => { curseur.style.display = "none"; });

  const legende = document.getElementById("legende");
  legende.innerHTML = `<span><i style="background:var(--ensemble);height:4px"></i>Prévision corrigée</span>`
    + `<span><i style="background:repeating-linear-gradient(90deg,var(--maintenant) 0 5px,transparent 5px 8px);height:3px"></i>Puffs</span>`
    + Object.entries(MODELES).map(
      ([m, nom]) => `<span><i style="background:var(--m-${m})"></i>${nom}</span>`).join("");
}

// ---------------------------------------------------------------- démarrage

let derniereMaj = 0;
let dateAffichee = null;

async function demarrer() {
  const etat = document.getElementById("etat");
  try {
    const poids = await (await fetch("poids_modeles.json")).json();
    const sport = poids.sport;
    const base = "https://api.open-meteo.com/v1/forecast"
      + `?latitude=${poids.spot.latitude}&longitude=${poids.spot.longitude}`;
    const urlVent = base
      + "&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m"
      + `&models=${Object.keys(MODELES).join(",")}`
      + "&wind_speed_unit=kn&timezone=America%2FToronto&forecast_days=7";
    const urlMeteo = base
      + "&hourly=weather_code,precipitation,precipitation_probability"
      + "&timezone=America%2FToronto&forecast_days=7";
    const [repVent, repMeteo] = await Promise.all([fetch(urlVent), fetch(urlMeteo)]);
    if (!repVent.ok) throw new Error(`Open-Meteo HTTP ${repVent.status}`);
    const donnees = await repVent.json();
    const meteo = repMeteo.ok ? await repMeteo.json() : null;

    const heures = construireHeures(donnees, meteo, poids);
    rendreExecution(heures, poids, sport);
    rendreGraphique(heures, sport);
    rendreSemaine(heures, poids, sport);
    derniereMaj = Date.now();
    dateAffichee = dateMontreal();

    const maintenant = new Date();
    document.getElementById("fraicheur").textContent =
      `Mis à jour à ${maintenant.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })}`
      + ` · rafraîchi chaque heure de ${RAFRAICHIR_DE} h à ${RAFRAICHIR_A} h.`;
    document.getElementById("recalibrage").textContent =
      `% d'un GO : part des GO confirmés (${poids.periode_backtest}). `
      + `Recalibré le ${poids.genere_le}.`;

    // Les deux versions côte à côte : ce qui est affiché (interface) et ce qui
    // a calculé les chiffres (modèle). Le modèle renvoie à un jeu de poids
    // archivé dans data/modeles/<version>/, restaurable tel quel.
    const versionModele = poids.version_modele ?? "non versionné";
    document.getElementById("versions").textContent =
      `Interface v${VERSION_UI} · modèle ${versionModele}`;

    etat.hidden = true;
    for (const id of ["semaine", "execution", "pied"]) {
      document.getElementById(id).hidden = false;
    }
  } catch (err) {
    etat.textContent = `Impossible de charger les prévisions (${err.message}). Réessaie dans quelques minutes.`;
  }
}

function rafraichirSiPertinent() {
  const h = heureMontreal();
  const primee = Date.now() - derniereMaj >= RAFRAICHIR_MS - 30000;
  if (primee && h >= RAFRAICHIR_DE && h <= RAFRAICHIR_A) demarrer();
}

if (typeof document !== "undefined") {
  demarrer();
  // Rafraîchissement horaire (6 h–22 h, heure de Montréal) tant que la page
  // est ouverte + mise à jour immédiate quand on revient sur l'onglet.
  // pageshow couvre la restauration d'onglet par Safari (bfcache), où
  // visibilitychange ne se déclenche pas toujours : sans lui, une page
  // laissée ouverte la veille réafficherait le rendu d'hier au matin.
  setInterval(rafraichirSiPertinent, 5 * 60 * 1000);
  const reveil = () => {
    const perime = Date.now() - derniereMaj > 30 * 60 * 1000
      || (dateAffichee && dateAffichee !== dateMontreal());
    if (!perime) return;
    // `pageshow` se déclenche aussi à l'ouverture, avant que la première
    // prévision ne soit arrivée : derniereMaj vaut encore 0 et la page passe
    // ici. Compter ce cas ferait un événement par page vue, qui ne dirait
    // rien. Seul un vrai retour sur une page déjà servie compte.
    if (derniereMaj) window.track?.("foil-forecast-refresh", {});
    demarrer();
  };
  document.addEventListener("visibilitychange", () => { if (!document.hidden) reveil(); });
  window.addEventListener("pageshow", reveil);
}

// Export pour tests hors navigateur (node tests/test_dashboard.js)
if (typeof module !== "undefined") {
  module.exports = { fenetresDuJour, secteurDe, horizonPour, corrige,
                     construireHeures, directionFiable, flecheSVG,
                     regulariteFenetres, iconeMeteo, resumeMeteoJour };
}
