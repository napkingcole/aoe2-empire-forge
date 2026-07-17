/**
 * builder.js — wizard state management for the New Civ builder.
 *
 * Draft is persisted to localStorage under EF_DRAFT_KEY so users can
 * close and reopen the tab without losing work.
 */

const EF_DRAFT_KEY = "ef_builder_draft";
const TOTAL_STEPS  = 8;

// ── Draft helpers ─────────────────────────────────────────────────────────────

function loadDraft() {
  try { return JSON.parse(localStorage.getItem(EF_DRAFT_KEY) || "{}"); }
  catch { return {}; }
}

function saveDraft() {
  localStorage.setItem(EF_DRAFT_KEY, JSON.stringify(draft));
}

let draft = loadDraft();
// Migrate old single team_bonus → team_bonuses array
if (draft.team_bonus && !draft.team_bonuses) {
  draft.team_bonuses = [draft.team_bonus];
  delete draft.team_bonus;
  saveDraft();
}
if (!draft.team_bonuses) draft.team_bonuses = [];
// v2: UT effects now use UT slot IDs (0-59), not civ bonus IDs. Clear old effects.
if ((draft._draftVer || 0) < 2) {
  if (draft.castle_ut)   draft.castle_ut.effects   = [];
  if (draft.imperial_ut) draft.imperial_ut.effects = [];
  draft._draftVer = 2;
  saveDraft();
}
// v3: Multiplier scaling changed from command-duplication to mathematical
// (d**N for EC_MULTIPLY, d*N for EC_ADD). Existing bonus/UT choices are still
// valid; no data to clear — just stamp the new version.
if ((draft._draftVer || 0) < 3) {
  draft._draftVer = 3;
  saveDraft();
}
let currentStep = 1;

// ── Step navigation ───────────────────────────────────────────────────────────

function showStep(n) {
  document.querySelectorAll(".wizard-panel").forEach(p => p.classList.add("d-none"));
  document.getElementById(`panel-${n}`).classList.remove("d-none");

  document.querySelectorAll(".wizard-step").forEach(dot => {
    const s = parseInt(dot.dataset.step, 10);
    dot.classList.toggle("active",    s === n);
    dot.classList.toggle("completed", s < n);
    dot.classList.remove("active");
    if (s === n)   dot.classList.add("active");
    if (s < n)     dot.classList.add("completed");
  });

  const btnPrev = document.getElementById("btn-prev");
  const btnNext = document.getElementById("btn-next");
  btnPrev.disabled = (n === 1);

  if (n === TOTAL_STEPS) {
    btnNext.innerHTML = '<i class="fa-solid fa-download me-1"></i> Generate Mod';
    btnNext.disabled  = true; // disabled until pipeline is wired up
    populateReview();
  } else {
    btnNext.innerHTML = 'Next <i class="fa-solid fa-arrow-right ms-1"></i>';
    btnNext.disabled  = false;
  }

  document.getElementById("step-counter").textContent = `Step ${n} of ${TOTAL_STEPS}`;
  currentStep = n;

  // Scroll to top of wizard area on step change
  document.getElementById(`panel-${n}`).scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("btn-prev").addEventListener("click", () => {
  if (currentStep > 1) showStep(currentStep - 1);
});

document.getElementById("btn-next").addEventListener("click", async () => {
  if (!validateStep(currentStep)) return;
  if (currentStep === 2) {
    await loadBonusCatalog();
  }
  if (currentStep === 3) {
    await loadUUCatalog();
    renderUUGrid();
  }
  const nextStep = currentStep + 1;
  if (nextStep === 5 || nextStep === 6) {
    await loadBonusCatalog();
    showStep(nextStep);
    initUTPanel(nextStep);
    return;
  }
  if (currentStep < TOTAL_STEPS) showStep(currentStep + 1);
});

// Clicking a completed dot lets you jump back
document.querySelectorAll(".wizard-step").forEach(dot => {
  dot.addEventListener("click", () => {
    const target = parseInt(dot.dataset.step, 10);
    if (target < currentStep) {
      showStep(target);
      if (target === 5 || target === 6) initUTPanel(target);
    }
  });
});

// ── Validation ────────────────────────────────────────────────────────────────

function validateStep(n) {
  if (n === 1) {
    const name = document.getElementById("civ-name").value.trim();
    if (!name) {
      document.getElementById("civ-name").classList.add("is-invalid");
      document.getElementById("civ-name").focus();
      return false;
    }
    document.getElementById("civ-name").classList.remove("is-invalid");

    if (!draft.architecture) {
      showArchError(true);
      return false;
    }
    showArchError(false);
  }
  if (n === 4) {
    if (!draft.unique_unit || draft.unique_unit.km_idx == null) {
      showUUError(true);
      return false;
    }
    showUUError(false);
  }
  if (n === 5 || n === 6) {
    const { key, prefix } = UT_STEPS[n];
    const utName = document.getElementById(`${prefix}-name`)?.value.trim() || draft[key]?.name || "";
    if (!utName) {
      const el = document.getElementById(`${prefix}-name`);
      el?.classList.add("is-invalid");
      el?.focus();
      return false;
    }
    document.getElementById(`${prefix}-name`)?.classList.remove("is-invalid");
  }
  return true;
}

function showUUError(show) {
  let err = document.getElementById("uu-error");
  if (!err && show) {
    err = document.createElement("div");
    err.id = "uu-error";
    err.className = "text-danger small mt-2";
    err.textContent = "Please select a Unique Unit before continuing.";
    document.getElementById("uu-grid").after(err);
  }
  if (err) err.style.display = show ? "" : "none";
}

function showArchError(show) {
  let err = document.getElementById("arch-error");
  if (!err && show) {
    err = document.createElement("div");
    err.id = "arch-error";
    err.className = "text-danger small mt-1";
    err.textContent = "Please select an architecture set.";
    document.getElementById("arch-grid").after(err);
  }
  if (err) err.style.display = show ? "" : "none";
}

// ── Step 1: identity inputs → draft ──────────────────────────────────────────

document.getElementById("civ-name").addEventListener("input", e => {
  draft.alias = e.target.value.trim();
  saveDraft();
});

document.getElementById("civ-tagline").addEventListener("input", e => {
  draft.tagline = e.target.value.trim();
  saveDraft();
});

document.getElementById("wonder-select").addEventListener("change", e => {
  draft.wonder = parseInt(e.target.value, 10);
  saveDraft();
});

document.getElementById("castle-select").addEventListener("change", e => {
  draft.castle = parseInt(e.target.value, 10);
  saveDraft();
});

document.getElementById("voice-select").addEventListener("change", e => {
  draft.language = parseInt(e.target.value, 10);
  saveDraft();
});

// ── Emblem upload ─────────────────────────────────────────────────────────────

document.getElementById("emblem-file").addEventListener("change", e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    draft.emblem = ev.target.result; // data URI
    saveDraft();
    renderEmblemPreview(ev.target.result);
  };
  reader.readAsDataURL(file);
});

