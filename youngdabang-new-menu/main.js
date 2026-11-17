// 청년다방 신메뉴 — watercolor menu journal. Pure function of t; everything built under fixed seeds in init.
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const C = window.CONTENT;
window.DUR = 30.0;
const TEAL = '#55AAB8';               // the one accent (brand BI colour): stamps only
const DX = [0, 1500, 3000];           // dish centres along the one long sheet (world x)
let PAPER_IMG;

// ---------- timeline (seconds) ----------
const T = {
  q0: .25, q1: 1.55, drop: 2.2, mist: 3.5,
  d: [
    { wash: 3.7, bowl: [3.3, 4.5], fill: [4.2, 5.7], top: [5.1, 6.4], fin: [5.9, 6.7], tag: 4.9, name: 5.0, note: 6.0, stamp: 7.5 },
    { wash: 10.3, bowl: [11.0, 12.1], fill: [11.9, 13.4], top: [13.3, 14.1], fin: [13.9, 14.5], tag: 12.4, name: 12.5, note: 13.4, stamp: 16.25, pull: [14.6, 15.8] },
    { wash: 17.5, bowl: [19.0, 19.9], fill: [20.0, 20.55], top: [20.5, 21.3], fin: [21.1, 21.7], tag: 19.9, name: 20.0, note: 20.7, stamp: 22.5 },
  ],
  hush: 23.75, pull: [24.4, 26.6], title: 25.1, sub: 25.45, labels: 25.8, seal: 27.5,
};

// ---------- camera: one world → screen function ----------
const camX = monotone([[0, -40], [2.6, -40], [5.0, 250], [10.0, 262], [11.8, DX[1] + 250], [17.9, DX[1] + 262], [19.4, DX[2] + 250], [24.4, DX[2] + 258], [26.6, DX[1]], [30, DX[1]]]);
const camY = monotone([[0, 10], [2.6, 10], [5.0, 20], [10.0, 20], [24.4, 20], [26.6, 40], [30, 40]]);
const camZ = monotone([[0, 2.4], [2.4, 2.6], [5.0, 1.25], [10.0, 1.3], [11.8, 1.25], [17.9, 1.31], [19.4, 1.25], [24.4, 1.29], [26.6, .5], [30, .51]]);
let CX, CY, CZ;
function setCam(t) { CX = camX(t); CY = camY(t); CZ = camZ(t); }
const sx = wx => (wx - CX) * CZ + 960, sy = wy => (wy - CY) * CZ + 560;
function worldXf(ox = 0) { ctx.setTransform(CZ, 0, 0, CZ, (ox - CX) * CZ + 960, -CY * CZ + 560); }
function screenXf() { ctx.setTransform(1, 0, 0, 1, 0, 0); }

