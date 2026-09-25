/* 臺灣防空識別區航情圖 — Taiwan ADIZ traffic map.
   Airspace, routes, waypoints and aerodromes: AIP Taiwan (ais.caa.gov.tw).
   ATC sector frequencies west of the Strait: AIP CHINA ENR 2.1.3 / 2.2.1.
   Research and training use only — not for navigation.                      */
(function () {
'use strict';
const D = window.__TW__;
const el = id => document.getElementById(id);
const esc = t => String(t == null ? '' : t).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ── state ─────────────────────────────────────────────────────────────── */
const S = {
  basemap: 'vector', awy: true, wpt: false, apt: true, adiz: true, fir: true,
  lab: true, sec: false, gnd: true,
  key: '', feed: '', interval: 30, query: '',
  flights: [], byHex: new Map(), trails: new Map(),
  selected: null, feedKind: 'demo', note: '',
};

/* ── geometry ──────────────────────────────────────────────────────────── */
const R2D = 180 / Math.PI, D2R = Math.PI / 180;
function inRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
const inBox = (lon, lat, b) => lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3];
function destination(lat, lon, brgDeg, distNm) {
  const d = distNm / 3440.065, b = brgDeg * D2R, p1 = lat * D2R, l1 = lon * D2R;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1),
                             Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [p2 * R2D, ((l2 * R2D + 540) % 360) - 180];
}
function gcNm(a1, o1, a2, o2) {
  const h = Math.sin((a2 - a1) * D2R / 2) ** 2 +
    Math.cos(a1 * D2R) * Math.cos(a2 * D2R) * Math.sin((o2 - o1) * D2R / 2) ** 2;
  return 2 * 3440.065 * Math.asin(Math.sqrt(h));
}
function bearing(a1, o1, a2, o2) {
  const p1 = a1 * D2R, p2 = a2 * D2R, dl = (o2 - o1) * D2R;
  return (Math.atan2(Math.sin(dl) * Math.cos(p2),
    Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)) * R2D + 360) % 360;
}

/* ── formatting ────────────────────────────────────────────────────────── */
const grp = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const ftOf = m => (m == null ? null : Math.round(m / 0.3048));
function flOf(ft) { return ft == null ? '—' : 'FL' + String(Math.round(ft / 100)).padStart(3, '0'); }
function dms(lon, lat) {
  const one = (v, isLat) => {
    const h = isLat ? (v >= 0 ? 'N' : 'S') : (v >= 0 ? 'E' : 'W');
    v = Math.abs(v);
    const d = Math.floor(v), m = Math.floor((v - d) * 60), s = (v - d - m / 60) * 3600;
    return h + String(d).padStart(isLat ? 2 : 3, '0') + '°' +
           String(m).padStart(2, '0') + "'" + s.toFixed(1).padStart(4, '0') + '"';
  };
  return one(lat, true) + ' ' + one(lon, false);
}

/* ── controlling unit / frequency ──────────────────────────────────────── */
const ZONES = D.zones.features;
const ADIZ = ZONES.find(z => z.properties.kind === 'ADIZ').geometry.coordinates[0];
const FIR = ZONES.find(z => z.properties.kind === 'FIR').geometry.coordinates[0];
const SECTORS = D.sectors || [];

function verticalHas(s, altM) {
  if (altM == null || s.upper_m == null) return false;
  const hi = s.upper_ref === 'QNH' ? s.upper_m : s.upper_m;
  const lo = s.lower_m || 0;
  return (s.lower_exclusive ? altM > lo : altM >= lo) &&
         (s.upper_exclusive ? altM < hi : altM <= hi);
}
function controllingUnit(lon, lat, altM) {
  const inFir = inRing(lon, lat, FIR);
  const hits = SECTORS.filter(s => inBox(lon, lat, s.bbox) && inRing(lon, lat, s.ring));
  const rank = s => (s.kind === 'APP' ? 0 : 1) * 1e9 + s.area_km2;
  const ok = hits.filter(s => verticalHas(s, altM)).sort((a, b) => rank(a) - rank(b));
  if (ok.length) {
    const s = ok[0];
    return { kind: 'sector', sector: s, unit: s.acc_cn + ' / ' + s.acc_en,
             callsign: s.callsign_en, freq: s.freq_mhz, sec: s.freq_sec_mhz,
             detail: s.id, inFir };
  }
  if (inFir) {
    const u = D.units.find(x => x.scope === 'fir');
    return { kind: 'fir', unit: u.name_zh + ' / ' + u.name_en, callsign: u.callsign,
             freqs: u.freqs, emergency: u.emergency, inFir: true };
  }
  return { kind: 'none', inFir: false };
}

/* ── hit testing ────────────────────────────────────────────────────────
   deck.gl picks by reading back a colour-coded frame, and that read comes
   back empty in some embeddings (an Artifact frame among them) — a click
   would then never select anything. Aircraft are few and their positions are
   already in hand, so the nearest-within-N-pixels test is done here instead,
   in plain JS, which works wherever the map draws at all.                   */
