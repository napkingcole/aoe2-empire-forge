// Regional unit mutual-exclusivity checks.
//
// Each _REGIONAL_GROUPS entry names the unit lines that contest ONE building
// button.  The engine hands that cell to exactly one line, so a tree holding
// two reads in-game as "my civ is missing a unit it clearly has".  _toggleNode
// evicts every other line in the group.
//
// This was a two-sided a/b pair table until Viking Sagas made two groups
// three-way (Mounted Crossbowman on Archery Range button 3, Varangian Guard on
// Barracks button 4).  The sweeps below are written against N lines, so a
// fourth contender needs no new test — but a line added without wiring fails.
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

console.log('=== Selecting any line evicts every other line in its group ===');
for (const group of T.GROUPS) {
  for (const line of group.lines) {
    // Start with EVERY RIVAL selected — and only the rivals, since _toggleNode
    // toggles, so a line that is already on would be switched off.  Starting
    // with every rival present is what makes the three-way case meaningful: a
    // pair table evicts one and leaves the other sitting on the button.
    const rivals = group.lines.filter(l => l !== line);
    T.setNodeIndex(indexFor(group));
    T.setLocaltree({
      units: rivals.flatMap(l => l.ids),
      buildings: [group.bldg],
      techs: rivals.flatMap(l => l.techs || []),
    });
    T.toggle(unitNode(group.bldg, line.ids[0]), 60);

    const left = T.getLocaltree().units;
    const survivors = rivals.flatMap(l => l.ids).filter(u => left.includes(u));
    check(`[${groupName(group)}] ${line.name} evicts all ${rivals.length} rival line(s)`,
          survivors.length === 0, `still present: ${survivors.join(', ')}`);
    check(`[${groupName(group)}] ${line.name} itself stays selected`,
          left.includes(line.ids[0]));

    // A rival's line-owned techs must go too, or the tree keeps a research node
    // whose only target has just been evicted.
    const techsLeft = T.getLocaltree().techs;
    const orphaned = rivals.flatMap(l => l.techs || []).filter(t => techsLeft.includes(t));
    check(`[${groupName(group)}] ${line.name} takes rival line-techs with them`,
          orphaned.length === 0, `orphaned techs: ${orphaned.join(', ')}`);
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
// eviction order decides the outcome.
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

    // Selecting a rival must strip Cranequins along with the unit it upgrades.
    T.setNodeIndex(indexFor(g));
    T.setLocaltree({ units: [2700, 2701], buildings: [87], techs: [1452] });
    T.toggle(unitNode(87, 39), 60);
    check('choosing Cavalry Archers removes Cranequins',
          !T.getLocaltree().techs.includes(1452),
          `techs left: ${T.getLocaltree().techs.join(', ')}`);
    check('...and removes the Mounted Crossbowman itself',
          !T.getLocaltree().units.some(u => [2700, 2701].includes(u)));

    // Ticking the tech means wanting the line: the layout links Cranequins to
    // Thumb Ring, not to 2700, so the generic ancestor cascade cannot do this.
    T.setNodeIndex(indexFor(g));
    T.setLocaltree({ units: [39, 474], buildings: [87], techs: [] });
    T.toggle(techNode(87, 1452), 60);
    check('ticking Cranequins pulls in the Mounted Crossbowman',
          T.getLocaltree().units.includes(2700),
          `units: ${T.getLocaltree().units.join(', ')}`);
    check('...and evicts the Cavalry Archer it replaces',
          ![39, 474].some(u => T.getLocaltree().units.includes(u)),
          `units: ${T.getLocaltree().units.join(', ')}`);
  }
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
