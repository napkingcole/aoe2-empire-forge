/**
 * custom_bonuses.js — the custom civ bonus library, shared by two pages:
 *
 *   /builder/custom-bonuses  the library: add, edit, delete, import, export
 *   /builder (wizard)        step 3 picks library cards into the civ
 *
 * A card is one target plus a list of effects, in exactly the shape
 * custom_bonus.py normalises:
 *   {id, target: {type:"group", id:"cavalry"} | {type:"unit", id, name, kind},
 *    effects: [{attr, op, value, resource?}], text}
 *
 * Groups and attributes come from /api/builder/custom-bonus/catalog so the two
 * sides can't drift; cbCardText mirrors custom_bonus.card_text.
 */

let _cbCatalog = null;

async function cbLoadCatalog() {
  if (_cbCatalog) return _cbCatalog;
  try {
    _cbCatalog = await (await fetch("/api/builder/custom-bonus/catalog")).json();
    if (_cbCatalog.allowed_pending) _cbRefreshAllowed(1);
  } catch (e) {
    console.warn("Could not load custom bonus catalog:", e);
  }
  return _cbCatalog;
}

// The per-target effect lists need the game DAT, which may still be loading on
// a first visit; until they arrive every effect of the right kind is offered.
function _cbRefreshAllowed(attempt) {
  if (attempt > 10) return;
  setTimeout(async () => {
    try {
      const c = await (await fetch("/api/builder/custom-bonus/catalog")).json();
      if (c.allowed) _cbCatalog.allowed = c.allowed;
      else _cbRefreshAllowed(attempt + 1);
    } catch (e) { /* keep offering everything */ }
  }, 3000);
}

async function cbLoadLibrary() {
  try {
    return (await (await fetch("/api/custom-bonuses")).json()).bonuses || [];
  } catch (e) {
    console.warn("Could not load custom bonus library:", e);
    return [];
  }
}

const _CB_FASTER = { attack_speed: "attack", train_speed: "train", build_speed: "build", research_speed: "research" };
const _CB_COST    = new Set(["cost", "tech_cost"]);    // attrs with a resource picker

function _cbAttr(id)  { return (_cbCatalog?.attrs || []).find(a => a.id === id); }
function _cbGroup(id) { return (_cbCatalog?.groups || []).find(g => g.id === id); }
function _cbJob(id)   { return (_cbCatalog?.jobs   || []).find(j => j.id === id); }

function cbEsc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function _cbTargetKind(t) {
  if (!t) return "unit";
  if (t.type === "group") return _cbGroup(t.id)?.kind || "unit";
  if (t.type === "job") return "job";
  if (t.type === "tech") return "tech";
  return t.kind === "building" ? "building" : "unit";
}

function _cbTargetLabel(t) {
  if (!t) return "";
  if (t.type === "group") return _cbGroup(t.id)?.label || t.id;
  if (t.type === "job") return _cbJob(t.id)?.label || t.id;
  if (t.type === "tech") return t.name || `Tech ${t.id}`;
  return t.name || `Unit ${t.id}`;
}

function _cbNum(v) { return Number.isInteger(v) ? String(v) : String(+v.toFixed(3)); }

function _cbEffectText(e, target) {
  const a = _cbAttr(e.attr);
  if (a?.novalue) return a.label;                      // "free and instant"
  const v = Number(e.value);
  if (!a || !v) return "";
  if (e.attr === "tech_cost") {
    const res = e.resource || "all";
    return `${v > 0 ? "+" : "-"}${_cbNum(Math.abs(v))}${e.op === "mul" ? "%" : ""} ${res === "all" ? "cost" : res + " cost"}`;
  }
  const sign = v > 0 ? "+" : "-";
  const num  = _cbNum(Math.abs(v));
  if (e.attr === "cost") {
    const res = e.resource || "all";
    return `${sign}${num}% ${res === "all" ? "cost" : res + " cost"}`;
  }
  if (_CB_FASTER[e.attr]) return `${_CB_FASTER[e.attr]} ${num}% ${v > 0 ? "faster" : "slower"}`;
  // A job names its work rate: "gather rate", "build speed", "repair speed".
  const label = e.attr === "work_rate" && target?.type === "job" ? (_cbJob(target.id)?.work || a.label) : a.label;
  if (e.op === "mul") return `${sign}${num}% ${label}`;
  return `${sign}${num} ${label}`;
}