let SHOWN = [];
function viewport() {
  const box = el('scope').getBoundingClientRect();
  return new deck.WebMercatorViewport(Object.assign(
    { width: box.width || 900, height: box.height || 600 }, viewState));
}
/** The aircraft under (x, y) in scope pixels, or null. */
function hitTest(x, y, slack) {
  if (!SHOWN.length || !window.deck || !deck.WebMercatorViewport) return null;
  let vp;
  try { vp = viewport(); } catch (e) { return null; }
  const now = Date.now(), lim = (slack || 20) ** 2;
  let best = null, bd = lim;
  for (let i = 0; i < SHOWN.length; i++) {
    const f = SHOWN[i], pr = projected(f, now);
    let p;
    try { p = vp.project([pr[0], pr[1]]); } catch (e) { continue; }
    const d = (p[0] - x) ** 2 + (p[1] - y) ** 2;
    if (d < bd) { bd = d; best = f; }
  }
  return best;
}

/* ── aircraft symbol ─────────────────────────────────────────────────────
   The aircraft are real geometry, not icons. deck.gl's IconLayer has to pull
   its atlas in through fetch(), and a fetch() of a data: URL is refused when
   the page runs inside a sandboxed frame — the planes then never appear even
   though every other layer draws. A polygon needs no texture at all, so this
   always renders. Shape below is a plan-view airliner in a unit square, nose
   on +y (north); planePolygon() turns it into degrees at a fixed pixel size. */
const PLANE = [[32, 2], [35.4, 13], [35.4, 25.4], [61, 40.6], [61, 46.6], [35.4, 38.3],
               [35.4, 52], [42, 57.7], [42, 62.3], [32, 59.2], [22, 62.3], [22, 57.7],
               [28.6, 52], [28.6, 38.3], [3, 46.6], [3, 40.6], [28.6, 25.4], [28.6, 13]]
  .map(p => [(p[0] - 32) / 64, (32 - p[1]) / 64]);

/** Silhouette around lon/lat: `px` pixels long, nose on `hdg`° true.
    Web Mercator at zoom z puts 360/(512·2^z) degrees of longitude in a pixel;
    a degree of latitude covers cos(lat) as much ground, hence the sy term. */
function planePolygon(lon, lat, hdg, px, zoom) {
  const sx = px * 360 / (512 * Math.pow(2, zoom));
  const sy = sx * Math.cos(lat * D2R);
  const th = (hdg || 0) * D2R, c = Math.cos(th), s = Math.sin(th);
  const out = new Array(PLANE.length);
  for (let i = 0; i < PLANE.length; i++) {
    const u = PLANE[i][0], v = PLANE[i][1];
    out[i] = [lon + (u * c + v * s) * sx, lat + (v * c - u * s) * sy];
  }
  return out;
}

/* ── view bounds: the ADIZ, and nothing beyond it ──────────────────────── */
const B = D.bbox;                               // [west, south, east, north]
let VIEW0 = { longitude: (B[0] + B[2]) / 2, latitude: (B[1] + B[3]) / 2,
              zoom: 5.6, pitch: 0, bearing: 0 };
const LIMITS = { west: B[0], south: B[1], east: B[2], north: B[3],
                 minZoom: 4.5, maxZoom: 12 };
/** Size the opening view so the whole ADIZ fits, and make that the zoom-out
    floor — the map then cannot be pushed anywhere the zone is not visible. */
function fitToADIZ() {
  const box = el('scope');
  const w = box.clientWidth || 900, h = box.clientHeight || 600;
  try {
    const vp = new deck.WebMercatorViewport({ width: w, height: h });
    const f = vp.fitBounds([[B[0], B[1]], [B[2], B[3]]], { padding: Math.min(48, w / 12) });
    VIEW0 = { longitude: f.longitude, latitude: f.latitude, zoom: f.zoom,
              pitch: 0, bearing: 0 };
    LIMITS.minZoom = f.zoom - 0.25;
  } catch (e) { /* older bundle: keep the default */ }
  return VIEW0;
}
const clampView = v => Object.assign({}, v, {
  longitude: Math.min(Math.max(v.longitude, LIMITS.west), LIMITS.east),
  latitude: Math.min(Math.max(v.latitude, LIMITS.south), LIMITS.north),
  zoom: Math.min(Math.max(v.zoom, LIMITS.minZoom), LIMITS.maxZoom),
  pitch: Math.min(Math.max(v.pitch || 0, 0), 60),
});
let viewState = Object.assign({}, VIEW0);

/* ── theme ─────────────────────────────────────────────────────────────── */
const light = () => document.documentElement.dataset.theme === 'light';
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function rgb(hex) {
  const h = hex.replace('#', '');
  const v = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
}

/* ── layers ────────────────────────────────────────────────────────────── */
const TILES = {
  dark: ['https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png',
         'https://b.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png',
         'https://c.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png'],
  light: ['https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png',
          'https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png',
          'https://c.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png'],
};
/** The base. 'vector' is the coastline carried inside this page — it needs no
    network at all, so it is the only one that always draws; raster tiles have
    to be fetched, which a restricted embedding (an Artifact frame) refuses. */
function basemapLayer() {
  if (S.basemap === 'none' || !window.deck) return [];
  if (S.basemap === 'tiles') {
    const url = TILES[light() ? 'light' : 'dark'];
    if (!deck.TileLayer) return [];
    return [new deck.TileLayer({
      id: 'tiles-' + (light() ? 'light' : 'dark'), data: url,
      minZoom: 0, maxZoom: 19, tileSize: 256,
      pickable: false, onTileError: () => {},
      renderSubLayers: p => {
        const { west, south, east, north } = p.tile.bbox;
        return new deck.BitmapLayer(p, { data: null, image: p.data,
                                         bounds: [west, south, east, north] });
      },
    })];
  }
  const theme = light() ? 1 : 0;
  return [new deck.PolygonLayer({
    id: 'land', data: D.land || [], getPolygon: d => d,
    filled: true, stroked: true,
    getFillColor: [...T.land, 255], getLineColor: [...T.coast, 255],
    getLineWidth: 1, lineWidthUnits: 'pixels', lineWidthMinPixels: 0.6,
    pickable: false, parameters: { depthTest: false },
    updateTriggers: { getFillColor: theme, getLineColor: theme } })];
}