function renderEmblemPreview(dataUri) {
  const preview = document.getElementById("emblem-preview");
  const wrap    = document.getElementById("emblem-preview-wrap");
  const clearBtn = document.getElementById("emblem-clear");
  preview.src = dataUri;
  wrap.classList.remove("d-none");
  clearBtn.classList.remove("d-none");
}

function clearEmblem() {
  delete draft.emblem;
  saveDraft();
  document.getElementById("emblem-preview").src = "";
  document.getElementById("emblem-preview-wrap").classList.add("d-none");
  document.getElementById("emblem-clear").classList.add("d-none");
  document.getElementById("emblem-file").value = "";
}

// ── Architecture grid ─────────────────────────────────────────────────────────

function renderArchGrid(options) {
  const grid = document.getElementById("arch-grid");
  grid.innerHTML = "";
  options.forEach(opt => {
    const card = document.createElement("div");
    card.className = "arch-card" + (draft.architecture === opt.value ? " selected" : "");
    card.dataset.value = opt.value;
    card.innerHTML = `
      <div class="arch-card-label">${opt.label}</div>
      <div class="arch-card-example">${opt.example}</div>
    `;
    card.addEventListener("click", () => {
      document.querySelectorAll(".arch-card").forEach(c => c.classList.remove("selected"));
      card.classList.add("selected");
      draft.architecture = opt.value;
      saveDraft();
      showArchError(false);
    });
    grid.appendChild(card);
  });
}

// ── Populate selects ──────────────────────────────────────────────────────────

function populateSelect(id, options, currentValue, defaultLabel) {
  const sel = document.getElementById(id);
  sel.innerHTML = "";
  const def = document.createElement("option");
  def.value = -1;
  def.textContent = defaultLabel;
  sel.appendChild(def);
  options.forEach(opt => {
    const o = document.createElement("option");
    o.value = opt.value;
    o.textContent = opt.label;
    if (opt.value === currentValue) o.selected = true;
    sel.appendChild(o);
  });
  if (currentValue === undefined || currentValue === null) sel.value = -1;
}

function populateVoiceSelect(options, currentValue) {
  _voiceOptions = options;
  const sel = document.getElementById("voice-select");
  sel.innerHTML = "";
  options.forEach(opt => {
    const o = document.createElement("option");
    o.value = opt.value;
    o.textContent = opt.label;
    if (opt.value === currentValue) o.selected = true;
    sel.appendChild(o);
  });
  if (currentValue === undefined || currentValue === null) sel.value = 0;
}

// ── Review panel ──────────────────────────────────────────────────────────────

function _costStr(cost) {
  const parts = [];
  if (cost?.food)  parts.push(`${cost.food}<span class="ms-1" style="color:#e07b54;">F</span>`);
  if (cost?.wood)  parts.push(`${cost.wood}<span class="ms-1" style="color:#8a6c3e;">W</span>`);
  if (cost?.stone) parts.push(`${cost.stone}<span class="ms-1" style="color:#9ca3af;">S</span>`);
  if (cost?.gold)  parts.push(`${cost.gold}<span class="ms-1" style="color:#fca311;">G</span>`);
  return parts.length ? parts.join(" / ") : "Free";
}

function _reviewRow(label, value) {
  return `<tr><td class="text-muted small pe-3" style="white-space:nowrap;width:1%">${label}</td><td class="small">${value}</td></tr>`;
}