// ---------- helpers ----------
const ell = (cx, cy, rx, ry, n = 48, a0 = 0, a1 = Math.PI * 2) => { const o = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; o.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]); } return o; };
function offscreen(x0, y0, x1, y1, fn) {
  const c2 = document.createElement('canvas'); c2.width = Math.ceil(x1 - x0); c2.height = Math.ceil(y1 - y0);
  const c = c2.getContext('2d'); c.translate(-x0, -y0); fn(c); return { cv: c2, x0, y0, x1, y1 };
}
// a watercolour wash: 3 jittered passes + a pooled darker edge
function washOn(c, pts, fill, a, passes = 3, jit = 5, edge = null) {
  for (let p = 0; p < passes; p++) {
    c.beginPath(); pts.forEach(([x, y], i) => { const xx = x + rnd(-jit, jit), yy = y + rnd(-jit, jit); i ? c.lineTo(xx, yy) : c.moveTo(xx, yy); });
    c.closePath(); c.globalAlpha = a / passes * 1.6; c.fillStyle = fill; c.fill();
    if (edge) { c.globalAlpha = .22; c.strokeStyle = edge; c.lineWidth = 2.2; c.stroke(); }
  }
  c.globalAlpha = 1;
}
function washSprite(polys, pad = 30) {   // polys: [{pts, fill, a, jit, edge}]
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const q of polys) for (const [x, y] of q.pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return offscreen(x0 - pad, y0 - pad, x1 + pad, y1 + pad, c => { for (const q of polys) washOn(c, q.pts, q.fill, q.a, q.passes ?? 3, q.jit ?? 5, q.edge); });
}
const drawSpr = (s, a = 1) => { if (a <= 0) return; ctx.globalAlpha = a; ctx.drawImage(s.cv, s.x0, s.y0); ctx.globalAlpha = 1; };
// wobbly circular reveal (pigment spreading): clip radius r around (cx,cy)
function blobClip(cx, cy, r, seed) {
  ctx.beginPath();
  for (let i = 0; i <= 64; i++) { const a = i / 64 * Math.PI * 2, k = 1 + .16 * (vnoise(seed + i * .35) - .5) + .08 * Math.sin(a * 5 + seed); const x = cx + Math.cos(a) * r * k, y = cy + Math.sin(a) * r * k * .62; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  ctx.closePath(); ctx.clip();
}
// brush-edge wipe: a wavy vertical edge travelling left → right (local coords)
function wipeClip(x0, x1, y0, y1, p, seed) {
  const e = lerp(x0 - 60, x1 + 60, eio(p));
  ctx.beginPath(); ctx.moveTo(x0 - 80, y0);
  for (let y = y0; y <= y1; y += 30) ctx.lineTo(e + 50 * (vnoise(seed + y * .01) - .5) + 18 * Math.sin(y * .02 + seed), y);
  ctx.lineTo(x0 - 80, y1); ctx.closePath(); ctx.clip();
}
// a layer: stroke list painted in over [t0,t1], then a cached sprite
function layer(S, t0, t1) { return { S, t0, t1, spr: S.length ? sprite(S) : null }; }
function drawLayer(L, t) {
  const p = seg(t, L.t0, L.t1); if (p <= 0 || !L.spr) return;
  if (p < 1) drawList(ctx, L.S, p); else ctx.drawImage(L.spr.cv, L.spr.x0, L.spr.y0);
}

// ---------- the three dishes (local coords, centre 0,0) ----------
const D = [];
function crumbs(S, cx, cy, rx, ry, n, cols, w0 = 4, w1 = 8) { clump(S, cx, cy, Math.max(rx, ry), n, cols, { sx: rx / Math.max(rx, ry), sy: ry / Math.max(rx, ry), l0: 5, l1: 11, w0, w1, a0: .55, a1: .9 }); }

function buildTteok() {
  const g = {};
  g.bg = washSprite([{ pts: ell(40, 0, 700, 330, 40), fill: '#f2d3c6', a: .32, jit: 26 }], 60);
  // the sauce (the pigment drop that blooms)
  g.sauce = washSprite([
    { pts: ell(0, -14, 292, 124, 56), fill: '#d8705f', a: .78, jit: 4, edge: '#a8443a' },
    { pts: ell(-30, -30, 200, 80, 40), fill: '#e99a86', a: .45, jit: 8 },
    { pts: ell(40, 10, 150, 50, 30), fill: '#c95a4c', a: .28, jit: 10 },
  ]);
  // bowl: shading washes + rim strokes
  const bowlW = washSprite([
    { pts: [...ell(0, -20, 334, 152, 40, 0, Math.PI), ...qctrl(-334, -20, 0, 260, 334, -20, 30).reverse()], fill: '#9fb0ba', a: .38, jit: 3 },
    { pts: [...ell(0, -20, 334, 152, 40, Math.PI, Math.PI * 2), ...ell(0, -14, 296, 126, 40, Math.PI * 2, Math.PI)], fill: '#b9c4c8', a: .3, jit: 2 },
  ]);
  const B = [];
  B.push(mk(ell(0, -20, 336, 154, 60), 6, '#7d8a92', { prof: 'even', nb: 2, a: .8, rough: .3 }));
  B.push(mk(qctrl(-336, -18, 0, 262, 336, -18, 40), 7, '#6f7c84', { prof: 'even', nb: 3, a: .78 }));
  B.push(mk(ell(0, -14, 298, 128, 50, Math.PI * 1.05, Math.PI * 1.95), 4, '#8b969c', { prof: 'brush', nb: 0, a: .6 }));
  B.push(mk(qctrl(-120, 150, 0, 178, 120, 150, 12), 9, '#7d8a92', { prof: 'even', nb: 3, a: .55 }));   // foot
  g.bowlW = bowlW; g.bowl = layer(B, ...T.d[0].bowl);
  // rice cakes: thick short cylinders, sauce-coated edges
  const F = [];
  for (let i = 0; i < 17; i++) {
    const a = rnd(0, Math.PI * 2), rr = Math.sqrt(rnd()), x = Math.cos(a) * rr * 215, y = -14 + Math.sin(a) * rr * 82;
    const d = rnd(-.5, .5) + (rnd() < .5 ? 0 : Math.PI / 2.4), L = rnd(70, 96);
    const s = mk(qcurve(x - Math.cos(d) * L / 2, y - Math.sin(d) * L / 2 * .55, x + Math.cos(d) * L / 2, y + Math.sin(d) * L / 2 * .55, rnd(-4, 4), 8), rnd(25, 31), '#f5e3cd', { prof: 'even', nb: 3, a: .96, rib: .95, rough: .12 });
    F.push(s); F.push(edgeOf(s, 1, 7, '#c9604f', .8)); F.push(edgeOf(s, -1, 3, '#e9a58e', .55));
  }
  g.fill = layer(F, ...T.d[0].fill);
  // chadol (thin brisket) slices + fat streaks
  const P = [];
  for (let i = 0; i < 7; i++) {
    const x = rnd(-200, 200), y = -14 + rnd(-70, 60), d = rnd(-.6, .6), L = rnd(80, 120);
    const pts = []; for (let k = 0; k <= 10; k++) { const u = k / 10 - .5; pts.push([x + Math.cos(d) * L * u, y + Math.sin(d) * L * u * .5 + Math.sin(u * 9 + i) * 6]); }
    const s = mk(pts, rnd(30, 38), '#a9584f', { prof: 'leaf', nb: 4, a: .9, rough: .35 });
    P.push(s); P.push(edgeOf(s, 1, 4, '#f1d6c8', .85)); P.push(edgeOf(s, -1, 2.5, '#6e2f2a', .6));
  }
  g.top = layer(P, ...T.d[0].top);
  // green onion, sesame, pepper flakes
  const G = [];
  clump(G, -10, -20, 190, 26, ['#6f9a4e', '#a9c46c', '#86ad58'], { sx: 1.15, sy: .42, l0: 8, l1: 16, w0: 6, w1: 11 });
  for (let i = 0; i < 40; i++) { const x = rnd(-230, 230), y = -14 + rnd(-80, 70); G.push(mk(polar(x, y, rnd(0, 3), rnd(4, 7)), rnd(3, 4.5), rnd() < .7 ? '#f7eed8' : '#3d3129', { prof: 'leaf', nb: 0, a: .9 })); }
  g.fin = layer(G, ...T.d[0].fin);
  // steam: a few faint rising wisps (drawn with drift)
  g.steam = [0, 1, 2].map(i => mk(qctrl(-90 + i * 90, -150, -60 + i * 90 + rnd(-30, 30), -260, -90 + i * 90 + rnd(-20, 20), -360, 18), 9, '#b5aca2', { prof: 'leaf', nb: 2, a: .32 }));
  g.anchor = [160, -60];   // where the note's leader lands
  return g;
}

function buildKatsu() {
  const g = {};
  g.bg = washSprite([{ pts: ell(40, 0, 720, 330, 40), fill: '#f2e1ae', a: .34, jit: 26 }], 60);
  g.bowlW = washSprite([
    { pts: [...ell(0, 0, 360, 150, 40, 0, Math.PI), ...ell(0, -6, 320, 126, 40, Math.PI, 0)], fill: '#a9b6bb', a: .35, jit: 3 },
    { pts: ell(10, 20, 300, 100, 40), fill: '#d7dcd8', a: .22, jit: 6 },
  ]);
  const B = [];
  B.push(mk(ell(0, 0, 362, 152, 64), 6, '#7f8c93', { prof: 'even', nb: 2, a: .8, rough: .3 }));
  B.push(mk(ell(0, -6, 318, 124, 60, Math.PI * .05, Math.PI * .95), 4, '#8e999f', { prof: 'brush', nb: 0, a: .6 }));
  // cabbage shreds on the left
  for (let i = 0; i < 46; i++) { const x = -215 + rnd(-75, 70), y = -10 + rnd(-55, 45), a = rnd(-1, 1) + (rnd() < .5 ? 0 : 3.14); B.push(mk(polar(x, y, a, rnd(28, 60), rnd(-8, 8), 8), rnd(3.5, 6), rnd() < .5 ? '#b5cd86' : '#8fb066', { prof: 'leaf', nb: 0, a: rnd(.6, .9) })); }
  g.bowl = layer(B, ...T.d[1].bowl);
  // the cutlet: five slices (golden crust, crumb texture, cut face with cheese)
  g.slices = [];
  const xs = [-110, -38, 34, 106, 178];
  for (let k = 0; k < 5; k++) {
    const x0 = xs[k], w = 66, top = -78 + Math.abs(k - 2) * 6, bot = 52 - Math.abs(k - 2) * 4;
    const S = [];
    const body = [[x0, top + 8], [x0 + w * .5, top - 3], [x0 + w, top + 6], [x0 + w + 4, bot - 4], [x0 + w * .5, bot + 6], [x0 + 2, bot - 2]];
    const spr = washSprite([{ pts: body, fill: '#d49a48', a: .9, jit: 2.5, edge: '#9c5f24' }, { pts: body.map(([x, y]) => [x + 6, y + 6]).slice(0, 4), fill: '#b9792e', a: .25, jit: 4 }], 20);
    crumbs(S, x0 + w / 2, (top + bot) / 2 - 10, w * .42, (bot - top) * .38, 34, ['#e6bb66', '#a8662a', '#c98a3e']);
    // cut face (front): cream meat with a cheese band
    S.push(mk(qcurve(x0 + 4, bot - 6, x0 + w, bot - 4, -3, 6), 15, '#f1e4cb', { prof: 'even', nb: 2, a: .95, rough: .1 }));
    S.push(mk(qcurve(x0 + 6, bot - 7, x0 + w - 2, bot - 5, -3, 6), 6, '#f2c641', { prof: 'even', nb: 0, a: .95, rough: .15 }));
    g.slices.push({ spr, L: layer(S, T.d[1].fill[0] + k * .22, T.d[1].fill[0] + k * .22 + .7), t0: T.d[1].fill[0] + k * .22 });
  }
  // sauce zig-zag
  const Z = []; const zz = []; for (let i = 0; i <= 18; i++) zz.push([-120 + i * 17, -40 + (i % 2 ? 26 : -14) + Math.sin(i) * 4]);
  Z.push(mk(zz, 9, '#5e3420', { prof: 'even', nb: 3, a: .85, rough: .25 }));
  g.top = layer(Z, ...T.d[1].top);
  // parsley
  const G = []; clump(G, 30, -30, 120, 14, ['#6f9a4e', '#86ad58'], { sx: 1.4, sy: .5, l0: 4, l1: 8, w0: 4, w1: 7 });
  g.fin = layer(G, ...T.d[1].fin);
  g.anchor = [200, -40];
  return g;
}

function buildTwigim() {
  const g = {};
  g.bg = washSprite([{ pts: ell(40, 0, 720, 330, 40), fill: '#eccb98', a: .36, jit: 26 }], 60);
  // basket shading + liner paper
  g.bowlW = washSprite([
    { pts: [...ell(0, -10, 320, 140, 40, 0, Math.PI), ...qctrl(-320, -10, 0, 230, 320, -10, 30).reverse()], fill: '#c9a06a', a: .5, jit: 3 },
    { pts: ell(0, -10, 286, 118, 40), fill: '#efe2c4', a: .5, jit: 5 },
  ]);
  const B = [];
  B.push(mk(ell(0, -10, 322, 142, 64), 8, '#8f6438', { prof: 'even', nb: 3, a: .82, rough: .3 }));
  B.push(mk(qctrl(-322, -8, 0, 232, 322, -8, 40), 8, '#8f6438', { prof: 'even', nb: 3, a: .8 }));
  for (let i = 0; i < 26; i++) {          // weave
    const u = (i + .5) / 26, x = -310 + u * 620, yTop = -10 + Math.sqrt(Math.max(0, 1 - (x / 322) ** 2)) * 142, yBot = yTop + 70 * Math.sqrt(Math.max(0, 1 - (x / 330) ** 2));
    B.push(mk(qcurve(x - 6, yTop + 4, x + 8, yBot, 3, 6), 6, i % 2 ? '#a57a48' : '#b98b55', { prof: 'even', nb: 0, a: .7 }));
  }
  for (let i = 0; i < 4; i++) B.push(mk(qcurve(-250 + i * 40, -60 + i * 8, 220 - i * 30, -110 + i * 12, -10, 10), 1.6, '#c7a77a', { prof: 'even', nb: 0, a: .5 }));   // liner ruled lines
  g.bowl = layer(B, ...T.d[2].bowl);
  // fritters: the burst — all paint at once
  const F = [];
  for (let i = 0; i < 13; i++) {
    const a = rnd(0, Math.PI * 2), rr = Math.sqrt(rnd()) * .85, x = Math.cos(a) * rr * 220, y = -14 + Math.sin(a) * rr * 80, d = rnd(-1.2, 1.2), L = rnd(105, 150);
    const s = mk(polar(x - Math.cos(d) * L / 2, y - Math.sin(d) * L / 4, d, L, rnd(-10, 10), 10), rnd(40, 54), i % 4 === 0 ? '#c9893a' : '#dca64c', { prof: 'leaf', nb: 5, a: .95, rib: .9, rough: .3 });
    F.push(s); F.push(edgeOf(s, -1, 5, '#a8692c', .8));
    if (i % 4 === 1) F.push(edgeOf(s, 1, 6, '#7f5a7a', .65));  // sweet-potato skin
  }
  g.fill = layer(F, ...T.d[2].fill);
  const P = [];
  crumbs(P, 0, -14, 230, 85, 70, ['#e9c070', '#b9792e', '#f0d08a'], 4, 7);
  for (let i = 0; i < 4; i++) { const pts = []; for (let k = 0; k <= 14; k++) pts.push([-190 + i * 30 + k * 26, -60 + i * 22 + Math.sin(k * .9 + i) * 16]); P.push(mk(pts, 7, '#e9b84a', { prof: 'even', nb: 2, a: .7 })); }  // honey-butter drizzle
  g.top = layer(P, ...T.d[2].top);
  const G = [];
  clump(G, 0, -20, 170, 22, ['#6f9a4e', '#86ad58'], { sx: 1.3, sy: .45, l0: 4, l1: 8, w0: 4, w1: 7 });
  for (let i = 0; i < 14; i++) { const x = rnd(-200, 200), y = -14 + rnd(-70, 60); G.push(mk(polar(x, y, rnd(0, 3), rnd(10, 18)), rnd(4, 6), '#fbf3dc', { prof: 'leaf', nb: 0, a: .85 })); }  // glints (cream, never white)
  g.fin = layer(G, ...T.d[2].fin);
  g.anchor = [190, -50];
  return g;
}

// ---------- text ----------
let TXT = [];   // collected each frame for window.TEXTS
const SERIF = '"Noto Serif KR"', PEN = '"Nanum Pen Script"', MONO = '"IBM Plex Mono"';
function txt(id, s, x, y, font, size, p, o = {}) {   // x,y in current transform; p = left→right reveal
  if (p <= 0) return;
  ctx.save(); ctx.font = `${o.w || 700} ${size}px ${font}`; ctx.textAlign = o.align || 'left'; ctx.textBaseline = 'middle';
  if (o.track) ctx.letterSpacing = o.track + 'px';
  const w = ctx.measureText(s).width, x0 = o.align === 'center' ? x - w / 2 : o.align === 'right' ? x - w : x;
  ctx.beginPath(); ctx.rect(x0 - 8, y - size, (w + 16) * eo(p), size * 2); ctx.clip();
  ctx.shadowColor = rgba(PAPER, .95); ctx.shadowBlur = 12; ctx.fillStyle = rgba(o.col || INK, o.a ?? .9);
  ctx.fillText(s, x, y); if (o.twice !== false) ctx.fillText(s, x, y);
  ctx.restore();
  if ((o.a ?? .9) * (ctx.globalAlpha) > .5) {   // report the full text from its first visible frame, in screen px
    const m = ctx.getTransform(); TXT.push({ id, text: s, x0: m.a * x0 + m.e, y0: m.d * (y - size * .6) + m.f, x1: m.a * (x0 + w) + m.e, y1: m.d * (y + size * .6) + m.f });
  }
}
function leaderLine(x0, y0, x1, y1, p, bend = 24) {
  if (p <= 0) return;
  const pts = qcurve(x0, y0, x1, y1, bend, 16), m = Math.max(1, Math.round(16 * clamp(p)));
  ctx.beginPath(); for (let i = 0; i <= m; i++) i ? ctx.lineTo(pts[i][0], pts[i][1]) : ctx.moveTo(pts[i][0], pts[i][1]);
  ctx.strokeStyle = rgba(INK, .72); ctx.lineWidth = 1.8; ctx.lineCap = 'round'; ctx.stroke();
  if (p >= 1) { ctx.beginPath(); ctx.arc(x1, y1, 3.4, 0, 7); ctx.fillStyle = rgba(INK, .72); ctx.fill(); }
}
// the teal seal: a hand-stamped ring with uneven ink
let SEAL;
function buildSeal() {
  const r = 58;
  SEAL = offscreen(-r - 20, -r - 20, r + 20, r + 20, c => {
    for (let k = 0; k < 3; k++) {
      c.beginPath(); for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2, rr = r - k * 7 + rnd(-1.5, 1.5); i ? c.lineTo(Math.cos(a) * rr, Math.sin(a) * rr) : c.moveTo(Math.cos(a) * rr, Math.sin(a) * rr); }
      c.closePath(); c.lineWidth = k === 0 ? 7 : 2.5; c.strokeStyle = rgba(TEAL, k === 0 ? .85 : .6); c.stroke();
    }
    c.font = `500 34px ${MONO}`; c.letterSpacing = '4px'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillStyle = rgba(TEAL, .9); c.fillText(C.stamp, 3, 2);
    // speckle the ink: knock out random specks with paper
    c.globalCompositeOperation = 'destination-out';
    for (let i = 0; i < 260; i++) { c.globalAlpha = rnd(.2, .8); c.beginPath(); c.arc(rnd(-r, r), rnd(-r, r), rnd(.6, 2.2), 0, 7); c.fill(); }
    c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
  });
}
function seal(x, y, t0, t, sc = 1, rot = -.18) {
  const p = seg(t, t0 - .12, t0 + .08); if (p <= 0) return;
  const s = sc * lerp(1.35, 1, eo(p)), a = ss(p);
  ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.scale(s, s); ctx.globalAlpha *= a; ctx.drawImage(SEAL.cv, SEAL.x0, SEAL.y0); ctx.restore();
}

