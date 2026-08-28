/*
 * Adapted from SiegeEngineers/aoe2techtree (MIT License)
 * Modifications: removed standalone web-app scaffolding; added showTechtree()
 * embed API and canEdit=3 toggle mode for the civbuilder wizard.
 */

let data = {};
let parentConnections;
let focusedNodeId = null;

const PADDING = 20;
const PADDING_BETWEEN_COLUMNS = 10;
const TOP_PADDING = 20;

// ── Wizard embed state ────────────────────────────────────────────────────────
let _imgroot  = '/static/aoe2techtree/img';
let _treeroot = '/static/aoe2techtree/data/trees';
let _locroot  = '/static/aoe2techtree/data/locales';
let _canEdit  = false;
// localtree: mirrors draft.tree format (three plain arrays of integer IDs)
let _localtree = { units: [], buildings: [], techs: [] };
let _currentCivName = null;
// Reverse map: node_id → [civName, ...] — built once after data loads
let _nodeIdToCivs = {};
// node_id (number) → units_techs item — rebuilt each time civ() renders
let _nodeIndex = {};
let _successorIndex = {};
// building_id → [units_techs items] — for cascade-disable when a building is toggled off
let _buildingItems = {};
// item.id → building object — fallback for highlight path when parentConnections has no entry
let _itemToBuilding = {};

// Buildings that are always enabled and can never be toggled (Town Center, House)
const HARD_ALWAYS_ON_BUILDINGS = new Set([109, 621]);

// Resource drop-off buildings.  Always on *unless* a regional building that
// replaces them is selected (see _REGIONAL_BUILDING_SWAPS below).
const _CAMP_BUILDING_IDS = new Set([68, 562, 584]);   // Mill, Lumber Camp, Mining Camp

// Farm's home when no regional replacement is active: a child of the Mill.
const _FARM_STANDARD = { building_id: 68, id: 'Building_50_68', link_id: 68 };

// Some layouts drop a camp entirely because a regional building replaced it —
// POLES.json has no Mill column at all, only a Folwark.  Switching such a civ
// back to the standard camps needs the column recreated, so keep a definition
// of each.  Field-for-field copies of the columns in FULL.json.
const _CAMP_NODE_DEFS = {
    68: {
        age_id: 1, building_id: 68, building_in_new_column: false,
        building_upgraded_from_id: -1, help_string_id: 105157,
        id: 'Building_68_68', link_id: null, link_node_type: 'BuildingTech',
        name: 'Mill', name_string_id: 14157, node_id: 68,
        node_status: 'ResearchedCompleted', node_type: 'BuildingTech',
        picture_index: 19, row: 0, use_type: 'Building',
    },
    562: {
        age_id: 1, building_id: 562, building_in_new_column: null,
        building_upgraded_from_id: -1, help_string_id: 105464,
        id: 'Building_562_562', link_id: null, link_node_type: 'BuildingTech',
        name: 'Lumber Camp', name_string_id: 14464, node_id: 562,
        node_status: 'ResearchedCompleted', node_type: 'BuildingTech',
        picture_index: 40, row: 0, use_type: 'Building',
    },
    584: {
        age_id: 1, building_id: 584, building_in_new_column: null,
        building_upgraded_from_id: -1, help_string_id: 105487,
        id: 'Building_584_584', link_id: null, link_node_type: 'BuildingTech',
        name: 'Mining Camp', name_string_id: 14487, node_id: 584,
        node_status: 'ResearchedCompleted', node_type: 'BuildingTech',
        picture_index: 39, row: 0, use_type: 'Building',
    },
};

// ── Regional unit mutual-exclusivity ─────────────────────────────────────────
// Each pair: select one group's units → the other group is evicted.
// "Select All" keeps the standard side and excludes the regional side.
const _REGIONAL_PAIRS = [
    { a: [74, 75, 77, 473, 567],  b: [2550, 2588, 2552, 2554], bldg: 12,  nameA: "Militia line",       nameB: "Champi line"           },
    { a: [38, 283, 569],           b: [1944, 1946],              bldg: 101, nameA: "Knight line",        nameB: "Hei Guang Cavalry"     },
    { a: [280, 550, 588],          b: [1904, 1907],              bldg: 49,  nameA: "Mangonel line",      nameB: "Rocket Cart"           },
    { a: [1258, 422, 548],         b: [1744, 1746],              bldg: 49,  nameA: "Battering Ram line", nameB: "Armored Elephant line" },
    // Both lines train from Archery Range button 3, so only one can own the cell.
    { a: [39, 474],                b: [873, 875],                bldg: 87,  nameA: "Cavalry Archer line", nameB: "Elephant Archer line" },
];
// Flat set of all regional-side unit IDs — excluded from "Select All"
const _REGIONAL_UNIT_IDS = new Set([2550, 2588, 2552, 2554, 1944, 1946, 1904, 1907, 1744, 1746, 873, 875]);

// ── Picker-controlled units ──────────────────────────────────────────────────
// The siege ship is one Dock button with five candidates plus an elite toggle —
// more than the tree's on/off vocabulary can express — so it is chosen in the
// wizard's Siege Ship picker instead, and the backend rebuilds tree[0] from that
// choice.  The nodes stay visible in the Dock (that's where you'd look for
// them) but can't be toggled here, or the tree would show a ship the build
// won't produce.  builder.js keeps the displayed selection in sync.
const _PICKER_CONTROLLED_UNITS = new Set([420, 691, 2633, 1795, 1948]);
const _PICKER_HINT = 'Chosen with the Siege Ship picker, next to the tech tree button.';

// ── Bonus-mirrored units ─────────────────────────────────────────────────────
// Regional / second unique units whose make-avail tech is locked to its owner
// civ (tech.civ, not the tech-tree effect), so the backend has to reassign the
// whole tech chain for them to work.  That reassignment is the matching
// "Unlock ..." civ bonus, which the wizard *derives* from this tree — ticking a
// node here adds the bonus, unticking removes it.  So these toggle normally;
// the set exists only to explain the link in the hover hint, and to keep them
// out of "Enable All" (they are opt-in extras, and two of them share the
// Archery Range's Cavalry Archer button).  Keep in sync with
// civ_appender._UNLOCK_UNIT_BONUSES.
const _BONUS_CONTROLLED_UNITS = new Set([
    2569, 2571,   // Bolas Rider
    1952,         // Xianbei Raider
    1911,         // Grenadier
    1974,         // Jian Swordsman
    2586, 2587,   // Temple Guard
    2582, 2584,   // Ibirapema Warrior
    1962,         // War Chariot
    1923,         // Mounted Trebuchet
    1751, 1753,   // Shrivamsha Rider
    1811,         // Warrior Priest
    1750,         // Thirisadai
    1793,         // Legionary
    1813,         // Savar
]);
const _BONUS_HINT = 'Also adds the matching "Unlock ..." civ bonus on the Bonuses step.';

// True for a unit this editor shows but does not own the on/off decision for.
// Only the picker's siege ships qualify — the bonus-mirrored units are owned
// here, and merely publish their state to the Bonuses step.
function _isExternallyControlled(item) {
    return item.use_type === 'Unit' && _PICKER_CONTROLLED_UNITS.has(item.node_id);
}

// Every shipped layout reserves the same Dock cells for these: the Cannon
// Galleon and its elite in the last column, and whichever variant the civ has
// in column 1 row 7.  FULL.json has them stripped, so a from-scratch tree used
// to show no siege ship at all — the nodes are put back at render time instead
// of editing 54 layout files.  Only the picked variant occupies the variant
// cell, exactly as each real civ's layout does.
const _DOCK_BUILDING_ID = 45;
// role → the cell the shipped layouts normally use.  420 and 691 are their
// own roles; the three variants share the single 'variant' cell.
const _SIEGE_SHIP_CELLS = { 420: [6, 6], 691: [6, 7], variant: [1, 7] };
const _SIEGE_VARIANT_IDS = [2633, 1795, 1948];
const _SIEGE_SHIP_NODES = {
    420: {
        age_id: 4, building_id: 45, building_in_new_column: null,
        building_upgraded_from_id: null, grid: null, help_string_id: 105287,
        id: 'Unit_420_45', link_id: null, link_node_type: 'BuildingTech',
        name: 'Cannon Galleon', name_string_id: 14287, node_id: 420,
        node_status: 'ResearchRequired', node_type: 'Unit', picture_index: 55,
        row: 6, use_type: 'Unit',
    },
    691: {
        age_id: 4, building_id: 45, building_in_new_column: null,
        building_upgraded_from_id: null, grid: null, help_string_id: 105573,
        id: 'Unit_691_45', link_id: 420, link_node_type: 'Unit',
        name: 'Elite Cannon Galleon', name_string_id: 14573, node_id: 691,
        node_status: 'NotAvailable', node_type: null, picture_index: 298,
        row: 7, use_type: 'Unit',
    },
    2633: {
        age_id: 4, building_id: 45, building_in_new_column: null,
        building_upgraded_from_id: null, grid: null, help_string_id: 105572,
        id: 'Unit_2633_45', link_id: null, link_node_type: 'BuildingTech',
        name: 'Catapult Galleon', name_string_id: 14572, node_id: 2633,
        node_status: 'ResearchedCompleted', node_type: 'RegionalUnit',
        picture_index: 591, row: 7, use_type: 'Unit',
    },
    1795: {
        age_id: 4, building_id: 45, building_in_new_column: null,
        building_upgraded_from_id: null, grid: null, help_string_id: 105055,
        id: 'Unit_1795_45', link_id: null, link_node_type: 'BuildingTech',
        name: 'Dromon', name_string_id: 14055, node_id: 1795,
        node_status: 'ResearchedCompleted', node_type: 'RegionalUnit',
        picture_index: 406, row: 7, use_type: 'Unit',
    },
    1948: {
        age_id: 4, building_id: 45, building_in_new_column: null,
        building_upgraded_from_id: null, grid: null, help_string_id: 105601,
        id: 'Unit_1948_45', link_id: null, link_node_type: 'BuildingTech',
        name: 'Lou Chuan', name_string_id: 14601, node_id: 1948,
        node_status: 'ResearchedCompleted', node_type: 'RegionalUnit',
        picture_index: 431, row: 7, use_type: 'Unit',
    },
};