function populateReview() {
  const el = document.getElementById("review-content");

  // ── Identity ────────────────────────────────────────────────────────────
  const archName = (window._metaArchitectures || [])
    .find(a => a.value === draft.architecture)?.label || `#${draft.architecture}`;

  const civs = window._metaCivs || [];
  const castleName  = draft.castle  != null && draft.castle  >= 0
    ? (civs.find(c => c.value === draft.castle)?.label  || `#${draft.castle}`)
    : "Architecture Default";
  const wonderName  = draft.wonder  != null && draft.wonder  >= 0
    ? (civs.find(c => c.value === draft.wonder)?.label  || `#${draft.wonder}`)
    : "Architecture Default";
  const voiceName = draft.language != null
    ? (_voiceOptions.find(v => v.value === draft.language)?.label || `Voice #${draft.language}`)
    : "Default (Britons)";

  const identityRows = [
    _reviewRow("Name",         draft.alias || "<em class='text-danger'>Not set</em>"),
    _reviewRow("Tagline",      draft.tagline ? `A ${draft.tagline} Civilization` : "<em class='text-muted'>None</em>"),
    _reviewRow("Architecture", draft.architecture ? archName : "<em class='text-danger'>Not set</em>"),
    _reviewRow("Castle Skin",  castleName),
    _reviewRow("Wonder Skin",  wonderName),
    _reviewRow("Voice",        voiceName),
    _reviewRow("Emblem",       draft.emblem ? "&#10003; Uploaded" : "<em class='text-muted'>None</em>"),
  ].join("");

  // ── Tech Tree ───────────────────────────────────────────────────────────
  const treeHtml = draft.tree?.units
    ? `${draft.tree.units.length} units &nbsp;·&nbsp; ${draft.tree.buildings.length} buildings &nbsp;·&nbsp; ${draft.tree.techs.length} techs`
    : "<em class='text-muted'>Not configured (full tree will be used)</em>";

  // ── Bonuses ─────────────────────────────────────────────────────────────
  const bonusItems = (draft.bonuses || []).map(b => {
    const label = (_bonusCatalog.find(c => c.id === b.id) || {}).label || `Bonus #${b.id}`;
    return `<li class="small">${label}${b.multiplier > 1 ? ` <span class='text-muted'>×${b.multiplier}</span>` : ""}</li>`;
  }).join("") || "<li class='text-muted small fst-italic'>None</li>";

  const tbs = draft.team_bonuses || [];
  const tbLabel = tbs.length
    ? `<ul class="mb-0 ps-3">${tbs.map(tb => {
        const lbl = (_teamCatalog.find(c => c.id === tb.id) || {}).label || `Bonus #${tb.id}`;
        return `<li class="small">${lbl}</li>`;
      }).join("")}</ul>`
    : "<em class='text-muted'>None</em>";

  // ── UU ──────────────────────────────────────────────────────────────────
  let uuHtml = "<em class='text-danger'>Not set</em>";
  if (draft.unique_unit?.km_idx != null) {
    const base     = _uuCatalog.find(u => u.km_idx === draft.unique_unit.km_idx);
    const baseName = base?.name || `Unit #${draft.unique_unit.km_idx}`;
    const iconSrc  = base?.icon || UU_PLACEHOLDER;
    const override = draft.unique_unit.name;
    const display  = override || baseName;
    const subtitle = override ? `<div class="text-muted" style="font-size:.7rem;">base: ${baseName}</div>` : "";
    uuHtml = `<div class="d-flex align-items-center gap-2">
      <img src="${iconSrc}" style="width:32px;height:32px;object-fit:contain;background:oklch(from var(--body-bg) calc(l+0.06) c h);border-radius:4px;" onerror="this.src='${UU_PLACEHOLDER}'">
      <div><div>${display}</div>${subtitle}</div>
    </div>`;
  }

  // ── UT helper ───────────────────────────────────────────────────────────
  function utSection(key, label) {
    const ut = draft[key];
    if (!ut?.name) return `<div class="text-muted small fst-italic">Not set</div>`;
    const utCat = key === "castle_ut" ? _castleUtCatalog : _imperialUtCatalog;
    const fx = (ut.effects || []).map(e => {
      const lbl = (utCat.find(c => c.id === e.id) || {}).label || `Effect #${e.id}`;
      return `<li class="small">${lbl}${e.multiplier > 1 ? ` ×${e.multiplier}` : ""}</li>`;
    }).join("") || "<li class='text-muted small fst-italic'>No effects</li>";
    return `
      <div class="fw-semibold small">${ut.name}</div>
      <div class="small text-muted">${_costStr(ut.cost)} &nbsp;·&nbsp; ${ut.time ?? 60}s</div>
      <ul class="mb-0 mt-1 ps-3">${fx}</ul>`;
  }

  el.innerHTML = `
    <div class="row g-3">
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-id-badge me-1" style="color:var(--accent-2)"></i>Identity</div>
          <div class="card-body p-2"><table class="w-100"><tbody>${identityRows}</tbody></table></div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-diagram-project me-1" style="color:var(--accent-2)"></i>Tech Tree</div>
          <div class="card-body p-2 small">${treeHtml}</div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-shield-halved me-1" style="color:var(--accent-2)"></i>Bonuses</div>
          <div class="card-body p-2"><ul class="mb-0 ps-3">${bonusItems}</ul></div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-people-group me-1" style="color:var(--accent-2)"></i>Team Bonuses</div>
          <div class="card-body p-2 small">${tbLabel}</div>
        </div>
      </div>
      <div class="col-12">
        <div class="card" style="border-color: ${draft.dat_path ? 'oklch(from var(--body-bg) calc(l + 0.18) c h)' : '#dc3545'}">
          <div class="card-body p-2 d-flex align-items-center gap-2 small">
            <i class="fa-solid fa-folder-open" style="color:var(--accent-2)"></i>
            <span class="fw-semibold me-2">DAT File:</span>
            ${draft.dat_path
              ? `<span class="font-monospace text-success" style="font-size:.75rem;">${draft.dat_path}</span>`
              : `<span class="text-danger">Not set — go back to Step 1 and enter your DAT file path.</span>`}
          </div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-person-rifle me-1" style="color:var(--accent-2)"></i>Unique Unit</div>
          <div class="card-body p-2">${uuHtml}</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-chess-rook me-1" style="color:var(--accent-2)"></i>Castle UT</div>
          <div class="card-body p-2">${utSection("castle_ut", "Castle UT")}</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card h-100">
          <div class="card-header small fw-semibold"><i class="fa-solid fa-crown me-1" style="color:var(--accent-2)"></i>Imperial UT</div>
          <div class="card-body p-2">${utSection("imperial_ut", "Imperial UT")}</div>
        </div>
      </div>
    </div>
    <details class="mt-3">
      <summary class="small text-muted">Raw draft JSON</summary>
      <pre class="build-log mt-2" style="font-size:.7rem;max-height:200px;overflow:auto">${JSON.stringify(draft, (k, v) => k === "emblem" ? "[image data]" : v, 2)}</pre>
    </details>
  `;

  // Populate replace-civ dropdown from meta (if not already done)
  _populateReplaceCivSelect();
}