// ---------- the frame ----------
function drawDish(i, t) {
  const g = D[i], tt = T.d[i];
  worldXf(DX[i]);
  // background wash wiped in with a brush edge
  { const p = seg(t, tt.wash, tt.wash + 1.4); if (p > 0) { ctx.save(); if (p < 1) wipeClip(g.bg.x0, g.bg.x1, g.bg.y0, g.bg.y1, p, i * 7 + 1); drawSpr(g.bg); ctx.restore(); } }
  // vessel shading fades in under its strokes
  drawSpr(g.bowlW, ss(seg(t, tt.bowl[0] + .2, tt.bowl[1] + .2)));
  if (i === 0) {   // the sauce: the drop blooms into it (over the bowl's shading)
    const r = 330 * eo(seg(t, T.drop + .05, T.d[0].bowl[0] + .6));
    if (r > 0) { ctx.save(); blobClip(-40, -10, r, 3.1); drawSpr(g.sauce); ctx.restore(); }
  }
  drawLayer(g.bowl, t);
  if (i === 1) {
    const pull = eo(seg(t, tt.pull[0], tt.pull[1]));
    g.slices.forEach((s, k) => {
      const dx = k === 4 ? 92 * pull : 0, a = ss(seg(t, s.t0, s.t0 + .35));
      if (a <= 0) return;
      ctx.save(); ctx.translate(dx, k === 4 ? -10 * pull : 0); drawSpr(s.spr, a); drawLayer(s.L, t); ctx.restore();
    });
    if (pull > 0) {   // cheese strings stretch across the gap (drawn over the cut faces)
      withSeed(77, () => {
        const ys = [-38, -12, 12, 34], ws = [9, 12, 10, 13];
        for (let j = 0; j < 4; j++) {
          const y = ys[j], x0 = 160, x1 = 186 + 92 * pull, sag = (8 + 22 * pull) * (j % 2 ? 1 : .6);
          const s = mk(qcurve(x0, y, x1, y - 10 * pull, -sag, 12), ws[j] * (1 - .35 * pull), '#f2c641', { prof: 'even', nb: 2, a: .95, rough: .25 });
          drawS(ctx, s, 1); drawS(ctx, edgeOf(s, 1, 2.5, '#d9a21f', .7), 1);
        }
      });
    }
  }
  if (i !== 1) drawLayer(g.fill, t);
  drawLayer(g.top, t);
  drawLayer(g.fin, t);
  if (i === 0 && t > tt.fin[1]) {   // steam drifts up once finished
    for (let k = 0; k < 3; k++) {
      const ph = (t * .45 + k * .33) % 1, a = Math.sin(Math.PI * ph) * ss(seg(t, tt.fin[1], tt.fin[1] + 1));
      ctx.save(); ctx.translate(Math.sin(t * 1.1 + k) * 8, -ph * 60); ctx.transform(1, 0, .02 * Math.sin(1.15 * t + k), 1, 0, 0); drawS(ctx, g.steam[k], 1, null, a); ctx.restore();
    }
  }
  // annotation column: tag, name, hand note with leader, seal — fades as the final pull-back starts
  const m = C.menus[i], f = 1 - ss(seg(t, T.pull[0] - .1, T.pull[0] + .5));
  if (f > 0) {
    ctx.globalAlpha = f;
    const lx = 400;
    txt('tag' + i, m.tag, lx, -150, MONO, 24, seg(t, tt.tag, tt.tag + .4), { w: 500, track: 6, col: INK2, a: .75, twice: false });
    txt('name' + i, m.name, lx, -92, SERIF, 50, seg(t, tt.name, tt.name + .7), { w: 700 });
    leaderLine(lx + 6, 0, g.anchor[0], g.anchor[1], seg(t, tt.note - .2, tt.note + .4), 22);
    txt('note' + i, m.note, lx + 20, -10, PEN, 50, seg(t, tt.note, tt.note + 1.0), { w: 400, col: INK2 });
    seal(-300, -200, tt.stamp, t, .9);
    ctx.globalAlpha = 1;
  } else seal(-300, -200, tt.stamp, t, .9);
}