function cbCardText(card) {
  if (card.text) return card.text;
  let subject = _cbTargetLabel(card.target);
  if (card.target?.type === "unit" && card.target.kind !== "building") subject += " line";
  const parts = (card.effects || []).map(e => _cbEffectText(e, card.target)).filter(Boolean);
  return parts.length ? `${subject}: ${parts.join(", ")}` : subject;
}

// Content equality, ignoring the id — "has the library card changed since this
// civ copied it?"
function cbSameCard(a, b) {
  const strip = c => JSON.stringify({ target: c.target, effects: c.effects, text: c.text || "" });
  return strip(a) === strip(b);
}

// ── Editor ───────────────────────────────────────────────────────────────────
// Drives the #cb-editor markup in custom_bonuses.html.  cbOpenEditor(card, onSave)
// edits a copy; onSave(card) receives the cleaned card and returns a promise.

let _cbWork   = null;
let _cbOnSave = null;

// The effects a target can take: its kind's, narrowed to the ones that change
// a stat some unit it reaches has (no garrison space on Villagers, no range on
// a Champion).  Techs and the per-civ "Unique unit" group are not narrowed.
function _cbAttrsFor(target) {
  const kind = _cbTargetKind(target);
  const all = (_cbCatalog?.attrs || []).filter(a => a.kinds.includes(kind));
  const key = !target ? null
    : target.type === "group" ? `group:${target.id}`
    : target.type === "job"   ? `job:${target.id}`
    : target.type === "unit"  ? `${kind}:${target.id}` : null;
  const ok = key && _cbCatalog?.allowed?.[key];
  return ok ? all.filter(a => ok.includes(a.id)) : all;
}

// ── Target picker: Group | Unit | Villager | Building tabs over icon tiles ──
// One tab shows at a time, so only one target can ever be chosen.

let _cbTab      = "group";
let _cbCategory = "";        // Unit tab filter chip ("" = all)

// The Villager tab: everything at once, each job, and Fishing Ships — not a
// villager, but where someone looking for fishing bonuses will look.
const _CB_FISHING_SHIP = 13;

function _cbTabOf(t) {
  if (!t) return _cbTab;
  if (t.type === "job") return "villager";
  if (t.type === "tech") return "tech";
  if (t.type === "group") return _cbGroup(t.id)?.tab || "group";
  if (t.type === "unit" && t.id === _CB_FISHING_SHIP) return "villager";
  return t.kind === "building" ? "building" : "unit";
}

function _cbSameTarget(a, b) {
  return !!a && !!b && a.type === b.type && String(a.id) === String(b.id) && (a.kind || "") === (b.kind || "");
}

