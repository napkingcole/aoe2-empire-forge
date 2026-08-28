// Tech tree EDITOR layout checks — runs static/aoe2techtree/js/main.js in Node
// with the browser globals stubbed, and exercises the two transforms that
// rewrite the tree before it is drawn:
//
//   _applyBuildingVariantLayout  Settlement / Folwark / Mule Cart vs the
//                                standard Mill, Lumber Camp and Mining Camp
//   _applySiegeShipLayout        the Dock's siege ship, owned by the wizard's
//                                picker rather than by the tree
//
// Both synthesise nodes into whichever civ layout is loaded, so the sweeps
// below run every shipped layout against every selection combination.
//
//   node tests/test_editor_layout.js
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');

const src = fs.readFileSync(path.join(ROOT, 'static/aoe2techtree/js/main.js'), 'utf8');
const harness = `
${src}
module.exports = {
  applyLayout: (t) => { _applyBuildingVariantLayout(t); _applySiegeShipLayout(t); },
  SIEGE: _PICKER_CONTROLLED_UNITS,
  SIEGE_VARIANTS: _SIEGE_VARIANT_IDS,
  toggle: _toggleNode,
  setLocaltree: (t) => { _localtree = t; },
  getLocaltree: () => _localtree,
  activeSwaps: _activeBuildingSwaps,
  swapOwningCamp: _swapOwningCamp,
  forcedOn: _forcedOnBuildings,
  handleClick: _handleBuildingVariantClick,
  hint: _variantHint,
  SWAPS: _REGIONAL_BUILDING_SWAPS,
  CAMPS: _CAMP_BUILDING_IDS,
};
`;
// Stub the browser globals main.js touches when our entry points run.
global.window = { showToast: () => {} };
global.document = { getElementById: () => null, querySelectorAll: () => [] };
const Module = require('module');
const m = new Module('main-shim');
m._compile(harness, path.join(ROOT, 'static/aoe2techtree/js/main-shim.js'));
const T = m.exports;

const SETTLEMENT = 2556, FOLWARK = 1734, MULE = 1808;
const CAMPS = [68, 562, 584];
const CAMP_TECHS = [202, 203, 221, 14, 13, 12, 55, 182, 278, 279].sort((a, b) => a - b);
const TECH_HOME = { 202: 562, 203: 562, 221: 562, 14: 68, 13: 68, 12: 68,
                    55: 584, 182: 584, 278: 584, 279: 584 };

const loadTree = (name) =>
  JSON.parse(fs.readFileSync(path.join(ROOT, `static/aoe2techtree/data/trees/${name}.json`), 'utf8'));

let failures = 0;
function check(label, cond, extra) {
  if (!cond) { failures++; console.log('  FAIL ' + label + (extra ? ' — ' + extra : '')); }
  else console.log('  ok   ' + label);
}

function col(tree, nodeId) { return tree.buildings.find(b => b.node_id === nodeId); }
function techsIn(tree, buildingId) {
  return tree.units_techs.filter(i => i.building_id === buildingId && i.use_type === 'Tech')
                         .map(i => i.node_id).sort((a, b) => a - b);
}
// Where each camp tech belongs given a set of selected building ids.
function expectedOwner(nid, selected) {
  const home = TECH_HOME[nid];
  for (const s of T.SWAPS) if (selected.includes(s.id) && s.replaces.includes(home)) return s.id;
  return home;
}