// ── Regional building swaps ──────────────────────────────────────────────────
// A regional building replaces one or more of the standard resource camps and
// absorbs their techs into a single column (this is how the Settlement, Folwark
// and Mule Cart work in the shipped trees).  The swap is applied to whatever
// layout is loaded, so each one is reachable from *any* starting template —
// including the wide-open "Full" tree — instead of only from the handful of civ
// layouts that happen to ship the column.
//
// Two swaps can be active at once as long as they replace different camps: the
// Folwark takes over the Mill while the Mule Cart takes over the Lumber and
// Mining Camps, so those combine.  The Settlement takes all three, so it
// conflicts with both.  Selecting a swap evicts whatever overlaps it.
//
// standard_columns describes the layout when the swap is OFF: for each replaced
// building, the columns of tech node_ids it owns (top-to-bottom within a column).
// Folding a regional column back reads this map; unfolding it reads the live
// layout, so a template that already has the column (Mapuche) round-trips.
//
// farm: where the Farm node hangs when this swap owns the Mill.  Swaps that
// don't touch the Mill leave it null and the Farm stays put.
const _STD_CAMP_COLUMNS = {
    562: [[202, 203, 221]],           // Double-Bit Axe → Bow Saw → Two-Man Saw
    68:  [[14, 13, 12]],              // Horse Collar → Heavy Plow → Crop Rotation
    584: [[55, 182], [278, 279]],     // Gold Mining / Stone Mining + shaft upgrades
};
const _REGIONAL_BUILDING_SWAPS = [
    {
        id: 2556,
        label: 'Settlement',
        replaced_label: 'Mill, Lumber Camp and Mining Camp',
        replaces: [562, 68, 584],
        standard_columns: _STD_CAMP_COLUMNS,
        // Settlement re-roots Farm as its own column linked to the Settlement.
        farm: { building_id: 50, id: 'Building_50_50', link_id: 2556 },
        // Node used when the loaded layout has no column of its own.
        // Field-for-field copy of Building_2556_2556 from MAPUCHE.json.
        node: {
            age_id: 1, building_id: 2556, building_in_new_column: false,
            building_upgraded_from_id: -1, help_string_id: 105509,
            id: 'Building_2556_2556', link_id: null, link_node_type: 'BuildingTech',
            name: 'Settlement', name_string_id: 14509, node_id: 2556,
            node_status: 'ResearchedCompleted', node_type: 'RegionalBuilding',
            picture_index: 98, row: 0, use_type: 'Building',
        },
    },
    {
        id: 1734,
        label: 'Folwark',
        replaced_label: 'Mill',
        replaces: [68],
        standard_columns: _STD_CAMP_COLUMNS,
        // The Folwark absorbs the Farm as a child column (as the Poles have it).
        farm: { building_id: 1734, id: 'Building_50_1734', link_id: 1734 },
        // Copy of Building_1734_1734 from POLES.json.
        node: {
            age_id: 1, building_id: 1734, building_in_new_column: null,
            building_upgraded_from_id: -1, help_string_id: 105581,
            id: 'Building_1734_1734', link_id: null, link_node_type: 'BuildingTech',
            name: 'Folwark', name_string_id: 14581, node_id: 1734,
            node_status: 'ResearchedCompleted', node_type: 'UniqueBuilding',
            picture_index: 86, row: 0, use_type: 'Building',
        },
    },
    {
        id: 1808,
        label: 'Mule Cart',
        replaced_label: 'Lumber Camp and Mining Camp',
        replaces: [584, 562],
        standard_columns: _STD_CAMP_COLUMNS,
        farm: null,                       // doesn't touch the Mill
        // Copy of Building_1808_1808 from ARMENIANS.json.
        node: {
            age_id: 1, building_id: 1808, building_in_new_column: false,
            building_upgraded_from_id: -1, help_string_id: 105045,
            id: 'Building_1808_1808', link_id: null, link_node_type: 'BuildingNonTech',
            name: 'Mule Cart', name_string_id: 14045, node_id: 1808,
            node_status: 'ResearchedCompleted', node_type: 'RegionalBuilding',
            picture_index: 89, row: 0, use_type: 'Building',
        },
    },
];
const _REGIONAL_BUILDING_IDS = new Set(_REGIONAL_BUILDING_SWAPS.map(s => s.id));

// ── Utility ───────────────────────────────────────────────────────────────────

function loadJson(file, callback) {
    const xobj = new XMLHttpRequest();
    xobj.overrideMimeType('application/json');
    xobj.open('GET', file, true);
    xobj.onreadystatechange = function () {
        if (xobj.readyState === 4 && xobj.status === 200) {
            callback(JSON.parse(xobj.responseText));
        }
    };
    xobj.send(null);
}

function formatName(name) {
    if (name === undefined || name === null) return '?';
    // Keep <br>\n as a plain \n so SVG.js creates two tspan lines for long names.
    // Strip the HTML tag but preserve the newline character.
    return name.replace(/<br\s*\/?>\n?/gi, '\n').trim();
}

function resetHighlightPath() {
    unhighlightPath();
    if (focusedNodeId) highlightPath(focusedNodeId);
}

function unhighlightPath() {
    SVG.find('.node.is-highlight, .connection.is-highlight')
        .each((el) => el.removeClass('is-highlight'));
    document.querySelectorAll('[id$="_bg"]').forEach(el => {
        el.removeAttribute('stroke');
        el.removeAttribute('stroke-width');
    });
}

function highlightPath(caretId) {
    const visited = new Set();
    recurse(caretId);
    function recurse(caretId) {
        if (visited.has(caretId)) return;
        visited.add(caretId);
        SVG('#' + caretId).addClass('is-highlight');
        // Directly stroke the background rect — reliable in SVG where CSS outline may not render.
        const bg = document.getElementById(caretId + '_bg');
        if (bg) { bg.setAttribute('stroke', '#fff'); bg.setAttribute('stroke-width', '2'); }
        const parentIds = parentConnections.get(caretId);
        if (parentIds) {
            for (let parentId of parentIds) {
                const line = SVG(`#connection_${parentId}_${caretId}`);
                if (line) line.front().addClass('is-highlight');
                recurse(parentId);
            }
        } else {
            // No explicit connection in the layout (item stacked under another in the same
            // column with a now-broken chain). Climb to the owning building anyway.
            const building = _itemToBuilding[caretId];
            if (building) recurse(building.id);
        }
    }
}

function hideHelp() {
    focusedNodeId = null;
    const h = document.getElementById('helptext');
    if (h) h.style.display = 'none';
    resetHighlightPath();
}

function positionHelptext(caret, element_height, tree_height) {
    const helptext = document.getElementById('helptext');
    if (!helptext) return;
    helptext.style.display = 'block';
    positionHelptextBelow(caret, helptext, element_height, tree_height)
        || positionHelptextAbove(caret, helptext)
        || positionHelptextToLeftOrRight(caret, helptext, element_height);
}

function displayHelp(caretId, helpStringId, element_height, tree_height) {
    focusedNodeId = caretId;
    const helptextContent = document.getElementById('helptext__content');
    const helptextAdvancedStats = document.getElementById('helptext__advanced_stats');
    if (!helptextContent) return;
    const overlay = SVG(`#${caretId}_overlay`);
    const name   = overlay.data('name');
    const fullId = overlay.data('id').replace('_copy', '');
    const caret  = overlay.data('caret');
    helptextContent.innerHTML = getHelpText(name, fullId, helpStringId);
    if (helptextAdvancedStats) helptextAdvancedStats.innerHTML = getAdvancedStats(name, fullId);
    positionHelptext(caret, element_height, tree_height);
    resetHighlightPath();
}

function positionHelptextBelow(caret, helptext, element_height, tree_height) {
    let top = caret.y + element_height + document.getElementById('root').getBoundingClientRect().top;
    let helpbox = helptext.getBoundingClientRect();
    if (top + helpbox.height > tree_height) return false;
    let destX = caret.x - helpbox.width;
    let techtree = document.getElementById('techtree');
    if (destX < 0 || destX - techtree.scrollLeft < 0) destX = techtree.scrollLeft;
    helptext.style.top = top + 'px';
    helptext.style.left = destX + 'px';
    return true;
}

function positionHelptextAbove(caret, helptext) {
    let helpbox = helptext.getBoundingClientRect();
    let top = caret.y - helpbox.height + document.getElementById('root').getBoundingClientRect().top;
    if (top < 0) return false;
    let destX = caret.x - helpbox.width;
    let techtree = document.getElementById('techtree');
    if (destX < 0 || destX - techtree.scrollLeft < 0) destX = techtree.scrollLeft;
    helptext.style.top = top + 'px';
    helptext.style.left = destX + 'px';
    return true;
}

function positionHelptextToLeftOrRight(caret, helptext, element_height) {
    let helpbox = helptext.getBoundingClientRect();
    let destX = caret.x - helpbox.width;
    let techtree = document.getElementById('techtree');
    if (destX < 0 || destX - techtree.scrollLeft < 0) destX = caret.x + element_height;
    helptext.style.top = '0px';
    helptext.style.left = destX + 'px';
}

