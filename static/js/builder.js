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
// v4: UT panels now have mode ("vanilla"/"custom"). Old drafts that already have
// a UT built via the effects picker are "custom"; brand-new ones default to "vanilla".
if ((draft._draftVer || 0) < 4) {
  if (draft.castle_ut && !draft.castle_ut.mode) {
    draft.castle_ut.mode = draft.castle_ut.effects?.length ? "custom" : "vanilla";
  }
  if (draft.imperial_ut && !draft.imperial_ut.mode) {
    draft.imperial_ut.mode = draft.imperial_ut.effects?.length ? "custom" : "vanilla";
  }
  draft._draftVer = 4;
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
  try {
    if (currentStep === 2) {
      await loadBonusCatalog();
    }
    if (currentStep === 3) {
      showStep(currentStep + 1);
      renderUUGrid();                                              // immediate: icons+names from fast catalog
      const statsNotice = document.getElementById("uu-stats-loading");
      if (!_uuCatalogHasStats) {
        if (statsNotice) statsNotice.classList.remove("d-none");
        loadUUCatalog()
          .then(() => {
            renderUUGrid();
            if (statsNotice) statsNotice.classList.add("d-none");
            // Refresh stat defaults under overrides inputs if a unit is already selected.
            const selIdx = draft.unique_unit?.km_idx;
            if (selIdx != null) {
              const u = _uuCatalog.find(u => u.km_idx === selIdx);
              if (u) populateUUOverrides(u);
            }
          })
          .catch(console.error);
      }
      return;
    }
    const nextStep = currentStep + 1;
    if (nextStep === 5 || nextStep === 6) {
      await loadBonusCatalog();
      showStep(nextStep);
      initUTPanel(nextStep);
      return;
    }
    if (currentStep < TOTAL_STEPS) showStep(currentStep + 1);
  } catch (err) {
    console.error("btn-next error:", err);
    if (currentStep < TOTAL_STEPS) showStep(currentStep + 1);
  }
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

// Vanilla tech costs loaded from DAT (keyed by km_idx string)
let _castleUtCosts   = {};
let _imperialUtCosts = {};
let _utCostsLoaded   = false;

async function loadUTCosts() {
  if (_utCostsLoaded) return;
  const datPath = draft.dat_path || "";
  if (!datPath) return;
  try {
    const r = await fetch(`/api/builder/ut/costs?dat_path=${encodeURIComponent(datPath)}`);
    const d = await r.json();
    _castleUtCosts   = d.castle   || {};
    _imperialUtCosts = d.imperial || {};
    _utCostsLoaded   = true;
  } catch (e) {
    console.warn("Could not load UT costs:", e);
  }
}

function _utDraft(step) {
  const { key } = UT_STEPS[step];
  if (!draft[key]) draft[key] = { mode: "vanilla", cost: { food: 0, wood: 0, stone: 0, gold: 0 }, time: 60, effects: [] };
  return draft[key];
}

function _formatCostStr(cost, time) {
  const RES = { food: "F", wood: "W", stone: "S", gold: "G" };
  const parts = Object.entries(cost || {})
    .filter(([, v]) => v > 0)
    .map(([r, v]) => `${v}${RES[r]}`);
  return parts.length
    ? `${parts.join(" ")}${time > 0 ? ` · ${time}s` : ""}`
    : "";
}

function _updateUTCostPreview(step) {
  const { key, prefix } = UT_STEPS[step];
  const ut = draft[key] || {};
  const str = _formatCostStr(ut.cost, ut.time);
  const el  = document.getElementById(`${prefix}-cost-preview`);
  if (el) el.textContent = str ? `Cost: ${str}` : "";
}

// ── UT mode: vanilla vs custom ────────────────────────────────────────────────

function _setUTMode(step, mode) {
  const { key, prefix } = UT_STEPS[step];
  const ut = _utDraft(step);
  ut.mode  = mode;
  saveDraft();

  const vanillaSec  = document.getElementById(`${prefix}-vanilla-section`);
  const customSec   = document.getElementById(`${prefix}-custom-section`);
  const sharedSec   = document.getElementById(`${prefix}-shared-section`);
  const effectsSec  = document.getElementById(`${prefix}-effects-section`);

  if (mode === "vanilla") {
    if (vanillaSec) vanillaSec.style.display = "";
    if (customSec)  customSec.style.display  = "none";
    if (effectsSec) effectsSec.style.display = "none";
    // Show shared only if a tech is already selected
    if (ut.vanilla_km_idx != null) {
      if (sharedSec) sharedSec.classList.remove("d-none");
    }
  } else {
    if (vanillaSec) vanillaSec.style.display = "none";
    if (customSec)  customSec.style.display  = "";
    if (effectsSec) effectsSec.style.display = "";
    if (sharedSec)  sharedSec.classList.remove("d-none");
  }

  // Sync radio button state
  const radio = document.querySelector(`input[name="${prefix}-mode"][value="${mode}"]`);
  if (radio) radio.checked = true;
}

// ── UT vanilla grid ───────────────────────────────────────────────────────────

// Singleton floating tooltip for UT cards
let _utTooltipEl = null;
function _getUTTooltip() {
  if (!_utTooltipEl) {
    _utTooltipEl = document.createElement("div");
    _utTooltipEl.id = "ut-card-tooltip";
    document.body.appendChild(_utTooltipEl);
  }
  return _utTooltipEl;
}

function renderUTGrid(step) {
  const { prefix } = UT_STEPS[step];
  const catalog = step === 5 ? _castleUtCatalog : _imperialUtCatalog;
  const costs   = step === 5 ? _castleUtCosts   : _imperialUtCosts;
  const grid    = document.getElementById(`${prefix}-vanilla-grid`);
  if (!grid) return;

  const query = (document.getElementById(`${prefix}-vanilla-search`)?.value || "").toLowerCase();
  const ut    = draft[UT_STEPS[step].key] || {};
  const selId = ut.vanilla_km_idx ?? null;

  let items = catalog;
  if (query) items = items.filter(t => t.name.toLowerCase().includes(query) || t.desc.toLowerCase().includes(query));

  if (!items.length) {
    grid.innerHTML = '<div class="text-muted small fst-italic py-2">No results found.</div>';
    return;
  }

  grid.innerHTML = items.map(t => {
    const sel = t.id === selId ? " selected" : "";
    return `<div class="ut-card${sel}" data-id="${t.id}" data-name="${_esc(t.name)}" data-desc="${_esc(t.desc)}">
      <div class="ut-card-name">${t.name}</div>
      <div class="ut-card-desc">${t.desc}</div>
    </div>`;
  }).join("");

  const tooltip = _getUTTooltip();

  grid.querySelectorAll(".ut-card").forEach(card => {
    card.addEventListener("click", () => {
      selectVanillaTech(step, parseInt(card.dataset.id, 10));
    });
    card.addEventListener("mouseenter", e => {
      const id   = parseInt(card.dataset.id, 10);
      const name = card.dataset.name;
      const desc = card.dataset.desc;
      const c    = costs[String(id)];
      const cStr = c ? _formatCostStr(c.cost, c.time) : "";
      tooltip.innerHTML = `
        <div class="tip-name">${name}</div>
        <div class="tip-desc">${desc}</div>
        ${cStr ? `<div class="tip-cost">${cStr}</div>` : ""}`;
      tooltip.style.display = "block";
      _positionTooltip(tooltip, e);
    });
    card.addEventListener("mousemove", e => _positionTooltip(tooltip, e));
    card.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
  });
}

function _positionTooltip(el, e) {
  const margin = 12;
  const tw = el.offsetWidth, th = el.offsetHeight;
  let x = e.clientX + margin, y = e.clientY + margin;
  if (x + tw > window.innerWidth)  x = e.clientX - tw - margin;
  if (y + th > window.innerHeight) y = e.clientY - th - margin;
  el.style.left = `${x}px`;
  el.style.top  = `${y}px`;
}

function _esc(s) {
  return (s || "").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function selectVanillaTech(step, id) {
  const { key, prefix } = UT_STEPS[step];
  const catalog = step === 5 ? _castleUtCatalog : _imperialUtCatalog;
  const costs   = step === 5 ? _castleUtCosts   : _imperialUtCosts;
  const tech    = catalog.find(t => t.id === id);
  if (!tech) return;

  const ut = _utDraft(step);
  ut.vanilla_km_idx = id;
  ut.name           = tech.name;
  ut.description    = tech.desc;
  ut.effects        = [{ id, multiplier: 1 }];

  const c = costs[String(id)];
  if (c) {
    ut.cost = { ...c.cost };
    ut.time = c.time;
  }
  saveDraft();

  // Populate form fields
  const nameEl = document.getElementById(`${prefix}-name`);
  const descEl = document.getElementById(`${prefix}-desc`);
  if (nameEl) nameEl.value = tech.name;
  if (descEl) descEl.value = tech.desc;
  if (c) {
    ["food", "wood", "stone", "gold"].forEach(r => {
      const el = document.getElementById(`${prefix}-${r}`);
      if (el) el.value = c.cost[r] || 0;
    });
    const timeEl = document.getElementById(`${prefix}-time`);
    if (timeEl) timeEl.value = c.time || 60;
  }

  // Show selected badge + shared section
  const nameSpan  = document.getElementById(`${prefix}-vanilla-name`);
  const selBadge  = document.getElementById(`${prefix}-vanilla-selected`);
  const hint      = document.getElementById(`${prefix}-vanilla-hint`);
  const sharedSec = document.getElementById(`${prefix}-shared-section`);
  if (nameSpan) nameSpan.textContent = tech.name;
  if (selBadge) selBadge.classList.remove("d-none");
  if (hint)     hint.classList.add("d-none");
  if (sharedSec) sharedSec.classList.remove("d-none");

  renderUTGrid(step);
  _updateUTCostPreview(step);
}

// ── initUTPanel ───────────────────────────────────────────────────────────────

function initUTPanel(step) {
  const { key, prefix } = UT_STEPS[step];
  const ut = draft[key] || {};
  const mode = ut.mode || "vanilla";

  // Restore name + desc
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

  // Wire inputs → draft (once)
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
        _updateUTCostPreview(step);
      });
    });
    if (timeEl) timeEl.addEventListener("input", e => {
      _utDraft(step).time = Math.max(0, parseInt(e.target.value, 10) || 0);
      saveDraft();
      _updateUTCostPreview(step);
    });

    // Mode toggle radios
    document.querySelectorAll(`input[name="${prefix}-mode"]`).forEach(radio => {
      radio.addEventListener("change", () => _setUTMode(step, radio.value));
    });

    // Vanilla search filter
    const searchEl = document.getElementById(`${prefix}-vanilla-search`);
    if (searchEl) searchEl.addEventListener("input", () => renderUTGrid(step));

    // "Change" button in vanilla selected badge
    const changeBtn = document.getElementById(`${prefix}-vanilla-change`);
    if (changeBtn) changeBtn.addEventListener("click", () => {
      const ut2 = _utDraft(step);
      delete ut2.vanilla_km_idx;
      ut2.effects = [];
      saveDraft();
      document.getElementById(`${prefix}-vanilla-selected`)?.classList.add("d-none");
      document.getElementById(`${prefix}-vanilla-hint`)?.classList.remove("d-none");
      document.getElementById(`${prefix}-shared-section`)?.classList.add("d-none");
      renderUTGrid(step);
    });

    // Effect search picker (custom mode)
    const utCatalog = step === 5 ? _castleUtCatalog : _imperialUtCatalog;
    wireSearchPicker({
      inputId:   `${prefix}-effect-search`,
      resultsId: `${prefix}-effect-results`,
      catalog:   utCatalog,
      onSelect:  (id) => addUTEffect(step, id),
    });
  }

  // Set initial mode (shows/hides sections) + render grid
  _setUTMode(step, mode);

  // Restore vanilla selection state
  if (mode === "vanilla" && ut.vanilla_km_idx != null) {
    const nameSpan = document.getElementById(`${prefix}-vanilla-name`);
    const selBadge = document.getElementById(`${prefix}-vanilla-selected`);
    const hint     = document.getElementById(`${prefix}-vanilla-hint`);
    if (nameSpan) nameSpan.textContent = ut.name || "";
    if (selBadge) selBadge.classList.remove("d-none");
    if (hint)     hint.classList.add("d-none");
  }

  loadUTCosts().then(() => renderUTGrid(step));
  renderUTEffectSlots(step);
  _updateUTCostPreview(step);
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
let _uuCatalogHasStats = false;