// Mirror the render-time integrity rules: every grid id must resolve to an item
// whose building_id matches the column it sits in, and every item must be placed.
function auditLayout(tree, label) {
  const index = {};
  for (const it of tree.units_techs) index[it.id] = it;
  const placed = new Set();
  const bad = [];
  for (const b of tree.buildings) {
    const width = b.grid.length ? b.grid[0].length : 0;
    for (let r = 0; r < b.grid.length; r++) {
      if (b.grid[r].length !== width) bad.push(`${b.id} ragged row ${r}`);
      for (let c = 0; c < b.grid[r].length; c++) {
        const id = b.grid[r][c];
        if (!id) continue;
        const it = index[id];
        if (!it) { bad.push(`${b.id} references missing item ${id}`); continue; }
        if (it.building_id !== b.node_id) bad.push(`${id} building_id=${it.building_id} in column ${b.node_id}`);
        if (it.row !== r) bad.push(`${id} row=${it.row} placed at ${r}`);
        if (placed.has(id)) bad.push(`${id} placed twice`);
        placed.add(id);
      }
    }
  }
  for (const it of tree.units_techs) if (!placed.has(it.id)) bad.push(`orphan item ${it.id}`);
  check(label + ': layout integrity', bad.length === 0, bad.slice(0, 5).join('; '));
}

function render(treeName, selected) {
  const tree = loadTree(treeName);
  T.setLocaltree({ units: [], buildings: [109, 621, ...selected], techs: [] });
  T.applyLayout(tree);
  return tree;
}

console.log('\n=== Full layout, standard camps (default) ===');
{
  const tree = render('FULL', CAMPS);
  auditLayout(tree, 'FULL standard');
  for (const s of T.SWAPS) {
    check(`${s.label} stub exists and is clickable`, !!col(tree, s.id));
    check(`${s.label} column is empty`, col(tree, s.id).grid.every(r => r.every(c => c === null)));
  }
  check('Mill keeps its techs', JSON.stringify(techsIn(tree, 68)) === JSON.stringify([12, 13, 14]));
  check('Mining Camp keeps its techs', JSON.stringify(techsIn(tree, 584)) === JSON.stringify([55, 182, 278, 279]));
  check('Farm hangs off the Mill', col(tree, 50).id === 'Building_50_68' && col(tree, 50).link_id === 68);
}

console.log('\n=== Full layout, each regional building from scratch ===');
for (const s of T.SWAPS) {
  const selected = [s.id, ...CAMPS.filter(c => !s.replaces.includes(c))];
  const tree = render('FULL', selected);
  auditLayout(tree, `FULL ${s.label}`);
  const want = CAMP_TECHS.filter(n => s.replaces.includes(TECH_HOME[n]));
  check(`${s.label} owns exactly the techs it replaces`,
        JSON.stringify(techsIn(tree, s.id)) === JSON.stringify(want), JSON.stringify(techsIn(tree, s.id)));
  check(`${s.label}: replaced camps emptied`,
        s.replaces.every(id => techsIn(tree, id).length === 0));
  check(`${s.label}: replaced camps still clickable`, s.replaces.every(id => !!col(tree, id)));
  check(`${s.label}: untouched camps keep their techs`,
        CAMPS.filter(c => !s.replaces.includes(c))
             .every(c => techsIn(tree, c).length > 0));
}

console.log('\n=== Full layout, Folwark + Mule Cart together ===');
{
  const tree = render('FULL', [FOLWARK, MULE]);
  auditLayout(tree, 'FULL Folwark+Mule');
  check('Folwark owns the Mill techs', JSON.stringify(techsIn(tree, FOLWARK)) === JSON.stringify([12, 13, 14]));
  check('Mule Cart owns lumber + mining techs',
        JSON.stringify(techsIn(tree, MULE)) === JSON.stringify([55, 182, 202, 203, 221, 278, 279]));
  check('Settlement stays empty', techsIn(tree, SETTLEMENT).length === 0);
  check('all three camps emptied', CAMPS.every(id => techsIn(tree, id).length === 0));
  check('Farm hangs off the Folwark', col(tree, 50).id === 'Building_50_1734');
}

