"""Fully-upgraded unit stats for one civ, read from a DAT.

Simulates a post-Imperial start: every tech the civ can reach is researched, and
its effect's set/add/multiply commands are applied to the civ's own unit
definitions, recording which tech changed which stat.  Reads the DAT the build
wrote, never the card text, so what it shows is what the mod does.

    venv/bin/python fu_stats.py <civ index> <unit id> [<unit id> ...]

Not modelled: XS-driven techs (resource 33), resource-based effects (trickles,
productivity), auras, and allies' team bonuses (only the civ's own applies).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from copy import deepcopy

SET, ADD, MUL, ENABLE, UPGRADE, MODTECH, DISABLE, TECH_COST = 0, 4, 5, 2, 3, 8, 102, 101
# Team variants of set/enable/upgrade/add/multiply; a team bonus also reaches its owner.
_TEAM = {10: SET, 12: ENABLE, 13: UPGRADE, 14: ADD, 15: MUL}
_CIVILIAN = 4      # unit class of the Villager and its task forms (Builder 118, ...)
_OPT_IN = 12        # type=8 b=12 is the make-avail unlock; other b's edit cost etc.

ATTR_NAMES = {0: "HP", 1: "Line of sight", 5: "Speed", 8: "Armor", 9: "Attack",
              10: "Reload time", 11: "Accuracy", 12: "Range", 13: "Work rate",
              42: "Train location",
              23: "Search radius", 101: "Train time", 102: "Projectiles",
              103: "Food cost", 104: "Wood cost", 105: "Gold cost", 106: "Stone cost",
              107: "Max projectiles"}
_COST_ATTRS = {103: 0, 104: 1, 105: 3, 106: 2}     # attribute -> resource id


def reachable_techs(dat, civ_index: int) -> list[int]:
    """Tech ids a post-Imperial start researches for this civ, in firing order.

    Auto-fire techs settle before anything that must be researched: "Imperial
    Skirmisher (disable)" fires the instant Elite Skirmisher completes, before
    the Imperial Skirmisher could start.  A building's own tech (the age
    "Shadow Node"s) counts as fired — post-Imperial has every building."""
    civ = dat.civs[civ_index]
    # The tech tree and the civ's own team bonus both act at game start: the
    # Vietnamese team bonus is a type=102 of "Imperial Skirmisher (disable)".
    start = list(dat.effects[civ.tech_tree_id].effect_commands)
    if civ.team_bonus_id >= 0:
        start += dat.effects[civ.team_bonus_id].effect_commands
    modtech = (MODTECH, MODTECH + 10)      # 18 is the team variant (Incas TT)
    opted_in = {int(c.a) for c in start if c.type in modtech and int(c.b) == _OPT_IN}
    opt_in = {int(c.a) for e in dat.effects for c in e.effect_commands
              if c.type in modtech and int(c.b) == _OPT_IN}
    disabled = {int(c.d) for c in start if c.type == DISABLE} - opted_in
    building_techs = {u.building.tech_id for u in civ.units
                      if u is not None and u.building is not None and u.building.tech_id > 0}
    autofire = {tid for tid, t in enumerate(dat.techs)
                if all(r.location_id == -1 for r in t.research_locations)}
    # An auto-fire tech with a cost can never be paid: the older disable gate.
    # Setting that cost to zero (EC_TECH_COST, set mode) lifts it — how the
    # pre-Viking-Sagas Berber/Italian team bonuses unlocked the Genitour and
    # Condottiero.
    cost_gated = {tid for tid in autofire
                  if any(r.type >= 0 and r.amount > 0 for r in dat.techs[tid].resource_costs)}

    def ungate(cmds) -> None:
        cost_gated.difference_update(int(c.a) for c in cmds
                                     if c.type == TECH_COST and int(c.c) == 0 and c.d == 0)

    ungate(start)

    done: set[int] = set()
    order: list[int] = []

    def eligible(tid: int) -> bool:
        t = dat.techs[tid]
        if tid in done or tid in disabled or t.civ not in (-1, civ_index):
            return False
        if tid in opt_in and t.civ == -1 and tid not in opted_in:
            return False
        if tid in building_techs:
            return True
        reqs = [r for r in t.required_techs if r >= 0]
        return sum(r in done for r in reqs) >= t.required_tech_count

    def fire(tid: int) -> None:
        done.add(tid)
        order.append(tid)
        eid = dat.techs[tid].effect_id
        # A fired tech can disable others (tech 79).  The a=1104 b=1 on
        # "Imperial Skirmisher (disable)" is junk copied from the Demo Ship
        # commands; it disables like any other.
        # A type=102 never undoes a type=8 (CLAUDE.md quirk 10, confirmed
        # in-game): "[FTT] Adjust Regionals Positions" (121) disables the
        # Genitour and Condottiero, which the Berbers and Italians opted into.
        if eid >= 0:
            disabled.update(int(c.d) for c in dat.effects[eid].effect_commands
                            if c.type == DISABLE and int(c.d) not in opted_in)
            ungate(dat.effects[eid].effect_commands)

    while True:
        settled = False
        while not settled:
            settled = True
            for tid in sorted(autofire - cost_gated):
                if eligible(tid):
                    fire(tid)
                    settled = False
        batch = [tid for tid in range(len(dat.techs)) if tid not in autofire and eligible(tid)]
        if not batch:
            return order
        for tid in batch:
            if tid not in disabled:
                fire(tid)


def _targets(units, ec):
    a, b = int(ec.a), int(ec.b)
    # Unit -1 and class -1 together is NOT "every unit": Chemistry's lone
    # +1 melee command of that shape would otherwise reach the Champion, and
    # Chemistry lists the Mangonel line's +1 melee separately anyway.
    if a == -1 and b == -1:
        return
    for u in units:
        if u is None or (a != -1 and u.id != a) or (b != -1 and u.class_ != b):
            continue
        yield u


def _combine(typ: int, old, d):
    return d if typ == SET else old + d if typ == ADD else old * d


def _apply(u, typ: int, attr: int, d: float, slot: int = 0) -> dict | None:
    """Apply one command to unit u.  Returns {old, new} (plus cls for attack and
    armour), {"unmodelled": True} for an attribute this doesn't track, or None
    when the unit is untouched."""
    t50, cr = u.type_50, u.creatable
    if attr in (8, 9):
        if t50 is None:
            return None
        packed = abs(int(d))
        cls, val = packed >> 8, packed & 0xFF
        lst = t50.armours if attr == 8 else t50.attacks
        for i, ao in enumerate(lst):
            if ao.class_ == cls:
                old = ao.amount
                new = (val if typ == SET else old + (val if d >= 0 else -val) if typ == ADD
                       else round(old * val / 100))
                lst[i] = type(ao)(class_=cls, amount=new)
                return {"cls": cls, "old": old, "new": new}
        return None     # the unit has no entry for that class: no effect
    fields = {0: (u, "hit_points"), 1: (u, "line_of_sight"), 5: (u, "speed")}
    if t50 is not None:
        fields.update({10: (t50, "reload_time"), 11: (t50, "accuracy_percent"),
                       12: (t50, "max_range")})
    if u.bird is not None:
        fields.update({13: (u.bird, "work_rate"), 23: (u.bird, "search_radius")})
    if cr is not None:
        fields.update({102: (cr, "total_projectiles"), 107: (cr, "max_total_projectiles")})
    if attr in fields:
        obj, name = fields[attr]
        old = getattr(obj, name)
        setattr(obj, name, type(old)(_combine(typ, old, d)))
        return {"old": old, "new": getattr(obj, name)}
    if attr == 42 and cr is not None and typ == SET and slot < len(cr.train_locations):
        # Anarchy / Marauders: writes the train location `slot` names (attr 158).
        old = cr.train_locations[slot].unit_id
        cr.train_locations[slot].unit_id = int(d)
        return {"old": old, "new": int(d)}
    if attr == 101 and cr is not None and cr.train_locations:
        olds = []
        for tl in cr.train_locations:     # one train_time per location (quirk 14)
            olds.append(tl.train_time)
            tl.train_time = int(_combine(typ, tl.train_time, d))
        return {"old": olds[0], "new": cr.train_locations[0].train_time}
    if attr in _COST_ATTRS and cr is not None:
        res = _COST_ATTRS[attr]
        costs = list(cr.resource_costs)
        for i, rc in enumerate(costs):
            if rc.type == res and rc.flag == 1:
                new = int(_combine(typ, rc.amount, d))
                costs[i] = type(rc)(type=rc.type, amount=new, flag=rc.flag)
                cr.resource_costs = tuple(costs)
                return {"old": rc.amount, "new": new}
        # A resource with no slot of its own is lost: the engine never retypes
        # a slot (a Knight set from food + gold to wood + stone came out free,
        # in game 2026-10-26).  Hussite Reforms works because the Monk ships a
        # 0-food slot; the build readies slots the same way (cost_slots).
        return None
    return {"unmodelled": True}


def _describe(c: dict) -> str:
    if c.get("unmodelled"):
        return f"d={c['d']:g} (not modelled)"
    head = f"class {c['cls']}: " if "cls" in c else ""
    return f"{head}{c['old']:g} -> {c['new']:g}"


class Simulation:
    """A civ after a post-Imperial start: its unit definitions, the change log
    per unit, and the upgrade map (from -> to)."""

    def __init__(self, dat, civ_index: int):
        self.dat, self.civ_index = dat, civ_index
        self.units = deepcopy(dat.civs[civ_index].units)
        self.log: dict[int, list[dict]] = defaultdict(list)
        self.upgrades: dict[int, int] = {}
        self._train_slot: dict[int, int] = {}
        # Units the civ starts with, then whatever its techs enable (type=2).
        self.enabled = {u.id for u in self.units if u is not None and u.enabled}
        self.techs = reachable_techs(dat, civ_index)
        civ = dat.civs[civ_index]
        # The tech tree acts at game start too: besides its disables and
        # unlocks it hides units (type=2 b=0), e.g. the Militia for the Incas.
        if civ.tech_tree_id >= 0:
            self._run(civ.tech_tree_id, "Tech tree", None)
        if civ.team_bonus_id >= 0:
            self._run(civ.team_bonus_id, "Team bonus", None)
        for tid in self.techs:
            eid = dat.techs[tid].effect_id
            if eid >= 0:
                self._run(eid, dat.techs[tid].name, tid)

    def _run(self, effect_id: int, source: str, tech_id: int | None) -> None:
        for ec in self.dat.effects[effect_id].effect_commands:
            typ = _TEAM.get(ec.type, ec.type)
            if typ == UPGRADE:
                self.upgrades[int(ec.a)] = int(ec.b)
            elif typ == ENABLE:
                # b=0 hides; 1 shows, and so does -1 (Flaming Camel make-avail).
                (self.enabled.discard if int(ec.b) == 0 else self.enabled.add)(int(ec.a))
            elif typ in (SET, ADD, MUL):
                attr = int(ec.c)
                if attr == 158:
                    # Which train location a following attr 42 writes.  Inferred
                    # from Anarchy: 158=1, 42=Barracks, 158=0 fills the Huskarl's
                    # empty second slot, so the Castle keeps training it.
                    if typ == SET:
                        for u in _targets(self.units, ec):
                            self._train_slot[u.id] = int(ec.d)
                    continue
                if attr == 127:
                    # Hero "limited" flag (2 never retrainable, 4 retrainable;
                    # quirk 7): how Liu Bei and our own heroes are made available,
                    # with no type=2 at all.
                    if typ in (SET, ADD) and int(ec.d) in (2, 4):
                        self.enabled.update(u.id for u in _targets(self.units, ec))
                    continue
                for u in _targets(self.units, ec):
                    change = _apply(u, typ, attr, ec.d, self._train_slot.get(u.id, 0))
                    if change:
                        change.update(
                            source=source, tech=tech_id, attr=attr, d=ec.d,
                            stat=ATTR_NAMES.get(attr, f"attribute {attr}"),
                            op={SET: "set", ADD: "add", MUL: "multiply"}[typ])
                        change["change"] = _describe(change)
                        self.log[u.id].append(change)

    def available_lines(self) -> list[int]:
        """One base unit per line the civ can train or build, post-Imperial.

        Read from the simulated DAT, never the draft's tree list: that carries
        ids the editor doesn't show (every UU, the Condottiero, ...), so
        presence there is no choice.  A unit counts when it is enabled (from
        the start or by a reached tech) and has somewhere to be made; its line
        is shown once, as the unit it ends up as."""
        lines: dict[int, int] = {}
        for uid in sorted(self.enabled):
            u = self.units[uid] if 0 <= uid < len(self.units) else None
            if u is None or u.creatable is None or u.type_50 is None:
                continue
            # ...somewhere the civ has: the Merchant Ship is enabled for
            # everyone but trains at a Port no regular civ builds.
            if not any(self._has_maker(tl.unit_id) for tl in u.creatable.train_locations):
                continue
            lines.setdefault(self.final_unit(uid), uid)
        return list(lines.values())

    def _has_maker(self, uid: int) -> bool:
        """Can the civ have a uid to train things at?  It is enabled; or it is
        a villager form (class 4 — buildings are made by the Builder, 118,
        which is never enabled itself); or it is never made at all (the
        starting Town Center 109).  A Port is buildable but never enabled."""
        if uid in self.enabled:
            return True
        m = self.units[uid] if 0 <= uid < len(self.units) else None
        if m is None:
            return False
        return m.class_ == _CIVILIAN or m.creatable is None or not any(
            t.unit_id >= 0 for t in m.creatable.train_locations)

    def final_unit(self, unit_id: int) -> int:
        seen = set()
        while unit_id in self.upgrades and unit_id not in seen:
            seen.add(unit_id)
            unit_id = self.upgrades[unit_id]
        return unit_id

    def work_rate(self, unit_id: int) -> float:
        u = self.units[unit_id] if 0 <= unit_id < len(self.units) else None
        return (u.bird.work_rate if u is not None and u.bird is not None else 0) or 1.0

    def stats(self, base_unit_id: int) -> dict:
        """The fully-upgraded unit a base unit becomes, with its stats and the
        changes that produced them."""
        uid = self.final_unit(base_unit_id)
        u = self.units[uid]
        t50, cr = u.type_50, u.creatable
        out = {"base_unit": base_unit_id, "unit": uid, "class": u.class_,
               "hp": u.hit_points, "los": u.line_of_sight, "speed": u.speed,
               "changes": list(self.log[uid])}
        if t50 is not None:
            out.update(attack={a.class_: a.amount for a in t50.attacks},
                       armor={a.class_: a.amount for a in t50.armours},
                       reload=t50.reload_time, range=t50.max_range,
                       accuracy=t50.accuracy_percent)
        if cr is not None:
            out["cost"] = {c.type: c.amount for c in cr.resource_costs
                           if c.flag == 1 and c.type in (0, 1, 2, 3)}
            out["train"] = [{"building": tl.unit_id, "time": tl.train_time,
                             "work_rate": self.work_rate(tl.unit_id),
                             "effective": tl.train_time / self.work_rate(tl.unit_id),
                             "changes": [c for c in self.log[tl.unit_id] if c["attr"] == 13]}
                            for tl in cr.train_locations if tl.unit_id >= 0]
        return out


# ── The review panel's view ───────────────────────────────────────────────────

MELEE, PIERCE = 4, 3
_STAT_KEYS = {0: "hp", 1: "los", 5: "speed", 10: "reload", 11: "accuracy", 12: "range",
              101: "train_time", 102: "projectiles", 107: "projectiles", 42: "train_location",
              103: "cost", 104: "cost", 105: "cost", 106: "cost"}
_STAT_ORDER = [("hp", "Hit points"), ("attack", "Attack"), ("melee_armor", "Melee armor"),
               ("pierce_armor", "Pierce armor"), ("range", "Range"), ("reload", "Reload time"),
               ("accuracy", "Accuracy"), ("speed", "Speed"), ("los", "Line of sight")]


def _main_attack_class(u) -> int | None:
    """Melee or pierce, whichever the unit's attack is (the bigger one)."""
    if u.type_50 is None:
        return None
    amounts = {a.class_: a.amount for a in u.type_50.attacks}
    if MELEE not in amounts and PIERCE not in amounts:
        return None
    return PIERCE if amounts.get(PIERCE, -1) > amounts.get(MELEE, -1) else MELEE