// ── Help text ─────────────────────────────────────────────────────────────────

function chargeText(type) {
    const names = {1:'Charge Attack:&nbsp;',2:'Charge Hit Points:&nbsp;',3:'Charged Area Attack:&nbsp;',
                   4:'Projectile Dodging:&nbsp;',5:'Melee Attack Blocking:&nbsp;',
                   6:'Charged Ranged Attack (type 1):&nbsp;',7:'Charged Ranged Attack (type 2):&nbsp;'};
    return names[type] || 'Unknown Charge:&nbsp;';
}

function splitTrait(trait) {
    const traits = [];
    for (let x of [1, 2, 4, 8, 16, 32, 64, 128]) { if ((trait & x) > 0) traits.push(x); }
    return traits;
}

function traitsIfDefined(trait, traitPiece) {
    if (trait === undefined || trait === 0) return false;
    const traitdescriptions = [];
    for (let t of splitTrait(trait)) {
        switch (t) {
            case 1: traitdescriptions.push('Garrison Unit'); break;
            case 2: traitdescriptions.push('Ship Unit'); break;
            case 4: traitdescriptions.push('Builds:&nbsp;' + data.strings[data.data['Building'][traitPiece]['LanguageNameId']]); break;
            case 8: traitdescriptions.push('Transforms into:&nbsp;' + data.strings[(data.data['Building'][traitPiece] || data.data['Unit'][traitPiece])['LanguageNameId']]); break;
            case 16: traitdescriptions.push('<abbr title="has auto-scout behaviour if placed at start">Scout Unit</abbr>'); break;
            default: traitdescriptions.push('Unknown Trait:&nbsp;' + trait);
        }
    }
    return traitdescriptions;
}


function getHelpText(name, fullId, helpStringId) {
    const trueHelpStringId = helpStringId - 79000;
    const items = fullId.split('_');
    const type = items[0];
    const id   = items[1];
    let text = data.strings[trueHelpStringId];
    if (text === undefined) return '?';
    text = text.replace(/\n/g, '');
    if (type === 'Tech') {
        text = text.replace(/(.+?\(.+?\))(.*)/m,
            '<p class="helptext__heading">$1</p><p class="helptext__desc">$2</p><p class="helptext__stats">&nbsp;</p>');
    } else if (type === 'Unit') {
        text = text.replace(/(.+?\(‹cost›\))(.+?)<i>\s*(.+?)<\/i>(.*)/m,
            '<p class="helptext__heading">$1</p><p class="helptext__desc">$2</p><p class="helptext__upgrade_info"><em>$3</em></p><p class="helptext__stats">$4</p>');
    } else if (type === 'Building') {
        text = text.replace(/<b><i>(.+?)<\/b><\/i>/m, '<b><em>$1</em></b>');
        if (text.indexOf('<i>') >= 0) {
            text = text.replace(/(.+?\(‹cost›\))(.+?)<i>\s*(.+?)<\/i>(.*)/m,
                '<p class="helptext__heading">$1</p><p class="helptext__desc">$2</p><p class="helptext__upgrade_info"><em>$3</em></p><p class="helptext__stats">$4</p>');
        } else {
            text = text.replace(/(.+?\(‹cost›\))(.*)<br>(.*)/m,
                '<p>$1</p><p>$2</p><p class="helptext__stats">$3</p>');
        }
    }
    text = text.replace(/<br>/g, '');
    if ((type === 'Unit') && id in data.data.unit_upgrades) {
        text = text.replace(/<p class="helptext__stats">/,
            '<h3>Upgrade</h3><p class="helptext__upgrade_cost">' + cost(data.data.unit_upgrades[id].Cost)
            + ' (' + data.data.unit_upgrades[id].ResearchTime + 's)<p><p class="helptext__stats">');
    }
    let meta = data.data[type][id];
    if (meta !== undefined) {
        let displayAttack = false;
        let ranged = meta.Range > 1;
        text = text.replace(/‹cost›/, cost(meta.Cost));
        text = text.replaceAll(/‹static_cost=([^,›]*),([^›]*)›/g,
            (_, resource, c) => `<span class="cost ${resource.toLowerCase()}" title="${c} ${resource}">${c}</span>`);
        let stats = [];
        if (text.match(/‹hp›/))                          stats.push('HP:&nbsp;' + meta.HP);
        if (text.match(/‹attack›/) && meta.Attack > 0) { stats.push('Attack:&nbsp;' + meta.Attack); displayAttack = true; }
        if (text.match(/‹[Aa]rmor›/))                    stats.push('Armor:&nbsp;' + meta.MeleeArmor);
        if (text.match(/‹[Pp]iercearmor›/))              stats.push('Pierce armor:&nbsp;' + meta.PierceArmor);
        if (text.match(/‹garrison›/))                    stats.push('Garrison:&nbsp;' + meta.GarrisonCapacity);
        if (text.match(/‹range›/) && displayAttack)      stats.push('Range:&nbsp;' + meta.Range);
        stats.push(ifDefinedAndGreaterZero(meta.MinRange, 'Min Range:&nbsp;'));
        stats.push(ifDefined(meta.LineOfSight, 'Line of Sight:&nbsp;'));
        stats.push(ifDefined(meta.Speed, 'Speed:&nbsp;'));
        stats.push(secondsIfDefined(meta.TrainTime, 'Build Time:&nbsp;'));
        stats.push(secondsIfDefined(meta.ResearchTime, 'Research Time:&nbsp;'));
        stats.push(ifDefined(meta.FrameDelay, 'Frame Delay:&nbsp;', ranged));
        stats.push(ifDefinedAndGreaterZero(meta.BlastWidth, 'Blast Radius:&nbsp;'));
        stats.push(traitsIfDefined(meta.Trait, meta.TraitPiece));
        stats.push(ifDefinedAndGreaterZero(meta.MaxCharge, chargeText(meta.ChargeType)));
        stats.push(ifDefinedAndGreaterZero(meta.RechargeRate, 'Recharge Rate:&nbsp;'));
        stats.push(secondsIfDefined(meta.RechargeDuration, 'Recharge Duration:&nbsp;'));
        if (displayAttack) {
            stats.push(secondsIfDefined(meta.AttackDelaySeconds, 'Attack Delay:&nbsp;', ranged));
            stats.push(secondsIfDefined(meta.ReloadTime, 'Reload Time:&nbsp;'));
        }
        stats.push(accuracyIfDefined(meta.AccuracyPercent, 'Accuracy:&nbsp;', ranged));
        stats.push(repeatableIfDefined(meta.Repeatable));
        text = text.replace(/<p class="helptext__stats">(.+?)<\/p>/,
            '<h3>Stats</h3><p>' + stats.filter(Boolean).join(', ') + '</p>');
    }
    return text;
}

function getAdvancedStats(name, fullId) {
    const items = fullId.split('_');
    const entitytype = items[0];
    const id = items[1];
    let meta = data.data[entitytype][id];
    if (meta === undefined) return '';
    let text = '';
    text += arrayIfDefinedAndNonEmpty(meta.Attacks, '<h3>Attacks</h3>');
    text += arrayIfDefinedAndNonEmpty(meta.Armours, '<h3>Armours</h3>');
    return text;
}

function ifDefined(value, prefix, alwaysDisplay = true) {
    if (value !== undefined && (alwaysDisplay || value > 0)) return ' ' + prefix + value;
    return '';
}
function secondsIfDefined(value, prefix, alwaysDisplay = true) {
    if (value !== undefined && (alwaysDisplay || value > 0)) return ' ' + prefix + toMaxFixed2(value) + 's';
    return '';
}
function toMaxFixed2(value) { return Math.round(value * 100) / 100; }
function accuracyIfDefined(value, prefix, alwaysDisplay) {
    if (value !== undefined && (alwaysDisplay || (0 < value && value < 100))) return ' ' + prefix + value + '%';
    return '';
}
function ifDefinedAndGreaterZero(value, prefix) {
    if (value !== undefined && value > 0) return ' ' + prefix + value;
    return '';
}
function arrayIfDefinedAndNonEmpty(attacks, prefix) {
    if (attacks !== undefined && attacks.length > 0) {
        const strings = attacks.map(a => `${a['Amount']} (${attackAndArmorClasses[a['Class']] || a['Class']})`);
        return prefix + '<p>' + strings.join(', ') + '</p>';
    }
    return '';
}
function repeatableIfDefined(value) {
    if (value !== undefined) return value ? 'Repeatable' : 'Not Repeatable';
    return '';
}
function cost(cost_object) {
    let value = '';
    if ('Food'  in cost_object) value += `<span class="cost food"  title="${cost_object.Food} Food">${cost_object.Food}</span>`;
    if ('Wood'  in cost_object) value += `<span class="cost wood"  title="${cost_object.Wood} Wood">${cost_object.Wood}</span>`;
    if ('Gold'  in cost_object) value += `<span class="cost gold"  title="${cost_object.Gold} Gold">${cost_object.Gold}</span>`;
    if ('Stone' in cost_object) value += `<span class="cost stone" title="${cost_object.Stone} Stone">${cost_object.Stone}</span>`;
    return value;
}

// ── Edit-mode helpers ─────────────────────────────────────────────────────────

function _useTypeKey(useType) {
    // Map use_type from tree JSON → localtree key
    if (useType === 'Unit')     return 'units';
    if (useType === 'Building') return 'buildings';
    if (useType === 'Tech')     return 'techs';
    return null;
}

