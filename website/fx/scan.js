/* OncoloHealth fx: scan dividers and the SEQ HUD.
   Dividers are normal-flow bands (never pinned). Each scene is scrubbed by the band's natural
   travel through the viewport. Static layers (phantoms, tissue, speckle, film, rulers) are
   pre-rendered once per resize; frames only composite them. Rects are cached on resize / page
   change / layout change, so the animation frame never reads layout. */
(function () {
  'use strict';
  if (!window.OHX) return;

  var TAU = Math.PI * 2;
  var GOLD = 2.399963; // golden angle, used for radial k-space spokes
  var GLYPHS = '0123456789ABCDEFHKMNRSTX';

  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function seg(q, a, b) { return clamp((q - a) / (b - a), 0, 1); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function eOut(t) { return 1 - Math.pow(1 - t, 3); }        // decelerating reveals
  function eOut5(t) { return 1 - Math.pow(1 - t, 5); }       // snappy locks
  function eIO(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; } // travel
  function smooth(t) { return t * t * (3 - 2 * t); }         // fades
  function snap(v) { return Math.round(v) + 0.5; }           // crisp 1px hairlines
  function pad(n, l) { n = String(n); while (n.length < l) n = '0' + n; return n; }
  function rngf(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function glyph(i, tick) { return GLYPHS.charAt(((i + 3) * 7 + tick * 13 + ((i * tick) % 5)) % GLYPHS.length); }
  // DOM builder: strings become text nodes (no innerHTML).
  function h(tag, cls, kids) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    (kids || []).forEach(function (k) { el.appendChild(typeof k === 'string' ? document.createTextNode(k) : k); });
    return el;
  }
  // Offscreen layer drawn in CSS pixels.
  function layer(w, hh, dpr) {
    var cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.ceil(w * dpr));
    cv.height = Math.max(1, Math.ceil(hh * dpr));
    var g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { cv: cv, g: g, w: w, h: hh };
  }

  /* ---- colour: [r,g,b] arrays ---- */
  function rgb(hex) {
    var s = String(hex || '').replace('#', '');
    if (s.length === 3) s = s.charAt(0) + s.charAt(0) + s.charAt(1) + s.charAt(1) + s.charAt(2) + s.charAt(2);
    var n = parseInt(s, 16) || 0;
    return [n >> 16 & 255, n >> 8 & 255, n & 255];
  }
  function parseCss(s) {
    var m = String(s || '').match(/rgba?\(([^)]+)\)/i);
    if (!m) return null;
    var p = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
    return p.length >= 3 ? [p[0], p[1], p[2], p.length > 3 ? p[3] : 1] : null;
  }
  function col(c, a) {
    return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + clamp(a == null ? 1 : a, 0, 1).toFixed(3) + ')';
  }
  function mix(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]; }
  function lum(c) { return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255; }
  var WHITE = [255, 255, 255];

  function rrect(c, x, y, w, hh, r) {
    c.beginPath();
    c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + hh, r); c.arcTo(x + w, y + hh, x, y + hh, r);
    c.arcTo(x, y + hh, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  /* Radial sprites: gradients are rendered once and drawn scaled, never rebuilt per frame. */
  var sprites = {};
  function sprite(stops) {
    var key = stops.map(function (s) { return s[0] + ':' + s[1]; }).join('|');
    if (sprites[key]) return sprites[key];
    var S = 128, cv = document.createElement('canvas');
    cv.width = cv.height = S;
    var g = cv.getContext('2d'), gr = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    stops.forEach(function (s) { gr.addColorStop(s[0], s[1]); });
    g.fillStyle = gr; g.beginPath(); g.arc(S / 2, S / 2, S / 2, 0, TAU); g.fill(); // round: no square corners
    sprites[key] = cv;
    return cv;
  }

  var META = {
    mri: 'k-space · centre-out',
    pet: 'Count accumulation',
    path: 'Low to high power',
    xray: 'Exposure',
    us: 'Linear sweep',
    fusion: 'Rigid registration'
  };

  function init(fx) {
    var K = {};
    (function readPalette() {
      var p = fx.palette;
      K.ink = rgb(p.ink); K.cream = rgb(p.cream); K.paper = rgb(p.paper); K.peach = rgb(p.peach);
      K.pl = rgb(p.peachLight); K.pd = rgb(p.peachDeep); K.deep = rgb(p.deep); K.navy = rgb(p.navy);
      K.mono = getComputedStyle(document.documentElement).getPropertyValue('--fx-mono').trim() || 'ui-monospace, monospace';
    })();
    var FONT = '400 10px ' + K.mono;
    var FONT_SM = '400 9px ' + K.mono;

    function makeTone(dark, bg) {
      if (dark) {
        return { dark: true, bg: bg, line: K.cream, fg: K.cream, dim: mix(K.cream, bg, 0.3), faint: mix(K.cream, bg, 0.58),
          hi: K.pl, hot: K.peach, warm: K.pl, offset: col([182, 157, 145], 0.32) };
      }
      return { dark: false, bg: bg, line: K.ink, fg: K.ink, dim: mix(K.ink, bg, 0.34), faint: mix(K.ink, bg, 0.6),
        hi: K.pd, hot: [148, 82, 56], warm: K.pd, offset: col([231, 205, 189], 1) };
    }

    function label(c, txt, x, y, color, align, font) {
      c.font = font || FONT;
      c.textAlign = align || 'left';
      c.textBaseline = 'middle';
      if ('letterSpacing' in c) c.letterSpacing = '1.2px';
      c.fillStyle = color;
      c.fillText(txt, Math.round(x), Math.round(y));
      if ('letterSpacing' in c) c.letterSpacing = '0px';
    }

    /* ============================================================ scenes
       Scene contract: resize(w, h, dpr, P, ctx) pre-renders; draw(c, w, h, q, P, S) composites. */

    /* ================================================== image-based scenes
       Real licensed images, graded once per resize into the site palette through a per-pixel
       LUT, framed in a scanner panel. Frames only composite pre-rendered layers. */

    // Duotone LUTs: shadows navy -> mid mauve -> peach-light highlights -> warm white.
    function makeLut(stops) {
      var lut = new Uint8ClampedArray(768);
      for (var i = 0; i < 256; i++) {
        var t = i / 255, a = stops[0], b = stops[stops.length - 1];
        for (var s = 0; s < stops.length - 1; s++) if (t >= stops[s][0] && t <= stops[s + 1][0]) { a = stops[s]; b = stops[s + 1]; break; }
        var u = b[0] === a[0] ? 0 : (t - a[0]) / (b[0] - a[0]);
        u = u * u * (3 - 2 * u);
        lut[i * 3] = lerp(a[1][0], b[1][0], u); lut[i * 3 + 1] = lerp(a[1][1], b[1][1], u); lut[i * 3 + 2] = lerp(a[1][2], b[1][2], u);
      }
      return lut;
    }
    var LUT_WARM = null, LUT_COOL = null;
    function luts() {
      if (LUT_WARM) return;
      LUT_WARM = makeLut([[0, [11, 19, 33]], [0.3, [30, 48, 71]], [0.62, [160, 140, 142]], [0.84, K.pl], [1, [255, 248, 242]]]);
      LUT_COOL = makeLut([[0, [11, 19, 33]], [0.35, [36, 52, 74]], [0.7, [150, 156, 166]], [1, [242, 238, 234]]]);
    }

    /* Grade a crop of a source image into a w x h layer. Saturated pixels (annotation overlays
       in the source) are carried as a peach tint rather than flattened into grey. */
    function grade(img, crop, w, hh, dpr, o) {
      luts();
      var L = layer(w, hh, dpr), g = L.g;
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
      g.drawImage(img, crop[0], crop[1], crop[2], crop[3], 0, 0, w, hh);
      var id = g.getImageData(0, 0, L.cv.width, L.cv.height), p = id.data, lut = o.lut || LUT_WARM;
      var lo = o.lo || 0, hi = o.hi || 255, sc = 255 / (hi - lo), gam = o.gamma || 1, ov = o.overlay || 0, ac = o.accent || K.pl, inv = !!o.invert;
      var curve = new Uint8Array(256);
      for (var v = 0; v < 256; v++) curve[v] = clamp(Math.round(255 * Math.pow(clamp((v - lo) * sc, 0, 255) / 255, gam)), 0, 255);
      for (var i = 0; i < p.length; i += 4) {
        var r = p[i], gg = p[i + 1], b = p[i + 2];
        var mx = r > gg ? (r > b ? r : b) : (gg > b ? gg : b), mn = r < gg ? (r < b ? r : b) : (gg < b ? gg : b);
        var lum0 = (0.299 * r + 0.587 * gg + 0.114 * b) | 0, l = curve[inv ? 255 - lum0 : lum0] * 3;
        var R = lut[l], G2 = lut[l + 1], B = lut[l + 2], sat = (mx - mn) / 255;
        if (ov && sat > 0.16) {
          var t = Math.min(1, (sat - 0.16) * 3) * ov;
          l = curve[mx] * 3;
          R = lerp(lut[l], ac[0], t); G2 = lerp(lut[l + 1], ac[1], t); B = lerp(lut[l + 2], ac[2], t);
        }
        p[i] = R; p[i + 1] = G2; p[i + 2] = B;
      }
      g.putImageData(id, 0, 0);
      return L;
    }
    // Low-pass copies by repeated downsampling (no ctx.filter).
    function blurred(src, w, hh, dpr, scale) {
      var cur = src.cv, cw = cur.width, ch = cur.height;
      var tw = Math.max(2, Math.round(src.cv.width * scale)), th = Math.max(2, Math.round(src.cv.height * scale));
      while (cw / 2 > tw) {
        var nx = document.createElement('canvas');
        nx.width = Math.max(tw, Math.round(cw / 2)); nx.height = Math.max(th, Math.round(ch / 2));
        var ng = nx.getContext('2d'); ng.imageSmoothingQuality = 'high';
        ng.drawImage(cur, 0, 0, nx.width, nx.height);
        cur = nx; cw = nx.width; ch = nx.height;
      }
      var out = layer(w, hh, dpr);
      out.g.imageSmoothingEnabled = true; out.g.imageSmoothingQuality = 'high';
      out.g.drawImage(cur, 0, 0, w, hh);
      return out;
    }

    /* Panel geometry shared by the image scenes: a navy console with a soft shadow, a header
       strip, the main viewport (vw x vh) and an optional side element (sw wide). */
    function panelGeo(w, hh, aspect, sideRatio) {
      var compact = w < 640, pad = compact ? 12 : 18, head = 24;
      var ph = Math.round(hh * (compact ? 0.8 : 0.8)), py = Math.round(hh * 0.05);
      var vh2 = ph - pad * 2 - head, vw = Math.round(vh2 * aspect);
      var sw = compact ? 0 : Math.round(vh2 * sideRatio);
      var pw = vw + pad * 2 + (sw ? sw + pad : 0);
      var maxW = w - (compact ? 24 : 96);
      if (pw > maxW) { var k = maxW / pw; vh2 = Math.round(vh2 * k); vw = Math.round(vh2 * aspect); sw = compact ? 0 : Math.round(vh2 * sideRatio); pw = vw + pad * 2 + (sw ? sw + pad : 0); ph = vh2 + pad * 2 + head; }
      var px = Math.round((w - pw) / 2);
      return { compact: compact, pad: pad, head: head, px: px, py: py, pw: pw, ph: ph,
        vx: px + pad, vy: py + pad + head, vw: vw, vh: vh2, sx: px + pad * 2 + vw, sw: sw };
    }
    function hairRect(g, x, y, w, hh, color) {
      g.strokeStyle = color; g.lineWidth = 1;
      g.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, Math.round(w) - 1, Math.round(hh) - 1);
    }
    function cornerTicks(g, x, y, w, hh, color, l) {
      g.strokeStyle = color; g.lineWidth = 1; g.beginPath();
      [[x, y, 1, 1], [x + w, y, -1, 1], [x + w, y + hh, -1, -1], [x, y + hh, 1, -1]].forEach(function (p) {
        var a = snap(p[0] - (p[2] < 0 ? 1 : 0)), b = snap(p[1] - (p[3] < 0 ? 1 : 0));
        g.moveTo(a, b + p[3] * l); g.lineTo(a, b); g.lineTo(a + p[2] * l, b);
      });
      g.stroke();
    }
    function edgeRuler(g, x, y, len, n, color, vertical) {
      g.strokeStyle = color; g.lineWidth = 1; g.beginPath();
      for (var i = 0; i <= n; i++) {
        var t = Math.round(i / n * len), m = i % 4 === 0 ? 6 : 3;
        if (vertical) { var yy = snap(y + t); g.moveTo(x, yy); g.lineTo(x + m, yy); }
        else { var xx = snap(x + t); g.moveTo(xx, y); g.lineTo(xx, y - m); }
      }
      g.stroke();
    }
    // Console chrome, pre-rendered: soft shadow, navy panel, bloom, hairline frames, labels.
    function chrome(w, hh, dpr, P, G, labels) {
      var L = layer(w, hh, dpr), g = L.g, r = 3;
      g.save();
      g.shadowColor = P.dark ? 'rgba(0,0,0,.42)' : 'rgba(17,30,50,.26)'; g.shadowBlur = 44; g.shadowOffsetY = 20;
      rrect(g, G.px, G.py, G.pw, G.ph, r); g.fillStyle = col(P.dark ? [24, 38, 58] : K.deep, 1); g.fill();
      g.restore();
      g.save(); rrect(g, G.px, G.py, G.pw, G.ph, r); g.clip();
      var bl = g.createRadialGradient(G.px + G.pw * 0.78, G.py - G.ph * 0.2, 0, G.px + G.pw * 0.78, G.py - G.ph * 0.2, G.pw * 0.7);
      bl.addColorStop(0, 'rgba(255,255,255,.12)'); bl.addColorStop(0.55, 'rgba(255,255,255,.03)'); bl.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = bl; g.fillRect(G.px, G.py, G.pw, G.ph);
      g.restore();
      if (P.dark) { rrect(g, G.px + 0.5, G.py + 0.5, G.pw - 1, G.ph - 1, r); g.strokeStyle = col(K.cream, 0.1); g.lineWidth = 1; g.stroke(); }
      // header strip hairline
      g.fillStyle = col(K.cream, 0.1); g.fillRect(G.px + G.pad, G.py + G.head + Math.round(G.pad / 2) - 1, G.pw - G.pad * 2, 1);
      var hy = G.py + Math.round((G.head + G.pad) / 2) - 1;
      // secondary labels only where they fit beside the primary one
      function fits(a, b, span) { g.font = FONT; if ('letterSpacing' in g) g.letterSpacing = '1.2px'; var ok = g.measureText(a).width + g.measureText(b).width + 24 < span; if ('letterSpacing' in g) g.letterSpacing = '0px'; return ok; }
      label(g, labels[0], G.vx, hy, col(K.cream, 0.82));
      if (labels[1] && fits(labels[0], labels[1], G.vw)) label(g, labels[1], G.vx + G.vw, hy, col(K.cream, 0.45), 'right');
      if (G.sw && labels[2]) label(g, labels[2], G.sx, hy, col(K.cream, 0.82));
      if (G.sw && labels[3] && fits(labels[2], labels[3], G.sw)) label(g, labels[3], G.sx + G.sw, hy, col(K.cream, 0.45), 'right');
      // viewport frames
      g.fillStyle = col([8, 14, 25], 1); g.fillRect(G.vx, G.vy, G.vw, G.vh);
      hairRect(g, G.vx, G.vy, G.vw, G.vh, col(K.cream, 0.14));
      if (G.sw) hairRect(g, G.sx, G.vy, G.sw, G.vh, col(K.cream, 0.14));
      return L;
    }
    // Overlay chrome drawn above the image: corner ticks and edge rulers.
    function overlayChrome(w, hh, dpr, G, extra) {
      var L = layer(w, hh, dpr), g = L.g;
      cornerTicks(g, G.vx + 8, G.vy + 8, G.vw - 16, G.vh - 16, col(K.cream, 0.55), 10);
      edgeRuler(g, G.vx + 24, G.vy + G.vh - 1, G.vw - 48, 16, col(K.cream, 0.35), false);
      edgeRuler(g, G.vx, G.vy + 24, G.vh - 48, 16, col(K.cream, 0.35), true);
      if (extra) extra(g);
      return L;
    }

    var CREDIT = {
      'scan-brain.webp': { title: 'Brain MRI · Medical Segmentation Decathlon, Task01', credit: 'Antonelli, M., et al. The Medical Segmentation Decathlon. Nature Communications 13, 4128 (2022).', license: 'CC BY-SA 4.0', url: 'https://doi.org/10.1038/s41467-022-30695-9', note: 'Cropped and colour-graded; the crop is shared under the same licence. Source overlays retained.' },
      'scan-bone.webp': { title: 'Bone X-ray · BTXRD', credit: 'Yao, S., Huang, Y., Wang, X., et al. A Radiograph Dataset for the Classification, Localization, and Segmentation of Primary Bone Tumors. Scientific Data 12, 88 (2025).', license: 'CC BY 4.0', url: 'https://doi.org/10.6084/m9.figshare.27865398', note: 'Cropped and colour-graded.' },
      'scan-lung.webp': { title: 'Lung CT · LUNA16 / LIDC-IDRI', credit: 'Armato III, S. G., et al. (2015). Data From LIDC-IDRI. The Cancer Imaging Archive.', license: 'CC BY 3.0', url: 'https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX', note: 'Cropped and colour-graded; the PET-style uptake layer drawn over it in the fusion divider is an illustration, not acquired data.' }
    };

    /* MRI: a real brain slice reconstructs from k-space. Phase-encode lines fill centre-out in
       the k-space panel; the image sharpens from its low-frequency blur as they arrive. */
    function sceneMRI() {
      var G = null, ch = null, ov = null, lv = [], ks = null, cols = {}, img = null;
      var CROP = [104, 56, 572, 572];
      function kspace(S, dpr) {
        var L = layer(S, S, dpr), g = L.g, R = rngf(7), c0 = S / 2;
        g.fillStyle = col([8, 14, 25], 1); g.fillRect(0, 0, S, S);
        // log-magnitude look: bright centre, radial falloff, speckle grain, faint axes
        var id = g.getImageData(0, 0, L.cv.width, L.cv.height), p = id.data, W = L.cv.width, H = L.cv.height;
        luts();
        for (var y = 0; y < H; y++) {
          var dy = (y - H / 2) / (H / 2);
          for (var x = 0; x < W; x++) {
            var dx = (x - W / 2) / (W / 2), rr = Math.sqrt(dx * dx + dy * dy);
            var v = Math.exp(-rr * 5.2) * 0.95 + 0.22 * Math.exp(-rr * 1.6);
            v += 0.35 * Math.exp(-Math.abs(dx) * 60) * Math.exp(-Math.abs(dy) * 2.2) + 0.35 * Math.exp(-Math.abs(dy) * 60) * Math.exp(-Math.abs(dx) * 2.2);
            v *= 0.55 + 0.9 * R();
            v = clamp(Math.log(1 + v * 9) / Math.log(10), 0, 1);
            var l = (v * 255 | 0) * 3, i = (y * W + x) * 4;
            p[i] = LUT_WARM[l]; p[i + 1] = LUT_WARM[l + 1]; p[i + 2] = LUT_WARM[l + 2]; p[i + 3] = 255;
          }
        }
        g.putImageData(id, 0, 0);
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.strokeStyle = col(K.cream, 0.12); g.lineWidth = 1; g.beginPath();
        g.moveTo(snap(c0), 0); g.lineTo(snap(c0), S); g.moveTo(0, snap(c0)); g.lineTo(S, snap(c0)); g.stroke();
        return L;
      }
      return {
        img: 'scan-brain.webp',
        resize: function (w, hh, dpr, P, c, d) {
          img = d.images['scan-brain.webp'];
          G = panelGeo(w, hh, 1, 1);
          var detail = (d.detail || 'T2 · Axial').toUpperCase();
          ch = chrome(w, hh, dpr, P, G, ['MR · ' + detail, 'MSD TASK01', 'K-SPACE', 'PHASE ENCODE']);
          var full = grade(img, CROP, G.vw, G.vh, Math.min(dpr, 1.5), { lo: 6, hi: 235, gamma: 0.92, overlay: 0.5 });
          lv = [blurred(full, G.vw, G.vh, dpr, 1 / 40), blurred(full, G.vw, G.vh, dpr, 1 / 16), blurred(full, G.vw, G.vh, dpr, 1 / 6), full];
          ks = G.sw ? kspace(G.sw, Math.min(dpr, 1.5)) : null;
          ov = overlayChrome(w, hh, dpr, G, function (g) {
            label(g, 'R', G.vx + 14, G.vy + G.vh / 2, col(K.cream, 0.6));
            label(g, 'L', G.vx + G.vw - 14, G.vy + G.vh / 2, col(K.cream, 0.6), 'right');
            if (G.sw) {
              label(g, 'ky', G.sx + G.sw / 2 + 6, G.vy + 12, col(K.cream, 0.4));
              label(g, 'kx', G.sx + G.sw - 16, G.vy + G.vh / 2 - 8, col(K.cream, 0.4));
            }
          });
          cols.line = col(K.pl, 1); cols.glow = col(K.pl, 0.18); cols.txt = col(K.cream, 0.8); cols.dim = col(K.cream, 0.5); cols.hi = col(K.pl, 1);
        },
        draw: function (c, w, hh, q) {
          if (!G) return;
          var f = eIO(seg(q, 0.04, 0.97)), lines = Math.round(f * 256);
          c.drawImage(ch.cv, 0, 0, w, hh);
          // k-space: the filled band of phase-encode rows, centre-out
          if (ks && f > 0) {
            var half = f * G.sw / 2, top = G.sw / 2 - half, sc = ks.cv.width / G.sw;
            c.drawImage(ks.cv, 0, top * sc, ks.cv.width, half * 2 * sc, G.sx, G.vy + (G.vh - G.sw) / 2 + top, G.sw, half * 2);
            if (f < 1) {
              var yA = Math.round(G.vy + (G.vh - G.sw) / 2 + top), yB = Math.round(yA + half * 2);
              c.fillStyle = cols.glow; c.fillRect(G.sx, yA - 3, G.sw, 3); c.fillRect(G.sx, yB, G.sw, 3);
              c.fillStyle = cols.line; c.fillRect(G.sx, yA, G.sw, 1); c.fillRect(G.sx, yB - 1, G.sw, 1);
            }
          }
          // image: low-frequency blur -> sharp as k-space fills
          if (f > 0) {
            var s = Math.pow(f, 0.8) * 3, i0 = Math.min(2, Math.floor(s)), t = s - i0;
            c.globalAlpha = Math.min(1, f * 5);
            c.drawImage(lv[i0].cv, G.vx, G.vy, G.vw, G.vh);
            if (t > 0.01) { c.globalAlpha = Math.min(1, f * 5) * t; c.drawImage(lv[i0 + 1].cv, G.vx, G.vy, G.vw, G.vh); }
            c.globalAlpha = 1;
          }
          c.drawImage(ov.cv, 0, 0, w, hh);
          var fy = G.vy + G.vh - 14;
          label(c, f >= 1 ? 'RECON COMPLETE' : 'RECON ' + pad(Math.round(f * 100), 2) + '%', G.vx + G.vw - 14, fy - 10, f >= 1 ? cols.hi : cols.dim, 'right');
          if (G.sw) label(c, 'PE ' + pad(lines, 3) + ' / 256', G.sx + G.sw - 12, G.vy + G.vh - 14, cols.txt, 'right');
        }
      };
    }

    /* X-ray: the exposure bar develops the real radiograph from its latent image; a step wedge
       beside the film develops with it. */
    function sceneXRAY() {
      var G = null, ch = null, dev = null, lat = null, wedge = null, wedgeL = null, ov = null, glow = null, cols = {}, img = null;
      var CROP = [10, 0, 770, 770];
      return {
        img: 'scan-bone.webp',
        resize: function (w, hh, dpr, P, c, d) {
          img = d.images['scan-bone.webp'];
          G = panelGeo(w, hh, 1, 0.2);
          var detail = (d.detail || 'PA projection').toUpperCase();
          ch = chrome(w, hh, dpr, P, G, ['DX · ' + detail, 'BTXRD', 'WEDGE', '']);
          var d2 = Math.min(dpr, 1.5);
          dev = grade(img, CROP, G.vw, G.vh, d2, { lo: 34, hi: 228, gamma: 0.82 });
          // latent: the same frame, barely above film base
          lat = layer(G.vw, G.vh, d2);
          lat.g.fillStyle = col([12, 20, 34], 1); lat.g.fillRect(0, 0, G.vw, G.vh);
          lat.g.globalAlpha = 0.13; lat.g.drawImage(dev.cv, 0, 0, G.vw, G.vh); lat.g.globalAlpha = 1;
          if (G.sw) {
            var n = 11, sh = G.vh / n;
            wedge = layer(G.sw, G.vh, dpr); wedgeL = layer(G.sw, G.vh, dpr);
            for (var i = 0; i < n; i++) {
              var v = Math.round(i / (n - 1) * 255) * 3;
              wedge.g.fillStyle = 'rgb(' + LUT_WARM[v] + ',' + LUT_WARM[v + 1] + ',' + LUT_WARM[v + 2] + ')';
              wedge.g.fillRect(0, Math.round(i * sh), G.sw, Math.ceil(sh));
              label(wedge.g, pad(i, 2), G.sw - 8, i * sh + sh / 2, i > 6 ? col(K.deep, 0.75) : col(K.cream, 0.7), 'right', FONT_SM);
            }
            wedgeL.g.fillStyle = col([12, 20, 34], 1); wedgeL.g.fillRect(0, 0, G.sw, G.vh);
            wedgeL.g.globalAlpha = 0.13; wedgeL.g.drawImage(wedge.cv, 0, 0, G.sw, G.vh); wedgeL.g.globalAlpha = 1;
          }
          ov = overlayChrome(w, hh, dpr, G, function (g) {
            label(g, 'R', G.vx + 26, G.vy + 30, col(K.pl, 1));
            // film-edge markers: perforation-like ticks along the top edge
            g.fillStyle = col(K.cream, 0.18);
            for (var x = G.vx + 40; x < G.vx + G.vw - 40; x += 18) g.fillRect(Math.round(x), G.vy + 4, 8, 2);
          });
          glow = c.createLinearGradient(0, -36, 0, 0);
          glow.addColorStop(0, col(K.pl, 0)); glow.addColorStop(1, col(K.pl, 0.16));
          cols.bar = col(K.pl, 1); cols.dim = col(K.cream, 0.6); cols.hi = col(K.pl, 1);
        },
        draw: function (c, w, hh, q) {
          if (!G) return;
          var e = eIO(seg(q, 0.06, 0.97)), done = e >= 1;
          var y0 = G.vy, y1 = G.vy + G.vh, yb = Math.round(lerp(y1, y0, e));
          c.drawImage(ch.cv, 0, 0, w, hh);
          var sc = lat.cv.height / G.vh, top = yb - y0;
          // latent above the bar, developed below
          if (top > 0) c.drawImage(lat.cv, 0, 0, lat.cv.width, top * sc, G.vx, y0, G.vw, top);
          if (top < G.vh) c.drawImage(dev.cv, 0, top * sc, dev.cv.width, (G.vh - top) * sc, G.vx, yb, G.vw, G.vh - top);
          if (wedge) {
            var ws = wedge.cv.height / G.vh;
            if (top > 0) c.drawImage(wedgeL.cv, 0, 0, wedgeL.cv.width, top * ws, G.sx, y0, G.sw, top);
            if (top < G.vh) c.drawImage(wedge.cv, 0, top * ws, wedge.cv.width, (G.vh - top) * ws, G.sx, yb, G.sw, G.vh - top);
          }
          if (!done && e > 0) {
            var x0 = G.vx, x1 = (G.sw ? G.sx + G.sw : G.vx + G.vw), gTop = Math.max(y0, yb - 36);
            if (yb > y0) { c.save(); c.translate(0, yb); c.fillStyle = glow; c.fillRect(x0, gTop - yb, x1 - x0, yb - gTop); c.restore(); }
            c.fillStyle = cols.bar; c.fillRect(x0 - 10, yb, x1 - x0 + 20, 1);
          }
          c.drawImage(ov.cv, 0, 0, w, hh);
          label(c, done ? 'DEVELOPED' : 'EXPOSING ' + pad(Math.round(e * 100), 2) + '%', G.vx + G.vw - 26, G.vy + 30, done ? cols.hi : cols.dim, 'right');
        }
      };
    }

    /* Fusion: a real CT slice; an illustrative PET uptake layer slides and rotates into
       registration, crosshairs lock, and the residual-error trace runs down to zero. */
    function sceneFUSION() {
      var G = null, ch = null, ct = null, pet = null, ov = null, plot = null, cols = {}, img = null;
      var CROP = [14, 52, 750, 562], NOD = [456, 402], MED = [372, 300], NP = 120, err = new Float32Array(NP);
      for (var i = 0; i < NP; i++) { var t = i / (NP - 1); err[i] = 14.2 * Math.pow(1 - eIO(t), 1.15) + 0.35 * Math.sin(t * 19) * (1 - t); }
      function toV(px, py) { return [G.vx + (px - CROP[0]) / CROP[2] * G.vw, G.vy + (py - CROP[1]) / CROP[3] * G.vh]; }
      return {
        img: 'scan-lung.webp',
        resize: function (w, hh, dpr, P, c, d) {
          img = d.images['scan-lung.webp'];
          G = panelGeo(w, hh, CROP[2] / CROP[3], 0.8);
          ch = chrome(w, hh, dpr, P, G, ['PET/CT · AXIAL', 'LIDC-IDRI', 'REGISTRATION', 'RESIDUAL (MM)']);
          var d2 = Math.min(dpr, 1.5);
          ct = grade(img, CROP, G.vw, G.vh, d2, { lut: LUT_COOL, lo: 10, hi: 245, gamma: 1.1, overlay: 0 });
          // uptake layer in viewport-local coordinates, centred on the annotated nodule
          var S = Math.round(Math.max(G.vw, G.vh) * 1.2);
          pet = layer(S, S, d2);
          var n = toV(NOD[0], NOD[1]), m = toV(MED[0], MED[1]), ox = S / 2 - (n[0] - G.vx), oy = S / 2 - (n[1] - G.vy);
          var pg = pet.g, sx = G.vw / CROP[2];
          pg.globalCompositeOperation = 'lighter';
          pg.drawImage(sprite([[0, col(K.pl, 0.3)], [0.6, col(K.pl, 0.12)], [1, col(K.pl, 0)]]), ox + G.vw * 0.06, oy + G.vh * 0.04, G.vw * 0.88, G.vh * 0.86);
          var hot = sprite([[0, col(WHITE, 0.95)], [0.22, col([255, 226, 206], 0.85)], [0.55, col(K.pl, 0.5)], [1, col(K.pd, 0)]]);
          pg.drawImage(hot, ox + (n[0] - G.vx) - 58 * sx, oy + (n[1] - G.vy) - 58 * sx, 116 * sx, 116 * sx);
          pg.drawImage(hot, ox + (m[0] - G.vx) - 34 * sx, oy + (m[1] - G.vy) - 34 * sx, 68 * sx, 68 * sx);
          pg.globalCompositeOperation = 'source-over';
          G.petOx = ox; G.petOy = oy; G.petS = S; G.nod = n;
          ov = overlayChrome(w, hh, dpr, G);
          if (G.sw) {
            plot = layer(G.sw, G.vh, dpr);
            var g = plot.g, pl = 30, pr = 12, pt = 40, pb = 26, W2 = G.sw - pl - pr, H2 = G.vh - pt - pb;
            g.strokeStyle = col(K.cream, 0.08); g.lineWidth = 1; g.beginPath();
            for (var k = 0; k <= 4; k++) { var yy = snap(pt + k / 4 * H2); g.moveTo(pl, yy); g.lineTo(pl + W2, yy); }
            g.stroke();
            for (k = 0; k <= 4; k++) label(g, String(Math.round(16 - k * 4)), pl - 8, pt + k / 4 * H2, col(K.cream, 0.4), 'right', FONT_SM);
            label(g, 'ITERATION', pl + W2, G.vh - 10, col(K.cream, 0.4), 'right', FONT_SM);
            G.plot = { pl: pl, pt: pt, W2: W2, H2: H2 };
          }
          cols.hi = col(K.pl, 1); cols.dim = col(K.cream, 0.6); cols.fix = col(K.cream, 0.7); cols.trace = col(K.pl, 0.95);
        },
        draw: function (c, w, hh, q) {
          if (!G) return;
          var e = seg(q, 0.05, 0.86), lock = eOut5(seg(q, 0.86, 0.97)), upto = Math.max(1, Math.round(e * (NP - 1))), inv = clamp(err[upto] / 14.2, 0, 1) * (1 - lock);
          c.drawImage(ch.cv, 0, 0, w, hh);
          c.drawImage(ct.cv, G.vx, G.vy, G.vw, G.vh);
          var n = G.nod, dx = G.vw * 0.09 * inv, dy = -G.vh * 0.07 * inv, rot = 0.14 * inv;
          c.save();
          c.beginPath(); c.rect(G.vx, G.vy, G.vw, G.vh); c.clip();
          c.translate(n[0] + dx, n[1] + dy); c.rotate(rot);
          c.globalCompositeOperation = 'screen'; c.globalAlpha = 0.78 + 0.22 * lock;
          c.drawImage(pet.cv, -G.petS / 2, -G.petS / 2, G.petS, G.petS);
          c.restore();
          c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
          c.drawImage(ov.cv, 0, 0, w, hh);
          // crosshairs: fixed (CT) and moving (PET)
          var fx = snap(n[0]), fyy = snap(n[1]);
          c.lineWidth = 1; c.strokeStyle = cols.fix; c.beginPath();
          c.moveTo(fx - 22, fyy); c.lineTo(fx - 9, fyy); c.moveTo(fx + 9, fyy); c.lineTo(fx + 22, fyy);
          c.moveTo(fx, fyy - 22); c.lineTo(fx, fyy - 9); c.moveTo(fx, fyy + 9); c.lineTo(fx, fyy + 22); c.stroke();
          var mx = n[0] + dx, my = n[1] + dy;
          c.strokeStyle = cols.hi; c.beginPath(); c.arc(mx, my, 7, 0, TAU); c.stroke();
          if (lock > 0) {
            var b = Math.round(18 + 8 * (1 - lock)), l = 6;
            c.globalAlpha = lock; c.beginPath();
            [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(function (sg) {
              var x = snap(n[0] + sg[0] * b), y = snap(n[1] + sg[1] * b);
              c.moveTo(x, y - sg[1] * l); c.lineTo(x, y); c.lineTo(x - sg[0] * l, y);
            });
            c.stroke(); c.globalAlpha = 1;
          }
          label(c, lock > 0.5 ? 'REGISTERED' : 'ALIGNING', G.vx + G.vw - 26, G.vy + 30, lock > 0.5 ? cols.hi : cols.dim, 'right');
          // residual-error trace
          if (plot) {
            var Pp = G.plot, ox = G.sx, oy = G.vy;
            c.drawImage(plot.cv, ox, oy, G.sw, G.vh);
            c.strokeStyle = cols.trace; c.lineWidth = 1.25; c.beginPath();
            for (var i2 = 0; i2 <= upto; i2++) {
              var x2 = ox + Pp.pl + i2 / (NP - 1) * Pp.W2, y2 = oy + Pp.pt + (1 - clamp(err[i2], 0, 16) / 16) * Pp.H2;
              if (i2) c.lineTo(x2, y2); else c.moveTo(x2, y2);
            }
            c.stroke();
            c.fillStyle = cols.hi; c.beginPath(); c.arc(x2, y2, 2.5, 0, TAU); c.fill();
            var mm = Math.max(0, err[upto]);
            label(c, (lock > 0.5 ? 'Δ 0.0' : 'Δ ' + mm.toFixed(1)) + ' MM · θ ' + (lock > 0.5 ? '0.0' : (8.0 * inv).toFixed(1)) + '°', ox + 14, oy + 18, lock > 0.5 ? cols.hi : cols.dim, 'left');
          }
        }
      };
    }

    /* PET: a whole-body MIP builds up as counts accumulate: sparse early events give way to the
       full uptake map; hot spots bloom peach to white over the navy body. */
    function scenePET() {
      var G = null, ch = null, full = null, sparse = null, bar = null, ov = null, cols = {}, img = null;
      var CROP = [16, 0, 579, 900];
      return {
        img: 'scan-src/pet-mip.webp',
        resize: function (w, hh, dpr, P, c, d) {
          img = d.images[this.img];
          G = panelGeo(w, hh, CROP[2] / CROP[3], 0.34);
          ch = chrome(w, hh, dpr, P, G, ['PET · ' + (d.detail || 'FDG · SUV').toUpperCase(), 'MIP · CORONAL', 'SUV', '']);
          var d2 = Math.min(dpr, 1.5);
          // the source MIP is inverted (dark = uptake); grade on inverted luminance
          full = grade(img, CROP, G.vw, G.vh, d2, { invert: true, lo: 6, hi: 250, gamma: 0.62 });
          // early frame: a sparse random subset of events, weighted by uptake
          sparse = layer(G.vw, G.vh, d2);
          sparse.g.drawImage(full.cv, 0, 0, G.vw, G.vh);
          var id = sparse.g.getImageData(0, 0, sparse.cv.width, sparse.cv.height), p = id.data, R = rngf(31), bg = [8, 14, 25];
          for (var i = 0; i < p.length; i += 4) {
            var v = (p[i] + p[i + 1] + p[i + 2]) / 765;
            if (R() > v * v * 2.2 + 0.03) { p[i] = bg[0]; p[i + 1] = bg[1]; p[i + 2] = bg[2]; }
          }
          sparse.g.putImageData(id, 0, 0);
          if (G.sw) {
            // SUV colour bar on the same LUT as the image
            var bw = 14, bx = Math.round(G.sw / 2 - bw / 2) - 8, by = 26, bh = G.vh - 52;
            bar = layer(G.sw, G.vh, dpr); var g = bar.g;
            luts();
            for (var y = 0; y < bh; y++) {
              var l = Math.round((1 - y / bh) * 255) * 3;
              g.fillStyle = 'rgb(' + LUT_WARM[l] + ',' + LUT_WARM[l + 1] + ',' + LUT_WARM[l + 2] + ')';
              g.fillRect(bx, by + y, bw, 1);
            }
            hairRect(g, bx - 1, by - 1, bw + 2, bh + 2, col(K.cream, 0.25));
            for (var k = 0; k <= 4; k++) {
              var ty = snap(by + k / 4 * bh);
              g.fillStyle = col(K.cream, 0.45); g.fillRect(bx + bw + 3, Math.floor(ty), 5, 1);
              label(g, String(10 - k * 2.5).replace('.0', ''), bx + bw + 12, ty, col(K.cream, 0.6), 'left', FONT_SM);
            }
            G.bar = { x: bx, y: by, w: bw, h: bh };
          }
          ov = overlayChrome(w, hh, dpr, G, function (g) {
            label(g, 'R', G.vx + 26, G.vy + 30, col(K.cream, 0.6));
            label(g, 'L', G.vx + G.vw - 26, G.vy + 30, col(K.cream, 0.6), 'right');
          });
          cols.dim = col(K.cream, 0.6); cols.hi = col(K.pl, 1); cols.mark = col(K.pl, 1);
        },
        draw: function (c, w, hh, q) {
          if (!G) return;
          var f = seg(q, 0.04, 0.97), fe = eOut(f);
          c.drawImage(ch.cv, 0, 0, w, hh);
          var early = Math.min(1, f * 4) * (1 - smooth(seg(f, 0.25, 0.75)));
          if (early > 0.01) { c.globalAlpha = early; c.drawImage(sparse.cv, G.vx, G.vy, G.vw, G.vh); }
          if (fe > 0.01) { c.globalAlpha = smooth(seg(f, 0.15, 0.9)); c.drawImage(full.cv, G.vx, G.vy, G.vw, G.vh); }
          c.globalAlpha = 1;
          c.drawImage(ov.cv, 0, 0, w, hh);
          if (bar) {
            c.drawImage(bar.cv, G.sx, G.vy, G.sw, G.vh);
            // window level rises with accumulated counts
            var B = G.bar, my = Math.round(G.vy + B.y + B.h * (1 - smooth(f)));
            c.fillStyle = cols.mark; c.fillRect(G.sx + B.x - 7, my, 5, 1);
            c.beginPath(); c.moveTo(G.sx + B.x - 2, my + 0.5); c.lineTo(G.sx + B.x - 7, my - 3); c.lineTo(G.sx + B.x - 7, my + 4); c.closePath(); c.fill();
          }
          label(c, f >= 1 ? 'COMPLETE' : 'COUNTS ' + pad(Math.round(f * 100), 2) + '%', G.vx + G.vw / 2, G.vy + 30, f >= 1 ? cols.hi : cols.dim, 'center');
        }
      };
    }

    /* Ultrasound: the probe sweeps across the real B-mode frame; live speckle shimmers over it;
       a depth scale with a focus marker sits beside it. */
    function sceneUS() {
      var G = null, ch = null, frame = null, nz = [], ruler = null, ov = null, cols = {}, img = null, geo = null;
      var CROP = [0, 0, 1000, 802];
      return {
        img: 'scan-src/us-bmode.webp',
        anim: true,
        resize: function (w, hh, dpr, P, c, d) {
          img = d.images[this.img];
          G = panelGeo(w, hh, CROP[2] / CROP[3], 0.22);
          ch = chrome(w, hh, dpr, P, G, ['US · ' + (d.detail || 'B-mode').toUpperCase(), 'LINEAR', 'DEPTH', '']);
          var d2 = Math.min(dpr, 1.5);
          frame = grade(img, CROP, G.vw, G.vh, d2, { lo: 6, hi: 210, gamma: 0.74 });
          // fan geometry: the frame's edges converge on a virtual apex above it (source px)
          var sx = G.vw / CROP[2], sy = G.vh / CROP[3];
          geo = { ax: G.vx + 479 * sx, ay: G.vy - 1446 * sy, half: Math.atan2(0.28 * sx, sy) * 1.12 };
          // speckle shimmer: two pre-rendered grain fields, alternated
          var fd = frame.g.getImageData(0, 0, frame.cv.width, frame.cv.height).data;
          nz = [0, 1].map(function (s) {
            var L = layer(G.vw, G.vh, d2), g = L.g, id = g.createImageData(L.cv.width, L.cv.height), p = id.data, R = rngf(101 + s);
            for (var i = 0; i < p.length; i += 4) {
              var v = R(), lumv = (fd[i] + fd[i + 1] + fd[i + 2]) / 765; // grain only where tissue echoes
              if (v > 0.8 && lumv > 0.12) { p[i] = 255; p[i + 1] = 238; p[i + 2] = 228; p[i + 3] = (v - 0.8) * 260 * Math.min(1, lumv * 2.2); }
            }
            g.putImageData(id, 0, 0);
            return L;
          });
          if (G.sw) {
            ruler = layer(G.sw, G.vh, dpr); var g = ruler.g, x = 16, steps = 20;
            g.strokeStyle = col(K.cream, 0.5); g.lineWidth = 1; g.beginPath();
            g.moveTo(snap(x), 16); g.lineTo(snap(x), G.vh - 16);
            for (var k = 0; k <= steps; k++) { var yy = snap(lerp(16, G.vh - 16, k / steps)); g.moveTo(x, yy); g.lineTo(x + (k % 5 === 0 ? 9 : 4), yy); }
            g.stroke();
            for (k = 0; k <= 4; k++) label(g, String(k), x + 16, lerp(16, G.vh - 16, k / 4), col(K.cream, 0.65), 'left', FONT_SM);
            label(g, 'CM', x + 16, G.vh - 4, col(K.cream, 0.4), 'left', FONT_SM);
            G.rx = x;
          }
          ov = overlayChrome(w, hh, dpr, G);
          cols.sweep = col(K.pl, 0.95); cols.tint = col(K.pl, 0.1); cols.hi = col(K.pl, 1); cols.dim = col(K.cream, 0.6);
        },
        draw: function (c, w, hh, q, P, d, tick) {
          if (!G) return;
          var e = eIO(seg(q, 0.04, 0.9)), live = seg(q, 0.9, 0.97);
          c.drawImage(ch.cv, 0, 0, w, hh);
          var aL = Math.PI / 2 + geo.half, aR = Math.PI / 2 - geo.half, aCur = aL - 2 * geo.half * e;
          if (e > 0) {
            c.save();
            c.beginPath(); c.rect(G.vx, G.vy, G.vw, G.vh); c.clip();
            c.beginPath(); c.moveTo(geo.ax, geo.ay);
            c.arc(geo.ax, geo.ay, 99999, aCur, aL, false); c.closePath(); c.clip();
            c.drawImage(frame.cv, G.vx, G.vy, G.vw, G.vh);
            if (tick != null) { c.globalAlpha = 0.5; c.globalCompositeOperation = 'lighter'; c.drawImage(nz[tick & 1].cv, G.vx, G.vy, G.vw, G.vh); }
            c.restore();
            c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
            if (e < 1) {
              // sweep line, clipped to the viewport
              c.save(); c.beginPath(); c.rect(G.vx, G.vy, G.vw, G.vh); c.clip();
              c.fillStyle = cols.tint;
              c.beginPath(); c.moveTo(geo.ax, geo.ay); c.arc(geo.ax, geo.ay, 99999, aCur, aCur + 0.025, false); c.closePath(); c.fill();
              c.strokeStyle = cols.sweep; c.lineWidth = 1.25; c.beginPath();
              c.moveTo(geo.ax, geo.ay); c.lineTo(geo.ax + Math.cos(aCur) * 99999, geo.ay + Math.sin(aCur) * 99999); c.stroke();
              c.restore();
            }
          }
          c.drawImage(ov.cv, 0, 0, w, hh);
          if (ruler) {
            c.drawImage(ruler.cv, G.sx, G.vy, G.sw, G.vh);
            var fy = Math.round(G.vy + lerp(16, G.vh - 16, 0.45 * eOut(seg(q, 0.3, 0.8)) + 0.05));
            c.fillStyle = cols.hi; c.beginPath();
            c.moveTo(G.sx + G.rx - 3, fy); c.lineTo(G.sx + G.rx - 10, fy - 4); c.lineTo(G.sx + G.rx - 10, fy + 4); c.closePath(); c.fill();
          }
          label(c, e >= 1 ? (live > 0 ? 'LIVE' : 'FRAME') : 'SWEEP ' + pad(Math.round(e * 100), 2) + '%', G.vx + G.vw - 26, G.vy + 30, e >= 1 ? cols.hi : cols.dim, 'right');
        }
      };
    }

    /* Histopathology: zoom from low power into high power on a real H&E section inside the
       microscope field, with a scale bar and a magnification ladder (4x -> 40x). */
    function scenePATH() {
      var G = null, ch = null, levels = [], ring = null, ladder = null, cols = {}, img = null;
      var SRC = [3000, 2246], TGT = [1560, 1180], LV = [1, 2.6, 6.2, 10], Z0 = 1, Z1 = 10;
      var OBJ = [4, 10, 20, 40];
      function region(z, ar) { var rw = SRC[1] / z * ar, rh = SRC[1] / z; return [clamp(TGT[0] - rw / 2, 0, SRC[0] - rw), clamp(TGT[1] - rh / 2, 0, SRC[1] - rh), rw, rh]; }
      return {
        img: 'scan-src/path-hne.webp',
        resize: function (w, hh, dpr, P, c, d) {
          img = d.images[this.img];
          G = panelGeo(w, hh, 1, 0.36);
          ch = chrome(w, hh, dpr, P, G, ['H&E · BRIGHTFIELD', '', 'OBJECTIVE', '']);
          var d2 = Math.min(dpr, 1.5), lut = makeLut([[0, [24, 34, 60]], [0.36, [88, 80, 122]], [0.62, [206, 152, 146]], [0.82, K.peach], [1, [255, 251, 247]]]);
          // one graded tile per zoom level, each covering that level's field of view
          levels = LV.map(function (z) { var r = region(z, 1); return { z: z, r: r, L: grade(img, r, G.vw, G.vh, d2, { lut: lut, lo: 24, hi: 246, gamma: 0.9 }) }; });
          ring = layer(w, hh, dpr); var g = ring.g, cx = G.vx + G.vw / 2, cy = G.vy + G.vh / 2, R = G.vw / 2 - 10;
          // aperture: darken outside the round field, hairline ring with ticks
          g.fillStyle = col([8, 14, 25], 1); g.beginPath(); g.rect(G.vx, G.vy, G.vw, G.vh); g.arc(cx, cy, R, 0, TAU, true); g.fill();
          var vg = g.createRadialGradient(cx, cy, R * 0.7, cx, cy, R);
          vg.addColorStop(0, 'rgba(17,30,50,0)'); vg.addColorStop(1, 'rgba(17,30,50,.38)');
          g.fillStyle = vg; g.beginPath(); g.arc(cx, cy, R, 0, TAU); g.fill();
          g.strokeStyle = col(K.cream, 0.4); g.lineWidth = 1; g.beginPath(); g.arc(cx, cy, R + 0.5, 0, TAU); g.stroke();
          g.beginPath();
          for (var i = 0; i < 72; i++) {
            var a = i / 72 * TAU, l = i % 18 === 0 ? 7 : i % 6 === 0 ? 4 : 2;
            g.moveTo(cx + Math.cos(a) * (R + 3), cy + Math.sin(a) * (R + 3)); g.lineTo(cx + Math.cos(a) * (R + 3 + l), cy + Math.sin(a) * (R + 3 + l));
          }
          g.strokeStyle = col(K.cream, 0.3); g.stroke();
          G.cx = cx; G.cy = cy; G.R = R;
          if (G.sw) {
            ladder = layer(G.sw, G.vh, dpr); g = ladder.g;
            var top = 30, bot = G.vh - 30;
            g.strokeStyle = col(K.cream, 0.18); g.beginPath(); g.moveTo(snap(22), top); g.lineTo(snap(22), bot); g.stroke();
            OBJ.forEach(function (o, k) {
              var y = lerp(bot, top, k / (OBJ.length - 1));
              g.fillStyle = col(K.cream, 0.35); g.fillRect(18, Math.round(y), 9, 1);
              label(g, o + '×', 38, y, col(K.cream, 0.55), 'left');
            });
            G.lad = { top: top, bot: bot };
          }
          cols.hi = col(K.pl, 1); cols.dim = col(K.cream, 0.6); cols.bar = col(K.cream, 0.9); cols.ink = col(K.ink, 0.85);
        },
        draw: function (c, w, hh, q) {
          if (!G) return;
          var e = eIO(seg(q, 0.04, 0.95)), z = Z0 * Math.pow(Z1 / Z0, e), mag = 4 * z;
          c.drawImage(ch.cv, 0, 0, w, hh);
          // pick the tightest pre-rendered level that still covers the field, crop within it
          var li = 0;
          for (var i = 0; i < levels.length; i++) if (levels[i].z <= z) li = i;
          var Lv = levels[li], want = region(z, 1), s = Lv.L.cv.width / Lv.r[2];
          c.drawImage(Lv.L.cv, (want[0] - Lv.r[0]) * s, (want[1] - Lv.r[1]) * s, want[2] * s, want[3] * s, G.vx, G.vy, G.vw, G.vh);
          c.drawImage(ring.cv, 0, 0, w, hh);
          // scale bar: a fixed 200 µm at 4×, shrinking in µm as magnification rises
          var um = 200 / z, nice = um >= 100 ? 100 : um >= 50 ? 50 : um >= 20 ? 20 : 10, len = Math.round(nice / um * G.R * 0.22);
          // sits in the dark corner outside the round field, so it never fights the tissue
          var bx = Math.round(G.vx + G.vw - 22 - len), by = Math.round(G.vy + G.vh - 22);
          c.fillStyle = cols.bar; c.fillRect(bx, by, len, 1); c.fillRect(bx, by - 3, 1, 7); c.fillRect(bx + len - 1, by - 3, 1, 7);
          label(c, nice + ' µm', bx + len, by - 11, cols.dim, 'right');
          label(c, Math.round(mag) + '×', G.vx + G.vw - 26, G.vy + 30, e >= 1 ? cols.hi : cols.dim, 'right');
          if (ladder) {
            c.drawImage(ladder.cv, G.sx, G.vy, G.sw, G.vh);
            // marker position on a log scale between 4x and 40x
            var t = Math.log(mag / 4) / Math.log(10), y = Math.round(G.vy + lerp(G.lad.bot, G.lad.top, t));
            c.fillStyle = cols.hi; c.fillRect(G.sx + 14, y, 17, 1);
            c.beginPath(); c.arc(G.sx + 22.5, y + 0.5, 3, 0, TAU); c.fill();
            var cur = OBJ[0];
            for (var k = 0; k < OBJ.length; k++) if (mag >= OBJ[k] * 0.98) cur = OBJ[k];
            label(c, cur + '×', G.sx + 38, G.vy + lerp(G.lad.bot, G.lad.top, OBJ.indexOf(cur) / (OBJ.length - 1)), cols.hi, 'left');
          }
        }
      };
    }

    var SCENES = { mri: sceneMRI, pet: scenePET, path: scenePATH, xray: sceneXRAY, us: sceneUS, fusion: sceneFUSION };

    /* ========================================================== dividers */
    var dividers = [];
    var pending = true, vh = innerHeight, sy = window.pageYOffset || 0;
    function touch() { pending = true; if (fx.kick) fx.kick(); }

    function bgOf(el) {
      if (!el) return null;
      var c = parseCss(getComputedStyle(el).backgroundColor);
      return c && c[3] > 0.5 ? c : null;
    }
    function modalityByKey(key) {
      var all = fx.modalities || {}, ids = Object.keys(all);
      for (var i = 0; i < ids.length; i++) if (all[ids[i]].key === key) return all[ids[i]];
      return null;
    }
    function live(d) { return !d.page || d.page.classList.contains('active'); }

    // Draw on the page's own ground (cream, or navy on the business pages), or continue a
    // navy band that directly precedes the divider.
    function applyTone(d) {
      var el = d.el, forced = el.getAttribute('data-tone');
      var pb = bgOf(el.previousElementSibling), nb = bgOf(el.nextElementSibling);
      var body = bgOf(document.body) || K.cream;
      var bodyDark = lum(body) < 0.4, prevDark = !!(pb && lum(pb) < 0.4);
      var dark = forced ? forced === 'navy' : (pb ? prevDark : bodyDark);
      var band = dark ? (prevDark ? pb : (bodyDark ? null : K.navy)) : null;
      if (band) el.style.setProperty('--scan-band', col(band, 1)); else el.style.removeProperty('--scan-band');
      var from = pb && lum(pb) > 0.6 && !dark ? pb : null, to = nb && lum(nb) > 0.6 && !dark ? nb : null;
      if (from) el.style.setProperty('--scan-from', col(from, 1)); else el.style.removeProperty('--scan-from');
      if (to) el.style.setProperty('--scan-to', col(to, 1)); else el.style.removeProperty('--scan-to');
      var ground = band || body;
      var key = (dark ? 'navy' : 'cream') + ground.join(',');
      el.classList.toggle('is-navy', dark);
      el.classList.toggle('fx-bloom', !!band);
      if (d.tone !== key) { d.tone = key; d.P = makeTone(dark, dark && lum(ground) >= 0.4 ? K.navy : ground); d.stale = true; }
    }

    function applyLabel(d) {
      var pm = fx.modality(d.page ? d.page.getAttribute('data-page') : fx.page());
      var m = pm.key === d.key ? pm : (modalityByKey(d.key) || pm);
      d.detail = m.detail;
      while (d.id.firstChild) d.id.removeChild(d.id.firstChild);
      d.id.appendChild(h('b', null, ['SEQ ' + pad(pm.seq, 2)]));
      d.id.appendChild(document.createTextNode(' · ' + m.name + ' · ' + m.detail));
    }

    // Layout reads happen here only (resize, page change, layout change, visibility) — never per frame.
    function measure(d) {
      if (!live(d)) return;
      var r = d.el.getBoundingClientRect();
      d.top = r.top + (window.pageYOffset || 0);
      d.height = r.height;
      var w = Math.round(r.width), hh = Math.round(r.height);
      if (w < 2 || hh < 2) return;
      var dpr = Math.min(window.devicePixelRatio || 1, w > 900 ? 1.5 : 2);
      if (d.scene.img && !d.images[d.scene.img]) { d.ready = false; return; } // waits for its image
      if (w !== d.w || hh !== d.h || dpr !== d.dpr || d.stale) {
        d.w = w; d.h = hh; d.dpr = dpr; d.stale = false;
        d.canvas.width = Math.round(w * dpr); d.canvas.height = Math.round(hh * dpr);
        d.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        try { if (d.scene.resize) d.scene.resize(w, hh, dpr, d.P, d.ctx, d); d.ready = true; }
        catch (e) { d.ready = false; console.error('[fx] scan resize failed:', e); }
        d.q = -1;
      }
    }

    /* Images are decoded once and shared between dividers. */
    var imgCache = {};
    function loadImage(src, cb) {
      var o = imgCache[src];
      if (!o) {
        o = imgCache[src] = { el: new Image(), ok: false, cbs: [] };
        o.el.decoding = 'async';
        o.el.onload = function () {
          var go = function () { o.ok = true; o.cbs.forEach(function (f) { f(o.el); }); o.cbs = []; };
          if (o.el.decode) o.el.decode().then(go, go); else go();
        };
        o.el.onerror = function () { console.error('[fx] scan image failed to load:', src); };
        o.el.src = src;
      }
      if (o.ok) cb(o.el); else o.cbs.push(cb);
    }

    // Fetch a divider's image only once its page is shown (the H&E source is large).
    function ensureImage(d) {
      if (!d.scene.img || d.loading) return;
      d.loading = true;
      loadImage(d.scene.img, function (im) { d.images[d.scene.img] = im; d.stale = true; if (d.vis && live(d)) { measure(d); touch(); } });
    }

    function build(el) {
      if (el.__fxScan) return;
      var key = el.getAttribute('data-scan');
      var make = SCENES[key];
      if (!make) return;
      el.__fxScan = true;
      while (el.firstChild) el.removeChild(el.firstChild);
      el.classList.add('fx-scan--built');
      if (fx.reduced) el.classList.add('is-static');
      var stage = h('div', 'fx-scan__stage'), canvas = h('canvas', 'fx-canvas fx-scan__canvas');
      canvas.setAttribute('aria-hidden', 'true');
      stage.appendChild(canvas);
      el.appendChild(stage);
      var id = h('span', 'fx-scan__id'), fill = h('i');
      var st = h('span', 'fx-scan__st', [fx.reduced ? 'Acquired · 100%' : 'Acquiring 00%']);
      el.appendChild(h('div', 'fx-scan__hud wrap', [id, h('span', 'fx-scan__rule', [fill]), h('span', 'fx-scan__meta', [META[key] || '']), st]));
      var d = { el: el, key: key, page: el.closest('.page'), canvas: canvas, ctx: canvas.getContext('2d'), scene: make(),
        id: id, fill: fill, st: st, vis: false, q: -1, pct: -1, w: 0, h: 0, dpr: 1, top: 0, height: 0, tone: null, stale: true, images: {} };
      applyLabel(d);
      applyTone(d);
      fx.watch(el, function (v) { d.near = v; hudDock(); }, { rootMargin: '0px 0px -40px 0px' });
      fx.watch(el, function (v) {
        d.vis = v;
        if (v) { ensureImage(d); applyTone(d); measure(d); el.classList.add('is-in'); touch(); }
      }, { rootMargin: '120px 0px' });
      dividers.push(d);
    }

    function render(d) {
      if (!d.ready) return;
      // natural progress from cached geometry; complete as the band reaches the upper viewport
      var p = clamp((vh - (d.top - sy)) / (vh + d.height), 0, 1);
      var q = fx.reduced ? 1 : seg(p, 0.08, 0.58);
      var tick = d.scene.anim && !fx.reduced ? Math.floor(performance.now() / 140) : null;
      if (Math.abs(q - d.q) < 0.0005 && tick === d.tick) return;
      d.q = q; d.tick = tick;
      var c = d.ctx;
      c.setTransform(d.dpr, 0, 0, d.dpr, 0, 0);
      c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
      c.clearRect(0, 0, d.w, d.h);
      try { d.scene.draw(c, d.w, d.h, q, d.P, d, tick); }
      catch (e) { if (!d.err) { d.err = true; console.error('[fx] scan scene failed:', e); } }
      c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
      var pct = Math.round(q * 100);
      if (pct !== d.pct) {
        d.pct = pct;
        d.st.textContent = pct >= 100 ? 'Acquired · 100%' : 'Acquiring ' + pad(pct, 2) + '%';
        d.fill.style.transform = 'scaleX(' + (pct / 100) + ')';
      }
    }

    function scanSlots() {
      var els = document.querySelectorAll('.fx-scan[data-scan]');
      for (var i = 0; i < els.length; i++) build(els[i]);
    }
    function measureAll() {
      vh = innerHeight; sy = window.pageYOffset || 0;
      dividers.forEach(function (d) { if (live(d)) { ensureImage(d); applyTone(d); measure(d); } });
      hudMeasure();
      touch();
    }

    var profile = null; // opt-in: window.__fxScanProfile = [] collects per-frame work in ms
    fx.loop(function () {
      pending = false;
      profile = window.__fxScanProfile || null;
      var t0 = profile ? performance.now() : 0;
      for (var i = 0; i < dividers.length; i++) {
        var d = dividers[i];
        if (d.vis && live(d)) render(d);
      }
      if (profile) profile.push(performance.now() - t0);
    }, function () {
      for (var j = 0; j < dividers.length; j++) if (dividers[j].vis && dividers[j].ready && dividers[j].scene.anim && !fx.reduced && live(dividers[j])) return true;
      if (!pending) return false;
      for (var i = 0; i < dividers.length; i++) if (dividers[i].vis) return true;
      pending = false;
      return false;
    });

    // Dev aid: OHX.scanBench(60) draws every divider on the current page at 60 progress steps
    // synchronously and reports main-thread draw cost per frame (ms). Not used by the page itself.
    // Credits for every image the dividers use (wired into the site's sources dialog elsewhere).
    fx.scanCredits = Object.keys(CREDIT).map(function (f) {
      var c0 = CREDIT[f];
      return { file: f, title: c0.title, credit: c0.credit, license: c0.license, url: c0.url, note: c0.note };
    });

    fx.scanBench = function (steps) {
      steps = steps || 60;
      return dividers.filter(live).map(function (d) {
        measure(d);
        if (!d.ready) return { scan: d.key, pending: true };
        var t = [], c = d.ctx;
        for (var i = 0; i <= steps; i++) {
          var t0 = performance.now();
          c.setTransform(d.dpr, 0, 0, d.dpr, 0, 0); c.clearRect(0, 0, d.w, d.h);
          d.scene.draw(c, d.w, d.h, i / steps, d.P, d);
          c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
          t.push(performance.now() - t0);
        }
        d.q = -1; touch();
        t.sort(function (a, b) { return a - b; });
        return { scan: d.key, size: d.w + 'x' + d.h + '@' + d.dpr, p50: +t[Math.floor(t.length / 2)].toFixed(2), p95: +t[Math.floor(t.length * 0.95)].toFixed(2), max: +t[t.length - 1].toFixed(2) };
      });
    };

    addEventListener('scroll', function () { sy = window.pageYOffset || 0; touch(); }, { passive: true });
    var rzT = 0;
    addEventListener('resize', function () { clearTimeout(rzT); rzT = setTimeout(measureAll, 120); });
    // content above a divider can change height (tabs, images, other modules): re-measure
    if ('ResizeObserver' in window) {
      var roRaf = 0;
      new ResizeObserver(function () {
        if (roRaf) return;
        roRaf = requestAnimationFrame(function () { roRaf = 0; setTimeout(measureAll, 0); });
      }).observe(document.body);
    }

    /* =============================================================== scramble */
    // Brief glyph scramble of the HUD label on page change; resolves left to right.
    function scrambleText(el, text, dur) {
      if (el.__scr) cancelAnimationFrame(el.__scr);
      el.textContent = text;
      if (fx.reduced) return;
      var node = el.firstChild, n = text.length, t0 = performance.now(), last = text;
      (function step(now) {
        if (el.firstChild !== node || node.nodeValue !== last) { el.__scr = 0; return; }
        var p = Math.min(1, (now - t0) / dur), tick = Math.floor((now - t0) / 50), out = '';
        for (var i = 0; i < n; i++) {
          var ch = text.charAt(i);
          if (/[\s·\/.,:&×-]/.test(ch)) { out += ch; continue; }
          out += p >= 0.2 + 0.75 * (i / Math.max(1, n - 1)) ? ch : glyph(i, tick);
        }
        if (p >= 1) out = text;
        node.nodeValue = out; last = out;
        el.__scr = p < 1 ? requestAnimationFrame(step) : 0;
      })(t0);
    }

    /* =============================================================== HUD */
    var hud = h('div', 'fx-hud');
    hud.setAttribute('aria-hidden', 'true');
    var hSeq = h('span', 'fx-hud__seq', ['SEQ 01']);
    var hLabel = h('span', 'fx-hud__label');
    var hFill = h('i');
    var hPct = h('span', 'fx-hud__pct', ['00%']);
    [h('span', 'fx-hud__dot'), hSeq, h('span', 'fx-hud__sep', ['·']), hLabel, h('span', 'fx-hud__bar', [hFill]), hPct]
      .forEach(function (n) { hud.appendChild(n); });
    // Docked inside the sticky header so it can never sit on top of page content.
    (document.querySelector('.site-header') || document.body).appendChild(hud);
    var hudPage = null, hudPct = -1, hudTick = false, hudMax = 1;

    function hudMeasure() { hudMax = Math.max(1, document.documentElement.scrollHeight - innerHeight); hudSchedule(); }
    function hudSetPage(id) {
      var m = fx.modality(id);
      hSeq.textContent = 'SEQ ' + pad(m.seq, 2);
      hud.setAttribute('data-key', m.key);
      var txt = m.name + ' · ' + m.detail;
      if (hudPage === null) hLabel.textContent = txt; else scrambleText(hLabel, txt, 460);
      hudPage = id;
      hudPct = -1;
    }
    function hudUpdate() {
      hudTick = false;
      var prog = clamp(sy / hudMax, 0, 1), pct = Math.round(prog * 100);
      if (pct === hudPct) return;
      hudPct = pct;
      hFill.style.transform = 'scaleX(' + (pct / 100) + ')';
      hPct.textContent = pad(pct, 2) + '%';
    }
    function hudSchedule() { if (!hudTick) { hudTick = true; requestAnimationFrame(hudUpdate); } }
    addEventListener('scroll', hudSchedule, { passive: true });
    setTimeout(function () { hud.classList.add('is-on'); }, fx.reduced ? 0 : 900);

    var footer = document.querySelector('body > footer') || document.querySelector('footer');
    // The HUD steps aside over the footer and while a scan band (with its own readout) is on screen.
    var footerVis = false;
    function hudDock() {
      var band = false;
      for (var i = 0; i < dividers.length; i++) if (dividers[i].near && live(dividers[i])) { band = true; break; }
      hud.classList.toggle('is-docked', footerVis || band);
    }
    if (footer) fx.watch(footer, function (v) { footerVis = v; hudDock(); }, { rootMargin: '0px 0px -24px 0px' });

    /* ============================================================ lifecycle */
    scanSlots();
    fx.onPage(function (id) {
      scanSlots();
      dividers.forEach(function (d) { if (live(d)) applyLabel(d); });
      hudSetPage(id);
      hudDock();
      setTimeout(measureAll, 30);
      // the page ground may transition between cream and navy; settle the tone afterwards
      setTimeout(measureAll, 700);
    });

    // Slots that other modules add later.
    var moT = 0, main = document.querySelector('main');
    if (main && 'MutationObserver' in window) {
      new MutationObserver(function (list) {
        for (var i = 0; i < list.length; i++) {
          var added = list[i].addedNodes;
          for (var j = 0; j < added.length; j++) {
            var n = added[j];
            if (n.nodeType === 1 && (n.matches('.fx-scan') || n.querySelector('.fx-scan'))) {
              clearTimeout(moT); moT = setTimeout(function () { scanSlots(); measureAll(); }, 120); return;
            }
          }
        }
      }).observe(main, { childList: true, subtree: true });
    }
    addEventListener('load', measureAll);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { dividers.forEach(function (d) { d.stale = true; }); measureAll(); });
  }

  // core.js starts modules on a 0ms timer once the document is interactive; when this deferred
  // script arrives after that (slow or uncached load) registering would be too late, so run
  // directly in that case.
  if (document.documentElement.classList.contains('fx')) {
    try { init(OHX); } catch (e) { console.error('[fx] scan failed:', e); }
  } else {
    OHX.register('scan', init);
  }
})();
