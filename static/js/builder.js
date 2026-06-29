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

document.getElementById("btn-next").addEventListener("click", () => {
  if (!validateStep(currentStep)) return;
  if (currentStep < TOTAL_STEPS) showStep(currentStep + 1);
});

// Clicking a completed dot lets you jump back
document.querySelectorAll(".wizard-step").forEach(dot => {
  dot.addEventListener("click", () => {
    const target = parseInt(dot.dataset.step, 10);
    if (target < currentStep) showStep(target);
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
  return true;
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

function populateReview() {
  const el = document.getElementById("review-content");
  const rows = [
    ["Civ Name",      draft.alias       || "<em class='text-danger'>Not set</em>"],
    ["Tagline",       draft.tagline     ? `A ${draft.tagline} Civilization` : "<em class='text-muted'>None</em>"],
    ["Architecture",  draft.architecture ? `#${draft.architecture}` : "<em class='text-danger'>Not set</em>"],
    ["Voice",         draft.language    != null ? `Voice ${draft.language}` : "<em class='text-muted'>Default</em>"],
    ["Wonder Skin",   draft.wonder      != null && draft.wonder >= 0 ? `Civ #${draft.wonder}` : "Architecture default"],
    ["Castle Skin",   draft.castle      != null && draft.castle >= 0 ? `Civ #${draft.castle}` : "Architecture default"],
    ["Emblem",        draft.emblem      ? "Uploaded" : "<em class='text-muted'>None (placeholder)</em>"],
  ];
  el.innerHTML = `
    <table class="table table-sm mb-3">
      <tbody>
        ${rows.map(([k, v]) => `<tr><td class="text-muted" style="width:40%">${k}</td><td>${v}</td></tr>`).join("")}
      </tbody>
    </table>
    <details>
      <summary class="small text-muted">Raw draft JSON</summary>
      <pre class="build-log mt-2" style="font-size:0.72rem">${JSON.stringify(draft, (k, v) => k === "emblem" ? "[image data]" : v, 2)}</pre>
    </details>
  `;
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

  await populateTtTemplates();
  updateTreeSummary();

  showStep(1);
}

init();