console.log('\n=== Farm placement follows whoever owns the Mill ===');
for (const [selected, wantId, label] of [
  [CAMPS, 'Building_50_68', 'standard camps → Mill'],
  [[SETTLEMENT], 'Building_50_50', 'Settlement → its own root'],
  [[FOLWARK, 562, 584], 'Building_50_1734', 'Folwark → the Folwark'],
  [[MULE, 68], 'Building_50_68', 'Mule Cart only → still the Mill'],
]) {
  const tree = render('FULL', selected);
  check(label, col(tree, 50).id === wantId, col(tree, 50).id);
}

console.log('\n=== Native layouts, kept and reverted ===');
for (const [name, id, label] of [
  ['MAPUCHE', SETTLEMENT, 'Settlement'], ['POLES', FOLWARK, 'Folwark'], ['ARMENIANS', MULE, 'Mule Cart'],
]) {
  const swap = T.SWAPS.find(s => s.id === id);
  const kept = render(name, [id, ...CAMPS.filter(c => !swap.replaces.includes(c))]);
  auditLayout(kept, `${name} keeps ${label}`);
  const want = CAMP_TECHS.filter(n => swap.replaces.includes(TECH_HOME[n]));
  check(`${name}: ${label} owns its techs`,
        JSON.stringify(techsIn(kept, id)) === JSON.stringify(want), JSON.stringify(techsIn(kept, id)));

  const reverted = render(name, CAMPS);
  auditLayout(reverted, `${name} reverted`);
  check(`${name}: camp techs all restored`,
        CAMP_TECHS.every(n => techsIn(reverted, TECH_HOME[n]).includes(n)));
  check(`${name}: ${label} emptied but still clickable`,
        !!col(reverted, id) && techsIn(reverted, id).length === 0);
  check(`${name}: Farm back on the Mill`, col(reverted, 50).id === 'Building_50_68');
}

console.log('\n=== Every shipped layout x every selection combination ===');
{
  const names = fs.readdirSync(path.join(ROOT, 'static/aoe2techtree/data/trees'))
                  .filter(f => f.endsWith('.json')).map(f => f.replace('.json', ''));
  const combos = [CAMPS, [SETTLEMENT], [FOLWARK, 562, 584], [MULE, 68], [FOLWARK, MULE]];
  const bad = [];
  const campTechsPresent = (tree) => tree.units_techs
    .filter(i => i.use_type === 'Tech' && CAMP_TECHS.includes(i.node_id)
                 && [...CAMPS, SETTLEMENT, FOLWARK, MULE].includes(i.building_id))
    .map(i => i.node_id).sort((a, b) => a - b);

  for (const name of names) {
    const baseline = JSON.stringify(campTechsPresent(loadTree(name)));
    for (const selected of combos) {
      let tree;
      try { tree = render(name, selected); }
      catch (e) { bad.push(`${name} [${selected}]: threw ${e.message}`); continue; }

      const index = {};
      for (const it of tree.units_techs) index[it.id] = it;
      const placed = new Set();
      for (const b of tree.buildings) {
        for (let r = 0; r < b.grid.length; r++) {
          for (let c = 0; c < b.grid[r].length; c++) {
            const id = b.grid[r][c];
            if (!id) continue;
            if (!index[id]) { bad.push(`${name} [${selected}]: dangling ${id}`); continue; }
            if (index[id].building_id !== b.node_id) bad.push(`${name} [${selected}]: ${id} in column ${b.node_id}`);
            if (placed.has(id)) bad.push(`${name} [${selected}]: ${id} placed twice`);
            placed.add(id);
          }
        }
      }
      for (const it of tree.units_techs) if (!placed.has(it.id)) bad.push(`${name} [${selected}]: orphan ${it.id}`);

      if (JSON.stringify(campTechsPresent(tree)) !== baseline) {
        bad.push(`${name} [${selected}]: camp techs ${baseline} → ${JSON.stringify(campTechsPresent(tree))}`);
      }
      for (const it of tree.units_techs) {
        if (it.use_type !== 'Tech' || !(it.node_id in TECH_HOME)) continue;
        const want = expectedOwner(it.node_id, selected);
        if (it.building_id !== want) bad.push(`${name} [${selected}]: tech ${it.node_id} on ${it.building_id} want ${want}`);
      }
    }
  }
  check(`${names.length} layouts × ${combos.length} combinations`, bad.length === 0, bad.slice(0, 6).join('; '));
}