// Simple SVG placeholder used when a unit has no icon
const UU_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='6' fill='%231e293b'/%3E%3Ctext x='32' y='44' text-anchor='middle' font-size='30' fill='%2364748b'%3E%E2%9A%94%3C/text%3E%3C/svg%3E";

// Fast catalog load — no stats, returns immediately. Used at init time so the
// grid can render with icons/names even before the DAT has been parsed.
async function loadUUCatalogFast() {
  if (_uuCatalog.length) return;
  try {
    const res = await fetch("/api/builder/uu/catalog");
    _uuCatalog = await res.json();
  } catch (e) {
    console.warn("Could not load UU catalog (fast):", e);
  }
}

// Stats-enriched catalog load — re-fetches even if the fast version is already
// loaded, to overlay the hover popup stats. Fast when prewarm is done, slow if not.
async function loadUUCatalog() {
  if (_uuCatalogHasStats) return;
  try {
    const datPath = draft.dat_path || "";
    const res  = await fetch(`/api/builder/uu/catalog?dat_path=${encodeURIComponent(datPath)}`);
    _uuCatalog = await res.json();
    _uuCatalogHasStats = true;
  } catch (e) {
    console.warn("Could not load UU catalog:", e);
  }
}

// Update the cost preview line below the UU description textarea
function _updateUUCostPreview(unit) {
  const el = document.getElementById("uu-cost-preview");
  if (!el) return;
  if (!unit) { el.textContent = ""; return; }
  const cost = unit.training_cost;
  el.textContent = cost ? `Training cost will be appended: ${cost}` : "";
}

