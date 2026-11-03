/* fx registry: Models page (registry stats, model table, upgrades chart, dated
   project record) and the PET "uptake" hover glow used across editorial rows.
   Native scrolling only: the project record scrolls sideways inside its own
   viewport, and on phones its rail follows the list's natural pass through the
   viewport. Nothing pins, snaps or intercepts the wheel. */
(function () {
  'use strict';

  OHX.register('registry', function (fx) {
    var gsap = fx.gsap;

    var MOD = { xray: 'X-ray', ct: 'CT', mri: 'MRI', mammography: 'Mammography', ultrasound: 'Ultrasound', pathology: 'Pathology', pet: 'PET', dermoscopy: 'Skin imaging', microscopy: 'Microscopy', genomics: 'Genomics', clinical: 'Clinical data', text: 'Language & coordination', photo: 'Photography' };
    var ACCESS = { open: 'Open', gated_auto: 'Gated · automatic approval', gated_manual: 'Gated · manual approval', registration: 'Registration', 'review source': 'Review source', 'model terms apply': 'Model terms apply' };
    var BUCKET_LABEL = { open: 'Open access', gated: 'Registration or gated', review: 'Review source terms' };
    var BUCKET_ORDER = { open: 0, gated: 1, review: 2 };
    var LICENSE = { 'apache-2.0': 'Apache 2.0', mit: 'MIT', 'public-domain': 'Public domain', 'owkin-non-commercial': 'Owkin non-commercial', 'health-ai-developer-foundations': 'HAI-DEF terms', 'cc-by-nc-nd-4.0': 'CC BY-NC-ND 4.0', 'Review source and checkpoint terms': 'Review source terms' };
    var STATE = { cataloged: 'Cataloged', mapped: 'Mapped', 'project coordinator': 'Project coordinator' };
    var STATE_ORDER = { cataloged: 0, 'project coordinator': 1, mapped: 2 };

    function motion() { return !!gsap && !fx.reduced; }
    function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }
    function modLabel(m) { return MOD[m] || cap(m); }
    function bucket(r) { var a = r.access || ''; return a === 'open' ? 'open' : (a === 'registration' || a.indexOf('gated') === 0) ? 'gated' : 'review'; }
    function accessLabel(r) { return ACCESS[r.access] || cap(String(r.access || '').replace(/_/g, ' ')); }
    function licenseLabel(l) { return LICENSE[l] || String(l || '').split(';')[0]; }
    function stateLabel(s) { return STATE[s] || cap(s); }
    function permissionLabel(p) { return cap(String(p || 'unreviewed').replace(/_/g, ' ')); }
    function fmtInt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

    /* Tiny DOM builder: text always goes through textContent, never innerHTML. */
    function h(tag, attrs, kids) {
      var el = document.createElement(tag);
      if (attrs) Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === 'text') el.textContent = v;
        else if (k === 'class') el.className = v;
        else el.setAttribute(k, v === true ? '' : v);
      });
      (kids || []).forEach(function (c) { if (c != null) el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
      return el;
    }

    function sourceLink(r) {
      var m = String(r.citation || '').match(/https?:\/\/[^\s;]+/);
      return m ? m[0] : 'https://github.com/oncolohealth/oncolohealth/blob/main/catalog/models.json';
    }

    /* Simple count-up used only when the shared OHX.countUp is not available. */
    function countFallback(el) {
      var target = parseFloat(el.getAttribute('data-count')) || 0;
      if (!motion()) { el.textContent = fmtInt(target); return; }
      var o = { v: 0 };
      gsap.to(o, { v: target, duration: 1.4, ease: 'power3.out', onUpdate: function () { el.textContent = fmtInt(Math.round(o.v)); } });
    }

    var catalogReady = fetch('catalog.json').then(function (r) { if (!r.ok) throw new Error('catalog ' + r.status); return r.json(); });

    /* ================= PET uptake glow ================= */
    (function glow() {
      // Layout is read once when the pointer enters a target; pointermove only stores
      // coordinates and one rAF per frame writes two custom properties. Page scroll is
      // folded in arithmetically, so nothing measures while the cursor moves.
      var SEL = '.mr-row, .platform-stack article, .research-finding-ledger > div, .catalog-record, .about-record';
      var cur = null, left = 0, top = 0, sy = 0, x = 0, y = 0, raf = 0;
      function write() {
        raf = 0;
        if (!cur) return;
        cur.style.setProperty('--gx', (x - left).toFixed(1) + 'px');
        cur.style.setProperty('--gy', (y - top + (pageYOffset - sy)).toFixed(1) + 'px');
      }
      function queue() { if (!raf && cur) raf = requestAnimationFrame(write); }
      function enter(el) {
        if (cur) cur.classList.remove('fx-glow-on');
        cur = el;
        if (!el) return;
        var r = el.getBoundingClientRect();
        left = r.left; top = r.top; sy = pageYOffset;
        write();
        el.classList.add('fx-glow-on');
      }
      document.addEventListener('pointerover', function (e) {
        if (e.pointerType === 'touch' || !fx.fine) return;
        var el = e.target.closest ? e.target.closest(SEL) : null;
        if (el && !fx.isLive(el)) el = null;
        x = e.clientX; y = e.clientY;
        if (el !== cur) enter(el);
      }, { passive: true });
      document.addEventListener('pointermove', function (e) {
        if (!cur) return;
        x = e.clientX; y = e.clientY;
        queue();
      }, { passive: true });
      document.addEventListener('pointerout', function (e) {
        if (cur && (!e.relatedTarget || !cur.contains(e.relatedTarget))) enter(null);
      }, { passive: true });
      addEventListener('scroll', queue, { passive: true });
      addEventListener('resize', function () { if (cur) enter(cur); });
      addEventListener('blur', function () { enter(null); });
    })();

    var page = fx.pageEl('models');
    if (!page) return;
    var live = function () { return fx.isLive(page); };

    /* ================= registry stats ================= */
    var statsSeen = false;
    function initStats(models) {
      var wrap = page.querySelector('[data-mr-stats]');
      if (!wrap) return;
      var n = models.length;
      var by = function (fn) { var c = {}; models.forEach(function (r) { var k = fn(r); c[k] = (c[k] || 0) + 1; }); return c; };
      var st = by(function (r) { return r.state; });
      var ac = by(bucket);
      var mods = {};
      models.forEach(function (r) { (r.modality || []).forEach(function (m) { mods[m] = (mods[m] || 0) + 1; }); });
      var modKeys = Object.keys(mods).sort(function (a, b) { return mods[b] - mods[a] || modLabel(a).localeCompare(modLabel(b)); });
      var unresolved = models.filter(function (r) { return r.unresolved && r.unresolved.length; }).length;

      function setCount(key, v) {
        var el = wrap.querySelector('[data-mr-stat="' + key + '"]');
        if (!el || String(el.getAttribute('data-count')) === String(v)) return;
        el.setAttribute('data-count', v);
        el.textContent = fmtInt(v);
      }
      setCount('total', n);
      setCount('open', ac.open || 0);
      setCount('modalities', modKeys.length);
      setCount('unresolved', unresolved);
      var of = wrap.querySelector('[data-mr-stat="total-of"]');
      if (of) of.textContent = fmtInt(n);

      function fillSplit(name, parts) {
        var bar = wrap.querySelector('[data-mr-split="' + name + '"]');
        var legend = wrap.querySelector('[data-mr-legend="' + name + '"]');
        if (!bar || !legend) return;
        var bars = bar.querySelectorAll('i'), items = legend.querySelectorAll('li');
        parts.forEach(function (p, i) {
          if (bars[i]) bars[i].style.setProperty('--w', (n ? p[1] / n * 100 : 0).toFixed(2) + '%');
          if (items[i]) { items[i].textContent = ''; items[i].appendChild(h('b', { text: fmtInt(p[1]) })); items[i].appendChild(document.createTextNode(' ' + p[0])); }
        });
      }
      fillSplit('state', [['cataloged', st.cataloged || 0], ['project coordinator', st['project coordinator'] || 0], ['mapped', st.mapped || 0]]);
      fillSplit('access', [['open', ac.open || 0], ['registration or gated', ac.gated || 0], ['review source terms', ac.review || 0]]);
      fillSplit('questions', [['name what still needs checking', unresolved], ['none recorded', n - unresolved]]);

      // Modality coverage: one cell per modality, tinted by how many records list it.
      // Counts overlap (a record can list several), so cells are equal width, not shares.
      var strip = wrap.querySelector('[data-mr-split="mods"]');
      var mlist = wrap.querySelector('[data-mr-legend="mods"]');
      if (strip && mlist) {
        var top = mods[modKeys[0]] || 1;
        strip.textContent = '';
        modKeys.forEach(function (m) {
          var c = h('i', { title: modLabel(m) + ': ' + mods[m] });
          c.style.setProperty('--w', (100 / modKeys.length).toFixed(3) + '%');
          c.style.opacity = (0.28 + 0.72 * mods[m] / top).toFixed(2);
          if (motion() && !statsSeen) gsap.set(c, { scaleX: 0 });
          strip.appendChild(c);
        });
        mlist.textContent = '';
        modKeys.slice(0, 3).forEach(function (m, i) {
          var li = h('li', null, [h('b', { text: fmtInt(mods[m]) }), ' ' + (m === 'ct' || m === 'mri' ? modLabel(m) : modLabel(m).toLowerCase())]);
          if (i === 2 && modKeys.length > 3) li.appendChild(document.createTextNode(', and ' + (modKeys.length - 3) + ' more'));
          mlist.appendChild(li);
        });
      }
    }

    (function statsMotion() {
      var wrap = page.querySelector('[data-mr-stats]');
      if (!wrap) return;
      if (motion()) gsap.set(wrap.querySelectorAll('.mr-split i'), { scaleX: 0 });
      fx.once(wrap, function () {
        statsSeen = true;
        if (typeof fx.countUp !== 'function') wrap.querySelectorAll('[data-count]').forEach(countFallback);
        if (motion()) gsap.to(wrap.querySelectorAll('.mr-split i'), { scaleX: 1, duration: 1.1, ease: 'power3.inOut', stagger: 0.04, clearProps: 'transform' });
      }, 0.25);
    })();

    /* ================= model registry table ================= */
    function initRegistry(models) {
      var body = page.querySelector('#mr-body');
      var tabsHost = page.querySelector('[data-mr-modality]');
      var search = page.querySelector('#mr-search');
      var selAccess = page.querySelector('#mr-access');
      var selLicense = page.querySelector('#mr-license');
      var selState = page.querySelector('#mr-state');
      var reset = page.querySelector('#mr-reset');
      var count = page.querySelector('#mr-count');
      var sorted = page.querySelector('#mr-sorted');
      var empty = page.querySelector('#mr-empty');
      var emptyNote = empty.querySelector('p');
      var table = page.querySelector('.mr-table');
      if (!body || !table) return;

      var state = { mod: 'all', q: '', access: 'all', license: 'all', st: 'all', key: 'name', dir: 1 };
      var SORT_LABEL = { name: 'MODEL', modality: 'MODALITY', access: 'ACCESS', license: 'LICENCE', state: 'STATE' };

      // ---- modality tabs, licence and state options (with counts) ----
      var modCount = {};
      models.forEach(function (r) { (r.modality || []).forEach(function (m) { modCount[m] = (modCount[m] || 0) + 1; }); });
      var modKeys = Object.keys(modCount).sort(function (a, b) { return modCount[b] - modCount[a] || modLabel(a).localeCompare(modLabel(b)); });
      var tabs = [['all', 'All models', models.length]].concat(modKeys.map(function (m) { return [m, modLabel(m), modCount[m]]; })).map(function (t) {
        var b = h('button', { type: 'button', 'data-mod': t[0], 'aria-pressed': t[0] === 'all' ? 'true' : 'false' }, [t[1], h('span', { text: String(t[2]) })]);
        tabsHost.appendChild(b);
        return b;
      });
      tabsHost.addEventListener('click', function (e) {
        var b = e.target.closest('button[data-mod]');
        if (!b) return;
        state.mod = b.getAttribute('data-mod');
        render();
      });

      function fillSelect(sel, values, label) {
        var c = {};
        models.forEach(function (r) { var v = values(r); c[v] = (c[v] || 0) + 1; });
        Object.keys(c).sort(function (a, b) { return c[b] - c[a] || label(a).localeCompare(label(b)); }).forEach(function (v) {
          sel.appendChild(h('option', { value: v, text: label(v) + ' (' + c[v] + ')' }));
        });
      }
      fillSelect(selLicense, function (r) { return r.license; }, licenseLabel);
      fillSelect(selState, function (r) { return r.state; }, stateLabel);

      // ---- rows (built once, reordered on render so open state survives) ----
      var rows = models.map(function (r) {
        var id = 'mr-detail-' + String(r.id).replace(/[^a-z0-9_-]/gi, '-');
        var mods = (r.modality || []).map(modLabel);
        var btn = h('button', { type: 'button', 'aria-expanded': 'false', 'aria-controls': id, text: r.name });
        var tr = h('tr', { class: 'mr-row', role: 'row', 'data-id': r.id }, [
          h('th', { class: 'mr-c-name', role: 'rowheader', scope: 'row', 'data-col': 'name' }, [h('div', { class: 'mr-name' }, [btn, h('small', { text: r.summary })])]),
          h('td', { class: 'mr-c-mod', role: 'cell', 'data-col': 'modality' }, [h('div', { class: 'mr-mods' }, mods.map(function (m) { return h('span', { text: m }); }))]),
          h('td', { class: 'mr-c-access', role: 'cell', 'data-col': 'access' }, [h('span', { class: 'mr-access mr-cell-text', 'data-a': bucket(r), text: accessLabel(r) })]),
          h('td', { class: 'mr-c-license', role: 'cell', 'data-col': 'license' }, [h('span', { class: 'mr-cell-text', text: licenseLabel(r.license) })]),
          h('td', { class: 'mr-c-state', role: 'cell', 'data-col': 'state' }, [h('span', { class: 'mr-state mr-cell-text', 'data-s': r.state, text: stateLabel(r.state) })]),
          h('td', { class: 'mr-toggle', role: 'cell', 'aria-hidden': 'true', text: '+' })
        ]);

        var questions = (r.unresolved || []).length
          ? h('ul', null, r.unresolved.map(function (q) { return h('li', { text: q }); }))
          : h('p', { class: 'mr-none', text: 'No open questions recorded.' });
        var dl = h('dl', null, [
          ['Modalities', mods.join(', ')],
          ['Access', bucket(r) === 'open' ? 'Open access' : accessLabel(r) + ' · ' + BUCKET_LABEL[bucket(r)].toLowerCase()],
          ['Licence', String(r.license || '')],
          ['Permission', permissionLabel(r.permission)],
          ['Record state', stateLabel(r.state)],
          ['Record id', String(r.id), true]
        ].map(function (p) { return h('div', null, [h('dt', { text: p[0] }), h('dd', { class: p[2] ? 'fx-mono' : null, text: p[1] })]); }));
        var detail = h('tr', { class: 'mr-detail', role: 'row', id: id, hidden: true }, [
          h('td', { role: 'cell', colspan: '6' }, [
            h('div', { class: 'mr-detail-clip' }, [h('div', { class: 'mr-detail-body' }, [h('div', { class: 'mr-detail-grid' }, [
              h('div', null, [
                h('h4', { text: 'SUMMARY' }), h('p', { text: r.summary }),
                h('h4', { text: 'OPEN QUESTIONS' }), questions,
                h('h4', { text: 'SOURCE & CITATION' }), h('p', { class: 'mr-cite-text', text: r.citation }),
                h('a', { class: 'mr-cite', href: sourceLink(r), target: '_blank', rel: 'noopener' }, ['Open source', h('span', { 'aria-hidden': 'true', text: '↗' }), h('span', { class: 'mr-visually-hidden', text: ' for ' + r.name + ' (opens in a new tab)' })])
              ]),
              dl
            ])])])
          ])
        ]);
        var hay = [r.name, r.summary, mods.join(' '), r.license, licenseLabel(r.license), r.access, accessLabel(r), r.citation, r.id, stateLabel(r.state)].join(' ').toLowerCase();
        return { r: r, tr: tr, detail: detail, btn: btn, hay: hay, open: false, out: true, anim: null };
      });

      // Detail panel: the row's height opens on a grid-rows track (one row, one layout
      // per frame), then the contents settle in and a peach hairline draws across.
      function toggle(row, open) {
        row.open = open == null ? !row.open : open;
        row.btn.setAttribute('aria-expanded', String(row.open));
        row.tr.classList.toggle('is-open', row.open);
        var d = row.detail;
        clearTimeout(row.timer);
        if (row.open) {
          d.hidden = false;
          if (fx.reduced) { d.classList.add('is-open'); return; }
          void d.offsetHeight;
          d.classList.add('is-open');
        } else {
          d.classList.remove('is-open');
          if (fx.reduced || !live()) { d.hidden = true; return; }
          row.timer = setTimeout(function () { if (!row.open) d.hidden = true; }, 420);
        }
      }
      body.addEventListener('click', function (e) {
        var tr = e.target.closest('tr.mr-row');
        if (!tr || e.target.closest('a')) return;
        if (!e.target.closest('button') && window.getSelection && String(window.getSelection()).length) return;
        var row = rows.filter(function (x) { return x.tr === tr; })[0];
        if (row) toggle(row);
      });

      // Column crosshair: the hovered cell's header lights up (ported from the heatmap probe).
      var heads = table.querySelectorAll('thead th[data-col]');
      body.addEventListener('pointerover', function (e) {
        var cell = e.target.closest('[data-col]');
        var col = cell ? cell.getAttribute('data-col') : null;
        heads.forEach(function (th) { th.classList.toggle('is-col', th.getAttribute('data-col') === col); });
      });
      body.addEventListener('pointerleave', function () { heads.forEach(function (th) { th.classList.remove('is-col'); }); });

      // ---- sorting ----
      function sortValue(row, key) {
        var r = row.r;
        if (key === 'modality') return modLabel((r.modality || [])[0] || '');
        if (key === 'access') return BUCKET_ORDER[bucket(r)];
        if (key === 'license') return licenseLabel(r.license).toLowerCase();
        if (key === 'state') return STATE_ORDER[r.state] != null ? STATE_ORDER[r.state] : 9;
        return String(r.name).toLowerCase();
      }
      table.querySelector('thead').addEventListener('click', function (e) {
        var b = e.target.closest('button[data-sort]');
        if (!b) return;
        var key = b.getAttribute('data-sort');
        if (state.key === key) state.dir = -state.dir; else { state.key = key; state.dir = 1; }
        render();
      });

      // ---- filters ----
      search.addEventListener('input', function () { state.q = search.value.trim().toLowerCase(); render(); });
      selAccess.addEventListener('change', function () { state.access = selAccess.value; render(); });
      selLicense.addEventListener('change', function () { state.license = selLicense.value; render(); });
      selState.addEventListener('change', function () { state.st = selState.value; render(); });
      function doReset() {
        state.mod = 'all'; state.q = ''; state.access = 'all'; state.license = 'all'; state.st = 'all';
        search.value = ''; selAccess.value = 'all'; selLicense.value = 'all'; selState.value = 'all';
        render();
      }
      reset.addEventListener('click', doReset);
      page.querySelectorAll('[data-mr-reset]').forEach(function (b) { b.addEventListener('click', function () { doReset(); search.focus(); }); });

      // ---- render with a FLIP reorder ----
      var first = true, sortSig = '', syncTimer = 0;
      // Sorting sets CSS `order` on the flex tbody (no nodes move, so no boxes are rebuilt);
      // the DOM is brought into the same order when the browser is idle, for assistive tech.
      function syncDom(ordered) {
        var frag = document.createDocumentFragment();
        ordered.forEach(function (row) { frag.appendChild(row.tr); frag.appendChild(row.detail); });
        body.appendChild(frag);
      }
      function render() {
        var ordered = rows.slice().sort(function (a, b) {
          var va = sortValue(a, state.key), vb = sortValue(b, state.key);
          var d = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
          return d * state.dir || String(a.r.name).localeCompare(String(b.r.name));
        });
        var show = ordered.filter(function (row) {
          var r = row.r;
          return (state.mod === 'all' || (r.modality || []).indexOf(state.mod) > -1) &&
            (state.access === 'all' || bucket(r) === state.access) &&
            (state.license === 'all' || r.license === state.license) &&
            (state.st === 'all' || r.state === state.st) &&
            (!state.q || row.hay.indexOf(state.q) > -1);
        });

        // FLIP, transform only, via the Web Animations API (compositor-run, no per-frame JS).
        // Reads are batched before and after the single style change, so layout runs once.
        var animate = motion() && !first && live() && !!document.body.animate;
        var before = {};
        if (animate) rows.forEach(function (row) { if (!row.out) before[row.r.id] = row.tr.getBoundingClientRect().top; });
        rows.forEach(function (row) { if (row.anim) { row.anim.cancel(); row.anim = null; } });

        var showSet = {};
        show.forEach(function (row) { showSet[row.r.id] = true; });
        rows.forEach(function (row) {
          var out = !showSet[row.r.id];
          if (out !== row.out) { row.out = out; row.tr.classList.toggle('is-out', out); row.detail.classList.toggle('is-out', out); }
          row.tr.classList.toggle('is-last', row === show[show.length - 1]);
        });
        var sig = state.key + state.dir;
        if (sig !== sortSig) {
          sortSig = sig;
          ordered.forEach(function (row, i) { row.tr.style.order = 2 * i; row.detail.style.order = 2 * i + 1; });
          if (first) syncDom(ordered);
          else {
            clearTimeout(syncTimer);
            syncTimer = setTimeout(function () {
              if (window.requestIdleCallback) requestIdleCallback(function () { syncDom(ordered); }, { timeout: 1500 });
              else syncDom(ordered);
            }, 500);
          }
        }

        if (animate) {
          var after = show.map(function (row) { return row.tr.getBoundingClientRect().top; });
          var EASE = 'cubic-bezier(.2,.7,.1,1)', n = 0;
          show.forEach(function (row, i) {
            var top = before[row.r.id];
            if (top == null) {
              row.anim = row.tr.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }],
                { duration: 280, delay: Math.min(180, n++ * 14), easing: EASE, fill: 'backwards' });
              return;
            }
            var dy = top - after[i];
            if (Math.abs(dy) > 0.5) row.anim = row.tr.animate([{ transform: 'translateY(' + dy.toFixed(1) + 'px)' }, { transform: 'none' }], { duration: 420, easing: EASE });
          });
        }
        first = false;

        tabs.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-mod') === state.mod)); });
        table.querySelectorAll('thead th[data-col]').forEach(function (th) {
          th.setAttribute('aria-sort', th.getAttribute('data-col') === state.key ? (state.dir > 0 ? 'ascending' : 'descending') : 'none');
        });
        var dirLabel = state.key === 'name' || state.key === 'license' || state.key === 'modality' ? (state.dir > 0 ? 'A–Z' : 'Z–A') : (state.dir > 0 ? 'ASCENDING' : 'DESCENDING');
        sorted.textContent = 'SORTED BY ' + SORT_LABEL[state.key] + ' · ' + dirLabel;
        count.textContent = '';
        count.appendChild(document.createTextNode('Showing '));
        count.appendChild(h('b', { text: String(show.length) }));
        count.appendChild(document.createTextNode(' of ' + rows.length + (rows.length === 1 ? ' model' : ' models')));
        empty.hidden = show.length > 0;
        if (!show.length) {
          var bits = [];
          if (state.q) bits.push('“' + search.value.trim() + '”');
          if (state.mod !== 'all') bits.push(modLabel(state.mod));
          if (state.access !== 'all') bits.push(BUCKET_LABEL[state.access]);
          if (state.license !== 'all') bits.push(licenseLabel(state.license));
          if (state.st !== 'all') bits.push(stateLabel(state.st));
          emptyNote.textContent = 'Nothing matches ' + bits.join(' · ') + '. Remove a filter or reset them all.';
        }
        reset.disabled = !(state.mod !== 'all' || state.q || state.access !== 'all' || state.license !== 'all' || state.st !== 'all');
      }
      render();
    }

    function registryFailed() {
      var body = page.querySelector('#mr-body');
      var count = page.querySelector('#mr-count');
      if (count) count.textContent = 'The model records could not be loaded.';
      if (body) {
        var a = h('a', { class: 'underlink', href: 'https://github.com/oncolohealth/oncolohealth/blob/main/catalog/models.json', target: '_blank', rel: 'noopener' }, ['Read catalog/models.json on GitHub ', h('span', { text: '↗' })]);
        body.appendChild(h('tr', { role: 'row' }, [h('td', { role: 'cell', class: 'mr-empty', colspan: '6' }, [a])]));
      }
    }

    /* ================= upgrades: comparison chart ================= */
    (function initCompare() {
      var host = page.querySelector('[data-mr-compare]');
      if (!host) return;
      var panel = host.querySelector('#mr-cmp-panel');
      var tabs = Array.prototype.slice.call(host.querySelectorAll('[role="tab"]'));
      var DATA = {
        heads: {
          head: ['FROZEN RESNET-50 COMPARISON HEADS', 'ACCURACY / ORIGINAL → COMPARISON'],
          domain: [40, 90], ticks: [40, 50, 60, 70, 80, 90], tick: function (v) { return v + '%'; },
          fmt: function (v) { return v.toFixed(1) + '%'; }, delta: function (d) { return (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1) + ' pts'; },
          metric: 'accuracy', axis: 'ACCURACY · %', unit: 'CHANGE IN POINTS',
          rows: [['Pathology', '7,180 test images', 51.0, 80.8], ['Skin lesion', '2,005 test images', 51.5, 59.2], ['Breast ultrasound', '156 test images', 76.3, 77.6]],
          note: 'Accuracy for the original and comparison heads in the team’s report. For ultrasound, AUROC moved from 0.833 to 0.830 and malignant recall stayed at 66.7%. These test sources had already been examined.',
          link: ['Read the project record', 'https://github.com/oncolohealth/oncolohealth/blob/main/PROGRESS.md']
        },
        crop: {
          head: ['RESNET-50 / PADDING → NATIVE CENTER CROP', 'TEST ROC-AUC / CENTERS 2 + 3'],
          domain: [0.5, 0.8], ticks: [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8], tick: function (v) { return v.toFixed(2); },
          fmt: function (v) { return v.toFixed(3); }, delta: function (d) { return (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(3); },
          metric: 'test ROC-AUC', axis: 'TEST ROC-AUC', unit: 'CHANGE IN AUC',
          rows: [['Benign vs malignant', '522 test images', 0.623, 0.690], ['Three-class', '808 test images · macro', 0.609, 0.637], ['Tumor vs normal', '808 test images', 0.621, 0.623]],
          note: 'Each variant was chosen on center-1 validation data. Centers 2 and 3 had already been examined in the first baseline, and the image-level intervals overlap. Center-1 validation stays higher, at 0.84 to 0.94.',
          link: ['Read the source-shift report', 'https://github.com/oncolohealth/oncolohealth/blob/main/docs/reports/E-btxrd-source-shift.md']
        }
      };
      var current = 'heads', seen = false, tl = null;

      function pos(d, v) { return fx.clamp((v - d.domain[0]) / (d.domain[1] - d.domain[0]), 0, 1) * 100; }

      function build(key) {
        var d = DATA[key];
        panel.textContent = '';
        panel.appendChild(h('div', { class: 'mr-cmp-head' }, [h('span', { text: d.head[0] }), h('span', { text: d.head[1] })]));
        var parts = d.rows.map(function (r) {
          var a = pos(d, r[2]), b = pos(d, r[3]);
          var track = h('div', { class: 'mr-cmp-track', 'aria-hidden': 'true' });
          d.ticks.forEach(function (t) { var g = h('i', { class: 'mr-cmp-grid' }); g.style.left = pos(d, t) + '%'; track.appendChild(g); });
          var bar = h('span', { class: 'mr-cmp-bar' }); bar.style.left = Math.min(a, b) + '%'; bar.style.width = Math.max(0.6, Math.abs(b - a)) + '%';
          var base = h('span', { class: 'mr-cmp-dot is-base' }); base.style.left = a + '%';
          var dot = h('span', { class: 'mr-cmp-dot is-new' }); dot.style.left = b + '%';
          track.appendChild(bar); track.appendChild(base); track.appendChild(dot);
          var val = h('strong', { text: d.fmt(r[3]) });
          var row = h('div', { class: 'mr-cmp-row' }, [
            h('div', { class: 'mr-cmp-label' }, [h('strong', { text: r[0] }), h('small', { text: r[1] })]),
            track,
            h('div', { class: 'mr-cmp-vals', 'aria-hidden': 'true' }, [h('span', { text: d.fmt(r[2]) + ' →' }), val, h('b', { text: d.delta(r[3] - r[2]) })]),
            h('span', { class: 'mr-visually-hidden', text: r[0] + ': ' + d.metric + ' ' + d.fmt(r[2]) + ' to ' + d.fmt(r[3]) + ', ' + r[1] + '.' })
          ]);
          panel.appendChild(row);
          return { r: r, bar: bar, dot: dot, val: val, a: a, b: b };
        });
        var scale = h('div', { class: 'mr-cmp-scale' });
        d.ticks.forEach(function (t) {
          var s = h('span', { class: 'mr-cmp-tick' }, [h('i'), h('b', { text: d.tick(t) })]);
          s.style.left = pos(d, t) + '%';
          scale.appendChild(s);
        });
        var axis = h('div', { class: 'mr-cmp-axis', 'aria-hidden': 'true' }, [h('span', { class: 'mr-cmp-axis-title', text: d.axis }), scale, h('span', { class: 'mr-cmp-axis-unit', text: d.unit })]);
        panel.appendChild(axis);
        panel.appendChild(h('p', { class: 'fine', text: d.note }));
        panel.appendChild(h('a', { class: 'underlink', href: d.link[1], target: '_blank', rel: 'noopener' }, [d.link[0] + ' ', h('span', { 'aria-hidden': 'true', text: '↗' })]));
        return parts;
      }

      function play(parts, key) {
        if (tl) { tl.kill(); tl = null; }
        if (!motion()) return;
        var d = DATA[key];
        tl = gsap.timeline();
        parts.forEach(function (p, i) {
          var o = { v: p.r[2] };
          var t0 = 0.1 + i * 0.12;
          tl.fromTo(p.bar, { scaleX: 0 }, { scaleX: 1, duration: 1.1, ease: 'power3.inOut', clearProps: 'transform' }, t0);
          tl.fromTo(p.dot, { left: p.a + '%' }, { left: p.b + '%', duration: 1.1, ease: 'power3.inOut' }, t0);
          tl.to(o, { v: p.r[3], duration: 1.1, ease: 'power3.inOut', onUpdate: function () { p.val.textContent = d.fmt(o.v); } }, t0);
        });
      }

      function primed(parts) {
        if (!motion()) return;
        parts.forEach(function (p) { gsap.set(p.bar, { scaleX: 0 }); p.dot.style.left = p.a + '%'; p.val.textContent = DATA[current].fmt(p.r[2]); });
      }

      var parts = build(current);
      primed(parts);
      fx.once(host, function () { seen = true; play(parts, current); }, 0.3);

      function select(tab, focus) {
        var key = tab.getAttribute('data-cmp');
        tabs.forEach(function (t) { var on = t === tab; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; });
        panel.setAttribute('aria-labelledby', tab.id);
        if (focus) tab.focus();
        if (key === current) return;
        current = key;
        parts = build(key);
        if (!fx.reduced) { panel.classList.remove('mr-cmp-enter'); void panel.offsetWidth; panel.classList.add('mr-cmp-enter'); }
        if (seen) play(parts, key); else primed(parts);
      }
      tabs.forEach(function (t, i) {
        t.addEventListener('click', function () { select(t, false); });
        t.addEventListener('keydown', function (e) {
          var n = null;
          if (e.key === 'ArrowRight') n = tabs[(i + 1) % tabs.length];
          else if (e.key === 'ArrowLeft') n = tabs[(i - 1 + tabs.length) % tabs.length];
          else if (e.key === 'Home') n = tabs[0];
          else if (e.key === 'End') n = tabs[tabs.length - 1];
          if (!n) return;
          e.preventDefault();
          select(n, true);
        });
      });
    })();

    /* ================= upgrades: dated project record ================= */
    (function initLog() {
      var log = page.querySelector('[data-mr-log]');
      if (!log) return;
      var vp = log.querySelector('[data-mr-log-vp]');
      var content = log.querySelector('.mr-log-content');
      var fill = log.querySelector('[data-mr-log-fill]');
      var frame = log.querySelector('.mr-log-frame');
      var items = Array.prototype.slice.call(log.querySelectorAll('.mr-log-item'));
      var nodes = items.map(function (li) { return li.querySelector('.mr-log-node'); });
      var prev = log.querySelector('[data-mr-log-prev]');
      var next = log.querySelector('[data-mr-log-next]');
      var mobileQ = matchMedia('(max-width: 760px)');
      var armed = false, visible = false;

      // Day markers on the rail: the first milestone of each date carries the day's label.
      var MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
      var DAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
      var perDay = {};
      items.forEach(function (li) { var t = li.querySelector('time'); var k = t && t.getAttribute('datetime'); if (k) perDay[k] = (perDay[k] || 0) + 1; });
      var lastDay = null;
      items.forEach(function (li) {
        var t = li.querySelector('time');
        var k = t && t.getAttribute('datetime');
        if (!k || k === lastDay) return;
        lastDay = k;
        var p = k.split('-'), dt = new Date(+p[0], +p[1] - 1, +p[2]);
        li.classList.add('is-day-start');
        li.appendChild(h('span', { class: 'mr-log-day', 'aria-hidden': 'true' }, [
          h('b', { text: DAYS[dt.getDay()] + ' ' + p[2] + ' ' + MONTHS[dt.getMonth()] }),
          ' · ' + perDay[k] + (perDay[k] === 1 ? ' MILESTONE' : ' MILESTONES')
        ]));
      });

      function light(px, axis) {
        nodes.forEach(function (n, i) {
          var p = axis === 'x' ? items[i].offsetLeft : items[i].offsetTop + 26;
          n.classList.toggle('is-on', p <= px);
        });
      }

      function updateX() {
        if (mobileQ.matches || !live()) return;
        var max = vp.scrollWidth - vp.clientWidth;
        var total = content.offsetWidth || 1;
        var edge = max <= 1 ? total : vp.scrollLeft + vp.clientWidth * 0.85;
        frame.classList.toggle('is-end', vp.scrollLeft >= max - 2);
        prev.disabled = vp.scrollLeft <= 2;
        next.disabled = vp.scrollLeft >= max - 2;
        if (!armed) { fill.style.transform = 'scaleX(0)'; return; }
        fill.style.transform = 'scaleX(' + Math.min(1, edge / total).toFixed(4) + ')';
        light(edge, 'x');
      }

      function updateY() {
        if (!mobileQ.matches) return;
        var r = content.getBoundingClientRect();
        var p = fx.clamp((innerHeight * 0.7 - r.top) / (r.height || 1), 0, 1);
        fill.style.transform = 'scaleY(' + p.toFixed(4) + ')';
        light(p * content.offsetHeight, 'y');
      }

      function mode() {
        fill.style.transform = '';
        log.classList.toggle('is-live', !fx.reduced);
        if (fx.reduced) { nodes.forEach(function (n) { n.classList.add('is-on'); }); fill.style.transform = 'none'; return; }
        if (mobileQ.matches) updateY(); else updateX();
      }

      if (!fx.reduced) { log.classList.add('is-live'); fill.style.transform = mobileQ.matches ? 'scaleY(0)' : 'scaleX(0)'; }
      vp.addEventListener('scroll', updateX, { passive: true });
      addEventListener('resize', function () { if (live()) updateX(); });
      if (mobileQ.addEventListener) mobileQ.addEventListener('change', mode);

      // Phones: the rail follows the list's own pass through the viewport (no pinning).
      fx.watch(log, function (v) { visible = v; if (v) fx.kick(); });
      fx.loop(updateY, function () { return visible && mobileQ.matches && !fx.reduced && live(); });

      fx.once(log, function () { armed = true; mode(); }, 0.25);

      function step() { var a = items[0], b = items[1]; return b ? b.offsetLeft - a.offsetLeft : vp.clientWidth * 0.8; }
      function nudge(dir) { vp.scrollBy({ left: dir * step(), behavior: fx.reduced ? 'auto' : 'smooth' }); }
      prev.addEventListener('click', function () { nudge(-1); });
      next.addEventListener('click', function () { nudge(1); });

      // Drag to scroll with mouse or pen; touch keeps native swiping and the wheel is untouched.
      var drag = null, suppress = false;
      vp.addEventListener('pointerdown', function (e) {
        if (e.pointerType === 'touch' || e.button !== 0 || mobileQ.matches) return;
        if (vp.scrollWidth <= vp.clientWidth + 1) return;
        drag = { id: e.pointerId, x: e.clientX, left: vp.scrollLeft, moved: false };
      });
      vp.addEventListener('pointermove', function (e) {
        if (!drag || e.pointerId !== drag.id) return;
        var dx = e.clientX - drag.x;
        if (!drag.moved && Math.abs(dx) > 4) {
          drag.moved = true;
          vp.classList.add('is-dragging');
          try { vp.setPointerCapture(drag.id); } catch (err) { /* ignore */ }
        }
        if (drag.moved) vp.scrollLeft = drag.left - dx;
      });
      function endDrag(e) {
        if (!drag || (e && e.pointerId !== drag.id)) return;
        suppress = drag.moved;
        try { vp.releasePointerCapture(drag.id); } catch (err) { /* ignore */ }
        drag = null;
        vp.classList.remove('is-dragging');
      }
      vp.addEventListener('pointerup', endDrag);
      vp.addEventListener('pointercancel', endDrag);
      vp.addEventListener('dragstart', function (e) { if (drag) e.preventDefault(); });
      vp.addEventListener('click', function (e) { if (suppress) { e.preventDefault(); e.stopPropagation(); suppress = false; } }, true);

      fx.onPage(function (id) { if (id === 'models') requestAnimationFrame(mode); });
    })();

    catalogReady.then(function (data) {
      var models = (data && data.models) || [];
      initStats(models);
      initRegistry(models);
    }).catch(function (err) {
      console.error('[fx] registry: catalog unavailable', err);
      registryFailed();
    });
  });
})();
