"""
civ_overrides.py — Post-apply_civ DAT patches for civbuilder_v1 civ defs.

Extracted from wizard_build.py into a standalone module so both wizard_build
and build_all can import them without creating a circular dependency.

Two public functions:
  _override_ut_costs(dat, civ_result, draft)
  _apply_uu_overrides(dat, slot, uu_info, draft)

Both accept the wizard draft dict OR a civbuilder_v1-to_draft()-converted dict
since they share the same key schema.  KM-format civ_defs have none of these
keys so both functions are safe no-ops when called on them.
"""

from genieutils.effect import EffectCommand
from genieutils.tech import ResearchResourceCost
from genieutils.unit import AttackOrArmor


# ── UT cost / time override ───────────────────────────────────────────────────

def _override_ut_costs(dat, civ_result: dict, draft: dict) -> None:
    """
    After apply_civ creates Castle/Imperial UT techs, patch their costs and
    research time from the wizard draft (or civbuilder_v1 converted draft).
    """
    for draft_key, result_key in (
        ("castle_ut",  "castle_ut_tech_id"),
        ("imperial_ut","imp_ut_tech_id"),
    ):
        ut_data = draft.get(draft_key) or {}
        if not ut_data:
            continue
        tech_id = civ_result.get(result_key)
        if tech_id is None or tech_id >= len(dat.techs):
            continue

        tech = dat.techs[tech_id]

        time_val = ut_data.get("time")
        if time_val is not None:
            tech.research_time = max(0, int(time_val))

        cost = ut_data.get("cost") or {}
        slots: list[ResearchResourceCost] = []
        for res_name, res_type in (("food", 0), ("wood", 1), ("stone", 2), ("gold", 3)):
            amount = int(cost.get(res_name, 0))
            if amount > 0:
                slots.append(ResearchResourceCost(type=res_type, amount=amount, flag=1))
        while len(slots) < 3:
            slots.append(ResearchResourceCost(type=-1, amount=0, flag=0))
        tech.resource_costs = tuple(slots[:3])


# ── UU stat overrides + advanced flags ───────────────────────────────────────

