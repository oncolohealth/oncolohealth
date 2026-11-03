/* OncoloHealth effects: Open source and Support pages.
   Tabs that swap real content, copy buttons, a one-time type-on terminal, a magnifying
   lens over the public imaging examples, an ultrasound sector in the support hero, and
   rails scrubbed by each element's natural progress through the viewport.
   Native scrolling only: nothing here pins, snaps or intercepts the wheel. */
(function () {
  'use strict';

  OHX.register('pages', function (fx) {
    var osPage = fx.pageEl('open-source');
    var spPage = fx.pageEl('support');
    if (!osPage && !spPage) return;

    function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    function q(sel, root) { return (root || document).querySelector(sel); }

    /* ------------------------------------------------------------------
       Shared: accessible tabs. opts.swap(newPanel, oldPanel) replaces the
       default show/hide; opts.shared means every tab controls one panel.
       ------------------------------------------------------------------ */
    function tabs(list, opts) {
      opts = opts || {};
      var buttons = qa('[role="tab"]', list);
      var current = buttons.filter(function (b) { return b.getAttribute('aria-selected') === 'true'; })[0] || buttons[0];
      function panelOf(b) { return document.getElementById(b.getAttribute('aria-controls')); }
      function select(btn, focus) {
        if (!btn) return;
        if (focus) btn.focus();
        if (btn === current) return;
        var prev = current;
        current = btn;
        buttons.forEach(function (b) {
          var on = b === btn;
          b.setAttribute('aria-selected', String(on));
          b.tabIndex = on ? 0 : -1;
        });
        if (opts.swap) opts.swap(panelOf(btn), panelOf(prev), btn);
        else if (!opts.shared) {
          buttons.forEach(function (b) { var p = panelOf(b); if (p) p.hidden = b !== btn; });
        }
        if (opts.onSelect) opts.onSelect(btn, prev);
      }
      // Arrow, Home and End keys are handled for every [role="tablist"] by app.js,
      // which focuses and clicks the next tab; the click lands here.
      buttons.forEach(function (b) {
        b.addEventListener('click', function () { select(b, false); });
      });
      return { select: select, current: function () { return current; }, panel: function () { return panelOf(current); } };
    }

    /* Shared: clipboard with a select-the-text fallback. */
    function copy(text, btn, status, node) {
      var labelEl = q('[data-copy-label]', btn) || btn;
      function fallback() {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed'; ta.style.top = '-1000px'; ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        ta.remove();
        return ok;
      }
      function done(ok) {
        if (!ok && node) {
          try {
            var range = document.createRange(); range.selectNodeContents(node);
            var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
          } catch (err) { /* nothing more to do */ }
        }
        labelEl.textContent = ok ? 'Copied' : 'Selected';
        btn.classList.toggle('is-copied', ok);
        if (status) status.textContent = ok ? 'Copied to the clipboard' : 'Copy unavailable; the text is selected';
        clearTimeout(btn._ohxT);
        btn._ohxT = setTimeout(function () {
          labelEl.textContent = 'Copy';
          btn.classList.remove('is-copied');
          if (status) status.textContent = '';
        }, 1800);
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback()); });
      } else done(fallback());
    }

    /* Shared: scroll-scrubbed updates, batched into one frame and run for the shown page only. */
    var scrubbers = [];
    var pending = false;
    var stale = true;
    function runScrub() {
      pending = false;
      var id = fx.page();
      var mine = scrubbers.filter(function (s) { return s.page === id; });
      if (!mine.length) return;
      if (stale) { stale = false; mine.forEach(function (s) { if (s.measure) s.measure(); }); }
      mine.forEach(function (s) { s.fn(); });
    }
    function requestScrub() { if (!pending) { pending = true; requestAnimationFrame(runScrub); } }
    addEventListener('scroll', requestScrub, { passive: true });
    addEventListener('resize', function () { stale = true; requestScrub(); });
    var narrowQuery = matchMedia('(max-width: 900px)');

    /* ==================================================================
       OPEN SOURCE
       ================================================================== */
    if (osPage) {
      /* Reveal the "what is open" columns once, staggered. */
      qa('[data-os-reveal]', osPage).forEach(function (el, i) {
        if (fx.reduced) return;
        el.classList.add('is-armed');
        el.style.transitionDelay = (i * 90) + 'ms';
        fx.once(el, function () { el.classList.add('is-in'); }, 0.15);
      });

      /* Repository explorer: each folder button swaps the panel and re-registers it. */
      var tree = q('[data-os-tree]', osPage);
      if (tree) {
        // The package folder expands to show its modules while it or one of them is selected.
        var pkgBtn = q('#os-t-package', tree);
        var syncOpen = function (btn) {
          var open = btn === pkgBtn || btn.classList.contains('os-child');
          tree.classList.add('is-collapsible');
          tree.classList.toggle('is-open', open);
        };
        syncOpen(q('[aria-selected="true"]', tree) || pkgBtn);
        tabs(tree, {
          onSelect: function (btn) {
            syncOpen(btn);
            // A module tab that was collapsed when app.js tried to focus it can take focus now.
            if (tree.contains(document.activeElement) && document.activeElement !== btn) btn.focus();
            if (fx.reduced) return;
            var panel = document.getElementById(btn.getAttribute('aria-controls'));
            if (!panel) return;
            // CSS animations restart whenever a panel goes from display:none to shown,
            // so the class only needs to be present; no reflow is forced.
            panel.classList.add('os-enter');
          }
        });
      }

      /* Quick start: tabs, copy, and a one-time type-on of the first snippet. */
      var snippetList = q('[data-os-snippets]', osPage);
      var copyBtn = q('[data-os-copy]', osPage);
      var copyStatus = q('[data-os-copy-status]', osPage);
      var typer = null;
      if (snippetList) {
        var snippets = tabs(snippetList, {
          onSelect: function () { if (typer) typer.finish(); }
        });
        if (copyBtn) copyBtn.addEventListener('click', function () {
          if (typer) typer.finish();
          var pre = snippets.panel();
          var text = qa('.os-l', pre).filter(function (l) { return !l.classList.contains('os-c'); }).map(function (l) {
            var c = l.cloneNode(true);
            qa('.os-p', c).forEach(function (p) { p.remove(); });
            return c.textContent;
          }).join('\n');
          copy(text, copyBtn, copyStatus, pre);
        });

        var firstCode = q('#os-c-app code', osPage);
        var term = q('.os-term', osPage);
        if (firstCode && term && !fx.reduced) {
          fx.once(term, function () { typer = typeOn(firstCode); }, 0.35);
        }
      }

      function typeOn(code) {
        var walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT, null);
        var nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        var full = nodes.map(function (n) { return n.nodeValue; });
        var instant = nodes.map(function (n) { return !!(n.parentNode.closest('.os-p') || n.parentNode.closest('.os-c') || !n.parentNode.closest('.os-l')); });
        var cursor = document.createElement('span');
        cursor.className = 'os-cursor';
        cursor.setAttribute('aria-hidden', 'true');
        var ni = 0, ci = 0, timer = 0, finished = false;
        nodes.forEach(function (n, i) { if (n.parentNode.closest('.os-l')) n.nodeValue = ''; else full[i] = n.nodeValue; });
        code.setAttribute('aria-busy', 'true');
        function lineOf(n) { return n.parentNode.closest('.os-l'); }
        function place(n) { var l = lineOf(n); if (l) l.appendChild(cursor); }
        function finish() {
          if (finished) return;
          finished = true;
          clearTimeout(timer);
          nodes.forEach(function (n, i) { n.nodeValue = full[i]; });
          cursor.remove();
          code.removeAttribute('aria-busy');
        }
        function step() {
          if (finished) return;
          if (!fx.isLive(code)) { finish(); return; }
          if (ni >= nodes.length) { finished = true; code.removeAttribute('aria-busy'); setTimeout(function () { cursor.remove(); }, 2400); return; }
          var n = nodes[ni];
          if (instant[ni]) {
            n.nodeValue = full[ni];
            place(n);
            ni++; ci = 0;
            timer = setTimeout(step, 70);
            return;
          }
          ci++;
          n.nodeValue = full[ni].slice(0, ci);
          place(n);
          if (ci >= full[ni].length) {
            var endsLine = !nodes[ni + 1] || lineOf(nodes[ni + 1]) !== lineOf(n);
            ni++; ci = 0;
            timer = setTimeout(step, endsLine ? 300 : 20);
            return;
          }
          timer = setTimeout(step, 14 + Math.random() * 20);
        }
        timer = setTimeout(step, 250);
        return { finish: finish };
      }

      initZoom();

      /* Contribute: the rail fills with the list's natural progress; steps light as it passes. */
      var steps = q('[data-os-steps]', osPage);
      if (steps) {
        var items = qa('li', steps);
        // Item offsets are measured once per layout, so a scroll frame reads a single rect.
        var stepOffsets = [];
        var measureSteps = function () { stepOffsets = items.map(function (li) { return li.offsetTop; }); };
        scrubbers.push({ page: 'open-source', measure: measureSteps, fn: function () {
          if (!fx.isLive(steps)) return;
          var line = innerHeight * 0.68;
          var r = steps.getBoundingClientRect();
          var fill = fx.reduced ? 1 : fx.clamp((line - r.top) / Math.max(1, r.height), 0, 1);
          steps.style.setProperty('--fill', fill.toFixed(4));
          items.forEach(function (li, i) {
            li.classList.toggle('is-lit', fx.reduced || r.top + (stepOffsets[i] || 0) < line);
          });
        } });
      }
    }

    /* Deep zoom: a lens over the public imaging examples. */
    function initZoom() {
      var scope = q('[data-os-scope]', osPage);
      if (!scope) return;
      var img = q('.os-scope-img', scope);
      var lens = q('.os-lens', scope);
      var lensRead = q('.os-lens-read', scope);
      var posEl = q('[data-os-zoom-pos]', osPage);
      var srcEl = q('[data-os-zoom-source]', osPage);
      var licEl = q('[data-os-zoom-licence]', osPage);
      var hudEl = q('[data-os-zoom-label]', osPage);
      var zoomTabs = q('[data-os-zoom-tabs]', osPage);
      var DATA = {
        lung: { file: 'scan-lung.webp', label: 'LUNG CT', source: 'LUNA16 / LIDC-IDRI', licence: 'CC BY 3.0', alt: 'Lung CT research example with a candidate marker from LIDC-IDRI' },
        bone: { file: 'scan-bone.webp', label: 'BONE X-RAY', source: 'BTXRD', licence: 'CC BY 4.0', alt: 'Bone X-ray research example from the BTXRD dataset' },
        mammo: { file: 'scan-mammo.webp', label: 'MAMMOGRAPHY', source: 'CBIS-DDSM', licence: 'CC BY 3.0', alt: 'Mammography research example with an outline from CBIS-DDSM' },
        brain: { file: 'scan-brain.webp', label: 'BRAIN MRI', source: 'Medical Segmentation Decathlon, Task01', licence: 'CC BY-SA 4.0', alt: 'Brain MRI research example with segmentation overlay from the Medical Segmentation Decathlon' }
      };
      var MAG = 2.5;
      var W = 0, H = 0, D = 0;
      var pos = { x: 0, y: 0 }, target = { x: 0, y: 0 };
      var moving = false, rate = 0.22, dragging = false, lastRead = '';

      if (!fx.fine) scope.classList.add('is-touch');

      // The magnified copy is an image inside a round clip, moved with transforms only.
      var lensImg = q('.os-lens-img', lens);
      if (!lensImg) { lensImg = document.createElement('img'); lensImg.className = 'os-lens-img'; lensImg.alt = ''; lensImg.src = img.getAttribute('src'); }
      var clip = document.createElement('div');
      clip.className = 'os-lens-clip';
      clip.appendChild(lensImg);
      lens.insertBefore(clip, lens.firstChild);

      function setImage(key) {
        var d = DATA[key];
        if (!d) return;
        img.src = d.file;
        img.alt = d.alt;
        lensImg.src = d.file;
        if (srcEl) srcEl.textContent = d.source;
        if (licEl) licEl.textContent = d.licence;
        if (hudEl) hudEl.textContent = d.label;
        draw();
      }

      function measure() {
        if (!fx.isLive(scope)) return;
        var r = scope.getBoundingClientRect();
        if (!r.width) return;
        var oldW = W, oldH = H;
        W = r.width; H = r.height;
        D = lens.offsetWidth || 180;
        lensImg.style.width = (W * MAG).toFixed(1) + 'px';
        lensImg.style.height = (H * MAG).toFixed(1) + 'px';
        if (!oldW) { pos.x = target.x = W * 0.5; pos.y = target.y = H * 0.46; }
        else if (oldW !== W) {
          pos.x *= W / oldW; pos.y *= H / oldH; target.x *= W / oldW; target.y *= H / oldH;
        }
        draw();
      }

      function draw() {
        if (!W) return;
        lens.style.transform = 'translate3d(' + pos.x.toFixed(1) + 'px,' + pos.y.toFixed(1) + 'px,0)';
        lensImg.style.transform = 'translate3d(' + (D / 2 - pos.x * MAG).toFixed(1) + 'px,' + (D / 2 - pos.y * MAG).toFixed(1) + 'px,0)';
        var flip = pos.y > H - D / 2 - 44;
        if (flip !== lens._flip) { lens._flip = flip; lens.classList.toggle('is-flip', flip); }
        var nw = img.naturalWidth || 781, nh = img.naturalHeight || 781;
        var s = MAG + '× · x ' + Math.round(pos.x / W * nw) + ' · y ' + Math.round(pos.y / H * nh);
        if (s !== lastRead) {
          lastRead = s;
          if (posEl) posEl.textContent = s;
          if (lensRead) lensRead.textContent = s;
        }
      }

      fx.loop(function () {
        var dx = target.x - pos.x, dy = target.y - pos.y;
        if (Math.abs(dx) < 0.2 && Math.abs(dy) < 0.2) { pos.x = target.x; pos.y = target.y; moving = false; }
        else { pos.x += dx * rate; pos.y += dy * rate; }
        draw();
      }, function () { return moving && fx.isLive(scope); });

      function setTarget(x, y) {
        if (!W) measure();
        target.x = fx.clamp(x, 0, W); target.y = fx.clamp(y, 0, H);
        if (fx.reduced) { pos.x = target.x; pos.y = target.y; draw(); return; }
        moving = true;
        fx.kick();
      }
      function local(e) { var r = scope.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }

      scope.addEventListener('pointermove', function (e) {
        if (e.pointerType === 'touch' && !dragging) return;
        var p = local(e);
        rate = e.pointerType === 'mouse' ? 0.24 : 0.4;
        setTarget(p.x, p.y);
      });
      scope.addEventListener('pointerdown', function (e) {
        var p = local(e);
        if (e.pointerType === 'touch') {
          rate = 0.2;
          if (e.target === lens || lens.contains(e.target)) {
            dragging = true;
            try { scope.setPointerCapture(e.pointerId); } catch (err) { /* capture unsupported */ }
          }
        }
        setTarget(p.x, p.y);
      });
      function endDrag() { dragging = false; }
      scope.addEventListener('pointerup', endDrag);
      scope.addEventListener('pointercancel', endDrag);
      scope.addEventListener('keydown', function (e) {
        var step = e.shiftKey ? 60 : 20, dx = 0, dy = 0;
        if (e.key === 'ArrowLeft') dx = -step;
        else if (e.key === 'ArrowRight') dx = step;
        else if (e.key === 'ArrowUp') dy = -step;
        else if (e.key === 'ArrowDown') dy = step;
        else return;
        e.preventDefault();
        rate = 0.3;
        setTarget(target.x + dx, target.y + dy);
      });

      if (zoomTabs) {
        tabs(zoomTabs, {
          shared: true,
          onSelect: function (btn) {
            scope.setAttribute('aria-labelledby', btn.id);
            setImage(btn.getAttribute('data-os-zoom'));
          }
        });
        // Warm the other examples so switching is instant.
        Object.keys(DATA).forEach(function (k) { var i = new Image(); i.src = DATA[k].file; });
      }
      img.addEventListener('load', draw);

      if (window.ResizeObserver) new ResizeObserver(function () { measure(); }).observe(scope);
      fx.onPage(function (id) { if (id === 'open-source') requestAnimationFrame(function () { measure(); requestScrub(); }); });

      // Acquisition: the field settles in scale and exposure with the frame's natural
      // progress through the viewport (transform and opacity only, one rect read).
      var lastK = -1;
      scrubbers.push({ page: 'open-source', fn: function () {
        if (!fx.isLive(scope)) return;
        var k = fx.reduced ? 1 : fx.ease(fx.seg(fx.progress(scope), 0.04, 0.32));
        if (Math.abs(k - lastK) < 0.002) return;
        lastK = k;
        img.style.opacity = k >= 1 ? '' : (0.35 + 0.65 * k).toFixed(3);
        img.style.transform = k >= 1 ? '' : 'scale(' + (1 + (1 - k) * 0.06).toFixed(4) + ')';
      } });
    }

    /* ==================================================================
       SUPPORT
       ================================================================== */
    if (spPage) {
      /* Audience switch: research <-> commercial & partners. */
      var sw = q('[data-sp-switch]', spPage);
      var stage = q('[data-sp-stage]', spPage);
      if (sw && stage) {
        // Both panels share one grid cell, so the stage keeps a stable height and the
        // switch is a cross-fade (opacity and transform only). The inactive panel is
        // inert and visibility:hidden, so it leaves the tab order and accessibility tree.
        var spPanels = qa('[data-sp-panel]', stage);
        stage.classList.add('is-stacked');
        spPanels.forEach(function (p) {
          var on = !p.hidden;
          p.hidden = false;
          p.classList.toggle('is-off', !on);
          if (on) p.removeAttribute('inert'); else p.setAttribute('inert', '');
        });
        tabs(sw, {
          swap: function (newP, oldP, btn) {
            spPage.setAttribute('data-sp-audience', btn.getAttribute('data-sp-tab'));
            oldP.classList.add('is-off');
            oldP.setAttribute('inert', '');
            newP.classList.remove('is-off');
            newP.removeAttribute('inert');
          }
        });
      }

      /* "Cite the work" jumps to the citation block on this page. */
      qa('[data-sp-jump]', spPage).forEach(function (b) {
        b.addEventListener('click', function () {
          var t = document.getElementById(b.getAttribute('data-sp-jump'));
          if (!t) return;
          t.scrollIntoView({ behavior: fx.reduced ? 'auto' : 'smooth', block: 'start' });
          var h = q('h2', t);
          if (h) h.focus({ preventScroll: true });
        });
      });

      /* Citation: format tabs and copy. */
      var citeTabs = q('[data-sp-cite-tabs]', spPage);
      var citeCopy = q('[data-sp-copy]', spPage);
      if (citeTabs && citeCopy) {
        var cite = tabs(citeTabs);
        citeCopy.addEventListener('click', function () {
          var pre = cite.panel();
          var lines = qa('.sp-l', pre);
          var text = lines.length ? lines.map(function (l) { return l.textContent; }).join('\n') : pre.textContent.trim();
          copy(text, citeCopy, q('[data-sp-copy-status]', spPage), pre);
        });
      }

      /* Roadmap: the rail fills with natural progress and items acquire in order. */
      var lanes = q('[data-sp-lanes]', spPage);
      if (lanes) {
        var laneItems = qa('li', lanes);
        if (!fx.reduced) lanes.classList.add('is-armed');
        var laneOffsets = [];
        var measureLanes = function () {
          var top = lanes.getBoundingClientRect().top;
          laneOffsets = laneItems.map(function (li) { return li.getBoundingClientRect().top - top; });
        };
        scrubbers.push({ page: 'support', measure: measureLanes, fn: function () {
          if (!fx.isLive(lanes)) return;
          if (fx.reduced) { lanes.style.setProperty('--fill', '1'); return; }
          var vh = innerHeight, fill;
          if (narrowQuery.matches) {
            var line = vh * 0.72, r = lanes.getBoundingClientRect();
            fill = fx.clamp((line - r.top) / Math.max(1, r.height), 0, 1);
            laneItems.forEach(function (li, i) { li.classList.toggle('is-lit', r.top + (laneOffsets[i] || 0) < line); });
          } else {
            fill = fx.seg(fx.progress(lanes), 0.12, 0.5);
            var n = laneItems.length;
            laneItems.forEach(function (li, i) { li.classList.toggle('is-lit', fill >= (i + 0.5) / n || fill >= 0.999); });
          }
          lanes.style.setProperty('--fill', fill.toFixed(4));
        } });
      }

      initFan();
    }

    /* Ultrasound sector: peach speckle on navy, a sweeping beam whose tint follows the audience. */
    function initFan() {
      var host = q('[data-sp-fan]', spPage);
      if (!host) return;
      var cv = null, g = null, base = null, bright = null, visible = false;
      var t0 = performance.now(), PERIOD = 7.5;
      var BEAM = { research: [241, 213, 197], partners: [178, 202, 228] };
      var beam = BEAM.research.slice();

      function hexRgb(h) { var n = parseInt(h.replace('#', ''), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
      function rgba(c, a) { return 'rgba(' + Math.round(c[0]) + ',' + Math.round(c[1]) + ',' + Math.round(c[2]) + ',' + a + ')'; }
      function hash(i, j) {
        var h = (Math.imul(i, 374761393) + Math.imul(j, 668265263)) | 0;
        h = Math.imul(h ^ (h >>> 13), 1274126177);
        h ^= h >>> 16;
        return (h >>> 0) / 4294967295;
      }
      function vnoise(u, v) {
        var i = Math.floor(u), j = Math.floor(v), fu = u - i, fv = v - j;
        fu = fu * fu * (3 - 2 * fu); fv = fv * fv * (3 - 2 * fv);
        var a = hash(i, j), b = hash(i + 1, j), c = hash(i, j + 1), d = hash(i + 1, j + 1);
        return a + (b - a) * fu + (c - a) * fv + (a - b - c + d) * fu * fv;
      }
      function smooth(e0, e1, x) { var t = fx.clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); }

      function build() {
        if (!fx.isLive(host)) return false;
        if (!cv) cv = fx.canvas(host);
        cv.resize();
        var cw = cv.w, ch = cv.h, dpr = cv.dpr;
        if (cw < 40 || ch < 40) return false;
        var ink = hexRgb(fx.palette.peachLight || '#eac3b6');
        var line = hexRgb('#c5d3d5');
        var half = 0.62, ax = cw * 0.5, ay = -ch * 0.04;
        var r1 = Math.min(ch * 0.98 - ay, (cw * 0.49) / Math.sin(half)), r0 = r1 * 0.12;
        g = { cw: cw, ch: ch, ax: ax, ay: ay, r0: r0, r1: r1, half: half, dpr: dpr };

        var tex = document.createElement('canvas'); tex.width = cw; tex.height = ch;
        var tctx = tex.getContext('2d');
        var imgB = tctx.createImageData(cw, ch), imgH = tctx.createImageData(cw, ch);
        var dB = imgB.data, dH = imgH.data, span = r1 - r0;
        var lr = r0 + span * 0.52, lt = 0.2, lrad = span * 0.085;
        var lx = ax + Math.sin(lt) * lr, ly = ay + Math.cos(lt) * lr;
        for (var y = 0; y < ch; y++) {
          for (var x = 0; x < cw; x++) {
            var dx = x - ax, dy = y - ay, r = Math.sqrt(dx * dx + dy * dy);
            if (r < r0 || r > r1) continue;
            var th = Math.atan2(dx, dy), ath = Math.abs(th);
            if (ath > half) continue;
            var n = 0.62 * vnoise(r / 1.7, (th * r) / 4.6) + 0.38 * vnoise(r / 1.7 * 2.1 + 17.3, (th * r) / 4.6 * 2.1 + 5.1);
            var speck = Math.pow(n, 2.4) * 1.9;
            var depth = (r - r0) / span;
            var iface = Math.pow(0.5 + 0.5 * Math.sin(depth * 23 + 1.6 * Math.sin(th * 3.1 + 0.7)), 10);
            var layer = 0.55 + 0.45 * vnoise(r / 40, th * 6);
            var ldx = (x - lx) / lrad, ldy = (y - ly) / (lrad * 0.82), ld = Math.sqrt(ldx * ldx + ldy * ldy);
            var lesion = ld < 1 ? 0.18 + 0.2 * ld : (ld < 1.18 ? 1.6 : 1);
            if (ld >= 1.18 && y > ly && Math.abs(x - lx) < lrad * 0.9) lesion *= 1.18;
            var att = 0.32 + 0.68 * Math.exp(-depth * 1.25);
            var near = depth < 0.05 ? 1.5 - depth * 10 : 1;
            var edge = smooth(half, half - 0.05, ath) * smooth(r1, r1 - span * 0.05, r) * smooth(r0, r0 + 3, r);
            var val = Math.min(1, (speck * layer + iface * 0.7 * n) * att * lesion * near * edge);
            var k = (y * cw + x) * 4;
            dB[k] = dH[k] = ink[0]; dB[k + 1] = dH[k + 1] = ink[1]; dB[k + 2] = dH[k + 2] = ink[2];
            dB[k + 3] = Math.round(val * 0.3 * 255);
            dH[k + 3] = Math.round(Math.min(1, val * 0.85 + 0.04 * edge) * 255);
          }
        }
        tctx.putImageData(imgH, 0, 0);
        bright = tex;
        var btex = document.createElement('canvas'); btex.width = cw; btex.height = ch;
        btex.getContext('2d').putImageData(imgB, 0, 0);

        base = document.createElement('canvas');
        base.width = cv.canvas.width; base.height = cv.canvas.height;
        var b = base.getContext('2d');
        b.setTransform(dpr, 0, 0, dpr, 0, 0);
        b.drawImage(btex, 0, 0, cw, ch);
        var phiL = Math.PI / 2 + half, phiR = Math.PI / 2 - half;
        b.lineWidth = 1;
        b.strokeStyle = rgba(line, 0.32);
        b.beginPath();
        b.arc(ax, ay, r0, phiR, phiL);
        b.lineTo(ax + Math.cos(phiL) * r1, ay + Math.sin(phiL) * r1);
        b.arc(ax, ay, r1, phiL, phiR, true);
        b.closePath();
        b.stroke();
        b.setLineDash([2, 6]);
        b.strokeStyle = rgba(line, 0.12);
        for (var qd = 1; qd < 8; qd++) { b.beginPath(); b.arc(ax, ay, r0 + span * (qd / 8), phiR, phiL); b.stroke(); }
        b.setLineDash([]);
        b.strokeStyle = rgba(line, 0.4);
        b.fillStyle = rgba(line, 0.6);
        b.font = '10px "DM Mono", ui-monospace, monospace';
        b.textBaseline = 'middle';
        for (var s = 0; s <= 16; s++) {
          var rt = r0 + span * (s / 16), ex = ax + Math.cos(phiR) * rt, ey = ay + Math.sin(phiR) * rt;
          var len = s % 4 === 0 ? 8 : 4;
          b.beginPath(); b.moveTo(ex + 4, ey); b.lineTo(ex + 4 + len, ey); b.stroke();
          if (s % 4 === 0 && s > 0 && ex + 26 < cw) b.fillText(String(s), ex + 15, ey);
        }
        return true;
      }

      function angleAt(t) { return g.half * 0.92 * Math.sin((t / PERIOD) * Math.PI * 2); }
      function wedge(c, a1, a2) {
        var lo = Math.min(a1, a2) - 0.004, hi = Math.max(a1, a2) + 0.004;
        c.beginPath(); c.moveTo(g.ax, g.ay);
        c.arc(g.ax, g.ay, g.r1 + 2, Math.PI / 2 - hi, Math.PI / 2 - lo);
        c.closePath();
      }
      function draw(t) {
        if (!g || !cv) return;
        var c = cv.ctx;
        var want = BEAM[spPage.getAttribute('data-sp-audience')] || BEAM.research;
        for (var i = 0; i < 3; i++) beam[i] += (want[i] - beam[i]) * 0.06;
        c.setTransform(1, 0, 0, 1, 0, 0);
        c.clearRect(0, 0, cv.canvas.width, cv.canvas.height);
        c.drawImage(base, 0, 0);
        c.setTransform(g.dpr, 0, 0, g.dpr, 0, 0);
        var BANDS = 7, DT = 0.11;
        for (var j = BANDS - 1; j >= 0; j--) {
          var f = 1 - j / BANDS;
          c.save();
          wedge(c, angleAt(t - j * DT), angleAt(t - (j + 1) * DT));
          c.clip();
          c.globalAlpha = f * f * 0.9;
          c.drawImage(bright, 0, 0, g.cw, g.ch);
          c.restore();
        }
        c.globalAlpha = 1;
        var a = angleAt(t);
        var sx = g.ax + Math.sin(a) * g.r0, sy = g.ay + Math.cos(a) * g.r0;
        var ex = g.ax + Math.sin(a) * g.r1, ey = g.ay + Math.cos(a) * g.r1;
        var grad = c.createLinearGradient(sx, sy, ex, ey);
        grad.addColorStop(0, rgba(beam, 0.95));
        grad.addColorStop(0.7, rgba(beam, 0.35));
        grad.addColorStop(1, rgba(beam, 0));
        c.strokeStyle = grad;
        c.lineWidth = 1.25;
        c.beginPath(); c.moveTo(sx, sy); c.lineTo(ex, ey); c.stroke();
      }

      function ensure() {
        if (visible && !g && build()) draw(PERIOD * 0.08);
        fx.kick();
      }
      fx.watch(host, function (vis) { visible = vis; ensure(); }, { rootMargin: '200px 0px' });
      fx.onPage(function (id) { if (id === 'support') requestAnimationFrame(ensure); });
      fx.loop(function (now) { draw((now - t0) / 1000); }, function () {
        return visible && !!g && !fx.reduced && fx.isLive(host);
      });
      var lastW = 0;
      if (window.ResizeObserver) new ResizeObserver(function (entries) {
        var w = Math.round(entries[0].contentRect.width);
        if (!g || !w || Math.abs(w - lastW) < 2) { lastW = w || lastW; return; }
        lastW = w;
        g = null;
        ensure();
      }).observe(host);
      // A reduced-motion switch still redraws the static frame in the new tint.
      if (sw) sw.addEventListener('click', function () {
        if (fx.reduced && g) { var w = BEAM[spPage.getAttribute('data-sp-audience')]; beam = w.slice(); draw(PERIOD * 0.08); }
      });
    }

    fx.onPage(function () { stale = true; requestScrub(); });
    // Panels and FAQ answers change layout below; re-measure the rails after they settle.
    document.addEventListener('toggle', function (e) {
      if (e.target.closest && (e.target.closest('.open-source-page') || e.target.closest('.support-page'))) { stale = true; setTimeout(requestScrub, 420); }
    }, true);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { stale = true; requestScrub(); });
  });
})();
