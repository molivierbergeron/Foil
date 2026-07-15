/* Dashboard vent Lac Maskinongé.
 *
 * Architecture de fraîcheur : les prévisions brutes sont récupérées EN DIRECT
 * chez Open-Meteo à chaque ouverture (CORS, sans clé). Les corrections
 * (biais/poids par modèle et horizon) viennent de poids_modeles.json,
 * recalibré chaque semaine par le cron — le cron ne sert jamais à l'affichage.
 * Tous les seuils du sport sont lus dans poids_modeles.json (section sport).
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
const SEUIL_DIVERGENCE = 5; // nds d'écart entre modèles = mention de divergence

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

// --------------------------------------------------------------- ensemble

function construireHeures(donnees, poids) {
  /* Retourne une liste d'objets {t, jourISO, heure, decalage, parModele,
   * ensemble, rafales, direction, divergence} en heure locale du spot. */
  const temps = donnees.hourly.time;
  const aujourdhui = temps[0].slice(0, 10);
  const ratioDefaut = poids.ratio_rafales_defaut ?? 1.6;
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
    });
  }
  return heures;
}

function analyseJour(heures, jourISO, sport) {
  const jour = heures.filter((h) => h.jourISO === jourISO
    && h.heure >= sport.heure_debut && h.heure < sport.heure_fin);
  const vents = jour.map((h) => h.ensemble);
  const fenetres = fenetresDuJour(vents, sport);
  const dansBande = (v) => v != null && v >= sport.vent_min && v <= sport.vent_max;
  // Rafaleux si la MAJORITÉ des heures en bande de la fenêtre le sont —
  // une seule heure limite ne doit pas étiqueter toute la journée.
  let nBande = 0, nRafaleuses = 0;
  for (const [d, f] of fenetres) {
    for (let i = d; i < f; i++) {
      const h = jour[i];
      if (!dansBande(h.ensemble)) continue;
      nBande++;
      if (h.rafales != null && h.rafales / h.ensemble > sport.ratio_rafaleux) nRafaleuses++;
    }
  }
  const rafaleux = nBande > 0 && nRafaleuses / nBande > 0.5;
  const heuresDivergentes = jour.filter((h) => h.divergence > SEUIL_DIVERGENCE).length;
  const max = Math.max(...vents.filter((v) => v != null), 0);
  return { jour, fenetres, rafaleux, heuresDivergentes, max };
}

// ---------------------------------------------------------------- verdicts

function texteConfiance(decalage, poids) {
  const h = decalage <= 1 ? "24h" : decalage === 2 ? "48h" : "96h";
  const fiab = poids.fiabilite_go_par_horizon?.[h];
  if (!fiab) return "";
  const bas = Math.round(fiab.ic95[0] * 10);
  const haut = Math.round(fiab.ic95[1] * 10);
  const quand = { "24h": "à moins de 2 jours", "48h": "à 2 jours", "96h": "à 3-4 jours" }[h];
  const fourchette = bas === haut ? `environ ${bas}` : `entre ${bas} et ${haut}`;
  return `À cet horizon (${quand}), ${fourchette} GO sur 10 se confirment.`;
}

function etiquetteFenetre(analyse, sport) {
  if (!analyse.fenetres.length) {
    return analyse.max >= sport.vent_marginal
      ? `max ${analyse.max.toFixed(0)} nds — sous la bande`
      : "petit temps";
  }
  const [d, f] = analyse.fenetres.reduce((a, b) => (b[1] - b[0] > a[1] - a[0] ? b : a));
  const debut = analyse.jour[d].heure, fin = analyse.jour[f - 1].heure + 1;
  const pic = Math.max(...analyse.jour.slice(d, f).map((h) => h.ensemble));
  return `fenêtre ${debut} h–${fin} h, pic ${pic.toFixed(0)} nds`;
}

function fleche(direction) {
  if (direction == null) return "";
  // Direction d'où vient le vent -> flèche pointant où il va
  const fleches = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"];
  return fleches[Math.floor(((direction + 22.5) % 360) / 45)];
}

// ----------------------------------------------------------------- rendu

function rendreSemaine(heures, poids, sport) {
  const conteneur = document.getElementById("cartes-semaine");
  const jours = [...new Set(heures.map((h) => h.jourISO))].slice(0, 7);
  for (const jourISO of jours) {
    const a = analyseJour(heures, jourISO, sport);
    if (!a.jour.length) continue;
    const decalage = a.jour[0].decalage;
    const go = a.fenetres.length > 0;
    const d = new Date(`${jourISO}T12:00`);
    const milieu = a.jour[Math.floor(a.jour.length / 2)];

    const carte = document.createElement("article");
    carte.className = "carte";
    const etiquettes = [];
    if (go && a.rafaleux) etiquettes.push("rafaleux");
    if (a.heuresDivergentes >= 2) etiquettes.push("modèles divisés");
    carte.innerHTML = `
      <div class="entete">
        <span class="jour">${decalage === 0 ? "aujourd'hui" : decalage === 1 ? "demain" : JOURS[d.getDay()]}</span>
        <span class="date">${d.getDate()}/${d.getMonth() + 1}</span>
        <span class="badge ${go ? "go" : "no"}">${go ? "GO" : "NO"}</span>
      </div>
      <p class="resume">${fleche(milieu.direction)} ${etiquetteFenetre(a, sport)}</p>
      ${go ? `<p class="confiance">${texteConfiance(decalage, poids)}</p>` : ""}
      ${etiquettes.length ? `<div class="etiquettes">${etiquettes.map((e) => `<span class="etiquette">${e}</span>`).join("")}</div>` : ""}`;
    conteneur.appendChild(carte);
  }
}