console.log('\n=== Click semantics ===');
{
  const sel = () => T.getLocaltree().buildings.filter(b => [68, 562, 584, SETTLEMENT, FOLWARK, MULE].includes(b)).sort((a, b) => a - b);
  T.setLocaltree({ units: [], buildings: [109, 621, ...CAMPS], techs: [] });

  check('clicking Mill with no swap active does nothing',
        T.handleClick(68) === true && sel().join() === '68,562,584'.split(',').map(Number).sort((a, b) => a - b).join());

  T.handleClick(SETTLEMENT);
  check('Settlement adopted, all three camps dropped', sel().join() === String(SETTLEMENT));
  check('forced-on set excludes all three camps',
        ![...T.forcedOn()].some(id => CAMPS.includes(id)));

  T.handleClick(562);
  check('clicking a replaced camp reverts to standard', sel().join() === '68,562,584'.split(',').map(Number).sort((a, b) => a - b).join());

  T.handleClick(FOLWARK);
  check('Folwark takes only the Mill', sel().join() === [562, 584, FOLWARK].sort((a, b) => a - b).join(), sel().join());

  T.handleClick(MULE);
  check('Mule Cart coexists with the Folwark',
        sel().join() === [FOLWARK, MULE].sort((a, b) => a - b).join(), sel().join());
  check('both are reported active', T.activeSwaps().length === 2);
  check('Mill owned by the Folwark', T.swapOwningCamp(68).id === FOLWARK);
  check('Lumber Camp owned by the Mule Cart', T.swapOwningCamp(562).id === MULE);

  T.handleClick(SETTLEMENT);
  check('Settlement evicts both (it needs all three camps)',
        sel().join() === String(SETTLEMENT), sel().join());

  T.handleClick(SETTLEMENT);
  check('clicking it again returns every camp', sel().join() === [68, 562, 584].sort((a, b) => a - b).join());

  T.handleClick(MULE);
  check('Mule Cart leaves the Mill alone', sel().join() === [68, MULE].sort((a, b) => a - b).join(), sel().join());
  check('Mill still forced on', T.forcedOn().has(68));
  check('Mill hint stays "Always available."',
        T.hint({ use_type: 'Building', node_id: 68 }) === 'Always available.');
  check('Lumber Camp hint names its owner',
        T.hint({ use_type: 'Building', node_id: 562 }) === 'Replaced by the Mule Cart — click to restore.');
  check('Settlement hint warns about the eviction',
        T.hint({ use_type: 'Building', node_id: SETTLEMENT }).includes('Removes the Mule Cart'),
        T.hint({ use_type: 'Building', node_id: SETTLEMENT }));
  check('Folwark hint does not warn (no overlap)',
        !T.hint({ use_type: 'Building', node_id: FOLWARK }).includes('Removes'));

  check('unrelated building not intercepted', T.handleClick(12) === false);
}

