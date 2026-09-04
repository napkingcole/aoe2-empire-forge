// Blank-civ seed tree checks — a brand-new draft is seeded from the "full"
// union tree (every civ's nodes merged), so anything the union carries but the
// editor cannot represent silently becomes part of a civ nobody configured.
//
// Two things went wrong that way:
//   * civ-unique buildings (Feitoria, Krepost, Donjon, ...) rode along, and
//     _patch_per_civ_techtree then advertised them in the F2 viewer even though
//     the DAT refuses to enable them  (issue #31)
//   * units behind an "Unlock ..." card rode along, and _deriveUnlockBonuses
//     ticked ~10 bonus cards on a civ the user had just created
//
// This pins _filterFullTree against the real shipped data.json + FULL.json.
//
//   node tests/test_seed_tree.js
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');

let failures = 0;
function check(label, ok, detail) {
  if (ok) { console.log(`  ok   ${label}`); return; }
  failures++;
  console.log(`  FAIL ${label}${detail ? `\n       ${detail}` : ''}`);
}

// ── Pull _filterFullTree out of builder.js ──────────────────────────────────
// builder.js is a browser script that touches the DOM at load, so rather than
// executing all of it we lift the one pure function plus the constant it reads.
const src = fs.readFileSync(path.join(ROOT, 'static/js/builder.js'), 'utf8');

function lift(name, kind) {
  const start = src.indexOf(`${kind} ${name}`);
  if (start === -1) throw new Error(`could not find ${kind} ${name} in builder.js`);
  let depth = 0, seen = false;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{' || src[i] === '[') { depth++; seen = true; }
    else if (src[i] === '}' || src[i] === ']') {
      depth--;
      if (seen && depth === 0) return src.slice(start, i + 1) + (kind === 'const' ? ');' : '');
    }
  }
  throw new Error(`unbalanced ${name}`);
}

// main.js owns the regional-swap sets that _filterFullTree reads.
const mainSrc = fs.readFileSync(path.join(ROOT, 'static/aoe2techtree/js/main.js'), 'utf8');
const regUnitsLine = mainSrc.match(/const _REGIONAL_UNIT_IDS = new Set\(\[[^\]]*\]\);/)[0];
const swapIds = [...mainSrc
  .match(/const _REGIONAL_BUILDING_SWAPS = \[[\s\S]*?\n\];/)[0]
  .matchAll(/\bid:\s*(\d+)/g)].map(m => Number(m[1]));

const harness = `
${regUnitsLine}
const _REGIONAL_BUILDING_IDS = new Set(${JSON.stringify(swapIds)});
let _unlockBonusUnits = UNLOCK_FROM_TEST;
${lift('_CIV_UNIQUE_BUILDING_IDS', 'const')}
${lift('_filterFullTree', 'function')}
module.exports = { _filterFullTree, _CIV_UNIQUE_BUILDING_IDS };
`;

// civ_appender._UNLOCK_UNIT_BONUSES, mirrored by /api/builder/meta. Kept here as
// the id lists only; test_unlock_units_match_backend below pins them to Python.
const UNLOCK = {
  405: [2569, 2571], 406: [1952], 407: [1911], 408: [1974],
  409: [2586, 2587], 410: [2582, 2584], 411: [1962], 412: [1923],
  413: [1751, 1753], 414: [1811], 415: [1750], 416: [1793], 417: [1813],
};

const Module = require('module');
const m = new Module('seed-harness');
m._compile(harness.replace('UNLOCK_FROM_TEST', JSON.stringify(UNLOCK)), 'seed-harness.js');
const T = m.exports;

// ── The real shipped data ───────────────────────────────────────────────────
const td = JSON.parse(fs.readFileSync(
  path.join(ROOT, 'static/aoe2techtree/data/data.json'), 'utf8'));
