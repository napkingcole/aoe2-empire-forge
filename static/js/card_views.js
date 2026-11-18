/* Card views — Standard, Condensed, Text only.
 *
 * One choice for every card list (civ and team bonuses, unique techs, custom
 * bonuses), kept in this browser.  It is a class on <html> — data-cards =
 * "condensed" or "text", absent for Standard — and the CSS does the rest
 * (plaster.css "Card views"), so a list never re-renders to change view.
 * efCardViewSwitch() makes the three-way switch each filter bar carries; every
 * copy follows a change made in any of them.
 */
(() => {
  const KEY = "ef.cardView";
  const VIEWS = [
    { id: "",          label: "Standard",  icon: "fa-table-cells-large" },
    { id: "condensed", label: "Condensed", icon: "fa-table-list" },
    { id: "text",      label: "Text only", icon: "fa-align-left" },
  ];

  function current() {
    try {
      const v = localStorage.getItem(KEY) || "";
      return VIEWS.some(x => x.id === v) ? v : "";
    } catch { return ""; }
  }

  function apply(v) {
    if (v) document.documentElement.dataset.cards = v;
    else delete document.documentElement.dataset.cards;
    document.querySelectorAll(".card-view-switch button").forEach(b =>
      b.setAttribute("aria-pressed", String(b.dataset.view === v)));
  }

  function set(v) {
    try { localStorage.setItem(KEY, v); } catch { /* private window: this page only */ }
    apply(v);
    // Lists change height: let anything placed against them (back-to-top) re-measure.
    window.dispatchEvent(new Event("resize"));
  }

  window.efCardViewSwitch = function () {
    const wrap = document.createElement("div");
    wrap.className = "card-view-switch";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Card view");
    const v = current();
    for (const view of VIEWS) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.view = view.id;
      b.title = view.label;
      b.setAttribute("aria-label", view.label);
      b.setAttribute("aria-pressed", String(view.id === v));
      b.innerHTML = `<i class="fa-solid ${view.icon}" aria-hidden="true"></i>`;
      b.addEventListener("click", () => set(view.id));
      wrap.appendChild(b);
    }
    return wrap;
  };

  apply(current());
})();