function render(t) {
  TXT = [];
  setCam(t);
  screenXf(); ctx.globalAlpha = 1; ctx.drawImage(PAPER_IMG, 0, 0);
  for (let i = 0; i < 3; i++) {
    const dl = (DX[i] - CX) * CZ;   // skip dishes far off screen
    if (Math.abs(dl) < 960 + 1100 * CZ && t >= T.d[i].wash - .01 || i === 0) drawDish(i, t);
  }
  screenXf();
  // opening: the handwritten question, then a falling drop of rose pigment; mist erases the question
  if (t < T.mist + 1.2) {
    const mist = seg(t, T.mist, T.mist + .9);
    ctx.save();
    if (mist > 0) { ctx.beginPath(); const e = lerp(1080, -40, eio(mist)); ctx.moveTo(0, 0); ctx.lineTo(1920, 0); for (let x = 1920; x >= 0; x -= 40) ctx.lineTo(x, e - 120 + 30 * Math.sin(x * .006 + 1) + 20 * vnoise(x * .01)); ctx.closePath(); ctx.clip(); }
    txt('question', C.question, 180, 210, PEN, 96, seg(t, T.q0, T.q1), { w: 400, col: INK2 });
    // pencil underline
    if (t > T.q1 - .2) withSeed(5, () => drawS(ctx, mk(qcurve(176, 262, 560, 258, -4, 20), 4, INK2, { prof: 'brush', nb: 0, a: .6 }), seg(t, T.q1 - .2, T.q1 + .4)));
    ctx.restore();
  }
  { // the drop: falls from above onto the sauce point, lands at T.drop
    const p = seg(t, T.drop - .45, T.drop);
    if (p > 0 && p < 1) {
      const x = sx(-40), y = lerp(-60, sy(-10), ei(p)), r = 14 + 6 * p;
      ctx.beginPath(); ctx.moveTo(x, y - r * 2.2); ctx.quadraticCurveTo(x + r, y - r * .2, x, y + r); ctx.quadraticCurveTo(x - r, y - r * .2, x, y - r * 2.2);
      ctx.fillStyle = rgba('#c95a4c', .9); ctx.fill();
    }
  }
  // ending: title, line, labels under each dish, the big seal
  if (t > T.pull[0]) {
    txt('title', C.title, 960, 170, SERIF, 78, seg(t, T.title, T.title + .9), { align: 'center' });
    txt('sub', C.sub, 960, 262, PEN, 54, seg(t, T.sub, T.sub + 1.0), { w: 400, align: 'center', col: INK2 });
    for (let i = 0; i < 3; i++) txt('label' + i, C.menus[i].name, sx(DX[i]), sy(250), SERIF, 32, seg(t, T.labels + i * .15, T.labels + i * .15 + .6), { align: 'center', a: .85 });
    seal(1395, 175, T.seal, t, 1.15, -.22);
  }
}
window.render = render;
window.TEXTS = t => { render(t); return TXT.map(o => ({ ...o })); };