// Singleton stat popup for UU grid hover
let _uuPopupEl = null;
function _getUUPopup() {
  if (!_uuPopupEl) _uuPopupEl = document.getElementById("uu-stat-popup");
  return _uuPopupEl;
}

function _buildUUPopupHTML(unit) {
  const s = unit.stats;
  const badge = unit.vanilla ? "Vanilla" : "Custom";

  // No stats loaded yet (no dat_path at catalog time)
  if (!s) {
    return `<div class="pop-name">${unit.name}</div>
            <div class="pop-row"><span class="pop-label">Type</span><span class="pop-val">${badge}</span></div>`;
  }

  const b = s.base || {};
  const e = s.elite || {};

  function fmt(bv, ev) {
    if (bv == null && ev == null) return null;
    const bStr = bv != null ? bv : "—";
    const eStr = ev != null ? ev : "—";
    return bStr === eStr ? `${bStr}` : `${bStr} <span class="pop-elite">(${eStr})</span>`;
  }

  const isRanged = s.ranged;
  const atkLabel = isRanged ? "Proj. Attack" : "Attack";

  const rows = [];

  // Cost
  const cost = s.cost || unit.training_cost;
  if (cost) rows.push(`<div class="pop-row"><span class="pop-label">Cost</span><span class="pop-val">${cost}</span></div>`);

  // Core stats — Normal (Elite) pattern
  const hpFmt = fmt(b.hp, e.hp);
  if (hpFmt) rows.push(`<div class="pop-row"><span class="pop-label">HP</span><span class="pop-val">${hpFmt}</span></div>`);

  const atkFmt = fmt(b.attack, e.attack);
  if (atkFmt) rows.push(`<div class="pop-row"><span class="pop-label">${atkLabel}</span><span class="pop-val">${atkFmt}</span></div>`);

  const maFmt = fmt(b.melee_armor, e.melee_armor);
  const paFmt = fmt(b.pierce_armor, e.pierce_armor);
  if (maFmt || paFmt) {
    rows.push(`<div class="pop-row"><span class="pop-label">Armor (M/P)</span><span class="pop-val">${maFmt ?? "—"}/${paFmt ?? "—"}</span></div>`);
  }

  if (isRanged) {
    const rngFmt = fmt(b.range, e.range);
    if (rngFmt) rows.push(`<div class="pop-row"><span class="pop-label">Range</span><span class="pop-val">${rngFmt}</span></div>`);
    if (b.min_range) rows.push(`<div class="pop-row"><span class="pop-label">Min Range</span><span class="pop-val">${b.min_range}</span></div>`);
  }

  if (b.reload_time != null) {
    rows.push(`<div class="pop-row"><span class="pop-label">Reload</span><span class="pop-val">${b.reload_time}s</span></div>`);
  }

  const spdFmt = fmt(b.speed, e.speed);
  if (spdFmt) rows.push(`<div class="pop-row"><span class="pop-label">Speed</span><span class="pop-val">${spdFmt}</span></div>`);

  // Attack bonuses — merge base and elite into a single display
  const baseBons  = b.bonuses || [];
  const eliteBons = e.bonuses || [];
  const allClasses = [...new Set([...baseBons.map(x => x[0]), ...eliteBons.map(x => x[0])])];
  if (allClasses.length) {
    const bonRows = allClasses.map(cls => {
      const bv = baseBons.find(x => x[0] === cls)?.[1] ?? null;
      const ev = eliteBons.find(x => x[0] === cls)?.[1] ?? null;
      const val = fmt(bv ? `+${bv}` : null, ev ? `+${ev}` : null);
      return `<div class="pop-bonus-row"><span class="pop-bonus-name">vs ${cls}</span><span class="pop-bonus-val">${val}</span></div>`;
    });
    rows.push(`<div class="pop-section-label">Bonuses</div>${bonRows.join("")}`);
  }

  // Special traits
  const traits = s.traits || [];
  if (traits.length) {
    const traitRows = traits.map(t => `<div class="pop-trait">${t}</div>`).join("");
    rows.push(`<div class="pop-section-label">Special</div>${traitRows}`);
  }

  return `<div class="pop-name">${unit.name}</div>
          <div class="pop-type">${badge}</div>
          ${rows.join("")}`;
}