def _stat_key(c: dict, main_cls: int | None) -> str:
    if c["attr"] == 9:
        return "attack" if c["cls"] == main_cls else f"bonus:{c['cls']}"
    if c["attr"] == 8:
        return {MELEE: "melee_armor", PIERCE: "pierce_armor"}.get(c["cls"], f"armor:{c['cls']}")
    return _STAT_KEYS.get(c["attr"], "other")


def _stat_values(u, main_cls) -> dict:
    t50 = u.type_50
    out = {"hp": u.hit_points, "los": u.line_of_sight, "speed": u.speed}
    if t50 is not None:
        atk = {a.class_: a.amount for a in t50.attacks}
        arm = {a.class_: a.amount for a in t50.armours}
        out.update(melee_armor=arm.get(MELEE), pierce_armor=arm.get(PIERCE),
                   range=t50.max_range, reload=t50.reload_time, accuracy=t50.accuracy_percent)
        if main_cls is not None:
            out["attack"] = atk.get(main_cls)
    return out


def _step(c: dict, name) -> dict:
    return {"source": name(c), "tech": c["tech"], "op": c["op"],
            "old": c.get("old"), "new": c.get("new"),
            "amount": (c["new"] - c["old"]) if c["op"] == "add" and "old" in c else
                      (c["d"] if c["op"] == "multiply" else c.get("new"))}