def _apply_uu_overrides(dat, slot: int, uu_info: dict | None, draft: dict) -> None:
    """
    Apply wizard stat overrides and advanced flags to UU unit objects in the DAT.
    Called after apply_civ so the base unit data is already in place.
    """
    if uu_info is None:
        return
    uu        = draft.get("unique_unit") or {}
    overrides = uu.get("overrides")      or {}
    flags     = uu.get("advanced_flags") or {}
    if not overrides and not flags:
        return

    base_id  = uu_info.get("unit_id")
    elite_id = uu_info.get("elite_id")

    def _unit(uid):
        if uid is None:
            return None
        try:
            return dat.civs[slot].units[uid]
        except (IndexError, KeyError, TypeError):
            return None

    base_unit  = _unit(base_id)
    elite_unit = _unit(elite_id) if elite_id != base_id else None

    tiers = [(base_unit, "_base"), (elite_unit, "_elite")]

    # ── Stat overrides ──────────────────────────────────────────────────────

    for u, sfx in tiers:
        if u is None:
            continue

        if overrides.get(f"hp{sfx}") is not None:
            u.hit_points = int(overrides[f"hp{sfx}"])

        if overrides.get(f"speed{sfx}") is not None:
            u.speed = float(overrides[f"speed{sfx}"])

        if u.type_50 is not None:
            if overrides.get(f"range{sfx}") is not None:
                u.type_50.max_range = float(overrides[f"range{sfx}"])

            if overrides.get(f"reload{sfx}") is not None:
                u.type_50.displayed_reload_time = float(overrides[f"reload{sfx}"])

            if overrides.get(f"attack{sfx}") is not None:
                v = int(overrides[f"attack{sfx}"])
                u.type_50.displayed_attack = v
                cls4 = next((a for a in u.type_50.attacks if a.class_ == 4), None)
                cls3 = next((a for a in u.type_50.attacks if a.class_ == 3), None)
                dominant = (
                    cls4 if (cls4 and (not cls3 or cls4.amount >= cls3.amount)) else cls3
                )
                if dominant:
                    dominant.amount = v
                elif u.type_50.attacks:
                    u.type_50.attacks[0].amount = v

            if overrides.get(f"melee{sfx}") is not None:
                v = int(overrides[f"melee{sfx}"])
                for a in u.type_50.armours:
                    if a.class_ == 4:
                        a.amount = v
                        break
                u.type_50.displayed_melee_armour = v

            if overrides.get(f"pierce{sfx}") is not None:
                v = int(overrides[f"pierce{sfx}"])
                for a in u.type_50.armours:
                    if a.class_ == 3:
                        a.amount = v
                        break
                if u.creatable:
                    u.creatable.displayed_pierce_armour = v

        if overrides.get(f"train{sfx}") is not None and u.creatable:
            if u.creatable.train_locations:
                u.creatable.train_locations[0].train_time = int(overrides[f"train{sfx}"])

    # Training cost overrides (shared — applies to both tiers)
    _RES = {"food": 0, "wood": 1, "stone": 2, "gold": 3}
    cost_overrides = {
        _RES[r]: int(overrides[f"cost_{r}"])
        for r in _RES if f"cost_{r}" in overrides
    }
    if cost_overrides:
        for u, _ in tiers:
            if u is None or not u.creatable:
                continue
            rc = u.creatable.resource_costs
            covered = {s.type: i for i, s in enumerate(rc) if s.type != -1}
            empty   = [i for i, s in enumerate(rc) if s.type == -1]
            for res_type, amount in cost_overrides.items():
                if res_type in covered:
                    i = covered[res_type]
                    rc[i].amount = amount
                    rc[i].flag = 1 if amount > 0 else 0
                elif amount > 0 and empty:
                    i = empty.pop(0)
                    rc[i].type   = res_type
                    rc[i].amount = amount
                    rc[i].flag   = 1

    # ── Advanced flags ──────────────────────────────────────────────────────

    if flags.get("no_convert"):
        for u, _ in tiers:
            if u and u.creatable:
                u.creatable.min_conversion_time_mod = 32767.0
                u.creatable.max_conversion_time_mod = 32767.0

    if flags.get("trample"):
        for u, _ in tiers:
            if u and u.type_50:
                u.type_50.blast_attack_level = 2
                if not u.type_50.blast_width:
                    u.type_50.blast_width = 0.5

    # Runs after attack override so displayed_attack reflects the user's value.
    if flags.get("ignore_armor"):
        for u, _ in tiers:
            if u and u.type_50:
                disp = u.type_50.displayed_attack or 0
                new_attacks = [a for a in u.type_50.attacks if a.class_ not in (3, 4)]
                new_attacks.insert(0, AttackOrArmor(class_=50, amount=int(disp)))
                u.type_50.attacks = new_attacks

    if flags.get("bonus_dmg_resist") is not None:
        pct = float(flags["bonus_dmg_resist"])
        resistance = max(0.0, min(1.0, 1.0 - pct / 100.0))
        for u, _ in tiers:
            if u and u.type_50:
                u.type_50.bonus_damage_resistance = resistance

    if flags.get("charge_pool") is not None:
        pool = float(flags["charge_pool"])
        rate = float(flags.get("charge_rate") or 0.25)
        for u, _ in tiers:
            if u and u.creatable:
                u.creatable.max_charge    = pool
                u.creatable.recharge_rate = rate
                u.creatable.charge_event  = 1
                u.creatable.charge_type   = 2

    if flags.get("regen_hp"):
        regen_amount   = float(flags.get("regen_amount")   or 1)
        regen_interval = float(flags.get("regen_interval") or 5)
        regen_per_min  = (regen_amount / regen_interval) * 60.0
        tt_eff = dat.effects[dat.civs[slot].tech_tree_id]
        for uid in [base_id, elite_id]:
            if uid is not None:
                tt_eff.effect_commands.append(
                    EffectCommand(type=0, a=uid, b=-1, c=109, d=regen_per_min)
                )


# ── Hero unit ─────────────────────────────────────────────────────────────────

_HERO_HP_FLOOR    = 300
_HERO_TRAIN_TIME  = 60
_HERO_COST_FOOD   = 500
_HERO_COST_GOLD   = 500