function _cbIcon(icon, label) {
  if (!icon) return `<span class="cb-tile-art cb-tile-art--none"><i class="fa-solid fa-question"></i></span>`;
  if (icon.startsWith("fa-")) return `<span class="cb-tile-art cb-tile-art--fa"><i class="fa-solid ${icon}"></i></span>`;
  return `<img class="cb-tile-art" src="${icon}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
}

// Tiles for a tab, with { heading } entries between sections.  Groups carry
// their own tab and section (custom_bonus.GROUPS), so a new group lands in the
// right place without touching this.
function _cbTilesFor(tab) {
  const c = _cbCatalog;
  const groupTile = g => ({ target: { type: "group", id: g.id }, label: g.label, icon: g.icon });
  const sectioned = groups => {
    const out = [];
    let last = null;
    for (const g of groups) {
      if (g.section && g.section !== last) { out.push({ heading: g.section }); last = g.section; }
      out.push(groupTile(g));
    }
    return out;
  };
  if (tab === "group") return sectioned(c.groups.filter(g => g.tab === "group"));
  if (tab === "villager") {
    const all  = c.groups.find(g => g.id === "villagers");
    const ship = c.units.find(u => u.id === _CB_FISHING_SHIP);
    return [
      { target: { type: "group", id: "villagers" }, label: "All villagers", icon: all?.icon },
      ...c.jobs.map(j => ({ target: { type: "job", id: j.id }, label: j.label, icon: j.icon })),
      ...(ship ? [{ target: { type: "unit", id: ship.id, name: ship.name, kind: "unit" },
                    label: "Fishing Ships", icon: ship.icon }] : []),
    ];
  }
  // Unit / Building: this tab's groups first (the civ's own UU; economic,
  // drop-off, ...), then the searchable list.  The search filters both.
  const q = (document.getElementById("cb-search").value || "").trim().toLowerCase();
  const hit = label => !q || label.toLowerCase().includes(q);
  const groups = c.groups.filter(g => g.tab === tab && hit(g.label) && !_cbCategory);
  const pool = ({ unit: c.units, building: c.buildings, tech: c.techs }[tab] || [])
    .filter(x => hit(x.name))
    .filter(x => !_cbCategory || x.category === _cbCategory)
    .map(x => ({ target: x.kind === "tech"
                   ? { type: "tech", id: x.id, name: x.name }
                   : { type: "unit", id: x.id, name: x.name, kind: x.kind },
                 label: x.name, icon: x.icon }));
  if (!groups.length) return pool;
  const listHeading = { unit: "Units", building: "Individual buildings", tech: "Individual techs" }[tab];
  // The Tech tab's groups carry their own sections (Ages, Researched at, ...).
  const head = tab === "tech" ? sectioned(groups) : [{ heading: tab === "unit" ? "Special" : "Groups" }, ...groups.map(groupTile)];
  return [...head, ...(pool.length ? [{ heading: listHeading }, ...pool] : [])];
}

function _cbRenderPicker() {
  // The choice stays visible while browsing another tab.
  const chosen = document.getElementById("cb-target-chosen");
  chosen.innerHTML = _cbWork.target
    ? `<i class="fa-solid fa-check me-1"></i>${cbEsc(_cbTargetLabel(_cbWork.target))}`
    : `<span class="text-muted fw-normal">— pick one below</span>`;
  document.querySelectorAll(".cb-tab").forEach(b => {
    const on = b.dataset.tab === _cbTab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on);
  });
  const searchable = ["unit", "building", "tech"].includes(_cbTab);
  document.getElementById("cb-picker-tools").classList.toggle("d-none", !searchable);
  document.getElementById("cb-search").placeholder =
    { unit: "Search units… e.g. knight", building: "Search buildings… e.g. tower",
      tech: "Search techs… e.g. forging" }[_cbTab] || "Search…";

  const chips = document.getElementById("cb-chips");
  // Only chips that would show something.
  const pool = { unit: _cbCatalog.units, tech: _cbCatalog.techs }[_cbTab] || [];
  const cats = ({ unit: _cbCatalog.unit_categories, tech: _cbCatalog.tech_categories }[_cbTab] || null)
    ?.filter(cat => pool.some(x => x.category === cat.id));
  chips.innerHTML = cats
    ? [{ id: "", label: "All" }, ...cats].map(cat =>
        `<button type="button" class="cb-chip${cat.id === _cbCategory ? " active" : ""}" data-cat="${cat.id}">${cbEsc(cat.label)}</button>`).join("")
    : "";
  chips.querySelectorAll(".cb-chip").forEach(b => b.addEventListener("click", () => {
    _cbCategory = b.dataset.cat;
    _cbRenderPicker();
  }));

  const tiles = _cbTilesFor(_cbTab);
  const grid  = document.getElementById("cb-tiles");
  grid.classList.toggle("cb-tiles--big", !searchable);
  grid.innerHTML = tiles.map((t, i) => {
    if (t.heading) return `<div class="cb-section">${cbEsc(t.heading)}</div>`;
    const on = _cbSameTarget(t.target, _cbWork.target);
    return `<button type="button" class="cb-tile${on ? " selected" : ""}" data-i="${i}" aria-pressed="${on}" title="${cbEsc(t.label)}">
      ${_cbIcon(t.icon, t.label)}<span class="cb-tile-label">${cbEsc(t.label)}</span></button>`;
  }).join("") || `<div class="text-muted small fst-italic p-2">Nothing matches that search.</div>`;
  grid.querySelectorAll(".cb-tile").forEach(el => el.addEventListener("click", () =>
    _cbSetTarget(tiles[parseInt(el.dataset.i, 10)].target)));
}

function _cbTargetHint(t) {
  if (!t) return "";
  if (t.type === "group") {
    return {
      cavalry:       "Includes cavalry archers and mounted gunpowder, just like the game's definition.",
      archers:       "Foot archers, cavalry archers and hand cannoneers — the units Archery armor upgrades cover.",
      foot_soldiers: "Infantry and foot archers.",
      villagers:     "Every villager, whatever job it is doing.",
      buildings:     "Every building, including walls, towers and farms — as the game's building HP bonuses do.",
      gunpowder:     "Every gunpowder unit, unique ones included.",
      military:      "Land military: infantry, archers, cavalry and Petards. Not siege or ships, like the game's definition.",
      unique_unit:   "Whatever unique unit the civ using this card has, base and elite — resolved when the mod is built.",
      drop_off:      "Town Center, Mill, Lumber Camp, Mining Camp, Dock, Settlement, Folwark and Mule Cart.",
      economic:      "The drop-off sites plus Market, Feitoria and Caravanserai.",
      military_buildings: "Barracks, Archery Range, Stable, Siege Workshop and Dock.",
      defensive:     "Every tower (Donjon and Bombard Tower included), Castle and Krepost.",
    }[t.id] || (_cbGroup(t.id)?.section === "Trained at"
      ? "Whatever this civ trains there, unique and regional units included — resolved when the mod is built."
      : "");
  }
  if (t.type === "tech" || _cbGroup(t.id)?.kind === "tech") {
    const g = _cbGroup(t.id);
    if (g?.id === "unique_techs") return "This civ's Castle and Imperial unique techs — resolved when the mod is built.";
    if (g?.section === "Researched at") return "Every tech this civ researches there, resolved when the mod is built. Age advances are separate.";
    if (g?.id === "set_farm") return "Horse Collar, Heavy Plow and Crop Rotation — or their Pasture replacements on a Pasture civ.";
    return "Flat cost changes only touch resources the tech already costs, and never go below zero. " +
           "Free means no cost and no research time, as the game's own free techs do.";
  }
  if (t.type === "job") {
    return "Applies only while a villager does this job. HP, cost and train time aren't offered here: " +
           "HP carries over when a villager changes job, and only the base Villager is ever trained.";
  }
  if (t.kind === "building") {
    return t.id === 45
      ? "Applies to every Dock, including the Malay Harbor it upgrades into."
      : "Applies to every age version of this building.";
  }
  return "Applies to the whole upgrade line and any alternate forms — e.g. Knight also covers Cavalier and Paladin.";
}

function _cbSetTarget(target) {
  _cbWork.target = target;
  document.getElementById("cb-target-hint").textContent = _cbTargetHint(target);
  // Drop effects the new target can't take (movement speed on a building, HP on
  // a villager job) — the server enforces the same list.
  const ok = new Set(_cbAttrsFor(target).map(a => a.id));
  _cbWork.effects = _cbWork.effects.filter(e => ok.has(e.attr));
  if (!_cbWork.effects.length) _cbWork.effects.push(_cbNewEffect());
  _cbError("");
  _cbRenderPicker();
  _cbRenderEffects();
}

function _cbRenderEffects() {
  const wrap  = document.getElementById("cb-effects");
  // A saved card keeps an effect the target no longer offers, so editing it
  // never swaps that effect for another one silently.
  const offered = _cbAttrsFor(_cbWork.target);
  const kept = _cbWork.effects.map(e => e.attr)
    .filter(id => !offered.some(a => a.id === id)).map(_cbAttr).filter(Boolean);
  const attrs = [...offered, ...kept];
  wrap.innerHTML = _cbWork.effects.map((e, i) => {
    const a = _cbAttr(e.attr);
    const job = _cbWork.target?.type === "job" ? _cbJob(_cbWork.target.id) : null;
    const nameOf = x => (x.id === "work_rate" && job) ? job.work : x.label;   // "build speed"
    const attrOpts = attrs.map(x => {
      const n = nameOf(x);
      return `<option value="${x.id}"${x.id === e.attr ? " selected" : ""}>${cbEsc(n.charAt(0).toUpperCase() + n.slice(1))}</option>`;
    }).join("");
    const unitLabel = op => op === "add" ? "flat" : (_CB_FASTER[e.attr] ? "% faster" : "%");
    if (a?.novalue) {
      // Free / instant take no amount.
      return `<div class="cb-effect" data-idx="${i}">
        <select class="form-select form-select-sm cb-attr">${attrOpts}</select>
        <span class="cb-op-fixed small text-muted">${e.attr === "free" ? "no cost, no wait" : "no wait"}</span>
        <button type="button" class="btn btn-sm btn-link text-danger cb-effect-remove" title="Remove effect"><i class="fa-solid fa-xmark"></i></button>
      </div>`;
    }
    const opCtl = a && a.ops.length > 1
      ? `<select class="form-select form-select-sm cb-op">${a.ops.map(op =>
          `<option value="${op}"${op === e.op ? " selected" : ""}>${unitLabel(op)}</option>`).join("")}</select>`
      : `<span class="cb-op-fixed small text-muted">${unitLabel(e.op)}</span>`;
    const resCtl = _CB_COST.has(e.attr)
      ? `<select class="form-select form-select-sm cb-res">${_cbCatalog.cost_resources.map(r =>
          `<option value="${r}"${r === (e.resource || "all") ? " selected" : ""}>${r === "all" ? "all resources" : r}</option>`).join("")}</select>`
      : "";
    return `<div class="cb-effect" data-idx="${i}">
      <select class="form-select form-select-sm cb-attr">${attrOpts}</select>
      <input type="number" step="any" class="form-control form-control-sm cb-value" value="${e.value ?? ""}" placeholder="e.g. ${e.op === "add" ? 2 : 20}">
      ${opCtl}
      ${resCtl}
      <button type="button" class="btn btn-sm btn-link text-danger cb-effect-remove" title="Remove effect"><i class="fa-solid fa-xmark"></i></button>
    </div>`;
  }).join("");

  wrap.querySelectorAll(".cb-effect").forEach(row => {
    const idx = parseInt(row.dataset.idx, 10);
    const e   = _cbWork.effects[idx];
    row.querySelector(".cb-attr").addEventListener("change", ev => {
      e.attr = ev.target.value;
      const a = _cbAttr(e.attr);
      if (!a.ops.includes(e.op)) e.op = a.ops[0];
      if (!_CB_COST.has(e.attr)) delete e.resource;
      if (a.novalue) delete e.value;
      _cbRenderEffects();
    });
    row.querySelector(".cb-value")?.addEventListener("input", ev => {
      const n = parseFloat(ev.target.value);
      e.value = isNaN(n) ? null : n;
      _cbUpdatePreview();
    });
    row.querySelector(".cb-op")?.addEventListener("change", ev => { e.op = ev.target.value; _cbRenderEffects(); });
    row.querySelector(".cb-res")?.addEventListener("change", ev => { e.resource = ev.target.value; _cbUpdatePreview(); });
    row.querySelector(".cb-effect-remove").addEventListener("click", () => {
      _cbWork.effects.splice(idx, 1);
      _cbRenderEffects();
    });
  });
  _cbUpdatePreview();
}

function _cbNewEffect() {
  const used  = new Set(_cbWork.effects.map(e => e.attr));
  const attrs = _cbAttrsFor(_cbWork.target);
  const a = attrs.find(x => !used.has(x.id)) || attrs[0];
  return { attr: a.id, op: a.id === "hp" ? "mul" : a.ops[0], value: null };
}

function _cbUpdatePreview() {
  const textEl = document.getElementById("cb-text");
  const out = cbCardText({ ..._cbWork, text: textEl.value.trim() });
  document.getElementById("cb-preview-text").textContent = _cbWork.target ? `• ${out}` : "—";
  textEl.placeholder = cbCardText({ ..._cbWork, text: "" });
}

async function cbOpenEditor(card, onSave) {
  if (!await cbLoadCatalog()) return;
  _cbOnSave = onSave;
  _cbWork = card ? JSON.parse(JSON.stringify(card)) : { target: null, effects: [], text: "" };
  _cbTab = _cbTabOf(_cbWork.target);
  _cbCategory = "";
  document.getElementById("cb-search").value = "";
  _cbRenderPicker();
  document.getElementById("cb-target-hint").textContent = _cbTargetHint(_cbWork.target);
  document.getElementById("cb-text").value = _cbWork.text || "";
  document.getElementById("cb-error").classList.add("d-none");
  document.getElementById("cb-editor-title").textContent = card ? "Edit bonus" : "New bonus";
  if (!_cbWork.effects.length) _cbWork.effects.push(_cbNewEffect());
  _cbRenderEffects();
  document.getElementById("cb-editor").classList.remove("d-none");
  document.getElementById("cb-new")?.classList.add("d-none");
  document.querySelector(".cb-tab.active")?.focus();
}

function cbCloseEditor() {
  _cbWork = null;
  document.getElementById("cb-editor").classList.add("d-none");
  document.getElementById("cb-new")?.classList.remove("d-none");
}

function _cbError(msg) {
  const err = document.getElementById("cb-error");
  err.textContent = msg;
  err.classList.toggle("d-none", !msg);
}

async function _cbSave() {
  if (!_cbWork.target) return _cbError("Choose who this bonus applies to.");
  const effects = _cbWork.effects.filter(e =>
    _cbAttr(e.attr)?.novalue || (e.value !== null && e.value !== undefined && e.value !== 0 && !isNaN(e.value)));
  if (!effects.length) return _cbError("Add at least one effect with a non-zero amount.");
  const tooLow = effects.find(e => e.op === "mul" && e.value <= -100);
  if (tooLow) return _cbError(`${_cbAttr(tooLow.attr).label} can't go down by 100% or more.`);
  const card = {
    target:  _cbWork.target,
    effects: effects.map(e => {
      if (_cbAttr(e.attr)?.novalue) return { attr: e.attr, op: "set" };
      const out = { attr: e.attr, op: e.op, value: e.value };
      if (_CB_COST.has(e.attr)) out.resource = e.resource || "all";
      return out;
    }),
    text: document.getElementById("cb-text").value.trim(),
  };
  if (_cbWork.id) card.id = _cbWork.id;
  try {
    await _cbOnSave(card);
    cbCloseEditor();
  } catch (e) {
    _cbError(e.message || "Couldn't save that bonus.");
  }
}