def card(sim: Simulation, base_unit_id: int, name) -> dict:
    """One unit line's stat card: each stat's base value, final value and the
    steps between them.  `name(change)` turns a change into its source's label.
    A stat built from both adds and multiplies is flagged "mixed": its value
    depends on the order the engine applies them, which is unconfirmed."""
    uid = sim.final_unit(base_unit_id)
    u, base = sim.units[uid], sim.dat.civs[sim.civ_index].units[uid]
    main_cls = _main_attack_class(u)
    before, after = _stat_values(base, main_cls), _stat_values(u, main_cls)
    steps: dict[str, list] = defaultdict(list)
    for c in sim.log[uid]:
        steps[_stat_key(c, main_cls)].append(c)

    stats = []
    for key, label in _STAT_ORDER:
        if after.get(key) is None or (key in ("range", "accuracy") and not after[key]):
            continue
        if key == "accuracy" and after[key] == 100 and not steps[key]:
            continue
        ops = {c["op"] for c in steps[key]}
        stats.append({"key": key, "label": label, "value": after[key], "base": before.get(key),
                      "steps": [_step(c, name) for c in steps[key]],
                      "mixed": {"add", "multiply"} <= ops})
        if key == "attack":
            stats[-1]["kind"] = "pierce" if main_cls == PIERCE else "melee"

    bonus = []
    if u.type_50 is not None:
        base_atk = {a.class_: a.amount for a in base.type_50.attacks}
        for a in u.type_50.attacks:
            if a.class_ in (MELEE, PIERCE) or a.amount <= 0:
                continue
            bonus.append({"cls": a.class_, "value": a.amount, "base": base_atk.get(a.class_, 0),
                          "steps": [_step(c, name) for c in steps[f"bonus:{a.class_}"]]})

    out = {"unit": uid, "base_unit": base_unit_id, "class": u.class_, "stats": stats,
           "bonus": bonus, "sources": sorted({c["tech"] for c in sim.log[uid]
                                              if c["tech"] is not None}),
           "team_bonus": any(c["tech"] is None for c in sim.log[uid]),
           "other": [_step(c, name) | {"stat": c["stat"]} for k, cs in steps.items()
                     if k in ("other", "cost", "train_time", "projectiles")
                     or k.startswith("armor:") for c in cs]}
    cr = u.creatable
    if cr is not None:
        out["cost"] = {r: a for r, a in ((c.type, c.amount) for c in cr.resource_costs
                                         if c.flag == 1) if r in (0, 1, 2, 3) and a > 0}
        out["train"] = [{"building": tl.unit_id, "time": tl.train_time,
                         "work_rate": sim.work_rate(tl.unit_id),
                         "effective": round(tl.train_time / sim.work_rate(tl.unit_id), 1),
                         "steps": [_step(c, name) for c in sim.log[tl.unit_id] if c["attr"] == 13]}
                        for tl in cr.train_locations if tl.unit_id >= 0]
    return out