function matches(f) {
  if (!S.query) return true;
  const q = S.query.toUpperCase();
  return (f.callsign || '').toUpperCase().includes(q) ||
         (f.registration || '').toUpperCase().includes(q) ||
         (f.type || '').toUpperCase().includes(q) ||
         (f.dep || '').toUpperCase().includes(q) || (f.arr || '').toUpperCase().includes(q);
}

/** Dead-reckon between feed updates so aircraft glide instead of jumping.
    Extrapolation is capped: a stale target stops moving rather than drifting. */
function projected(f, now) {
  const age = (now - f.t) / 1000;
  if (!(f.gs_kt > 30) || f.track == null || age <= 0) return [f.lon, f.lat, age];
  const capped = Math.min(age, 120);
  const [la, lo] = destination(f.lat, f.lon, f.track, f.gs_kt * capped / 3600);
  return [lo, la, age];
}

let T = {};
function readTokens() {
  const g = n => css(n) || '#888888';
  T = { awy: rgb(g('--awy')), wpt: rgb(g('--wpt')), apt: rgb(g('--apt')),
        adiz: rgb(g('--adiz')), fir: rgb(g('--fir')), ground: rgb(g('--ground')),
        land: rgb(g('--land')), coast: rgb(g('--coast')),
        ac: rgb(g('--ac')), acSel: rgb(g('--ac-sel')), acGnd: rgb(g('--ac-gnd')) };
}
function buildLayers() {
  readTokens();
  const L = basemapLayer();

  if (S.awy) {
    L.push(new deck.PathLayer({
      id: 'awy', data: D.routes, getPath: d => d.path,
      getColor: [...T.awy, 190], getWidth: 1,
      widthUnits: 'pixels', widthMinPixels: 1, pickable: true }));
    L.push(new deck.TextLayer({
      id: 'awy-t',
      data: ((viewState && viewState.zoom) || 6) < 5.8 ? [] :
        D.routes.map(r => ({ r, p: r.path[Math.floor(r.path.length / 2)] })),
      getPosition: d => d.p, getText: d => d.r.designator, getSize: 10,
      sizeUnits: 'pixels', getColor: [...T.awy, 235],
      fontFamily: '"IBM Plex Mono", monospace', getPixelOffset: [0, -7] }));
  }
  if (S.wpt) {
    L.push(new deck.ScatterplotLayer({
      id: 'wpt', data: D.waypoints, getPosition: d => [d.lon, d.lat],
      getFillColor: [...T.wpt, 210], getRadius: 2,
      radiusUnits: 'pixels', radiusMinPixels: 2, pickable: true }));
    L.push(new deck.TextLayer({
      id: 'wpt-t', data: D.waypoints, getPosition: d => [d.lon, d.lat],
      getText: d => d.name, getSize: 9, sizeUnits: 'pixels',
      getColor: [...T.wpt, 225], getPixelOffset: [0, -8],
      fontFamily: '"IBM Plex Mono", monospace' }));
  }
  if (S.sec && D.sectors) {
    L.push(new deck.PolygonLayer({
      id: 'sec', data: D.sectors, getPolygon: d => d.ring, filled: true, stroked: true,
      extruded: false, getFillColor: d => [...d.colour, 16],
      getLineColor: d => [...d.colour, 120], lineWidthMinPixels: 1, pickable: true }));
  }
  if (S.fir) {
    L.push(new deck.PathLayer({
      id: 'fir', data: [{ path: FIR }], getPath: d => d.path,
      getColor: [...T.fir, 150], getWidth: 1.4,
      widthUnits: 'pixels', widthMinPixels: 1 }));
  }
  if (S.adiz) {
    L.push(new deck.PathLayer({
      id: 'adiz', data: [{ path: ADIZ }], getPath: d => d.path,
      getColor: [...T.adiz, 225], getWidth: 2.2,
      widthUnits: 'pixels', widthMinPixels: 2 }));
  }
  if (S.apt) {
    const ap = D.aerodromes.filter(a => a.in_adiz);
    L.push(new deck.ScatterplotLayer({
      id: 'apt', data: ap, getPosition: d => [d.lon, d.lat],
      getFillColor: [...T.apt, 235], getRadius: 3.2,
      radiusUnits: 'pixels', radiusMinPixels: 3, stroked: true,
      getLineColor: [...T.ground, 230], lineWidthMinPixels: 1, pickable: true }));
    L.push(new deck.TextLayer({
      id: 'apt-t', data: ap, getPosition: d => [d.lon, d.lat],
      getText: d => d.icao, getSize: 10, sizeUnits: 'pixels',
      getColor: [...T.apt, 240], getPixelOffset: [0, -10],
      fontFamily: '"IBM Plex Mono", monospace' }));
  }

  // trail of the selected flight, drawn under the aircraft
  const sel = S.selected && S.byHex.get(S.selected);
  if (sel) {
    const tr = S.trails.get(S.selected);
    if (tr && tr.length > 1)
      L.push(new deck.PathLayer({
        id: 'trail', data: [{ path: tr }], getPath: d => d.path,
        getColor: [...T.ac, 190], getWidth: 2,
        widthUnits: 'pixels', widthMinPixels: 2 }));
  }

  const now = Date.now();
  const zoom = (viewState && viewState.zoom) || 6;
  const shown = S.flights.filter(f => matches(f) && (S.gnd || !f.onGround));
  SHOWN = shown;
  const rows = shown.map(f => {
    const [lon, lat, age] = projected(f, now);
    return { f, pos: [lon, lat], age,
             sel: S.selected === f.hex,
             col: S.selected === f.hex ? T.acSel
                : f.onGround ? T.acGnd : T.ac };
  });
  rows.forEach(d => { d.poly = planePolygon(d.pos[0], d.pos[1], d.f.track,
                                            d.sel ? 27 : 20, zoom); });
  if (rows.length) {
    L.push(new deck.PolygonLayer({
      id: 'ac', data: rows, getPolygon: d => d.poly,
      filled: true, stroked: true,
      getFillColor: d => [...d.col, d.age > 180 ? 120 : 255],
      getLineColor: [...T.ground, 200], getLineWidth: 1,
      lineWidthUnits: 'pixels', lineWidthMinPixels: 0.7,
      pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 150],
      updateTriggers: { getFillColor: [S.selected, S.basemap],
                        getLineColor: S.basemap } }));
  }
  // at low zoom 30 labels turn into a smear — show the selected one only
  const labelRows = zoom >= 6.4 ? rows : rows.filter(d => d.sel);
  if (S.lab && labelRows.length) {
    L.push(new deck.TextLayer({
      id: 'ac-t', data: labelRows, getPosition: d => d.pos,
      getText: d => d.f.callsign, getSize: d => (d.sel ? 12 : 10.5), sizeUnits: 'pixels',
      getColor: d => [...d.col, 245], getPixelOffset: [0, -16],
      fontFamily: '"IBM Plex Mono", monospace', background: true,
      getBackgroundColor: [...T.ground, light() ? 190 : 150],
      backgroundPadding: [3, 1],
      updateTriggers: { getColor: [S.selected, S.basemap], getSize: S.selected } }));
  }
  return L;
}

