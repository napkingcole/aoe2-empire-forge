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

from civ_schema import norm_elite_upgrade
from civ_appender import (HERO_POOL_OFFSET, _campaign_sid,
                          format_unit_tooltip_help, format_unit_extended_tooltip)


# ── UT cost / time override ───────────────────────────────────────────────────

def _override_ut_costs(dat, civ_result: dict, draft: dict) -> None:
    """
    After apply_civ creates Castle/Imperial UT techs, patch their costs and
    research time from the wizard draft (or civbuilder_v1 converted draft) —
    and the Elite unique-unit upgrade's, from unique_unit.elite_upgrade.
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

        _set_tech_cost_time(dat.techs[tech_id], ut_data.get("cost"), ut_data.get("time"))

    # The Elite UU upgrade (#68).  km_uu_elite_tech_id is this civ's own copy of
    # the upgrade tech — for a vanilla UU too (Teutonic Knight: 364 -> 1514) —
    # so changing it touches no other civ.
    elite_up = norm_elite_upgrade((draft.get("unique_unit") or {}).get("elite_upgrade"))
    elite_tid = civ_result.get("km_uu_elite_tech_id")
    if elite_up and isinstance(elite_tid, int) and 0 <= elite_tid < len(dat.techs):
        _set_tech_cost_time(dat.techs[elite_tid], elite_up["cost"], elite_up["time"])


def _set_tech_cost_time(tech, cost: dict | None, time_val) -> None:
    """Write a player-set cost and research time onto a tech.

    Zero means "unset", not "free".  Nothing can currently express the
    difference: the wizard seeds a new UT with an all-zero cost, KM import
    emits zeros, and from_draft/to_draft both write `int(x or 0)` on every
    save round-trip.  Applying those zeros stripped the real cost and
    research time off a copied vanilla tech, so a KM-imported UT was free
    and instant.  Skipping them leaves what apply_civ produced — a vanilla
    copy keeps its own cost/time, a synthesised custom UT keeps
    _make_tech's free/60s default — which is right in both modes.
    A deliberately free UT stays inexpressible until normalize() can carry
    absent and zero apart (PLAN-canonical-schema, finding 5).

    The time lives on each ResearchLocation; genieutils' Tech has no
    research_time field.  This used to write `tech.research_time`, which
    Python accepted as a stray attribute and the DAT never saw, so every
    custom UT research time was silently ignored (found 2026-10-08).
    """
    if time_val is not None and int(time_val) > 0:
        for loc in tech.research_locations:
            if loc.location_id >= 0:            # -1 is an auto-fire placeholder
                loc.research_time = int(time_val)

    cost = cost or {}
    wanted = [(res_type, int(cost.get(res_name) or 0))
              for res_name, res_type in (("food", 0), ("wood", 1),
                                         ("stone", 2), ("gold", 3))]
    if any(amount > 0 for _, amount in wanted):
        slots = [ResearchResourceCost(type=res_type, amount=amount, flag=1)
                 for res_type, amount in wanted if amount > 0]
        while len(slots) < 3:
            slots.append(ResearchResourceCost(type=-1, amount=0, flag=0))
        tech.resource_costs = tuple(slots[:3])


# ── UU stat overrides + advanced flags ───────────────────────────────────────

_CASTLE_BUILDING     = 82
_KREPOST_BUILDING    = 1251
_CASTLE_BTN1_HOTKEY  = 16101   # Q key, Castle/Krepost button 1


def _refresh_uu_tooltips(dat, slot: int, civ_result: dict | None) -> None:
    """Re-render the KM-custom UU's Castle tooltips from the unit's CURRENT stats.

    apply_civ builds these strings while it is still assembling the civ, which
    is before _apply_uu_overrides has touched the unit — so a UU with a cost or
    stat override published the preset numbers and the user's own values showed
    up nowhere (issue #34).  Re-rendering here is cheap and keeps one copy of
    the formatting logic, in civ_appender, rather than a second one per caller.

    No-op for vanilla KM UUs: those strings are written by the caller after this
    point and already read the overridden unit.
    """
    if not civ_result:
        return
    entries = (civ_result.get("bonus_results") or {}).get("extra_unit_strings") or []
    for ext in entries:
        regen = ext.get("regen")
        uid   = ext.get("unit_id")
        if not regen or uid is None:
            continue
        try:
            unit = dat.civs[slot].units[uid]
        except (IndexError, KeyError, TypeError):
            continue
        if unit is None:
            continue
        ext["help_text"] = format_unit_tooltip_help(
            unit, ext["name"], extra=regen.get("extra", ""))
        ext["ext_text"] = format_unit_extended_tooltip(
            unit, ext["name"], tag=regen.get("tag", ""), desc=regen.get("desc", ""))


_RES = {"food": 0, "wood": 1, "stone": 2, "gold": 3}
_SPENDABLE = set(_RES.values())


def _dominant_attack(u):
    cls4 = next((a for a in u.type_50.attacks if a.class_ == 4), None)
    cls3 = next((a for a in u.type_50.attacks if a.class_ == 3), None)
    return cls4 if (cls4 and (not cls3 or cls4.amount >= cls3.amount)) else cls3


def write_unit_stats(u, stats: dict) -> None:
    """Write player-set stats onto one unit: hp, speed, range, reload, attack,
    melee, pierce, los, train.  Absent (or None) means "keep the game's".
    Shared by the unique unit's overrides and the tech tree's unit edits."""
    stats = {k: v for k, v in stats.items() if v is not None}

    if "hp" in stats:
        u.hit_points = int(stats["hp"])

    if "speed" in stats:
        u.speed = float(stats["speed"])

    if "los" in stats:
        u.line_of_sight = float(stats["los"])

    if u.type_50 is not None:
        # Each stat has a real field and a displayed one, and KM writes both.
        # Writing only the displayed reload left the unit attacking at its
        # vanilla speed (issues #98, #104); only max_range left the tooltip
        # on the old range.
        if "range" in stats:
            u.type_50.max_range = u.type_50.displayed_range = float(stats["range"])

        if "reload" in stats:
            u.type_50.reload_time = u.type_50.displayed_reload_time = float(stats["reload"])

        if "attack" in stats:
            v = int(stats["attack"])
            u.type_50.displayed_attack = v
            dominant = _dominant_attack(u)
            if dominant:
                dominant.amount = v
            elif u.type_50.attacks:
                u.type_50.attacks[0].amount = v

        if "melee" in stats:
            v = int(stats["melee"])
            for a in u.type_50.armours:
                if a.class_ == 4:
                    a.amount = v
                    break
            u.type_50.displayed_melee_armour = v

        if "pierce" in stats:
            v = int(stats["pierce"])
            for a in u.type_50.armours:
                if a.class_ == 3:
                    a.amount = v
                    break
            if u.creatable:
                u.creatable.displayed_pierce_armour = v

    if "train" in stats and u.creatable:
        # train_time is a field of each TrainLocation, not of the unit, so a
        # UU that trains in more than one building has one copy per slot.
        # Writing only [0] left the Anarchy Barracks slot and the Krepost
        # slot on the vanilla time while the Castle showed the override
        # (issue #29).  apply_civ appends those extra slots before we run,
        # so every one of them is already here.
        for tl in u.creatable.train_locations:
            tl.train_time = int(stats["train"])


def write_unit_cost(u, cost: dict, label: str = "unit") -> None:
    """Make {food, wood, stone, gold} the unit's complete spendable cost.

    `resource_costs` is a fixed 3-slot tuple, and most trainable units spend
    one slot on population (type 4, flag 0), which leaves room for just TWO
    spendable resources.  The old code merged into whatever slots happened to
    be free, so asking a Samurai (food + gold + population — all three slots
    full) for wood silently dropped the wood and left the vanilla cost intact
    (issue #35).

    The cost is therefore read as the complete spendable cost, not as a patch
    over the vanilla one: "wood 65, gold 30" means the unit costs 65 wood and
    30 gold, with the unmentioned food gone.  Non-spendable slots (population,
    and the rarer 214/215/501/514 counters) are preserved.  Writing the slots
    directly can retype them, which an EC_SET cannot (CLAUDE.md quirk 14).
    """
    if not u.creatable:
        return
    _NAME  = {v: k for k, v in _RES.items()}
    wanted = [(_RES[r], int(a)) for r, a in sorted(cost.items(), key=lambda kv: _RES[kv[0]])
              if r in _RES and int(a or 0) > 0]
    rc = u.creatable.resource_costs
    free = [i for i, s in enumerate(rc) if s.type in _SPENDABLE or s.type == -1]

    if len(wanted) > len(free):
        dropped = ", ".join(f"{_NAME[t]} {a}" for t, a in wanted[len(free):])
        print(f"       WARNING: {label} cost needs {len(wanted)} resource "
              f"slots but only {len(free)} are spendable (a unit has 3 slots "
              f"total and this one reserves "
              f"{len(rc) - len(free)} for population) — dropped: {dropped}")

    for i, (res_type, amount) in zip(free, wanted):
        rc[i].type   = res_type
        rc[i].amount = amount
        rc[i].flag   = 1
    for i in free[len(wanted):]:          # clear any slot we no longer use
        rc[i].type   = -1
        rc[i].amount = 0
        rc[i].flag   = 0


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
    uu = draft.get("unique_unit") or {}
    # Every read below is a membership test ("cost_food" in overrides), which an
    # explicit null passes before reaching int(None).  to_draft strips nulls, so
    # the wizard door could never hit that; the upload door hands us the raw
    # schema, which keeps them — a hand-authored file with `"cost_food": null`
    # crashed the build.  Restore the absence == "no override" contract here so
    # both doors read the same thing.
    overrides = {k: v for k, v in (uu.get("overrides")      or {}).items() if v is not None}
    flags     = {k: v for k, v in (uu.get("advanced_flags") or {}).items() if v is not None}

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
        if u is not None:
            write_unit_stats(u, {k[:-len(sfx)]: v for k, v in overrides.items()
                                 if k.endswith(sfx)})

    # Training cost overrides (shared — applies to both tiers).  The four boxes
    # are the complete spendable cost, matching the wizard's one combined
    # "Default: 45F 30G" label; see write_unit_cost.
    cost_overrides = {r: int(overrides[f"cost_{r}"]) for r in _RES if f"cost_{r}" in overrides}
    if cost_overrides:
        for u, _ in tiers:
            if u is not None:
                write_unit_cost(u, cost_overrides, "unique unit")

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

    # DISABLED — this flag cannot be expressed in the DAT, and the previous
    # implementation reduced the unit to 1 damage against everything.
    #
    # It replaced the unit's Base Melee/Base Pierce attacks with a single attack
    # on armour class 50.  **No unit in the game has armour class 50** (checked:
    # 0 of 421 trainable attacking units), and the damage formula is
    #     dmg = max( Σ max(At_i − Ar_i, 0), 1 )
    # where a missing armour class on the defender means Ar_i = the base armour
    # value, "almost always 1000" (UGC guide, damage_calculation.md).  So the one
    # remaining attack line resolved to max(25 − 1000, 0) = 0 and the unit dealt
    # the engine minimum of 1.  Confirmed in-game 2026-09-18 on a 25-attack
    # Janissary that was hitting for 1.
    #
    # There is no correct replacement available to us.  Armour class 31 looks
    # like a candidate (99.3% of units carry it, 96% at zero) but it is the
    # cavalry-vs-buildings class — every cavalry unit attacks it, and the only
    # non-zero holders are Castles, towers and Docks, so using it would give the
    # unit nothing and penalise it against exactly the targets it should beat.
    # And diffing the Leitis, the game's own armour-ignoring unit, against a
    # Knight across every scalar field on unit/type_50/creatable turns up only
    # graphics and stats — its behaviour is hardcoded in the engine by unit id,
    # not something the DAT can grant to an arbitrary unit.
    if flags.get("ignore_armor"):
        print("       WARNING: the unique unit's 'ignore armor' flag is not "
              "supported and was ignored. AoE2 has no data-level way to grant "
              "it — the unit keeps its normal attack. (The previous behaviour "
              "was worse: it reduced the unit to 1 damage.)")

    if flags.get("bonus_dmg_resist") is not None:
        pct = float(flags["bonus_dmg_resist"])
        resistance = max(0.0, min(1.0, 1.0 - pct / 100.0))
        for u, _ in tiers:
            if u and u.type_50:
                u.type_50.bonus_damage_resistance = resistance

    # Charge Attack is the Comitatenses / Coustillier charge: event 1 (attacking
    # spends it), type 1 "attack charge".  This wrote type 2 until 2026-10-08 —
    # undocumented ("??? charge" in the UGC guide) and used by no vanilla unit.
    # Type 1 is not melee-only: Alexander's Mercenary Archer and Harald are
    # ranged units that carry it.
    if flags.get("charge_pool") is not None:
        pool = float(flags["charge_pool"])
        rate = float(flags.get("charge_rate") or 0.25)
        for u, _ in tiers:
            if u and u.creatable:
                u.creatable.max_charge    = pool
                u.creatable.recharge_rate = rate
                u.creatable.charge_event  = 1
                u.creatable.charge_type   = 1

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
      - Castle btn 4 (placed by civ_appender._place_hero), 60 s train time
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

    # The hero used to share Castle button 2 with the Trebuchet, so this
    # disabled tech 256 (the Trebuchet's Imperial unlock) to make room — which
    # is why picking a hero cost the civ its Trebuchet.  The hero now trains on
    # button 4 (civ_appender._place_hero), so the Trebuchet stays (2026-10-05).

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

    # Only claim the pool SIDs when the caller will actually write text to them.
    # The pool holds *existing* campaign strings, so repointing without writing
    # does not blank the name — it swaps the hero's name for whatever campaign
    # line happens to live at that id ("The English castle at Falkirk is no
    # more!").  An unnamed hero keeps its vanilla strings instead, which is
    # always a sane fallback.  wizard_build.py / app.py gate their string writes
    # on the same non-empty name, so the two stay in step.
    if (hero.get("name") or "").strip():
        unit.language_dll_name     = hero_name_sid
        unit.language_dll_creation = hero_name_sid + 1000
        unit.language_dll_help     = hero_name_sid + 100000
    else:
        print("       Hero unit: no name given — keeping vanilla strings "
              "(a pool SID with no text written shows campaign dialogue)")

    if unit.creatable:
        # ── Train location: placed by apply_civ (civ_appender._place_hero) ──
        # Castle button 4, or wherever the button planner moved it — button 2
        # is the Trebuchet's, and forcing it here took the Trebuchet away.
        # Only the train time is the hero's own default.
        if unit.creatable.train_locations:
            unit.creatable.train_locations[0].train_time = _HERO_TRAIN_TIME

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


# ── Tech-tree edits (the tree page's side panel) ─────────────────────────────

# Age-ups swap every building for its next-age unit (Barracks 12 -> 498 -> 132
# -> 20) by EC_UPGRADE, so an edit on the node id alone is gone at Feudal.
_AGE_TECHS = (101, 102, 103)

# One thing in the game, several units in the DAT.  The tree shows one node;
# an edit has to reach every form, or a packed Trebuchet keeps the old HP the
# moment it unpacks.  Vanilla's own effects disagree on which form to target
# (Trade Cart and Ram effects hit both, Trebuchet effects mostly the unpacked
# 42, Monk effects only 125), so the forms are listed rather than inferred.
_UNIT_FORMS: dict[int, tuple[int, ...]] = {
    331:  (42,),     # Trebuchet: packed (trained) / unpacked
    125:  (286,),    # Monk / Monk carrying a relic (CLAUDE.md quirk 12)
    128:  (204,),    # Trade Cart: empty / full
    1258: (35,),     # Battering Ram: the trained orphan / the upgraded (quirk 4)
    1105: (885,),    # Siege Tower
}
_VILLAGER, _CIVILIAN_CLASS = 83, 4    # Loom reaches every villager by class 4

# Fields a form only takes if it already has that stat: the packed Trebuchet
# neither attacks nor stands still, the unpacked one never moves.
_COMBAT_FIELDS = ("attack", "range", "reload")


def upgrade_successors(dat) -> dict[int, set[int]]:
    """unit -> the units a researchable upgrade turns it into (Knight -> Cavalier,
    Cavalier -> Paladin and Savar).  Age techs are left out: what they swap are
    building forms, see unit_forms.  So are upgrades that change the unit's
    class: Flemish Revolution turns Villagers into Flemish Militia, which is not
    the next Villager, and must not inherit a Villager's cost."""
    units = dat.civs[1].units
    succ: dict[int, set[int]] = {}

    def same_class(a, b):
        return (a < len(units) and b < len(units) and units[a] is not None
                and units[b] is not None and units[a].class_ == units[b].class_)

    for tid, t in enumerate(dat.techs):
        if tid in _AGE_TECHS or not 0 <= t.effect_id < len(dat.effects):
            continue
        if not any(rl.location_id >= 0 for rl in t.research_locations):
            continue
        for c in dat.effects[t.effect_id].effect_commands:
            if c.type == 3 and c.a >= 0 and c.b >= 0 and c.a != c.b and same_class(c.a, c.b):
                succ.setdefault(c.a, set()).add(c.b)
    return succ


def unit_forms(dat, units, uid: int) -> list[int]:
    """Every DAT unit that is the tree node `uid` in the game, uid first."""
    forms = [uid]
    if uid == _VILLAGER:
        forms += [i for i, u in enumerate(units)
                  if u is not None and i != uid and u.class_ == _CIVILIAN_CLASS]
    forms += [f for f in _UNIT_FORMS.get(uid, ()) if f not in forms]
    # Each age tech upgrades from the ORIGINAL building (12 -> 498, 12 -> 132,
    # 12 -> 20), and a later one may start from an earlier variant, so walk all.
    age_up: dict[int, set[int]] = {}
    for tid in _AGE_TECHS:
        if tid < len(dat.techs):
            for c in dat.effects[dat.techs[tid].effect_id].effect_commands:
                if c.type == 3:
                    age_up.setdefault(c.a, set()).add(c.b)
    i = 0
    while i < len(forms):
        forms += [b for b in sorted(age_up.get(forms[i], ())) if b not in forms]
        i += 1
    return [f for f in forms if 0 <= f < len(units) and units[f] is not None]


def _descendants(succ: dict[int, set[int]], root: int, stop=()) -> set[int]:
    out, todo = set(), [root]
    while todo:
        for v in succ.get(todo.pop(), ()):
            if v not in out and v != root:
                out.add(v)
                if v not in stop:
                    todo.append(v)
    return out


def _flow_down(succ: dict[int, set[int]], own: dict) -> dict:
    """Each unit's value: its own, else its latest edited upgrade ancestor's.

    "Latest", not "fewest steps": the Paladin tech upgrades the Knight AND the
    Cavalier straight to Paladin, so with both edited the Paladin is one step
    from each, and it is the Cavalier's cost it should get."""
    reach = {r: _descendants(succ, r, stop=own) for r in own}
    every = {r: _descendants(succ, r) for r in own}
    out = dict(own)
    for v in set().union(*reach.values()) - set(own):
        cands = [r for r in own if v in reach[r]]
        latest = [r for r in cands if not any(o != r and o in every[r] for o in cands)]
        out[v] = own[min(latest or cands)]
    return out


def read_unit_stats(u) -> dict:
    """The values write_unit_stats writes, as the unit has them now."""
    out = {"hp": u.hit_points, "speed": u.speed, "los": u.line_of_sight}
    if u.type_50 is not None:
        dom = _dominant_attack(u)
        out.update(range=u.type_50.max_range, reload=u.type_50.reload_time,
                   attack=dom.amount if dom else u.type_50.displayed_attack,
                   melee=u.type_50.displayed_melee_armour)
    if u.creatable is not None:
        out["pierce"] = u.creatable.displayed_pierce_armour
    return out


def write_bonus_attacks(u, bonus: dict) -> None:
    """{armour class: amount}: set the unit's attack against each class, adding
    the class when the unit lacks it; 0 removes it."""
    if u.type_50 is None:
        return
    from genieutils.unit import AttackOrArmor
    for cls, amount in bonus.items():
        cls, amount = int(cls), int(amount)
        have = next((a for a in u.type_50.attacks if a.class_ == cls), None)
        if amount <= 0:
            if have is not None:
                u.type_50.attacks.remove(have)
        elif have is not None:
            have.amount = amount
        else:
            u.type_50.attacks.append(AttackOrArmor(class_=cls, amount=amount))


def _fights(u) -> bool:
    return u.type_50 is not None and any(a.amount > 0 for a in u.type_50.attacks)


def _apply_unit_edits(dat, slot: int, overrides: dict) -> int:
    """The tree page's unit and building edits, written onto this civ's own
    units (no effect commands).  Cost and train time flow down the upgrade line
    unless a later tier has its own; everything else is per tier.  Returns the
    number of units written."""
    from civ_schema import norm_unit_edits
    edits = {int(k): e for k, e in norm_unit_edits(overrides.get("unit_edits")).items()}
    if not edits:
        return 0
    units = dat.civs[slot].units
    succ = upgrade_successors(dat)
    touched: set[int] = set()

    def each_form(uid):
        if 0 <= uid < len(units) and units[uid] is not None:
            for f in unit_forms(dat, units, uid):
                touched.add(f)
                yield f, units[f], f == uid

    for uid, cost in _flow_down(succ, {u: e["cost"] for u, e in edits.items() if "cost" in e}).items():
        for f, u, _ in each_form(uid):
            write_unit_cost(u, cost, f"unit {f}")
    for uid, t in _flow_down(succ, {u: e["train"] for u, e in edits.items() if "train" in e}).items():
        for _, u, _ in each_form(uid):
            write_unit_stats(u, {"train": t})

    # The node takes the player's number; its other forms take the same
    # difference, so they keep their own (a Barracks gains 300 HP and 1 armour
    # an age: edited to 2000 in the Dark Age, it is 2900 in Imperial).
    for uid, e in sorted(edits.items()):
        stats = {k: v for k, v in e.items() if k not in ("cost", "train", "bonus", "name")}
        if not (0 <= uid < len(units) and units[uid] is not None):
            continue
        node_now = read_unit_stats(units[uid])
        delta = {k: v - node_now[k] for k, v in stats.items() if k in node_now}
        for _, u, is_node in each_form(uid):
            if is_node:
                write_unit_stats(u, stats)
            else:
                now = read_unit_stats(u)
                own = {k: now[k] + d for k, d in delta.items() if k in now}
                for k in _COMBAT_FIELDS:
                    if k in own and not _fights(u):
                        own.pop(k)
                if "speed" in own and not u.speed:
                    own.pop("speed")
                if "hp" in own:
                    own["hp"] = max(1, int(own["hp"]))
                write_unit_stats(u, own)
            if e.get("bonus") and (is_node or _fights(u)):
                write_bonus_attacks(u, e["bonus"])
    return len(touched)


def edited_fields(dat, units, raw_edits) -> dict[int, set[str]]:
    """Which fields the tree edits set on each DAT unit, as _apply_unit_edits
    writes them: stats and bonus classes ("bonus:<cls>") on the node and its
    forms, "train" and "cost" down the line too.  The stats preview uses it to
    tell an edit from the game's own value."""
    from civ_schema import norm_unit_edits
    edits = {int(k): e for k, e in norm_unit_edits(raw_edits).items()}
    out: dict[int, set[str]] = {}

    def mark(uid, field):
        if 0 <= uid < len(units) and units[uid] is not None:
            for f in unit_forms(dat, units, uid):
                out.setdefault(f, set()).add(field)

    succ = upgrade_successors(dat) if any("cost" in e or "train" in e for e in edits.values()) else {}
    for field in ("cost", "train"):
        for uid in _flow_down(succ, {u: 1 for u, e in edits.items() if field in e}):
            mark(uid, field)
    for uid, e in edits.items():
        for k, v in e.items():
            if k == "bonus":
                for cls in v:
                    mark(uid, f"bonus:{cls}")
            elif k not in ("cost", "train"):
                mark(uid, k)
    return out


def _tech_time(tech) -> int:
    return next((int(rl.research_time) for rl in tech.research_locations
                 if rl.location_id >= 0), 0)


def _apply_tech_edits(dat, slot: int, overrides: dict, warnings: list) -> int:
    """The tree page's tech cost and research-time edits.

    A tech is shared by every civ, so it can't be written directly.  Each edit
    becomes a "ghost" command in one civ-owned auto-fire tech: EC_TECH_COST /
    EC_TECH_TIME in multiply mode (c=2), scaling the game's value to the
    player's.  Vanilla writes exactly this (Byzantine Imperial Age gold x0.67,
    Turkish Chemistry food and wood x0.5, Vietnamese time x0.5).  Multiplies
    commute, so a "-50% gold" card gives the same result before or after.

    A multiply can't add a resource the tech doesn't already cost, so that is
    skipped with a warning (the panel only offers the tech's own resources).
    Returns the number of commands written."""
    from civ_schema import norm_tech_edits
    from civ_appender import _append_effect, _append_tech, _make_tech
    edits = norm_tech_edits(overrides.get("tech_edits"))
    cmds: list[EffectCommand] = []
    for key, e in sorted(edits.items(), key=lambda kv: int(kv[0])):
        tid = int(key)
        if not 0 <= tid < len(dat.techs):
            continue
        tech = dat.techs[tid]
        have = {rc.type: rc.amount for rc in tech.resource_costs
                if rc.type in _SPENDABLE and rc.amount > 0}
        for res, amount in (e.get("cost") or {}).items():
            rtype = _RES[res]
            if rtype not in have:
                if amount > 0:
                    warnings.append(f"{tech.name}: can't add a {res} cost to a tech that "
                                    f"doesn't already cost {res}; left as the game's.")
                continue
            if amount != have[rtype]:
                cmds.append(EffectCommand(type=101, a=tid, b=rtype, c=2,
                                          d=amount / have[rtype]))
        if e.get("time") is not None and (now := _tech_time(tech)) > 0 and e["time"] != now:
            cmds.append(EffectCommand(type=103, a=tid, b=-1, c=2, d=e["time"] / now))
    if not cmds:
        return 0
    eff = Effect(name="Tech tree edits", effect_commands=cmds)
    eid = _append_effect(dat, eff)
    _append_tech(dat, _make_tech("Tech tree edits", eid, slot))
    return len(cmds)


def _apply_unit_names(dat, slot: int, overrides: dict, civ_result: dict,
                      uu_info: dict | None) -> int:
    """The tree page's renames.  A unit's name is its language_dll_name, and
    units are per civ, so pointing this civ's copy at a fresh pool id renames
    it here only.  The id comes from the mod-wide editor block (_editor_sid);
    the name, "Create …" label and both tooltips go out through
    extra_unit_strings, which all three routes write, and `renamed_units`
    {unit: sid} lets the F2 tree viewer name the node the same way.

    Every form named after the node is renamed with it, keeping what tells
    the forms apart: the node's name less any "(…)" is the stem, and a form
    whose name starts with it keeps the rest ("Trebuchet (Packed)" and
    "Trebuchet" -> "Siege Engine (Packed)" and "Siege Engine"; "Monk with
    Relic" -> "Priest with Relic").  Forms named otherwise (the villager jobs)
    keep their names.  Each distinct new name takes one pool id.  The civ's unique unit and
    hero are named on their own wizard steps, so they are left alone here.
    Runs after the stat edits, so the tooltips quote the edited numbers.

    The upgrade TECH keeps its name: techs are shared by every civ, and a
    per-civ copy would hide the upgrade from the AI (it researches by id) and
    from cards that discount that tech."""
    from civ_appender import (_OWN_STRING_NAMES, _creation_sid, _display_name, _editor_sid,
                              _extended_tooltip_sid, _help_sid)
    from civ_schema import norm_unit_edits
    names = {int(k): e["name"] for k, e in norm_unit_edits(overrides.get("unit_edits")).items()
             if e.get("name")}
    own = {uu_info.get("unit_id"), uu_info.get("elite_id")} if uu_info else set()
    units = dat.civs[slot].units
    template = dat.civs[1].units
    renamed = civ_result.setdefault("renamed_units", {})
    extra = civ_result.setdefault("bonus_results", {}).setdefault("extra_unit_strings", [])
    import re
    shown = lambda u: _display_name(u.language_dll_name, u.name) or ""   # noqa: E731
    for uid, name in sorted(names.items()):
        node = units[uid] if 0 <= uid < len(units) else None
        if node is None or uid in own or uid in renamed:
            continue
        stem = re.sub(r"\s*\(.*\)$", "", shown(node)).strip()
        texts: dict[int, str] = {}                       # form -> its new name
        for f in unit_forms(dat, units, uid):
            u = units[f]
            if u is None:
                continue
            t = shown(u)
            if f == uid or (stem and t.startswith(stem)):
                texts[f] = name + (t[len(stem):] if stem and t.startswith(stem) else "")
        sids: dict[str, int] = {}
        for f, text in texts.items():                    # node first: unit_forms order
            if text not in sids:
                sids[text] = _editor_sid(dat)
                _OWN_STRING_NAMES[sids[text]] = text     # what logs and previews show
            sid = sids[text]
            u = units[f]
            u.language_dll_name = sid
            u.language_dll_creation = _creation_sid(sid)
            u.language_dll_help = _help_sid(sid)
            renamed[f] = sid
        for text, sid in sids.items():
            u = units[next(f for f, t in texts.items() if t == text)]
            where = ""
            if u.creatable and u.creatable.train_locations:
                b = u.creatable.train_locations[0].unit_id
                bu = template[b] if 0 <= b < len(template) else None
                where = shown(bu) if bu else ""
            extra.append({
                "sid": sid, "name": text, "desc_sid": _help_sid(sid),
                "help_text": format_unit_tooltip_help(
                    u, name, extra=f"Trainable at {where}." if where else ""),
                "ext_sid": _extended_tooltip_sid(sid),
                "ext_text": format_unit_extended_tooltip(u, name),
            })
    return len(renamed)


# ── The whole DAT write for one civ ───────────────────────────────────────────

def apply_civ_with_overrides(dat, civ_def: dict, slot: int,
                             overrides: dict | None = None) -> tuple[dict, dict | None]:
    """apply_civ plus every post-apply patch, in the order all three build
    routes run them.  Returns (civ_result, uu_info).

    overrides — the dict the UU/UT/hero patches read: the wizard passes its
    draft, the other routes the civ_def itself (the default).  One function so
    the stats preview (fu_stats) sees exactly the DAT a build writes."""
    from civ_appender import apply_civ
    from build_civ import _resolve_uu_info
    overrides = civ_def if overrides is None else overrides
    civ_result = apply_civ(dat, civ_def, target_slot=slot)
    uu_info = _resolve_uu_info(civ_def, dat, slot, civ_result)
    _override_ut_costs(dat, civ_result, overrides)
    _apply_uu_overrides(dat, slot, uu_info, overrides)
    _refresh_uu_tooltips(dat, slot, civ_result)
    _apply_hero_unit(dat, slot, overrides)
    _apply_unit_edits(dat, slot, overrides)
    _apply_unit_names(dat, slot, overrides, civ_result, uu_info)
    _apply_tech_edits(dat, slot, overrides, civ_result.setdefault("warnings", []))
    return civ_result, uu_info
