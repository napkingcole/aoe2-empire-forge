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

    let edits = { unit_edits: {}, tech_edits: {} };
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
    function unitEdit(id) { return edits.unit_edits[String(id)] || {}; }
    function techEdit(id) { return edits.tech_edits[String(id)] || {}; }

    function setUnitField(id, field, value) {
        const k = String(id);
        const e = Object.assign({}, edits.unit_edits[k]);
        if (value === null || value === undefined) delete e[field];
        else e[field] = value;
        if (Object.keys(e).length) edits.unit_edits[k] = e;
        else delete edits.unit_edits[k];
    }

    function setTechField(id, field, value) {
        const k = String(id);
        const e = Object.assign({}, edits.tech_edits[k]);
        if (value === null || value === undefined) delete e[field];
        else e[field] = value;
        if (Object.keys(e).length) edits.tech_edits[k] = e;
        else delete edits.tech_edits[k];
    }

    function isEdited(item) {
        const kind = kindOf(item);
        if (kind === 'tech') return !!edits.tech_edits[String(item.node_id)];
        if (edits.unit_edits[String(item.node_id)]) return true;
        const up = upgradeOf[item.node_id];
        return up !== undefined && !!edits.tech_edits[String(up)];
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
        if (current) decorate(current.item, current.element_height);
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

    // ── rendering ───────────────────────────────────────────────────────────
    function mount(el) {
        panel = el;
        if (window.getDatPath) stepsRequest(null);       // start the build now
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
        const focused = focusKey(document.activeElement);
        const scrollTop = panel.scrollTop;
        const kind = kindOf(item);
        const name = (typeof formatName === 'function' && data.strings)
            ? formatName(data.strings[item.name_string_id] || item.name) : item.name;
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
            <div id="tt-insp-body"><div class="tt-insp-loading">Loading stats…</div></div>`;
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
        body.innerHTML = kind === 'tech' ? techBody(inf) : unitBody(inf, kind);
        wire(body, inf, kind);
        redecorate();
        panel.scrollTop = scrollTop;
        restoreFocus(focused);
        if (kind !== 'tech') fillUpgrades(body, inf, kind);
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
                ${numInput({ id, value: e[f], base: inf[f], step, min, max })}
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

        return `
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
        const only = RES.filter(r => tech.cost[r] > 0);
        return `${costBlock(prefix, shown, tech.cost, { only })}
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
            const err = body.querySelector('#tt-insp-cost-error');
            body.querySelectorAll('[id^="tt-insp-cost-"][data-res]').forEach(el => {
                el.addEventListener('change', () => {
                    const cost = {};
                    body.querySelectorAll('[id^="tt-insp-cost-"][data-res]').forEach(x => {
                        cost[x.dataset.res] = clamp(parseFloat(x.value || '0'), 0, SHORT, 1) || 0;
                    });
                    const used = RES.filter(r => cost[r] > 0).length;
                    if (used > inf.cost_slots) {
                        err.textContent = `This unit can cost at most ${inf.cost_slots} resource${inf.cost_slots === 1 ? '' : 's'}`
                            + ' (each unit has three cost slots, and one holds its population).';
                        return;
                    }
                    err.textContent = '';
                    // Back to what it would get anyway (inherited or the game's): drop the edit.
                    const without = effectiveCost(Object.assign({}, inf, { id: -1 })).cost;
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
            if (kind === 'tech') delete edits.tech_edits[String(inf.id)];
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
                    if (!x.disabled) cost[x.dataset.res] = clamp(parseFloat(x.value || '0'), 0, SHORT, 1) || 0;
                });
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
        load(e) {
            edits = { unit_edits: clone(e && e.unit_edits), tech_edits: clone(e && e.tech_edits) };
            current = null;
            for (const k of Object.keys(stepsCache)) delete stepsCache[k];   // the draft may have changed
        },
        edits: () => clone(edits),
    };
})();