function cbWireEditor() {
  document.getElementById("cb-cancel").addEventListener("click", cbCloseEditor);
  document.getElementById("cb-save").addEventListener("click", _cbSave);
  document.getElementById("cb-add-effect").addEventListener("click", () => {
    _cbWork.effects.push(_cbNewEffect());
    _cbRenderEffects();
  });
  document.getElementById("cb-text").addEventListener("input", _cbUpdatePreview);
  document.querySelectorAll(".cb-tab").forEach(b => b.addEventListener("click", () => {
    _cbTab = b.dataset.tab;
    _cbCategory = "";
    document.getElementById("cb-search").value = "";
    _cbRenderPicker();
  }));
  document.getElementById("cb-search").addEventListener("input", _cbRenderPicker);
}

// ── Server writes ────────────────────────────────────────────────────────────

async function cbSaveToLibrary(card) {
  const res  = await fetch("/api/custom-bonuses", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(card),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Couldn't save that bonus.");
  return body;
}

// ── Library page ─────────────────────────────────────────────────────────────

async function _cbLibraryPage() {
  const list   = document.getElementById("cb-library-list");
  const status = document.getElementById("cb-status");
  let library  = [];

  const say = (msg, kind = "muted") => {
    status.className = `small mb-3 text-${kind}`;
    status.textContent = msg;
  };

  async function refresh() {
    const res = await (await fetch("/api/custom-bonuses")).json().catch(() => ({}));
    library = res.bonuses || [];
    if (res.path) document.getElementById("cb-path").textContent = res.path;
    document.getElementById("cb-count").textContent =
      library.length ? `${library.length} bonus${library.length === 1 ? "" : "es"}` : "";
    document.getElementById("cb-export-all").classList.toggle("disabled", !library.length);
    if (!library.length) {
      list.innerHTML = `<div class="text-muted small fst-italic py-3">No custom bonuses yet — make one, or import a file someone shared with you.</div>`;
      return;
    }
    list.innerHTML = library.map(c => `
      <div class="cb-row" data-id="${cbEsc(c.id)}">
        <i class="fa-solid fa-wand-magic-sparkles cb-row-icon"></i>
        <span class="cb-row-text">${cbEsc(cbCardText(c))}</span>
        <a class="btn btn-sm btn-link" href="/api/custom-bonuses/export?ids=${encodeURIComponent(c.id)}" title="Download to share"><i class="fa-solid fa-download"></i></a>
        <button type="button" class="btn btn-sm btn-link cb-edit" title="Edit"><i class="fa-solid fa-pen"></i></button>
        <button type="button" class="btn btn-sm btn-link text-danger cb-remove" title="Delete"><i class="fa-solid fa-trash"></i></button>
      </div>`).join("");
    list.querySelectorAll(".cb-row").forEach(row => {
      const card = library.find(c => c.id === row.dataset.id);
      row.querySelector(".cb-edit").addEventListener("click", () => cbOpenEditor(card, async saved => {
        await cbSaveToLibrary(saved);
        say("Saved. Civs that already use this bonus keep their copy until you update them in the wizard.");
        await refresh();
      }));
      row.querySelector(".cb-remove").addEventListener("click", async () => {
        // Two-click delete rather than confirm() — browser dialogs block automation
        // and read as an error on this page's styling.
        const btn = row.querySelector(".cb-remove");
        if (!btn.dataset.armed) {
          btn.dataset.armed = "1";
          btn.innerHTML = `<span class="small">Delete?</span>`;
          setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.innerHTML = `<i class="fa-solid fa-trash"></i>`; } }, 3000);
          return;
        }
        await fetch(`/api/custom-bonuses/${encodeURIComponent(card.id)}`, { method: "DELETE" });
        say("Deleted. Civs that already use it keep their copy.");
        await refresh();
      });
    });
  }

  cbWireEditor();
  await cbLoadCatalog();
  document.getElementById("cb-new").addEventListener("click", () => cbOpenEditor(null, async card => {
    await cbSaveToLibrary(card);
    say("Saved to your library.", "success");
    await refresh();
  }));

  const fileInput = document.getElementById("cb-import-file");
  document.getElementById("cb-import").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const f = fileInput.files[0];
    fileInput.value = "";
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    const res  = await fetch("/api/custom-bonuses/import", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) return say(body.error || "Import failed.", "danger");
    const bits = [`${body.added} added`];
    if (body.skipped) bits.push(`${body.skipped} already in your library`);
    if (body.invalid) bits.push(`${body.invalid} couldn't be read`);
    say(`Imported ${f.name}: ${bits.join(", ")}.`, body.added ? "success" : "muted");
    await refresh();
  });

  await refresh();
}

if (document.getElementById("cb-library-page")) _cbLibraryPage();