function _populateReplaceCivSelect() {
  const sel = document.getElementById("replace-civ-select");
  if (!sel || sel.dataset.populated) return;
  const civs = window._metaCivs || [];
  if (!civs.length) return;
  sel.innerHTML = "";
  // Standard pick list — skip Chronicles civs (value ≥ 52 correspond to newer DLC slots)
  civs.forEach(c => {
    const o = document.createElement("option");
    o.value       = c.label;
    o.textContent = c.label;
    if (c.label === "Goths") o.selected = true;
    sel.appendChild(o);
  });
  sel.dataset.populated = "1";
}

// ── Generate Mod ──────────────────────────────────────────────────────────────

document.getElementById("btn-generate").addEventListener("click", async () => {
  const replaceCiv  = document.getElementById("replace-civ-select")?.value || "Goths";
  const errEl       = document.getElementById("build-error");
  const successEl   = document.getElementById("build-success");
  const formEl      = document.getElementById("build-form");
  const btn         = document.getElementById("btn-generate");

  errEl.classList.add("d-none");
  successEl.classList.add("d-none");
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Building…';

  try {
    const res  = await fetch("/builder/build", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({ draft, replace_civ: replaceCiv, dat_path: draft.dat_path || "" }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || "Build failed.";
      errEl.classList.remove("d-none");
      return;
    }
    // Show download section
    const link = document.getElementById("build-download-link");
    link.href  = data.url;
    document.getElementById("build-download-name").textContent = data.filename || "Download Mod";
    successEl.classList.remove("d-none");
    formEl.classList.add("d-none");
  } catch (e) {
    errEl.textContent = `Network error: ${e.message}`;
    errEl.classList.remove("d-none");
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-hammer me-2"></i>Generate Mod';
  }
});

// ── Bonuses ───────────────────────────────────────────────────────────────────

const MAX_CIV_BONUSES = 6;
let _bonusCatalog      = [];   // [{id, label}]
let _teamCatalog       = [];
let _voiceOptions      = [];   // [{value, label}] stored from meta for review lookup
let _castleUtCatalog   = [];   // [{id, label}] — UT slot IDs for castle UT effects
let _imperialUtCatalog = [];   // [{id, label}] — UT slot IDs for imperial UT effects

async function loadBonusCatalog() {
  if (_bonusCatalog.length) return;
  try {
    const res  = await fetch("/api/builder/bonuses/catalog");
    const data = await res.json();
    _bonusCatalog = data.civ;
    _teamCatalog  = data.team;
  } catch (e) {
    console.warn("Could not load bonus catalog:", e);
  }
}

async function loadUTCatalog() {
  if (_castleUtCatalog.length) return;
  try {
    const r = await fetch("/api/builder/ut/catalog");
    const d = await r.json();
    _castleUtCatalog.push(...d.castle);
    _imperialUtCatalog.push(...d.imperial);
  } catch (e) {
    console.warn("Could not load UT catalog:", e);
  }
}

// Shared search + results logic for both civ and team pickers
function wireSearchPicker({ inputId, resultsId, catalog, onSelect }) {
  const input   = document.getElementById(inputId);
  const results = document.getElementById(resultsId);

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) { results.classList.add("d-none"); results.innerHTML = ""; return; }

    const matches = catalog
      .filter(b => b.label.toLowerCase().includes(q))
      .slice(0, 40);

    if (!matches.length) {
      results.innerHTML = `<div class="bonus-result-item text-muted">No results for "${q}"</div>`;
    } else {
      results.innerHTML = matches.map(b =>
        `<div class="bonus-result-item" data-id="${b.id}">${b.label}</div>`
      ).join("");
      results.querySelectorAll(".bonus-result-item[data-id]").forEach(el => {
        el.addEventListener("click", () => {
          onSelect(parseInt(el.dataset.id, 10), el.textContent);
          input.value = "";
          results.classList.add("d-none");
          results.innerHTML = "";
        });
      });
    }
    results.classList.remove("d-none");
  });

  // Close results when clicking outside
  document.addEventListener("click", e => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.add("d-none");
    }
  }, true);
}