/* ── deck ──────────────────────────────────────────────────────────────── */
let dk = null;
function tooltip({ object, layer }) {
  if (!object) return null;
  const style = { background: css('--panel'), color: css('--ink'),
                  border: '1px solid ' + css('--line'), borderRadius: '7px',
                  padding: '6px 9px', fontSize: '12px', lineHeight: '1.45',
                  fontFamily: 'Archivo, system-ui, sans-serif', maxWidth: '240px' };
  if (layer.id === 'ac') {
    const f = object.f;
    return { html: '<b style="font-family:var(--mono)">' + esc(f.callsign) + '</b> ' +
      esc(f.type || '') + '<br>' + esc(f.dep || '?') + ' → ' + esc(f.arr || '?') +
      '<br>' + flOf(ftOf(f.alt_m)) + ' · ' + (f.gs_kt ? Math.round(f.gs_kt) + ' kt' : '—'),
      style };
  }
  if (layer.id === 'apt') return { html: '<b>' + object.icao +
    (object.iata ? ' / ' + object.iata : '') + '</b><br>' + esc(object.name_zh) + '<br>' +
    esc(object.name_en), style };
  if (layer.id === 'awy') return { html: '<b>' + object.designator + '</b><br>' +
    object.points.length + ' 個定位點' +
    (object.order_confidence !== 'high' ? '<br><span style="color:' + css('--warn') +
     '">點序為推算，待查</span>' : ''), style };
  if (layer.id === 'wpt') return { html: '<b>' + object.name + '</b><br>' +
    object.type.toUpperCase() + (object.facility ? ' · ' + esc(object.facility) : ''), style };
  if (layer.id === 'sec') return { html: '<b>' + object.id + '</b><br>' +
    esc(object.acc_cn) + '<br>' + (object.freq_mhz ? object.freq_mhz + ' MHz' : '—'), style };
  return null;
}
/** Credit whichever base is actually on screen. */
function attribution() {
  const n = el('attrib');
  if (!n) return;
  n.hidden = S.basemap === 'none';
  n.textContent = S.basemap === 'tiles' ? '© OpenStreetMap · © CARTO'
                                        : '海岸線 Natural Earth';
}
let DIAG = [];
function diag(msg) {
  DIAG.push(String(msg).slice(0, 160));
  DIAG = DIAG.slice(-4);
  const n = el('feed-note');
  if (n) { n.textContent = DIAG.join(' | '); n.style.display = ''; }
}
let rafId = 0, builtZoom = null;
/** Coalesce zoom-driven rebuilds into one per frame. */
function scheduleRender() {
  if (rafId) return;
  rafId = requestAnimationFrame(() => {
    rafId = 0;
    const z = (viewState && viewState.zoom) || 6;
    if (builtZoom == null || Math.abs(z - builtZoom) > 0.005) render();
  });
}
function render() {
  if (!dk) return;
  builtZoom = (viewState && viewState.zoom) || 6;
  let layers = [];
  try { layers = buildLayers(); }
  catch (e) { diag('layers: ' + (e && e.message)); return; }
  dk.setProps({ layers });
  const n = S.flights.filter(f => matches(f) && (S.gnd || !f.onGround)).length;
  el('s-count').innerHTML = '<b>' + n + '</b> 架';
  if (S.selected) paintPanel();
}

