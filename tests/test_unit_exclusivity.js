// Regional unit mutual-exclusivity checks.
//
// Each _REGIONAL_PAIRS entry names two unit lines that share one building
// button, so the tree must never hold both — the engine gives that cell to one
// of them and the other is simply unreachable, which reads in-game as "my civ
// is missing a unit it clearly has".  _toggleNode evicts the opposing side.
//
// Sweeps every declared pair in both directions rather than spot-checking the
// newest one, so adding a pair without wiring it up fails here.
//
//   node tests/test_unit_exclusivity.js
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');

const src = fs.readFileSync(path.join(ROOT, 'static/aoe2techtree/js/main.js'), 'utf8');
const harness = `
${src}
module.exports = {
  PAIRS: _REGIONAL_PAIRS,
  REGIONAL: _REGIONAL_UNIT_IDS,
  toggle: _toggleNode,
  setLocaltree: (t) => { _localtree = t; },
  getLocaltree: () => _localtree,
  setNodeIndex: (i) => { _nodeIndex = i; },
};
`;
global.window = { showToast: () => {} };
global.document = { getElementById: () => null, querySelectorAll: () => [] };
// Toggling a node off draws a cross over it via SVG.js.  We only care about the
// bookkeeping in _localtree, so hand back a chainable no-op for every draw call.
const svgStub = new Proxy(function () {}, {
  get: () => svgStub,
  apply: () => svgStub,
  construct: () => svgStub,
});
global.SVG = svgStub;
const Module = require('module');
const m = new Module('exclusivity-harness');
m._compile(harness, 'exclusivity-harness.js');
const T = m.exports;

let failures = 0;
function check(label, ok, detail) {
  if (ok) { console.log(`  ok   ${label}`); return; }
  failures++;
  console.log(`  FAIL ${label}${detail ? `\n       ${detail}` : ''}`);
}

// _toggleNode looks opposing units up in _nodeIndex by `${building}_${unit}`.
function nodeFor(bldg, uid) {
  return { use_type: 'Unit', node_id: uid, id: `Unit_${uid}_${bldg}`, building_id: bldg };
}
function indexFor(pair) {
  const idx = {};
  for (const uid of [...pair.a, ...pair.b]) idx[`${pair.bldg}_${uid}`] = nodeFor(pair.bldg, uid);
  return idx;
}

console.log('=== Selecting one side evicts the other ===');
for (const pair of T.PAIRS) {
  for (const [fromName, from, toName, to] of [
    [pair.nameA, pair.a, pair.nameB, pair.b],
    [pair.nameB, pair.b, pair.nameA, pair.a],
  ]) {
    // Start with the opposing side fully selected, then turn on one of ours.
    T.setNodeIndex(indexFor(pair));
    T.setLocaltree({ units: [...to], buildings: [pair.bldg], techs: [] });
    T.toggle(nodeFor(pair.bldg, from[0]), 60);
    const left = T.getLocaltree().units;
    const survivors = to.filter(u => left.includes(u));
    check(`${fromName} evicts ${toName}`, survivors.length === 0,
          `still present: ${survivors.join(', ')}`);
    check(`${fromName} itself stays selected`, left.includes(from[0]));
  }
}

console.log('\n=== Both sides of every pair share one building ===');
for (const pair of T.PAIRS) {
  check(`${pair.nameA} / ${pair.nameB} declare a building`,
        Number.isInteger(pair.bldg) && pair.a.length > 0 && pair.b.length > 0);
}

console.log('\n=== The regional side is excluded from Select All ===');
for (const pair of T.PAIRS) {
  const missing = pair.b.filter(u => !T.REGIONAL.has(u));
  check(`${pair.nameB} is in _REGIONAL_UNIT_IDS`, missing.length === 0,
        `not listed: ${missing.join(', ')}`);
  // The "a" side is the standard one and must NOT be excluded, or a blank civ
  // would silently lose it.
  const wrong = pair.a.filter(u => T.REGIONAL.has(u));
  check(`${pair.nameA} is not in _REGIONAL_UNIT_IDS`, wrong.length === 0,
        `wrongly listed: ${wrong.join(', ')}`);
}

console.log('\n=== Shock infantry (issue #25) ===');
{
  const pair = T.PAIRS.find(p => p.a.includes(1901) && p.b.includes(751));
  check('Fire Lancer / Eagle Warrior pair exists', !!pair);
  if (pair) {
    check('both lines are on Barracks button 4 (building 12)', pair.bldg === 12);
    check('Fire Lancer line covers base and elite',
          [1901, 1903].every(u => pair.a.includes(u)));
    check('Eagle line covers scout, warrior and elite',
          [751, 753, 752].every(u => pair.b.includes(u)));
    // Fire Lancers are the default side — five civs have one, Eagles have two.
    check('Fire Lancers stay in a blank civ', !pair.a.some(u => T.REGIONAL.has(u)));
    check('Eagles are opt-in', pair.b.every(u => T.REGIONAL.has(u)));
  }
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
