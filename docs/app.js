/* Dashboard vent Lac Maskinongé.
 *
 * Architecture de fraîcheur : les prévisions brutes sont récupérées EN DIRECT
 * chez Open-Meteo à chaque ouverture (CORS, sans clé), puis re-rafraîchies
 * automatiquement toutes les heures entre 7 h et 17 h (heure de Montréal)
 * tant que la page est ouverte. Les corrections (biais/poids par modèle et
 * horizon) viennent de poids_modeles.json, recalibré chaque semaine par le
 * cron — le cron ne sert jamais à l'affichage. Tous les seuils du sport sont
 * lus dans poids_modeles.json (section sport).
 */
"use strict";

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

// Auto-rafraîchissement : chaque heure entre 7 h et 17 h (heure de Montréal)
const RAFRAICHIR_DE = 7, RAFRAICHIR_A = 17, RAFRAICHIR_MS = 60 * 60 * 1000;

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
   * icône dominante, cumul de pluie, drapeau orage. */
  const codes = jour.map((h) => h.meteoCode).filter((c) => c != null);
  if (!codes.length) return null;
  const orage = codes.some((c) => CODES_ORAGE.includes(c));
  const pluie = jour.reduce((s, h) => s + (h.pluie ?? 0), 0);
  const probMax = Math.max(...jour.map((h) => h.probPluie ?? 0));
  // Icône du "pire" moment hors orage (le plus couvert/mouillé), pour ne pas
  // afficher soleil quand l'après-midi est sous la pluie.
  const dominant = Math.max(...codes.filter((c) => !CODES_ORAGE.includes(c)), 0);
  let texte;
  if (pluie < 0.5) texte = probMax >= 40 ? `risque d'averses (${probMax} %)` : "sec";
  else if (pluie < 5) texte = `un peu de pluie (${pluie.toFixed(0)} mm)`;
  else if (pluie < 15) texte = `pluie (${pluie.toFixed(0)} mm)`;
  else texte = `grosse pluie (${pluie.toFixed(0)} mm)`;
  return { icone: iconeMeteo(orage ? 95 : dominant), texte, orage, pluie };
}

// --------------------------------------------------------------- ensemble

function construireHeures(donnees, meteo, poids) {
  /* Retourne une liste d'objets {t, jourISO, heure, decalage, parModele,
   * ensemble, rafales, direction, divergence, meteoCode, pluie, probPluie}
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

function heureMontreal() {
  return Number(new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Toronto", hour: "2-digit", hour12: false,
  }).format(new Date()));
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
  /* Bande heure par heure (8 h–20 h) : vent, rafales, météo, orage. */
  const cellules = analyse.jour
    .filter((h) => h.decalage > 0 || h.heure >= Math.max(sport.heure_debut, heureCourante))
    .map((h) => {
      const orage = CODES_ORAGE.includes(h.meteoCode);
      return `<div class="cellule ${classeHeure(h, sport)}${orage ? " orage" : ""}">
        <span class="ch">${h.heure} h</span>
        <span class="cv">${h.ensemble != null ? h.ensemble.toFixed(0) : "—"}</span>
        <span class="cr">${h.rafales != null ? `raf ${h.rafales.toFixed(0)}` : ""}</span>
        <span class="cm">${orage ? "⚡" : iconeMeteo(h.meteoCode)}</span>
      </div>`;
    });
  if (!cellules.length) return `<p class="aide">journée navigable terminée</p>`;
  return `<div class="bande-heures">${cellules.join("")}</div>`;
}

function ligneMeteo(meteo) {
  if (!meteo) return "";
  const orage = meteo.orage
    ? ` <span class="orage-badge">⚡ risque d'orages — pas d'eau à ce moment-là</span>` : "";
  return `<p class="meteo">${meteo.icone} ${meteo.texte}${orage}</p>`;
}