/* ── flight panel ──────────────────────────────────────────────────────── */
function paintPanel() {
  const f = S.byHex.get(S.selected);
  const box = el('fp');
  if (!f) { box.hidden = true; return; }
  const ft = ftOf(f.alt_m);
  const u = controllingUnit(f.lon, f.lat, f.alt_m);
  const apt = c => D.aerodromes.find(a => a.icao === c || a.iata === c);
  const side = (code, name, right) =>
    '<div class="' + (right ? 'to' : '') + '"><div class="code">' + esc(code || '—') +
    '</div><div class="nm">' + esc(name || '') + '</div></div>';
  const dp = apt(f.dep), ar = apt(f.arr);
  let freq;
  if (u.kind === 'sector') {
    freq = '<div class="freqbox"><div class="v">' + (u.freq || '—') + '<small>MHz</small></div>' +
      '<div class="u">' + esc(u.callsign) + ' · ' + u.detail +
      (u.sec ? ' · 備用 ' + u.sec : '') + '</div></div>';
  } else if (u.kind === 'fir') {
    freq = '<div class="freqbox"><div class="v" style="font-size:1.05rem">' +
      esc(u.callsign) + '</div><div class="u">' + esc(u.unit) +
      '<br>公布頻率 ' + u.freqs.slice(0, 6).join(' · ') + ' …（AIP 未分扇區公布）</div></div>';
  } else {
    freq = '<div class="freqbox none"><div class="v" style="font-size:1.05rem">識別區外</div>' +
      '<div class="u">Outside the Taiwan ADIZ</div></div>';
  }
  box.innerHTML =
    '<header><div><div class="cs">' + esc(f.callsign) + '</div>' +
      '<div class="sub">' + esc(f.type || '—') + ' · ' + esc(f.registration || '—') +
      (f.demo ? ' · DEMO' : '') + '</div></div>' +
      '<button class="x" id="fp-x" aria-label="關閉">✕</button></header>' +
    '<div class="route">' + side(f.dep, dp ? dp.name_zh : '') +
      '<div class="arr">→</div>' + side(f.arr, ar ? ar.name_zh : '', true) + '</div>' +
    freq +
    '<div class="grid">' +
      '<div class="cell"><k>高度 ALT</k><v>' + (ft == null ? '—' : grp(ft)) +
        '<small>ft</small></v></div>' +
      '<div class="cell"><k>FL</k><v>' + flOf(ft) + '</v></div>' +
      '<div class="cell"><k>地速 GS</k><v>' + (f.gs_kt ? Math.round(f.gs_kt) : '—') +
        '<small>kt</small></v></div>' +
      '<div class="cell"><k>航跡 TRK</k><v>' +
        (f.track == null ? '—' : String(Math.round(f.track)).padStart(3, '0') + '°') + '</v></div>' +
      '<div class="cell"><k>升降 V/S</k><v>' + (f.vs_fpm == null ? '—' : Math.round(f.vs_fpm)) +
        '<small>fpm</small></v></div>' +
      '<div class="cell"><k>squawk</k><v>' + esc(f.squawk || '—') + '</v></div>' +
    '</div>' +
    '<div class="note">' + dms(f.lon, f.lat) + ' · ' +
      (u.inFir ? '臺北飛航情報區 Taipei FIR' : '情報區外') +
      ' · 更新於 ' + Math.max(0, Math.round((Date.now() - f.t) / 1000)) + ' 秒前</div>';
  box.hidden = false;
  el('fp-x').onclick = () => { S.selected = null; box.hidden = true; render(); };
}
function select(hex) { S.selected = hex; paintPanel(); render(); }

/* ── traffic ───────────────────────────────────────────────────────────── */
/* Two 250 NM discs cover the whole ADIZ box (21–29 N, 117.5–123 E). */
const DISCS = [[23.0, 120.0, 250], [27.2, 120.3, 250]];
const RAPID_HOST = 'adsbexchange-com1.p.rapidapi.com';
const sleep = ms => new Promise(r => setTimeout(r, ms));

function feedUrl(lat, lon, dist) {
  if (S.feed) return S.feed.replace('{lat}', lat).replace('{lon}', lon).replace('{dist}', dist);
  return 'https://' + RAPID_HOST + '/v2/lat/' + lat + '/lon/' + lon + '/dist/' + dist + '/';
}
async function jget(url) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 9000);
  const headers = (!S.feed && S.key)
    ? { 'X-RapidAPI-Key': S.key, 'X-RapidAPI-Host': RAPID_HOST } : {};
  try {
    const r = await fetch(url, { signal: ctl.signal, headers });
    if (r.status === 401 || r.status === 403) { const e = new Error('auth'); e.kind = 'auth'; throw e; }
    if (r.status === 429) { const e = new Error('quota'); e.kind = 'quota'; throw e; }
    const ct = r.headers.get('content-type') || '';
    if (!ct.includes('json')) { const e = new Error('http'); e.kind = 'http'; throw e; }
    return await r.json();
  } catch (e) {
    if (e.name === 'TypeError') e.kind = 'cors';
    else if (e.name === 'AbortError') e.kind = 'timeout';
    throw e;
  } finally { clearTimeout(timer); }
}
function adopt(a, now) {
  const ab = a.alt_baro;
  const onGround = ab === 'ground';
  return {
    hex: a.hex, callsign: (a.flight || '').trim() || (a.r || a.hex || '').toUpperCase(),
    registration: (a.r || '').trim(), type: (a.t || '').trim(),
    lat: +a.lat, lon: +a.lon,
    alt_m: onGround ? 0 : (ab == null ? null : +ab * 0.3048),
    onGround, gs_kt: a.gs, track: a.track ?? a.true_heading,
    vs_fpm: a.baro_rate ?? a.geom_rate, squawk: a.squawk,
    dep: null, arr: null, demo: false, t: now,
  };
}
async function fetchLive() {
  const now = Date.now(), seen = new Map();
  let lastErr = null, ok = 0;
  for (let i = 0; i < DISCS.length; i++) {
    if (i) await sleep(400);
    try {
      const js = await jget(feedUrl(DISCS[i][0], DISCS[i][1], DISCS[i][2]));
      ok++;
      for (const a of (js.ac || js.aircraft || [])) {
        if (!a.hex || a.lat == null || a.lon == null || seen.has(a.hex)) continue;
        if (!inBox(+a.lon, +a.lat, B)) continue;      // keep it to the ADIZ
        seen.set(a.hex, adopt(a, now));
      }
    } catch (e) {
      lastErr = e;
      if (e.kind === 'cors' || e.kind === 'auth' || e.kind === 'timeout') throw e;
    }
  }
  if (!ok) throw lastErr || Object.assign(new Error('network'), { kind: 'network' });
  return [...seen.values()];
}

