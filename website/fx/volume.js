/* OncoloHealth fx: CT volume band (home), count-ups (shared), research-area k-space track
   (research) and a subtle magnetic primary button on the home hero.
   Native scrolling only: the volume is scrubbed by the band's natural travel through the
   viewport, and the research track moves by drag, buttons or keys, never by the wheel. */
(function () {
  'use strict';
  if (!window.OHX) return;
  var OHX = window.OHX;
  var TAU = Math.PI * 2;
  var DPR_CAP = 1.5;

  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function smooth(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
  function inOut(t) { t = clamp(t, 0, 1); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function mulberry(a) {
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hexRGB(hex) {
    var h = String(hex || '#ffffff').replace('#', '').trim();
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [n >> 16 & 255, n >> 8 & 255, n & 255];
  }
  function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + clamp(a, 0, 1).toFixed(3) + ')'; }
  function setText(el, v) { if (el && el.textContent !== v) el.textContent = v; }
  function arr(list) { return Array.prototype.slice.call(list || []); }
  function now() { return performance.now(); }

  /* Canvas sized to its CSS box, device pixel ratio capped at 1.5. Returns true when resized. */
  function surface(host, cls) {
    var c = document.createElement('canvas');
    c.className = cls || 'fx-canvas';
    c.setAttribute('aria-hidden', 'true');
    host.appendChild(c);
    var o = { canvas: c, ctx: c.getContext('2d'), w: 0, h: 0, dpr: 1 };
    o.resize = function () {
      var r = c.getBoundingClientRect();
      var w = Math.max(1, Math.round(r.width)), h = Math.max(1, Math.round(r.height));
      var d = Math.min(window.devicePixelRatio || 1, DPR_CAP);
      if (w === o.w && h === o.h && d === o.dpr) return false;
      o.w = w; o.h = h; o.dpr = d;
      c.width = Math.round(w * d); c.height = Math.round(h * d);
      o.ctx.setTransform(d, 0, 0, d, 0, 0);
      return true;
    };
    o.resize();
    return o;
  }
  function sprite(size, paint) {
    var c = document.createElement('canvas');
    c.width = c.height = size;
    paint(c.getContext('2d'), size);
    return c;
  }

  /* ====================================================================
     Count-ups. OHX.countUp(el) animates el's text (or its data-count value)
     from zero and always ends on the exact original string ("3,746", "80.8%").
     Any [data-count] element counts up automatically on first view.
     ==================================================================== */
  var FIG = /^(\D*?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?([\s\S]*)$/;
  function parseFigure(text) {
    var m = FIG.exec(text);
    if (!m) return null;
    return {
      text: text, pre: m[1], post: m[4],
      comma: m[2].indexOf(',') > -1,
      dec: m[3] ? m[3].length - 1 : 0,
      value: parseFloat(m[2].replace(/,/g, '') + (m[3] || ''))
    };
  }
  function formatFigure(f, v) {
    var s = v.toFixed(f.dec);
    if (f.comma) {
      var parts = s.split('.');
      parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      s = parts.join('.');
    }
    return f.pre + s + f.post;
  }
  function figureOf(el) {
    if (!el.__ohxFigure) {
      var attr = el.getAttribute('data-count');
      el.__ohxFigure = parseFigure((attr && /\d/.test(attr) ? attr : el.textContent).trim());
    }
    return el.__ohxFigure;
  }

  // One shared ticker drives every running count-up.
  var counting = [];
  function countFrame(t) {
    for (var i = counting.length - 1; i >= 0; i--) {
      var c = counting[i];
      if (!c.t0) c.t0 = t;
      var k = clamp((t - c.t0) / c.dur, 0, 1);
      if (k >= 1) {
        c.el.textContent = c.f.text;
        c.el.__ohxCount = 'done';
        c.el.classList.remove('fx-counting');
        counting.splice(i, 1);
      } else {
        var v = c.f.value * (1 - Math.pow(1 - k, 4));   // quartic ease-out: fast start, long settle
        setText(c.el, formatFigure(c.f, c.f.dec ? v : Math.floor(v)));
      }
    }
    if (counting.length) requestAnimationFrame(countFrame);
  }

  OHX.countUp = function (el, opts) {
    if (!el) return;
    var f = figureOf(el);
    if (!f) return;
    if (OHX.reduced || !(f.value > 0)) { el.textContent = f.text; el.__ohxCount = 'done'; return; }
    if (el.__ohxCount === 'running') return;
    el.__ohxCount = 'running';
    el.classList.add('fx-counting');
    el.textContent = formatFigure(f, 0);
    var dur = (opts && opts.duration) || clamp(850 + Math.log(f.value + 1) * 110, 850, 1700);
    counting.push({ el: el, f: f, dur: dur, t0: 0 });
    if (counting.length === 1) requestAnimationFrame(countFrame);
  };

  /* Prime (show the zero frame) and observe every [data-count] or selector match under root. */
  OHX.countUpAll = function (root, selector) {
    arr((root || document).querySelectorAll(selector || '[data-count]')).forEach(function (el) {
      if (el.__ohxWatched) return;
      el.__ohxWatched = true;
      var f = figureOf(el);
      if (!f || OHX.reduced) return;
      el.textContent = formatFigure(f, 0);
      OHX.once(el, function () { OHX.countUp(el); }, 0.35);
    });
  };

  function safe(name, fn) {
    try { fn(); } catch (e) { console.error('[fx] volume/' + name + ' failed:', e); }
  }

  OHX.register('volume', function (fx) {
    safe('countups', function () { setupCounts(fx); });
    safe('volume', function () { setupVolume(fx); });
    safe('branches', function () { setupBranches(fx); });
    safe('magnet', function () { setupMagnet(fx); });
  });

  function setupCounts(fx) {
    // Existing research and home figures, without editing their markup.
    arr(document.querySelectorAll('.stat-grid strong, .audit-population strong')).forEach(function (el) {
      if (!el.hasAttribute('data-count')) el.setAttribute('data-count', '');
    });
    fx.countUpAll(document);
    // Other modules may render [data-count] figures later; pick them up as they appear.
    var pending = false;
    new MutationObserver(function () {
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; fx.countUpAll(document); });
    }).observe(document.body, { childList: true, subtree: true });
    fx.onPage(function () { fx.countUpAll(document); });
    function finishAll() {
      counting.length = 0;
      arr(document.querySelectorAll('[data-count]')).forEach(function (el) {
        var f = el.__ohxFigure;
        if (f && el.__ohxCount !== 'done') { el.textContent = f.text; el.__ohxCount = 'done'; el.classList.remove('fx-counting'); }
      });
    }
    addEventListener('beforeprint', finishAll);
    matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', function (e) { if (e.matches) finishAll(); });
  }

  /* ====================================================================
     CT volume. A thorax built from analytic structures (body wall, lungs,
     heart, airway, spine, ribs, sternum and one nodule). The point cloud is
     cut by an axial scan plane; the cut face is drawn as a windowed CT slice
     (air dark, soft tissue mid, bone bright) between the points below the
     plane and the dimmed points above it.
     ==================================================================== */
  var MM_PER_UNIT = 122;   // body half-width 1.0 = 122 mm; 256 images 1.0 mm apart
  var Y0 = -1.05, Y1 = 1.05;

  function bodyR(y) { var t = smooth((y - 0.35) / 0.7); return [1.0 - 0.1 * t, 0.66 - 0.05 * t]; }
  function bodyXZ(y, th, scale, out) {
    var r = bodyR(y), s = Math.sin(th);
    out[0] = r[0] * Math.cos(th) * scale;
    out[1] = r[1] * s * (s > 0 ? 0.9 : 1) * scale;   // +z posterior: flatter back
  }
  var LUNG = { yb: -0.82, yt: 0.98, cx: 0.45, cz: 0.03, rx: 0.34, rz: 0.43 };
  function lungF(y) {
    if (y <= LUNG.yb || y >= LUNG.yt) return 0;
    var u = (y - LUNG.yb) / (LUNG.yt - LUNG.yb);
    return Math.pow(Math.sin(Math.PI * Math.pow(u, 0.8)), 0.55);
  }
  function lungXZ(side, f, th, out) {
    var c = Math.cos(th), s = Math.sin(th), med = Math.max(0, -side * c), k = 1 - 0.26 * med * med;
    out[0] = side * LUNG.cx + LUNG.rx * f * c * k;
    out[1] = LUNG.cz + LUNG.rz * f * s;
  }
  var HEART = { c: [-0.1, -0.42, -0.2], r: [0.34, 0.36, 0.3] };
  var SPINE = { z: 0.44, r: 0.11, canalZ: 0.585, canalR: 0.045 };
  var TRACHEA = { y0: 0.5, z: 0.16, r: 0.075 };
  var STERNUM = { y0: -0.45, y1: 0.75, w: 0.09, d: 0.035 };
  var NODULE = { c: [0.55, 0.3, -0.06], r: 0.1 };
  var RIBS = [];
  for (var rk = 0; rk < 10; rk++) RIBS.push(0.86 - rk * 0.17);
  var RIB_A0 = 0.3, RIB_A1 = 2.35, RIB_DROP = 0.2;
  function ribXYZ(side, y0, a, out) {
    var y = y0 - RIB_DROP * (a - RIB_A0) / (RIB_A1 - RIB_A0), r = bodyR(y);
    out[0] = side * r[0] * 0.9 * Math.sin(a);
    out[1] = y;
    out[2] = r[1] * 0.9 * Math.cos(a);
  }
  function isDisc(y) { return ((y + 4) / 0.17) % 1 > 0.8; }

  function setupVolume(fx) {
    var band = document.querySelector('[data-fx="volume"]');
    if (!band) return;
    var host = band.querySelector('[data-vol-canvas]');
    if (!host) return;
    var sf = surface(host, 'fx-canvas fx-vol-canvas');
    var g = sf.ctx;
    var sliceEl = band.querySelector('[data-vol-slice]');
    var zEl = band.querySelector('[data-vol-z]');
    var rotEl = band.querySelector('[data-vol-rot]');
    var mod = fx.modality('home');
    setText(band.querySelector('[data-vol-mod]'), (mod.seq < 10 ? '0' : '') + mod.seq + ' · ' + mod.name.toUpperCase());
    setText(band.querySelector('[data-vol-detail]'), mod.detail.toUpperCase());
    var mono = (getComputedStyle(document.documentElement).getPropertyValue('--fx-mono') || '').trim() || 'monospace';

    /* ---- points: generated once, shuffled so any prefix is a fair sample ---- */
    var NMAX = (window.innerWidth <= 760 || !fx.fine) ? 4200 : 7600;
    var rand = mulberry(0x0c7a11);
    var BODY = 0, LUNGK = 1, SOFT = 2, BONE = 3, NOD_K = 4;
    var PX = new Float32Array(NMAX), PY = new Float32Array(NMAX), PZ = new Float32Array(NMAX), PK = new Uint8Array(NMAX);
    var count = 0, tmp = [0, 0, 0];
    function put(x, y, z, k) { if (count < NMAX) { PX[count] = x; PY[count] = y; PZ[count] = z; PK[count] = k; count++; } }
    function jit(a) { return (rand() - 0.5) * a; }
    function sphereDir(out) { var y = rand() * 2 - 1, a = rand() * TAU, r = Math.sqrt(1 - y * y); out[0] = r * Math.cos(a); out[1] = y; out[2] = r * Math.sin(a); }
    var i, n, y, th, side, f;
    n = Math.round(NMAX * 0.3);                                     // body wall
    for (i = 0; i < n; i++) { y = Y0 + rand() * (Y1 - Y0); bodyXZ(y, rand() * TAU, 1, tmp); put(tmp[0] + jit(0.012), y, tmp[1] + jit(0.012), BODY); }
    n = Math.round(NMAX * 0.25);                                    // lungs, denser where wider
    for (i = 0; i < n;) {
      y = LUNG.yb + rand() * (LUNG.yt - LUNG.yb); f = lungF(y);
      if (rand() > f) continue;
      side = rand() < 0.5 ? -1 : 1; lungXZ(side, f, rand() * TAU, tmp);
      put(tmp[0] + jit(0.01), y, tmp[1] + jit(0.01), LUNGK); i++;
    }
    n = Math.round(NMAX * 0.08);                                    // heart
    for (i = 0; i < n; i++) { sphereDir(tmp); put(HEART.c[0] + tmp[0] * HEART.r[0], HEART.c[1] + tmp[1] * HEART.r[1], HEART.c[2] + tmp[2] * HEART.r[2], SOFT); }
    n = Math.round(NMAX * 0.025);                                   // trachea
    for (i = 0; i < n; i++) { y = TRACHEA.y0 + rand() * (Y1 - TRACHEA.y0); th = rand() * TAU; put(Math.cos(th) * TRACHEA.r, y, TRACHEA.z + Math.sin(th) * TRACHEA.r, LUNGK); }
    n = Math.round(NMAX * 0.08);                                    // vertebral bodies and canal, with disc gaps
    for (i = 0; i < n;) {
      y = Y0 + rand() * (Y1 - Y0);
      if (isDisc(y)) continue;
      th = rand() * TAU;
      var body = rand() < 0.78, cr = body ? SPINE.r : SPINE.canalR, cz = body ? SPINE.z : SPINE.canalZ;
      put(Math.cos(th) * cr, y, cz + Math.sin(th) * cr, BONE); i++;
    }
    n = Math.round(NMAX * 0.21);                                    // ribs
    for (i = 0; i < n; i++) {
      side = rand() < 0.5 ? -1 : 1;
      ribXYZ(side, RIBS[(rand() * RIBS.length) | 0], RIB_A0 + rand() * (RIB_A1 - RIB_A0), tmp);
      put(tmp[0] + jit(0.014), tmp[1] + jit(0.016), tmp[2] + jit(0.014), BONE);
    }
    n = Math.round(NMAX * 0.02);                                    // sternum
    for (i = 0; i < n; i++) { y = STERNUM.y0 + rand() * (STERNUM.y1 - STERNUM.y0); put(jit(STERNUM.w * 2), y, -bodyR(y)[1] * 0.9 + jit(STERNUM.d), BONE); }
    while (count < NMAX) {                                          // nodule: shell and core
      sphereDir(tmp);
      var rr = NODULE.r * (rand() < 0.6 ? 1 + jit(0.12) : Math.cbrt(rand()));
      put(NODULE.c[0] + tmp[0] * rr, NODULE.c[1] + tmp[1] * rr, NODULE.c[2] + tmp[2] * rr, NOD_K);
    }
    for (i = NMAX - 1; i > 0; i--) {                                // Fisher-Yates shuffle
      var j = (rand() * (i + 1)) | 0, t;
      t = PX[i]; PX[i] = PX[j]; PX[j] = t; t = PY[i]; PY[i] = PY[j]; PY[j] = t;
      t = PZ[i]; PZ[i] = PZ[j]; PZ[j] = t; t = PK[i]; PK[i] = PK[j]; PK[j] = t;
    }

    /* ---- palette and buckets: one fill per (class, alpha level, side of plane) ---- */
    var pal = fx.palette;
    var PEACH = hexRGB(pal.peachLight), PEACH_SOFT = hexRGB(pal.peach), CREAM = hexRGB(pal.cream), DEEP = hexRGB(pal.deep);
    var NOD = hexRGB('#e8ad94');   // warm peach between peach-light and peach-deep
    var CLS_FILL = ['#ffffff', pal.peachLight, pal.peach, '#e8ad94', '#ffffff'];
    var CLS_OF = [0, 1, 2, 0, 3];  // kind -> colour class; class 4 is the scan-band highlight
    var KB = [0.34, 0.5, 0.36, 0.85, 0.6];
    var LV = 8, NCL = CLS_FILL.length, NHALF = NCL * LV, NB = NHALF * 2;
    var bufs = [], cnts = new Int32Array(NB);
    for (var b = 0; b < NB; b++) bufs.push(new Float32Array(NMAX * 3));

    var nodGlow = sprite(64, function (c, s) {
      var gr = c.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
      gr.addColorStop(0, rgba(NOD, 0.55)); gr.addColorStop(0.5, rgba(NOD, 0.16)); gr.addColorStop(1, rgba(NOD, 0));
      c.fillStyle = gr; c.fillRect(0, 0, s, s);
    });
    var bloom = sprite(256, function (c, s) {
      var gr = c.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
      gr.addColorStop(0, 'rgba(255,255,255,0.12)'); gr.addColorStop(0.45, 'rgba(255,255,255,0.04)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      c.fillStyle = gr; c.fillRect(0, 0, s, s);
    });

    /* ---- layout and adaptive point budget ---- */
    var W = 0, H = 0, cx = 0, cy = 0, baseScale = 1, planeK = 1, nTarget = 3000, nActive = 0;
    function layout() {
      W = sf.w; H = sf.h;
      cx = W * 0.5; cy = H * 0.52;
      baseScale = Math.min(H * 0.33, W * (W < 520 ? 0.27 : 0.36));
      planeK = W < 520 ? 0.85 : 1;   // keeps the plane's corners clear of the ruler on phones
      nTarget = clamp(Math.round(W * H / 40), 2400, NMAX);
      nActive = nActive ? Math.min(nActive, nTarget) : nTarget;
    }

    /* ---- motion state ---- */
    var yaw = 0.55, offYaw = 0, offPitch = 0, vYaw = 0, vPitch = 0, tYaw = 0, tPitch = 0;
    var intro = 0, introStarted = false, tIdle = 0, planeY = Y1, p = 0.5, heat = 0;
    function staticState() { intro = 1; introStarted = true; p = 0.5; planeY = NODULE.c[1] - 0.02; heat = 1; offYaw = offPitch = 0; }
    function step(dt) {
      var k = dt * 60;
      vYaw += (tYaw - offYaw) * 0.012 * k; vYaw *= Math.pow(0.88, k); offYaw += vYaw * k;
      vPitch += (tPitch - offPitch) * 0.012 * k; vPitch *= Math.pow(0.88, k); offPitch += vPitch * k;
      yaw += 0.05 * dt;
      if (introStarted && intro < 1) intro = Math.min(1, intro + dt / 1.8);
      tIdle += dt;
      var scrolled = 0.85 - 1.7 * smooth((p - 0.1) / 0.8);         // head to foot as the band rises
      var target = clamp(scrolled + 0.22 * Math.sin(tIdle * 0.55), -0.95, 0.98);
      if (intro < 1) planeY = Y1 + OHX.ease(intro) * (target - Y1);
      else planeY += (target - planeY) * Math.min(1, dt * 4);
    }

    /* ---- projection: rotation terms computed once per frame ---- */
    var cY = 1, sY = 0, cP = 1, sP = 0, sc = 1, F = 3.1, PJx = 0, PJy = 0, PJs = 1;
    function project(x, y, z) {
      var x1 = x * cY + z * sY, z1 = -x * sY + z * cY;
      var y2 = y * cP - z1 * sP, z2 = y * sP + z1 * cP;
      var pr = F / (F + z2);
      PJx = cx + x1 * sc * pr; PJy = cy - y2 * sc * pr; PJs = pr;
    }

    /* ---- the cut face, drawn on the plane ---- */
    var q = [0, 0];
    function pathPlane(nSeg, fn) {
      g.beginPath();
      for (var s = 0; s <= nSeg; s++) {
        fn((s / nSeg) * TAU, q);
        project(q[0], planeY, q[1]);
        if (s === 0) g.moveTo(PJx, PJy); else g.lineTo(PJx, PJy);
      }
      g.closePath();
    }
    function ellipseOn(x, z, rx, rz, nSeg) { pathPlane(nSeg || 24, function (a, o) { o[0] = x + Math.cos(a) * rx; o[1] = z + Math.sin(a) * rz; }); }

    function drawSlice(alpha) {
      var y = planeY, s;
      if (y < Y0 || y > Y1 || alpha < 0.01) return;
      // body: soft tissue with a darker subcutaneous rim and a peach outline
      pathPlane(96, function (a, o) { bodyXZ(y, a, 1, o); });
      g.fillStyle = rgba(CREAM, 0.13 * alpha); g.fill();
      g.strokeStyle = rgba(PEACH, 0.95 * alpha); g.lineWidth = 1.3; g.stroke();
      pathPlane(96, function (a, o) { bodyXZ(y, a, 0.93, o); });
      g.fillStyle = rgba(CREAM, 0.08 * alpha); g.fill();
      // lungs: air, near-black on a lung window
      var lf = lungF(y);
      if (lf > 0.02) {
        for (s = -1; s <= 1; s += 2) {
          var sd = s;
          pathPlane(64, function (a, o) { lungXZ(sd, lf, a, o); });
          g.fillStyle = rgba(DEEP, 0.92 * alpha); g.fill();
          g.strokeStyle = rgba(PEACH, 0.55 * alpha); g.lineWidth = 1; g.stroke();
        }
      }
      // heart and mediastinum
      var hy = (y - HEART.c[1]) / HEART.r[1];
      if (hy > -1 && hy < 1) {
        var hk = Math.sqrt(1 - hy * hy);
        ellipseOn(HEART.c[0], HEART.c[2], HEART.r[0] * hk, HEART.r[2] * hk, 40);
        g.fillStyle = rgba(CREAM, 0.26 * alpha); g.fill();
        g.strokeStyle = rgba(PEACH_SOFT, 0.45 * alpha); g.lineWidth = 0.8; g.stroke();
      }
      // airway
      if (y > TRACHEA.y0) {
        ellipseOn(0, TRACHEA.z, TRACHEA.r, TRACHEA.r);
        g.fillStyle = rgba(DEEP, 0.95 * alpha); g.fill();
        g.strokeStyle = rgba(PEACH, 0.5 * alpha); g.lineWidth = 0.8; g.stroke();
      }
      // bone: vertebral body and canal, ribs, sternum
      if (!isDisc(y)) {
        ellipseOn(0, SPINE.z, SPINE.r, SPINE.r); g.fillStyle = rgba(CREAM, 0.88 * alpha); g.fill();
        ellipseOn(0, SPINE.canalZ, SPINE.canalR * 1.35, SPINE.canalR * 1.35); g.fillStyle = rgba(CREAM, 0.72 * alpha); g.fill();
        ellipseOn(0, SPINE.canalZ, SPINE.canalR * 0.75, SPINE.canalR * 0.75); g.fillStyle = rgba(DEEP, 0.9 * alpha); g.fill();
      }
      g.fillStyle = rgba(CREAM, 0.9 * alpha);
      for (var r = 0; r < RIBS.length; r++) {
        var a = RIB_A0 + (RIBS[r] - y) / RIB_DROP * (RIB_A1 - RIB_A0);
        if (a < RIB_A0 || a > RIB_A1) continue;
        for (s = -1; s <= 1; s += 2) {
          ribXYZ(s, RIBS[r], a, tmp);
          ellipseOn(tmp[0], tmp[2], 0.034, 0.024, 12);
          g.fill();
        }
      }
      if (y > STERNUM.y0 && y < STERNUM.y1) { ellipseOn(0, -bodyR(y)[1] * 0.9, STERNUM.w, STERNUM.d, 16); g.fill(); }
      // nodule: bright and slightly spiculated inside the dark lung
      var dy = y - NODULE.c[1];
      if (Math.abs(dy) < NODULE.r) {
        var nr = Math.sqrt(NODULE.r * NODULE.r - dy * dy);
        pathPlane(36, function (a2, o) { var k = 1 + 0.12 * Math.sin(a2 * 7 + 0.6) * Math.sin(a2 * 3); o[0] = NODULE.c[0] + Math.cos(a2) * nr * k; o[1] = NODULE.c[2] + Math.sin(a2) * nr * k; });
        g.fillStyle = rgba(CREAM, 0.95 * alpha); g.fill();
        g.strokeStyle = rgba(NOD, alpha); g.lineWidth = 1.2; g.stroke();
      }
      // patient orientation at the plane's edges, as on a reading console
      g.font = '500 10px ' + mono;
      g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillStyle = rgba(PEACH, 0.85 * alpha);
      project(-1.2, y, 0); g.fillText('R', PJx, PJy);
      project(1.2, y, 0); g.fillText('L', PJx, PJy);
      project(0, y, -0.84); g.fillText('A', PJx, PJy);
      project(0, y, 0.84); g.fillText('P', PJx, PJy);
    }

    var P2 = new Float32Array(8);
    function drawPlaneFrame(alpha) {
      var ex = 1.22 * planeK, ez = 0.9 * planeK, c;
      project(-ex, planeY, -ez); P2[0] = PJx; P2[1] = PJy;
      project(ex, planeY, -ez); P2[2] = PJx; P2[3] = PJy;
      project(ex, planeY, ez); P2[4] = PJx; P2[5] = PJy;
      project(-ex, planeY, ez); P2[6] = PJx; P2[7] = PJy;
      g.beginPath();
      g.moveTo(P2[0], P2[1]); g.lineTo(P2[2], P2[3]); g.lineTo(P2[4], P2[5]); g.lineTo(P2[6], P2[7]); g.closePath();
      g.fillStyle = rgba(PEACH, 0.06 * alpha); g.fill();
      g.strokeStyle = rgba(PEACH, 0.22 * alpha); g.lineWidth = 1; g.stroke();
      g.beginPath();
      for (c = 0; c < 4; c++) {
        var ax = P2[c * 2], ay = P2[c * 2 + 1], nx = P2[((c + 1) % 4) * 2], ny = P2[((c + 1) % 4) * 2 + 1], px = P2[((c + 3) % 4) * 2], py = P2[((c + 3) % 4) * 2 + 1];
        g.moveTo(ax + (nx - ax) * 0.07, ay + (ny - ay) * 0.07); g.lineTo(ax, ay); g.lineTo(ax + (px - ax) * 0.07, ay + (py - ay) * 0.07);
      }
      g.strokeStyle = rgba(PEACH, 0.9 * alpha); g.lineWidth = 1.5; g.stroke();
    }

    /* Slice ruler: 256 images; minor tick every 8, mid every 32, labelled major every 64. */
    function drawRuler(im) {
      var rx = W - 20, top = H * 0.2, bot = H * 0.8, span = bot - top, s;
      if (span < 90) return;
      g.beginPath();
      for (s = 0; s <= 256; s += 8) {
        var yy = Math.round(bot - span * (s / 256)) + 0.5;
        var len = s % 64 === 0 ? 12 : s % 32 === 0 ? 7 : 3.5;
        g.moveTo(rx - len, yy); g.lineTo(rx, yy);
      }
      g.moveTo(rx + 0.5, top); g.lineTo(rx + 0.5, bot + 0.5);
      g.strokeStyle = rgba(CREAM, 0.34); g.lineWidth = 1; g.stroke();
      g.font = '400 9px ' + mono;
      g.textAlign = 'right'; g.textBaseline = 'middle';
      g.fillStyle = rgba(CREAM, 0.42);
      for (s = 0; s <= 256; s += 64) g.fillText(String(s), rx - 16, Math.round(bot - span * (s / 256)) + 0.5);
      var my = Math.round(bot - span * ((im - 1) / 255)) + 0.5;
      g.beginPath(); g.moveTo(rx - 20, my); g.lineTo(rx + 5, my);
      g.strokeStyle = rgba(PEACH, 1); g.lineWidth = 1.5; g.stroke();
      g.beginPath(); g.moveTo(rx - 27, my - 4); g.lineTo(rx - 20, my); g.lineTo(rx - 27, my + 4); g.closePath();
      g.fillStyle = rgba(PEACH, 1); g.fill();
    }
    /* Scale bar: 50 mm at the plane's centre depth. */
    function drawScale() {
      var len = Math.round(50 / MM_PER_UNIT * sc), x1 = W - 54, x0 = x1 - len, yb = H - 29.5;
      g.beginPath();
      g.moveTo(x0 + 0.5, yb - 5); g.lineTo(x0 + 0.5, yb); g.lineTo(x1 - 0.5, yb); g.lineTo(x1 - 0.5, yb - 5);
      g.moveTo(Math.round((x0 + x1) / 2) + 0.5, yb - 3); g.lineTo(Math.round((x0 + x1) / 2) + 0.5, yb);
      g.strokeStyle = rgba(CREAM, 0.6); g.lineWidth = 1; g.stroke();
      g.font = '400 9px ' + mono;
      g.textAlign = 'right'; g.textBaseline = 'alphabetic';
      g.fillStyle = rgba(CREAM, 0.6);
      g.fillText('50 MM', x1, yb - 9);
    }

    /* ---- render ---- */
    var BAND_W = 0.045;
    function render() {
      if (W < 2 || H < 2) return;
      var zoom = 0.9 + 0.16 * smooth((p - 0.05) / 0.6);
      var revealY = intro < 1 ? Y1 - OHX.ease(intro) * (Y1 - Y0 + 0.1) : -99;
      var Yr = yaw + (p - 0.5) * 1.6 + offYaw;
      var Pt = clamp(-0.3 + (p - 0.5) * 0.22 + offPitch, -0.7, 0.05);
      cY = Math.cos(Yr); sY = Math.sin(Yr); cP = Math.cos(Pt); sP = Math.sin(Pt);
      sc = baseScale * zoom;
      var pa = intro < 1 ? smooth(intro * 1.4) : 1;

      g.globalCompositeOperation = 'source-over';
      g.globalAlpha = 1;
      g.clearRect(0, 0, W, H);
      g.drawImage(bloom, cx - sc * 1.9, cy - sc * 1.9, sc * 3.8, sc * 3.8);
      drawPlaneFrame(pa);

      // project and bucket
      var nb, x, y, z, x1, z1, y2, z2, pr, sx, sy, dn, kd, al, dist, hl, cls, lv, bk, o, above;
      for (nb = 0; nb < NB; nb++) cnts[nb] = 0;
      for (var i = 0; i < nActive; i++) {
        y = PY[i];
        if (y < revealY) continue;                                 // acquisition front, head to foot
        x = PX[i]; z = PZ[i];
        x1 = x * cY + z * sY; z1 = -x * sY + z * cY;
        y2 = y * cP - z1 * sP; z2 = y * sP + z1 * cP;
        pr = F / (F + z2);
        sx = cx + x1 * sc * pr; sy = cy - y2 * sc * pr;
        if (sx < -3 || sx > W + 3 || sy < -3 || sy > H + 3) continue;
        dn = 0.5 - z2 * 0.34; dn = dn < 0 ? 0 : dn > 1 ? 1 : dn;
        kd = PK[i];
        al = KB[kd] * (0.25 + 0.75 * dn);
        cls = CLS_OF[kd];
        dist = y - planeY; above = dist > 0; if (dist < 0) dist = -dist;
        if (dist < BAND_W) {
          hl = 1 - dist / BAND_W; hl *= hl;
          if (kd !== NOD_K) cls = 4;
          al += 0.75 * hl;
        } else if (above) al *= 0.55;                               // cut-away: the part above the plane recedes
        if (kd === NOD_K) al += 0.35 * heat;
        if (intro < 1 && y - revealY < 0.04) { cls = 4; al = 0.9; }
        if (al < 0.02) continue;
        lv = (al * LV) | 0; if (lv >= LV) lv = LV - 1;
        bk = (above ? NHALF : 0) + cls * LV + lv;
        o = cnts[bk] * 3;
        bufs[bk][o] = sx; bufs[bk][o + 1] = sy; bufs[bk][o + 2] = 0.9 + 1.0 * dn;
        cnts[bk]++;
      }
      flush(0, NHALF);                                             // pass 1: below the plane
      var dyN = Math.abs(planeY - NODULE.c[1]);
      heat += ((dyN < NODULE.r * 1.3 ? 1 - dyN / (NODULE.r * 1.3) : 0) - heat) * (fx.reduced ? 1 : 0.2);
      if (heat > 0.02) {
        project(NODULE.c[0], NODULE.c[1], NODULE.c[2]);
        var gr = NODULE.r * sc * PJs * 4.2;
        g.globalCompositeOperation = 'lighter';
        g.globalAlpha = heat;
        g.drawImage(nodGlow, PJx - gr, PJy - gr, gr * 2, gr * 2);
        g.globalAlpha = 1;
        g.globalCompositeOperation = 'source-over';
      }
      drawSlice(pa);                                               // the cut face
      flush(NHALF, NB);                                            // pass 2: above the plane, dimmed
      var im = clamp(Math.round((planeY - Y0) / (Y1 - Y0) * 255) + 1, 1, 256);
      drawRuler(im);
      drawScale();

      setText(sliceEl, ('00' + im).slice(-3));
      var zmm = (im - 128.5) * 1.0;
      setText(zEl, (zmm >= 0 ? '+' : '−') + ('00' + Math.abs(zmm).toFixed(1)).slice(-5));
      var deg = Math.round(((Yr * 180 / Math.PI) % 360 + 360) % 360) % 360;
      setText(rotEl, ('00' + deg).slice(-3));
    }
    function flush(from, to) {
      for (var bi = from; bi < to; bi++) {
        var nn = cnts[bi];
        if (!nn) continue;
        var buf = bufs[bi], local = bi % NHALF;
        g.globalAlpha = ((local % LV) + 0.5) / LV;
        g.fillStyle = CLS_FILL[(local / LV) | 0];
        g.beginPath();
        for (var k = 0; k < nn; k++) {
          var s3 = k * 3, sz = buf[s3 + 2];
          g.rect(buf[s3] - sz * 0.5, buf[s3 + 1] - sz * 0.5, sz, sz);
        }
        g.fill();
      }
      g.globalAlpha = 1;
    }

    /* ---- lifecycle ---- */
    var onScreen = false, ema = 0;
    var perf = { samples: new Float32Array(240), n: 0, points: function () { return nActive; } };
    fx.perf = fx.perf || {};
    fx.perf.volume = perf;
    function measure() {
      if (!fx.isLive(band)) return;
      sf.resize();
      layout();
      p = fx.progress(band);
      if (fx.reduced) staticState();
      render();
    }
    fx.watch(band, function (visible) {
      onScreen = visible;
      if (visible) { introStarted = true; if (!W || W < 2) measure(); fx.kick(); }
    });
    fx.onPage(function (id) { if (id === 'home') requestAnimationFrame(measure); });
    if ('ResizeObserver' in window) new ResizeObserver(function () { measure(); }).observe(host);
    else addEventListener('resize', measure);
    matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', function () { requestAnimationFrame(measure); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { if (W > 1) render(); });
    measure();

    fx.loop(function (time, dtMs) {
      var t0 = now();
      p = fx.progress(band);
      step(Math.min(0.05, dtMs / 1000));
      render();
      var work = now() - t0;
      perf.samples[perf.n % 240] = work; perf.n++;
      // Adapt the point budget to the measured frame cost (target well under 10 ms).
      ema = ema ? ema * 0.9 + work * 0.1 : work;
      if (perf.n > 20) {
        if (ema > 7 && nActive > 1600) { nActive = Math.round(nActive * 0.85); ema = 5; }
        else if (ema < 3 && nActive < nTarget) nActive = Math.min(nTarget, Math.round(nActive * 1.03) + 1);
      }
    }, function () { return !fx.reduced && onScreen && fx.isLive(band) && W > 1; });

    band.addEventListener('pointermove', function (e) {
      if (e.pointerType !== 'mouse' || fx.reduced) return;
      var r = band.getBoundingClientRect();
      tYaw = ((e.clientX - r.left) / r.width - 0.5) * 0.5;
      tPitch = ((e.clientY - r.top) / r.height - 0.5) * 0.22;
    });
    band.addEventListener('pointerleave', function () { tYaw = 0; tPitch = 0; });
  }

  /* ====================================================================
     Research areas: k-space track. Each area's cross-section is acquired
     (golden-angle spokes and a spiral) and reconstructed as it reaches the
     centre of the track, and dissolves back into k-space as it leaves.
     ==================================================================== */
  var GOLDEN = Math.PI * (3 - Math.sqrt(5));
  var SHAPES = [
    { // QA phantom: circular inserts on a ring
      outer: { rx: 0.94, ry: 0.94, h: [] }, inserts: true, lesion: { x: 0, y: 0, r: 0.13 }
    },
    { // two acquisitions of one section: a shifted second contour
      outer: { rx: 0.9, ry: 0.84, h: [[0.03, 2, 0.3], [0.03, 3, 2.2]] },
      organs: [{ x: -0.2, y: 0.1, rx: 0.5, ry: 0.44, h: [[0.05, 2, 0.9], [0.04, 3, 0.1]] }, { x: 0.48, y: 0.38, rx: 0.1, ry: 0.09, h: [] }],
      prev: { x: -0.02, y: -0.06, r: 0.27 }, lesion: { x: -0.12, y: 0.0, r: 0.14 }
    },
    { // abdomen: organs and a segmented lesion
      outer: { rx: 0.96, ry: 0.78, h: [[0.03, 2, 1.1], [0.025, 4, 0.2]] },
      organs: [
        { x: -0.34, y: -0.12, rx: 0.42, ry: 0.36, h: [[0.07, 2, 0.6], [0.04, 3, 1.7]] },
        { x: 0.42, y: 0.12, rx: 0.13, ry: 0.19, h: [[0.05, 2, 0.3]] },
        { x: -0.06, y: 0.32, rx: 0.12, ry: 0.17, h: [[0.05, 2, 1.2]] }
      ],
      lesion: { x: -0.4, y: -0.14, r: 0.15 }
    },
    { // thorax: two lung fields, a small nodule
      outer: { rx: 1, ry: 0.7, h: [[0.035, 2, 0.4], [0.02, 3, 1.3]] },
      organs: [
        { x: -0.43, y: -0.04, rx: 0.33, ry: 0.47, h: [[0.06, 2, 0.2], [0.03, 3, 2]] },
        { x: 0.43, y: -0.04, rx: 0.31, ry: 0.45, h: [[0.06, 2, 1.9], [0.03, 3, 0.5]] },
        { x: 0.06, y: 0.16, rx: 0.17, ry: 0.15, h: [[0.05, 2, 0]] }
      ],
      lesion: { x: 0.5, y: -0.2, r: 0.075 }
    },
    { // tissue section: glands and cells
      outer: { rx: 0.92, ry: 0.76, h: [[0.08, 3, 0.7], [0.05, 5, 2.1], [0.03, 7, 1]] },
      organs: [
        { x: -0.35, y: -0.18, rx: 0.14, ry: 0.11, h: [[0.08, 3, 0]] },
        { x: 0.22, y: -0.3, rx: 0.12, ry: 0.1, h: [[0.08, 3, 1]] },
        { x: 0.32, y: 0.22, rx: 0.15, ry: 0.12, h: [[0.08, 3, 2]] },
        { x: -0.2, y: 0.3, rx: 0.11, ry: 0.09, h: [[0.08, 3, 3]] }
      ],
      dots: 110, lesion: { x: 0.04, y: 0.02, r: 0.2 }
    }
  ];

  function blob(c, cx, cy, rx, ry, harm, jitter, jphase) {
    c.beginPath();
    for (var i = 0; i <= 96; i++) {
      var t = (i / 96) * TAU, m = 1;
      for (var k = 0; k < harm.length; k++) m += harm[k][0] * Math.sin(harm[k][1] * t + harm[k][2]);
      if (jitter) m += jitter * Math.sin(7 * t + jphase) + jitter * 0.6 * Math.sin(11 * t - jphase * 1.7);
      var x = cx + Math.cos(t) * rx * m, y = cy + Math.sin(t) * ry * m;
      if (i === 0) c.moveTo(x, y); else c.lineTo(x, y);
    }
    c.closePath();
  }

  function makeVis(panel, colors) {
    var host = panel.querySelector('[data-br-canvas]');
    if (!host) return null;
    var idx = parseInt(host.getAttribute('data-shape'), 10) || 0;
    var shape = SHAPES[idx] || SHAPES[0];
    var sf = surface(host, 'fx-canvas');
    var c = sf.ctx;
    var spokesEl = panel.querySelector('[data-br-spokes]');
    var reconEl = panel.querySelector('[data-br-recon]');
    var SPOKES = 144;
    var rand = mulberry(7 + idx * 97);
    var dots = [];
    for (var i = 0; i < (shape.dots || 0); i++) {
      var a = rand() * TAU, rr = Math.sqrt(rand()) * 0.78;
      dots.push([Math.cos(a) * rr * shape.outer.rx, Math.sin(a) * rr * shape.outer.ry, 0.006 + rand() * 0.01]);
    }
    var ring = null;   // field-of-view ring and ticks never change: pre-rendered per size
    var vis = { recon: -1 };
    vis.resize = function () {
      if (sf.resize() || !ring) {
        var d = sf.dpr, W = sf.w, H = sf.h, R = Math.min(W, H) * 0.38;
        ring = document.createElement('canvas');
        ring.width = Math.round(W * d); ring.height = Math.round(H * d);
        var rc = ring.getContext('2d');
        rc.setTransform(d, 0, 0, d, 0, 0);
        rc.strokeStyle = colors.ink; rc.globalAlpha = 0.45; rc.lineWidth = 1;
        rc.beginPath(); rc.arc(W / 2, H / 2, R * 1.14, 0, TAU); rc.stroke();
        rc.beginPath();
        for (var t = 0; t < 120; t++) {
          var ang = (t / 120) * TAU, len = t % 30 === 0 ? 10 : t % 10 === 0 ? 6 : 3;
          rc.moveTo(W / 2 + Math.cos(ang) * R * 1.14, H / 2 + Math.sin(ang) * R * 1.14);
          rc.lineTo(W / 2 + Math.cos(ang) * (R * 1.14 + len), H / 2 + Math.sin(ang) * (R * 1.14 + len));
        }
        rc.stroke();
        vis.recon = -1;
      }
    };
    vis.draw = function (r) {
      var W = sf.w, H = sf.h;
      if (W < 2 || H < 2 || !ring) return;
      if (vis.recon >= 0 && Math.abs(r - vis.recon) < 0.002) return;
      vis.recon = r;
      var cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.38;
      var acq = smooth(r / 0.55), img = smooth((r - 0.32) / 0.68);
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.globalAlpha = 1;
      c.clearRect(0, 0, c.canvas.width, c.canvas.height);
      c.drawImage(ring, 0, 0);
      c.setTransform(sf.dpr, 0, 0, sf.dpr, 0, 0);
      c.lineCap = 'round';

      var n = Math.round(acq * SPOKES), spokeA = 0.2 * (1 - img * 0.86);
      if (n > 0 && spokeA > 0.004) {
        c.strokeStyle = colors.ink; c.lineWidth = 0.6; c.globalAlpha = spokeA;
        c.beginPath();
        for (var s = 0; s < n; s++) {
          var a2 = s * GOLDEN, dx = Math.cos(a2) * R * 1.1, dy = Math.sin(a2) * R * 1.1;
          c.moveTo(cx - dx, cy - dy); c.lineTo(cx + dx, cy + dy);
        }
        c.stroke();
        if (acq < 1) {
          var al = (n - 1) * GOLDEN;
          c.globalAlpha = 0.9 * (1 - img); c.strokeStyle = colors.accent; c.lineWidth = 1.4;
          c.beginPath();
          c.moveTo(cx - Math.cos(al) * R * 1.1, cy - Math.sin(al) * R * 1.1);
          c.lineTo(cx + Math.cos(al) * R * 1.1, cy + Math.sin(al) * R * 1.1);
          c.stroke();
        }
      }
      var spA = 0.6 * (1 - img);
      if (spA > 0.01 && acq > 0) {
        var turns = 7, maxT = acq * turns * TAU;
        c.globalAlpha = spA; c.strokeStyle = colors.accent; c.lineWidth = 0.9;
        c.beginPath();
        c.moveTo(cx, cy);
        for (var qq = 0.06; qq <= maxT; qq += 0.06) {
          var rad = (qq / (turns * TAU)) * R * 1.05;
          c.lineTo(cx + Math.cos(qq) * rad, cy + Math.sin(qq) * rad);
        }
        c.stroke();
      }
      if (img > 0.001) {
        var jit = (1 - img) * 0.06, o = shape.outer;
        var gfill = c.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 1.05);
        gfill.addColorStop(0, colors.white); gfill.addColorStop(1, colors.bgSoft);
        c.globalAlpha = 0.55 * img; c.fillStyle = gfill;
        blob(c, cx, cy, R * o.rx, R * o.ry, o.h, jit, 0.3); c.fill();
        c.strokeStyle = colors.ink;
        for (var j = 0; j < 5; j++) {
          var scl = 1 - j * 0.075;
          c.globalAlpha = img * (j === 0 ? 0.8 : 0.3 - j * 0.05);
          c.lineWidth = j === 0 ? 1.2 : 0.6;
          blob(c, cx, cy, R * o.rx * scl, R * o.ry * scl, o.h, jit * (1 + j * 0.4), j * 1.3);
          c.stroke();
        }
        var orgs = shape.organs || [];
        for (var k = 0; k < orgs.length; k++) {
          var og = orgs[k], ox = cx + og.x * R, oy = cy + og.y * R;
          c.globalAlpha = 0.08 * img; c.fillStyle = colors.ink;
          blob(c, ox, oy, og.rx * R, og.ry * R, og.h, jit, k); c.fill();
          c.globalAlpha = 0.55 * img; c.lineWidth = 0.8; c.strokeStyle = colors.ink; c.stroke();
          c.globalAlpha = 0.2 * img;
          blob(c, ox, oy, og.rx * R * 0.8, og.ry * R * 0.8, og.h, jit, k + 2); c.stroke();
        }
        if (dots.length) {
          c.globalAlpha = 0.5 * img; c.fillStyle = colors.ink;
          c.beginPath();
          for (var d2 = 0; d2 < dots.length; d2++) {
            var dd = dots[d2];
            c.moveTo(cx + dd[0] * R + dd[2] * R, cy + dd[1] * R);
            c.arc(cx + dd[0] * R, cy + dd[1] * R, dd[2] * R, 0, TAU);
          }
          c.fill();
        }
        if (shape.inserts) {
          c.lineWidth = 0.8;
          for (var pI = 0; pI < 8; pI++) {
            var pa = (pI / 8) * TAU - Math.PI / 2, prr = 0.05 + pI * 0.017;
            var ix = cx + Math.cos(pa) * R * 0.58, iy = cy + Math.sin(pa) * R * 0.58;
            c.globalAlpha = (0.05 + pI * 0.03) * img; c.fillStyle = colors.ink;
            c.beginPath(); c.arc(ix, iy, prr * R, 0, TAU); c.fill();
            c.globalAlpha = 0.55 * img; c.strokeStyle = colors.ink; c.stroke();
          }
          c.globalAlpha = 0.14 * img;
          c.beginPath();
          c.moveTo(cx - R * 0.9, cy); c.lineTo(cx + R * 0.9, cy);
          c.moveTo(cx, cy - R * 0.9); c.lineTo(cx, cy + R * 0.9);
          c.stroke();
        }
        var seg = smooth((img - 0.55) / 0.45);
        if (shape.prev && seg > 0) {
          var pv = shape.prev;
          c.globalAlpha = 0.7 * seg; c.strokeStyle = colors.ink; c.lineWidth = 1;
          c.setLineDash([3, 4]);
          c.beginPath(); c.arc(cx + pv.x * R, cy + pv.y * R, pv.r * R, 0, TAU * seg); c.stroke();
          c.setLineDash([]);
        }
        if (shape.lesion && seg > 0) {
          var L = shape.lesion, lx = cx + L.x * R, ly = cy + L.y * R, lr = L.r * R;
          c.globalAlpha = 0.3 * seg; c.fillStyle = colors.accent;
          blob(c, lx, ly, lr, lr * 0.92, [[0.08, 3, 0.4], [0.05, 5, 1]], 0, 0); c.fill();
          var per = TAU * lr * 1.1;
          c.globalAlpha = 0.95 * seg; c.strokeStyle = colors.accentDeep; c.lineWidth = 1.5;
          c.setLineDash([per * seg, per]); c.stroke(); c.setLineDash([]);
        }
      }
      c.globalAlpha = 1;
      setText(spokesEl, 'SPOKES ' + ('00' + Math.round(acq * SPOKES)).slice(-3) + '/' + SPOKES);
      setText(reconEl, 'RECON ' + ('00' + Math.round(img * 100)).slice(-3) + '%');
    };
    return vis;
  }

  function setupBranches(fx) {
    var root = document.querySelector('[data-fx="branches"] [data-br]');
    if (!root) return;
    var viewport = root.querySelector('[data-br-viewport]');
    var track = root.querySelector('[data-br-track]');
    var panels = arr(track.querySelectorAll('[data-br-panel]'));
    var picks = arr(root.querySelectorAll('[data-br-go]'));
    var prevBtn = root.querySelector('[data-br-prev]');
    var nextBtn = root.querySelector('[data-br-next]');
    var numEl = root.querySelector('[data-br-num]');
    var fillEl = root.querySelector('[data-br-fill]');
    var liveEl = root.querySelector('[data-br-live]');
    var n = panels.length;
    if (!n) return;
    root.classList.add('is-enhanced');

    var pal = fx.palette;
    var colors = { ink: pal.navy, white: '#ffffff', bgSoft: pal.peach, accent: pal.peachDeep, accentDeep: '#9c6a54' };
    var vis = panels.map(function (pnl) { return makeVis(pnl, colors); });
    var titles = panels.map(function (pnl) { var h = pnl.querySelector('h3'); return h ? h.textContent.replace(/\s+/g, ' ').trim().replace(/\.$/, '') : ''; });

    var f = 0, target = 0, step = 0, current = -1, tween = null;
    var recon = panels.map(function () { return 0; });
    var shownRecon = picks.map(function () { return -1; });
    var started = false, onScreen = false, drag = null, justDragged = false;

    function reduced() { return fx.reduced; }
    function place() {
      track.style.transform = 'translate3d(' + (-f * step).toFixed(1) + 'px,0,0)';
      var fr = clamp(f, 0, n - 1), idx = Math.min(n - 1, Math.floor(fr + 1e-4));
      var frac = Math.min(9, Math.floor((fr - idx) * 10 + 1e-4));
      setText(numEl, (idx + 1 < 10 ? '0' : '') + (idx + 1) + '.' + frac);
      if (fillEl) fillEl.style.transform = 'scaleX(' + (n > 1 ? fr / (n - 1) : 1).toFixed(4) + ')';
    }
    function syncPickProgress() {
      for (var i = 0; i < picks.length; i++) {
        var v = i === current ? Math.round(recon[i] * 50) / 50 : 0;
        if (v !== shownRecon[i]) { shownRecon[i] = v; picks[i].style.setProperty('--recon', String(v)); }
      }
    }
    function drawAll() { for (var i = 0; i < n; i++) if (vis[i]) vis[i].draw(recon[i]); syncPickProgress(); }
    function settleReduced() { tween = null; f = target; recon = recon.map(function () { return 1; }); }
    function measure() {
      if (!fx.isLive(root)) return;
      var a = panels[0], b = panels[1];
      step = b ? b.offsetLeft - a.offsetLeft : a.offsetWidth;
      vis.forEach(function (v) { if (v) v.resize(); });
      if (reduced()) settleReduced();
      place();
      drawAll();
    }
    function goal(i) {
      if (!started) return 0;
      var d = Math.abs(i - f);
      return d < 0.04 ? 1 : smooth(1 - d / 0.8) * 0.85;
    }
    function setCurrent(i) {
      if (i === current) return;
      current = i;
      panels.forEach(function (pnl, k) {
        var on = k === i;
        pnl.classList.toggle('is-current', on);
        if (on) pnl.removeAttribute('aria-hidden'); else pnl.setAttribute('aria-hidden', 'true');
        arr(pnl.querySelectorAll('a, button')).forEach(function (el) {
          if (on) el.removeAttribute('tabindex'); else el.setAttribute('tabindex', '-1');
        });
      });
      picks.forEach(function (btn, k) { btn.setAttribute('aria-pressed', k === i ? 'true' : 'false'); });
      if (prevBtn) prevBtn.disabled = i <= 0;
      if (nextBtn) nextBtn.disabled = i >= n - 1;
      setText(liveEl, titles[i] + ', area ' + (i + 1) + ' of ' + n);
    }
    function go(i) {
      target = clamp(i, 0, n - 1);
      setCurrent(target);
      if (reduced()) { settleReduced(); place(); drawAll(); return; }
      var dist = Math.abs(target - f);
      tween = dist < 0.001 ? null : { from: f, to: target, t0: 0, dur: clamp(480 + 170 * dist, 480, 980) };
      fx.kick();
    }
    function busy() {
      if (drag && drag.moved) return true;
      if (tween) return true;
      for (var i = 0; i < n; i++) if (Math.abs(goal(i) - recon[i]) > 0.003) return true;
      return false;
    }

    fx.loop(function (time, dtMs) {
      var dt = Math.min(0.05, dtMs / 1000);
      if (tween && !(drag && drag.moved)) {
        if (!tween.t0) tween.t0 = time;
        var k = clamp((time - tween.t0) / tween.dur, 0, 1);
        f = tween.from + (tween.to - tween.from) * inOut(k);
        if (k >= 1) { f = tween.to; tween = null; }
      }
      for (var i = 0; i < n; i++) {
        var gl = goal(i), rate = gl > recon[i] ? 0.8 : 1.8;   // acquire deliberately, dissolve quickly
        recon[i] += clamp(gl - recon[i], -rate * dt, rate * dt);
      }
      place();
      drawAll();
    }, function () { return !reduced() && onScreen && fx.isLive(root) && busy(); });

    picks.forEach(function (btn) {
      btn.addEventListener('click', function () { go(parseInt(btn.getAttribute('data-br-go'), 10) || 0); });
    });
    if (prevBtn) prevBtn.addEventListener('click', function () { go(current - 1); });
    if (nextBtn) nextBtn.addEventListener('click', function () { go(current + 1); });
    root.addEventListener('keydown', function (e) {
      if (e.target.closest('a')) return;
      if (e.key === 'ArrowRight') { e.preventDefault(); go(current + 1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); go(current - 1); }
      else if (e.key === 'Home') { e.preventDefault(); go(0); }
      else if (e.key === 'End') { e.preventDefault(); go(n - 1); }
    });

    // Drag (mouse, pen, touch). touch-action: pan-y keeps vertical page scrolling native.
    viewport.addEventListener('pointerdown', function (e) {
      if (e.button) return;
      drag = { id: e.pointerId, x0: e.clientX, y0: e.clientY, f0: f, lastX: e.clientX, lastT: now(), v: 0, moved: false };
    });
    viewport.addEventListener('pointermove', function (e) {
      if (!drag || e.pointerId !== drag.id || !step) return;
      var dx = e.clientX - drag.x0;
      if (!drag.moved) {
        if (Math.abs(dx) < 8) return;
        if (Math.abs(e.clientY - drag.y0) > Math.abs(dx)) { drag = null; return; }
        drag.moved = true;
        drag.f0 = f; drag.x0 = e.clientX; dx = 0;   // pick up from wherever a running transition is
        tween = null;
        root.classList.add('is-dragging');
        try { viewport.setPointerCapture(e.pointerId); } catch (err) { /* not capturable */ }
      }
      var raw = drag.f0 - dx / step;
      if (raw < 0) raw *= 0.3; else if (raw > n - 1) raw = n - 1 + (raw - (n - 1)) * 0.3;
      var t = now();
      drag.v = drag.v * 0.6 + ((e.clientX - drag.lastX) / Math.max(8, t - drag.lastT)) * 0.4;
      drag.lastX = e.clientX; drag.lastT = t;
      f = raw;
      setCurrent(clamp(Math.round(f), 0, n - 1));
      if (reduced()) place();
      fx.kick();
    });
    function endDrag(e) {
      if (!drag || (e && e.pointerId !== drag.id)) return;
      var d = drag;
      drag = null;
      if (!d.moved) return;
      root.classList.remove('is-dragging');
      justDragged = true;
      setTimeout(function () { justDragged = false; }, 0);
      var flick = d.v < -0.35 ? 0.5 : d.v > 0.35 ? -0.5 : 0;
      go(Math.round(clamp(f + flick, 0, n - 1)));
    }
    viewport.addEventListener('pointerup', endDrag);
    viewport.addEventListener('pointercancel', endDrag);
    viewport.addEventListener('lostpointercapture', endDrag);
    // A drag never also follows a link it ended on; a click on a side panel brings it to the centre.
    viewport.addEventListener('click', function (e) {
      if (justDragged) { e.preventDefault(); e.stopPropagation(); return; }
      var pnl = e.target.closest('[data-br-panel]');
      var i = pnl ? panels.indexOf(pnl) : -1;
      if (i > -1 && i !== current) { e.preventDefault(); go(i); }
    }, true);
    // Focus landing in a panel (e.g. screen-reader navigation) brings it to the centre.
    track.addEventListener('focusin', function (e) {
      var pnl = e.target.closest('[data-br-panel]');
      var i = pnl ? panels.indexOf(pnl) : -1;
      if (i > -1 && i !== current) go(i);
    });

    fx.watch(root, function (visible) {
      onScreen = visible;
      if (visible) { started = true; fx.kick(); }
    }, { threshold: 0.2 });
    fx.onPage(function (id) { if (id === 'research') requestAnimationFrame(measure); });
    if ('ResizeObserver' in window) new ResizeObserver(function () { measure(); }).observe(viewport);
    else addEventListener('resize', measure);
    matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', function () { requestAnimationFrame(measure); });
    setCurrent(0);
    measure();
  }

  /* ====================================================================
     Magnetic primary button on the home hero (fine pointers only). Uses the
     independent `translate` property so the button's own hover lift stays.
     ==================================================================== */
  function setupMagnet(fx) {
    if (!fx.fine) return;
    var btn = document.querySelector('.page[data-page="home"] .hero .button.primary');
    if (!btn || !('translate' in btn.style)) return;
    var x = 0, y = 0, tx = 0, ty = 0, active = false;
    fx.loop(function () {
      x += (tx - x) * 0.18; y += (ty - y) * 0.18;
      if (Math.abs(tx - x) < 0.05 && Math.abs(ty - y) < 0.05) { x = tx; y = ty; if (!tx && !ty) active = false; }
      btn.style.translate = x.toFixed(2) + 'px ' + y.toFixed(2) + 'px';
    }, function () { return active && fx.isLive(btn); });
    btn.addEventListener('pointermove', function (e) {
      if (e.pointerType !== 'mouse' || fx.reduced) return;
      var r = btn.getBoundingClientRect();
      tx = (e.clientX - (r.left + r.width / 2)) * 0.14;
      ty = (e.clientY - (r.top + r.height / 2)) * 0.22;
      active = true;
      fx.kick();
    });
    btn.addEventListener('pointerleave', function () { tx = 0; ty = 0; fx.kick(); });
  }
})();