def _print(dat, civ_index: int, s: dict) -> None:
    from civ_appender import unit_label
    print(f"\n=== {dat.civs[civ_index].name}: {unit_label(dat, civ_index, s['base_unit'])}"
          f" -> {unit_label(dat, civ_index, s['unit'])} (class {s['class']}) ===")
    print(f"HP {s['hp']}  LOS {s['los']:g}  Speed {s['speed']:.3g}")
    if "attack" in s:
        print(f"Attack {s['attack']}\nArmor  {s['armor']}")
        print(f"Reload {s['reload']:g}  Range {s['range']:g}  Accuracy {s['accuracy']}")
    if "cost" in s:
        print(f"Cost {s['cost']}")
        for t in s["train"]:
            print(f"Train at {unit_label(dat, civ_index, t['building'])}: {t['time']}s"
                  f" / work rate {t['work_rate']:g} = {t['effective']:.1f}s")
            for c in t["changes"]:
                print(f"    {c['source']:36s} {c['op']:8s} {c['change']}")
    print("-- changes --")
    for c in s["changes"]:
        print(f"  {c['source']:38s} {c['stat']:14s} {c['op']:8s} {c['change']}")


if __name__ == "__main__":
    from dat_reader import find_game_dat, load_dat
    dat = load_dat(find_game_dat())
    civ_index = int(sys.argv[1])
    sim = Simulation(dat, civ_index)
    for uid in map(int, sys.argv[2:]):
        _print(dat, civ_index, sim.stats(uid))