function renderCivBonusSlots() {
  const container = document.getElementById("bonus-slots");
  const hint      = document.getElementById("bonus-empty-hint");
  const bonuses   = draft.bonuses || [];

  // Remove existing slots (not the hint)
  container.querySelectorAll(".bonus-slot").forEach(el => el.remove());

  hint.style.display = bonuses.length ? "none" : "";

  bonuses.forEach((b, idx) => {
    const label = (_bonusCatalog.find(c => c.id === b.id) || {}).label || `Bonus #${b.id}`;
    const slot  = document.createElement("div");
    slot.className = "bonus-slot d-flex align-items-center gap-2";
    slot.innerHTML = `
      <span class="bonus-slot-label flex-grow-1 small">${label}</span>
      <div class="input-group input-group-sm" style="width:auto;">
        <span class="input-group-text" style="background: oklch(from var(--body-bg) calc(l + 0.04) c h); border-color: oklch(from var(--body-bg) calc(l + 0.18) c h); font-size:.75rem; color:var(--accent-3)">×</span>
        <select class="form-select form-select-sm bonus-mult" data-idx="${idx}" style="width:4.5rem;">
          <option value="1" ${b.multiplier===1?'selected':''}>1</option>
          <option value="2" ${b.multiplier===2?'selected':''}>2</option>
          <option value="3" ${b.multiplier===3?'selected':''}>3</option>
        </select>
      </div>
      <button class="btn btn-sm bonus-remove" data-idx="${idx}"
        style="background:transparent; border:1px solid oklch(from var(--body-bg) calc(l + 0.2) c h); color:var(--accent-3); padding:2px 7px; line-height:1.5;"
        title="Remove bonus">✕</button>
    `;
    container.appendChild(slot);
  });

  // Wire multiplier changes
  container.querySelectorAll(".bonus-mult").forEach(sel => {
    sel.addEventListener("change", e => {
      const idx = parseInt(e.target.dataset.idx, 10);
      draft.bonuses[idx].multiplier = parseInt(e.target.value, 10);
      saveDraft();
    });
  });

  // Wire remove buttons
  container.querySelectorAll(".bonus-remove").forEach(btn => {
    btn.addEventListener("click", e => {
      const idx = parseInt(e.target.dataset.idx, 10);
      draft.bonuses.splice(idx, 1);
      saveDraft();
      renderCivBonusSlots();
    });
  });
}

function addCivBonus(id) {
  if (!draft.bonuses) draft.bonuses = [];
  if (draft.bonuses.length >= MAX_CIV_BONUSES) {
    alert(`You can have at most ${MAX_CIV_BONUSES} civilization bonuses.`);
    return;
  }
  if (draft.bonuses.find(b => b.id === id)) {
    alert("That bonus is already selected.");
    return;
  }
  draft.bonuses.push({ id, multiplier: 1 });
  saveDraft();
  renderCivBonusSlots();
}

function renderTeamBonusSlots() {
  const container = document.getElementById("team-bonus-slot");
  const hint      = document.getElementById("team-bonus-empty-hint");
  if (!draft.team_bonuses) draft.team_bonuses = [];
  const tbs = draft.team_bonuses;

  container.querySelectorAll(".bonus-slot").forEach(el => el.remove());
  hint.style.display = tbs.length ? "none" : "";

  tbs.forEach((tb, idx) => {
    const label = (_teamCatalog.find(c => c.id === tb.id) || {}).label || `Team Bonus #${tb.id}`;
    const slot  = document.createElement("div");
    slot.className = "bonus-slot d-flex align-items-center gap-2";
    slot.innerHTML = `
      <span class="bonus-slot-label flex-grow-1 small">${label}</span>
      <div class="input-group input-group-sm" style="width:auto;">
        <span class="input-group-text" style="background: oklch(from var(--body-bg) calc(l + 0.04) c h); border-color: oklch(from var(--body-bg) calc(l + 0.18) c h); font-size:.75rem; color:var(--accent-3)">×</span>
        <select class="form-select form-select-sm tb-mult" data-idx="${idx}" style="width:4.5rem;">
          <option value="1" ${tb.multiplier===1?'selected':''}>1</option>
          <option value="2" ${tb.multiplier===2?'selected':''}>2</option>
          <option value="3" ${tb.multiplier===3?'selected':''}>3</option>
        </select>
      </div>
      <button class="btn btn-sm bonus-remove" data-idx="${idx}"
        style="background:transparent; border:1px solid oklch(from var(--body-bg) calc(l + 0.2) c h); color:var(--accent-3); padding:2px 7px; line-height:1.5;"
        title="Remove team bonus">✕</button>
    `;
    container.appendChild(slot);
  });

  container.querySelectorAll(".tb-mult").forEach(sel => {
    sel.addEventListener("change", e => {
      const idx = parseInt(e.target.dataset.idx, 10);
      draft.team_bonuses[idx].multiplier = parseInt(e.target.value, 10);
      saveDraft();
    });
  });

  container.querySelectorAll(".bonus-remove").forEach(btn => {
    btn.addEventListener("click", e => {
      const idx = parseInt(e.target.dataset.idx, 10);
      draft.team_bonuses.splice(idx, 1);
      saveDraft();
      renderTeamBonusSlots();
    });
  });
}

function setTeamBonus(id) {
  if (!draft.team_bonuses) draft.team_bonuses = [];
  if (!draft.team_bonuses.some(tb => tb.id === id)) {
    draft.team_bonuses.push({ id, multiplier: 1 });
  }
  saveDraft();
  renderTeamBonusSlots();
}

// ── Unique Technologies (Castle + Imperial) ───────────────────────────────────

const MAX_UT_EFFECTS = 5;