def _apply_hero_unit(dat, slot: int, draft: dict) -> None:
    """
    Enable and configure a hero unit for the civ.

    Standard defaults applied to every hero (matching Three Kingdoms hero standard):
      - Castle btn 2, 60 s train time
      - 500 Food / 500 Gold cost
      - 300 HP floor
      - hero_mode 1|2 (one-at-a-time + cannot convert); basic regen is engine-automatic
    Enhanced regen (draft flags.regen_hp): adds EC_SET attr 109 = 60 HP/min explicitly.
    User stat overrides are applied last and always win.
    """
    hero    = draft.get("hero_unit") or {}
    base_id = hero.get("base_unit_id")
    if base_id is None:
        return

    if base_id >= len(dat.civs[slot].units):
        return
    unit = dat.civs[slot].units[base_id]
    if unit is None:
        return

    # EC_ENABLE — make the unit visible/trainable
    tt_eff = dat.effects[dat.civs[slot].tech_tree_id]
    tt_eff.effect_commands.append(EffectCommand(type=2, a=base_id, b=1, c=-1, d=0.0))

    if unit.creatable:
        # ── Train location: always Castle btn 2 ──────────────────────────────
        if unit.creatable.train_locations:
            loc = unit.creatable.train_locations[0]
            loc.building_id = 82
            loc.button_id   = 2
            loc.train_time  = _HERO_TRAIN_TIME

        # ── Cost: 500 Food / 500 Gold ─────────────────────────────────────────
        rc = unit.creatable.resource_costs
        for rc_slot in rc:
            rc_slot.type   = -1
            rc_slot.amount = 0
            rc_slot.flag   = 0
        if len(rc) >= 1:
            rc[0].type = 0; rc[0].amount = _HERO_COST_FOOD; rc[0].flag = 1
        if len(rc) >= 2:
            rc[1].type = 3; rc[1].amount = _HERO_COST_GOLD; rc[1].flag = 1

        # ── hero_mode ─────────────────────────────────────────────────────────
        unit.creatable.hero_mode      = 1 | 2   # one-at-a-time + cannot convert
        unit.creatable.creatable_type = 1

    # ── HP floor ──────────────────────────────────────────────────────────────
    if unit.hit_points < _HERO_HP_FLOOR:
        unit.hit_points = _HERO_HP_FLOOR

    # ── Enhanced regen (optional) ─────────────────────────────────────────────
    flags = hero.get("flags") or {}
    if flags.get("regen_hp"):
        # 60 HP/min = 1 HP/sec, visibly stronger than the automatic hero regen
        tt_eff.effect_commands.append(
            EffectCommand(type=0, a=base_id, b=-1, c=109, d=60.0)
        )

    # ── Stat overrides (applied last — always win over defaults) ──────────────
    overrides = hero.get("overrides") or {}
    if overrides.get("hp") is not None:
        unit.hit_points = int(overrides["hp"])
    if overrides.get("speed") is not None:
        unit.speed = float(overrides["speed"])
    if unit.type_50 is not None:
        if overrides.get("attack") is not None:
            v = int(overrides["attack"])
            unit.type_50.displayed_attack = v
            cls4 = next((a for a in unit.type_50.attacks if a.class_ == 4), None)
            cls3 = next((a for a in unit.type_50.attacks if a.class_ == 3), None)
            dominant = cls4 if (cls4 and (not cls3 or cls4.amount >= cls3.amount)) else cls3
            if dominant:
                dominant.amount = v
        if overrides.get("melee_armor") is not None:
            v = int(overrides["melee_armor"])
            unit.type_50.displayed_melee_armour = v
            for a in unit.type_50.armours:
                if a.class_ == 4:
                    a.amount = v
                    break
        if overrides.get("pierce_armor") is not None:
            v = int(overrides["pierce_armor"])
            if unit.creatable:
                unit.creatable.displayed_pierce_armour = v
            for a in unit.type_50.armours:
                if a.class_ == 3:
                    a.amount = v
                    break
    if overrides.get("train_time") is not None and unit.creatable:
        if unit.creatable.train_locations:
            unit.creatable.train_locations[0].train_time = int(overrides["train_time"])