function rendreSemaine(heures, poids, sport) {
  const conteneur = document.getElementById("cartes-semaine");
  conteneur.innerHTML = "";
  const jours = [...new Set(heures.map((h) => h.jourISO))].slice(0, 7);
  for (const jourISO of jours) {
    const a = analyseJour(heures, jourISO, sport);
    if (!a.jour.length) continue;
    const decalage = a.jour[0].decalage;
    const go = a.fenetres.length > 0;
    const conf = confianceGo(decalage, poids);
    const d = new Date(`${jourISO}T12:00`);
    const milieu = a.jour[Math.floor(a.jour.length / 2)];

    const carte = document.createElement("article");
    carte.className = "carte";
    const etiquettes = [];
    if (go && a.regularite) etiquettes.push(
      `<span class="etiquette ${a.regularite.classe}">${a.regularite.niveau}</span>`);
    if (a.heuresDivergentes >= 2) etiquettes.push(`<span class="etiquette">modèles divisés</span>`);
    carte.innerHTML = `
      <div class="entete">
        <span class="jour">${decalage === 0 ? "aujourd'hui" : decalage === 1 ? "demain" : JOURS[d.getDay()]}</span>
        <span class="date">${d.getDate()}/${d.getMonth() + 1}</span>
        <span class="badge ${go ? "go" : "no"}">${go && conf != null ? `GO · ${conf} %` : go ? "GO" : "NO"}</span>
      </div>
      <p class="resume">${fleche(milieu.direction)} ${etiquetteFenetre(a, sport)}</p>
      <div class="rangee-blocs">${Object.entries(a.blocs).map(([nom, b]) => {
        const valeur = b.vent > 0
          ? `${b.vent.toFixed(0)}<small> / raf ${b.rafales.toFixed(0)}</small>` : "—";
        return `<div class="bloc ${b.go ? "go" : ""}">
          <span class="nom-bloc">${LIBELLES_BLOCS[nom] ?? nom}</span>
          <span class="valeur">${valeur}</span></div>`;
      }).join("")}</div>
      ${ligneMeteo(a.meteo)}
      ${etiquettes.length ? `<div class="etiquettes">${etiquettes.join("")}</div>` : ""}`;
    conteneur.appendChild(carte);
  }
}

function rendreExecution(heures, sport) {
  const conteneur = document.getElementById("blocs-jours");
  conteneur.innerHTML = "";
  const heureCourante = heureMontreal();
  const jours = [...new Set(heures.map((h) => h.jourISO))].slice(0, 2);
  jours.forEach((jourISO, idx) => {
    const a = analyseJour(heures, jourISO, sport);
    if (!a.jour.length) return;
    const div = document.createElement("div");
    div.className = "jour-blocs";
    const chips = [];
    if (a.regularite) chips.push(
      `<span class="etiquette ${a.regularite.classe}">${a.regularite.niveau}</span>`);
    div.innerHTML = `<div class="titre-jour">${idx === 0 ? "aujourd'hui" : "demain"}
        ${chips.join("")}</div>`
      + bandeHoraire(a, sport, heureCourante)
      + ligneMeteo(a.meteo);
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
    avis.textContent = `⚠️ Les modèles s'écartent de plus de ${SEUIL_DIVERGENCE} nds pendant `
      + `${divergentes.length} h sur les 48 prochaines heures — verdict moins fiable que d'habitude.`;
  }
}

function rendreGraphique(heures, sport) {
  const h48 = heures.filter((h) => h.decalage <= 1);
  const L = 720, H = 260, mg = { g: 30, d: 8, h: 12, b: 34 };
  const larg = L - mg.g - mg.d, haut = H - mg.h - mg.b;
  const maxY = Math.max(20, ...h48.map((h) => h.ensemble ?? 0),
                        ...h48.flatMap((h) => Object.values(h.parModele))) + 1;
  const x = (i) => mg.g + (i / (h48.length - 1)) * larg;
  const y = (v) => mg.h + haut - (v / maxY) * haut;

  const chemin = (points) => points
    .map((p, i) => (p == null ? null : `${i === 0 || points[i - 1] == null ? "M" : "L"}${x(i).toFixed(1)},${y(p).toFixed(1)}`))
    .filter(Boolean).join(" ");

  let svg = `<svg viewBox="0 0 ${L} ${H}" width="100%" style="min-width:640px" role="img" aria-label="Vent prévu sur 48 heures, par modèle et ensemble corrigé">`;
  svg += `<rect x="${mg.g}" y="${y(sport.vent_max)}" width="${larg}" height="${y(sport.vent_min) - y(sport.vent_max)}" fill="var(--bande)"/>`;

  // Heures déjà passées : grisées, avec un repère « maintenant »
  const heureCourante = heureMontreal();
  const iMaintenant = h48.findIndex((h) => h.decalage === 0 && h.heure === heureCourante);
  if (iMaintenant > 0) {
    svg += `<rect x="${mg.g}" y="${mg.h}" width="${x(iMaintenant) - mg.g}" height="${haut}" fill="var(--passe)"/>`
      + `<line x1="${x(iMaintenant)}" x2="${x(iMaintenant)}" y1="${mg.h}" y2="${H - mg.b}" stroke="var(--maintenant)" stroke-width="1.6"/>`
      + `<text x="${x(iMaintenant) + 4}" y="${mg.h + 10}" font-size="10" fill="var(--maintenant)">maintenant</text>`;
  }

  for (const v of [0, 5, 10, 15, 20].filter((v) => v <= maxY)) {
    svg += `<line x1="${mg.g}" x2="${L - mg.d}" y1="${y(v)}" y2="${y(v)}" stroke="var(--bordure)" stroke-width="0.7"/>`
      + `<text x="${mg.g - 5}" y="${y(v) + 3}" text-anchor="end" font-size="10" fill="var(--texte-3)">${v}</text>`;
  }
  for (let i = 0; i < h48.length; i++) {
    if (h48[i].heure % 6 === 0) {
      svg += `<text x="${x(i)}" y="${H - mg.b + 14}" text-anchor="middle" font-size="10" fill="var(--texte-3)">${h48[i].heure} h</text>`;
    }
    if (h48[i].heure === 0 && i > 0) {
      svg += `<line x1="${x(i)}" x2="${x(i)}" y1="${mg.h}" y2="${H - mg.b}" stroke="var(--bordure)" stroke-width="1" stroke-dasharray="3 3"/>`
        + `<text x="${x(i) + 4}" y="${H - mg.b + 28}" font-size="10" fill="var(--texte-2)">demain</text>`;
    }
  }
  svg += `<text x="${mg.g + 4}" y="${H - mg.b + 28}" font-size="10" fill="var(--texte-2)">aujourd'hui</text>`;
  for (const m of Object.keys(MODELES)) {
    const points = h48.map((h) => h.parModele[m] ?? null);
    if (points.every((p) => p == null)) continue;
    svg += `<path d="${chemin(points)}" fill="none" stroke="var(--m-${m})" stroke-width="1.3" opacity="0.55"/>`;
  }
  svg += `<path d="${chemin(h48.map((h) => h.ensemble))}" fill="none" stroke="var(--ensemble)" stroke-width="2.6"/>`;
  svg += `<g id="curseur" style="display:none"><line y1="${mg.h}" y2="${H - mg.b}" stroke="var(--texte-3)" stroke-width="1"/>`
    + `<circle r="4" fill="var(--ensemble)"/>`
    + `<rect width="170" height="20" rx="4" fill="var(--surface-carte)" stroke="var(--bordure)"/>`
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
    const tx = Math.min(Math.max(x(i) - 85, mg.g), L - 178);
    const boite = curseur.querySelector("rect");
    boite.setAttribute("x", tx); boite.setAttribute("y", mg.h);
    const texte = curseur.querySelector("text");
    texte.setAttribute("x", tx + 7); texte.setAttribute("y", mg.h + 14);
    texte.textContent = `${hh.decalage === 0 ? "auj." : "dem."} ${hh.heure} h · `
      + `vent ${hh.ensemble.toFixed(1)}`
      + (hh.rafales != null ? ` · raf ${hh.rafales.toFixed(0)} nds` : " nds");
  };
  el.addEventListener("mousemove", bouger);
  el.addEventListener("touchstart", bouger, { passive: true });
  el.addEventListener("touchmove", bouger, { passive: true });
  el.addEventListener("mouseleave", () => { curseur.style.display = "none"; });

  const legende = document.getElementById("legende");
  legende.innerHTML = `<span><i style="background:var(--ensemble);height:4px"></i>Ensemble corrigé</span>`
    + Object.entries(MODELES).map(
      ([m, nom]) => `<span><i style="background:var(--m-${m})"></i>${nom}</span>`).join("");
}