// Maps wizard step → { draft key, input prefix }
const UT_STEPS = {
  5: { key: "castle_ut",   prefix: "cut" },
  6: { key: "imperial_ut", prefix: "iut" },
};

function _utDraft(step) {
  const { key } = UT_STEPS[step];
  if (!draft[key]) draft[key] = { cost: { food: 0, wood: 0, stone: 0, gold: 0 }, time: 60, effects: [] };
  return draft[key];
}

function initUTPanel(step) {
  const { key, prefix } = UT_STEPS[step];
  const ut = draft[key] || {};

  // Restore text values
  const nameEl = document.getElementById(`${prefix}-name`);
  const descEl = document.getElementById(`${prefix}-desc`);
  if (nameEl) nameEl.value = ut.name || "";
  if (descEl) descEl.value = ut.description || "";

  // Restore cost + time
  const cost = ut.cost || {};
  ["food", "wood", "stone", "gold"].forEach(r => {
    const el = document.getElementById(`${prefix}-${r}`);
    if (el) el.value = cost[r] ?? 0;
  });
  const timeEl = document.getElementById(`${prefix}-time`);
  if (timeEl) timeEl.value = ut.time ?? 60;

  // Wire inputs → draft (only once; guard with a flag)
  if (!nameEl?._utWired) {
    if (nameEl) {
      nameEl._utWired = true;
      nameEl.addEventListener("input", e => {
        _utDraft(step).name = e.target.value.trim();
        saveDraft();
      });
    }
    if (descEl) descEl.addEventListener("input", e => {
      _utDraft(step).description = e.target.value;
      saveDraft();
    });
    ["food", "wood", "stone", "gold"].forEach(r => {
      const el = document.getElementById(`${prefix}-${r}`);
      if (el) el.addEventListener("input", e => {
        _utDraft(step).cost[r] = Math.max(0, parseInt(e.target.value, 10) || 0);
        saveDraft();
      });
    });
    if (timeEl) timeEl.addEventListener("input", e => {
      _utDraft(step).time = Math.max(0, parseInt(e.target.value, 10) || 0);
      saveDraft();
    });

    // Wire effect search picker with the step-specific UT catalog
    const utCatalog = step === 5 ? _castleUtCatalog : _imperialUtCatalog;
    wireSearchPicker({
      inputId:   `${prefix}-effect-search`,
      resultsId: `${prefix}-effect-results`,
      catalog:   utCatalog,
      onSelect:  (id) => addUTEffect(step, id),
    });
  }

  renderUTEffectSlots(step);
}

function renderUTEffectSlots(step) {
  const { key, prefix } = UT_STEPS[step];
  const ut       = draft[key] || {};
  const effects  = ut.effects || [];
  const container = document.getElementById(`${prefix}-effect-slots`);
  const hint      = document.getElementById(`${prefix}-effect-empty`);

  container.querySelectorAll(".bonus-slot").forEach(el => el.remove());
  hint.style.display = effects.length ? "none" : "";

  const utCatalog = step === 5 ? _castleUtCatalog : _imperialUtCatalog;
  effects.forEach((b, idx) => {
    const label = (utCatalog.find(c => c.id === b.id) || {}).label || `Effect #${b.id}`;
    const slot  = document.createElement("div");
    slot.className = "bonus-slot d-flex align-items-center gap-2";
    slot.innerHTML = `
      <span class="bonus-slot-label flex-grow-1 small">${label}</span>
      <div class="input-group input-group-sm" style="width:auto;">
        <span class="input-group-text" style="background: oklch(from var(--body-bg) calc(l + 0.04) c h); border-color: oklch(from var(--body-bg) calc(l + 0.18) c h); font-size:.75rem; color:var(--accent-3)">×</span>
        <select class="form-select form-select-sm ut-eff-mult" data-idx="${idx}" style="width:4.5rem;">
          <option value="1" ${b.multiplier===1?'selected':''}>1</option>
          <option value="2" ${b.multiplier===2?'selected':''}>2</option>
          <option value="3" ${b.multiplier===3?'selected':''}>3</option>
        </select>
      </div>
      <button class="btn btn-sm ut-eff-remove" data-idx="${idx}"
        style="background:transparent; border:1px solid oklch(from var(--body-bg) calc(l + 0.2) c h); color:var(--accent-3); padding:2px 7px; line-height:1.5;"
        title="Remove effect">✕</button>
    `;
    container.appendChild(slot);
  });

  container.querySelectorAll(".ut-eff-mult").forEach(sel => {
    sel.addEventListener("change", e => {
      const idx = parseInt(e.target.dataset.idx, 10);
      _utDraft(step).effects[idx].multiplier = parseInt(e.target.value, 10);
      saveDraft();
    });
  });
  container.querySelectorAll(".ut-eff-remove").forEach(btn => {
    btn.addEventListener("click", e => {
      const idx = parseInt(e.target.dataset.idx, 10);
      _utDraft(step).effects.splice(idx, 1);
      saveDraft();
      renderUTEffectSlots(step);
    });
  });
}

function addUTEffect(step, id) {
  const ut = _utDraft(step);
  if (!ut.effects) ut.effects = [];
  if (ut.effects.length >= MAX_UT_EFFECTS) {
    alert(`A unique tech can have at most ${MAX_UT_EFFECTS} effects.`);
    return;
  }
  if (ut.effects.find(e => e.id === id)) {
    alert("That effect is already added.");
    return;
  }
  ut.effects.push({ id, multiplier: 1 });
  saveDraft();
  renderUTEffectSlots(step);
}