function _isSelected(item) {
    if (item.use_type === 'Building' && HARD_ALWAYS_ON_BUILDINGS.has(item.node_id)) return true;
    const key = _useTypeKey(item.use_type);
    if (!key) return true;  // unknown types treated as always-selected
    return _localtree[key].includes(item.node_id);
}

// ── Regional building swaps ──────────────────────────────────────────────────

// Every regional building the draft currently has selected.  More than one can
// be active at a time when they replace different camps (Folwark + Mule Cart).
function _activeBuildingSwaps() {
    return _REGIONAL_BUILDING_SWAPS.filter(s => _localtree.buildings.includes(s.id));
}

// The active swap that has taken over a given camp, if any.
function _swapOwningCamp(campId) {
    return _activeBuildingSwaps().find(s => s.replaces.includes(campId)) || null;
}

// Buildings that must be present in _localtree for the current variant.
function _forcedOnBuildings() {
    const forced = new Set(HARD_ALWAYS_ON_BUILDINGS);
    for (const id of _CAMP_BUILDING_IDS) {
        if (!_swapOwningCamp(id)) forced.add(id);
    }
    return forced;
}

function _dropBuilding(id) {
    const idx = _localtree.buildings.indexOf(id);
    if (idx !== -1) _localtree.buildings.splice(idx, 1);
}

function _addBuilding(id) {
    if (!_localtree.buildings.includes(id)) _localtree.buildings.push(id);
}

// Give a swap's camps back and drop the regional building itself.
function _clearSwap(swap) {
    _dropBuilding(swap.id);
    for (const id of swap.replaces) _addBuilding(id);
}

// Adopt a regional building, evicting any active swap that wants the same camps.
// Returns the label of whatever got evicted, for the toast.
function _applySwap(swap) {
    let evicted = null;
    for (const other of _activeBuildingSwaps()) {
        if (other.id === swap.id) continue;
        if (other.replaces.some(id => swap.replaces.includes(id))) {
            _clearSwap(other);
            evicted = other.label;
        }
    }
    _addBuilding(swap.id);
    for (const id of swap.replaces) _dropBuilding(id);
    return evicted;
}

// Re-render after a variant change — the swap moves whole columns around, so it
// changes the layout rather than just which nodes are crossed.
function _refreshAfterVariantChange(message) {
    if (message && typeof window.showToast === 'function') window.showToast(message);
    // The pointer hasn't moved, so no fresh mouseover will fire after the
    // re-render — drop the tooltip rather than leave it describing the old state.
    _hideEditTooltip();
    if (_currentCivName) civ(_currentCivName);
}

// Intercept clicks on a camp or regional building.  Returns true when the click
// was handled as a variant switch (so _toggleNode should not fall through).
function _handleBuildingVariantClick(nodeId) {
    if (_REGIONAL_BUILDING_IDS.has(nodeId)) {
        const swap = _REGIONAL_BUILDING_SWAPS.find(s => s.id === nodeId);
        if (_localtree.buildings.includes(swap.id)) {
            _clearSwap(swap);
            _refreshAfterVariantChange(`${swap.replaced_label} restored.`);
        } else {
            const evicted = _applySwap(swap);
            _refreshAfterVariantChange(
                `${swap.replaced_label} replaced by the ${swap.label}.`
                + (evicted ? ` ${evicted} removed — it needs the same buildings.` : ''));
        }
        return true;
    }
    if (_CAMP_BUILDING_IDS.has(nodeId)) {
        // Camps can't be turned off on their own — clicking one only means
        // "give me this camp back" when a regional building has taken it over.
        const owner = _swapOwningCamp(nodeId);
        if (owner) {
            _clearSwap(owner);
            _refreshAfterVariantChange(`${owner.replaced_label} restored.`);
        }
        return true;
    }
    return false;
}

// ── Regional building layout transform ───────────────────────────────────────

function _itemIndexOf(treeData) {
    const index = {};
    for (const item of treeData.units_techs) index[item.id] = item;
    return index;
}

// Read a building's grid back out as an array of columns of items (top-to-bottom).
function _columnsOf(building, itemIndex) {
    const cols = [];
    const width = building.grid.length ? building.grid[0].length : 0;
    for (let c = 0; c < width; c++) {
        const col = [];
        for (let r = 0; r < building.grid.length; r++) {
            const id = building.grid[r][c];
            if (id && itemIndex[id]) col.push(itemIndex[id]);
        }
        cols.push(col);
    }
    return cols;
}

// Rewrite a building's grid from an array of columns.  Each item keeps its own
// row (which encodes its age), so vertical placement is preserved across moves.
function _setColumns(building, cols) {
    const rows = 8;
    const width = Math.max(cols.length, 1);
    building.grid = Array.from({ length: rows }, () => new Array(width).fill(null));
    cols.forEach((col, c) => {
        for (const item of col) building.grid[item.row][c] = item.id;
    });
}

// Move an item into another building, rewriting the id the DOM/index keys use.
function _reparentItem(item, buildingId) {
    item.building_id = buildingId;
    item.id = `${item.use_type}_${item.node_id}_${buildingId}`;
}

function _findBuilding(treeData, nodeId) {
    return treeData.buildings.find(b => b.node_id === nodeId);
}

function _setFarmHome(treeData, home) {
    const farm = treeData.buildings.find(b => b.node_id === 50 && b.use_type === 'Building');
    if (!farm) return;
    farm.building_id = home.building_id;
    farm.id          = home.id;
    farm.link_id     = home.link_id;
}

function _insertStub(treeData, def, insertAt) {
    const stub = Object.assign({}, def);
    _setColumns(stub, []);
    treeData.buildings.splice(insertAt, 0, stub);
    return stub;
}

// Recreate a standard camp column the loaded layout doesn't have.  POLES.json
// ships a Folwark and no Mill, so switching that civ back to the standard camps
// needs somewhere to put the Mill's techs.
function _ensureCampColumn(treeData, campId) {
    if (_findBuilding(treeData, campId)) return;
    const def = _CAMP_NODE_DEFS[campId];
    if (!def) return;
    // Sit next to whichever camps the layout does have, else at the end.
    let insertAt = treeData.buildings.length;
    for (const other of _CAMP_BUILDING_IDS) {
        const idx = treeData.buildings.findIndex(b => b.node_id === other);
        if (idx !== -1 && idx + 1 < insertAt) insertAt = idx + 1;
    }
    _insertStub(treeData, def, insertAt);
}

// Make sure the regional building has a column in the layout even when it isn't
// selected, so it renders crossed-out and stays clickable.  Without this the
// Settlement would only ever be visible on the four South American layouts that
// ship one, which is exactly why it used to be unreachable from a blank tree.
function _ensureRegionalStub(treeData, swap) {
    if (_findBuilding(treeData, swap.id)) return;
    // Slot it in right after the last camp it replaces.
    let insertAt = treeData.buildings.length;
    for (const rid of swap.replaces) {
        const idx = treeData.buildings.findIndex(b => b.node_id === rid);
        if (idx !== -1 && (insertAt === treeData.buildings.length || idx + 1 > insertAt)) {
            insertAt = idx + 1;
        }
    }
    _insertStub(treeData, swap.node, insertAt);
}

// Fold a regional building column back into the standard camps, so every layout
// starts from the same shape regardless of which civ it came from.  The column
// itself stays (emptied) — it is the control for switching back on.
function _foldRegionalColumn(treeData, swap) {
    const regional = _findBuilding(treeData, swap.id);
    if (!regional) return;

    const itemIndex = _itemIndexOf(treeData);
    const owned = {};
    for (const col of _columnsOf(regional, itemIndex)) {
        for (const item of col) owned[item.node_id] = item;
    }
    // Nothing to fold: the layout is already on the standard camps (this is the
    // normal case, and rebuilding their columns from an empty source would wipe
    // the techs they legitimately own).
    if (!Object.keys(owned).length) return;

    const claimed = new Set();
    for (const rid of swap.replaces) {
        const home = _findBuilding(treeData, rid);
        if (!home) continue;
        const cols = (swap.standard_columns[rid] || []).map(nodeIds => {
            const col = [];
            for (const nid of nodeIds) {
                const item = owned[nid];
                if (!item) continue;
                _reparentItem(item, rid);
                claimed.add(nid);
                col.push(item);
            }
            return col;
        });
        _setColumns(home, cols);
    }

    // Anything else that lived in the regional column (e.g. the Mapuche
    // Skirmisher/Spearman duplicates) has a home elsewhere in the layout, so
    // drop the copy rather than leaving an orphan the renderer can't place.
    const dropped = new Set();
    for (const nid of Object.keys(owned)) {
        if (!claimed.has(Number(nid))) dropped.add(owned[nid].id);
    }
    if (dropped.size) {
        treeData.units_techs = treeData.units_techs.filter(i => !dropped.has(i.id));
    }

    _setColumns(regional, []);
}

// Merge the replaced camps' columns into the regional building's column, leaving
// the camps as empty stubs so they stay visible (crossed) and clickable.
function _unfoldRegionalColumn(treeData, swap) {
    const itemIndex = _itemIndexOf(treeData);
    const cols = [];

    for (const rid of swap.replaces) {
        const home = _findBuilding(treeData, rid);
        if (!home) continue;
        for (const col of _columnsOf(home, itemIndex)) {
            if (!col.length) continue;
            for (const item of col) _reparentItem(item, swap.id);
            cols.push(col);
        }
        _setColumns(home, []);
    }

    _setColumns(_findBuilding(treeData, swap.id), cols);
}

