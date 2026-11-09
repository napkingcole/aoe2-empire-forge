/*
 * The tech tree's side panel: click a unit, building or tech to see its stats
 * and edit them.  Shift-click still toggles a node on or off.
 *
 * Edits live in two maps that mirror the draft keys the build reads
 * (civ_overrides._apply_unit_edits / _apply_tech_edits):
 *   unit_edits {unit id: {hp, attack, melee, pierce, range, reload, speed, los,
 *                         train, cost: {food, wood, stone, gold}, bonus: {cls: n}}}
 *   tech_edits {tech id: {cost: {...}, time}}
 * Base values come from /api/builder/node-info (the DAT, Britons template).
 * Like the on/off state, edits are saved to the draft as they are made.
 */
(function () {
    const RES = ['food', 'wood', 'stone', 'gold'];
    const RES_LABEL = { food: 'Food', wood: 'Wood', stone: 'Stone', gold: 'Gold' };
    const SHORT = 32767;

    // field, label, step, min, max, which nodes show it
    const STAT_FIELDS = [
        ['hp',     'Hit points',    1,    1,      SHORT, () => true],
        ['attack', 'Attack',        1,    0,      SHORT, i => i.fights],
        ['melee',  'Melee armour',  1,   -SHORT,  SHORT, () => true],
        ['pierce', 'Pierce armour', 1,   -SHORT,  SHORT, () => true],
        ['range',  'Range',         0.5,  0,      100,   i => i.fights],
        ['reload', 'Reload time',   0.05, 0.1,    100,   i => i.fights],
        ['speed',  'Speed',         0.01, 0,      10,    i => i.moves],
        ['los',    'Line of sight', 1,    0,      100,   () => true],
    ];
    // The game's stat icons (static/icons/properties, as on the review step).
    const STAT_ICON = { hp: 'heart', attack: 'attack', melee: 'armor', pierce: 'pierce_armor',
                        range: 'range', reload: 'reload_time', speed: 'speed', los: 'line_of_sight' };

    let edits = { unit_edits: {}, tech_edits: {}, added_lines: [] };
    let panel = null;
    let current = null;          // { item, element_height }
    const infoCache = {};        // "kind:id" -> node-info response (a promise)
    const unitNames = {};        // unit id -> name, for "From the Knight edit"
    const upgradeOf = {};        // unit id -> upgrade tech id (learned from node-info)
    const stepsCache = {};       // unit id -> /api/builder/tree-steps response (a promise)
    let lastFill = null;         // { body, inf, kind } — what treeChanged() refills

    const clone = o => JSON.parse(JSON.stringify(o || {}));
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    function kindOf(item) {
        return item.use_type === 'Tech' ? 'tech' : item.use_type === 'Building' ? 'building' : 'unit';
    }

    function datQuery() {
        const p = window.getDatPath ? window.getDatPath() : '';
        return p ? `&dat_path=${encodeURIComponent(p)}` : '';
    }

    async function info(kind, id) {
        const key = `${kind}:${id}`;
        if (!infoCache[key]) {
            infoCache[key] = fetch(`/api/builder/node-info?kind=${kind}&id=${id}${datQuery()}`)
                .then(r => r.json())
                .then(r => { if (kind !== 'tech' && r && r.name) unitNames[id] = r.name; return r; })
                .catch(() => ({ status: 'error' }));
        }
        return infoCache[key];
    }

    // ── edit bookkeeping ────────────────────────────────────────────────────
    // An added line's tier is keyed "a<line>.<tier>" and its upgrade
    // "a<line>.<tier>u" (added_lines.py); its edits live on the line itself,
    // so the same panel code edits a tier as it edits a vanilla unit.
    const ADDED_KEY = /^a(\d+)\.(\d+)(u?)$/;
    function addedRef(id) {
        const m = ADDED_KEY.exec(String(id));
        if (!m) return null;
        const line = edits.added_lines.find(l => l.id === +m[1]);
        const tier = line && line.tiers[+m[2]];
        return tier ? { line, n: +m[2], tier, up: !!m[3] } : null;
    }

    function unitEdit(id) {
        const ref = addedRef(id);
        if (ref) return Object.assign({}, ref.tier.edits || {}, ref.tier.name ? { name: ref.tier.name } : {});
        return edits.unit_edits[String(id)] || {};
    }

    // A renamed unit's name (civ_overrides._apply_unit_names), or '' for the
    // game's.  The tree's labels and tooltip read it too (main.js _nodeName).
    // The civ's unique unit (the Castle's UniqueUnit node) is named on its own
    // wizard step; regional units share the node type and can be renamed.
    function canRename(item) {
        return kindOf(item) === 'unit'
            && !(item.node_type === 'UniqueUnit' && /_82$/.test(item.id));
    }
    function nameOf(item) {
        if (item.added) return tierName(item.node_id);
        return canRename(item) ? (unitEdit(item.node_id).name || '') : '';
    }
    function techEdit(id) {
        const ref = addedRef(id);
        if (ref) return ref.tier.upgrade || {};
        return edits.tech_edits[String(id)] || {};
    }

    function setUnitField(id, field, value) {
        const ref = addedRef(id);
        if (ref) {
            if (field === 'name') ref.tier.name = value || '';
            else {
                const e = Object.assign({}, ref.tier.edits);
                if (value === null || value === undefined) delete e[field];
                else e[field] = value;
                if (Object.keys(e).length) ref.tier.edits = e;
                else delete ref.tier.edits;
            }
            return;
        }
        const k = String(id);
        const e = Object.assign({}, edits.unit_edits[k]);
        if (value === null || value === undefined) delete e[field];
        else e[field] = value;
        if (Object.keys(e).length) edits.unit_edits[k] = e;
        else delete edits.unit_edits[k];
    }

    function setTechField(id, field, value) {
        const ref = addedRef(id);
        if (ref) {
            const e = Object.assign({}, ref.tier.upgrade);
            if (value === null || value === undefined) delete e[field];
            else e[field] = value;
            if (Object.keys(e).length) ref.tier.upgrade = e;
            else delete ref.tier.upgrade;
            return;
        }
        const k = String(id);
        const e = Object.assign({}, edits.tech_edits[k]);
        if (value === null || value === undefined) delete e[field];
        else e[field] = value;
        if (Object.keys(e).length) edits.tech_edits[k] = e;
        else delete edits.tech_edits[k];
    }

    // Every unit's ancestors and upgrade tech, loaded once (/api/builder/tree-lines)
    // so a node changed through its line is marked before it is ever opened.
    let lines = { before: {}, upgrade: {} };
    const known = {};            // node id -> [item, element_height], for redecorate()

    function loadLines() {
        const dat = window.getDatPath ? window.getDatPath() : '';
        fetch('/api/builder/tree-lines?dat_path=' + encodeURIComponent(dat))
            .then(r => r.json())
            .then(r => { if (r.status === 'ok') { lines = r; redecorate(); } })
            .catch(() => {});
    }

    // Edited = its own edit, its upgrade tech's, or a cost / train time it
    // inherits from an edited ancestor (the build's _flow_down).
    function isEdited(item) {
        if (item.add) return false;
        if (item.added) {
            const ref = addedRef(item.node_id);
            return !!(ref && (ref.tier.edits || ref.tier.upgrade));
        }
        const kind = kindOf(item);
        if (kind === 'tech') return !!edits.tech_edits[String(item.node_id)];
        if (edits.unit_edits[String(item.node_id)]) return true;
        const up = upgradeOf[item.node_id] ?? lines.upgrade[item.node_id];
        if (up !== undefined && edits.tech_edits[String(up)]) return true;
        return (lines.before[item.node_id] || []).some(a => {
            const e = unitEdit(a);
            return e.cost !== undefined || e.train !== undefined;
        });
    }

    function costEqual(a, b) {
        return RES.every(r => (a[r] || 0) === (b[r] || 0));
    }

    function costText(c) {
        const parts = RES.filter(r => c[r]).map(r => `${c[r]} ${RES_LABEL[r].toLowerCase()}`);
        return parts.length ? parts.join(', ') : 'free';
    }

    // The cost a unit really gets: its own edit, else the latest edited
    // ancestor's (the build's _flow_down), else the game's.
    function effectiveCost(inf) {
        const own = unitEdit(inf.id).cost;
        if (own) return { cost: own, from: null };
        for (const anc of inf.line_before || []) {
            const c = unitEdit(anc).cost;
            if (c) return { cost: c, from: anc };
        }
        return { cost: inf.cost, from: undefined };
    }

    function effectiveTrain(inf) {
        const own = unitEdit(inf.id).train;
        if (own !== undefined) return { train: own, from: null };
        for (const anc of inf.line_before || []) {
            const t = unitEdit(anc).train;
            if (t !== undefined) return { train: t, from: anc };
        }
        return { train: inf.train, from: undefined };
    }

    function clamp(v, lo, hi, step) {
        if (!Number.isFinite(v)) return null;
        v = Math.min(Math.max(v, lo), hi);
        return step >= 1 ? Math.round(v) : Math.round(v * 1000) / 1000;
    }

    // ── tree decoration ─────────────────────────────────────────────────────
    function decorate(item, element_height) {
        known[item.id] = [item, element_height];
        window._ttRelabel?.(item, element_height);
        const id = `${item.id}_edited`;
        document.getElementById(id)?.remove();
        if (!isEdited(item)) return;
        const group = document.getElementById(item.id);
        if (!group) return;
        const ns = 'http://www.w3.org/2000/svg';
        const dot = document.createElementNS(ns, 'circle');
        dot.setAttribute('id', id);
        dot.setAttribute('class', 'tt-edited-dot');
        dot.setAttribute('cx', item.x + element_height - 7);
        dot.setAttribute('cy', item.y + 7);
        dot.setAttribute('r', 5);
        // Below the overlay, so clicks still reach the node.
        const overlay = document.getElementById(`${item.id}_overlay`);
        group.insertBefore(dot, overlay);
    }

    function redecorate() {
        for (const [item, eh] of Object.values(known)) decorate(item, eh);
    }

    function markSelected(item) {
        document.querySelectorAll('.node.tt-selected').forEach(n => n.classList.remove('tt-selected'));
        if (item) document.getElementById(item.id)?.classList.add('tt-selected');
    }

    // ── "with cards" and "fully upgraded" ───────────────────────────────────
    // The server builds the civ once per set of cards (~15 s, started when the
    // tech tree step opens), with every tree tech switched on, and sends each
    // unit's tech steps tagged with the tree tech they come from.  They replay
    // here onto whatever is typed, minus the techs the live tree has off, so
    // the numbers follow every edit and every click instantly.
    function stepsRequest(id) {
        return fetch('/api/builder/tree-steps', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ draft: window.getDraft ? window.getDraft() : {},
                                   dat_path: window.getDatPath ? window.getDatPath() : '', id }),
        }).then(r => r.json()).catch(() => ({ status: 'error' }));
    }

    function steps(id) {
        if (!stepsCache[id]) {
            stepsCache[id] = stepsRequest(id).then(r => {   // don't keep a failure
                if (!r || r.status !== 'ok') delete stepsCache[id];
                return r;
            });
        }
        return stepsCache[id];
    }

    function replay(v, list) {
        for (const s of list) {
            v = s.op === 'set' ? s.v : s.op === 'add' ? v + s.v : v * s.v;
            if (s.r === 'round') v = Math.round(v);
            else if (s.r === 'trunc') v = Math.trunc(v);
        }
        return v;
    }

    const fmt = v => String(Math.round(v * 100) / 100);
    const stepText = s => `${s.op === 'set' ? '= ' + fmt(s.v) : s.op === 'add' ? (s.v >= 0 ? '+' : '−') + fmt(Math.abs(s.v))
        : '×' + fmt(s.v)}  ${s.source}${s.card ? ' (card)' : ''}`;

    // One stat: "→ 40 with cards · 52 fully upgraded", each part only when it
    // changes something.  Not focusable, so Tab skips it.
    function fuLine(now, list, cardList = list.filter(s => s.card), wc, full) {
        if (wc === undefined) wc = replay(now, cardList);
        if (full === undefined) full = replay(now, list);
        const parts = [];
        if (fmt(wc) !== fmt(now)) parts.push(`<b>${fmt(wc)}</b> with cards`);
        if (fmt(full) !== fmt(wc)) parts.push(`<b>${fmt(full)}</b> fully upgraded`);
        return { html: parts.length ? '→ ' + parts.join(' · ') : '', title: list.map(stepText).join('\n') };
    }

    function setFu(el, line) {
        el.innerHTML = line.html;
        el.title = line.html ? line.title : '';
    }

    // A step from a tree tech counts while that tech is ticked, or while a
    // ticked node needs it — the build keeps such a prerequisite (the Hand
    // Cannoneer keeps Chemistry).  `needs` comes with every steps answer.
    function liveTechs(needs) {
        const on = new Set(_localtree.techs);
        const add = k => (needs[k] || []).forEach(t => on.add(t));
        _localtree.techs.forEach(t => add('t' + t));
        _localtree.units.concat(_localtree.buildings).forEach(u => add('u' + u));
        return on;
    }

    async function fillUpgrades(body, inf, kind) {
        lastFill = { body, inf, kind };
        const status = body.querySelector('#tt-insp-fu-status');
        const res = await steps(inf.id);
        if (!current || !body.isConnected) return;
        if (!res || res.status !== 'ok') {
            if (status) status.textContent = '';
            return;
        }
        if (status) status.textContent = '';
        const on = liveTechs(res.needs || {});
        const live = list => list.filter(s => !s.node || on.has(s.node));
        const all = live(res.steps || []);
        const of = key => all.filter(s => s.key === key);
        const e = unitEdit(inf.id);

        body.querySelectorAll('[data-fu]').forEach(el => {
            const key = el.dataset.fu;
            if (key === 'train') {
                const now = effectiveTrain(inf).train;
                const t = of('train'), rate = res.train || { rate: 1, steps: [] };
                rate.steps = live(rate.steps);
                const card = l => l.filter(s => s.card);
                const wc = replay(now, card(t)) / replay(rate.rate, card(rate.steps));
                const full = replay(now, t) / replay(rate.rate, rate.steps);
                setFu(el, fuLine(now, t.concat(rate.steps), null, wc, full));
            } else if (key === 'cost') {
                const now = effectiveCost(inf).cost;
                const calc = pick => Object.fromEntries(RES.map(r =>
                    [r, replay(now[r] || 0, pick(of(`cost:${r}`)))]));
                const wc = calc(l => l.filter(s => s.card)), full = calc(l => l);
                const list = RES.flatMap(r => of(`cost:${r}`).map(s => Object.assign({}, s,
                    { source: `${RES_LABEL[r]}: ${s.source}` })));
                const parts = [];
                if (!costEqual(wc, now)) parts.push(`<b>${esc(costText(wc))}</b> with cards`);
                if (!costEqual(full, wc)) parts.push(`<b>${esc(costText(full))}</b> fully upgraded`);
                setFu(el, { html: parts.length ? '→ ' + parts.join(' · ') : '', title: list.map(stepText).join('\n') });
            } else if (key.startsWith('bonus:')) {
                const cls = key.slice(6);
                const base = (inf.bonus || []).find(b => String(b.cls) === cls);
                const now = (e.bonus && e.bonus[cls] !== undefined) ? e.bonus[cls] : (base ? base.amount : 0);
                setFu(el, fuLine(now, of(key)));
            } else {
                const now = e[key] !== undefined ? e[key] : inf[key];
                if (now === undefined || now === null) return;
                setFu(el, fuLine(now, of(key)));
            }
        });
    }

    // ── "+ Add Unit" lines ──────────────────────────────────────────────────
    const AGE_NAMES = ['Dark Age', 'Feudal Age', 'Castle Age', 'Imperial Age'];
    // Every military unit in the player's game, grouped (/api/builder/unit-catalog),
    // and the AI's unit lines (roles, /api/builder/add-unit-options).
    let catalog = { byId: {}, units: [], roles: [], loaded: false };
    const lineInfoCache = {};     // "base:role" -> /api/builder/added-line-info
    const lookCache = {};         // base -> the looks it may wear

    function loadCatalog() {
        if (catalog.loading) return;
        catalog.loading = true;
        Promise.all([
            fetch('/api/builder/unit-catalog?' + datQuery().slice(1)).then(r => r.json()),
            fetch('/api/builder/add-unit-options?building=-1' + datQuery()).then(r => r.json()),
        ]).then(([units, opts]) => {
            catalog.loading = false;
            if (units.status !== 'ok') return;
            catalog.units = units.units;
            for (const u of units.units) catalog.byId[u.id] = u;
            // A base saved before the catalog had it (or one it now dedupes away).
            for (const b of (opts.other || [])) if (!catalog.byId[b.id]) catalog.byId[b.id] = Object.assign({ art: true }, b);
            catalog.roles = opts.roles || [];
            catalog.loaded = true;
            // Labels and pictures of added lines come from here.
            if (edits.added_lines.length) window._ttRelayout?.();
        }).catch(() => { catalog.loading = false; });
    }

    function looksFor(base) {
        if (!lookCache[base]) {
            lookCache[base] = fetch(`/api/builder/unit-catalog?look_for=${base}${datQuery()}`)
                .then(r => r.json()).then(r => r.units || []).catch(() => []);
        }
        return lookCache[base];
    }

    function lineInfo(base, role, from) {
        const key = `${base}:${role ?? ''}:${from ?? ''}`;
        if (!lineInfoCache[key]) {
            lineInfoCache[key] = fetch(`/api/builder/added-line-info?base=${base}`
                    + (role !== null && role !== undefined ? `&role=${role}` : '')
                    + (from !== null && from !== undefined ? `&from=${from}` : '') + datQuery())
                .then(r => r.json()).catch(() => ({ status: 'error' }));
        }
        return lineInfoCache[key];
    }

    function baseName(id) { return (catalog.byId[id] || {}).name || `unit ${id}`; }
    function baseIcon(id) { return (catalog.byId[id] || {}).icon; }
    // A unit's picture: the tree's own art when it has some, else the game's
    // icon read from the player's install (heroes, scenario units).
    function unitImage(id) {
        const u = catalog.byId[id];
        if (u && u.art) return `${_imgroot}/Unit/${u.icon}.png`;
        return `/api/unit-icon/${id}?${datQuery().slice(1)}`;
    }
    // What a line's nodes show: its look's picture when it wears one.
    function lineImage(line) { return unitImage(line.appearance ?? line.base); }

    // added_lines.default_names: tier 1 the base's (or tier 1's own) name,
    // the last "Elite …", any between "Veteran …" / "Heavy …".
    function defaultNames(stem, n) {
        if (n === 1) return [stem];
        const mid = ['Veteran', 'Heavy'].slice(0, n - 2);
        return [stem, ...mid.map(m => `${m} ${stem}`), `Elite ${stem}`];
    }
    // added_lines.extension_names: the next title the unit hasn't got —
    // Halberdier -> Elite Halberdier, Elite Skirmisher -> Imperial Skirmisher.
    const EXTEND_PREFIXES = ['Elite', 'Imperial', 'Royal', 'Legendary'];
    function extensionNames(fromName, n) {
        const words = fromName.split(' ');
        const stem = words.filter(w => !EXTEND_PREFIXES.includes(w)).join(' ') || fromName;
        const free = EXTEND_PREFIXES.filter(p => !words.includes(p));
        const out = free.slice(0, n).map(p => `${p} ${stem}`);
        for (let i = free.length + 1; out.length < n; i++) out.push(`${stem} ${i}`);
        return out;
    }
    function defaultTierName(ref) {
        const { line, n } = ref;
        if (line.replaces != null) return line.tiers[0].name || baseName(line.base);
        if (line.from != null) {
            const first = line.tiers[0].name;
            if (first) return n ? extensionNames(first, line.tiers.length - 1)[n - 1] : first;
            return extensionNames(baseName(line.from), line.tiers.length)[n];
        }
        const stem = line.tiers[0].name || baseName(line.base);
        return defaultNames(stem, line.tiers.length)[n];
    }
    function tierName(key) {
        const ref = addedRef(key);
        return ref ? (ref.tier.name || defaultTierName(ref)) : '';
    }
    // What the tree's hover shows for a tier: the base with every edit up to
    // this tier carried on (as renderAdded), the line's description or the
    // base's, and for a later tier the upgrade into it.
    async function addedTip(key) {
        const ref = addedRef(key);
        if (!ref) return null;
        const { line, n, tier } = ref;
        const [base, defs] = await Promise.all([info('unit', line.base), lineInfo(line.base, line.role, line.from)]);
        if (!base || base.status !== 'ok') return { name: tierName(key), desc: line.description || '' };
        const carried = {};
        for (let i = 0; i <= n; i++) Object.assign(carried, line.tiers[i].edits || {});
        const stat = f => carried[f] !== undefined ? carried[f] : base[f];
        let upgrade = null;
        if (n || line.from != null) {
            const def = defs && defs.status === 'ok' ? defs.upgrades[String(tier.age)] : null;
            const own = tier.upgrade || {};
            upgrade = {
                cost: own.cost || (def && def.cost) || null,
                time: own.time !== undefined ? own.time : def && def.time,
            };
        }
        return {
            name: tierName(key),
            replaces: line.replaces != null ? baseName(line.replaces) : null,
            age: tier.age, n, of: line.tiers.length,
            cost: Object.assign({ food: 0, wood: 0, stone: 0, gold: 0 }, base.cost, carried.cost || {}),
            hp: stat('hp'), attack: base.fights ? stat('attack') : null,
            melee: stat('melee'), pierce: stat('pierce'),
            range: base.fights ? stat('range') : null,
            desc: line.description || base.desc || '',
            upgrade,
        };
    }

    function tierItemId(line, n) { return `Unit_a${line.id}_${n}_${line.building}`; }

    // A line changed shape (a tier, an age, the base): save, redraw the tree,
    // and open `selectId` (a tier's tree id) once it is drawn.
    function relayout(selectId) {
        if (selectId) current = { item: { id: selectId }, element_height: current?.element_height };
        window._ttCommit?.();
        window._ttRelayout?.();
    }

    function addLine(building, age, base, from, replaces) {
        const id = Math.max(0, ...edits.added_lines.map(l => l.id)) + 1;
        const line = { id, building, base, role: null, appearance: null, tiers: [{ age, name: '' }] };
        if (from != null) line.from = from;
        if (replaces != null) line.replaces = replaces;
        edits.added_lines.push(line);
        relayout(tierItemId(line, 0));
    }

    // ── The unit picker window ──────────────────────────────────────────────
    // One large window, like the wizard's unique-unit and hero pickers: every
    // military unit in the game, by group and kind, with a search.
    const GROUPS = [
        ['here', 'Trained here'], ['all', 'All'], ['standard', 'Standard'], ['regional', 'Regional'],
        ['unique', 'Unique'], ['chronicles', 'Chronicles'], ['scenario', 'Scenario'], ['hero', 'Heroes'],
    ];
    const GROUP_BADGE = { regional: ['R', 'vanilla'], unique: ['U', 'custom'], chronicles: ['C', 'chronicles'],
                          scenario: ['S', 'scenario'], hero: ['H', 'hero'] };
    const badge = g => GROUP_BADGE[g] ? `<span class="uu-badge uu-badge-${GROUP_BADGE[g][1]}">${GROUP_BADGE[g][0]}</span>` : '';
    const KINDS = [
        ['all', 'All kinds'], ['infantry', 'Infantry', [6, 35]], ['archers', 'Archers & gunpowder', [0, 36, 44]],
        ['cavalry', 'Cavalry', [12, 23, 47]], ['siege', 'Siege', [13, 55]], ['monks', 'Monks', [18]],
        ['ships', 'Ships', [2, 20, 21, 22]],
    ];
    let pickerEl = null, pickerModal = null;
    const pickerState = { group: null, kind: 'all', q: '' };

    function pickerShell() {
        if (pickerEl) return pickerEl;
        pickerEl = document.createElement('div');
        pickerEl.className = 'modal fade tt-unit-picker';
        pickerEl.tabIndex = -1;
        pickerEl.setAttribute('aria-hidden', 'true');
        pickerEl.innerHTML = `<div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable modal-fullscreen-lg-down">
            <div class="modal-content">
                <div class="modal-header">
                    <div><h5 class="modal-title" id="tt-pick-title"></h5>
                        <div class="small text-muted" id="tt-pick-sub"></div></div>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                        <input type="search" id="tt-pick-search" class="form-control form-control-sm"
                            style="max-width:16rem" placeholder="Search units" aria-label="Search units" autocomplete="off">
                        <select id="tt-pick-kind" class="form-select form-select-sm" style="max-width:13rem" aria-label="Kind">
                            ${KINDS.map(([k, label]) => `<option value="${k}">${label}</option>`).join('')}</select>
                        <span id="tt-pick-count" class="text-muted small"></span>
                    </div>
                    <div class="btn-group btn-group-sm flex-wrap mb-3" role="group" id="tt-pick-groups"></div>
                    <div class="uu-grid tt-pick-grid" id="tt-pick-grid"></div>
                </div>
                <div class="modal-footer small text-muted justify-content-start" id="tt-pick-foot">
                    ${badge('regional')} Regional · ${badge('unique')} Unique · ${badge('chronicles')} Chronicles ·
                    ${badge('scenario')} Scenario · ${badge('hero')} Hero<span class="tt-pick-heronote"> (trains like any unit here: no hero rules)</span> ·
                    Press <i class="fa-solid fa-play mx-1"></i> to see one move.
                </div>
            </div></div>`;
        document.body.appendChild(pickerEl);
        pickerModal = new bootstrap.Modal(pickerEl);
        pickerEl.addEventListener('show.bs.modal', () => document.body.classList.add('tt-picker-open'));
        pickerEl.addEventListener('hidden.bs.modal', () => document.body.classList.remove('tt-picker-open'));
        return pickerEl;
    }

    function cardStats(u) {
        const parts = [`<i class="fa-solid fa-heart"></i> ${u.hp}`];
        if (u.attack) parts.push(`<i class="fa-solid fa-khanda"></i> ${u.attack}`);
        parts.push(`<i class="fa-solid fa-shield-halved"></i> ${u.ma}/${u.pa}`);
        if (u.range >= 1) parts.push(`<i class="fa-solid fa-bullseye"></i> ${Math.round(u.range * 10) / 10}`);
        return parts.join(' ');
    }

    // opts: {title, sub, building, pool (looks) | null, current, ownLook, onPick(id|null)}
    async function openUnitPicker(opts) {
        const el = pickerShell();
        if (!catalog.loaded) loadCatalog();
        el.querySelector('#tt-pick-title').textContent = opts.title;
        el.querySelector('#tt-pick-sub').textContent = opts.sub || '';
        el.querySelector('.tt-pick-heronote').hidden = !!opts.pool;
        const grid = el.querySelector('#tt-pick-grid');
        const search = el.querySelector('#tt-pick-search');
        const kindSel = el.querySelector('#tt-pick-kind');
        const groupsEl = el.querySelector('#tt-pick-groups');
        grid.innerHTML = typeof _loaderHtml === 'function' ? _loaderHtml('Loading units…') : 'Loading units…';
        pickerModal.show();
        let picked = false;
        el.addEventListener('hidden.bs.modal', () => { if (!picked) opts.onCancel?.(); }, { once: true });

        let pool = opts.pool ? await opts.pool : null;
        while (!pool && !catalog.loaded) {
            await new Promise(r => setTimeout(r, 300));
            if (!el.classList.contains('show')) return;
        }
        // The Dock trains ships only, and no other building trains them.
        const naval = opts.building === 45;
        const units = (pool || catalog.units).filter(u => opts.pool || u.naval === naval);
        const here = opts.building != null ? units.filter(u => (u.at || []).includes(opts.building)) : [];
        const groups = GROUPS.filter(([g]) => g === 'all' || (g === 'here' ? here.length
            : units.some(u => u.group === g)));
        if (!groups.some(([g]) => g === pickerState.group)) pickerState.group = here.length ? 'here' : 'all';
        if (opts.first != null) pickerState.group = here.length ? 'here' : 'all';
        if (opts.pool) pickerState.group = 'all';

        groupsEl.innerHTML = groups.map(([g, label]) => {
            const n = g === 'here' ? here.length : g === 'all' ? units.length : units.filter(u => u.group === g).length;
            return `<button type="button" class="btn btn-outline-secondary" data-group="${g}">${label} <span class="opacity-50">${n}</span></button>`;
        }).join('');
        const draw = () => {
            groupsEl.querySelectorAll('[data-group]').forEach(b => b.classList.toggle('active', b.dataset.group === pickerState.group));
            const q = search.value.trim().toLowerCase();
            const kind = KINDS.find(k => k[0] === kindSel.value);
            const list = (pickerState.group === 'here' ? here : pickerState.group === 'all' ? units
                : units.filter(u => u.group === pickerState.group))
                .filter(u => !q || u.name.toLowerCase().includes(q))
                .filter(u => !kind[2] || kind[2].includes(u.cls))
                .sort((a, b) => (b.id === opts.first) - (a.id === opts.first));
            el.querySelector('#tt-pick-count').textContent = `${list.length} unit${list.length === 1 ? '' : 's'}`;
            const own = opts.ownLook ? `<div class="uu-card${opts.current == null ? ' selected' : ''}" data-pick="">
                    <img class="uu-card-icon" src="${unitImage(opts.ownLook)}" alt="">
                    <div class="uu-card-name">Its own look</div></div>` : '';
            grid.innerHTML = own + list.map(u => `<div class="uu-card${u.id === opts.current ? ' selected' : ''}" data-pick="${u.id}"
                    title="${esc(u.name)}">
                    ${typeof _previewBtnHtml === 'function' ? _previewBtnHtml(u.id, u.name) : ''}
                    ${badge(u.group)}
                    <img class="uu-card-icon" src="${unitImage(u.id)}" alt="" loading="lazy">
                    <div class="uu-card-name">${esc(u.name)}</div>
                    <div class="tt-pick-stats">${cardStats(u)}</div>
                </div>`).join('') || (own ? '' : `<div class="text-muted small fst-italic">${units.length
                    ? 'No units match.' : opts.pool ? 'No other look fits this unit\'s kind and size.' : 'Point Empire Forge at your game (step 1) to list its units.'}</div>`);
            if (typeof _wirePreviewButtons === 'function') _wirePreviewButtons(grid);
            grid.querySelectorAll('[data-pick]').forEach(card => card.addEventListener('click', () => {
                picked = true;
                pickerModal.hide();
                opts.onPick(card.dataset.pick === '' ? null : +card.dataset.pick);
            }));
        };
        groupsEl.querySelectorAll('[data-group]').forEach(b => b.addEventListener('click', () => {
            pickerState.group = b.dataset.group;
            draw();
        }));
        search.value = '';
        search.oninput = draw;
        kindSel.value = 'all';
        kindSel.onchange = draw;
        draw();
        setTimeout(() => search.focus({ preventScroll: true }), 200);
    }

    // The "+" under the last unit of a line: add tiers after it (an extension).
    // Its first tier starts in the next age (the same one in the Imperial Age),
    // a copy of that unit unless another is picked.
    function extend(item) {
        const from = item.node_id;
        const fromName = (window._ttNodeName ? window._ttNodeName(item) : baseName(from)).replace(/\n/g, ' ');
        const age = Math.min(4, (item.age_id || 1) + 1);
        openUnitPicker({
            title: `Add an upgrade after the ${fromName}`,
            sub: `The ${fromName} upgrades into it in the ${AGE_NAMES[age - 1]} (you can change the age next). `
                + `Pick the ${fromName} itself to make a stronger copy of it, like the Imperial Skirmisher.`,
            building: item.building_id, current: from, first: from,
            onPick: base => addLine(item.building_id, age, base, from),
        });
    }

    // Replace a unit an upgrade gives (Paladin) with another: the vanilla
    // upgrade stays, and a hidden tech after it turns the result into ours.
    function replace(item) {
        const name = (window._ttNodeName ? window._ttNodeName(item) : baseName(item.node_id)).replace(/\n/g, ' ');
        openUnitPicker({
            title: `Replace the ${name}`,
            sub: `Researching the ${name} upgrade gives this unit instead, and the button takes its name. `
                + `The button keeps the ${name}'s picture: the game can't change a technology's picture for one civilization.`,
            building: item.building_id,
            onPick: base => addLine(item.building_id, item.age_id || 1, base, null, item.node_id),
        });
    }

    // The "+" was clicked (item.add), or a line's base is being changed (item.rebase).
    function renderPicker(item) {
        const ctx = item.add;
        const line = ctx.line ? edits.added_lines.find(l => l.id === ctx.line) : null;
        const back = () => {
            const again = line && known[tierItemId(line, ctx.n || 0)];
            if (again) select(again[0], again[1]);
            else { current = null; markSelected(null); mount(panel); }
        };
        panel.innerHTML = `<div class="tt-insp-head"><div>
                <div class="tt-insp-title">${line ? 'Change the base unit' : 'Add a unit'}</div>
                <div class="tt-insp-kind">${esc(ctx.buildingName || '')} · ${AGE_NAMES[ctx.age - 1]}</div>
            </div></div>
            <div class="tt-insp-note">${line
                ? 'Every tier is a copy of this unit; your edits stay.'
                : 'Pick the unit to copy. It becomes a new line in this building, starting in this age; you can add later tiers, rename it and change its stats next.'}</div>
            <button type="button" class="tt-insp-reset" id="tt-pick-open">Choose a unit…</button>`;
        const open = () => openUnitPicker({
            title: line ? 'Change the base unit' : `Add a unit to the ${ctx.buildingName || 'building'}`,
            sub: line ? 'Every tier is a copy of this unit; your edits stay.'
                : `Starting in the ${AGE_NAMES[ctx.age - 1]}. Any unit fights the way it does in the game; heroes train like any unit here, without hero rules.`,
            building: ctx.building, current: line ? line.base : null,
            onCancel: line ? back : null,
            onPick: base => {
                if (line) {
                    line.base = base;
                    // A look must fit the new base's kind and size; the build drops one that doesn't.
                    looksFor(base).then(looks => {
                        if (line.appearance != null && !looks.some(l => l.id === line.appearance)) {
                            line.appearance = null;
                            relayout(tierItemId(line, ctx.n || 0));
                        }
                    });
                    relayout(tierItemId(line, ctx.n || 0));
                } else {
                    addLine(ctx.building, ctx.age, base);
                }
            },
        });
        panel.querySelector('#tt-pick-open').addEventListener('click', open);
        open();
    }

    function lineSection(ref, item, defs) {
        const { line, n } = ref;
        const last = line.tiers.length - 1;
        const minAge = item.added.fromAge || item.added.buildingAge || 1;
        const tiers = line.tiers.map((t, i) => {
            const lo = i === 0 ? minAge : line.tiers[i - 1].age + 1;
            const hi = i === last ? 4 : line.tiers[i + 1].age - 1;
            const ages = [];
            for (let a = lo; a <= hi; a++) ages.push(`<option value="${a}" ${a === t.age ? 'selected' : ''}>${AGE_NAMES[a - 1]}</option>`);
            return `<div class="tt-insp-tier${i === n ? ' is-current' : ''}">
                <button type="button" class="tt-insp-link tt-insp-tier-name" data-goto="${i}">${esc(tierName(`a${line.id}.${i}`))}</button>
                <select data-age="${i}" title="Age">${ages.join('')}</select>
                <button type="button" class="tt-insp-x" data-drop="${i}"
                    title="${line.tiers.length === 1 ? 'Remove this line' : 'Remove this tier'}">×</button>
            </div>`;
        }).join('');
        const lastAge = line.tiers[last].age;
        const addAges = [];
        for (let a = lastAge + 1; a <= 4 && line.tiers.length < 4; a++) addAges.push(`<option value="${a}">${AGE_NAMES[a - 1]}</option>`);
        const roleName = id => (catalog.roles.find(r => r.id === id) || {}).name;
        const auto = defs && defs.default_role != null ? roleName(defs.default_role) || `line ${defs.default_role}` : null;
        const roles = catalog.roles.map(r => `<option value="${r.id}" ${r.id === line.role ? 'selected' : ''}>${esc(r.name)}</option>`).join('');
        const look = line.appearance != null ? catalog.byId[line.appearance] : null;
        const swap = line.replaces != null;
        const was = swap ? (item.added.replacesName || baseName(line.replaces)) : '';
        return `<div class="tt-insp-line">
            <div class="tt-insp-section">${swap ? 'Replacement' : line.from != null ? 'Added upgrade' : 'Added line'}</div>
            ${swap ? `<div class="tt-insp-row tt-insp-baserow"><span class="tt-insp-label">Replaces</span>
                <span class="tt-insp-basename">${esc(was)}</span></div>` : ''}
            ${line.from != null ? `<div class="tt-insp-row tt-insp-baserow"><span class="tt-insp-label">Upgrades from</span>
                <span class="tt-insp-basename">${esc(item.added.fromName || baseName(line.from))}</span></div>` : ''}
            <div class="tt-insp-row tt-insp-baserow"><span class="tt-insp-label">Copy of</span>
                <span class="tt-insp-basename">${esc(baseName(line.base))}</span>
                <button type="button" class="tt-insp-link" id="tt-line-base">change</button></div>
            ${swap ? `<div class="tt-insp-note">Researching the ${esc(was)} upgrade gives this unit instead, and the
                button takes its name. The button keeps the ${esc(was)}'s picture: the game can't change a
                technology's picture for one civilization. The computer player gets it too, since it still
                researches the ${esc(was)} upgrade.</div>` : `
            <div class="tt-insp-tiers">${tiers}</div>
            ${addAges.length ? `<div class="tt-insp-bonus-add"><select id="tt-line-add">
                <option value="">Add a tier in…</option>${addAges.join('')}</select></div>` : ''}
            <div class="tt-insp-note">${line.from != null
                ? `Each tier is researched at the ${esc(item.added.fromName || '')}'s upgrade button, after the one before, and takes over its train button.`
                : 'Each tier after the first gets its own upgrade, one row below the unit\'s button.'}
                A stat you change carries on to later tiers unless they set their own.</div>`}
            <div class="tt-insp-row"><label class="tt-insp-label" for="tt-line-desc">Description</label>
                <textarea class="tt-insp-num tt-insp-text tt-insp-desc" id="tt-line-desc" rows="3" maxlength="300"
                    placeholder="The ${esc(baseName(line.base))}'s own description">${esc(line.description || '')}</textarea></div>
            <div class="tt-insp-row"><label class="tt-insp-label" for="tt-line-role">Computer player trains it as</label>
                <select id="tt-line-role"><option value="">${auto ? `Automatic: ${esc(auto)}` : 'Automatic (no line found; the computer player won\'t train it)'}</option>${roles}</select></div>
            ${line.tiers.length > 1 ? `<div class="tt-insp-note">The computer player trains the first tier only: it researches just the upgrades it knows by name.</div>` : ''}
            <div class="tt-insp-row tt-insp-baserow"><span class="tt-insp-label">Appearance</span>
                <span class="tt-insp-basename">${line.appearance == null ? 'Its own'
                    : esc(look ? look.name : `unit ${line.appearance}`)}</span>
                <button type="button" class="tt-insp-link" id="tt-line-look">change</button></div>
            <button type="button" class="tt-insp-reset" id="tt-line-remove">${swap ? `Undo: back to the ${esc(was)}` : 'Remove this line'}</button>
        </div>`;
    }

    function wireLine(ref, item) {
        const { line, n } = ref;
        const goto = i => {
            const again = known[tierItemId(line, i)];
            if (again) select(again[0], again[1]);
        };
        panel.querySelectorAll('[data-goto]').forEach(b => b.addEventListener('click', () => goto(+b.dataset.goto)));
        panel.querySelectorAll('select[data-age]').forEach(sel => sel.addEventListener('change', () => {
            line.tiers[+sel.dataset.age].age = +sel.value;
            relayout(tierItemId(line, n));
        }));
        panel.querySelectorAll('[data-drop]').forEach(b => b.addEventListener('click', () => {
            const i = +b.dataset.drop;
            if (line.tiers.length === 1) return removeLine(line);
            line.tiers.splice(i, 1);
            relayout(tierItemId(line, Math.min(n, line.tiers.length - 1)));
        }));
        const add = panel.querySelector('#tt-line-add');
        add?.addEventListener('change', () => {
            if (!add.value) return;
            line.tiers.push({ age: +add.value, name: '' });
            relayout(tierItemId(line, line.tiers.length - 1));
        });
        panel.querySelector('#tt-line-role')?.addEventListener('change', e => {
            line.role = e.target.value === '' ? null : +e.target.value;
            later();
        });
        panel.querySelector('#tt-line-desc')?.addEventListener('change', e => {
            line.description = e.target.value.replace(/\s+/g, ' ').trim().slice(0, 300);
            later();
        });
        panel.querySelector('#tt-line-look')?.addEventListener('click', () => openUnitPicker({
            title: 'Choose a look',
            sub: `Units of the same kind and size as the ${baseName(line.base)}, so the art fits. The last tier wears the look's Elite when it has one.`,
            pool: looksFor(line.base), current: line.appearance, ownLook: line.base,
            onPick: id => {
                line.appearance = id;
                relayout(tierItemId(line, n));
            },
        }));
        panel.querySelector('#tt-line-base')?.addEventListener('click', () => {
            select({ id: '__rebase', add: { building: line.building, age: line.tiers[0].age,
                     buildingName: item.added.buildingName, line: line.id, n } }, current.element_height);
        });
        const rm = panel.querySelector('#tt-line-remove');
        rm?.addEventListener('click', () => {
            if (rm.dataset.armed) return removeLine(line);
            rm.dataset.armed = '1';
            rm.textContent = line.replaces != null ? 'Click again to undo the replacement' : 'Click again to remove the whole line';
        });
    }

    function removeLine(line) {
        edits.added_lines = edits.added_lines.filter(l => l !== line);
        current = null;
        window._ttCommit?.();
        window._ttRelayout?.();
        mount(panel);
    }

    async function renderAdded(item) {
        const ref = addedRef(item.node_id);
        if (!ref) { current = null; return mount(panel); }
        const focused = focusKey(document.activeElement);
        const scrollTop = panel.scrollTop;
        const { line, n, tier } = ref;
        const key = item.node_id;
        const [base, defs] = await Promise.all([info('unit', line.base), lineInfo(line.base, line.role, line.from)]);
        if (!current || current.item !== item) return;
        panel.innerHTML = `<div class="tt-insp-head">
                <img class="tt-insp-icon" src="${lineImage(line)}" alt="">
                <div>
                    <div class="tt-insp-title">${esc(tierName(key))}</div>
                    <div class="tt-insp-kind">${line.replaces != null ? `Replaces the ${esc(item.added.replacesName || '')}`
                        : `${line.from != null ? `Added upgrade after the ${esc(item.added.fromName || '')}` : 'Added unit'}`
                          + ` · tier ${n + 1} of ${line.tiers.length}`} · ${AGE_NAMES[tier.age - 1]}</div>
                </div>
            </div>
            ${lineSection(ref, item, defs && defs.status === 'ok' ? defs : null)}
            <div id="tt-insp-body"></div>`;
        wireLine(ref, item);
        const body = panel.querySelector('#tt-insp-body');
        if (!base || base.status !== 'ok') {
            body.innerHTML = `<div class="tt-insp-note">${base && base.status === 'no_dat'
                ? 'Point Empire Forge at your game (step 1) to see and edit stats.' : 'This unit has no stats to edit.'}</div>`;
            return;
        }
        // The tier starts as the base with every earlier tier's edits carried
        // on (added_lines._flowed_edits), so its boxes show what it will be.
        const carried = {};
        for (let i = 0; i < n; i++) Object.assign(carried, line.tiers[i].edits || {});
        const inf = clone(base);
        inf.id = key;
        inf.name = defaultTierName(ref);
        for (const [f] of STAT_FIELDS) if (carried[f] !== undefined) inf[f] = carried[f];
        if (carried.train !== undefined) inf.train = carried.train;
        if (carried.cost) inf.cost = Object.assign({ food: 0, wood: 0, stone: 0, gold: 0 }, carried.cost);
        if (carried.bonus) {
            const b = Object.fromEntries((inf.bonus || []).map(x => [String(x.cls), x.amount]));
            Object.assign(b, carried.bonus);
            inf.bonus = Object.entries(b).map(([cls, amount]) => ({ cls: +cls, amount }));
        }
        inf.line_before = [];
        inf.line_after = [];
        inf.forms = 1;
        const up = defs && defs.status === 'ok' ? defs.upgrades[String(tier.age)] : null;
        inf.upgrade = (n || line.from != null) && up ? {
            id: `${key}u`, name: tierName(key), any: true,
            cost: Object.assign({ food: 0, wood: 0, stone: 0, gold: 0 }, up.cost),
            time: up.time,
        } : null;
        unitNames[key] = tierName(key);
        body.innerHTML = unitBody(inf, 'unit');
        const status = body.querySelector('#tt-insp-fu-status');
        if (status) status.textContent = '';
        wire(body, inf, 'unit');
        redecorate();
        panel.scrollTop = scrollTop;
        restoreFocus(focused);
    }

    // ── rendering ───────────────────────────────────────────────────────────
    function mount(el) {
        panel = el;
        if (window.getDatPath) stepsRequest(null);       // start the build now
        loadLines();
        if (!catalog.loaded) loadCatalog();
        panel.innerHTML = `<div class="tt-insp-empty">
            <div class="tt-insp-empty-title">Inspector</div>
            Click a unit, building or tech to see its stats and edit it.
            <div class="tt-insp-hint">Shift-click a node to turn it on or off without opening it.</div>
        </div>`;
    }

    function select(item, element_height) {
        current = { item, element_height };
        markSelected(item);
        render();
    }

    function includeRow(item) {
        let note = '';
        let locked = false;
        if (typeof _isExternallyControlled === 'function' && _isExternallyControlled(item)) {
            locked = true;
            note = 'Set by the Siege Ship picker or a bonus card, not here.';
        } else if (item.use_type === 'Building' && HARD_ALWAYS_ON_BUILDINGS.has(item.node_id)) {
            locked = true;
            note = 'Every civ has a Town Center.';
        }
        const on = _isSelected(item);
        return `<label class="tt-insp-include${locked ? ' is-locked' : ''}">
            <input type="checkbox" id="tt-insp-include" ${on ? 'checked' : ''} ${locked ? 'disabled' : ''}>
            <span>${on ? 'In this civ' : 'Not in this civ'}</span>
        </label>${note ? `<div class="tt-insp-note">${esc(note)}</div>` : ''}`;
    }

    function numInput(attrs) {
        const { id, value, base, step, min, max, disabled, title } = attrs;
        return `<input type="number" class="tt-insp-num${value !== undefined && value !== null ? ' is-edited' : ''}"
            id="${id}" step="${step}" min="${min}" max="${max}"
            placeholder="${esc(base)}" value="${value ?? ''}" ${disabled ? 'disabled' : ''}
            ${title ? `title="${esc(title)}"` : ''}>`;
    }

    function costBlock(prefix, shown, base, opts = {}) {
        // shown: the values in the boxes; base: the game's; opts.only: resources allowed
        return `<div class="tt-insp-cost">${RES.map(r => {
            const allowed = !opts.only || opts.only.includes(r);
            return `<label class="tt-insp-res${allowed ? '' : ' is-off'}" title="${allowed ? RES_LABEL[r]
                    : `This tech doesn't cost ${r}, and an edit can only scale a cost it already has.`}">
                <img src="/static/aoe2techtree/img/${r}.png" alt="">
                <span class="tt-insp-res-name">${RES_LABEL[r]}</span>
                <input type="number" class="tt-insp-num${(shown[r] || 0) !== (base[r] || 0) ? ' is-edited' : ''}"
                    data-res="${r}" id="${prefix}-${r}" min="0" max="${SHORT}" step="1"
                    value="${allowed ? (shown[r] || 0) : ''}" ${allowed ? '' : 'disabled'}>
            </label>`;
        }).join('')}</div>`;
    }

    // Every edit redraws the panel, which would drop keyboard focus.  So
    // redraws wait a tick (a Tab has moved focus on by then), and the box that
    // had focus gets it back afterwards.
    function focusKey(el) {
        if (!panel || !el || !panel.contains(el)) return null;
        if (el.id) return `#${el.id}`;
        if (el.dataset.cls !== undefined) return `input[data-cls="${el.dataset.cls}"]`;
        if (el.dataset.remove !== undefined) return `[data-remove="${el.dataset.remove}"]`;
        return null;
    }

    function restoreFocus(key) {
        const el = key && panel.querySelector(key);
        if (!el || el.disabled) return;
        el.focus({ preventScroll: true });
        if (el.tagName === 'INPUT' && el.type === 'number') el.select();
    }

    function later() { setTimeout(render, 0); window._ttCommit?.(); }

    async function render() {
        if (!panel || !current) return;
        const { item } = current;
        if (item.add) return renderPicker(item);
        if (item.added) return renderAdded(item);
        const focused = focusKey(document.activeElement);
        const scrollTop = panel.scrollTop;
        const kind = kindOf(item);
        const name = nameOf(item) || ((typeof formatName === 'function' && data.strings)
            ? formatName(data.strings[item.name_string_id] || item.name) : item.name);
        const icon = typeof _imgroot === 'string' && item.picture_index !== undefined
            ? `${_imgroot}/${item.use_type}/${item.picture_index}.png` : '';
        panel.innerHTML = `<div class="tt-insp-head">
                ${icon ? `<img class="tt-insp-icon" src="${esc(icon)}" alt="">` : ''}
                <div>
                    <div class="tt-insp-title">${esc(String(name).replace(/\n/g, ' '))}</div>
                    <div class="tt-insp-kind">${kind === 'tech' ? 'Technology' : kind === 'building' ? 'Building' : 'Unit'}</div>
                </div>
            </div>
            ${includeRow(item)}
            ${window._ttCanExtend?.(item) ? `<button type="button" class="tt-insp-reset" id="tt-insp-extend"
                title="A further upgrade for this line, like the Imperial Skirmisher">Add an upgrade after it…</button>` : ''}
            ${window._ttCanReplace?.(item) ? `<button type="button" class="tt-insp-reset" id="tt-insp-replace"
                title="Its upgrade gives another unit instead, like the Savar for the Paladin">Replace with another unit…</button>` : ''}
            <div id="tt-insp-body"><div class="tt-insp-loading">Loading stats…</div></div>`;
        panel.querySelector('#tt-insp-extend')?.addEventListener('click', () => extend(item));
        panel.querySelector('#tt-insp-replace')?.addEventListener('click', () => replace(item));
        panel.querySelector('#tt-insp-include')?.addEventListener('change', () => {
            _toggleNode(item, current.element_height);
            _treeChanged();
            later();
        });

        const inf = await info(kind, item.node_id);
        if (!current || current.item !== item) return;      // clicked elsewhere meanwhile
        const body = panel.querySelector('#tt-insp-body');
        if (!inf || inf.status === 'no_dat') {
            body.innerHTML = `<div class="tt-insp-note">Point Empire Forge at your game (step 1) to see and edit stats.</div>`;
            return;
        }
        if (inf.status !== 'ok') {
            body.innerHTML = `<div class="tt-insp-note">This node has no stats to edit.</div>`;
            return;
        }
        if (inf.upgrade) upgradeOf[item.node_id] = inf.upgrade.id;
        // Names for the "From the Knight edit" notes.
        await Promise.all((inf.line_before || []).map(a => info('unit', a)));
        if (!current || current.item !== item) return;
        body.innerHTML = ageRow(item, inf, kind) + (kind === 'tech' ? techBody(inf) : unitBody(inf, kind));
        body.querySelector('#tt-insp-age')?.addEventListener('change', e => {
            const v = +e.target.value;
            (kind === 'tech' ? setTechField : setUnitField)(item.node_id, 'age', v === inf.age_move.age ? null : v);
            relayout(item.id);
        });
        wire(body, inf, kind);
        redecorate();
        panel.scrollTop = scrollTop;
        restoreFocus(focused);
        if (kind !== 'tech') fillUpgrades(body, inf, kind);
    }

    // "Available from": an age earlier than the game's, down to its building's
    // and the unit or tech before it (civ_overrides._apply_age_moves).
    function ageRow(item, inf, kind) {
        const mv = inf.age_move;
        if (!mv || !mv.ok) return '';
        const own = (kind === 'tech' ? techEdit(item.node_id) : unitEdit(item.node_id)).age;
        const lo = Math.min(mv.age, window._ttMinAge ? window._ttMinAge(item) : 1);
        const opts = [];
        for (let a = lo; a <= mv.age; a++) {
            opts.push(`<option value="${a}" ${a === (own ?? mv.age) ? 'selected' : ''}>${AGE_NAMES[a - 1]}${a === mv.age ? ' (the game\'s)' : ''}</option>`);
        }
        return `<div class="tt-insp-row"><label class="tt-insp-label" for="tt-insp-age">Available from</label>
            <select id="tt-insp-age" class="${own != null ? 'is-edited' : ''}" ${opts.length < 2 ? 'disabled' : ''}
                title="${opts.length < 2 ? 'Its building, or what comes before it, isn\'t available any earlier' : ''}">${opts.join('')}</select></div>`;
    }

    function label(id, nm, base, edited) {
        return `<label class="tt-insp-label" for="${id}">${esc(nm)}
            <span class="tt-insp-base">${edited ? `game: ${esc(base)}` : ''}</span></label>`;
    }

    function unitBody(inf, kind) {
        const e = unitEdit(inf.id);
        const rows = STAT_FIELDS.filter(f => f[5](inf)).map(([f, nm, step, min, max]) => {
            const id = `tt-insp-${f}`;
            return `<div class="tt-insp-row">${label(id, nm, inf[f], e[f] !== undefined)}
                <div class="tt-insp-group"><span class="tt-insp-addon" aria-hidden="true">
                    <img src="/static/icons/properties/${STAT_ICON[f]}.png" alt=""></span>
                ${numInput({ id, value: e[f], base: inf[f], step, min, max })}</div>
                <div class="tt-insp-fu" data-fu="${f}"></div></div>`;
        }).join('');

        const tr = effectiveTrain(inf);
        const trainName = kind === 'building' ? 'Build time' : 'Train time';
        const trainNote = tr.from ? `<div class="tt-insp-note">From the ${esc(lineName(tr.from))} edit.</div>` : '';

        const ec = effectiveCost(inf);
        const costNote = ec.from
            ? `<div class="tt-insp-note">From the ${esc(lineName(ec.from))} edit. Change it here to give this tier its own.</div>`
            : '';
        const lineNote = (inf.line_after || []).length
            ? `<div class="tt-insp-note">Cost and ${trainName.toLowerCase()} carry on to later upgrades unless they have their own.</div>`
            : '';

        const notes = [];
        if (kind === 'building' && inf.forms > 1)
            notes.push('Buildings gain hit points and armour each age. Your change is added to every age\'s value.');
        else if (inf.forms > 1)
            notes.push(`This unit has ${inf.forms} forms in the game (${inf.id === 83 ? 'one per villager task' : 'packed, carrying and so on'}); the change reaches all of them.`);

        const nameRow = kind === 'unit' && current && canRename(current.item) ? `
            <div class="tt-insp-row tt-insp-name-row">${label('tt-insp-name', 'Name', inf.name, e.name !== undefined)}
                <input type="text" class="tt-insp-num tt-insp-text${e.name ? ' is-edited' : ''}" id="tt-insp-name"
                    maxlength="40" autocomplete="off" spellcheck="false"
                    placeholder="${esc(inf.name)}" value="${esc(e.name || '')}"></div>` : '';

        return `
            ${nameRow}
            ${notes.map(n => `<div class="tt-insp-note">${esc(n)}</div>`).join('')}
            <div class="tt-insp-section">Stats <span class="tt-insp-fu-status" id="tt-insp-fu-status">working out upgrades…</span></div>
            <div class="tt-insp-grid">${rows}
                <div class="tt-insp-row">${label('tt-insp-train', trainName, inf.train, e.train !== undefined)}
                    ${numInput({ id: 'tt-insp-train', value: e.train, base: tr.train, step: 1, min: 1, max: SHORT })}
                    <div class="tt-insp-fu" data-fu="train"></div></div>
            </div>${trainNote}
            ${inf.fights ? bonusSection(inf) : ''}
            <div class="tt-insp-section">Cost ${e.cost ? '<button type="button" class="tt-insp-link" id="tt-insp-cost-reset">use the game\'s</button>' : ''}</div>
            ${costBlock('tt-insp-cost', ec.cost, inf.cost)}
            <div class="tt-insp-fu" data-fu="cost"></div>
            <div class="tt-insp-error" id="tt-insp-cost-error"></div>
            ${costNote}${lineNote}
            ${inf.upgrade ? upgradeSection(inf.upgrade) : ''}
            ${(Object.keys(e).length || (inf.upgrade && edits.tech_edits[String(inf.upgrade.id)]))
                ? '<button type="button" class="tt-insp-reset" id="tt-insp-reset">Reset everything on this unit</button>' : ''}`;
    }

    function lineName(uid) {
        return unitNames[uid] || `unit ${uid}`;
    }

    function bonusSection(inf) {
        const e = unitEdit(inf.id).bonus || {};
        const base = Object.fromEntries((inf.bonus || []).map(b => [String(b.cls), b.amount]));
        const shown = Object.assign({}, base, e);
        const names = Object.fromEntries((inf.bonus_classes || []).map(c => [String(c.cls), c.name]));
        const rows = Object.entries(shown).filter(([, a]) => a > 0).map(([cls, amount]) => `
            <div class="tt-insp-bonus">
                <span>+ vs ${esc(names[cls] || `class ${cls}`)}</span>
                <input type="number" class="tt-insp-num${e[cls] !== undefined ? ' is-edited' : ''}" data-cls="${cls}"
                    min="0" max="${SHORT}" step="1" value="${amount}">
                <button type="button" class="tt-insp-x" data-remove="${cls}" title="Remove">×</button>
                <div class="tt-insp-fu" data-fu="bonus:${cls}"></div>
            </div>`).join('');
        const options = (inf.bonus_classes || []).filter(c => !(shown[String(c.cls)] > 0))
            .map(c => `<option value="${c.cls}">${esc(c.name)}</option>`).join('');
        return `<div class="tt-insp-section">Bonus damage</div>
            ${rows || '<div class="tt-insp-note">None.</div>'}
            <div class="tt-insp-bonus-add">
                <select id="tt-insp-bonus-cls"><option value="">Add bonus vs…</option>${options}</select>
                <input type="number" class="tt-insp-num" id="tt-insp-bonus-amt" min="1" max="${SHORT}" step="1" placeholder="+">
                <button type="button" class="tt-insp-add" id="tt-insp-bonus-add">Add</button>
            </div>`;
    }

    function techCostBlock(prefix, tech) {
        const e = techEdit(tech.id);
        const shown = Object.assign({}, tech.cost, e.cost || {});
        // A vanilla tech's edit can only scale what it costs; an added line's
        // upgrade is our own tech and may cost anything (up to three).
        const only = tech.any ? null : RES.filter(r => tech.cost[r] > 0);
        return `${costBlock(prefix, shown, tech.cost, { only })}
            <div class="tt-insp-error" id="${prefix}-error"></div>
            <div class="tt-insp-row">${label(`${prefix}-time`, 'Research time', tech.time, e.time !== undefined)}
                ${numInput({ id: `${prefix}-time`, value: e.time, base: tech.time, step: 1, min: 0, max: SHORT,
                             disabled: !tech.time })}</div>`;
    }

    function upgradeSection(up) {
        return `<div class="tt-insp-section">Upgrade: ${esc(up.name)}</div>
            ${techCostBlock('tt-insp-up', up)}`;
    }

    function techBody(inf) {
        const free = !RES.some(r => inf.cost[r] > 0);
        return `<div class="tt-insp-section">Research</div>
            ${free && !inf.time ? '<div class="tt-insp-note">Free and instant in the game; nothing to scale.</div>' : techCostBlock('tt-insp-tech', inf)}
            ${edits.tech_edits[String(inf.id)] ? '<button type="button" class="tt-insp-reset" id="tt-insp-reset">Reset this tech</button>' : ''}`;
    }

    // ── input wiring ────────────────────────────────────────────────────────
    function wire(body, inf, kind) {
        const rerender = later;

        if (kind === 'tech') {
            wireTechCost(body, 'tt-insp-tech', inf);
        } else {
            const nm = body.querySelector('#tt-insp-name');
            nm?.addEventListener('change', () => {
                const v = nm.value.replace(/\s+/g, ' ').trim().slice(0, 40);
                setUnitField(inf.id, 'name', v && v !== inf.name ? v : null);
                rerender();
            });
            for (const [f, , step, min, max] of STAT_FIELDS) {
                const el = body.querySelector(`#tt-insp-${f}`);
                if (!el) continue;
                el.addEventListener('change', () => {
                    const v = el.value === '' ? null : clamp(parseFloat(el.value), min, max, step);
                    setUnitField(inf.id, f, v === inf[f] ? null : v);
                    rerender();
                });
            }
            const tr = body.querySelector('#tt-insp-train');
            tr?.addEventListener('change', () => {
                const v = tr.value === '' ? null : clamp(parseFloat(tr.value), 1, SHORT, 1);
                setUnitField(inf.id, 'train', v);
                rerender();
            });

            // Cost: the four boxes are the complete cost, so any change commits
            // all four — unless that needs more resource slots than the unit has.
            // An emptied box is that resource unedited (inherited or the game's), not 0.
            const err = body.querySelector('#tt-insp-cost-error');
            body.querySelectorAll('[id^="tt-insp-cost-"][data-res]').forEach(el => {
                el.addEventListener('change', () => {
                    const without = effectiveCost(Object.assign({}, inf, { id: -1 })).cost;
                    const cost = {};
                    body.querySelectorAll('[id^="tt-insp-cost-"][data-res]').forEach(x => {
                        const r = x.dataset.res;
                        cost[r] = x.value.trim() === '' ? (without[r] || 0)
                            : clamp(parseFloat(x.value), 0, SHORT, 1) || 0;
                    });
                    const used = RES.filter(r => cost[r] > 0).length;
                    if (used > inf.cost_slots) {
                        err.textContent = `This unit can cost at most ${inf.cost_slots} resource${inf.cost_slots === 1 ? '' : 's'}`
                            + ' (each unit has three cost slots, and one holds its population).';
                        return;
                    }
                    err.textContent = '';
                    // Back to what it would get anyway (inherited or the game's): drop the edit.
                    setUnitField(inf.id, 'cost', costEqual(cost, without) ? null : cost);
                    rerender();
                });
            });
            body.querySelector('#tt-insp-cost-reset')?.addEventListener('click', () => {
                setUnitField(inf.id, 'cost', null);
                rerender();
            });

            // Bonus damage
            const setBonus = (cls, amount) => {
                const e = Object.assign({}, unitEdit(inf.id).bonus || {});
                const base = (inf.bonus || []).find(b => String(b.cls) === String(cls));
                if ((base ? base.amount : 0) === amount) delete e[cls];
                else e[cls] = amount;
                setUnitField(inf.id, 'bonus', Object.keys(e).length ? e : null);
                rerender();
            };
            body.querySelectorAll('.tt-insp-bonus input[data-cls]').forEach(el => {
                el.addEventListener('change', () => setBonus(el.dataset.cls, clamp(parseFloat(el.value || '0'), 0, SHORT, 1) || 0));
            });
            body.querySelectorAll('[data-remove]').forEach(b => {
                b.addEventListener('click', () => setBonus(b.dataset.remove, 0));
            });
            body.querySelector('#tt-insp-bonus-add')?.addEventListener('click', () => {
                const cls = body.querySelector('#tt-insp-bonus-cls').value;
                const amt = clamp(parseFloat(body.querySelector('#tt-insp-bonus-amt').value), 1, SHORT, 1);
                if (cls !== '' && amt) setBonus(cls, amt);
            });

            if (inf.upgrade) wireTechCost(body, 'tt-insp-up', inf.upgrade);
        }

        body.querySelector('#tt-insp-reset')?.addEventListener('click', () => {
            const ref = addedRef(inf.id);
            if (ref) {
                delete ref.tier.edits;
                delete ref.tier.upgrade;
            } else if (kind === 'tech') delete edits.tech_edits[String(inf.id)];
            else {
                delete edits.unit_edits[String(inf.id)];
                if (inf.upgrade) delete edits.tech_edits[String(inf.upgrade.id)];
            }
            rerender();
        });
    }

    function wireTechCost(body, prefix, tech) {
        body.querySelectorAll(`[id^="${prefix}-"][data-res]`).forEach(el => {
            el.addEventListener('change', () => {
                const cost = {};
                body.querySelectorAll(`[id^="${prefix}-"][data-res]`).forEach(x => {
                    const r = x.dataset.res;          // emptied = the game's, not 0
                    if (!x.disabled) cost[r] = x.value.trim() === '' ? (tech.cost[r] || 0)
                        : clamp(parseFloat(x.value), 0, SHORT, 1) || 0;
                });
                const err = body.querySelector(`#${prefix}-error`);
                if (tech.any && RES.filter(r => cost[r] > 0).length > 3) {
                    if (err) err.textContent = 'A tech can cost at most three resources.';
                    return;
                }
                if (err) err.textContent = '';
                setTechField(tech.id, 'cost', costEqual(cost, tech.cost) ? null : cost);
                later();
            });
        });
        const t = body.querySelector(`#${prefix}-time`);
        t?.addEventListener('change', () => {
            const v = t.value === '' ? null : clamp(parseFloat(t.value), 0, SHORT, 1);
            setTechField(tech.id, 'time', v === tech.time ? null : v);
            later();
        });
    }

    // The tree changed (and is already saved): refilter the open unit's steps.
    function treeChanged() {
        const f = lastFill && lastFill.body.isConnected ? lastFill : null;
        if (f) fillUpgrades(f.body, f.inf, f.kind);
    }

    window.ttInspector = {
        nameOf,
        treeChanged,
        mount,
        select,
        decorate,
        refresh: () => { if (current) render(); },
        rebind(items, element_height) {
            if (!current) return;
            const again = items.find(i => i.id === current.item.id);
            if (again) select(again, element_height);
            else { current = null; mount(panel); }
        },
        addedLines: () => edits.added_lines,
        addedTip,
        extend,
        tierName,
        baseIcon,
        lineImage,
        load(e) {
            edits = { unit_edits: clone(e && e.unit_edits), tech_edits: clone(e && e.tech_edits),
                      added_lines: Array.isArray(e && e.added_lines) ? JSON.parse(JSON.stringify(e.added_lines)) : [] };
            current = null;
            for (const k of Object.keys(known)) delete known[k];             // a new drawing
            for (const k of Object.keys(stepsCache)) delete stepsCache[k];   // the draft may have changed
        },
        edits: () => clone(edits),
    };
})();