/* adsbdb.com is CORS-enabled, so the origin/destination lookup works from a
   static page even when the position feed does not. */
const ROUTE_CACHE = new Map();
async function fillRoutes(list) {
  const todo = list.filter(f => f.callsign && !f.demo && !ROUTE_CACHE.has(f.callsign)).slice(0, 12);
  await Promise.all(todo.map(async f => {
    try {
      const r = await fetch('https://api.adsbdb.com/v0/callsign/' + encodeURIComponent(f.callsign));
      const j = await r.json();
      const fr = j && j.response && j.response.flightroute;
      ROUTE_CACHE.set(f.callsign, fr
        ? { dep: fr.origin && fr.origin.icao_code, arr: fr.destination && fr.destination.icao_code }
        : null);
    } catch (e) { ROUTE_CACHE.set(f.callsign, null); }
  }));
  list.forEach(f => {
    const c = ROUTE_CACHE.get(f.callsign);
    if (c) { f.dep = f.dep || c.dep; f.arr = f.arr || c.arr; }
  });
}

/* ── demo traffic: flown along the published airways ───────────────────── */
const DEMO = [
  ['CAL742', 'B738', 'B591', 1, 'RCTP', 'RJAA'], ['EVA188', 'B77W', 'B591', 1, 'RCTP', 'RJTT'],
  ['JAL814', 'B788', 'B591', 0, 'RJAA', 'RCTP'], ['ANA851', 'B789', 'B591', 0, 'RJTT', 'RCTP'],
  ['CPA472', 'A359', 'M750', 1, 'VHHH', 'RJTT'], ['CAL221', 'A333', 'M750', 0, 'RJBB', 'VHHH'],
  ['SIA877', 'B77W', 'A1', 1, 'WSSS', 'RJTT'],   ['EVA271', 'A321', 'A1', 0, 'RJTT', 'RCTP'],
  ['KAL691', 'B772', 'R583', 1, 'RKSI', 'VHHH'], ['UAL872', 'B789', 'R595', 1, 'RCTP', 'KSFO'],
  ['CXA8322', 'B738', 'W6', 1, 'ZSAM', 'RCTP'],  ['CES5133', 'A320', 'W2', 0, 'ZSFZ', 'RCTP'],
  ['CSN3172', 'B738', 'W4', 1, 'ZSAM', 'RCKH'],  ['CAL504', 'B738', 'W8', 0, 'ZSFZ', 'RCSS'],
  ['UIA236', 'A321', 'B591', 1, 'RCKH', 'RCTP'], ['TTW102', 'ATR7', 'W4', 0, 'RCQC', 'RCTP'],
  ['SJX712', 'A321', 'Q11', 1, 'RCTP', 'RPLL'],  ['CAL631', 'A333', 'Q13', 1, 'RCTP', 'VTBS'],
  ['EVA398', 'B788', 'G581', 1, 'RCTP', 'VHHH'], ['CPA451', 'A333', 'G581', 0, 'VHHH', 'RCTP'],
  ['FDX5150', 'B77F', 'B576', 1, 'RCTP', 'RKSI'],['ABW992', 'B748', 'R596', 1, 'RCTP', 'UUEE'],
  ['CAL5201', 'B744', 'A577', 0, 'VHHH', 'RCKH'],['JNA613', 'B738', 'Q12', 1, 'RCKH', 'RKPC'],
  ['THA632', 'A359', 'Q14', 0, 'VTBS', 'RCTP'],  ['MDA632', 'ERJ1', 'W8', 1, 'RCFG', 'RCSS'],
  ['CAL308', 'A359', 'G587', 1, 'RCTP', 'RKSI'], ['EVA672', 'A333', 'R200', 1, 'RCTP', 'ZGGG'],
];
const ROUTE_BY = Object.fromEntries(D.routes.map(r => [r.designator, r]));
function demoFlights(t) {
  const out = [];
  DEMO.forEach(([cs, typ, rte, dir, dep, arr], i) => {
    const R = ROUTE_BY[rte];
    if (!R || R.path.length < 2) return;
    const legs = [];
    let total = 0;
    for (let k = 0; k < R.path.length - 1; k++) {
      const d = gcNm(R.path[k][1], R.path[k][0], R.path[k + 1][1], R.path[k + 1][0]);
      legs.push(d); total += d;
    }
    const speed = 440 + (i % 5) * 18;
    const period = total / speed * 3600;
    let ph = ((t / period) + i * 0.0917) % 1;
    if (!dir) ph = 1 - ph;
    let want = ph * total, k = 0;
    while (k < legs.length - 1 && want > legs[k]) { want -= legs[k]; k++; }
    const fr = legs[k] ? want / legs[k] : 0;
    const a = R.path[k], b = R.path[k + 1];
    const lon = a[0] + (b[0] - a[0]) * fr, lat = a[1] + (b[1] - a[1]) * fr;
    const trk = dir ? bearing(a[1], a[0], b[1], b[0]) : bearing(b[1], b[0], a[1], a[0]);
    const cruise = [9450, 10050, 10650, 11250, 11900][i % 5];
    const edge = Math.min(ph, 1 - ph);
    const alt = edge < 0.06 ? cruise * (0.25 + 0.75 * edge / 0.06) : cruise;
    out.push({ hex: 'DEMO' + i, callsign: cs, type: typ,
               registration: 'B-' + (16000 + i * 37), lat, lon, alt_m: Math.round(alt),
               onGround: false, gs_kt: speed, track: Math.round(trk),
               vs_fpm: edge < 0.06 ? (ph < 0.5 ? 1900 : -1700) : 0,
               squawk: String(1000 + ((i * 137) % 6000)), dep, arr,
               demo: true, t: Date.now() });
  });
  return out;
}