// Put the Dock's siege ship where every shipped layout keeps it, showing the
// one the picker chose (crossed if the draft doesn't include it) and dropping
// any variant belonging to a different civ's layout.
function _applySiegeShipLayout(treeData) {
    const dock = _findBuilding(treeData, _DOCK_BUILDING_ID);
    if (!dock || !dock.grid.length) return;

    const chosenVariant = _SIEGE_VARIANT_IDS.find(id => _localtree.units.includes(id)) || null;
    const wanted = [420, 691];
    if (chosenVariant) wanted.push(chosenVariant);

    // Clear every siege node out of the Dock, then place the ones we want.
    // This also evicts, say, the Aztec Catapult Galleon when the picker says
    // Lou Chuan — otherwise the layout's variant would sit there crossed out
    // while the actual choice had nowhere to show.  Remember where each one was
    // first: a few layouts don't use the usual cells (the Burgundian Dock has no
    // Fast Fire Ship, so their Cannon Galleon sits a column over), and putting a
    // node back where its own layout had it beats any rule we could invent.
    const freed = {};
    const drop = new Set();
    for (const item of treeData.units_techs) {
        if (item.building_id !== _DOCK_BUILDING_ID) continue;
        if (!_PICKER_CONTROLLED_UNITS.has(item.node_id)) continue;
        drop.add(item.id);
        const role = _SIEGE_VARIANT_IDS.includes(item.node_id) ? 'variant' : item.node_id;
        for (let r = 0; r < dock.grid.length; r++) {
            const c = dock.grid[r].indexOf(item.id);
            if (c !== -1) { freed[role] = [c, r]; break; }
        }
    }
    if (drop.size) {
        treeData.units_techs = treeData.units_techs.filter(i => !drop.has(i.id));
        for (let r = 0; r < dock.grid.length; r++) {
            for (let c = 0; c < dock.grid[r].length; c++) {
                if (drop.has(dock.grid[r][c])) dock.grid[r][c] = null;
            }
        }
    }

    const isFree = ([c, r]) =>
        r < dock.grid.length && c < dock.grid[r].length && !dock.grid[r][c];

    for (const uid of wanted) {
        const role = _SIEGE_VARIANT_IDS.includes(uid) ? 'variant' : uid;
        // Its own cell in this layout, then the usual one, then a new column —
        // the Dravidian Thirisadai owns the variant cell, so a fallback is real.
        let cell = [freed[role], _SIEGE_SHIP_CELLS[role]].find(x => x && isFree(x));
        if (!cell) {
            const row = (_SIEGE_SHIP_CELLS[role] || _SIEGE_SHIP_CELLS.variant)[1];
            for (const r of dock.grid) r.push(null);
            cell = [dock.grid[0].length - 1, row];
        }
        const [col, row] = cell;
        const node = Object.assign({}, _SIEGE_SHIP_NODES[uid]);
        node.row = row;
        // Connect to whatever sits directly above in this column, so the line
        // matches the layout rather than a hard-coded predecessor.
        if (node.link_id === null) {
            for (let r = row - 1; r >= 0; r--) {
                const aboveId = dock.grid[r][col];
                if (!aboveId) continue;
                const above = treeData.units_techs.find(i => i.id === aboveId);
                if (above) { node.link_id = above.node_id; node.link_node_type = above.node_type; }
                break;
            }
        }
        treeData.units_techs.push(node);
        dock.grid[row][col] = node.id;
    }
}

// Normalise the loaded layout to the standard camps, then apply whichever
// regional buildings the draft actually selected (more than one can apply when
// they replace different camps, e.g. Folwark + Mule Cart).
function _applyBuildingVariantLayout(treeData) {
    // Every camp needs a column to fold techs back into before anything moves.
    for (const campId of _CAMP_BUILDING_IDS) _ensureCampColumn(treeData, campId);
    for (const swap of _REGIONAL_BUILDING_SWAPS) {
        _foldRegionalColumn(treeData, swap);
        _ensureRegionalStub(treeData, swap);
    }
    const active = _activeBuildingSwaps();
    for (const swap of active) _unfoldRegionalColumn(treeData, swap);

    // The Farm hangs off whichever building owns the Mill.
    const millOwner = active.find(s => s.replaces.includes(68));
    _setFarmHome(treeData, (millOwner && millOwner.farm) || _FARM_STANDARD);
}

// Walk the successor index to collect all items that depend on this one (BFS).
function _getDescendants(item) {
    const descendants = [];
    const queue = [item];
    const visited = new Set();
    while (queue.length > 0) {
        const current = queue.shift();
        const key = `${current.building_id}_${current.node_id}`;
        if (visited.has(key)) continue;
        visited.add(key);
        for (const child of (_successorIndex[key] || [])) {
            if (child.independent) continue; // layout-only link, not an upgrade chain
            descendants.push(child);
            queue.push(child);
        }
    }
    return descendants;
}

// Walk the link_id chain to collect all predecessor items (earliest first).
function _getAncestors(item) {
    if (item.independent) return []; // layout-only link, not an upgrade chain
    const ancestors = [];
    const visited = new Set();
    let current = item;
    while (true) {
        let key;
        if (current.use_type === 'Building') {
            // Buildings chain via building_upgraded_from_id; both parent and child
            // have node_id === building_id so keys are node_id_node_id.
            const fromId = current.building_upgraded_from_id;
            if (fromId === undefined || fromId === -1) break;
            key = `${fromId}_${fromId}`;
        } else {
            const lid = current.link_id;
            if (lid === null || lid === undefined || lid === -1) break;
            key = `${current.building_id}_${lid}`;
        }
        if (visited.has(key)) break;
        visited.add(key);
        const ancestor = _nodeIndex[key];
        if (!ancestor) break;
        ancestors.push(ancestor);
        current = ancestor;
    }
    return ancestors;
}

function _removeNodeCross(itemId) {
    document.getElementById(`${itemId}_disabled_gray`)?.remove();
    document.getElementById(`${itemId}_x`)?.remove();
}

function _addNodeCross(item, element_height) {
    const group = SVG('#' + item.id);
    if (!group) return;
    group.rect(element_height, element_height)
        .attr({ fill: '#000', opacity: 0.2, id: `${item.id}_disabled_gray` })
        .move(item.x, item.y);
    group.image(_imgroot + '/cross.png')
        .size(element_height * 0.7, element_height * 0.7)
        .attr({ id: item.id + '_x' })
        .addClass('cross')
        .move(item.x + element_height * 0.15, item.y - element_height * 0.04);
    // Keep overlay on top so it continues receiving clicks.
    const overlayDom = document.getElementById(`${item.id}_overlay`);
    if (overlayDom) overlayDom.parentNode.appendChild(overlayDom);
}

function _disableSingle(item, element_height) {
    // Cascades (e.g. switching the Dock off) must not strip the picker's ship
    // either — the backend puts it back, so removing it here would only make
    // the tree disagree with the build.
    if (_isExternallyControlled(item)) return;
    const key = _useTypeKey(item.use_type);
    if (!key) return;
    const arr = _localtree[key];
    const idx = arr.indexOf(item.node_id);
    if (idx !== -1) { arr.splice(idx, 1); _addNodeCross(item, element_height); }
}

function _disableBuildingItems(building, element_height) {
    for (const child of (_buildingItems[building.node_id] || [])) {
        _disableSingle(child, element_height);
    }
}

function _toggleNode(item, element_height) {
    // The siege ship is owned by the wizard's picker and the regional second
    // unique units by their bonus cards — neither decision lives in this tree.
    if (_isExternallyControlled(item)) return;

    if (item.use_type === 'Building') {
        // Town Center and House can never be toggled.
        if (HARD_ALWAYS_ON_BUILDINGS.has(item.node_id)) return;
        // Camps and the regional buildings that replace them are a set of
        // mutually exclusive variants, not independent on/off switches.
        if (_handleBuildingVariantClick(item.node_id)) return;
    }

    const key = _useTypeKey(item.use_type);
    if (!key) return;
    const arr = _localtree[key];
    const idx = arr.indexOf(item.node_id);
    if (idx === -1) {
        // Enable: add this item, then cascade-enable all ancestors in the upgrade chain.
        arr.push(item.node_id);
        _removeNodeCross(item.id);
        for (const ancestor of _getAncestors(item)) {
            // Skip buildings that aren't independently toggleable — always-on
            // ones, and camps/regional buildings owned by the variant switch
            // (cascading into those could re-add a camp the Settlement replaced).
            if (ancestor.use_type === 'Building'
                    && (HARD_ALWAYS_ON_BUILDINGS.has(ancestor.node_id)
                        || _CAMP_BUILDING_IDS.has(ancestor.node_id)
                        || _REGIONAL_BUILDING_IDS.has(ancestor.node_id))) continue;
            const aKey = _useTypeKey(ancestor.use_type);
            if (!aKey) continue;
            const aArr = _localtree[aKey];
            if (!aArr.includes(ancestor.node_id)) {
                aArr.push(ancestor.node_id);
                _removeNodeCross(ancestor.id);
            }
        }
        // Regional mutual exclusivity: evict the opposing group if any of its units are present.
        const pair = _REGIONAL_PAIRS.find(p =>
            p.bldg === item.building_id &&
            (p.a.includes(item.node_id) || p.b.includes(item.node_id))
        );
        if (pair) {
            const inA     = pair.a.includes(item.node_id);
            const evictIds = inA ? pair.b : pair.a;
            const evictName = inA ? pair.nameB : pair.nameA;
            const myName    = inA ? pair.nameA : pair.nameB;
            let evicted = false;
            for (const uid of evictIds) {
                const oItem = _nodeIndex[`${pair.bldg}_${uid}`];
                if (oItem && _localtree.units.includes(uid)) {
                    _disableSingle(oItem, element_height);
                    evicted = true;
                }
            }
            if (evicted && typeof window.showToast === 'function') {
                window.showToast(
                    `${evictName} removed — only one of ${myName} or ${evictName} may be selected at a time.`
                );
            }
        }
    } else {
        // Disable: cascade to upgrade-chain successors; also clear all items in any disabled building.
        _disableSingle(item, element_height);
        if (item.use_type === 'Building') _disableBuildingItems(item, element_height);
        for (const desc of _getDescendants(item)) {
            _disableSingle(desc, element_height);
            if (desc.use_type === 'Building') _disableBuildingItems(desc, element_height);
        }
    }
}