// ── Unique Unit ───────────────────────────────────────────────────────────────

let _uuCatalog = [];

// Simple SVG placeholder used when a unit has no icon
const UU_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='6' fill='%231e293b'/%3E%3Ctext x='32' y='44' text-anchor='middle' font-size='30' fill='%2364748b'%3E%E2%9A%94%3C/text%3E%3C/svg%3E";

async function loadUUCatalog() {
  if (_uuCatalog.length) return;
  try {
    const res  = await fetch("/api/builder/uu/catalog");
    _uuCatalog = await res.json();
  } catch (e) {
    console.warn("Could not load UU catalog:", e);
  }
}

function renderUUGrid() {
  const grid       = document.getElementById("uu-grid");
  const query      = (document.getElementById("uu-search")?.value || "").toLowerCase();
  const typeFilter = document.getElementById("uu-filter-type")?.value || "all";

  if (!_uuCatalog.length) {
    grid.innerHTML = '<div class="text-muted small fst-italic">No units available.</div>';
    return;
  }

  let items = _uuCatalog;
  if (typeFilter === "vanilla") items = items.filter(u => u.vanilla);
  if (typeFilter === "custom")  items = items.filter(u => !u.vanilla);
  if (query) items = items.filter(u => u.name.toLowerCase().includes(query));

  if (!items.length) {
    grid.innerHTML = '<div class="text-muted small fst-italic py-2">No results found.</div>';
    return;
  }

  const selectedIdx = draft.unique_unit?.km_idx;
  grid.innerHTML = items.map(u => {
    const iconSrc = u.icon || UU_PLACEHOLDER;
    const badge   = u.vanilla
      ? `<span class="uu-badge uu-badge-vanilla">V</span>`
      : `<span class="uu-badge uu-badge-custom">C</span>`;
    const sel = u.km_idx === selectedIdx ? " selected" : "";
    return `
      <div class="uu-card${sel}" data-km-idx="${u.km_idx}" title="${u.name}">
        ${badge}
        <img class="uu-card-icon" src="${iconSrc}" alt="${u.name}"
             onerror="this.src='${UU_PLACEHOLDER}'">
        <div class="uu-card-name">${u.name}</div>
      </div>`;
  }).join("");

  grid.querySelectorAll(".uu-card").forEach(card => {
    card.addEventListener("click", () => selectUU(parseInt(card.dataset.kmIdx, 10)));
  });
}

function selectUU(kmIdx) {
  const unit = _uuCatalog.find(u => u.km_idx === kmIdx);
  if (!unit) return;

  if (!draft.unique_unit) draft.unique_unit = {};
  draft.unique_unit.km_idx = kmIdx;
  saveDraft();
  showUUError(false);

  // Show selected panel, hide the prompt
  document.getElementById("uu-no-selection").classList.add("d-none");
  document.getElementById("uu-selected-panel").classList.remove("d-none");

  const iconEl = document.getElementById("uu-selected-icon");
  iconEl.src = unit.icon || UU_PLACEHOLDER;
  iconEl.onerror = () => { iconEl.src = UU_PLACEHOLDER; };
  document.getElementById("uu-selected-name").textContent = unit.name;
  document.getElementById("uu-selected-type").textContent =
    unit.vanilla ? "Vanilla base unit" : "Custom base unit";

  // Restore saved overrides
  document.getElementById("uu-name-override").value  = draft.unique_unit.name        || "";
  document.getElementById("uu-description").value    = draft.unique_unit.description  || "";

  renderUUGrid();
}

function clearUU() {
  delete draft.unique_unit;
  saveDraft();
  document.getElementById("uu-no-selection").classList.remove("d-none");
  document.getElementById("uu-selected-panel").classList.add("d-none");
  renderUUGrid();
}

// ── Tech tree ─────────────────────────────────────────────────────────────────

// KM's main.js calls this when the user clicks "Save Tech Tree"
window.setTechTree = function (localtree) {
  draft.tree = {
    units:     localtree[0],
    buildings: localtree[1],
    techs:     localtree[2],
  };
  saveDraft();
  updateTreeSummary();
};

function updateTreeSummary() {
  const t = draft.tree;
  if (!t || !t.units) return;
  document.getElementById("tt-summary").classList.remove("d-none");
  document.getElementById("tt-count-units").textContent     = t.units.length;
  document.getElementById("tt-count-buildings").textContent = t.buildings.length;
  document.getElementById("tt-count-techs").textContent     = t.techs.length;
  document.getElementById("btn-open-tree-label").textContent = "Edit Tech Tree";
}

async function populateTtTemplates() {
  try {
    const res  = await fetch("/api/builder/techtree/civs");
    const civs = await res.json();
    const sel  = document.getElementById("tt-template-select");

    // Prepend "current draft" option if user already has a tree
    if (draft.tree && draft.tree.units) {
      const curr = document.createElement("option");
      curr.value = "_current";
      curr.textContent = "— Continue editing current tree —";
      sel.insertBefore(curr, sel.firstChild);
      sel.value = "_current";
    }

    civs.forEach(name => {
      const o  = document.createElement("option");
      o.value  = name;
      o.textContent = name;
      sel.appendChild(o);
    });
  } catch (e) {
    console.warn("Could not load techtree civ list:", e);
  }
}