function renderUUGrid() {
  const grid       = document.getElementById("uu-grid");
  if (!grid) return;
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
      <div class="uu-card${sel}" data-km-idx="${u.km_idx}">
        ${badge}
        <img class="uu-card-icon" src="${iconSrc}" alt="${u.name}"
             onerror="this.src='${UU_PLACEHOLDER}'">
        <div class="uu-card-name">${u.name}</div>
      </div>`;
  }).join("");

  const popup = _getUUPopup();

  grid.querySelectorAll(".uu-card").forEach(card => {
    const kmIdx = parseInt(card.dataset.kmIdx, 10);
    const unit  = _uuCatalog.find(u => u.km_idx === kmIdx);

    card.addEventListener("click", () => selectUU(kmIdx));

    if (unit) {
      card.addEventListener("mouseenter", e => {
        popup.innerHTML = _buildUUPopupHTML(unit);
        popup.style.display = "block";
        _positionTooltip(popup, e);
      });
      card.addEventListener("mousemove", e => _positionTooltip(popup, e));
      card.addEventListener("mouseleave", () => { popup.style.display = "none"; });
    }
  });
}

function selectUU(kmIdx) {
  const prevIdx = draft.unique_unit?.km_idx;
  const unit = _uuCatalog.find(u => u.km_idx === kmIdx);
  if (!unit) return;

  if (!draft.unique_unit) draft.unique_unit = {};
  // Switching unit → clear any previous overrides and advanced flags
  if (prevIdx != null && prevIdx !== kmIdx) {
    delete draft.unique_unit.overrides;
    delete draft.unique_unit.advanced_flags;
  }
  draft.unique_unit.km_idx = kmIdx;
  saveDraft();
  showUUError(false);

  document.getElementById("uu-no-selection").classList.add("d-none");
  document.getElementById("uu-selected-panel").classList.remove("d-none");

  const iconEl = document.getElementById("uu-selected-icon");
  iconEl.src = unit.icon || UU_PLACEHOLDER;
  iconEl.onerror = () => { iconEl.src = UU_PLACEHOLDER; };
  document.getElementById("uu-selected-name").textContent = unit.name;
  document.getElementById("uu-selected-type").textContent =
    unit.vanilla ? "Vanilla base unit" : "Custom base unit";

  document.getElementById("uu-name-override").value = draft.unique_unit.name       || "";
  document.getElementById("uu-description").value   = draft.unique_unit.description || "";

  _updateUUCostPreview(unit);
  populateUUOverrides(unit);
  renderUUGrid();
}

function clearUU() {
  delete draft.unique_unit;
  saveDraft();
  document.getElementById("uu-no-selection").classList.remove("d-none");
  document.getElementById("uu-selected-panel").classList.add("d-none");
  document.getElementById("uu-overrides-card")?.classList.add("d-none");
  document.getElementById("uu-advanced-card")?.classList.add("d-none");
  renderUUGrid();
}

// ── UU Stat Overrides ─────────────────────────────────────────────────────────

// Each row: { id, statKey (in stats.base/elite), draftKey prefix, hasSuffix }
const _UO_ROWS = [
  { id: "hp",     statKey: "hp",           draftPfx: "hp"     },
  { id: "attack", statKey: "attack",       draftPfx: "attack" },
  { id: "melee",  statKey: "melee_armor",  draftPfx: "melee"  },
  { id: "pierce", statKey: "pierce_armor", draftPfx: "pierce" },
  { id: "range",  statKey: "range",        draftPfx: "range"  },
  { id: "reload", statKey: "reload_time",  draftPfx: "reload" },
  { id: "speed",  statKey: "speed",        draftPfx: "speed"  },
  { id: "train",  statKey: "train_time",   draftPfx: "train"  },
];
const _UO_COSTS = ["food", "wood", "stone", "gold"];

function populateUUOverrides(unit) {
  const card = document.getElementById("uu-overrides-card");
  if (!card) return;
  card.classList.remove("d-none");

  const s  = unit.stats;
  const bv = s?.base  || {};
  const ev = s?.elite || {};

  // Range row visibility
  document.getElementById("uo-row-range").style.display = s?.ranged ? "" : "none";

  // Advanced card
  const advCard = document.getElementById("uu-advanced-card");
  if (advCard) advCard.classList.remove("d-none");
  // Trample only for melee units
  const trampleRow = document.getElementById("ua-row-trample");
  if (trampleRow) trampleRow.style.display = s?.ranged ? "none" : "";
  _uaLoad();

  // Fill default labels
  for (const row of _UO_ROWS) {
    const bDef = bv[row.statKey];
    const eDef = ev[row.statKey];
    const baseDef  = document.getElementById(`uo-${row.id}-base-def`);
    const eliteDef = document.getElementById(`uo-${row.id}-elite-def`);
    if (baseDef)  baseDef.textContent  = bDef  != null ? `Default: ${bDef}`  : "";
    if (eliteDef) eliteDef.textContent = eDef  != null ? `Default: ${eDef}`  : "";
  }

  // Cost default label
  const costStr = s?.cost || unit.training_cost || "";
  const costDef = document.getElementById("uo-cost-def");
  if (costDef) costDef.textContent = costStr ? `Default: ${costStr}` : "";

  // Restore saved values (or clear if switching units)
  const saved = draft.unique_unit?.overrides || {};
  for (const row of _UO_ROWS) {
    const bi = document.getElementById(`uo-${row.id}-base`);
    const ei = document.getElementById(`uo-${row.id}-elite`);
    if (bi)  bi.value  = saved[`${row.draftPfx}_base`]  ?? "";
    if (ei)  ei.value  = saved[`${row.draftPfx}_elite`] ?? "";
  }
  for (const r of _UO_COSTS) {
    const el = document.getElementById(`uo-cost-${r}`);
    if (el) el.value = saved[`cost_${r}`] ?? "";
  }

  _uoUpdateBadge();
}

function clearUUOverrides() {
  if (draft.unique_unit) { delete draft.unique_unit.overrides; saveDraft(); }
  for (const row of _UO_ROWS) {
    const bi = document.getElementById(`uo-${row.id}-base`);
    const ei = document.getElementById(`uo-${row.id}-elite`);
    if (bi) bi.value = "";
    if (ei) ei.value = "";
  }
  for (const r of _UO_COSTS) {
    const el = document.getElementById(`uo-cost-${r}`);
    if (el) el.value = "";
  }
  _uoUpdateBadge();
}

// Minimums enforced in JS (pattern attr only validates visually, not saves).
const _UO_MINS = {
  hp_base: 1, hp_elite: 1, train_base: 1, train_elite: 1,
  reload_base: 0.1, reload_elite: 0.1, speed_base: 0.1, speed_elite: 0.1,
};

const _UO_NON_NEG = new Set([
  "hp_base","hp_elite","attack_base","attack_elite",
  "range_base","range_elite","reload_base","reload_elite",
  "speed_base","speed_elite","train_base","train_elite",
  "cost_food","cost_wood","cost_stone","cost_gold",
]);

function _uoSave(key, rawVal) {
  if (!draft.unique_unit) return;
  if (!draft.unique_unit.overrides) draft.unique_unit.overrides = {};
  let val = rawVal === "" ? null : Number(rawVal);
  if (val !== null && isNaN(val)) val = null;
  if (val !== null && _UO_NON_NEG.has(key) && val < 0) val = 0;
  if (val !== null && key in _UO_MINS && val < _UO_MINS[key]) val = _UO_MINS[key];
  // If the value was clamped, immediately show the corrected number in the field.
  // Skip mid-decimal ("0.") and mid-negative ("-") to avoid interrupting typing.
  if (val !== null && rawVal !== "" && !rawVal.endsWith(".") && rawVal !== "-" && val !== Number(rawVal)) {
    const el = document.getElementById(`uo-${key.replace(/_/g, "-")}`);
    if (el) el.value = val;
  }
  if (val === null) delete draft.unique_unit.overrides[key];
  else              draft.unique_unit.overrides[key] = val;
  saveDraft();
  _uoUpdateBadge();
}

function _uoUpdateBadge() {
  const badge = document.getElementById("uo-badge");
  if (!badge) return;
  const n = Object.keys(draft.unique_unit?.overrides || {}).length;
  if (n > 0) { badge.textContent = `${n} override${n > 1 ? "s" : ""}`; badge.classList.remove("d-none"); }
  else        { badge.classList.add("d-none"); }
}

function _wireUUOverrides() {
  for (const row of _UO_ROWS) {
    document.getElementById(`uo-${row.id}-base`)
      ?.addEventListener("input", e => _uoSave(`${row.draftPfx}_base`,  e.target.value));
    document.getElementById(`uo-${row.id}-elite`)
      ?.addEventListener("input", e => _uoSave(`${row.draftPfx}_elite`, e.target.value));
  }
  for (const r of _UO_COSTS) {
    document.getElementById(`uo-cost-${r}`)
      ?.addEventListener("input", e => _uoSave(`cost_${r}`, e.target.value));
  }
  document.getElementById("btn-clear-overrides")
    ?.addEventListener("click", clearUUOverrides);
  document.getElementById("uu-overrides-body")
    ?.addEventListener("show.bs.collapse", () => document.getElementById("uo-chevron")?.classList.add("fa-rotate-180"));
  document.getElementById("uu-overrides-body")
    ?.addEventListener("hide.bs.collapse", () => document.getElementById("uo-chevron")?.classList.remove("fa-rotate-180"));
}

// ── Advanced flags ────────────────────────────────────────────────────────────

function _uaSetCheck(id, val) {
  const el = document.getElementById(id);
  if (el) el.checked = !!val;
}

function _uaLoad() {
  const flags = draft.unique_unit?.advanced_flags || {};

  _uaSetCheck("ua-no-convert",   flags.no_convert);
  _uaSetCheck("ua-ignore-armor", flags.ignore_armor);
  _uaSetCheck("ua-trample",      flags.trample);

  _uaSetCheck("ua-regen-hp", flags.regen_hp);
  document.querySelector(".ua-regen-inputs")?.classList.toggle("d-none", !flags.regen_hp);
  const ra = document.getElementById("ua-regen-amount");
  const ri = document.getElementById("ua-regen-interval");
  if (ra) ra.value = flags.regen_amount  ?? "";
  if (ri) ri.value = flags.regen_interval ?? "";

  _uaSetCheck("ua-bonus-resist", flags.bonus_dmg_resist);
  document.querySelector(".ua-bonus-resist-inputs")?.classList.toggle("d-none", !flags.bonus_dmg_resist);
  const br = document.getElementById("ua-bonus-resist-pct");
  if (br) br.value = flags.bonus_dmg_resist ?? "";

  _uaSetCheck("ua-charge", flags.charge_pool);
  document.querySelector(".ua-charge-inputs")?.classList.toggle("d-none", !flags.charge_pool);
  const cp = document.getElementById("ua-charge-pool");
  const cr = document.getElementById("ua-charge-rate");
  if (cp) cp.value = flags.charge_pool ?? "";
  if (cr) cr.value = flags.charge_rate  ?? "";

  _uaUpdateBadge();
}

function _uaClear() {
  if (!draft.unique_unit) return;
  delete draft.unique_unit.advanced_flags;
  _uaLoad();
}

function _uaSave(key, val) {
  if (!draft.unique_unit) return;
  if (!draft.unique_unit.advanced_flags) draft.unique_unit.advanced_flags = {};
  if (val === null || val === false || val === "" || val === undefined)
    delete draft.unique_unit.advanced_flags[key];
  else
    draft.unique_unit.advanced_flags[key] = val;
  saveDraft();
  _uaUpdateBadge();
}

// Only count top-level traits (checkbox-gated), not sub-inputs like regen_amount.
const _UA_TOP_FLAGS = new Set(["no_convert","ignore_armor","trample","regen_hp","bonus_dmg_resist","charge_pool"]);

function _uaUpdateBadge() {
  const badge = document.getElementById("ua-badge");
  if (!badge) return;
  const flags = draft.unique_unit?.advanced_flags || {};
  const n = [..._UA_TOP_FLAGS].filter(k => flags[k]).length;
  if (n > 0) { badge.textContent = `${n} flag${n > 1 ? "s" : ""}`; badge.classList.remove("d-none"); }
  else        { badge.classList.add("d-none"); }
}

function _wireUUAdvanced() {
  document.getElementById("ua-no-convert")
    ?.addEventListener("change", e => _uaSave("no_convert", e.target.checked || null));
  document.getElementById("ua-ignore-armor")
    ?.addEventListener("change", e => _uaSave("ignore_armor", e.target.checked || null));
  document.getElementById("ua-trample")
    ?.addEventListener("change", e => _uaSave("trample", e.target.checked || null));
  document.getElementById("ua-regen-hp")?.addEventListener("change", e => {
    _uaSave("regen_hp", e.target.checked || null);
    document.querySelector(".ua-regen-inputs")?.classList.toggle("d-none", !e.target.checked);
  });
  document.getElementById("ua-regen-amount")
    ?.addEventListener("input", e => _uaSave("regen_amount", e.target.value ? Number(e.target.value) : null));
  document.getElementById("ua-regen-interval")
    ?.addEventListener("input", e => _uaSave("regen_interval", e.target.value ? Number(e.target.value) : null));

  document.getElementById("ua-bonus-resist")?.addEventListener("change", e => {
    const pct = Number(document.getElementById("ua-bonus-resist-pct")?.value) || 50;
    _uaSave("bonus_dmg_resist", e.target.checked ? pct : null);
    document.querySelector(".ua-bonus-resist-inputs")?.classList.toggle("d-none", !e.target.checked);
    if (e.target.checked) document.getElementById("ua-bonus-resist-pct")?.focus();
  });
  document.getElementById("ua-bonus-resist-pct")
    ?.addEventListener("input", e => _uaSave("bonus_dmg_resist", e.target.value ? Number(e.target.value) : null));

  document.getElementById("ua-charge")?.addEventListener("change", e => {
    if (e.target.checked) {
      _uaSave("charge_pool", Number(document.getElementById("ua-charge-pool")?.value) || 10);
      _uaSave("charge_rate", Number(document.getElementById("ua-charge-rate")?.value) || 0.25);
    } else {
      _uaSave("charge_pool", null);
      _uaSave("charge_rate", null);
    }
    document.querySelector(".ua-charge-inputs")?.classList.toggle("d-none", !e.target.checked);
    if (e.target.checked) document.getElementById("ua-charge-pool")?.focus();
  });
  document.getElementById("ua-charge-pool")
    ?.addEventListener("input", e => _uaSave("charge_pool", e.target.value ? Number(e.target.value) : null));
  document.getElementById("ua-charge-rate")
    ?.addEventListener("input", e => _uaSave("charge_rate", e.target.value ? Number(e.target.value) : null));

  // Rotate chevron on collapse toggle
  document.getElementById("uu-advanced-body")
    ?.addEventListener("show.bs.collapse",  () => document.getElementById("ua-chevron")?.classList.add("fa-rotate-180"));
  document.getElementById("uu-advanced-body")
    ?.addEventListener("hide.bs.collapse",  () => document.getElementById("ua-chevron")?.classList.remove("fa-rotate-180"));
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

  function _prewarmDat(datPath) {
    if (!datPath) return;
    fetch(`/api/builder/prewarm?dat_path=${encodeURIComponent(datPath)}`).catch(() => {});
  }

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
        _prewarmDat(draft.dat_path);
      } else {
        datStatus.textContent = "Not auto-detected — enter path manually.";
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
  if (draft.dat_path) _prewarmDat(draft.dat_path);
  else detectDat();

  datInput.addEventListener("change", () => {
    draft.dat_path = datInput.value.trim();
    saveDraft();
    _prewarmDat(draft.dat_path);
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

  // Wire UU search + filter + stat overrides
  document.getElementById("uu-search").addEventListener("input", renderUUGrid);
  document.getElementById("uu-filter-type").addEventListener("change", renderUUGrid);
  _wireUUOverrides();
  _wireUUAdvanced();

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

  // Fast catalog load (no stats) — so the grid is ready immediately when the
  // user navigates to step 4. Stats arrive separately via prewarm + loadUUCatalog().
  loadUUCatalogFast().then(() => {
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