// ── Edit-mode hover tooltip ───────────────────────────────────────────────────

function _buildNodeIdToCivs() {
    _nodeIdToCivs = {};
    for (const [civName, civData] of Object.entries(data.civs || {})) {
        for (const type of ['Unit', 'Building', 'Tech']) {
            for (const nodeId of (civData[type] || [])) {
                if (!_nodeIdToCivs[nodeId]) _nodeIdToCivs[nodeId] = [];
                _nodeIdToCivs[nodeId].push(civName);
            }
        }
    }
}

function _helpText(item) {
    const helpId = item.name_string_id + (item.use_type === 'Tech' ? 11000 : 12000);
    let raw = data.strings[String(helpId)];
    if (!raw) return '';
    // Drop placeholder tokens (‹cost›, ‹hp›, ‹attack›, etc.)
    raw = raw.replace(/‹[^›]*›/g, '').replace(/‹DEFAULT›/g, '');
    // The first line repeats the name/action — skip it; show only the description body.
    const brMatch = raw.match(/<br\s*\/?>\n?/i);
    if (brMatch) raw = raw.slice(brMatch.index + brMatch[0].length);
    // Collapse whitespace and trim
    return raw.replace(/\s+/g, ' ').trim();
}

function _costHtml(costObj) {
    if (!costObj) return '';
    const parts = [];
    if (costObj.Food)  parts.push(`${costObj.Food}F`);
    if (costObj.Wood)  parts.push(`${costObj.Wood}W`);
    if (costObj.Gold)  parts.push(`${costObj.Gold}G`);
    if (costObj.Stone) parts.push(`${costObj.Stone}S`);
    return parts.join(' · ');
}

// Explain what clicking a camp / regional building does — the swap is the one
// interaction in the editor that isn't a plain on/off toggle.
function _variantHint(item) {
    if (item.use_type === 'Unit' && _PICKER_CONTROLLED_UNITS.has(item.node_id)) {
        return _PICKER_HINT;
    }
    if (item.use_type === 'Unit' && _BONUS_CONTROLLED_UNITS.has(item.node_id)) {
        return _BONUS_HINT;
    }
    if (item.use_type !== 'Building') return '';
    if (_REGIONAL_BUILDING_IDS.has(item.node_id)) {
        const swap = _REGIONAL_BUILDING_SWAPS.find(s => s.id === item.node_id);
        if (_localtree.buildings.includes(swap.id)) {
            return `Click to go back to the ${swap.replaced_label}.`;
        }
        // Warn up front if picking this one costs another regional building.
        const conflict = _activeBuildingSwaps().find(
            o => o.id !== swap.id && o.replaces.some(id => swap.replaces.includes(id)));
        return `Click to replace the ${swap.replaced_label} with the ${swap.label}.`
            + (conflict ? ` Removes the ${conflict.label}.` : '');
    }
    if (_CAMP_BUILDING_IDS.has(item.node_id)) {
        const owner = _swapOwningCamp(item.node_id);
        return owner
            ? `Replaced by the ${owner.label} — click to restore.`
            : 'Always available.';
    }
    if (HARD_ALWAYS_ON_BUILDINGS.has(item.node_id)) return 'Always available.';
    return '';
}

function _showEditTooltip(itemToDraw, svgNodeLeft, svgNodeRight, svgY) {
    const svgX = svgNodeRight; // keep existing references below working
    const panel = document.getElementById('helptext');
    const content = document.getElementById('helptext__content');
    if (!panel || !content) return;

    const name = formatName(data.strings[itemToDraw.name_string_id] || '?');
    const idParts = itemToDraw.id.split('_');  // e.g. ["Unit","4","87"]
    const dataType = idParts[0];               // "Unit", "Tech", "Building"
    const dataId   = idParts[1];

    let costLine = '';
    let statsLine = '';
    const meta = data.data?.[dataType]?.[dataId];
    if (meta) {
        const c = _costHtml(meta.Cost);
        if (c) costLine = `<div style="margin-top:4px;font-size:11px;opacity:.8;">Cost: ${c}</div>`;
        if (meta.HP) {
            const parts = [`HP ${meta.HP}`];
            if (meta.Attack > 0) parts.push(`Atk ${meta.Attack}`);
            if (meta.MeleeArmor !== undefined) parts.push(`MA ${meta.MeleeArmor}/${meta.PierceArmor}`);
            statsLine = `<div style="margin-top:2px;font-size:11px;opacity:.7;">${parts.join(' · ')}</div>`;
        }
    }

    const totalCivs = Object.keys(data.civs || {}).length;
    const haveCivs  = (_nodeIdToCivs[itemToDraw.node_id] || []).length;
    const civLine   = totalCivs
        ? `<div style="margin-top:4px;font-size:11px;opacity:.7;">${haveCivs} / ${totalCivs} civs</div>`
        : '';

    const desc = _helpText(itemToDraw);
    const descLine = desc
        ? `<div style="margin-top:5px;font-size:11px;line-height:1.4;opacity:.88;">${desc}</div>`
        : '';

    const hint = _variantHint(itemToDraw);
    const hintLine = hint
        ? `<div style="margin-top:5px;font-size:11px;font-weight:600;color:#7a4a00;">${hint}</div>`
        : '';

    content.innerHTML = `<div style="font-weight:700;font-size:13px;">${name}</div>${costLine}${statsLine}${descLine}${hintLine}${civLine}`;
    document.getElementById('helptext__advanced_stats').innerHTML = '';
    panel.style.display = 'block';

    // Position near the node
    const treeEl = document.getElementById('techtree');
    const wrap   = treeEl?.parentElement;
    const scrollX = wrap ? wrap.scrollLeft : 0;
    const offsetX = treeEl ? treeEl.getBoundingClientRect().left - (wrap?.getBoundingClientRect().left || 0) + scrollX : 0;
    let left = svgX + offsetX + 10;
    const pw = panel.offsetWidth  || 260;
    const ph = panel.offsetHeight || 80;
    const ww = wrap ? wrap.offsetWidth  : window.innerWidth;
    const wh = wrap ? wrap.getBoundingClientRect().height : window.innerHeight;
    // Flip horizontally if the tooltip would overflow the right edge.
    // Use the node's LEFT edge so the popup opens clear of the card.
    if (left + pw > ww + scrollX) left = svgNodeLeft + offsetX - pw - 10;
    // Flip vertically: grow upward when the tooltip would go below the fold.
    let top = svgY + 10;
    if (top + ph > wh) top = svgY - ph - 5;
    top = Math.max(5, top);  // clamp so it never clips the top edge
    panel.style.left = left + 'px';
    panel.style.top  = top  + 'px';
}