function rendreBlocs(heures, sport) {
  const conteneur = document.getElementById("blocs-jours");
  const jours = [...new Set(heures.map((h) => h.jourISO))].slice(0, 2);
  jours.forEach((jourISO, idx) => {
    const a = analyseJour(heures, jourISO, sport);
    if (!a.jour.length) return;
    const div = document.createElement("div");
    div.className = "jour-blocs";
    const chips = Object.entries(sport.blocs).map(([nom, [debutB, finB]]) => {
      // Un bloc est GO si une fenêtre le recouvre d'au moins 1 h dans la bande
      let goBloc = false, pic = 0;
      for (const [d, f] of a.fenetres) {
        for (let i = d; i < f; i++) {
          const h = a.jour[i];
          if (h.heure >= debutB && h.heure < finB
              && h.ensemble >= sport.vent_min && h.ensemble <= sport.vent_max) {
            goBloc = true;
            pic = Math.max(pic, h.ensemble);
          }
        }
      }
      const libelle = { matin: "matin", apres_midi: "après-midi", soiree: "soirée" }[nom] ?? nom;
      return `<div class="bloc ${goBloc ? "go" : ""}">${libelle}
        <span class="valeur">${goBloc ? `GO · ${pic.toFixed(0)} nds` : "—"}</span></div>`;
    });
    div.innerHTML = `<div class="titre-jour">${idx === 0 ? "aujourd'hui" : "demain"}</div>
      <div class="rangee-blocs">${chips.join("")}</div>`;
    conteneur.appendChild(div);
  });

  // Mention de divergence sur les 48 h affichées
  const h48 = heures.filter((h) => h.decalage <= 1);
  const divergentes = h48.filter(
    (h) => h.heure >= sport.heure_debut && h.heure < sport.heure_fin
      && h.divergence > SEUIL_DIVERGENCE);
  if (divergentes.length >= 2) {
    const avis = document.getElementById("divergence");
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
  svg += `<g id="curseur" hidden><line y1="${mg.h}" y2="${H - mg.b}" stroke="var(--texte-3)" stroke-width="1"/>`
    + `<rect width="120" height="20" rx="4" fill="var(--surface-carte)" stroke="var(--bordure)"/>`
    + `<text font-size="11" fill="var(--texte)"></text></g>`;
  svg += `</svg>`;
  const cadre = document.getElementById("graphique");
  cadre.innerHTML = svg;

  // Survol / toucher : curseur + valeur de l'ensemble
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
    curseur.hidden = false;
    curseur.querySelector("line").setAttribute("x1", x(i));
    curseur.querySelector("line").setAttribute("x2", x(i));
    const tx = Math.min(x(i) + 6, L - 126);
    const boite = curseur.querySelector("rect");
    boite.setAttribute("x", tx); boite.setAttribute("y", mg.h);
    const texte = curseur.querySelector("text");
    texte.setAttribute("x", tx + 6); texte.setAttribute("y", mg.h + 14);
    texte.textContent = `${hh.decalage === 0 ? "auj." : "dem."} ${hh.heure} h : ${hh.ensemble.toFixed(1)} nds`;
  };
  el.addEventListener("mousemove", bouger);
  el.addEventListener("touchstart", bouger, { passive: true });
  el.addEventListener("touchmove", bouger, { passive: true });
  el.addEventListener("mouseleave", () => { curseur.hidden = true; });

  const legende = document.getElementById("legende");
  legende.innerHTML = `<span><i style="background:var(--ensemble);height:4px"></i>Ensemble corrigé</span>`
    + Object.entries(MODELES).map(
      ([m, nom]) => `<span><i style="background:var(--m-${m})"></i>${nom}</span>`).join("");
}

// ---------------------------------------------------------------- démarrage

async function demarrer() {
  const etat = document.getElementById("etat");
  try {
    const poids = await (await fetch("poids_modeles.json")).json();
    const sport = poids.sport;
    const url = "https://api.open-meteo.com/v1/forecast"
      + `?latitude=${poids.spot.latitude}&longitude=${poids.spot.longitude}`
      + "&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m"
      + `&models=${Object.keys(MODELES).join(",")}`
      + "&wind_speed_unit=kn&timezone=America%2FToronto&forecast_days=7";
    const rep = await fetch(url);
    if (!rep.ok) throw new Error(`Open-Meteo HTTP ${rep.status}`);
    const donnees = await rep.json();

    const heures = construireHeures(donnees, poids);
    rendreSemaine(heures, poids, sport);
    rendreBlocs(heures, sport);
    rendreGraphique(heures, sport);

    const maintenant = new Date();
    document.getElementById("fraicheur").textContent =
      `Prévisions chargées en direct le ${maintenant.toLocaleDateString("fr-CA")} à `
      + `${maintenant.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })} `
      + "(dernier run disponible de chaque modèle).";
    document.getElementById("recalibrage").textContent =
      `Corrections calibrées sur ${poids.periode_backtest} — dernier recalibrage des poids : ${poids.genere_le}.`;

    etat.hidden = true;
    for (const id of ["semaine", "execution", "pied"]) {
      document.getElementById(id).hidden = false;
    }
  } catch (err) {
    etat.textContent = `Impossible de charger les prévisions (${err.message}). Réessaie dans quelques minutes.`;
  }
}

if (typeof document !== "undefined") demarrer();

// Export pour tests hors navigateur (node tests/test_dashboard.mjs)
if (typeof module !== "undefined") {
  module.exports = { fenetresDuJour, secteurDe, horizonPour, corrige };
}