// ---------------------------------------------------------------- démarrage

let derniereMaj = 0;

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
    rendreExecution(heures, sport);
    rendreGraphique(heures, sport);
    rendreSemaine(heures, poids, sport);
    derniereMaj = Date.now();

    const maintenant = new Date();
    document.getElementById("fraicheur").textContent =
      `Prévisions chargées en direct le ${maintenant.toLocaleDateString("fr-CA")} à `
      + `${maintenant.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })} `
      + "(dernier run disponible de chaque modèle) — la page se rafraîchit "
      + `toute seule chaque heure entre ${RAFRAICHIR_DE} h et ${RAFRAICHIR_A} h.`;
    document.getElementById("recalibrage").textContent =
      `Le % d'un GO = la part des GO annoncés à cette échéance qui se sont `
      + `réellement confirmés (mesuré sur ${poids.periode_backtest}). `
      + `Dernier recalibrage des corrections : ${poids.genere_le}.`;

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
  // Rafraîchissement horaire (7 h–17 h, heure de Montréal) tant que la page
  // est ouverte + mise à jour immédiate quand on revient sur l'onglet.
  setInterval(rafraichirSiPertinent, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && Date.now() - derniereMaj > 30 * 60 * 1000) demarrer();
  });
}

// Export pour tests hors navigateur (node tests/test_dashboard.js)
if (typeof module !== "undefined") {
  module.exports = { fenetresDuJour, secteurDe, horizonPour, corrige,
                     regulariteFenetres, iconeMeteo, resumeMeteoJour };
}