function _hideEditTooltip() {
    const panel = document.getElementById('helptext');
    if (panel) panel.style.display = 'none';
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function hasItemsInGrid(building) {
    for (const row of building.grid)
        for (const item of row)
            if (item !== null) return true;
    return false;
}

function drawGrid(building, element_height, tree_height, draw, index) {
    for (let row = 0; row < building.grid.length; row++) {
        for (let col = 0; col < building.grid[row].length; col++) {
            const itemId = building.grid[row][col];
            if (itemId) drawItem(index[itemId], element_height, tree_height, draw);
        }
    }
}

function drawItem(itemToDraw, element_height, tree_height, draw) {
    const item = draw.group().attr({ id: itemToDraw.id }).addClass('node');
    item.rect(element_height, element_height).attr({
        fill: getColourForNodeType(itemToDraw.node_type || itemToDraw.use_type),
        id: `${itemToDraw.id}_bg`
    }).move(itemToDraw.x, itemToDraw.y);

    const name = formatName(data.strings[itemToDraw.name_string_id]);
    // Text anchored near the card bottom. SVG.js splits on \n → two tspans stacking downward,
    // so position the first line high enough that the second line still clears the card edge.
    item.text(name.toString())
        .font({ size: 11, weight: '500', leading: 0.85 })
        .attr({ fill: '#fff', opacity: 1, 'text-anchor': 'middle', id: itemToDraw.id + '_text' })
        .cx(itemToDraw.x + element_height / 2)
        .y(itemToDraw.y + element_height * 0.67);

    // Image occupies the top 58% of the card, centered horizontally.
    const imgSize = element_height * 0.58;
    const imgX = itemToDraw.x + (element_height - imgSize) / 2;
    item.rect(imgSize, imgSize)
        .attr({ fill: '#ffffff', opacity: 0.3, id: itemToDraw.id + '_imgph' })
        .move(imgX, itemToDraw.y + 2);

    item.image(_imgroot + '/' + itemToDraw.use_type + '/' + itemToDraw.picture_index + '.png')
        .size(imgSize, imgSize)
        .attr({ id: itemToDraw.id + '_img' })
        .move(imgX, itemToDraw.y + 2);

    // In edit mode: show cross if not in localtree; otherwise use node_status
    const disabled = _canEdit ? !_isSelected(itemToDraw) : (itemToDraw.node_status === 'NotAvailable');
    if (disabled) {
        item.rect(element_height, element_height)
            .attr({ fill: '#000', opacity: 0.2, id: `${itemToDraw.id}_disabled_gray` })
            .move(itemToDraw.x, itemToDraw.y);
        item.image(_imgroot + '/cross.png')
            .size(element_height * 0.7, element_height * 0.7)
            .attr({ id: itemToDraw.id + '_x' })
            .addClass('cross')
            .move(itemToDraw.x + element_height * 0.15, itemToDraw.y - element_height * 0.04);
    }

    item.rect(element_height, element_height)
        .attr({ id: itemToDraw.id + '_overlay', fill: 'transparent' })
        .addClass('node__overlay')
        .move(itemToDraw.x, itemToDraw.y)
        .data({ type: itemToDraw.node_type, caret: itemToDraw, name: itemToDraw.name, id: itemToDraw.id })
        .mouseover(function (e) {
            highlightPath(itemToDraw.id);
            if (_canEdit) _showEditTooltip(itemToDraw, itemToDraw.x, itemToDraw.x + element_height, itemToDraw.y);
        })
        .mouseout(function () {
            resetHighlightPath();
            if (_canEdit) _hideEditTooltip();
        })
        .click(function () {
            if (_canEdit) {
                _toggleNode(itemToDraw, element_height);
            } else {
                if (focusedNodeId === itemToDraw.id) hideHelp();
                else displayHelp(itemToDraw.id, itemToDraw.help_string_id, element_height, tree_height);
            }
        });
}

function techtreeDoesNotHaveScrollbar() {
    const el = document.getElementById('techtree');
    return el.scrollHeight <= el.clientHeight;
}
function shiftKeyIsNotPressed(e) { return !e.shiftKey; }

// ── civ() — load and render a per-civ tree ────────────────────────────────────

// Common (non-civ-specific) castle tech node_ids that are always shown.
const COMMON_CASTLE_TECH_IDS = new Set([315, 379, 408, 321]); // Conscription, Hoardings, Spies, Sappers

function _stripCastleUuAndUt(treeData) {
    const utIndex = {};
    for (const ut of treeData.units_techs) utIndex[ut.id] = ut;
    for (const b of treeData.buildings) {
        if (b.name !== 'Castle') continue;
        for (let r = 0; r < b.grid.length; r++) {
            for (let c = 0; c < b.grid[r].length; c++) {
                const id = b.grid[r][c];
                if (!id) continue;
                const ut = utIndex[id];
                if (!ut) continue;
                if (ut.node_type === 'UniqueUnit') { b.grid[r][c] = null; continue; }
                if (ut.use_type === 'Tech' && !COMMON_CASTLE_TECH_IDS.has(ut.node_id)) {
                    b.grid[r][c] = null;
                }
            }
        }
    }
}

function civ(civName) {
    _currentCivName = civName;
    const era = (data.civs && data.civs[civName]) ? data.civs[civName].era : 'base';

    loadJson(_treeroot + '/' + civName.toUpperCase() + '.json', function (treeData) {
        _stripCastleUuAndUt(treeData);
        _applyBuildingVariantLayout(treeData);
        _applySiegeShipLayout(treeData);
        const root = document.getElementById('root');
        if (root) document.getElementById('techtree').removeChild(root);

        const tree_height = Math.max(window.innerHeight - 80, 100);
        const row_height  = tree_height / 4;
        const element_height = row_height * 0.38;

        const connections = [];
        const index = {};
        _nodeIndex = {};
        _successorIndex = {};
        _buildingItems = {};
        _itemToBuilding = {};
        // Guarantee always-on buildings are present in _localtree regardless of
        // saved state.  Camps count as always-on only while no regional building
        // has replaced them.
        for (const id of _forcedOnBuildings()) {
            if (!_localtree.buildings.includes(id)) _localtree.buildings.push(id);
        }
        for (const building of treeData.buildings) {
            index[building.id] = building;
            // Buildings are keyed as node_id_node_id (since building_id === node_id for buildings).
            _nodeIndex[`${building.node_id}_${building.node_id}`] = building;
            // Use building_upgraded_from_id (not link_id) to determine the real
            // upgrade chain, avoiding false dependencies like Outpost→Watch Tower.
            const fromId = building.building_upgraded_from_id;
            if (fromId !== undefined && fromId !== -1) {
                const parentKey = `${fromId}_${fromId}`;
                if (!_successorIndex[parentKey]) _successorIndex[parentKey] = [];
                _successorIndex[parentKey].push(building);
            }
        }
        for (const item of treeData.units_techs) {
            index[item.id] = item;
            // Key by building_id+node_id to avoid conflicts when different buildings
            // share a node_id (e.g. node 93 = Spearman in Barracks AND a University tech).
            _nodeIndex[`${item.building_id}_${item.node_id}`] = item;
            if (item.link_id !== null && item.link_id !== undefined && item.link_id !== -1) {
                const parentKey = `${item.building_id}_${item.link_id}`;
                if (!_successorIndex[parentKey]) _successorIndex[parentKey] = [];
                _successorIndex[parentKey].push(item);
            }
            if (!_buildingItems[item.building_id]) _buildingItems[item.building_id] = [];
            _buildingItems[item.building_id].push(item);
            // Used by highlightPath to climb to the parent building even when no
            // visual connection line exists (e.g. Caravan/Guilds stacked below Trade Cart).
            _itemToBuilding[item.id] = index[`Building_${item.building_id}_${item.building_id}`] || null;
            item.y = item.row * row_height / 2 + TOP_PADDING;
        }

        let startX = 172, width = 0, previousRow = 0;
        let previousBuildingInOwnColumn = true, previousNodeType = '';
        for (let building of treeData.buildings) {
            const thisBuildingWidth = building.grid[0].length * (element_height + PADDING_BETWEEN_COLUMNS);
            if (building.building_in_new_column === true || previousBuildingInOwnColumn
                    || hasItemsInGrid(building) || previousRow > building.row
                    || previousNodeType !== building.node_type) {
                startX += width + PADDING;
                width = thisBuildingWidth;
            } else {
                width = Math.max(width, thisBuildingWidth);
                if (previousRow === building.row) building.row++;
            }
            if (building.link_id !== -1) {
                for (let lb of treeData.buildings) {
                    if (lb.node_id === building.link_id && lb.row === building.row) building.row++;
                }
            }
            building.x = startX + width / 2 - (element_height + PADDING_BETWEEN_COLUMNS) / 2;
            building.y = building.row * row_height / 2 + TOP_PADDING;
            for (let r = 0; r < building.grid.length; r++) {
                for (let c = 0; c < building.grid[r].length; c++) {
                    const iId = building.grid[r][c];
                    if (iId) index[iId].x = startX + c * (element_height + PADDING_BETWEEN_COLUMNS);
                }
            }
            previousRow = building.row;
            previousNodeType = building.node_type;
            previousBuildingInOwnColumn = building.building_in_new_column !== false;
        }
        startX += width;

        for (let building of treeData.buildings) {
            if (building.building_upgraded_from_id !== -1 && building.building_upgraded_from_id !== null) {
                for (let lb of treeData.buildings) {
                    if (lb.node_id === building.building_upgraded_from_id) connections.push([lb.id, building.id]);
                }
            } else if (building.link_id !== -1) {
                for (let lb of treeData.buildings) {
                    if (lb.node_id === building.link_id && building.link_node_type === lb.node_type
                            && ((lb.building_in_new_column !== false) || (lb.node_id === building.building_id))) {
                        connections.push([lb.id, building.id]);
                    }
                }
            }
            for (let r = 0; r < building.grid.length; r++) {
                for (let c = 0; c < building.grid[r].length; c++) {
                    const iId = building.grid[r][c];
                    if (!iId) continue;
                    const item = index[iId];
                    if (item.link_id !== -1 && item.link_id !== null) {
                        for (let sr = r - 1; sr >= 0; sr--) {
                            const topId = building.grid[sr][c];
                            if (topId) {
                                const top = index[topId];
                                if (item.link_id === top.node_id && item.link_node_type === top.node_type)
                                    connections.push([top.id, item.id]);
                                break;
                            }
                        }
                    } else {
                        let drawToBldg = true;
                        for (let sr = r - 1; sr >= 0; sr--) {
                            if (building.grid[sr][c]) { drawToBldg = false; break; }
                        }
                        if (drawToBldg) connections.push([building.id, item.id]);
                    }
                }
            }
        }

        parentConnections = new Map();
        connections.forEach(([parent, child]) => {
            if (!parentConnections.has(child)) parentConnections.set(child, []);
            parentConnections.get(child).push(parent);
        });

        const tree_width = startX + PADDING_BETWEEN_COLUMNS;
        const draw = SVG().addTo('#techtree').id('root').size(tree_width, tree_height)
            .click((e) => { if (e.target.id === 'root') hideHelp(); });
        document.getElementById('techtree').onclick = (e) => { if (e.target.id === 'techtree') hideHelp(); };

        // Age row highlights (subtle amber on parchment)
        draw.rect(tree_width, row_height).attr({ fill: '#7a5010', opacity: 0.12 }).click(hideHelp);
        draw.rect(tree_width, row_height).attr({ fill: '#7a5010', opacity: 0.12 }).click(hideHelp).y(row_height * 2);

        // Age icons
        const icon_height = Math.min(row_height / 2, 112);
        const icon_width = 112;
        const vertical_spacing = (row_height - icon_height) / 2 - 10;
        const margin_left = 20;
        const image_urls = AGE_IMAGES[era] || AGE_IMAGES['base'];
        const age_name_list = getAgeNames(era);
        for (let i = 0; i < image_urls.length; i++) {
            const grp = draw.group().click(hideHelp);
            const img = grp.image(_imgroot + '/Ages/' + image_urls[i])
                .size(icon_width, icon_height).x(margin_left).y(row_height * i + vertical_spacing);
            grp.text(age_name_list[i] || '')
                .font({ size: 16, weight: 'bold' })
                .cx(icon_width / 2 + margin_left)
                .y(img.attr('y') + img.attr('height') + 5);
        }

        // Connection lines
        const cg = draw.group().attr({ id: 'connection_lines' });
        for (let conn of connections) {
            const from = index[conn[0]], to = index[conn[1]];
            const off = element_height / 2;
            const ih = (from.y + off) + (element_height * 2 / 3);
            cg.polyline([from.x + off, from.y + off, from.x + off, ih, to.x + off, ih, to.x + off, to.y + off])
                .attr({ id: `connection_${conn[0]}_${conn[1]}`, fill: 'none', stroke: 'rgba(60,30,10,0.6)', 'stroke-width': 1.5 })
                .addClass('connection').click(hideHelp);
        }

        // Draw all nodes
        for (const building of treeData.buildings) {
            drawItem(building, element_height, tree_height, draw);
            drawGrid(building, element_height, tree_height, draw, index);
        }
    });
}

// ── showTechtree — wizard embed API ──────────────────────────────────────────
//
// civName:     civ whose layout to display (e.g. "Britons", or null for "full")
// initialTree: [[unitIds], [buildingIds], [techIds]] — starting selection
// relativepath: Flask static prefix, e.g. "/static"
//
window.showTechtree = function showTechtree(civName, initialTree, relativepath) {
    relativepath = relativepath || '/static';
    _imgroot  = relativepath + '/aoe2techtree/img';
    _treeroot = relativepath + '/aoe2techtree/data/trees';
    _locroot  = relativepath + '/aoe2techtree/data/locales';
    _canEdit  = true;

    // Normalise initialTree: [[units],[buildings],[techs]] or null/undefined
    _localtree = {
        units:     (initialTree && initialTree[0]) ? initialTree[0].slice() : [],
        buildings: (initialTree && initialTree[1]) ? initialTree[1].slice() : [],
        techs:     (initialTree && initialTree[2]) ? initialTree[2].slice() : [],
    };

    // Hide the rest of the page
    document.querySelectorAll('body > *').forEach(el => { el.hidden = true; });

    // Build overlay container
    const container = document.createElement('div');
    container.id = 'tt-container';
    container.style.cssText = [
        'position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;overflow:hidden;',
        'background:#c8a96e url("/static/aoe2techtree/img/Backgrounds/bg_aoe2_hd_paper.jpg") repeat;',
    ].join('');

    // Toolbar
    const toolbar = document.createElement('div');
    toolbar.id = 'tt-toolbar';
    toolbar.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(60,30,10,0.82);border-bottom:2px solid #7a5c2e;flex-shrink:0;';

    const btnStyle = 'padding:5px 12px;border:1px solid rgba(255,255,255,0.25);border-radius:4px;cursor:pointer;font-size:13px;';
    const mkBtn = (label, bg, fn) => {
        const b = document.createElement('button');
        b.textContent = label;
        b.style.cssText = btnStyle + 'background:' + bg + ';color:#fff;';
        b.onclick = fn;
        return b;
    };

    const doneBtn  = mkBtn('Save Tech Tree', '#2c5729', _saveTechTree);
    const fillBtn  = mkBtn('Enable All',     '#4a3a10', _fillAll);
    const resetBtn = mkBtn('Disable All',    '#5a1a1a', _disableAll);
    const hint     = document.createElement('span');
    hint.style.cssText = 'color:#aaa;font-size:12px;margin-left:8px;';
    hint.textContent = 'Click a unit/tech/building to toggle it on or off.';

    toolbar.appendChild(doneBtn);
    toolbar.appendChild(fillBtn);
    toolbar.appendChild(resetBtn);
    toolbar.appendChild(hint);

    // Inject tree-specific styles (no external CSS file loaded in wizard context)
    const ttStyle = document.createElement('style');
    ttStyle.id = 'tt-tree-styles';
    ttStyle.textContent = `
        .connection.is-highlight { stroke: #fff !important; stroke-width: 2px !important; }
        .node.is-highlight .node__overlay { outline: 2px solid #fff; border-radius: 2px; }
        #helptext {
            background: rgba(245,225,170,0.97);
            border: 1px solid #8b6d35;
            border-radius: 6px;
            padding: 9px 12px;
            font-size: 14px;
            color: #2a1a05;
            pointer-events: none;
            box-shadow: 2px 3px 10px rgba(0,0,0,0.25);
            width: 400px;
            line-height: 1.4;
        }
        #helptext details { display: none; }
    `;
    document.head.appendChild(ttStyle);

    // Help panel
    const helptext = document.createElement('div');
    helptext.id = 'helptext';
    helptext.style.cssText = 'display:none;position:absolute;z-index:10000;';
    helptext.innerHTML = '<div id="helptext__content"></div><div id="helptext__advanced_stats"></div>';

    // Tree panel
    const treeWrap = document.createElement('div');
    treeWrap.style.cssText = 'flex:1;overflow:auto;position:relative;';
    const treeEl = document.createElement('div');
    treeEl.id = 'techtree';
    treeEl.style.cssText = 'width:max-content;min-height:100%;';
    treeWrap.appendChild(treeEl);
    treeWrap.appendChild(helptext);

    container.appendChild(toolbar);
    container.appendChild(treeWrap);
    document.body.appendChild(container);

    // Scroll-to-horizontal with mouse wheel
    // treeWrap.addEventListener('wheel', function (e) {
    //     if (e.deltaX !== 0) return;
    //     if (!e.shiftKey && treeEl.scrollHeight <= treeEl.clientHeight) {
    //         treeWrap.scrollLeft += e.deltaY > 0 ? 150 : -150;
    //     }
    // });

    // Load data then render
    const dataUrl = relativepath + '/aoe2techtree/data/data.json';
    const locUrl  = relativepath + '/aoe2techtree/data/locales/en/strings.json';

    loadJson(dataUrl, function (resp) {
        data = resp;
        loadJson(locUrl, function (strings) {
            data.strings = strings;
            _buildNodeIdToCivs();
            const resolvedCiv = civName || 'Britons';
            civ(resolvedCiv);
        });
    });
};

function _saveTechTree() {
    if (window.setTechTree) {
        window.setTechTree([
            _localtree.units.slice(),
            _localtree.buildings.slice(),
            _localtree.techs.slice(),
        ]);
    }
    _closeTreeOverlay();
}

function _closeTreeOverlay() {
    const container = document.getElementById('tt-container');
    if (container) container.remove();
    document.getElementById('tt-tree-styles')?.remove();
    document.querySelectorAll('body > *').forEach(el => { el.hidden = false; });
    _canEdit = false;
    focusedNodeId = null;
}

function _fillAll() {
    // Re-render with all items enabled: gather all node_ids from the current civ tree.
    // Regional replacement units (Champi, Hei Guang, Rocket Cart, Armored/Siege Elephant)
    // are excluded — standard lines (Militia, Knight, Mangonel, Ram) are kept.
    if (!_currentCivName) return;
    // The picker owns the siege ship — carry the current choice across.
    const keepShips = _localtree.units.filter(id => _PICKER_CONTROLLED_UNITS.has(id));
    loadJson(_treeroot + '/' + _currentCivName.toUpperCase() + '.json', function (treeData) {
        _localtree = { units: keepShips.slice(), buildings: [], techs: [] };
        const seen = { units: new Set(keepShips), buildings: new Set(), techs: new Set() };
        const push = (key, id) => {
            if (seen[key].has(id)) return;   // layouts can list a node twice
            seen[key].add(id);
            _localtree[key].push(id);
        };
        for (const b of treeData.buildings) {
            // Regional buildings are opt-in, same as regional units — "Enable
            // All" keeps the standard Mill / Lumber Camp / Mining Camp.
            if (_REGIONAL_BUILDING_IDS.has(b.node_id)) continue;
            push('buildings', b.node_id);
        }
        for (const id of _CAMP_BUILDING_IDS) push('buildings', id);
        for (const item of treeData.units_techs) {
            const key = _useTypeKey(item.use_type);
            if (key === 'units' && _REGIONAL_UNIT_IDS.has(item.node_id)) continue;
            // Never enable a siege ship the picker didn't ask for.
            if (_isExternallyControlled(item)) continue;
            // Second unique units are opt-in extras, and Bolas Rider / Xianbei
            // Raider would land on the Cavalry Archer's button — "Enable All"
            // should not quietly hand out a colliding tree.
            if (key === 'units' && _BONUS_CONTROLLED_UNITS.has(item.node_id)) continue;
            if (key) push(key, item.node_id);
        }
        civ(_currentCivName);
    });
}

function _disableAll() {
    // Resets to the standard camps — the regional building is a deliberate pick.
    // The siege ship survives: it belongs to the picker, not to this tree.
    const keepShips = _localtree.units.filter(id => _PICKER_CONTROLLED_UNITS.has(id));
    _localtree = { units: keepShips, buildings: [], techs: [] };
    _localtree.buildings = [...HARD_ALWAYS_ON_BUILDINGS, ..._CAMP_BUILDING_IDS];
    if (_currentCivName) civ(_currentCivName);
}