const union = { units: new Set(), buildings: new Set(), techs: new Set() };
for (const cv of Object.values(td.civs)) {
  (cv.Unit     || []).forEach(id => union.units.add(id));
  (cv.Building || []).forEach(id => union.buildings.add(id));
  (cv.Tech     || []).forEach(id => union.techs.add(id));
}
const seed = T._filterFullTree({
  units:     [...union.units].sort((a, b) => a - b),
  buildings: [...union.buildings].sort((a, b) => a - b),
  techs:     [...union.techs].sort((a, b) => a - b),
});
const seedUnits = new Set(seed.units);
const seedBldgs = new Set(seed.buildings);

console.log('=== A blank civ carries no Unlock-card units ===');
{
  const leaked = Object.entries(UNLOCK)
    .flatMap(([bid, units]) => units.filter(u => seedUnits.has(u)).map(u => `${bid}:${u}`));
  check('no unlock unit survives the seed filter', leaked.length === 0, leaked.join(', '));
  const present = Object.values(UNLOCK).flat().filter(u => union.units.has(u));
  check('the union really does contain them (test would pass vacuously otherwise)',
        present.length > 0, `only ${present.length} of them are in data.json`);
}

console.log('\n=== A blank civ carries no civ-unique buildings ===');
{
  const leaked = [...T._CIV_UNIQUE_BUILDING_IDS].filter(id => seedBldgs.has(id));
  check('no civ-unique building survives the seed filter', leaked.length === 0, leaked.join(', '));

  // Every node-less building in the union is either standard equipment or one
  // we deliberately strip.  A new id appearing here means the data shipped a
  // building the editor cannot represent and nobody classified it.
  const full = JSON.parse(fs.readFileSync(
    path.join(ROOT, 'static/aoe2techtree/data/trees/FULL.json'), 'utf8'));
  const nodeBldgs = new Set(full.buildings.map(b => b.node_id));
  const owners = id => Object.values(td.civs).filter(cv => (cv.Building || []).includes(id)).length;
  const nCivs  = Object.keys(td.civs).length;

  const unclassified = [...union.buildings]
    .filter(id => !nodeBldgs.has(id))
    .filter(id => !T._CIV_UNIQUE_BUILDING_IDS.has(id) && !swapIds.includes(id))
    .filter(id => owners(id) < nCivs / 2);
  check('every node-less minority building is classified',
        unclassified.length === 0,
        `unclassified: ${unclassified.map(id => `${id} (${owners(id)} owners)`).join(', ')}`);
}

console.log('\n=== Standard equipment survives ===');
{
  // Fish Trap is node-less like the unique buildings but 53 civs have it —
  // stripping it would quietly remove Fish Traps from every new civ.
  check('Fish Trap (199) is still seeded', seedBldgs.has(199));
  for (const [id, name] of [[12, 'Barracks'], [45, 'Dock'], [68, 'Mill'],
                            [70, 'House'], [109, 'Town Center'], [584, 'Mining Camp']]) {
    check(`${name} (${id}) is still seeded`, seedBldgs.has(id));
  }
  check('the seed is not empty', seed.units.length > 50 && seed.techs.length > 50,
        `${seed.units.length} units / ${seed.techs.length} techs`);
}

console.log('\n=== Unlock unit table matches the backend ===');
{
  const py = fs.readFileSync(path.join(ROOT, 'civ_appender.py'), 'utf8');
  const block = py.match(/_UNLOCK_UNIT_BONUSES: dict\[int, dict\] = \{[\s\S]*?\n\}/)[0];
  const fromPy = {};
  for (const m of block.matchAll(/^\s*(\d+):[^\n]*"units":\s*\(([^)]*)\)/gm)) {
    fromPy[m[1]] = m[2].split(',').map(s => s.trim()).filter(Boolean).map(Number);
  }
  const norm = o => JSON.stringify(Object.fromEntries(
    Object.entries(o).map(([k, v]) => [k, [...v].sort((a, b) => a - b)])
      .sort((a, b) => Number(a[0]) - Number(b[0]))));
  check('test table equals civ_appender._UNLOCK_UNIT_BONUSES', norm(fromPy) === norm(UNLOCK),
        `python: ${norm(fromPy)}\n       test:   ${norm(UNLOCK)}`);
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
