/*
 * "Advanced: armour classes" — shared by the tech tree's side panel
 * (inspector.js) and the unique unit tab (builder.js).
 *
 * A unit's armour is a list of {class: amount}.  An attacker's bonus against a
 * class reaches the unit only when the unit has that class, reduced by the
 * amount (flat, never below 0).  Edits are {class: amount | "immune"}: only
 * what differs from the game's, "immune" removing the class
 * (civ_overrides.write_armours).  The classes offered, and who deals bonus
 * damage to each, come from /api/builder/damage-classes.
 */
(function () {
    const SHORT = 32767;
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    let classesPromise = null, classesFor = null;
    const openState = {};        // prefix -> open, so a redraw keeps the section open

    function load(datPath) {
        if (!classesPromise || classesFor !== datPath) {
            classesFor = datPath;
            classesPromise = fetch(`/api/builder/damage-classes?dat_path=${encodeURIComponent(datPath || '')}`)
                .then(r => r.json()).then(r => (r.status === 'ok' ? r.classes : []))
                .catch(() => []);
        }
        return classesPromise;
    }

    function injectStyle() {
        if (document.getElementById('armour-classes-style')) return;
        const st = document.createElement('style');
        st.id = 'armour-classes-style';
        st.textContent = `
            .ac-wrap { margin-top: 10px; border-top: 1px solid color-mix(in srgb, currentColor 22%, transparent); padding-top: 6px; }
            .ac-wrap > summary { cursor: pointer; font-weight: 700; font-size: 12px; letter-spacing: .04em; text-transform: uppercase; padding: 4px 0; }
            .ac-intro { font-size: 12px; font-style: italic; opacity: .85; margin: 4px 0 6px; line-height: 1.4; }
            .ac-help { background: none; border: 0; padding: 0; color: inherit; text-decoration: underline; cursor: pointer; font: inherit; font-style: normal; font-weight: 600; }
            .ac-row { padding: 6px 0; border-bottom: 1px dashed color-mix(in srgb, currentColor 18%, transparent); }
            .ac-line { display: grid; grid-template-columns: 1fr 74px auto; gap: 6px; align-items: center; font-size: 12px; }
            .ac-name { font-weight: 600; }
            .ac-cls { opacity: .65; font-weight: 400; white-space: nowrap; }
            .ac-num { width: 100%; padding: 3px 6px; border: 1px solid color-mix(in srgb, currentColor 35%, transparent); border-radius: 4px;
                      background: color-mix(in srgb, Canvas 75%, transparent); color: inherit; font: inherit; font-size: 12px; }
            .ac-num.is-edited { border-color: #b8860b; box-shadow: 0 0 0 1px #b8860b inset; }
            .ac-btn { background: none; border: 1px solid color-mix(in srgb, currentColor 35%, transparent); border-radius: 4px; color: inherit;
                      font-size: 11px; padding: 2px 6px; cursor: pointer; white-space: nowrap; }
            .ac-row.is-stat { opacity: .6; cursor: pointer; }
            .ac-row.is-stat .ac-num { cursor: pointer; }
            .ac-row.is-immune .ac-name { text-decoration: line-through; }
            .ac-immune { font-size: 11px; font-weight: 700; color: #9b1c1c; }
            .ac-who { font-size: 11px; opacity: .8; margin-top: 3px; line-height: 1.45; }
            .ac-who b { font-weight: 600; }
            .ac-add { display: grid; grid-template-columns: 1fr 64px auto; gap: 6px; margin-top: 8px; }
            .ac-add select { font-size: 12px; padding: 3px; border: 1px solid color-mix(in srgb, currentColor 35%, transparent); border-radius: 4px;
                             background: color-mix(in srgb, Canvas 75%, transparent); color: inherit; min-width: 0; }
            .ac-note { font-size: 11.5px; font-style: italic; opacity: .85; margin-top: 8px; line-height: 1.4; }
            dialog.ac-dialog { max-width: 560px; border: 1px solid #7a5c2e; border-radius: 8px; padding: 18px 20px; color: #2b1c08;
                               background: #f6ecd2; box-shadow: 0 10px 40px rgba(0,0,0,.45); font-size: 14px; line-height: 1.5; }
            dialog.ac-dialog::backdrop { background: rgba(20,12,4,.55); }
            dialog.ac-dialog h3 { font-size: 18px; margin: 0 0 8px; }
            dialog.ac-dialog h4 { font-size: 14px; margin: 14px 0 4px; }
            dialog.ac-dialog table { border-collapse: collapse; width: 100%; font-size: 13px; margin: 6px 0; }
            dialog.ac-dialog th, dialog.ac-dialog td { border-bottom: 1px solid rgba(110,75,30,.3); padding: 3px 6px; text-align: left; }
            dialog.ac-dialog ol { padding-left: 20px; margin: 4px 0; }
            dialog.ac-dialog .ac-close { float: right; }
        `;
        document.head.appendChild(st);
    }

    // "How does this work?": the three rules and the Pikeman against a Knight.
    function explain() {
        injectStyle();
        let d = document.getElementById('ac-dialog');
        if (!d) {
            d = document.createElement('dialog');
            d.id = 'ac-dialog';
            d.className = 'ac-dialog';
            d.innerHTML = `<button type="button" class="ac-btn ac-close" aria-label="Close">Close</button>
                <h3>How armour classes work</h3>
                <p>Every unit has a list of <b>armour classes</b>, each with a value, and every attacker has a list of
                <b>attack classes</b>. A hit adds up each attack class the target also has, as
                <i>attack − armour</i>, never below 0. Melee armour (class 4) and pierce armour (class 3) are two of them,
                the two the game shows.</p>
                <h4>A Pikeman hits a Knight</h4>
                <table><thead><tr><th>Class</th><th>Pikeman's attack</th><th>Knight's armour</th><th>Damage</th></tr></thead>
                <tbody><tr><td>Melee (4)</td><td>4</td><td>2</td><td>2</td></tr>
                <tr><td>Cavalry (8)</td><td>+22</td><td>0</td><td>22</td></tr>
                <tr><td colspan="3"><b>Total</b></td><td><b>24</b></td></tr></tbody></table>
                <p>A Long Swordsman has no Cavalry class, so the same Pikeman's +22 is ignored: 4 − 1 = <b>3</b>.</p>
                <h4>Three rules</h4>
                <ol>
                <li><b>Armour is per class, not per attacker.</b> Every anti-cavalry unit attacks class 8, so a value there
                    applies to Pikemen, Camels and Mamelukes alike.</li>
                <li><b>It's a flat subtraction.</b> Cavalry armour 11 takes 11 off every anti-cavalry bonus: the
                    Halberdier's +32 becomes +21, the Pikeman's +22 becomes +11, a Camel Rider's +9 becomes 0.</li>
                <li><b>It only matters against bonus damage.</b> If no attacker has a bonus against the class, it does nothing.
                    To resist a unit with no bonus damage, like the militia line, raise melee or pierce armour instead.</li>
                </ol>
                <h4>Values</h4>
                <p><b>0</b> takes the full bonus (a vanilla Knight's Cavalry armour). A higher value reduces it; a
                negative one adds to it. <b>Immune</b> removes the class, so no bonus against it reaches the unit.
                Adding a class (Cavalry to an infantry unit) makes it a target for those bonuses; it doesn't make it
                that kind of unit for upgrades or bonus cards.</p>`;
            document.body.appendChild(d);
            d.querySelector('.ac-close').addEventListener('click', () => d.close());
            d.addEventListener('click', e => { if (e.target === d) d.close(); });
        }
        d.showModal();
    }

    // Who deals bonus damage to the class, and what's left of it after `value`.
    function whoLine(cls, value, immune) {
        const top = (cls.attackers || []).slice(0, 5);
        if (!top.length) return '<div class="ac-who">No unit deals bonus damage to it.</div>';
        const more = (cls.attackers || []).length - top.length;
        const after = a => immune ? 0 : Math.max(0, a.amount - (value || 0));
        const show = a => (immune || value) ? `<b>${esc(a.name)}</b> +${a.amount} → +${after(a)}` : `<b>${esc(a.name)}</b> +${a.amount}`;
        return `<div class="ac-who">Bonus from: ${top.map(show).join(' · ')}${more > 0 ? ` and ${more} more` : ''}</div>`;
    }

    /*
     * render(el, {classes, game, edits, melee, pierce, onChange, onStat, statsWhere, prefix})
     *   game:   the unit's own armour {class: amount}
     *   edits:  {class: amount | "immune"}
     *   melee, pierce: the values the stat rows show (edited or the game's)
     *   onChange(edits): the new edits (null when none)
     *   onStat("melee" | "pierce"): go to that stat box
     */
    function render(el, o) {
        injectStyle();
        const byCls = Object.fromEntries((o.classes || []).map(c => [String(c.cls), c]));
        const game = o.game || {};
        const edits = Object.assign({}, o.edits || {});
        const offered = new Set(Object.keys(byCls));
        const shownCls = [...new Set([...Object.keys(game), ...Object.keys(edits)])]
            .filter(c => offered.has(c)).sort((a, b) => +a - +b);
        const p = o.prefix || 'ac';
        const where = o.statsWhere || 'in the stats above';

        const statRow = (which, cls, label, val) => `
            <div class="ac-row is-stat" data-stat="${which}" title="Edit ${label.toLowerCase()} ${esc(where)}">
                <div class="ac-line"><span class="ac-name">${label} <span class="ac-cls">· class ${cls}</span></span>
                <input type="text" class="ac-num" value="${esc(val ?? '')}" readonly tabindex="-1" aria-label="${label}">
                <span></span></div></div>`;
        const rows = shownCls.map(c => {
            const cls = byCls[c];
            const e = edits[c];
            const immune = e === 'immune';
            const g = game[c];
            const value = immune ? null : (e !== undefined ? e : g);
            return `<div class="ac-row${immune ? ' is-immune' : ''}">
                <div class="ac-line">
                    <span class="ac-name">${esc(cls.name)} <span class="ac-cls">· class ${c}</span></span>
                    ${immune ? '<span class="ac-immune">Immune</span>' : `
                    <input type="number" class="ac-num${e !== undefined ? ' is-edited' : ''}" data-cls="${c}"
                        step="1" min="${-SHORT}" max="${SHORT}" value="${value ?? ''}"
                        placeholder="${g ?? ''}" aria-label="${esc(cls.name)} armour">`}
                    ${immune ? `<button type="button" class="ac-btn" data-undo="${c}">Undo</button>`
                        : g !== undefined ? `<button type="button" class="ac-btn" data-immune="${c}"
                            title="Remove the class: no ${esc(cls.name.toLowerCase())} bonus reaches it">Immune</button>`
                        : `<button type="button" class="ac-btn" data-drop="${c}" title="Remove this class">×</button>`}
                </div>
                ${whoLine(cls, value, immune)}
                ${g === undefined && !immune ? '<div class="ac-who">Added: not in the game\'s list for this unit.</div>' : ''}
            </div>`;
        }).join('');
        const addable = (o.classes || []).filter(c => !shownCls.includes(String(c.cls)));
        el.innerHTML = `<details class="ac-wrap"${openState[p] ? ' open' : ''}>
            <summary>Advanced: armour classes${Object.keys(edits).length ? ` (${Object.keys(edits).length} edited)` : ''}</summary>
            <div class="ac-intro">Which bonus damage reaches this unit, and how much of it.
                <button type="button" class="ac-help">How does this work?</button></div>
            ${o.extra || ''}
            ${statRow('melee', 4, 'Melee armour', o.melee)}
            ${statRow('pierce', 3, 'Pierce armour', o.pierce)}
            ${rows}
            <div class="ac-add">
                <select id="${p}-add-cls" aria-label="Add an armour class"><option value="">Add a class…</option>
                    ${addable.map(c => `<option value="${c.cls}">${esc(c.name)} (class ${c.cls})</option>`).join('')}</select>
                <input type="number" class="ac-num" id="${p}-add-val" step="1" value="0" aria-label="Its armour">
                <button type="button" class="ac-btn" id="${p}-add">Add</button>
            </div>
            <div class="ac-note">To resist a unit with no bonus damage (like the militia line), raise melee or pierce armour instead.</div>
        </details>`;

        const details = el.querySelector('details');
        details.addEventListener('toggle', () => { openState[p] = details.open; });
        const commit = () => o.onChange(Object.keys(edits).length ? Object.assign({}, edits) : null);
        el.querySelector('.ac-help').addEventListener('click', explain);
        el.querySelectorAll('[data-stat]').forEach(r => r.addEventListener('click', () => o.onStat?.(r.dataset.stat)));
        el.querySelectorAll('input[data-cls]').forEach(inp => inp.addEventListener('change', () => {
            const c = inp.dataset.cls;
            const v = inp.value.trim() === '' ? null : Math.max(-SHORT, Math.min(SHORT, Math.round(+inp.value)));
            if (v === null || Number.isNaN(v)) {
                if (game[c] !== undefined) delete edits[c];
                else edits[c] = 0;                       // an added class stays, at 0
            } else if (v === game[c]) delete edits[c];
            else edits[c] = v;
            commit();
        }));
        el.querySelectorAll('[data-immune]').forEach(b => b.addEventListener('click', () => {
            edits[b.dataset.immune] = 'immune';
            commit();
        }));
        el.querySelectorAll('[data-undo]').forEach(b => b.addEventListener('click', () => {
            delete edits[b.dataset.undo];
            commit();
        }));
        el.querySelectorAll('[data-drop]').forEach(b => b.addEventListener('click', () => {
            delete edits[b.dataset.drop];
            commit();
        }));
        el.querySelector(`#${p}-add`).addEventListener('click', () => {
            const c = el.querySelector(`#${p}-add-cls`).value;
            if (!c) return;
            const v = Math.max(-SHORT, Math.min(SHORT, Math.round(+el.querySelector(`#${p}-add-val`).value || 0)));
            edits[c] = v;
            commit();
        });
    }

    window.ArmourClasses = { load, render, explain };
})();