/* ── refresh ───────────────────────────────────────────────────────────── */
const WHY = {
  auth: ['金鑰無效或未訂閱', 'RapidAPI 回應 401/403：請確認已在 RapidAPI 訂閱 adsbexchange-com1，且金鑰正確。'],
  quota: ['配額用盡', 'RapidAPI 回應 429。降低更新頻率，或等配額重置。'],
  cors: ['來源未開放跨域', '這個端點沒有送 Access-Control-Allow-Origin，靜態網頁讀不到。改用 ADS-B Exchange（RapidAPI）或你自己的 CORS 端點。'],
  timeout: ['連線逾時', '端點 9 秒內沒有回應。'],
  http: ['回應格式不符', '端點回傳的不是 JSON。'],
  network: ['無法連線', '請檢查網路連線。'],
};
function setFeed(kind, text) {
  const p = el('s-feed');
  p.className = 'stat ' + (kind === 'live' ? 'live' : 'demo');
  p.innerHTML = '<i class="dot"></i>' + text;
  S.feedKind = kind;
}
function ingest(list) {
  const keep = new Map();
  list.forEach(f => keep.set(f.hex, f));
  // trails accumulate across refreshes; drop aircraft that have left
  list.forEach(f => {
    const tr = S.trails.get(f.hex) || [];
    const last = tr[tr.length - 1];
    if (!last || gcNm(last[1], last[0], f.lat, f.lon) > 0.3) tr.push([f.lon, f.lat]);
    if (tr.length > 60) tr.shift();
    S.trails.set(f.hex, tr);
  });
  for (const hex of [...S.trails.keys()]) if (!keep.has(hex)) S.trails.delete(hex);
  S.flights = list;
  S.byHex = keep;
  if (S.selected && !keep.has(S.selected)) { S.selected = null; el('fp').hidden = true; }
}
function showNote(t) {
  S.note = t || '';
  const n = el('feed-note');
  if (n) { n.textContent = S.note; n.style.display = S.note ? '' : 'none'; }
}
async function refresh() {
  if (!S.key && !S.feed) {
    ingest(demoFlights(Date.now() / 1000));
    setFeed('demo', '示範資料 DEMO');
    showNote('尚未設定實時來源。在「設定」貼上 RapidAPI 金鑰，或填入你自己的 CORS 端點，即可切換為實時航班。');
    render(); return;
  }
  try {
    const list = await fetchLive();
    await fillRoutes(list);
    ingest(list);
    setFeed('live', list.length ? '實時 LIVE' : '實時 LIVE · 區內 0 架');
    showNote(list.length ? '' :
      '連線正常，但此刻識別區內沒有被 ADS-B 接收到的航班。');
  } catch (e) {
    const [head, why] = WHY[e.kind] || WHY.network;
    ingest(demoFlights(Date.now() / 1000));
    setFeed('demo', head + ' → DEMO');
    showNote(why);
  }
  render();
}
function safeRefresh() {
  return refresh().catch(err => {
    ingest(demoFlights(Date.now() / 1000));
    setFeed('demo', '示範資料 DEMO');
    showNote('載入實時資料時發生錯誤：' + (err && err.message ? err.message : err));
    render();
  });
}

