/* OncoloHealth effects core.
   Shared runtime for the fx/ modules: palette tokens, page lifecycle, visibility,
   scroll progress and a single animation loop. Native scrolling only: nothing here
   pins, snaps, smooths or intercepts the wheel. */
(function () {
  'use strict';

  var root = document.documentElement;
  var gsap = window.gsap || null;
  var ScrollTrigger = window.ScrollTrigger || null;
  if (gsap && ScrollTrigger) gsap.registerPlugin(ScrollTrigger);

  var reducedQuery = matchMedia('(prefers-reduced-motion: reduce)');
  var fineQuery = matchMedia('(hover: hover) and (pointer: fine)');

  // Each page reads as one imaging study; this is the modality it is "acquired" with.
  var MODALITIES = {
    home:          { seq: 1,  key: 'ct',     name: 'CT',              detail: 'Axial · 1.0 mm' },
    research:      { seq: 2,  key: 'path',   name: 'Histopathology',  detail: 'H&E · 40×' },
    platform:      { seq: 3,  key: 'mri',    name: 'MRI',             detail: 'T2 · Axial' },
    models:        { seq: 4,  key: 'pet',    name: 'PET',             detail: 'FDG · SUV' },
    catalog:       { seq: 5,  key: 'mri',    name: 'MRI',             detail: 'T1 · Sagittal' },
    'open-source': { seq: 6,  key: 'fusion', name: 'PET/CT fusion',   detail: 'Registered' },
    commercial:    { seq: 7,  key: 'xray',   name: 'X-ray',           detail: 'PA projection' },
    quote:         { seq: 8,  key: 'xray',   name: 'X-ray',           detail: 'Lateral' },
    support:       { seq: 9,  key: 'us',     name: 'Ultrasound',      detail: 'B-mode · 7.5 MHz' },
    privacy:       { seq: 10, key: 'us',     name: 'Ultrasound',      detail: 'Doppler' },
    about:         { seq: 11, key: 'fusion', name: 'Fusion',          detail: 'Report' }
  };

  function cssVar(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }

  function readPalette() {
    return {
      deep: cssVar('--fx-deep') || '#111e32',
      navy: cssVar('--fx-navy') || '#1e3047',
      ink: cssVar('--fx-ink') || '#172237',
      cream: cssVar('--fx-cream') || '#fbf5f1',
      paper: cssVar('--fx-paper') || '#fffaf6',
      peach: cssVar('--fx-peach') || '#f1d5c5',
      peachLight: cssVar('--fx-peach-light') || '#eac3b6',
      peachDeep: cssVar('--fx-peach-deep') || '#bc8a72',
      green: cssVar('--fx-green') || '#80a995',
      line: cssVar('--fx-line') || '#e3d4d0',
      bloom: cssVar('--fx-bloom') || '#ffffff'
    };
  }

  var modules = [];
  var started = false;
  var pageListeners = [];
  var currentPage = null;

  var OHX = {
    gsap: gsap,
    ScrollTrigger: ScrollTrigger,
    reduced: reducedQuery.matches,
    fine: fineQuery.matches,
    modalities: MODALITIES,
    palette: readPalette(),

    /* Register a module; it runs once the DOM is ready, isolated from failures elsewhere. */
    register: function (name, fn) {
      // A module whose script arrives after start-up runs straight away.
      if (started) safe(name, function () { fn(OHX); });
      else modules.push({ name: name, fn: fn });
    },

    page: function () { return document.body.dataset.page || 'home'; },
    pageEl: function (id) { return document.querySelector('.page[data-page="' + (id || OHX.page()) + '"]'); },
    modality: function (id) { return MODALITIES[id || OHX.page()] || MODALITIES.home; },

    /* Called with the page id now and on every page change. */
    onPage: function (fn) { pageListeners.push(fn); if (currentPage) safe('onPage', function () { fn(currentPage); }); },

    /* Is el inside the currently shown page (or outside any page, e.g. header/footer)? */
    isLive: function (el) { var p = el.closest('.page'); return !p || p.classList.contains('active'); },

    /* IntersectionObserver helper. cb(isVisible, entry). Returns a disconnect function. */
    watch: function (el, cb, opts) {
      if (!('IntersectionObserver' in window)) { cb(true); return function () {}; }
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { cb(e.isIntersecting, e); });
      }, opts || { rootMargin: '120px 0px' });
      io.observe(el);
      return function () { io.disconnect(); };
    },

    /* Fire cb once the first time el scrolls into view. */
    once: function (el, cb, threshold) {
      var stop = OHX.watch(el, function (vis) { if (vis) { stop(); cb(); } }, { threshold: threshold || 0.2 });
    },

    /* 0 when el's top meets the viewport bottom, 1 when its bottom meets the viewport top. */
    progress: function (el) {
      var r = el.getBoundingClientRect(), vh = innerHeight;
      var t = (vh - r.top) / (vh + r.height);
      return t < 0 ? 0 : t > 1 ? 1 : t;
    },

    /* Shared rAF loop. fn(time, dt) runs only while active() returns true. */
    loop: function (fn, active) { loops.push({ fn: fn, active: active || function () { return true; } }); kick(); },

    /* Canvas sized to its CSS box at device pixel ratio (capped). Returns {canvas, ctx, w, h, dpr, resize}. */
    canvas: function (host, cls) {
      var c = document.createElement('canvas');
      c.className = cls || 'fx-canvas';
      c.setAttribute('aria-hidden', 'true');
      host.appendChild(c);
      var o = { canvas: c, ctx: c.getContext('2d'), w: 0, h: 0, dpr: 1 };
      o.resize = function () {
        var r = c.getBoundingClientRect();
        o.dpr = Math.min(window.devicePixelRatio || 1, 2);
        o.w = Math.max(1, Math.round(r.width));
        o.h = Math.max(1, Math.round(r.height));
        c.width = Math.round(o.w * o.dpr);
        c.height = Math.round(o.h * o.dpr);
        o.ctx.setTransform(o.dpr, 0, 0, o.dpr, 0, 0);
        return o;
      };
      o.resize();
      return o;
    },

    rng: function (seed) {
      var s = seed >>> 0 || 1;
      return function () { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 1e6) / 1e6; };
    },
    clamp: function (v, a, b) { return v < a ? a : v > b ? b : v; },
    lerp: function (a, b, t) { return a + (b - a) * t; },
    seg: function (q, a, b) { return OHX.clamp((q - a) / (b - a), 0, 1); },
    ease: function (t) { return 1 - Math.pow(1 - t, 3); },
    rgba: function (hex, a) {
      var h = hex.replace('#', '');
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      var n = parseInt(h, 16);
      return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
    }
  };

  function safe(name, fn) {
    try { fn(); } catch (e) { console.error('[fx] ' + name + ' failed:', e); }
  }

  /* ---- animation loop ---- */
  var loops = [];
  var running = false;
  var last = 0;
  function frame(t) {
    var dt = last ? Math.min(64, t - last) : 16;
    last = t;
    var any = false;
    for (var i = 0; i < loops.length; i++) {
      var l = loops[i];
      if (document.hidden || !l.active()) continue;
      any = true;
      try { l.fn(t, dt); } catch (e) { console.error('[fx] loop failed:', e); loops.splice(i--, 1); }
    }
    if (any) requestAnimationFrame(frame); else { running = false; last = 0; }
  }
  function kick() { if (!running) { running = true; requestAnimationFrame(frame); } }
  addEventListener('scroll', kick, { passive: true });
  addEventListener('resize', kick);
  document.addEventListener('visibilitychange', kick);
  OHX.kick = kick;

  /* ---- page lifecycle: app.js sets body[data-page]; we follow it ---- */
  function pageChanged() {
    var id = OHX.page();
    if (id === currentPage) return;
    currentPage = id;
    root.dataset.modality = OHX.modality(id).key;
    pageListeners.forEach(function (fn) { safe('onPage', function () { fn(id); }); });
    if (ScrollTrigger) requestAnimationFrame(function () { ScrollTrigger.refresh(); });
    kick();
  }

  reducedQuery.addEventListener('change', function (e) { OHX.reduced = e.matches; root.classList.toggle('fx-reduced', e.matches); });
  fineQuery.addEventListener('change', function (e) { OHX.fine = e.matches; });

  window.OHX = OHX;

  function start() {
    if (started) return;
    started = true;
    root.classList.add('fx');
    root.classList.toggle('fx-reduced', OHX.reduced);
    OHX.palette = readPalette();
    modules.forEach(function (m) { safe(m.name, function () { m.fn(OHX); }); });
    new MutationObserver(pageChanged).observe(document.body, { attributes: true, attributeFilter: ['data-page'] });
    pageChanged();
    var refresh = function () { if (ScrollTrigger) ScrollTrigger.refresh(); kick(); };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(refresh);
    addEventListener('load', refresh);
  }

  // Modules are deferred scripts after this one. DOMContentLoaded fires only after every
  // deferred script has run, so all of them have registered by then.
  if (document.readyState === 'complete') start();
  else document.addEventListener('DOMContentLoaded', start);
})();
