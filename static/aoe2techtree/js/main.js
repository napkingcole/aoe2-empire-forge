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
    return name.replace(/<br\s*\/?>/gi, ' ').trim();
}

function resetHighlightPath() {
    unhighlightPath();
    if (focusedNodeId) highlightPath(focusedNodeId);
}

function unhighlightPath() {
    SVG.find('.node.is-highlight, .connection.is-highlight')
        .each((el) => el.removeClass('is-highlight'));
}

function highlightPath(caretId) {
    recurse(caretId);
    function recurse(caretId) {
        SVG('#' + caretId).addClass('is-highlight');
        const parentIds = parentConnections.get(caretId);
        if (!parentIds) return;
        for (let parentId of parentIds) {
            const line = SVG(`#connection_${parentId}_${caretId}`);
            if (line) line.front().addClass('is-highlight');
            recurse(parentId);
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
    const key = _useTypeKey(item.use_type);
    if (!key) return true;  // unknown types treated as always-selected
    return _localtree[key].includes(item.node_id);
}

function _toggleNode(item, element_height) {
    const key = _useTypeKey(item.use_type);
    if (!key) return;
    const arr = _localtree[key];
    const idx = arr.indexOf(item.node_id);
    if (idx === -1) {
        // add — remove cross overlay via native DOM (SVG.js selector is unreliable here)
        arr.push(item.node_id);
        document.getElementById(`${item.id}_disabled_gray`)?.remove();
        document.getElementById(`${item.id}_x`)?.remove();
    } else {
        // remove — add cross overlay, then move the click-capture rect back on top
        arr.splice(idx, 1);
        const group = SVG('#' + item.id);
        if (group) {
            group.rect(element_height, element_height)
                .attr({ fill: '#000', opacity: 0.2, id: `${item.id}_disabled_gray` })
                .move(item.x, item.y);
            group.image(_imgroot + '/cross.png')
                .size(element_height * 0.7, element_height * 0.7)
                .attr({ id: item.id + '_x' })
                .addClass('cross')
                .move(item.x + element_height * 0.15, item.y - element_height * 0.04);
            // Gray rect + cross were appended after the overlay, covering it.
            // Move the overlay DOM node to the end so it stays on top and receives clicks.
            const overlayDom = document.getElementById(`${item.id}_overlay`);
            if (overlayDom) overlayDom.parentNode.appendChild(overlayDom);
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

function _costHtml(costObj) {
    if (!costObj) return '';
    const parts = [];
    if (costObj.Food)  parts.push(`${costObj.Food}F`);
    if (costObj.Wood)  parts.push(`${costObj.Wood}W`);
    if (costObj.Gold)  parts.push(`${costObj.Gold}G`);
    if (costObj.Stone) parts.push(`${costObj.Stone}S`);
    return parts.join(' · ');
}

function _showEditTooltip(itemToDraw, svgX, svgY) {
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

    content.innerHTML = `<div style="font-weight:700;font-size:13px;">${name}</div>${costLine}${statsLine}${civLine}`;
    document.getElementById('helptext__advanced_stats').innerHTML = '';
    panel.style.display = 'block';

    // Position near the node
    const treeEl = document.getElementById('techtree');
    const wrap   = treeEl?.parentElement;
    const scrollX = wrap ? wrap.scrollLeft : 0;
    const offsetX = treeEl ? treeEl.getBoundingClientRect().left - (wrap?.getBoundingClientRect().left || 0) + scrollX : 0;
    let left = svgX + offsetX + 10;
    let top  = svgY + 10;
    const pw = panel.offsetWidth || 180;
    const ww = wrap ? wrap.offsetWidth : window.innerWidth;
    if (left + pw > ww + scrollX) left = svgX + offsetX - pw - 10;
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
    item.text(name.toString())
        .font({ size: 9, weight: 'bold' })
        .attr({ fill: '#1a1a1a', opacity: 0.9, 'text-anchor': 'middle', id: itemToDraw.id + '_text' })
        .cx(itemToDraw.x + element_height / 2)
        .y(itemToDraw.y + element_height / 1.5);

    item.rect(element_height * 0.6, element_height * 0.6)
        .attr({ fill: '#ffffff', opacity: 0.3, id: itemToDraw.id + '_imgph' })
        .move(itemToDraw.x + element_height * 0.2, itemToDraw.y);

    item.image(_imgroot + '/' + itemToDraw.use_type + '/' + itemToDraw.picture_index + '.png')
        .size(element_height * 0.6, element_height * 0.6)
        .attr({ id: itemToDraw.id + '_img' })
        .move(itemToDraw.x + element_height * 0.2, itemToDraw.y);

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
            if (_canEdit) _showEditTooltip(itemToDraw, itemToDraw.x + element_height, itemToDraw.y);
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

function civ(civName) {
    _currentCivName = civName;
    const era = (data.civs && data.civs[civName]) ? data.civs[civName].era : 'base';

    loadJson(_treeroot + '/' + civName.toUpperCase() + '.json', function (treeData) {
        const root = document.getElementById('root');
        if (root) document.getElementById('techtree').removeChild(root);

        const tree_height = Math.max(window.innerHeight - 80, 100);
        const row_height  = tree_height / 4;
        const element_height = row_height / 3;

        const connections = [];
        const index = {};
        for (const building of treeData.buildings) index[building.id] = building;
        for (const item of treeData.units_techs) {
            index[item.id] = item;
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
        .connection.is-highlight { stroke: #8b4000 !important; stroke-width: 2.5px !important; }
        .node.is-highlight .node__overlay { outline: 2px solid rgba(139,64,0,0.5); border-radius: 2px; }
        #helptext {
            background: rgba(245,225,170,0.97);
            border: 1px solid #8b6d35;
            border-radius: 6px;
            padding: 9px 12px;
            font-size: 12px;
            color: #2a1a05;
            pointer-events: none;
            box-shadow: 2px 3px 10px rgba(0,0,0,0.25);
            max-width: 200px;
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
    treeWrap.addEventListener('wheel', function (e) {
        if (e.deltaX !== 0) return;
        if (!e.shiftKey && treeEl.scrollHeight <= treeEl.clientHeight) {
            treeWrap.scrollLeft += e.deltaY > 0 ? 150 : -150;
        }
    });

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
    // Re-render with all items enabled: gather all node_ids from the current civ tree
    if (!_currentCivName) return;
    loadJson(_treeroot + '/' + _currentCivName.toUpperCase() + '.json', function (treeData) {
        _localtree = { units: [], buildings: [], techs: [] };
        for (const b of treeData.buildings) {
            _localtree.buildings.push(b.node_id);
        }
        for (const item of treeData.units_techs) {
            const key = _useTypeKey(item.use_type);
            if (key) _localtree[key].push(item.node_id);
        }
        civ(_currentCivName);
    });
}

function _disableAll() {
    _localtree = { units: [], buildings: [], techs: [] };
    if (_currentCivName) civ(_currentCivName);
}
