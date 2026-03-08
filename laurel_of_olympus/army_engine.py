"""
army_engine.py – Barracks construction, Army recruitment, and Campaign system.

Data sources:
  data/army_units.json       – Unit definitions, army size limits
  data/campaign_regions.json – Campaign regions, launch cost, rewards
  data/flavor_text.json      – Victory / event flavor lines

Public API:
  build_barracks(state) -> tuple[bool, str]
      Deduct resources and unlock soldier recruitment.

  recruit_unit(state, unit_id) -> tuple[bool, str]
      Pay unit cost, add unit to army list.

  disband_unit(state, unit_id) -> tuple[bool, str]
      Remove one instance of a unit from the army.

  get_army_strength(state, buffs=None) -> float
      Sum unit strengths scaled by the army_strength buff multiplier.

  get_army_details(state) -> list[dict]
      Enriched units currently in the army (collapsed by type + count).

  get_all_units() -> list[dict]
      All unit definitions with enriched display fields.

  get_all_regions() -> list[dict]
      All campaign region definitions.

  launch_campaign(state, region_id, buffs=None) -> dict
      Full campaign resolution — mutates state, returns result dict
      compatible with the frontend event-popup format.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from laurel_of_olympus.game_state import PlayerState
from laurel_of_olympus import creature_engine, relic_engine, buff_engine

# ---------------------------------------------------------------------------
# Load data files once at import time
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent / "data"

_UNITS_RAW      = json.loads((_DATA_DIR / "army_units.json").read_text())
_UNITS: List[dict]  = _UNITS_RAW["units"]
_UNIT_MAP: Dict[str, dict] = {u["id"]: u for u in _UNITS}
_ARMY_LIMITS: dict  = _UNITS_RAW["army_limits"]

_REGIONS_RAW    = json.loads((_DATA_DIR / "campaign_regions.json").read_text())
_REGIONS: List[dict] = _REGIONS_RAW["regions"]
_REGION_MAP: Dict[str, dict] = {r["id"]: r for r in _REGIONS}
_CAMPAIGN_COST: dict = _REGIONS_RAW["campaign_cost"]

_FLAVOR         = json.loads((_DATA_DIR / "flavor_text.json").read_text())
_VICTORY_LINES: List[str] = _FLAVOR.get("victory_lines", [
    "Victory echoes across the valley.",
    "Your strength prevails.",
    "The enemy falters.",
    "A triumphant moment.",
    "The gods nod in approval.",
])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BARRACKS_COST: Dict[str, int] = {"drachmae": 600, "grain": 40, "wine": 10}

UNIT_ICONS: Dict[str, str] = {
    "hoplite":          "⚔️",
    "archer":           "🏹",
    "cavalry":          "🐴",
    "myrmidon_captain": "🛡️",
}

RARITY_ICONS: Dict[str, str] = {
    "common":    "🌿",
    "rare":      "⚡",
    "epic":      "🔥",
    "legendary": "✨",
}

RARITY_COLORS: Dict[str, str] = {
    "common":    "var(--success)",
    "rare":      "var(--accent)",
    "epic":      "#e06c1a",
    "legendary": "var(--gold)",
}

_DEFEAT_LINES: List[str] = [
    "The enemy holds the line.",
    "Your army retreats, battered.",
    "Not every campaign ends in glory.",
    "The gods look away today.",
    "Regroup. The war is not over.",
    "Defeat stings, but resolve remains.",
    "The scroll records this setback quietly.",
    "Tomorrow belongs to the disciplined.",
]


# ---------------------------------------------------------------------------
# Barracks
# ---------------------------------------------------------------------------

def build_barracks(state: PlayerState) -> Tuple[bool, str]:
    """
    Construct a Barracks on the estate.
    Cost: 600 drachmae + 40 grain + 10 wine.
    Returns (success, message).
    """
    if state.barracks_built:
        return False, "The Barracks is already standing."
    # Resource checks
    if state.drachmae < BARRACKS_COST["drachmae"]:
        return False, (
            f"Not enough drachmae. Need {BARRACKS_COST['drachmae']} "
            f"(have {state.drachmae:.0f})."
        )
    if state.grain < BARRACKS_COST["grain"]:
        return False, (
            f"Not enough grain. Need {BARRACKS_COST['grain']} "
            f"(have {state.grain})."
        )
    if state.wine < BARRACKS_COST["wine"]:
        return False, (
            f"Not enough wine. Need {BARRACKS_COST['wine']} "
            f"(have {state.wine})."
        )
    # Deduct cost
    state.drachmae  = round(state.drachmae - BARRACKS_COST["drachmae"], 2)
    state.grain    -= BARRACKS_COST["grain"]
    state.wine     -= BARRACKS_COST["wine"]
    state.barracks_built = True
    state.army_limit = _ARMY_LIMITS["barracks_level_1"]  # 10
    return True, "Barracks constructed. Soldiers may now be recruited."


# ---------------------------------------------------------------------------
# Army recruitment / disbanding
# ---------------------------------------------------------------------------

def recruit_unit(state: PlayerState, unit_id: str) -> Tuple[bool, str]:
    """
    Recruit one unit of the given type.
    Deducts resources and appends unit_id to state.army.
    Returns (success, message).
    """
    if not state.barracks_built:
        return False, "Build a Barracks before recruiting soldiers."
    if unit_id not in _UNIT_MAP:
        return False, f"Unknown unit: {unit_id}"
    if len(state.army) >= state.army_limit:
        return False, (
            f"Army is at full strength ({state.army_limit}/{state.army_limit} units). "
            "Disband a unit to make room."
        )
    unit = _UNIT_MAP[unit_id]
    cost = unit["cost"]

    # Resource checks
    if state.drachmae < cost.get("drachmae", 0):
        return False, (
            f"Not enough drachmae. Need {cost['drachmae']} "
            f"(have {state.drachmae:.0f})."
        )
    if state.grain < cost.get("grain", 0):
        return False, f"Not enough grain. Need {cost['grain']} (have {state.grain})."
    if cost.get("wine") and state.wine < cost["wine"]:
        return False, f"Not enough wine. Need {cost['wine']} (have {state.wine})."
    if cost.get("olive_oil") and state.olive_oil < cost["olive_oil"]:
        return False, (
            f"Not enough olive oil. Need {cost['olive_oil']} "
            f"(have {state.olive_oil})."
        )

    # Deduct cost
    state.drachmae  = round(state.drachmae - cost.get("drachmae", 0), 2)
    state.grain    -= cost.get("grain", 0)
    if cost.get("wine"):      state.wine      -= cost["wine"]
    if cost.get("olive_oil"): state.olive_oil -= cost["olive_oil"]

    state.army.append(unit_id)
    return True, f"{unit['name']} recruited into the army."


def disband_unit(state: PlayerState, unit_id: str) -> Tuple[bool, str]:
    """
    Disband one unit of the given type (removes the first occurrence).
    Returns (success, message).
    """
    if unit_id not in state.army:
        return False, "That unit is not in your army."
    state.army.remove(unit_id)  # removes first occurrence
    name = _UNIT_MAP.get(unit_id, {}).get("name", unit_id)
    return True, f"{name} disbanded."


# ---------------------------------------------------------------------------
# Army strength
# ---------------------------------------------------------------------------

def get_army_strength(state: PlayerState, buffs: Optional[dict] = None) -> float:
    """
    Calculate total army strength:
      raw = sum of each unit's strength
      buffed = raw * army_strength buff multiplier (from creatures/relics)
    """
    buffs = buffs or {}
    raw   = sum(
        _UNIT_MAP[uid]["strength"]
        for uid in state.army
        if uid in _UNIT_MAP
    )
    return round(raw * buffs.get("army_strength", 1.0), 2)


# ---------------------------------------------------------------------------
# Campaign launch
# ---------------------------------------------------------------------------

def launch_campaign(
    state: PlayerState,
    region_id: str,
    buffs: Optional[dict] = None,
) -> dict:
    """
    Resolve a military campaign against the given region.

    Steps:
      1. Validate state (barracks, army, resources).
      2. Deduct launch cost.
      3. Compare army_strength to region difficulty.
      4a. Victory: award drachmae (scaled by campaign_rewards buff), roll for
          relic and creature rewards.  Increment campaigns_won.
      4b. Defeat: lose 1–3 random units.
      5. Return a result dict compatible with the frontend event-popup.

    The returned dict contains:
      type, victory, region_*, army_strength, difficulty,
      icon, title, lines (for event popup),
      drachmae_earned, relic_reward (dict|None), creature_reward (dict|None),
      units_lost (list[str]), campaigns_won.
    """
    buffs = buffs or {}

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not state.barracks_built:
        return {"error": "Build a Barracks before launching campaigns."}
    if not state.army:
        return {"error": "Recruit at least one soldier before launching a campaign."}

    region = _REGION_MAP.get(region_id)
    if not region:
        return {"error": f"Unknown region: {region_id!r}"}

    cost = _CAMPAIGN_COST
    if state.drachmae < cost["drachmae"]:
        return {"error": f"Not enough drachmae. Campaign costs 🪙 {cost['drachmae']}."}
    if state.grain < cost["grain"]:
        return {"error": f"Not enough grain. Campaign costs 🌾 {cost['grain']}."}

    # ── Deduct launch cost ───────────────────────────────────────────────────
    state.drachmae  = round(state.drachmae - cost["drachmae"], 2)
    state.grain    -= cost["grain"]

    # ── Battle resolution ────────────────────────────────────────────────────
    army_str = get_army_strength(state, buffs)
    victory  = army_str > region["difficulty"]

    result: dict = {
        "type":               "campaign",
        "victory":            victory,
        "region_id":          region_id,
        "region_name":        region["name"],
        "region_description": region["description"],
        "army_strength":      army_str,
        "difficulty":         region["difficulty"],
        "drachmae_earned":    0.0,
        "relic_reward":       None,
        "creature_reward":    None,
        "units_lost":         [],
        "campaigns_won":      state.campaigns_won,
        "icon":               "⚔️" if victory else "💀",
        "title":              (
            f"Victory at {region['name']}" if victory
            else f"Defeat at {region['name']}"
        ),
        "lines": [],
    }

    if victory:
        # ── Drachmae reward ──────────────────────────────────────────────────
        rmin, rmax   = region["reward_drachmae"]
        base_reward  = random.randint(rmin, rmax)
        camp_buff    = buffs.get("campaign_rewards", 1.0)
        earned       = round(base_reward * camp_buff, 2)
        state.drachmae = round(state.drachmae + earned, 2)
        result["drachmae_earned"] = earned

        state.campaigns_won    += 1
        result["campaigns_won"] = state.campaigns_won

        # ── Relic reward ─────────────────────────────────────────────────────
        relic_chance = buff_engine.effective_relic_chance(buffs, region["relic_chance"])
        if random.random() < relic_chance:
            relic = relic_engine.roll_relic_reward()
            if relic:
                result["relic_reward"] = relic

        # ── Creature reward ──────────────────────────────────────────────────
        creature_chance = buff_engine.effective_creature_chance(buffs, region["creature_chance"])
        if random.random() < creature_chance:
            creature = creature_engine.maybe_creature_encounter(
                "walking", chance=1.0  # guaranteed encounter; rarity rolled inside
            )
            if creature:
                result["creature_reward"] = creature

        # ── Flavor text ──────────────────────────────────────────────────────
        lines = random.sample(_VICTORY_LINES, min(2, len(_VICTORY_LINES)))
        lines.append(
            f"Army strength {army_str:.0f} overcame difficulty {region['difficulty']}."
        )
        lines.append(f"⚔️ +{earned:.0f} drachmae from the campaign.")
        if result["relic_reward"]:
            lines.append(f"⚗️ A relic was discovered: {result['relic_reward']['name']}.")
        if result["creature_reward"]:
            lines.append(
                f"🐾 A {result['creature_reward']['name']} emerges from the wilderness."
            )
        result["lines"] = lines

    else:
        # ── Unit losses ──────────────────────────────────────────────────────
        n_lost   = min(len(state.army), random.randint(1, 3))
        lost_ids = random.sample(list(state.army), n_lost)
        for uid in lost_ids:
            state.army.remove(uid)
        units_lost_names = [
            _UNIT_MAP.get(uid, {}).get("name", uid) for uid in lost_ids
        ]
        result["units_lost"] = units_lost_names

        # ── Flavor text ──────────────────────────────────────────────────────
        lines = random.sample(_DEFEAT_LINES, min(2, len(_DEFEAT_LINES)))
        lines.append(
            f"Army strength {army_str:.0f} fell short of difficulty {region['difficulty']}."
        )
        lines.append(f"Units lost: {', '.join(units_lost_names)}.")
        result["lines"] = lines

    return result


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def get_all_units() -> List[dict]:
    """Return all unit definitions with enriched display fields."""
    return [_enrich_unit(u) for u in _UNITS]


def get_army_details(state: PlayerState) -> List[dict]:
    """
    Return the current army as a collapsed list (one entry per unit type,
    with count and total_strength fields added).
    """
    counts = Counter(state.army)
    details = []
    for unit_id, count in counts.items():
        if unit_id in _UNIT_MAP:
            enriched = _enrich_unit(_UNIT_MAP[unit_id])
            enriched["count"]          = count
            enriched["total_strength"] = _UNIT_MAP[unit_id]["strength"] * count
            details.append(enriched)
    return details


def get_all_regions() -> List[dict]:
    """Return all campaign regions (plain data)."""
    return list(_REGIONS)


def _enrich_unit(unit: dict) -> dict:
    """Add display-only fields to a unit dict."""
    uid    = unit.get("id", "")
    rarity = unit.get("rarity", "common")
    return {
        **unit,
        "icon":       UNIT_ICONS.get(uid, "⚔️"),
        "cost_str":   _format_cost(unit.get("cost", {})),
        "rarity_color": RARITY_COLORS.get(rarity, "var(--text)"),
    }


def _format_cost(cost: dict) -> str:
    """Format a cost dict as a human-readable string."""
    parts = []
    if cost.get("drachmae"): parts.append(f"🪙 {cost['drachmae']}")
    if cost.get("grain"):    parts.append(f"🌾 {cost['grain']}")
    if cost.get("wine"):     parts.append(f"🍷 {cost['wine']}")
    if cost.get("olive_oil"): parts.append(f"🫒 {cost['olive_oil']}")
    return " · ".join(parts)
