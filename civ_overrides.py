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

from genieutils.effect import Effect, EffectCommand
from genieutils.tech import ResearchLocation, ResearchResourceCost, Tech
from genieutils.unit import AttackOrArmor

from civ_appender import HERO_POOL_OFFSET, _campaign_sid


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

_CASTLE_BUILDING     = 82
_KREPOST_BUILDING    = 1251
_CASTLE_BTN1_HOTKEY  = 16101   # Q key, Castle/Krepost button 1


def _apply_uu_overrides(dat, slot: int, uu_info: dict | None, draft: dict) -> None:
    """
    Apply wizard stat overrides and advanced flags to UU unit objects in the DAT.
    Called after apply_civ so the base unit data is already in place.

    Always forces vanilla UUs to Castle btn1 so they don't conflict with the
    existing militia/other unit lines at their native Barracks/Stable/etc. buttons.
    KM-custom UUs are already placed at Castle by append_km_custom_uu, so the
    train_location guard is a no-op for them.
    """
    if uu_info is None:
        return
    uu        = draft.get("unique_unit") or {}
    overrides = uu.get("overrides")      or {}
    flags     = uu.get("advanced_flags") or {}

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

    # Force any vanilla UU that naturally trains outside the Castle to Castle btn1.
    # This prevents button conflicts (e.g. militia line at Barracks btn1).
    for u in (base_unit, elite_unit):
        if u is None or not u.creatable or not u.creatable.train_locations:
            continue
        tl = u.creatable.train_locations[0]
        if tl.unit_id not in (_CASTLE_BUILDING, _KREPOST_BUILDING):
            tl.unit_id    = _CASTLE_BUILDING
            tl.button_id  = 1
            tl.hot_key_id = _CASTLE_BTN1_HOTKEY

    if not overrides and not flags:
        return

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

    Standard defaults applied to every hero (matching Liu Bei / Three Kingdoms hero):
      - Castle btn 2 (W key, hotkey 16381), 60 s train time
      - 500 Food / 500 Gold cost
      - 300 HP floor
      - hero_mode 1 (one-at-a-time + passive regen, Liu Bei pattern)
      - language_dll_creation / language_dll_help set explicitly on the unit
    Enhanced regen (draft flags.regen_hp): adds EC_SET attr 109 = 60 HP/min explicitly.
    User stat overrides are applied last and always win.
    """
    hero    = draft.get("hero_unit") or {}
    base_id = hero.get("base_unit_id")
    print(f"       Hero unit: hero_unit key present={bool(draft.get('hero_unit'))} base_unit_id={base_id!r}")
    if base_id is None:
        return

    unit_count = len(dat.civs[slot].units)
    if base_id >= unit_count:
        print(f"       Hero unit: base_unit_id={base_id} out of range (civ has {unit_count} units) — skipping")
        return
    unit = dat.civs[slot].units[base_id]
    if unit is None:
        print(f"       Hero unit: unit slot {base_id} is None — skipping")
        return

    print(f"       Hero unit: applying base_unit_id={base_id} ({getattr(unit, 'name', '?')!r})"
          f"  creatable={'yes' if unit.creatable else 'NO — will be invisible'}")

    tt_eff = dat.effects[dat.civs[slot].tech_tree_id]

    # Hide hero from tech tree panel in Castle Age.  The auto-fire imp_tech below
    # fires EC_ENABLE b=1 when Imperial Age is reached, showing it there and in the
    # Castle training panel.  Note: hero is NOT in tree[0], so no vanilla type=8
    # for it lands in the TT — the hero is not trainable until imp_tech fires.
    tt_eff.effect_commands.append(EffectCommand(type=2, a=base_id, b=0, c=-1, d=0.0))

    # Gate hero to Imperial Age (tech 103).  full_tech_mode=1 + repeatable=1 makes
    # this fire automatically (like km_custom_uu._make_avail_tech) without needing a
    # type=8 in the TT.  EC_ENABLE b=1 both shows the hero in the tech tree panel
    # and makes it appear in the Castle training panel.
    zero_costs = (
        ResearchResourceCost(type=-1, amount=0, flag=0),
        ResearchResourceCost(type=-1, amount=0, flag=0),
        ResearchResourceCost(type=-1, amount=0, flag=0),
    )
    # One-at-a-time enforcement (attributes 126 / 127).  This — NOT creatable.hero_mode —
    # is what caps a hero at a single live instance.  Vanilla effect 1066 "Liu Bei
    # (make avail)" consists of exactly these two commands and nothing else:
    #   attr 126 "Available Unit Flag"  = number of trainable units (1)
    #   attr 127 "Disabled Unit Flag"   = 1 disabled
    #                                     2 limited, CANNOT be retrained after death
    #                                     4 limited, CAN be retrained after death
    # Attribute 126 is only honoured once flag 2 or 4 is present on 127, so both
    # commands are required.  EC_ADD on 127 mirrors vanilla; unit.disabled is forced
    # to 0 below so the add lands on a clean base.
    imp_eff = Effect(
        name=f"__hero_imp_enable_{slot}",
        effect_commands=[
            EffectCommand(type=2, a=base_id, b=1,  c=-1,  d=0.0),    # EC_ENABLE — show in Castle panel
            EffectCommand(type=0, a=base_id, b=-1, c=126, d=1.0),    # EC_SET  — 1 trainable at a time
            EffectCommand(type=4, a=base_id, b=-1, c=127, d=4.0),    # EC_ADD  — limited, retrainable on death
        ],
    )
    new_eff_id = len(dat.effects)
    dat.effects.append(imp_eff)

    imp_tech = Tech(
        required_techs=(103, -1, -1, -1, -1, -1),   # 103 = Imperial Age
        resource_costs=zero_costs,
        required_tech_count=1,
        civ=slot,
        full_tech_mode=1,   # auto-fire when requirements met (no type=8 needed)
        language_dll_name=-1,
        language_dll_description=-1,
        effect_id=new_eff_id,
        type=0,
        icon_id=-1,
        language_dll_help=-1,
        language_dll_tech_tree=-1,
        name=f"__hero_imp_enable_{slot}",
        repeatable=1,   # matches km_custom_uu._make_avail_tech pattern
        research_locations=[ResearchLocation(location_id=-1, research_time=0, button_id=0, hot_key_id=-1)],
    )
    new_tech_id = len(dat.techs)
    dat.techs.append(imp_tech)
    print(f"       Hero unit: Imperial Age auto-fire enable tech id={new_tech_id} eff_id={new_eff_id}")

    # Disable the standard Trebuchet: tech 256 enables unit 331 (PTREB) at Castle btn 2
    # on Imperial Age, which would overwrite the hero at the same button.
    tt_eff.effect_commands.append(EffectCommand(type=102, a=-1, b=-1, c=-1, d=256.0))
    print("       Hero unit: disabled Trebuchet tech 256 (frees Castle btn 2)")

    # ── Language string DAT fields — assign a pool-allocated ID as language_dll_name
    # so wizard_build.py can write custom strings to it reliably.  Campaign heroes
    # carry their own (possibly 0 or campaign-specific) language_dll_name; we replace
    # it with a known-good CAMPAIGN_STRING_POOL entry in the 44000-range so the
    # +21000 Castle hover slot (65000-range, safe and overridable) works correctly.
    # Also sever the base_id/copy_id chain: campaign heroes point at a source unit,
    # making the engine show campaign bio text instead of our strings.
    hero_name_sid = _campaign_sid(HERO_POOL_OFFSET + slot)
    unit.base_id = base_id
    unit.copy_id = base_id
    # unit.enabled is deliberately left at its vanilla value (0 for every campaign
    # hero).  Liu Bei — the shipped one-at-a-time hero — is enabled=0 too; the cap
    # comes from attributes 126/127 in imp_eff above, not from the enabled flag.
    unit.disabled = 0   # clean base for the EC_ADD on attribute 127
    unit.language_dll_name     = hero_name_sid
    unit.language_dll_creation = hero_name_sid + 1000
    unit.language_dll_help     = hero_name_sid + 100000

    if unit.creatable:
        # ── Train location: always Castle btn 2 (W key = hotkey 16381) ───────
        if unit.creatable.train_locations:
            loc = unit.creatable.train_locations[0]
            loc.unit_id    = 82   # Castle
            loc.button_id  = 2
            loc.hot_key_id = 16381  # W key, button 2 — matches Liu Bei
            loc.train_time = _HERO_TRAIN_TIME

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

        # ── hero_mode 1 = hero status: gold portrait border, passive regen, ──
        # conversion immunity.  It does NOT cap the unit count — that is the
        # 126/127 attribute pair in imp_eff.  creatable_type is left alone: it
        # is the unit's combat class (1 cavalry / 2 infantry / 3 archer / 5 monk)
        # and overwriting it breaks bonus-damage matchups for the chosen base.
        unit.creatable.hero_mode = 1
    else:
        print(f"       Hero unit: WARNING — unit {base_id} has no Creatable data; "
              "train location, cost, and hero_mode cannot be set. "
              "Choose a trainable military unit as the hero base.", flush=True)

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
