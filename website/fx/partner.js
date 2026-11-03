/* OncoloHealth partner effects: X-ray lens service cards, the engagement procedure line,
   and the quote request form. Native scrolling only; nothing here pins or hijacks the wheel.

   Performance notes
   - Each card's radiograph is painted once into a canvas per size change (never per frame).
   - The lens is a circular window moved and scaled with transform; the film inside carries the
     inverse transform, so a frame costs three transform writes and no paint or layout.
   - Pointer handlers only store coordinates; rects are read once at the start of a frame. */
(function () {
  'use strict';
  if (!window.OHX) return;

  var SERVICE_KEY = 'ohx:quote:service';
  var GOTO_KEY = 'ohx:goto';

  function $(sel, el) { return el ? el.querySelector(sel) : null; }
  function $$(sel, el) { return el ? Array.prototype.slice.call(el.querySelectorAll(sel)) : []; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function store(k, v) { try { if (v == null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } }
  function load(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function headerOffset() { var h = document.querySelector('.site-header'); return (h ? h.getBoundingClientRect().height : 76) + 16; }
  function on(el, type, fn, opts) { if (el) el.addEventListener(type, fn, opts); }

  OHX.register('partner', function (fx) {
    var parts = { links: initLinks, services: initServices, procedure: initProcedure, quote: initQuote };
    Object.keys(parts).forEach(function (k) {
      try { parts[k](fx); } catch (e) { console.error('[fx] partner/' + k + ' failed:', e); }
    });
  });

  /* ------------------------------------------------------------------
     Cross-page links. The router only knows page hashes, so a service
     preselection or an in-page target travels through sessionStorage.
     ------------------------------------------------------------------ */
  function initLinks(fx) {
    document.addEventListener('click', function (e) {
      var a = e.target && e.target.closest ? e.target.closest('a[data-quote-service], a[data-fx-goto]') : null;
      if (!a) return;
      if (a.hasAttribute('data-quote-service')) store(SERVICE_KEY, a.getAttribute('data-quote-service'));
      if (a.hasAttribute('data-fx-goto')) store(GOTO_KEY, a.getAttribute('data-fx-goto'));
    });
    fx.onPage(function () {
      var id = load(GOTO_KEY);
      if (!id) return;
      var el = document.getElementById(id);
      if (!el || !fx.isLive(el)) return;
      store(GOTO_KEY, null);
      // app.js scrolls to the top on every route; land on the target after that.
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          window.scrollTo({ top: window.pageYOffset + el.getBoundingClientRect().top - headerOffset() + 16, behavior: fx.reduced ? 'auto' : 'smooth' });
        });
      });
    });
  }

  /* ==================================================================
     Radiograph renderer. Navy film, cream bone graded toward peach.
     Scenes are drawn in a 300 x 260 design box, fitted to the film.
     ================================================================== */
  var BONE = [246, 236, 228];
  var PEACH = [234, 195, 182];
  function c(rgb, a) { return 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + a + ')'; }
  var MONO = '"DM Mono", ui-monospace, Menlo, monospace';

  /* A tubular bone (metacarpal or phalanx) from (x0,y0) along angle ang (radians, 0 = up). */
  function longBone(path, x0, y0, ang, L, w, tip) {
    var ux = Math.sin(ang), uy = -Math.cos(ang), nx = -uy, ny = ux;
    function P(a, b) { return [x0 + ux * a + nx * b, y0 + uy * a + ny * b]; }
    var hw = w / 2, waist = hw * 0.6, head = hw * (tip ? 0.62 : 0.84);
    var segs = [
      [P(L * 0.22, -hw * 0.78), P(L * 0.52, -waist), P(L * 0.8, -head)],
      [P(L * 0.95, -head), P(L, -head * 0.62), P(L, 0)],
      [P(L, head * 0.62), P(L * 0.95, head), P(L * 0.8, head)],
      [P(L * 0.52, waist), P(L * 0.22, hw * 0.78), P(0, hw)],
      [P(-hw * 0.32, hw * 0.55), P(-hw * 0.32, -hw * 0.55), P(0, -hw)]
    ];
    var s0 = P(0, -hw);
    path.moveTo(s0[0], s0[1]);
    segs.forEach(function (s) { path.bezierCurveTo(s[0][0], s[0][1], s[1][0], s[1][1], s[2][0], s[2][1]); });
    path.closePath();
    return P(L, 0);
  }

  /* A quadratic curve thickened to a band of width w0 -> w1 (ribs, clavicles). */
  function band(x0, y0, cx, cy, x1, y1, w0, w1) {
    var n = 18, top = [], bot = [], i, t, x, y, dx, dy, len, w;
    for (i = 0; i <= n; i++) {
      t = i / n;
      x = (1 - t) * (1 - t) * x0 + 2 * (1 - t) * t * cx + t * t * x1;
      y = (1 - t) * (1 - t) * y0 + 2 * (1 - t) * t * cy + t * t * y1;
      dx = 2 * (1 - t) * (cx - x0) + 2 * t * (x1 - cx);
      dy = 2 * (1 - t) * (cy - y0) + 2 * t * (y1 - cy);
      len = Math.sqrt(dx * dx + dy * dy) || 1;
      w = (w0 + (w1 - w0) * t) / 2;
      top.push([x - dy / len * w, y + dx / len * w]);
      bot.push([x + dy / len * w, y - dx / len * w]);
    }
    var p = new Path2D();
    p.moveTo(top[0][0], top[0][1]);
    top.forEach(function (q) { p.lineTo(q[0], q[1]); });
    for (i = bot.length - 1; i >= 0; i--) p.lineTo(bot[i][0], bot[i][1]);
    p.closePath();
    return p;
  }

  function ellipse(p, x, y, rx, ry, rot) {
    rot = rot || 0;
    p.moveTo(x + rx * Math.cos(rot), y + rx * Math.sin(rot));
    p.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2);
    return p;
  }

  /* Radiographic bone: translucent body, bright cortical rim, hairline edge. */
  function bone(g, path, a, K) {
    a = a == null ? 1 : a;
    g.save();
    g.shadowColor = c(BONE, 0.28 * a); g.shadowBlur = 7 * K;
    g.fillStyle = c(BONE, 0.17 * a); g.fill(path);
    g.restore();
    g.save(); g.clip(path);
    g.lineWidth = 5; g.strokeStyle = c(BONE, 0.2 * a); g.stroke(path);
    g.lineWidth = 2; g.strokeStyle = c(BONE, 0.42 * a); g.stroke(path);
    g.restore();
    g.lineWidth = 0.6; g.strokeStyle = c(BONE, 0.7 * a); g.stroke(path);
  }
  function soft(g, path, a, K) {
    g.save();
    g.shadowColor = c(BONE, 0.1 * a); g.shadowBlur = 26 * K;
    g.fillStyle = c(BONE, 0.045 * a); g.fill(path);
    g.restore();
  }
  function hair(g, a, w, dash) { g.strokeStyle = c(PEACH, a); g.lineWidth = w || 0.6; g.setLineDash(dash || []); }
  function label(g, text, x, y, align, a) {
    g.save(); g.setLineDash([]);
    g.font = '500 8.6px ' + MONO; g.textAlign = align || 'left'; g.textBaseline = 'middle';
    g.fillStyle = c(BONE, a == null ? 0.85 : a);
    if (g.letterSpacing !== undefined) g.letterSpacing = '0.8px';
    g.fillText(text, x, y);
    g.restore();
  }
  function dot(g, x, y, r) { g.beginPath(); g.arc(x, y, r || 1.6, 0, Math.PI * 2); g.fillStyle = c(PEACH, 0.95); g.fill(); }

  var SCENES = {
    /* AP hip: proximal femur seated in the acetabulum, axis lines, ROC inset (schematic, no values). */
    'study-design': function (g, K) {
      soft(g, new Path2D('M14 60 C28 120 30 200 30 290 L168 290 C166 214 176 150 214 112 C176 82 120 70 14 60 Z'), 1, K);
      var pelvis = new Path2D();
      pelvis.moveTo(80, -20); pelvis.bezierCurveTo(88, 8, 100, 26, 112, 34);
      pelvis.arc(138, 52, 25, Math.PI * 200 / 180, Math.PI * 340 / 180, false);
      pelvis.bezierCurveTo(166, 58, 163, 72, 168, 84);
      pelvis.bezierCurveTo(176, 100, 192, 108, 214, 108);
      pelvis.bezierCurveTo(240, 108, 268, 100, 320, 96);
      pelvis.lineTo(320, -20); pelvis.closePath();
      bone(g, pelvis, 0.9, K);
      bone(g, new Path2D('M168 96 C160 126 168 160 188 172 C212 184 246 176 268 160 L320 150 L320 120 C290 126 262 122 244 112 C224 104 196 100 168 96 Z'), 0.75, K);
      var foramen = ellipse(new Path2D(), 214, 140, 26, 17, -0.2);
      g.fillStyle = 'rgba(13,22,38,.85)'; g.fill(foramen);
      hair(g, 0.18); g.stroke(foramen);
      var femur = new Path2D();
      femur.moveTo(62, 64);
      femur.bezierCurveTo(54, 74, 54, 90, 60, 104);
      femur.bezierCurveTo(64, 124, 66, 146, 66, 172);
      femur.lineTo(67, 290); femur.lineTo(97, 290); femur.lineTo(96, 172);
      femur.bezierCurveTo(96, 142, 98, 124, 104, 114);
      femur.bezierCurveTo(108, 110, 113, 108, 113, 101);
      femur.bezierCurveTo(109, 96, 104, 93, 105, 87);
      femur.bezierCurveTo(112, 80, 120, 75, 127.5, 70.2);
      femur.arc(138, 52, 21, Math.PI * 120 / 180, Math.PI * -150 / 180, true);
      femur.bezierCurveTo(108, 44, 92, 50, 80, 54);
      femur.bezierCurveTo(74, 50, 66, 55, 62, 64);
      femur.closePath();
      bone(g, femur, 1, K);
      // trabecular lines of head and neck; endosteal margins of the shaft
      g.save(); g.clip(femur);
      g.strokeStyle = c(BONE, 0.13); g.lineWidth = 0.5;
      var i;
      for (i = 0; i < 7; i++) { g.beginPath(); g.moveTo(126 + i * 3.4, 36 + i * 3.2); g.quadraticCurveTo(104, 74 + i * 3, 92 + i * 1.5, 118 + i * 7); g.stroke(); }
      for (i = 0; i < 5; i++) { g.beginPath(); g.moveTo(66 + i * 4, 70); g.quadraticCurveTo(100, 60 + i * 4, 150, 52 + i * 2); g.stroke(); }
      g.strokeStyle = c(BONE, 0.3); g.lineWidth = 0.6;
      g.beginPath(); g.moveTo(73, 150); g.lineTo(74, 290); g.moveTo(89, 150); g.lineTo(88.5, 290); g.stroke();
      g.restore();
      hair(g, 0.6, 0.6, [3, 3]);
      g.beginPath(); g.moveTo(82, 280); g.lineTo(84, 100); g.moveTo(138, 52); g.lineTo(84, 100); g.stroke();
      g.setLineDash([]); g.beginPath(); g.arc(84, 100, 13, -Math.PI * 0.73, -Math.PI * 0.49, false); g.stroke();
      dot(g, 138, 52, 1.4); dot(g, 84, 100, 1.4);
      label(g, 'AXIS', 36, 96, 'left', 0.7);
      var bx = 196, by = 150, bw = 92, bh = 92;
      g.fillStyle = 'rgba(12,21,36,.82)'; g.fillRect(bx, by, bw, bh);
      hair(g, 0.55); g.strokeRect(bx + 0.5, by + 0.5, bw - 1, bh - 1);
      hair(g, 0.14);
      for (i = 1; i < 4; i++) { g.beginPath(); g.moveTo(bx + bw * i / 4, by); g.lineTo(bx + bw * i / 4, by + bh); g.moveTo(bx, by + bh * i / 4); g.lineTo(bx + bw, by + bh * i / 4); g.stroke(); }
      hair(g, 0.35, 0.6, [2, 3]); g.beginPath(); g.moveTo(bx, by + bh); g.lineTo(bx + bw, by); g.stroke();
      hair(g, 0.6, 0.8, [3, 2]); g.beginPath(); g.moveTo(bx, by + bh); g.bezierCurveTo(bx + 10, by + 40, bx + 40, by + 20, bx + bw, by); g.stroke();
      g.setLineDash([]); g.strokeStyle = c(BONE, 0.95); g.lineWidth = 1.1;
      g.beginPath(); g.moveTo(bx, by + bh); g.bezierCurveTo(bx + 2, by + 18, bx + 22, by + 6, bx + bw, by); g.stroke();
      label(g, 'ROC · HELD-OUT', bx, by - 8);
      label(g, 'BASELINE', bx + bw - 4, by + 46, 'right', 0.6);
    },

    /* PA hand: radius, ulna, carpus, metacarpals and phalanges with joint spaces. */
    'model-adaptation': function (g, K) {
      var rays = [
        { x: 118, y: 208, a: -44, L: [44, 30, 23], w: [10, 9, 8] },
        { x: 133, y: 190, a: -11, L: [58, 35, 21, 16], w: [9.5, 8.6, 7.6, 6.6] },
        { x: 147, y: 188, a: -1.5, L: [61, 39, 24, 17], w: [10, 9, 8, 6.8] },
        { x: 161, y: 190, a: 8, L: [56, 36, 22, 16], w: [9.2, 8.3, 7.3, 6.3] },
        { x: 173, y: 197, a: 19, L: [49, 28, 17, 14], w: [8.4, 7.4, 6.4, 5.6] }
      ];
      var tissue = new Path2D();
      rays.forEach(function (r) {
        var ang = r.a * Math.PI / 180, total = r.L.reduce(function (s, v) { return s + v + 3.6; }, 0);
        tissue.moveTo(r.x, r.y); tissue.lineTo(r.x + Math.sin(ang) * (total + 4), r.y - Math.cos(ang) * (total + 4));
      });
      g.save();
      g.lineCap = 'round'; g.lineJoin = 'round'; g.lineWidth = 24;
      g.shadowColor = c(BONE, 0.12); g.shadowBlur = 18 * K;
      g.strokeStyle = c(BONE, 0.05); g.stroke(tissue);
      g.fillStyle = c(BONE, 0.05);
      g.fill(new Path2D('M100 200 C110 176 180 176 190 196 C196 230 186 270 180 300 L118 300 C112 270 96 236 100 200 Z'));
      g.restore();
      bone(g, new Path2D('M116 252 C120 243 140 240 156 243 C158 249 157 256 153 262 L151 300 L124 300 L122 262 C119 259 115 256 116 252 Z'), 0.95, K);
      bone(g, new Path2D('M162 254 C165 247 175 246 179 253 L176 300 L163 300 Z'), 0.85, K);
      [[131, 233, 9, 6, -0.45], [147, 236, 8, 7, 0], [161, 232, 7, 6, 0.2], [170, 227, 4.6, 4.6, 0],
       [123, 216, 8, 6, -0.6], [137, 213, 6.2, 6, 0], [151, 215, 7, 9.5, 0], [165, 213, 7, 7.6, 0.2]].forEach(function (e) {
        bone(g, ellipse(new Path2D(), e[0], e[1], e[2], e[3], e[4]), 0.8, K);
      });
      rays.forEach(function (r, ri) {
        var ang = r.a * Math.PI / 180, x = r.x, y = r.y;
        r.L.forEach(function (L, i) {
          var p = new Path2D();
          var a2 = ang + (i ? (ri - 2) * 0.015 * i : 0);
          var end = longBone(p, x, y, a2, L, r.w[i], i === r.L.length - 1);
          bone(g, p, i === 0 ? 0.95 : 0.9, K);
          x = end[0] + Math.sin(a2) * 3.6; y = end[1] - Math.cos(a2) * 3.6;
        });
      });
      bone(g, ellipse(new Path2D(), 93, 179, 3, 2.4, 0), 0.7, K);
      hair(g, 0.6, 0.6, [2, 3]);
      g.beginPath(); g.moveTo(108, 22); g.lineTo(108, 16); g.lineTo(196, 16); g.lineTo(196, 22); g.stroke();
      g.beginPath(); g.moveTo(196, 16); g.lineTo(220, 16); g.stroke();
      dot(g, 196, 16); label(g, 'TASK HEAD', 224, 16);
      g.beginPath(); g.moveTo(206, 120); g.lineTo(212, 120); g.lineTo(212, 238); g.lineTo(206, 238); g.stroke();
      g.beginPath(); g.moveTo(212, 178); g.lineTo(224, 178); g.stroke();
      dot(g, 212, 178); label(g, 'FROZEN', 228, 178);
      label(g, 'ENCODER', 228, 189, 'left', 0.55);
    },

    /* AP lumbar spine: five vertebrae with pedicles, transverse and spinous processes, sacrum. */
    workbench: function (g, K) {
      soft(g, new Path2D('M128 30 C110 110 92 190 76 290 L102 290 C112 200 126 120 140 40 Z M172 30 C190 110 208 190 224 290 L198 290 C188 200 174 120 160 40 Z'), 1, K);
      var cx = 150;
      for (var i = 0; i < 5; i++) {
        var top = 8 + i * 44, bh = 33, bw = 56 + i * 3, l = cx - bw / 2, r = cx + bw / 2, b = top + bh;
        var body = new Path2D();
        body.moveTo(l + 4, top + 1);
        body.quadraticCurveTo(cx, top - 2, r - 4, top + 1);
        body.quadraticCurveTo(r + 1, top + 2, r, top + 7);
        body.quadraticCurveTo(r - 4, top + bh / 2, r, b - 6);
        body.quadraticCurveTo(r + 1, b - 1, r - 4, b);
        body.quadraticCurveTo(cx, b + 2, l + 4, b);
        body.quadraticCurveTo(l - 1, b - 1, l, b - 6);
        body.quadraticCurveTo(l + 4, top + bh / 2, l, top + 7);
        body.quadraticCurveTo(l - 1, top + 2, l + 4, top + 1);
        body.closePath();
        var tl = 20 + (i === 2 ? 8 : (i === 1 || i === 3) ? 5 : 0);
        var tp = new Path2D();
        tp.moveTo(l + 2, top + 9); tp.quadraticCurveTo(l - tl * 0.6, top + 6, l - tl, top + 11);
        tp.quadraticCurveTo(l - tl - 2, top + 16, l - tl + 2, top + 17); tp.quadraticCurveTo(l - tl * 0.5, top + 16, l + 2, top + 19); tp.closePath();
        tp.moveTo(r - 2, top + 9); tp.quadraticCurveTo(r + tl * 0.6, top + 6, r + tl, top + 11);
        tp.quadraticCurveTo(r + tl + 2, top + 16, r + tl - 2, top + 17); tp.quadraticCurveTo(r + tl * 0.5, top + 16, r - 2, top + 19); tp.closePath();
        bone(g, tp, 0.7, K);
        bone(g, body, 0.95, K);
        g.strokeStyle = c(BONE, 0.45); g.lineWidth = 0.9;
        g.beginPath(); g.moveTo(l + 5, top + 2); g.quadraticCurveTo(cx, top - 1, r - 5, top + 2); g.moveTo(l + 5, b - 1); g.quadraticCurveTo(cx, b + 1, r - 5, b - 1); g.stroke();
        [l + 10, r - 10].forEach(function (px) {
          var ped = ellipse(new Path2D(), px, top + 12, 5, 7.5, 0);
          g.fillStyle = c(BONE, 0.06); g.fill(ped);
          g.strokeStyle = c(BONE, 0.62); g.lineWidth = 1.6; g.stroke(ped);
        });
        var sp = new Path2D(); sp.moveTo(cx, top + 15); sp.bezierCurveTo(cx + 6, top + 18, cx + 5, top + 34, cx, top + 38); sp.bezierCurveTo(cx - 5, top + 34, cx - 6, top + 18, cx, top + 15); sp.closePath();
        g.fillStyle = c(BONE, 0.12); g.fill(sp); g.strokeStyle = c(BONE, 0.5); g.lineWidth = 0.8; g.stroke(sp);
        hair(g, 0.5, 0.6); g.beginPath(); g.moveTo(l - 34, top + bh / 2); g.lineTo(l - 26, top + bh / 2); g.stroke();
        label(g, 'L' + (i + 1), l - 38, top + bh / 2, 'right', 0.8);
      }
      bone(g, new Path2D('M114 232 C126 226 174 226 186 232 C206 236 232 240 252 252 L240 300 L60 300 L48 252 C68 240 94 236 114 232 Z'), 0.8, K);
      g.strokeStyle = c(BONE, 0.3); g.lineWidth = 0.7;
      [[132, 256], [168, 256], [136, 280], [164, 280]].forEach(function (f) { g.beginPath(); g.arc(f[0], f[1], 4, 0, Math.PI * 2); g.stroke(); });
      hair(g, 0.6, 0.6, [2, 3]);
      g.beginPath(); g.moveTo(222, 8); g.lineTo(228, 8); g.lineTo(228, 217); g.lineTo(222, 217); g.stroke();
      g.beginPath(); g.moveTo(228, 112); g.lineTo(238, 112); g.stroke();
      dot(g, 228, 112); label(g, 'RUNS', 242, 107); label(g, 'LOCALLY', 242, 118);
    },

    /* PA chest: clavicles, scapulae, posterior and anterior ribs, mediastinum, diaphragm. */
    'licensing-review': function (g, K) {
      soft(g, new Path2D('M4 52 C34 26 96 16 150 16 C204 16 266 26 296 52 L304 290 L-4 290 Z'), 1.2, K);
      var abd = new Path2D('M-4 300 L-4 236 C30 222 70 176 118 206 C132 214 140 222 150 226 C164 214 196 184 236 196 C264 204 286 226 304 238 L304 300 Z');
      g.save(); g.shadowColor = c(BONE, 0.16); g.shadowBlur = 16 * K; g.fillStyle = c(BONE, 0.12); g.fill(abd); g.restore();
      var med = new Path2D('M134 18 L166 18 C170 70 172 100 186 122 C214 136 226 170 214 204 C202 228 160 232 128 222 C108 214 106 176 116 140 C124 108 130 64 134 18 Z');
      g.save(); g.shadowColor = c(BONE, 0.2); g.shadowBlur = 20 * K; g.fillStyle = c(BONE, 0.1); g.fill(med); g.restore();
      for (var v = 0; v < 15; v++) {
        var vb = new Path2D(), vy = 6 + v * 16;
        vb.moveTo(142, vy); vb.lineTo(158, vy); vb.quadraticCurveTo(160, vy + 6, 158, vy + 12); vb.lineTo(142, vy + 12); vb.quadraticCurveTo(140, vy + 6, 142, vy); vb.closePath();
        bone(g, vb, 0.45, K);
      }
      [-1, 1].forEach(function (s) {
        for (var i = 0; i < 9; i++) {
          var y0 = 30 + i * 19, sp = 1 + i * 0.06, reach = 126 * Math.min(1, 0.84 + i * 0.03);
          bone(g, band(150 + s * 9, y0, 150 + s * 70 * sp, y0 - 20, 150 + s * reach, y0 + 30, 6, 7), 0.55, K);
          bone(g, band(150 + s * reach, y0 + 30, 150 + s * 104, y0 + 62, 150 + s * 46, y0 + 58, 5, 4), 0.25, K);
        }
        bone(g, band(150 + s * 12, 30, 150 + s * 64, 8, 150 + s * 116, 20, 7, 8), 1, K);
        var x0 = 150 + s * 104;
        bone(g, new Path2D('M' + x0 + ' 22 C' + (150 + s * 128) + ' 30 ' + (150 + s * 140) + ' 70 ' + (150 + s * 134) + ' 110 C' + (150 + s * 120) + ' 80 ' + (150 + s * 108) + ' 50 ' + x0 + ' 22 Z'), 0.5, K);
      });
      hair(g, 0.65, 0.6);
      g.beginPath(); g.moveTo(84, 15); g.lineTo(60, 2); g.lineTo(18, 2); g.stroke(); dot(g, 84, 15); label(g, 'LICENSE', 18, -6);
      g.beginPath(); g.moveTo(232, 96); g.lineTo(262, 72); g.lineTo(286, 72); g.stroke(); dot(g, 232, 96); label(g, 'ACCESS', 286, 64, 'right');
      g.beginPath(); g.moveTo(176, 180); g.lineTo(220, 232); g.lineTo(286, 232); g.stroke(); dot(g, 176, 180); label(g, 'INTENDED USE', 286, 224, 'right');
    },

    /* Contact sheet of crops from a BTXRD pelvis radiograph: an exact duplicate pair (01, 07),
       a pair whose copies carry different labels (04 B, 10 N), and an excluded copy (12). */
    'dataset-audit': function (g, K, img) {
      var xs = [10, 82, 154, 226], ys = [14, 96, 178], t = 64, i;
      var crops = [[0, 250, 300], [300, 0, 260], [480, 0, 300], [230, 400, 250], [0, 0, 300], [520, 330, 264],
                   [0, 250, 300], [120, 380, 250], [560, 500, 224], [230, 400, 250], [0, 480, 260], [440, 380, 250]];
      for (i = 0; i < 12; i++) {
        var x = xs[i % 4], y = ys[(i / 4) | 0], cr = crops[i];
        g.fillStyle = 'rgba(8,14,24,.9)'; g.fillRect(x, y, t, t);
        if (img) g.drawImage(img, cr[0], cr[1], cr[2], cr[2], x, y, t, t);
        hair(g, 0.28); g.strokeRect(x + 0.5, y + 0.5, t - 1, t - 1);
        label(g, pad(i + 1), x + 1, y + t + 7, 'left', 0.45);
      }
      hair(g, 0.9, 0.9);
      g.strokeRect(xs[0] - 2.5, ys[0] - 2.5, t + 5, t + 5); g.strokeRect(xs[2] - 2.5, ys[1] - 2.5, t + 5, t + 5);
      hair(g, 0.8, 0.7, [3, 3]);
      g.beginPath(); g.moveTo(xs[0] + t + 3, ys[0] + t / 2); g.bezierCurveTo(xs[1] + 40, ys[0] + t / 2, xs[1] + 30, ys[1] + t / 2, xs[2] - 3, ys[1] + t / 2); g.stroke();
      g.fillStyle = 'rgba(12,21,36,.95)'; g.fillRect(xs[1] + 22, ys[0] + t + 12, 24, 10);
      label(g, 'DUP', xs[1] + 34, ys[0] + t + 17, 'center', 0.95);
      hair(g, 0.75, 0.8, [2, 2]);
      g.strokeRect(xs[3] - 2.5, ys[0] - 2.5, t + 5, t + 5); g.strokeRect(xs[1] - 2.5, ys[2] - 2.5, t + 5, t + 5);
      g.setLineDash([]);
      [[xs[3], ys[0], 'B'], [xs[1], ys[2], 'N']].forEach(function (f) {
        g.fillStyle = c(PEACH, 0.95); g.fillRect(f[0] + t - 13, f[1] + 3, 10, 10);
        g.save(); g.font = '500 7px ' + MONO; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#16233a'; g.fillText(f[2], f[0] + t - 8, f[1] + 8.5); g.restore();
      });
      var ex = xs[3], ey = ys[2];
      g.fillStyle = 'rgba(12,21,36,.55)'; g.fillRect(ex, ey, t, t);
      hair(g, 0.9, 1);
      g.beginPath(); g.moveTo(ex + 8, ey + 8); g.lineTo(ex + t - 8, ey + t - 8); g.moveTo(ex + t - 8, ey + 8); g.lineTo(ex + 8, ey + t - 8); g.stroke();
      label(g, 'EXCL', ex + t, ey + t + 7, 'right', 0.85);
    }
  };

  /* The BTXRD radiograph, graded to the site palette once through a 256-entry lookup table. */
  var graded = null, gradedState = 0, gradedWaiters = [];
  function withGraded(cb) {
    if (gradedState === 2) { cb(graded); return; }
    gradedWaiters.push(cb);
    if (gradedState === 1) return;
    gradedState = 1;
    var img = new Image();
    function finish() { gradedState = 2; var list = gradedWaiters; gradedWaiters = []; list.forEach(function (fn) { fn(graded); }); }
    img.onload = function () {
      try {
        var w = img.naturalWidth, h = img.naturalHeight, cv = document.createElement('canvas');
        cv.width = w; cv.height = h;
        var g = cv.getContext('2d');
        g.drawImage(img, 0, 0);
        var data = g.getImageData(0, 0, w, h), d = data.data;
        var stops = [[0, [10, 17, 30]], [0.42, [44, 62, 88]], [0.7, [150, 146, 150]], [0.86, [226, 196, 184]], [1, [251, 243, 236]]];
        var lut = new Uint8ClampedArray(256 * 3);
        for (var v = 0; v < 256; v++) {
          var t = Math.pow(v / 255, 1.15), k = 1;
          while (k < stops.length - 1 && t > stops[k][0]) k++;
          var a = stops[k - 1], b = stops[k], u = (t - a[0]) / ((b[0] - a[0]) || 1);
          for (var ch = 0; ch < 3; ch++) lut[v * 3 + ch] = a[1][ch] + (b[1][ch] - a[1][ch]) * u;
        }
        for (var p = 0; p < d.length; p += 4) {
          var l = (d[p] * 0.299 + d[p + 1] * 0.587 + d[p + 2] * 0.114) | 0;
          d[p] = lut[l * 3]; d[p + 1] = lut[l * 3 + 1]; d[p + 2] = lut[l * 3 + 2];
        }
        g.putImageData(data, 0, 0);
        graded = cv;
      } catch (e) { graded = null; }
      finish();
    };
    img.onerror = finish;
    img.src = 'scan-bone.webp';
  }

  function paintFilm(canvas, scene, w, h, dpr, padTop, padBottom) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    var g = canvas.getContext('2d');
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    var bg = g.createRadialGradient(w * 0.5, h * 0.4, 0, w * 0.5, h * 0.4, Math.max(w, h) * 0.78);
    bg.addColorStop(0, '#2b405d'); bg.addColorStop(0.42, '#1b2b42'); bg.addColorStop(1, '#0c1525');
    g.fillStyle = bg; g.fillRect(0, 0, w, h);

    // The scene goes into its own buffer so the crop can be feathered like a film edge.
    var top = padTop, bottom = h - padBottom, left = 18, right = w - 18;
    var bw = right - left, bh = bottom - top;
    if (bw < 40 || bh < 40) return;
    var s = Math.min(bw / 300, bh / 260);
    var buf = document.createElement('canvas');
    buf.width = Math.round(bw * dpr); buf.height = Math.round(bh * dpr);
    var b = buf.getContext('2d');
    var ox = (bw - 300 * s) / 2, oy = (bh - 260 * s) / 2;
    b.setTransform(dpr * s, 0, 0, dpr * s, dpr * ox, dpr * oy);
    b.lineJoin = 'round'; b.lineCap = 'round';
    if (SCENES[scene]) SCENES[scene](b, s * dpr, graded);
    b.setTransform(1, 0, 0, 1, 0, 0);
    b.globalCompositeOperation = 'destination-in';
    var fy = b.createLinearGradient(0, 0, 0, buf.height);
    var e = Math.min(0.12, 18 * dpr / buf.height);
    fy.addColorStop(0, 'rgba(0,0,0,0)'); fy.addColorStop(e, '#000'); fy.addColorStop(1 - e, '#000'); fy.addColorStop(1, 'rgba(0,0,0,0)');
    b.fillStyle = fy; b.fillRect(0, 0, buf.width, buf.height);
    g.drawImage(buf, left, top, bw, bh);

    var vg = g.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.max(w, h) * 0.75);
    vg.addColorStop(0, 'rgba(6,11,20,0)'); vg.addColorStop(1, 'rgba(6,11,20,.55)');
    g.fillStyle = vg; g.fillRect(0, 0, w, h);

    // film-edge markers: millimetre ruler on the left edge, corner brackets around the field
    g.strokeStyle = c(PEACH, 0.32); g.lineWidth = 1;
    g.beginPath();
    for (var y = top, n = 0; y <= bottom; y += 6, n++) { var len = n % 5 ? 3 : 7; g.moveTo(8, Math.round(y) + 0.5); g.lineTo(8 + len, Math.round(y) + 0.5); }
    g.stroke();
    g.strokeStyle = c(PEACH, 0.55);
    var k = 10;
    g.beginPath();
    g.moveTo(left, top + k); g.lineTo(left, top); g.lineTo(left + k, top);
    g.moveTo(right - k, top); g.lineTo(right, top); g.lineTo(right, top + k);
    g.moveTo(left, bottom - k); g.lineTo(left, bottom); g.lineTo(left + k, bottom);
    g.moveTo(right - k, bottom); g.lineTo(right, bottom); g.lineTo(right, bottom - k);
    g.stroke();
  }

  /* ------------------------------------------------------------------
     1. Services: a circular lens follows a fine pointer and exposes the
        radiograph under the card. Tap, the toggle, or keyboard focus on
        the toggle reveal the whole film.
     ------------------------------------------------------------------ */
  function initServices(fx) {
    var sec = document.getElementById('services');
    if (!sec) return;
    var cards = $$('[data-lens]', sec).map(makeCard).filter(Boolean);
    if (!cards.length) return;
    var moving = [];
    var rectsDirty = true;
    var fontsReady = !document.fonts || document.fonts.status === 'loaded';

    function makeCard(card) {
      var win = $('.fxs-xray', card), film = $('.fxs-film', card), canvas = $('.fxs-canvas', card);
      if (!win || !film || !canvas) return null;
      return {
        card: card, win: win, film: film, canvas: canvas, ring: $('.fxs-lens', card), btn: $('.fxs-toggle', card),
        scene: canvas.getAttribute('data-scene'),
        w: 0, h: 0, R: 100, left: 0, top: 0,
        x: 0, y: 0, sc: 0, tx: 0, ty: 0, ts: 0, px: 0, py: 0,
        hover: false, follow: false, pressed: false, preview: false, visible: false,
        painted: '', down: null, snap: false, snapPos: false
      };
    }

    function measure(s) {
      var w = s.card.clientWidth, h = s.card.clientHeight;
      if (!w || !h) return false;
      s.w = w; s.h = h;
      s.R = fx.clamp(w * 0.3, 78, 118);
      s.card.style.setProperty('--R', s.R + 'px');
      s.card.style.setProperty('--cw', w + 'px');
      s.card.style.setProperty('--ch', h + 'px');
      return true;
    }
    /* Paint the film once for the card's current size. */
    function paint(s) {
      if (!fx.isLive(s.card) || !measure(s)) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var key = s.w + 'x' + s.h + '@' + dpr + (fontsReady ? 'f' : '') + (s.scene === 'dataset-audit' && graded ? 'g' : '');
      if (key === s.painted) return;
      var narrow = s.w < 420;
      paintFilm(s.canvas, s.scene, s.w, s.h, dpr, narrow ? 54 : 58, narrow ? 162 : 156);
      s.painted = key;
      if (s.scene === 'dataset-audit' && gradedState !== 2) withGraded(function () { s.painted = ''; paint(s); });
      if (full(s)) { s.ts = farthest(s, s.tx, s.ty) / s.R; animate(s, true); }
    }
    function farthest(s, cx, cy) {
      return Math.sqrt(Math.pow(Math.max(cx, s.w - cx), 2) + Math.pow(Math.max(cy, s.h - cy), 2)) * 1.04 + 12;
    }
    function animate(s, instant) {
      if (instant || fx.reduced) s.snap = true;
      if (moving.indexOf(s) < 0) moving.push(s);
      if (fx.kick) fx.kick();
    }
    function full(s) { return s.pressed || s.preview; }
    function sync(s, cx, cy) {
      var f = full(s);
      s.card.classList.toggle('is-full', f);
      if (s.btn) s.btn.setAttribute('aria-pressed', String(s.pressed));
      if (cx != null) { s.tx = cx; s.ty = cy; if (s.sc < 0.02) s.snapPos = true; }
      s.ts = f ? farthest(s, s.tx, s.ty) / s.R : (s.hover ? 1 : 0);
      s.follow = s.hover && !f;
      animate(s);
    }
    function centerOf(s, el) {
      // Click and focus handlers only, never per frame.
      var b = s.card.getBoundingClientRect(), bb = el.getBoundingClientRect();
      return { x: bb.left - b.left + bb.width / 2, y: bb.top - b.top + bb.height / 2 };
    }
    var HIDE = 'translate3d(-9999px,0,0) scale(0)';
    function write(s) {
      var x = s.x, y = s.y, R = s.R, sc = s.sc;
      if (sc < 0.004) {
        s.win.style.transform = HIDE;
        if (s.ring) s.ring.style.transform = HIDE;
        return;
      }
      var at = 'translate3d(' + (x - R).toFixed(2) + 'px,' + (y - R).toFixed(2) + 'px,0) scale(';
      s.win.style.transform = at + sc.toFixed(4) + ')';
      s.film.style.transform = 'translate3d(' + (R - x / sc).toFixed(2) + 'px,' + (R - y / sc).toFixed(2) + 'px,0) scale(' + (1 / sc).toFixed(5) + ')';
      if (s.ring) s.ring.style.transform = at + Math.min(sc, 1.2).toFixed(4) + ')';
    }

    cards.forEach(function (s) {
      var card = s.card;
      card.addEventListener('pointerenter', function (e) {
        if (e.pointerType !== 'mouse') return;
        if (!s.painted) paint(s);
        s.hover = true; s.px = e.clientX; s.py = e.clientY; rectsDirty = true;
        card.classList.add('is-lens');
        if (full(s)) return;
        s.follow = true; s.ts = 1; s.snapPos = true;
        animate(s);
      });
      card.addEventListener('pointermove', function (e) {
        if (!s.hover || e.pointerType !== 'mouse') return;
        s.px = e.clientX; s.py = e.clientY;
        if (!full(s)) animate(s);
      }, { passive: true });
      card.addEventListener('pointerleave', function () {
        if (!s.hover) return;
        s.hover = false; s.follow = false;
        card.classList.remove('is-lens');
        if (!full(s)) { s.ts = 0; animate(s); }
      });
      // Touch and pen: a tap (not a scroll) toggles the whole film from the tap point.
      card.addEventListener('pointerdown', function (e) { s.down = { t: e.pointerType, x: e.clientX, y: e.clientY }; }, { passive: true });
      card.addEventListener('click', function (e) {
        if (e.target.closest('a, button')) return;
        if (!s.down || s.down.t === 'mouse') return;
        if (Math.abs(e.clientX - s.down.x) + Math.abs(e.clientY - s.down.y) > 12) return;
        if (!s.painted) paint(s);
        var b = card.getBoundingClientRect();
        s.pressed = !s.pressed;
        sync(s, e.clientX - b.left, e.clientY - b.top);
      });
      on(s.btn, 'click', function () {
        if (!s.painted) paint(s);
        var p = centerOf(s, s.btn);
        s.pressed = !s.pressed; s.preview = false;
        sync(s, p.x, p.y);
      });
      // Keyboard focus on the toggle previews the film; pressing it keeps it.
      on(s.btn, 'focus', function () {
        var kb = false;
        try { kb = s.btn.matches(':focus-visible'); } catch (e) { kb = false; }
        if (!kb || s.pressed) return;
        if (!s.painted) paint(s);
        var p = centerOf(s, s.btn);
        s.preview = true;
        sync(s, p.x, p.y);
      });
      on(s.btn, 'blur', function () { if (s.preview) { s.preview = false; sync(s); } });
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && full(s)) { s.pressed = false; s.preview = false; sync(s); }
      });
      fx.watch(card, function (vis) { s.visible = vis; if (vis && !s.painted) paint(s); }, { rootMargin: '200px 0px' });
    });

    // One frame: read rects once if the page moved, then write transforms only.
    fx.loop(function (t, dt) {
      var i, s;
      if (rectsDirty) {
        for (i = 0; i < moving.length; i++) { var r = moving[i].card.getBoundingClientRect(); moving[i].left = r.left; moving[i].top = r.top; }
        rectsDirty = false;
      }
      var kp = 1 - Math.pow(1 - 0.42, dt / 16.7), ks = 1 - Math.pow(1 - 0.2, dt / 16.7);
      for (i = moving.length - 1; i >= 0; i--) {
        s = moving[i];
        if (s.follow && s.hover && !full(s)) { s.tx = s.px - s.left; s.ty = s.py - s.top; }
        if (s.snapPos) { s.x = s.tx; s.y = s.ty; s.snapPos = false; }
        if (s.snap) { s.x = s.tx; s.y = s.ty; s.sc = s.ts; s.snap = false; }
        s.x += (s.tx - s.x) * kp; s.y += (s.ty - s.y) * kp; s.sc += (s.ts - s.sc) * ks;
        var settled = Math.abs(s.tx - s.x) < 0.2 && Math.abs(s.ty - s.y) < 0.2 && Math.abs(s.ts - s.sc) < 0.002;
        if (settled) { s.x = s.tx; s.y = s.ty; s.sc = s.ts; }
        write(s);
        if (settled) moving.splice(i, 1);
      }
    }, function () { return moving.length > 0 && fx.isLive(sec); });

    addEventListener('scroll', function () {
      rectsDirty = true;
      cards.forEach(function (s) { if (s.hover && !full(s)) animate(s); });
    }, { passive: true });
    var resizeTimer = 0;
    addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        rectsDirty = true;
        cards.forEach(function (s) { s.painted = ''; if (s.visible) paint(s); });
      }, 120);
    });
    fx.onPage(function () {
      if (!fx.isLive(sec)) return;
      requestAnimationFrame(function () { cards.forEach(function (s) { if (s.visible || !('IntersectionObserver' in window)) paint(s); }); });
    });
    if (document.fonts && document.fonts.load) {
      document.fonts.load('500 10px "DM Mono"').then(function () {
        fontsReady = true;
        cards.forEach(function (s) { if (s.painted) { s.painted = ''; paint(s); } });
      }, function () {});
    }
  }

  /* ------------------------------------------------------------------
     2. Procedure: the line fills with the list's natural travel through
        the viewport (no pin). Rects are cached; frames write transforms.
     ------------------------------------------------------------------ */
  function initProcedure(fx) {
    var sec = document.getElementById('procedure');
    var list = $('.fxp-steps', sec);
    if (!list) return;
    var steps = $$('.fxp-step', list);
    var n = steps.length;
    if (!n) return;
    var fills = steps.map(function (s) { return $('.fxp-fill', s); });
    var visible = false, cur = -1, target = 0;
    var geo = { top: 0, h: 1, vh: window.innerHeight, wide: window.innerWidth > 900 };
    var lastFill = steps.map(function () { return -1; });
    var lastActive = -2, lastCurrent = -2;

    function cache() {
      if (!fx.isLive(list)) return;
      var r = list.getBoundingClientRect();
      geo.top = r.top + window.pageYOffset; geo.h = r.height || 1;
      geo.vh = window.innerHeight;
      var wide = window.innerWidth > 900;
      if (wide !== geo.wide) lastFill = lastFill.map(function () { return -1; });
      geo.wide = wide;
    }
    function render(p) {
      var pos = p * (n - 1), i;
      var active = p > 0.002 ? Math.min(n - 1, Math.floor(pos + 0.04)) : -1;
      if (active !== lastActive) {
        steps.forEach(function (s, k) { s.classList.toggle('is-active', k <= active); });
        lastActive = active;
      }
      var current = p > 0.002 && p < 0.998 ? active : -1;
      if (current !== lastCurrent) {
        steps.forEach(function (s, k) { s.classList.toggle('is-current', k === current); });
        lastCurrent = current;
      }
      for (i = 0; i < n; i++) {
        if (!fills[i]) continue;
        var v = Math.round(fx.clamp(pos - i, 0, 1) * 1000) / 1000;
        if (v === lastFill[i]) continue;
        lastFill[i] = v;
        fills[i].style.transform = (geo.wide ? 'scaleX(' : 'scaleY(') + v + ')';
      }
    }
    function progressNow() {
      var top = geo.top - window.pageYOffset, vh = geo.vh;
      var startLine = vh * (geo.wide ? 0.85 : 0.8), endLine = vh * (geo.wide ? 0.42 : 0.55);
      return fx.clamp((startLine - top) / (geo.h + startLine - endLine), 0, 1);
    }

    steps.forEach(function (s) {
      var head = $('.fxp-head', s), detail = $('.fxp-detail', s);
      if (!head || !detail) return;
      head.addEventListener('click', function () {
        var open = head.getAttribute('aria-expanded') !== 'true';
        head.setAttribute('aria-expanded', String(open));
        detail.hidden = !open;
        s.classList.toggle('is-open', open);
      });
    });

    if ('ResizeObserver' in window) new ResizeObserver(function () { cache(); if (fx.kick) fx.kick(); }).observe(list);
    addEventListener('resize', cache);
    fx.onPage(function () { if (fx.isLive(list)) requestAnimationFrame(function () { cache(); cur = -1; if (fx.kick) fx.kick(); }); });

    if (fx.reduced) { render(1); return; }
    cache();
    render(0);
    fx.watch(list, function (v) { visible = v; if (v && fx.kick) fx.kick(); }, { rootMargin: '80px 0px' });
    fx.loop(function (t, dt) {
      target = progressNow();
      if (cur < 0) cur = target;
      cur += (target - cur) * (1 - Math.pow(1 - 0.2, dt / 16.7));
      if (Math.abs(target - cur) < 0.0005) cur = target;
      render(cur);
    }, function () { return fx.isLive(list) && (visible || Math.abs(target - cur) > 0.0005); });
  }

  /* ------------------------------------------------------------------
     3. Quote request form
     collect() -> payload with the API's keys; postForm() sends it when
     data-quote-endpoint is set, otherwise the final step composes a
     brief to copy and send on LinkedIn.
     ------------------------------------------------------------------ */
  function initQuote(fx) {
    var page = document.querySelector('.page[data-page="quote"]');
    var form = $('[data-fxq-form]', page);
    var done = $('[data-fxq-done]', page);
    if (!form || !done) return;

    var STORE = 'ohx:quote:v1';
    var steps = $$('[data-fxq-step]', form);
    var N = steps.length;
    var body = $('[data-fxq-body]', form);
    var count = $('[data-fxq-count]', form);
    var live = $('[data-fxq-live]', form);
    var alertEl = $('[data-fxq-alert]', form);
    var review = $('[data-fxq-review]', form);
    var progBtns = $$('[data-fxq-goto]', form);
    var btnBack = $('[data-fxq-back]', form);
    var btnNext = $('[data-fxq-next]', form);
    var btnSubmit = $('[data-fxq-submit]', form);
    var btnReview = $('[data-fxq-review-jump]', form);
    var briefEl = $('[data-fxq-brief]', done);
    var copyStatus = $('[data-fxq-copy-status]', done);
    var chars = $('[data-fxq-chars]', form);
    var notesEl = form.elements.namedItem('notes');
    var startedEl = form.elements.namedItem('startedAt');
    if (!N || !btnNext || !btnSubmit) return;
    var endpoint = (form.getAttribute('data-quote-endpoint') || '').trim();
    var submitLabel = endpoint ? 'Send request ' : 'Prepare brief ';
    var cur = 1, max = 1, sending = false;

    var LABELS = ['Organisation', 'Needs', 'Data', 'Scope', 'Contact', 'Review'];
    var FIELDS = {
      1: ['orgType', 'orgName', 'role'],
      2: ['services'],
      3: ['dataSource', 'modalities'],
      4: ['timeline', 'volume', 'notes'],
      5: ['name', 'email', 'consent', 'website']
    };
    var STEP_OF = {};
    Object.keys(FIELDS).forEach(function (s) { FIELDS[s].forEach(function (f) { STEP_OF[f] = +s; }); });
    var GROUPS = { services: 1, modalities: 1 };
    var LIMITS = { orgName: 200, role: 120, volume: 100, notes: 4000, name: 120, email: 254 };
    var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

    if (btnSubmit.firstChild && btnSubmit.firstChild.nodeType === 3) btnSubmit.firstChild.nodeValue = submitLabel;

    /* ---------- field helpers ---------- */
    function controls(name) { return Array.prototype.filter.call(form.elements, function (x) { return x.name === name; }); }
    function getVal(name) {
      var els = controls(name);
      if (!els.length) return GROUPS[name] ? [] : '';
      var t = els[0].type;
      if (t === 'radio') { var ch = els.filter(function (x) { return x.checked; })[0]; return ch ? ch.value : ''; }
      if (t === 'checkbox') {
        if (GROUPS[name]) return els.filter(function (x) { return x.checked; }).map(function (x) { return x.value; });
        return els[0].checked;
      }
      return els[0].value;
    }
    function setVal(name, v) {
      var els = controls(name);
      if (!els.length) return;
      var t = els[0].type;
      if (t === 'radio') els.forEach(function (x) { x.checked = x.value === v; });
      else if (t === 'checkbox') {
        if (GROUPS[name]) els.forEach(function (x) { x.checked = Array.isArray(v) && v.indexOf(x.value) > -1; });
        else els[0].checked = v === true;
      } else if (els[0].tagName === 'SELECT') {
        var ok = Array.prototype.some.call(els[0].options, function (o) { return o.value === v; });
        els[0].value = ok ? v : '';
      } else if (typeof v === 'string') {
        els[0].value = v.slice(0, LIMITS[name] || 4000);
      }
    }

    /** The payload. Keys follow the OncoloHealth API's quote request shape (api/src/schemas.ts). */
    function collect() {
      var started = parseInt(startedEl && startedEl.value, 10);
      return {
        orgType: getVal('orgType'),
        orgName: String(getVal('orgName')).trim(),
        role: String(getVal('role')).trim(),
        services: getVal('services'),
        dataSource: getVal('dataSource'),
        modalities: getVal('modalities'),
        timeline: getVal('timeline'),
        volume: String(getVal('volume')).trim(),
        notes: String(getVal('notes')).trim(),
        name: String(getVal('name')).trim(),
        email: String(getVal('email')).trim(),
        consent: getVal('consent') === true,
        website: getVal('website'),
        startedAt: isFinite(started) ? started : null
      };
    }

    Array.prototype.forEach.call(form.elements, function (x) {
      if (x.name) x.setAttribute('data-fxq-desc', x.getAttribute('aria-describedby') || '');
    });
    function setError(name, msg) {
      var err = form.querySelector('#fxq-err-' + name);
      var field = form.querySelector('[data-field="' + name + '"]');
      if (err) { err.textContent = msg || ''; err.hidden = !msg; }
      if (field) field.classList.toggle('is-invalid', !!msg);
      controls(name).forEach(function (x) {
        var base = x.getAttribute('data-fxq-desc') || '';
        if (msg) {
          x.setAttribute('aria-invalid', 'true');
          x.setAttribute('aria-describedby', (base + ' fxq-err-' + name).trim());
        } else {
          x.removeAttribute('aria-invalid');
          if (base) x.setAttribute('aria-describedby', base); else x.removeAttribute('aria-describedby');
        }
      });
    }
    function check(name, d) {
      switch (name) {
        case 'orgType': return d.orgType ? '' : 'Choose the type of organisation.';
        case 'orgName':
          if (d.orgName.length < 2) return 'Enter your organisation’s name.';
          return d.orgName.length <= 200 ? '' : 'Keep this under 200 characters.';
        case 'role': return d.role.length <= 120 ? '' : 'Keep this under 120 characters.';
        case 'services': return d.services.length ? '' : 'Select at least one kind of help.';
        case 'dataSource': return d.dataSource ? '' : 'Choose where the data would come from, or “Not decided yet”.';
        case 'modalities': return d.modalities.length ? '' : 'Select at least one modality, or “Not sure yet”.';
        case 'timeline': return d.timeline ? '' : 'Choose a timeline.';
        case 'volume': return d.volume.length <= 100 ? '' : 'Keep this under 100 characters.';
        case 'notes': return d.notes.length <= 4000 ? '' : 'Keep this under 4,000 characters.';
        case 'name':
          if (!d.name) return 'Enter your name.';
          return d.name.length <= 120 ? '' : 'Keep this under 120 characters.';
        case 'email':
          if (!d.email) return 'Enter your work email.';
          return EMAIL_RE.test(d.email) && d.email.length <= 254 ? '' : 'Enter an email address like name@organisation.org.';
        case 'consent': return d.consent ? '' : 'Please confirm we may contact you about this request.';
        default: return '';
      }
    }
    function focusField(name) {
      var els = controls(name);
      if (!els.length) return;
      var target = els.filter(function (x) { return x.checked; })[0] || els[0];
      try { target.focus({ preventScroll: false }); } catch (e) { target.focus(); }
    }
    function validateStep(n, show) {
      var d = collect(), bad = [];
      (FIELDS[n] || []).forEach(function (f) {
        if (f === 'website') return;
        var msg = check(f, d);
        if (show) setError(f, msg);
        if (msg) bad.push(f);
      });
      if (show && bad.length) {
        focusField(bad[0]);
        announce(bad.length === 1 ? 'One field needs attention.' : bad.length + ' fields need attention.');
      }
      return bad.length === 0;
    }
    function announce(msg) {
      if (!live) return;
      live.textContent = '';
      setTimeout(function () { live.textContent = msg; }, 40);
    }
    function setAlert(msg) { if (!alertEl) return; alertEl.textContent = msg || ''; alertEl.hidden = !msg; }

    /* ---------- persistence ---------- */
    var PERSIST = ['orgType', 'orgName', 'role', 'services', 'dataSource', 'modalities', 'timeline', 'volume', 'notes', 'name', 'email', 'consent'];
    function save() {
      var d = collect(), v = {};
      PERSIST.forEach(function (k) { v[k] = d[k]; });
      store(STORE, JSON.stringify({ v: v, s: cur, m: max, t: d.startedAt }));
    }
    function restore() {
      try {
        var raw = load(STORE);
        if (!raw) return;
        var d = JSON.parse(raw);
        if (!d || typeof d !== 'object') return;
        var v = d.v || {};
        PERSIST.forEach(function (k) { if (k in v) setVal(k, v[k]); });
        if (startedEl && typeof d.t === 'number') startedEl.value = String(d.t);
        max = fx.clamp(parseInt(d.m, 10) || 1, 1, N);
        cur = fx.clamp(parseInt(d.s, 10) || 1, 1, max);
      } catch (e) { /* ignore corrupt state */ }
    }

    /* ---------- review, laid out as the brief ---------- */
    function optText(name, value) {
      var input = controls(name).filter(function (x) { return x.value === value; })[0];
      if (!input) return value;
      var lab = input.closest('label');
      var t = lab && lab.querySelector('[data-fxq-text]');
      return (t || lab || input).textContent.trim();
    }
    function selectText(name) {
      var s = controls(name)[0];
      if (!s || !s.value || !s.options) return '';
      return s.options[s.selectedIndex] ? s.options[s.selectedIndex].textContent : s.value;
    }
    var REVIEW = [
      { step: 1, title: 'Organisation', rows: [['Type', 'orgType'], ['Name', 'orgName'], ['Role', 'role']] },
      { step: 2, title: 'Needs', rows: [['Services', 'services']] },
      { step: 3, title: 'Data', rows: [['Source', 'dataSource'], ['Modalities', 'modalities']] },
      { step: 4, title: 'Scope', rows: [['Timeline', 'timeline'], ['Data size', 'volume'], ['Question', 'notes']] },
      { step: 5, title: 'Contact', rows: [['Name', 'name'], ['Work email', 'email'], ['Consent', 'consent']] }
    ];
    function display(key, d) {
      var v = d[key];
      if (key === 'orgType' || key === 'dataSource') return v ? optText(key, v) : '';
      if (key === 'services' || key === 'modalities') return (v || []).map(function (x) { return optText(key, x); }).join(', ');
      if (key === 'timeline') return selectText(key);
      if (key === 'consent') return v ? 'Yes, you may contact me about this request' : '';
      return v;
    }
    function make(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
    function today() {
      try { return new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase(); } catch (e) { return ''; }
    }
    function renderReview() {
      if (!review) return;
      var d = collect();
      while (review.firstChild) review.removeChild(review.firstChild);
      var doc = make('article', 'fxq-doc');
      var head = make('header', 'fxq-doc-head');
      var kick = make('div', 'fxq-doc-kicker');
      kick.appendChild(make('span', '', 'Collaboration brief'));
      kick.appendChild(make('span', '', today()));
      head.appendChild(kick);
      head.appendChild(make('h3', 'fxq-doc-title', d.orgName || 'Your organisation'));
      doc.appendChild(head);
      REVIEW.forEach(function (grp) {
        var sec = make('section');
        var h = make('h3');
        h.appendChild(make('span', '', pad(grp.step)));
        h.appendChild(document.createTextNode(grp.title));
        var dl = make('dl');
        grp.rows.forEach(function (r) {
          var text = display(r[1], d);
          dl.appendChild(make('dt', '', r[0]));
          dl.appendChild(make('dd', text ? '' : 'is-empty', text || 'Not provided'));
        });
        var edit = make('button', 'fxq-review-edit', 'Edit');
        edit.type = 'button';
        edit.setAttribute('data-fxq-edit-step', String(grp.step));
        edit.setAttribute('aria-label', 'Edit ' + grp.title.toLowerCase());
        sec.appendChild(h); sec.appendChild(dl); sec.appendChild(edit);
        doc.appendChild(sec);
      });
      review.appendChild(doc);
    }

    /* ---------- the brief ---------- */
    function composeBrief(d) {
      var out = ['OncoloHealth collaboration request', ''];
      out.push('Organisation: ' + d.orgName + (d.orgType ? ' (' + optText('orgType', d.orgType) + ')' : ''));
      if (d.role) out.push('Role: ' + d.role);
      out.push('Help needed: ' + display('services', d));
      out.push('Data: ' + display('dataSource', d));
      out.push('Modalities: ' + display('modalities', d));
      out.push('Timeline: ' + display('timeline', d));
      if (d.volume) out.push('Approximate data size: ' + d.volume);
      if (d.notes) { out.push(''); out.push('Question and constraints:'); out.push(d.notes); }
      out.push(''); out.push('Contact: ' + d.name + ' <' + d.email + '>');
      return out.join('\n');
    }

    /* ---------- step UI ---------- */
    function paint() {
      progBtns.forEach(function (b) {
        var k = +b.getAttribute('data-fxq-goto');
        b.classList.toggle('is-current', k === cur);
        b.classList.toggle('is-done', k !== cur && k <= max && k < N && validateStep(k, false));
        b.disabled = k > max;
        if (k === cur) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
        b.setAttribute('aria-label', 'Step ' + k + ': ' + LABELS[k - 1] + (k === cur ? ' (current)' : (k <= max ? '' : ' (not yet available)')));
      });
      if (count) count.textContent = pad(cur) + ' / ' + pad(N);
      if (btnBack) btnBack.hidden = cur === 1;
      btnNext.hidden = cur === N;
      btnSubmit.hidden = cur !== N;
      if (btnReview) btnReview.hidden = !(max === N && cur < N);
    }
    function showOnly(n) { steps.forEach(function (s) { s.hidden = +s.getAttribute('data-fxq-step') !== n; }); }
    function scrollToCard(target) {
      var r = target.getBoundingClientRect(), off = headerOffset();
      if (r.top < off || r.top > window.innerHeight * 0.6) {
        window.scrollTo({ top: window.pageYOffset + r.top - off, behavior: fx.reduced ? 'auto' : 'smooth' });
      }
    }
    function focusStep(stepEl) {
      var t = $('[data-fxq-step-title]', stepEl);
      if (t) { try { t.focus({ preventScroll: true }); } catch (e) { t.focus(); } }
      scrollToCard(form);
    }
    function enter(node, cls, dir) {
      if (fx.reduced || !node) return;
      node.style.setProperty('--dir', String(dir || 1));
      node.classList.remove(cls);
      void node.offsetWidth;
      node.classList.add(cls);
      node.addEventListener('animationend', function off() { node.classList.remove(cls); node.removeEventListener('animationend', off); });
    }
    function scan() {
      if (fx.reduced || !body) return;
      body.style.setProperty('--scan-h', body.offsetHeight + 'px');
      body.classList.remove('is-scanning');
      void body.offsetWidth;
      body.classList.add('is-scanning');
    }
    function goTo(n, after) {
      n = fx.clamp(n, 1, N);
      if (n === cur) { if (after) after(); return; }
      var dir = n > cur ? 1 : -1;
      if (n === N) renderReview();
      cur = n;
      max = Math.max(max, n);
      paint();
      save();
      showOnly(n);
      enter(steps[n - 1], 'is-entering', dir);
      scan();
      focusStep(steps[n - 1]);
      announce('Step ' + n + ' of ' + N + ': ' + LABELS[n - 1]);
      if (after) after();
    }
    function firstInvalidBefore(k) {
      for (var i = 1; i < k; i++) if (!validateStep(i, false)) return i;
      return 0;
    }
    function next() {
      setAlert('');
      if (!validateStep(cur, true)) return;
      goTo(cur + 1);
    }
    function jump(k) {
      if (k === cur) return;
      if (k > cur) {
        var bad = firstInvalidBefore(k);
        if (bad) {
          if (bad === cur) validateStep(cur, true);
          else goTo(bad, function () { validateStep(bad, true); });
          return;
        }
      }
      goTo(k);
    }

    /* ---------- submission ---------- */
    var REFERENCE = /^OH-[QC]-[0-9A-Z-]{4,32}$/;
    function retryText(header) {
      var seconds = Number(header);
      if (!isFinite(seconds) || seconds <= 0) return 'in a few minutes';
      var minutes = Math.ceil(seconds / 60);
      return minutes <= 1 ? 'in about a minute' : 'in about ' + minutes + ' minutes';
    }
    function readErrors(b) {
      if (!b || typeof b !== 'object' || !b.errors || typeof b.errors !== 'object' || Array.isArray(b.errors)) return null;
      var out = {}, any = false;
      Object.keys(b.errors).forEach(function (k) {
        var m = b.errors[k];
        if (typeof m === 'string' && m.length <= 500) { out[k] = m; any = true; }
      });
      return any ? out : null;
    }
    /** Port of postForm (web/src/scripts/api.ts): resolves {ok, reference} | {ok:false, errors}; rejects on network failure. */
    function postForm(url, data) {
      var ctrl = 'AbortController' in window ? new AbortController() : null;
      var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 15000) : 0;
      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(data),
        credentials: 'omit', cache: 'no-store', redirect: 'error',
        signal: ctrl ? ctrl.signal : undefined
      }).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (b) {
          clearTimeout(timer);
          if (res.ok && b && b.ok === true && typeof b.reference === 'string' && REFERENCE.test(b.reference)) return { ok: true, reference: b.reference };
          switch (res.status) {
            case 400: return { ok: false, errors: readErrors(b) || { _form: 'Some details need attention.' } };
            case 403: return { ok: false, errors: { _form: 'Your request was blocked by our security checks. Refresh the page and try again.' } };
            case 413: return { ok: false, errors: { _form: 'That submission is too large. Please shorten your notes and try again.' } };
            case 429: return { ok: false, errors: { _form: 'You’ve sent several requests in a short time. Please try again ' + retryText(res.headers.get('Retry-After')) + '.' } };
            default: {
              var rid = b && typeof b.requestId === 'string' ? b.requestId.slice(0, 64) : '';
              return { ok: false, errors: { _form: 'Something went wrong on our side' + (rid ? ' (ref ' + rid + ')' : '') + '. Please try again shortly.' } };
            }
          }
        });
      }, function (err) { clearTimeout(timer); throw err; });
    }
    function showErrors(errors) {
      errors = errors || {};
      var firstStep = 0, firstField = null, general = [];
      Object.keys(errors).forEach(function (key) {
        var msg = String(errors[key] || 'Check this field.');
        var s = STEP_OF[key];
        if (s && key !== 'website' && form.querySelector('#fxq-err-' + key)) {
          setError(key, msg);
          if (!firstStep || s < firstStep) { firstStep = s; firstField = key; }
        } else general.push(msg);
      });
      setAlert(general.length ? general.join(' ') : (firstStep ? 'Some details need attention before we can send your request.' : ''));
      if (firstStep) {
        goTo(firstStep, function () {
          Object.keys(errors).forEach(function (k) { if (STEP_OF[k] === firstStep && k !== 'website') setError(k, String(errors[k])); });
          focusField(firstField);
        });
      } else if (general.length && alertEl) {
        alertEl.setAttribute('tabindex', '-1');
        alertEl.focus();
      }
    }
    function setSending(onOff) {
      sending = onOff;
      btnSubmit.disabled = onOff;
      btnSubmit.setAttribute('aria-busy', String(onOff));
      if (btnSubmit.firstChild && btnSubmit.firstChild.nodeType === 3) btnSubmit.firstChild.nodeValue = onOff ? 'Sending… ' : submitLabel;
    }
    function handleSubmit() {
      if (sending) return;
      setAlert('');
      var bad = firstInvalidBefore(N);
      if (bad) { goTo(bad, function () { validateStep(bad, true); }); return; }
      var data = collect();
      if (!endpoint) { showDone(data, ''); return; }
      setSending(true);
      postForm(endpoint, data).then(function (res) {
        setSending(false);
        if (res && res.ok) showDone(data, res.reference);
        else showErrors((res && res.errors) || { _form: 'We couldn’t send your request. Please try again.' });
      }, function () {
        setSending(false);
        showErrors({ _form: 'Network error: we couldn’t reach the server. Your answers are saved; please try again.' });
      });
    }
    function setText(sel, text) { var x = $(sel, done); if (x) x.textContent = text; }
    function showDone(data, reference) {
      if (briefEl) briefEl.value = composeBrief(data);
      if (copyStatus) copyStatus.textContent = '';
      var title = $('[data-fxq-done-title]', done);
      if (title) {
        while (title.firstChild) title.removeChild(title.firstChild);
        title.appendChild(document.createTextNode(reference ? 'Request ' : 'Your brief is '));
        title.appendChild(make('em', '', reference ? 'received.' : 'ready.'));
      }
      if (reference) {
        setText('[data-fxq-done-kicker]', 'Request sent');
        setText('[data-fxq-ref]', reference);
        setText('[data-fxq-done-lead]', 'Your reference is ' + reference + '. Quote it in any follow-up. A copy of your brief is below.');
        store(STORE, null);
      } else {
        setText('[data-fxq-done-kicker]', 'Your brief');
        setText('[data-fxq-ref]', 'READY');
        setText('[data-fxq-done-lead]', 'Copy it and send it to Jordi on LinkedIn, where collaboration conversations start.');
      }
      form.hidden = true;
      done.hidden = false;
      enter(done, 'is-entering', 1);
      if (title) { try { title.focus({ preventScroll: true }); } catch (e) { title.focus(); } }
      scrollToCard(done);
      announce(reference ? 'Request received. Reference ' + reference.split('').join(' ') + '.' : 'Your brief is ready to copy.');
    }
    function copyBrief() {
      if (!briefEl) return;
      var text = briefEl.value;
      function say(m) { if (copyStatus) copyStatus.textContent = m; }
      function fallback() {
        var ok = false;
        briefEl.focus();
        briefEl.select();
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        say(ok ? 'Brief copied to the clipboard.' : 'Select the brief and copy it with Ctrl+C or Cmd+C.');
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { say('Brief copied to the clipboard.'); }, fallback);
      } else fallback();
    }
    function backToForm(step) {
      done.hidden = true;
      form.hidden = false;
      cur = 0;
      goTo(step || N);
    }
    function restart() {
      form.reset();
      Object.keys(STEP_OF).forEach(function (f) { setError(f, ''); });
      setAlert('');
      if (startedEl) startedEl.value = '';
      cur = 1; max = 1;
      store(STORE, null);
      done.hidden = true;
      form.hidden = false;
      showOnly(1); paint(); updateChars();
      focusStep(steps[0]);
    }

    /* ---------- events ---------- */
    function updateChars() { if (chars && notesEl) chars.textContent = notesEl.value.length.toLocaleString('en') + ' / 4,000'; }
    form.addEventListener('focusin', function () {
      if (startedEl && !startedEl.value) { startedEl.value = String(Date.now()); save(); }
    });
    function onEdit(e) {
      var t = e.target;
      if (!t || !t.name || t.name === 'website' || t.name === 'startedAt') return;
      if (t.name === 'notes') updateChars();
      // "Not sure yet" and specific modalities exclude each other.
      if (t.name === 'modalities' && t.checked && e.type === 'change') {
        controls('modalities').forEach(function (x) {
          if (x !== t && (t.value === 'unsure' || x.value === 'unsure')) x.checked = false;
        });
      }
      var field = form.querySelector('[data-field="' + t.name + '"]');
      if (field && field.classList.contains('is-invalid')) setError(t.name, check(t.name, collect()));
      save();
    }
    form.addEventListener('input', onEdit);
    form.addEventListener('change', onEdit);
    form.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.isComposing || e.shiftKey || e.altKey || e.metaKey || e.ctrlKey) return;
      var t = e.target;
      if (!t || (t.tagName !== 'INPUT' && t.tagName !== 'SELECT')) return;
      e.preventDefault();
      if (cur < N) next(); else handleSubmit();
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (cur < N) next(); else handleSubmit();
    });
    btnNext.addEventListener('click', next);
    on(btnBack, 'click', function () { setAlert(''); goTo(cur - 1); });
    on(btnReview, 'click', function () { jump(N); });
    progBtns.forEach(function (b) { b.addEventListener('click', function () { jump(+b.getAttribute('data-fxq-goto')); }); });
    on(review, 'click', function (e) {
      var b = e.target.closest('[data-fxq-edit-step]');
      if (b) goTo(+b.getAttribute('data-fxq-edit-step'));
    });
    on($('[data-fxq-copy]', done), 'click', copyBrief);
    on($('[data-fxq-edit]', done), 'click', function () { backToForm(N); });
    on($('[data-fxq-restart]', done), 'click', restart);

    /* ---------- boot ---------- */
    restore();
    if (cur === N) renderReview();
    showOnly(cur);
    paint();
    updateChars();

    // A service card linked here: tick that service without clearing other answers.
    fx.onPage(function (id) {
      if (id !== 'quote') return;
      var svc = load(SERVICE_KEY);
      if (!svc) return;
      store(SERVICE_KEY, null);
      var box = controls('services').filter(function (x) { return x.value === svc; })[0];
      if (!box) return;
      box.checked = true;
      setError('services', '');
      save();
      paint();
      if (cur === N) renderReview();
    });
  }
})();
