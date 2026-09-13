"""Dump every civ bonus's card text next to the actual effect commands its
catalog techs fire, so the mapping can be audited by eye.

    ./venv/bin/python scripts/dump_bonuses.py /tmp/bonus_audit.txt

Produced docs/AUDIT-bonus-catalog-mismaps.md.  Re-run after a game patch.
Takes ~20s, essentially all of it load_dat.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dat_reader import find_game_dat, load_dat
import bonus_names

ROOT = Path(__file__).resolve().parent.parent
GUIDE = Path("/Users/bryan/Sites/aoe2/AoE2DE_UGC_Guide-main/docs/general/xs/constants/constants.json")

raw = json.loads((ROOT / "bonus_catalog_raw.json").read_text())
cards = json.loads((ROOT / "static/data/bonus_cards.json").read_text())
names = json.loads((ROOT / "bonus_names.json").read_text())

const = json.loads(GUIDE.read_text())
ATTR = {e["value"]: e["name"][1:] for e in const["Object Attribute"]}
RES = {e["value"]: e["name"].replace("cAttribute", "") for e in const["resource"]}
CLS = {e["value"] - 900: e["name"][1:].replace("Class", "") for e in const["Object Class"]}

dat = load_dat(find_game_dat())
units = dat.civs[0].units
UNIT = {}
for i, u in enumerate(units):
    if u is not None:
        UNIT[i] = u.name.strip("\x00")

TECH = {i: (t.name.strip("\x00"), t.effect_id, t.civ) for i, t in enumerate(dat.techs)}


def eff_name(eid):
    if eid is None or eid < 0 or eid >= len(dat.effects):
        return "<none>"
    return dat.effects[eid].name.strip("\x00")


def unit(a, b=None):
    if a == -1:
        return f"ALL class {b}:{CLS.get(b, '?')}"
    return f"{a}:{UNIT.get(a, '?')}"


MODE = {0: "SET", 1: "ADD", -1: "DELTA", 2: "MULT"}


def fmt_ec(c):
    t, a, b, cc, d = c.type, c.a, c.b, c.c, c.d
    if t == 0:
        return f"SET       {unit(a, b)} attr {cc}:{ATTR.get(cc,'?')} = {d}"
    if t == 4:
        return f"ADD       {unit(a, b)} attr {cc}:{ATTR.get(cc,'?')} += {d}"
    if t == 5:
        return f"MULT      {unit(a, b)} attr {cc}:{ATTR.get(cc,'?')} *= {d}"
    if t == 1:
        m = {0: "set", 1: "add", -1: "trickle"}.get(b, b)
        return f"RESOURCE  {a}:{RES.get(a,'?')} {m} {d}"
    if t == 2:
        # b is tri-state: 1 = show, 0 = hide, -1 = leave visibility alone.
        vis = {1: "show", 0: "hide", -1: "b=-1 (no visibility change)"}.get(b, f"b={b}")
        return f"ENABLE    {unit(a)} {vis}"
    if t == 3:
        return f"UPGRADE   {unit(a)} -> {unit(b)}"
    if t == 101:
        return f"TECHCOST  tech {a}:{TECH.get(a,('?',))[0]} res {b}:{RES.get(b,'?')} {MODE.get(cc,cc)} {d}"
    if t == 103:
        return f"TECHTIME  tech {a}:{TECH.get(a,('?',))[0]} {MODE.get(cc,cc)} {d}"
    if t == 102:
        tid = int(d)
        return f"DISABLE   tech {tid}:{TECH.get(tid,('?',))[0]}"
    if t == 8:
        return f"UNLOCK    a={a} b={b} c={cc} d={d}"
    return f"TYPE{t:<5} a={a} b={b} c={cc} d={d}"


out = []
civ_map = raw["civ"]
ec_list = raw.get("ec_list", {})
hidden = set(bonus_names.DEPRECATED_BONUSES)

ids = sorted({int(k) for k in civ_map} | {int(k) for k in ec_list})
for bid in ids:
    techs = civ_map.get(str(bid), [])
    ecl = ec_list.get(str(bid), [])
    if not techs and not ecl:
        continue
    card = cards.get(str(bid), {})
    out.append("=" * 78)
    flag = " [DEPRECATED/HIDDEN]" if bid in hidden else ""
    out.append(f"BONUS {bid}{flag}")
    out.append(f"  name: {names.get(str(bid), '?')}")
    if card:
        bits = [card.get("heading"), card.get("stat"), card.get("description"),
                card.get("prog_label")]
        bits += card.get("lines") or []
        bits += [f"{a.get('age')}={a.get('value')}" for a in card.get("ages") or []]
        out.append("  card: " + " | ".join(str(b) for b in bits if b))
        out.append(f"  entity: {card.get('entity')} {card.get('entity2') or ''} type={card.get('type','value')}")
    else:
        out.append("  card: <NO CARD>")
    for tid in techs:
        nm, eid, civ = TECH.get(tid, ("<MISSING>", None, None))
        out.append(f"  tech {tid} '{nm}' civ={civ} effect {eid} '{eff_name(eid)}'")
        if eid is not None and 0 <= eid < len(dat.effects):
            cmds = dat.effects[eid].effect_commands
            for c in cmds[:40]:
                out.append("      " + fmt_ec(c))
            if len(cmds) > 40:
                out.append(f"      ... {len(cmds)-40} more commands")
    for entry in ecl:
        out.append(f"  ec_list requires={entry.get('requires')}")
        for e in entry.get("ecs", []):
            class C:
                pass
            c = C()
            c.type, c.a, c.b, c.c, c.d = e["type"], e["A"], e["B"], e["C"], e["D"]
            out.append("      " + fmt_ec(c))

Path(sys.argv[1]).write_text("\n".join(out))
print("bonuses dumped:", len(ids))