/* ── wiring ────────────────────────────────────────────────────────────── */
function press(n, on) { n.setAttribute('aria-pressed', on ? 'true' : 'false'); }
function syncChips() {
  [['c-awy', 'awy'], ['c-apt', 'apt'], ['c-adiz', 'adiz'], ['c-sec', 'sec']]
    .forEach(([id, k]) => { const n = el(id); if (n) press(n, S[k]); });
  [['t-awy', 'awy'], ['t-wpt', 'wpt'], ['t-apt', 'apt'], ['t-adiz', 'adiz'],
   ['t-fir', 'fir'], ['t-lab', 'lab'], ['t-sec', 'sec'], ['t-gnd', 'gnd']]
    .forEach(([id, k]) => { const n = el(id); if (n) n.checked = S[k]; });
}
function wire() {
  [['c-awy', 'awy'], ['c-apt', 'apt'], ['c-adiz', 'adiz'], ['c-sec', 'sec']]
    .forEach(([id, k]) => { el(id).onclick = () => { S[k] = !S[k]; syncChips(); render(); }; });
  [['t-awy', 'awy'], ['t-wpt', 'wpt'], ['t-apt', 'apt'], ['t-adiz', 'adiz'],
   ['t-fir', 'fir'], ['t-lab', 'lab'], ['t-sec', 'sec'], ['t-gnd', 'gnd']]
    .forEach(([id, k]) => {
      const n = el(id); if (!n) return;
      n.onchange = e => { S[k] = e.target.checked; syncChips(); render(); };
    });
  document.querySelectorAll('[data-bm]').forEach(b => b.onclick = () => {
    S.basemap = b.dataset.bm;
    document.querySelectorAll('[data-bm]').forEach(x => press(x, x === b));
    attribution();
    render();
  });
  el('scope').addEventListener('click', ev => {
    const r = el('scope').getBoundingClientRect();
    const f = hitTest(ev.clientX - r.left, ev.clientY - r.top, 20);
    if (f) { select(f.hex); return; }
    if (S.selected) { S.selected = null; el('fp').hidden = true; render(); }
  });
  el('q').oninput = e => { S.query = e.target.value.trim(); render(); };
  el('b-set').onclick = () => {
    const sh = el('sheet'); sh.hidden = !sh.hidden; press(el('b-set'), !sh.hidden);
  };
  el('b-theme').onclick = () => {
    document.documentElement.dataset.theme = light() ? 'dark' : 'light';
    render();
  };
  el('b-reset').onclick = () => {
    viewState = Object.assign({}, VIEW0, { transitionDuration: 500 });
    dk.setProps({ initialViewState: viewState });
    render();
  };
  const keyIn = el('s-key'), feedIn = el('s-feed-url');
  try {
    S.key = localStorage.getItem('tw_adiz_key') || '';
    S.feed = localStorage.getItem('tw_adiz_feed') || '';
  } catch (e) { /* private window */ }
  const qs = new URLSearchParams(location.search);
  if (qs.get('key')) S.key = qs.get('key');
  if (qs.get('feed')) S.feed = qs.get('feed');
  if (keyIn) keyIn.value = S.key;
  if (feedIn) feedIn.value = S.feed;
  el('b-key').onclick = () => {
    S.key = keyIn.value.trim();
    try { localStorage.setItem('tw_adiz_key', S.key); } catch (e) {}
    safeRefresh();
  };
  el('b-key-clear').onclick = () => {
    S.key = ''; keyIn.value = '';
    try { localStorage.removeItem('tw_adiz_key'); } catch (e) {}
    safeRefresh();
  };
  el('b-feed').onclick = () => {
    S.feed = feedIn.value.trim();
    try { localStorage.setItem('tw_adiz_feed', S.feed); } catch (e) {}
    safeRefresh();
  };
  el('s-int').onchange = e => { S.interval = +e.target.value; schedule(); };
  const warn = D.routes.filter(r => r.order_confidence !== 'high').map(r => r.designator);
  const w = el('awy-warn');
  if (w) w.textContent = warn.length ? '（' + warn.join('、') + ' 的點序信心較低）' : '';
  syncChips();
}

let timer = null;
function schedule() {
  if (timer) clearInterval(timer);
  timer = setInterval(safeRefresh, S.interval * 1000);
}

/* ── boot ──────────────────────────────────────────────────────────────── */
window.__TW_BOOT = function () {
  addEventListener('error', e => diag('js: ' + (e.message || e.type)));
  addEventListener('unhandledrejection', e => diag('promise: ' +
    (e.reason && e.reason.message ? e.reason.message : e.reason)));
  if (!(window.deck && deck.DeckGL)) {
    el('scope').innerHTML = '<div class="fallback"><h2>地圖引擎未載入</h2>' +
      '<p>本頁需要從 CDN 載入 deck.gl。請檢查網路連線後重新整理。</p></div>';
    return;
  }
  viewState = fitToADIZ();
  dk = new deck.DeckGL({
    container: el('scope'), initialViewState: viewState,
    controller: { dragRotate: false },
    onViewStateChange: ({ viewState: vs }) => {
      viewState = clampView(vs);
      scheduleRender();      // aircraft are sized in pixels: rebuild on zoom
      return viewState;      // deck applies the returned state
    },
    layers: [], getTooltip: tooltip,
    onError: e => diag('deck: ' + (e && e.message)),
    onClick: ({ object, layer }) => {           // used when GPU picking works
      if (layer && layer.id === 'ac' && object) select(object.f.hex);
    },
  });
  wire();
  attribution();
  ingest(demoFlights(Date.now() / 1000));
  setFeed('demo', '示範資料 DEMO');
  render();
  safeRefresh();
  schedule();
  // demo traffic animates; live traffic is dead-reckoned between updates
  setInterval(() => {
    if (S.feedKind === 'demo') ingest(demoFlights(Date.now() / 1000));
    render();
  }, 1000);
  let rt = null;
  addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => {
      const keep = viewState.zoom;
      const fitted = fitToADIZ();
      if (keep <= LIMITS.minZoom + 0.3) {      // was showing the whole zone
        viewState = fitted;
        dk.setProps({ initialViewState: viewState });
      }
      render();
    }, 200);
  });
};
})();
