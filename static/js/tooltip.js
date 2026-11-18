/**
 * tooltip.js — one hover tooltip for the whole site, in the spirit of AoE2's:
 * a bold serif heading on its own line, then the description.
 *
 * Any element with `data-tip` (the description; "\n" starts a new line) and,
 * optionally, `data-tip-title` (the heading) gets it.  One delegated listener
 * serves every grid — vanilla bonus cards, team cards, unique techs, custom
 * cards — so they all behave the same.  Give such an element no `title`, or
 * the browser's own tooltip shows on top of this one.
 *
 *   - appears after 500ms; while one is showing, the next card's appears at
 *     once ("warm"), which is what scanning a grid wants
 *   - follows the cursor, 14px off, flipping at the viewport edges
 *   - never takes the mouse (pointer-events: none), so it can't block a click
 *   - hides on leaving, clicking, scrolling or Escape
 *   - keyboard focus shows it anchored under the element, with
 *     aria-describedby, so the text reaches keyboard and screen-reader users
 *   - off on touch-only devices, which have no hover to end it
 * Text only (textContent): a description is never parsed as HTML.
 */
(() => {
  const DELAY = 500;          // ms before the first tooltip
  const WARM  = 300;          // ms after one hides during which the next is instant
  const GAP   = 14;           // px between cursor and box

  if (window.matchMedia?.("(hover: none)").matches) return;

  let box = null, titleEl = null, bodyEl = null;
  let target = null, timer = null, shown = false, hiddenAt = 0;
  let lastX = 0, lastY = 0;

  function ensureBox() {
    if (box) return;
    box = document.createElement("div");
    box.id = "ef-tooltip";
    box.setAttribute("role", "tooltip");
    titleEl = document.createElement("div");
    titleEl.className = "ef-tooltip-title";
    bodyEl = document.createElement("div");
    bodyEl.className = "ef-tooltip-body";
    box.append(titleEl, bodyEl);
    document.body.appendChild(box);
  }

  function fill(el) {
    ensureBox();
    const title = el.dataset.tipTitle || "";
    titleEl.textContent = title;
    titleEl.hidden = !title;
    bodyEl.replaceChildren(...String(el.dataset.tip || "").split("\n").filter(Boolean).map(line => {
      const p = document.createElement("div");
      p.textContent = line;
      return p;
    }));
  }

  // Beside the cursor, flipped to the other side when it would leave the
  // viewport.  `rect` (keyboard focus) anchors it under an element instead.
  function place(x, y, rect) {
    const w = box.offsetWidth, h = box.offsetHeight;
    const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    let left, top;
    if (rect) {
      left = Math.min(Math.max(8, rect.left), vw - w - 8);
      top  = rect.bottom + 8 + h > vh ? rect.top - h - 8 : rect.bottom + 8;
    } else {
      left = x + GAP + w > vw ? x - GAP - w : x + GAP;
      top  = y + GAP + h > vh ? y - GAP - h : y + GAP;
    }
    box.style.left = `${Math.max(8, left)}px`;
    box.style.top  = `${Math.max(8, top)}px`;
  }

  function show(el, rect) {
    fill(el);
    box.classList.add("is-visible");
    shown = true;
    place(lastX, lastY, rect);
    if (rect) el.setAttribute("aria-describedby", "ef-tooltip");
  }

  function hide() {
    clearTimeout(timer);
    timer = null;
    if (target) target.removeAttribute("aria-describedby");
    target = null;
    if (shown) {
      box.classList.remove("is-visible");
      shown = false;
      hiddenAt = Date.now();
    }
  }

  function arm(el, rect) {
    clearTimeout(timer);
    // A condensed card already shows its full text (builder.js card views).
    if (document.documentElement.dataset.cards && el.matches(".bonus-card")) { hide(); return; }
    target = el;
    if (shown || Date.now() - hiddenAt < WARM) show(el, rect);
    else timer = setTimeout(() => { if (target === el) show(el, rect); }, DELAY);
  }

  document.addEventListener("mouseover", e => {
    const el = e.target.closest?.("[data-tip]");
    if (el === target) return;
    if (!el) { hide(); return; }
    lastX = e.clientX; lastY = e.clientY;
    arm(el);
  });
  document.addEventListener("mousemove", e => {
    lastX = e.clientX; lastY = e.clientY;
    if (shown && target) place(lastX, lastY);
  }, { passive: true });
  document.addEventListener("mouseout", e => {
    // Leaving the page, or the card for something that isn't inside it.
    if (target && (!e.relatedTarget || !target.contains(e.relatedTarget))
        && e.relatedTarget?.closest?.("[data-tip]") !== target) hide();
  });
  document.addEventListener("mousedown", hide, true);
  document.addEventListener("scroll", hide, { capture: true, passive: true });
  // Escape dismisses; Enter/Space usually toggle the card, which re-draws the
  // grid and would leave the box describing an element that is gone.
  document.addEventListener("keydown", e => { if (["Escape", "Enter", " "].includes(e.key)) hide(); });

  document.addEventListener("focusin", e => {
    const el = e.target.closest?.("[data-tip]");
    if (el && el.matches(":focus-visible")) arm(el, el.getBoundingClientRect());
  });
  document.addEventListener("focusout", e => {
    if (target && e.target.closest?.("[data-tip]") === target) hide();
  });
})();