// sound and cue events for the mixer
window.EV = [
  { t: T.q0, type: 'pencil', d: T.q1 - T.q0 }, { t: T.drop, type: 'drop' }, { t: T.mist, type: 'mist' },
  ...T.d.flatMap((d, i) => [
    { t: d.wash, type: 'wash', i }, { t: d.bowl[0], type: 'brush', d: d.bowl[1] - d.bowl[0], i },
    { t: d.fill[0], type: i === 2 ? 'burst' : 'brush', d: d.fill[1] - d.fill[0], i }, { t: d.top[0], type: 'brush', d: d.top[1] - d.top[0], i },
    { t: d.note, type: 'pencil', d: 1.0, i }, { t: d.stamp, type: 'stamp', i },
  ]),
  { t: 10.0, type: 'dolly' }, { t: 17.9, type: 'dolly' }, { t: T.d[1].pull[0], type: 'crunch' }, { t: 18.6, type: 'sizzle', d: 4.6 },
  { t: T.hush, type: 'hush' }, { t: T.pull[0], type: 'pullback' }, { t: T.sub, type: 'pencil', d: 1.0 }, { t: T.seal, type: 'seal' },
];

(async () => {
  PAPER_IMG = new Image(); PAPER_IMG.src = 'paper.jpg'; await PAPER_IMG.decode();
  await Promise.all([`700 50px ${SERIF}`, `400 50px ${PEN}`, `500 24px ${MONO}`].map(f => document.fonts.load(f, C.title + C.sub + C.question + C.menus.map(m => m.name + m.note + m.tag).join('') + C.stamp)));
  D.push(withSeed(101, buildTteok), withSeed(202, buildKatsu), withSeed(303, buildTwigim));
  withSeed(404, buildSeal);
  window.READY = true;
})();