document.getElementById("btn-open-tree").addEventListener("click", async () => {
  const templateVal = document.getElementById("tt-template-select").value;

  let treeToLoad;

  // If user has a saved tree and chose "current", load it; otherwise fetch template
  if (draft.tree && draft.tree.units && templateVal === "_current") {
    treeToLoad = [draft.tree.units, draft.tree.buildings, draft.tree.techs];
  } else {
    try {
      const url = templateVal === "full"
        ? "/api/builder/techtree?civ=full"
        : `/api/builder/techtree?civ=${encodeURIComponent(templateVal)}`;
      const res  = await fetch(url);
      const data = await res.json();
      treeToLoad = [data.units, data.buildings, data.techs];
    } catch (e) {
      alert("Failed to load tech tree data. Please try again.");
      return;
    }
  }

  // canEdit 3 = builder edit mode (toggle nodes, Save Tech Tree callback)
  showTechtree(treeToLoad, 0, 3, 0, "", "/static");
});

// ── Bootstrap: fetch meta & restore draft ────────────────────────────────────

async function init() {
  try {
    const res  = await fetch("/api/builder/meta");
    const meta = await res.json();

    window._metaArchitectures = meta.architectures;
    window._metaCivs          = meta.civs;

    renderArchGrid(meta.architectures);
    populateSelect("wonder-select", meta.civs, draft.wonder,  "— Architecture Default —");
    populateSelect("castle-select", meta.civs, draft.castle,  "— Architecture Default —");
    populateVoiceSelect(meta.voices, draft.language);

    // Restore text fields
    if (draft.alias)   document.getElementById("civ-name").value    = draft.alias;
    if (draft.tagline) document.getElementById("civ-tagline").value  = draft.tagline;

    // Restore emblem preview
    if (draft.emblem) renderEmblemPreview(draft.emblem);

  } catch (err) {
    console.error("Failed to load builder metadata:", err);
  }

  // ── Game Files (DAT path) ──────────────────────────────────────────────────
  const datInput = document.getElementById("dat-path-input");
  const ctInput  = document.getElementById("civtechtrees-path-input");
  const datStatus = document.getElementById("dat-detect-status");

  async function detectDat() {
    datStatus.textContent = "Detecting…";
    datStatus.className   = "form-text text-muted";
    try {
      const r = await fetch("/api/builder/detect-dat");
      const d = await r.json();
      if (d.found) {
        datInput.value = d.dat_path;
        ctInput.value  = d.civtechtrees_path;
        draft.dat_path          = d.dat_path;
        draft.civtechtrees_path = d.civtechtrees_path;
        saveDraft();
        datStatus.textContent = "✓ Auto-detected";
        datStatus.className   = "form-text text-success";
      } else {
        datStatus.innerHTML   = "Not auto-detected — enter path manually.<br>"
          + "<small>Steam: <code>…/Steam/steamapps/common/AoE2DE/resources/_common/dat/empires2_x2_p1.dat</code><br>"
          + "Microsoft Store: <code>C:\\Program Files\\WindowsApps\\Microsoft.MSPhoenix_[version]\\resources\\_common\\dat\\empires2_x2_p1.dat</code></small>";
        datStatus.className   = "form-text text-warning";
      }
    } catch {
      datStatus.textContent = "Detection failed.";
      datStatus.className   = "form-text text-danger";
    }
  }

  // Restore saved paths from draft; if blank, auto-detect
  if (draft.dat_path)          datInput.value = draft.dat_path;
  if (draft.civtechtrees_path) ctInput.value  = draft.civtechtrees_path;
  if (!draft.dat_path) detectDat();

  datInput.addEventListener("change", () => {
    draft.dat_path = datInput.value.trim();
    saveDraft();
  });
  ctInput.addEventListener("change", () => {
    draft.civtechtrees_path = ctInput.value.trim();
    saveDraft();
  });
  document.getElementById("btn-detect-dat").addEventListener("click", () => {
    draft.dat_path = "";
    draft.civtechtrees_path = "";
    datInput.value = "";
    ctInput.value  = "";
    detectDat();
  });

  // Wire UU search + filter
  document.getElementById("uu-search").addEventListener("input", renderUUGrid);
  document.getElementById("uu-filter-type").addEventListener("change", renderUUGrid);

  document.getElementById("uu-name-override").addEventListener("input", e => {
    if (!draft.unique_unit) return;
    draft.unique_unit.name = e.target.value.trim();
    saveDraft();
  });
  document.getElementById("uu-description").addEventListener("input", e => {
    if (!draft.unique_unit) return;
    draft.unique_unit.description = e.target.value;
    saveDraft();
  });

  await populateTtTemplates();
  updateTreeSummary();

  // Pre-load UU + bonus catalogs in background
  loadUUCatalog().then(() => {
    if (draft.unique_unit?.km_idx != null) {
      selectUU(draft.unique_unit.km_idx);
    }
  });

  Promise.all([loadBonusCatalog(), loadUTCatalog()]).then(() => {
    // Restore UT panels if user had already filled them in a previous session
    if (draft.castle_ut)   initUTPanel(5);
    if (draft.imperial_ut) initUTPanel(6);
    wireSearchPicker({
      inputId:   "bonus-search",
      resultsId: "bonus-results",
      catalog:   _bonusCatalog,
      onSelect:  (id) => addCivBonus(id),
    });
    wireSearchPicker({
      inputId:   "team-bonus-search",
      resultsId: "team-bonus-results",
      catalog:   _teamCatalog,
      onSelect:  (id) => setTeamBonus(id),
    });
    // Restore saved bonuses
    renderCivBonusSlots();
    renderTeamBonusSlots();
  });

  showStep(1);
}

init();