console.log('\n=== Siege ship: the picker\'s choice always has a Dock node ===');
{
  const dockUnits = (tree) => tree.units_techs
    .filter(i => i.building_id === 45 && T.SIEGE.has(i.node_id))
    .map(i => i.node_id).sort((a, b) => a - b);

  // From scratch (FULL layout) the nodes used to be missing entirely.
  for (const [ship, label] of [[420, 'Cannon Galleon'], [2633, 'Catapult Galleon'],
                               [1795, 'Dromon'], [1948, 'Lou Chuan']]) {
    const units = ship === 420 ? [420, 691] : [ship];
    const tree = render('FULL', []);   // buildings only; set units separately
    T.setLocaltree({ units, buildings: [109, 621, 68, 562, 584], techs: [] });
    const t2 = loadTree('FULL');
    T.applyLayout(t2);
    auditLayout(t2, `FULL ${label}`);
    check(`FULL: ${label} has a Dock node`, dockUnits(t2).includes(ship), JSON.stringify(dockUnits(t2)));
    check(`FULL: ${label} — no other variant shown`,
          T.SIEGE_VARIANTS.filter(v => v !== ship && dockUnits(t2).includes(v)).length === 0,
          JSON.stringify(dockUnits(t2)));
  }

  // A civ layout that ships a different variant must yield to the picker.
  T.setLocaltree({ units: [1948], buildings: [109, 621, 68, 562, 584], techs: [] });
  const aztec = loadTree('AZTECS');
  T.applyLayout(aztec);
  auditLayout(aztec, 'AZTECS with Lou Chuan picked');
  check('Aztec layout + Lou Chuan: Catapult Galleon evicted', !dockUnits(aztec).includes(2633),
        JSON.stringify(dockUnits(aztec)));
  check('Aztec layout + Lou Chuan: Lou Chuan placed', dockUnits(aztec).includes(1948));

  // Every layout, every ship — nodes land and the layout stays sane.
  const names = fs.readdirSync(path.join(ROOT, 'static/aoe2techtree/data/trees'))
                  .filter(f => f.endsWith('.json')).map(f => f.replace('.json', ''));
  const bad = [];
  for (const name of names) {
    for (const units of [[420, 691], [2633], [1795], [1948], []]) {
      T.setLocaltree({ units: units.slice(), buildings: [109, 621, 68, 562, 584], techs: [] });
      const tree = loadTree(name);
      try { T.applyLayout(tree); } catch (e) { bad.push(`${name} [${units}]: ${e.message}`); continue; }
      const shown = dockUnits(tree);
      for (const u of units) if (!shown.includes(u)) bad.push(`${name} [${units}]: ${u} missing`);
      for (const v of T.SIEGE_VARIANTS) {
        if (!units.includes(v) && shown.includes(v)) bad.push(`${name} [${units}]: stray variant ${v}`);
      }
      // Cells must not be double-booked or dangling.
      const index = {};
      for (const it of tree.units_techs) index[it.id] = it;
      const dock = tree.buildings.find(b => b.node_id === 45);
      const seen = new Set();
      for (let r = 0; r < dock.grid.length; r++) {
        for (let c = 0; c < dock.grid[r].length; c++) {
          const id = dock.grid[r][c];
          if (!id) continue;
          if (!index[id]) bad.push(`${name} [${units}]: dangling ${id}`);
          if (seen.has(id)) bad.push(`${name} [${units}]: ${id} twice`);
          seen.add(id);
        }
      }
      for (const it of tree.units_techs) {
        if (it.building_id === 45 && !seen.has(it.id)) bad.push(`${name} [${units}]: orphan ${it.id}`);
      }
    }
  }
  check(`${names.length} layouts × 5 siege selections`, bad.length === 0, bad.slice(0, 6).join('; '));
}

console.log('\n=== Siege ship nodes are locked in the tree ===');
{
  T.setLocaltree({ units: [2633], buildings: [109, 621, 68, 562, 584], techs: [] });
  const ships = () => T.getLocaltree().units.filter(id => T.SIEGE.has(id));
  T.toggle({ use_type: 'Unit', node_id: 2633, id: 'Unit_2633_45', building_id: 45 }, 60);
  check('cannot toggle the picked ship off', ships().join() === '2633');
  T.toggle({ use_type: 'Unit', node_id: 420, id: 'Unit_420_45', building_id: 45 }, 60);
  check('cannot toggle another ship on', ships().join() === '2633');
  check('hint points at the picker',
        T.hint({ use_type: 'Unit', node_id: 420 }).includes('Siege Ship picker'));
  check('non-siege units unaffected', T.hint({ use_type: 'Unit', node_id: 74 }) === '');
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
