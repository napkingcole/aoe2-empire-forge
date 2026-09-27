// Regional unit line checks.
//
// Each _REGIONAL_GROUPS entry names the unit lines that share ONE building
// button.  They used to be mutually exclusive — _toggleNode evicted every other
// line in the group — because the engine drew one line per cell.  Since
// 2026-09-26 the build moves every line after the first to the building's
// second page, so lines coexist; what the table still decides is which line a
// blank civ starts with, and which techs belong to a line (Cranequins).
//
//   node tests/test_unit_exclusivity.js
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');

const src = fs.readFileSync(path.join(ROOT, 'static/aoe2techtree/js/main.js'), 'utf8');
const harness = `
${src}
module.exports = {
  GROUPS: _REGIONAL_GROUPS,
  REGIONAL: _REGIONAL_UNIT_IDS,
  LINE_TECHS: _REGIONAL_LINE_TECH_IDS,
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

// _toggleNode looks nodes up in _nodeIndex by `${building}_${node_id}`.
const unitNode = (bldg, uid) =>
  ({ use_type: 'Unit', node_id: uid, id: `Unit_${uid}_${bldg}`, building_id: bldg });
const techNode = (bldg, tid) =>
  ({ use_type: 'Tech', node_id: tid, id: `Tech_${tid}_${bldg}`, building_id: bldg });

function indexFor(group) {
  const idx = {};
  for (const line of group.lines) {
    for (const uid of line.ids) idx[`${group.bldg}_${uid}`] = unitNode(group.bldg, uid);
    for (const tid of (line.techs || [])) idx[`${group.bldg}_${tid}`] = techNode(group.bldg, tid);
  }
  return idx;
}
const allUnits  = (g) => g.lines.flatMap(l => l.ids);
const allTechs  = (g) => g.lines.flatMap(l => l.techs || []);
const groupName = (g) => g.lines.map(l => l.name).join(' / ');

console.log('=== Lines that share a button no longer evict each other ===');
for (const group of T.GROUPS) {
  for (const line of group.lines) {
    // Start with every OTHER line selected, then tick this one: all of them
    // must survive.  (Only the others — _toggleNode toggles, so a line already
    // on would be switched off.)
    const rivals = group.lines.filter(l => l !== line);
    T.setNodeIndex(indexFor(group));
    T.setLocaltree({
      units: rivals.flatMap(l => l.ids),
      buildings: [group.bldg],
      techs: rivals.flatMap(l => l.techs || []),
    });
    T.toggle(unitNode(group.bldg, line.ids[0]), 60);

    const t = T.getLocaltree();
    const lost = rivals.flatMap(l => l.ids).filter(u => !t.units.includes(u));
    check(`[${groupName(group)}] ${line.name} leaves the other lines selected`,
          lost.length === 0, `removed: ${lost.join(', ')}`);
    const lostTechs = rivals.flatMap(l => l.techs || []).filter(x => !t.techs.includes(x));
    check(`[${groupName(group)}] ${line.name} leaves their line-techs alone`,
          lostTechs.length === 0, `removed: ${lostTechs.join(', ')}`);
    check(`[${groupName(group)}] ${line.name} itself is selected`, t.units.includes(line.ids[0]));
  }
}

console.log('\n=== Every group is well-formed ===');
for (const group of T.GROUPS) {
  check(`[${groupName(group)}] declares a building and 2+ lines`,
        Number.isInteger(group.bldg) && group.lines.length >= 2);
  check(`[${groupName(group)}] every line has at least one unit`,
        group.lines.every(l => l.ids.length > 0));
  const standards = group.lines.filter(l => l.standard);
  check(`[${groupName(group)}] exactly one line is the standard side`,
        standards.length === 1,
        `standard lines: ${standards.map(l => l.name).join(', ') || '(none)'}`);
}

console.log('\n=== One building button is contested by one group only ===');
// Two groups may share a building (Barracks holds both the Militia/Champi and
// the shock-infantry buttons), but a unit must never appear in two groups, or
// its line's techs would belong to two owners.
{
  const seen = new Map();
  let dupes = [];
  for (const g of T.GROUPS) for (const uid of allUnits(g)) {
    if (seen.has(uid)) dupes.push(uid); else seen.set(uid, g);
  }
  check('no unit appears in two groups', dupes.length === 0,
        `duplicated: ${[...new Set(dupes)].join(', ')}`);
}

console.log('\n=== Opt-in lines are excluded from "Enable All" ===');
for (const group of T.GROUPS) {
  for (const line of group.lines) {
    const listed = line.ids.filter(u => T.REGIONAL.has(u));
    if (line.standard) {
      // The standard line must NOT be excluded, or a blank civ loses it.
      check(`${line.name} (standard) stays in a blank civ`, listed.length === 0,
            `wrongly listed: ${listed.join(', ')}`);
    } else {
      check(`${line.name} is opt-in`, listed.length === line.ids.length,
            `not listed: ${line.ids.filter(u => !T.REGIONAL.has(u)).join(', ')}`);
    }
    const techMissing = (line.techs || []).filter(t => !T.LINE_TECHS.has(t));
    check(`${line.name} line-techs are registered`, techMissing.length === 0,
          `not listed: ${techMissing.join(', ')}`);
  }
}

console.log('\n=== Shock infantry: Barracks button 4 (issue #25 + Viking Sagas) ===');
{
  const g = T.GROUPS.find(x => x.lines.some(l => l.ids.includes(1901)));
  check('Fire Lancer / Eagle / Varangian Guard group exists', !!g);
  if (g) {
    check('all three sit on the Barracks (building 12)', g.bldg === 12);
    check('three lines contest the button', g.lines.length === 3,
          `${g.lines.length} lines`);
    check('Fire Lancer line covers base and elite',
          [1901, 1903].every(u => g.lines.some(l => l.ids.includes(u))));
    check('Eagle line covers scout, warrior and elite',
          [751, 753, 752].every(u => g.lines.some(l => l.ids.includes(u))));
    check('Varangian Guard covers base (2703) and elite (2704)',
          [2703, 2704].every(u => g.lines.some(l => l.ids.includes(u))));
    check('Fire Lancers are still the default side',
          g.lines.find(l => l.ids.includes(1901)).standard === true);
    check('the Varangian Guard is opt-in',
          [2703, 2704].every(u => T.REGIONAL.has(u)));
  }
}

console.log('\n=== Mounted Crossbowman: Archery Range button 3 ===');
{
  const g = T.GROUPS.find(x => x.lines.some(l => l.ids.includes(2700)));
  check('Cavalry Archer / Elephant Archer / Mounted Crossbowman group exists', !!g);
  if (g) {
    check('all three sit on the Archery Range (building 87)', g.bldg === 87);
    check('three lines contest the button', g.lines.length === 3);
    check('Cavalry Archers are still the default side',
          g.lines.find(l => l.ids.includes(39)).standard === true);
    const mx = g.lines.find(l => l.ids.includes(2700));
    check('Mounted Crossbowman covers base (2700) and heavy (2701)',
          [2700, 2701].every(u => mx.ids.includes(u)));

    // Cranequins upgrades the Mounted Crossbowman and nothing else.
    check('Cranequins (1452) belongs to the Mounted Crossbowman line',
          (mx.techs || []).includes(1452), `techs: ${JSON.stringify(mx.techs)}`);
    check('no other line claims Cranequins',
          g.lines.filter(l => (l.techs || []).includes(1452)).length === 1);

    // Cranequins needs the Mounted Crossbowman and nothing else (the user,
    // 2026-09-27): not the Heavy upgrade, and not Parthian Tactics, which the
    // game's layout links it to for drawing only.
    T.setNodeIndex(indexFor(g));
    T.setLocaltree({ units: [39, 474], buildings: [87], techs: [] });
    T.toggle(techNode(87, 1452), 60);
    let t = T.getLocaltree();
    check('ticking Cranequins pulls in the Mounted Crossbowman', t.units.includes(2700),
          `units: ${t.units.join(', ')}`);
    check('...but not the Heavy Mounted Crossbowman', !t.units.includes(2701));
    check('...and keeps the Cavalry Archers', [39, 474].every(u => t.units.includes(u)));

    T.setLocaltree({ units: [2700, 2701], buildings: [87], techs: [1452] });
    T.toggle(unitNode(87, 2701), 60);
    check('unticking the Heavy Mounted Crossbowman keeps Cranequins',
          T.getLocaltree().techs.includes(1452));
    T.toggle(unitNode(87, 2701), 60);
    check('...and ticking it again leaves Cranequins as it was',
          T.getLocaltree().techs.includes(1452) && T.getLocaltree().units.includes(2701));
    T.setLocaltree({ units: [2700, 2701], buildings: [87], techs: [] });
    T.toggle(unitNode(87, 2701), 60);
    T.toggle(unitNode(87, 2701), 60);
    check('ticking the Heavy Mounted Crossbowman never adds Cranequins',
          !T.getLocaltree().techs.includes(1452));

    T.setLocaltree({ units: [2700], buildings: [87], techs: [1452] });
    T.toggle(unitNode(87, 2700), 60);
    check('removing the last Mounted Crossbowman takes Cranequins with it',
          !T.getLocaltree().techs.includes(1452),
          `techs left: ${T.getLocaltree().techs.join(', ')}`);
  }
}

console.log('\n=== Cranequins against the real layout (FULL.json) ===');
{
  // The layout gives Cranequins link_id 436 (Parthian Tactics); marked
  // "independent", that link is drawing-only and must not cascade either way.
  const full = JSON.parse(fs.readFileSync(
    path.join(ROOT, 'static/aoe2techtree/data/trees/FULL.json'), 'utf8'));
  const idx = {};
  (function walk(o) {
    if (Array.isArray(o)) return o.forEach(walk);
    if (!o || typeof o !== 'object') return;
    if (o.node_id !== undefined && o.use_type && o.building_id !== undefined)
      idx[`${o.building_id}_${o.node_id}`] = o;
    Object.values(o).forEach(walk);
  })(full);
  const cq = idx['87_1452'];
  check('FULL.json has Cranequins, marked independent', !!cq && cq.independent === true);
  if (cq) {
    T.setNodeIndex(idx);
    T.setLocaltree({ units: [2700], buildings: [87], techs: [] });
    T.toggle(cq, 60);
    check('ticking Cranequins does not add Parthian Tactics',
          !T.getLocaltree().techs.includes(436), `techs: ${T.getLocaltree().techs.join(', ')}`);
    T.setLocaltree({ units: [2700], buildings: [87], techs: [436, 1452] });
    T.toggle(idx['87_436'], 60);
    check('unticking Parthian Tactics keeps Cranequins', T.getLocaltree().techs.includes(1452));
  }
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
