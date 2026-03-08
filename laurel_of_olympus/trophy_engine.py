"""
trophy_engine.py – Monster trophy inventory and passive buff computation.

Trophies are awarded when a player completes a 6-session microcycle.
Each trophy is permanently kept in the player's inventory and provides a
passive bonus that stacks additively across all trophies of the same type.

All trophy definitions are loaded from data/trophies.json.

Public API:
  award_trophy(state, monster_id) -> dict | None
      Add the trophy matching monster_id to the player's inventory.
      Multiple copies are allowed (defeating the same monster again stacks
      its bonus).  Returns the enriched trophy dict, or None if not found.

  get_trophy_buffs(state) -> dict
      Sum all additive bonus_values by bonus_type across the full inventory.
      Returns a flat dict of {bonus_type: total_value}.
      Example: two Satyrs trophies (drachmae_gain +0.03 each) → {"drachmae_gain": 0.06}

  get_trophy_inventory(state) -> list[dict]
      Return enriched dicts for every trophy in the player's inventory
      (one entry per copy earned).

  get_all_trophies() -> list[dict]
      Return all trophy definitions with enriched display fields.

  describe_buff(bonus_type, bonus_value) -> str
      Human-readable label for a trophy bonus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from laurel_of_olympus.game_state import PlayerState

# ---------------------------------------------------------------------------
# Load data file once at import time
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent / "data"
_RAW: dict = json.loads((_DATA_DIR / "trophies.json").read_text())
_TROPHIES: List[dict] = _RAW["trophies"]
_TROPHY_MAP: Dict[str, dict] = {t["id"]: t for t in _TROPHIES}

RARITY_ICONS = {
    "common":    "🌿",
    "rare":      "⚡",
    "epic":      "🔥",
    "legendary": "✨",
}


# ---------------------------------------------------------------------------
# Award
# ---------------------------------------------------------------------------

def award_trophy(state: PlayerState, monster_id: str) -> Optional[dict]:
    """
    Add the trophy for monster_id to the player's inventory.

    Duplicates are allowed — each copy contributes its bonus independently.
    Returns the enriched trophy dict, or None if monster_id has no trophy entry.
    """
    trophy = _TROPHY_MAP.get(monster_id)
    if trophy is None:
        return None
    state.trophies.append(monster_id)
    return _enrich(trophy)


# ---------------------------------------------------------------------------
# Buff computation
# ---------------------------------------------------------------------------

def get_trophy_buffs(state: PlayerState) -> dict:
    """
    Accumulate all trophy bonuses additively by bonus_type.

    Returns a flat dict, e.g.:
        {"drachmae_gain": 0.09, "farm_production": 0.03, "relic_chance": 0.07}

    Bonus types returned:
        drachmae_gain      – all-workout drachmae boost
        strength_rewards   – strength-specific drachmae boost
        farm_production    – farm output boost
        creature_chance    – creature encounter spawn bonus
        campaign_strength  – army strength boost
        relic_chance       – campaign relic-drop chance bonus
    """
    totals: dict = {}
    for trophy_id in state.trophies:
        trophy = _TROPHY_MAP.get(trophy_id)
        if not trophy:
            continue
        btype = trophy.get("bonus_type", "")
        bval  = float(trophy.get("bonus_value", 0.0))
        if btype:
            totals[btype] = totals.get(btype, 0.0) + bval
    return totals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_trophy_inventory(state: PlayerState) -> List[dict]:
    """Return enriched dicts for every trophy in the player's inventory."""
    return [_enrich(_TROPHY_MAP[tid]) for tid in state.trophies if tid in _TROPHY_MAP]


def get_all_trophies() -> List[dict]:
    """Return all trophy definitions with enriched display fields."""
    return [_enrich(t) for t in _TROPHIES]


def _enrich(trophy: dict) -> dict:
    rarity     = trophy.get("rarity", "common")
    bonus_type = trophy.get("bonus_type", "")
    bonus_value = float(trophy.get("bonus_value", 0.0))
    return {
        **trophy,
        "icon":        RARITY_ICONS.get(rarity, "🏆"),
        "bonus_label": describe_buff(bonus_type, bonus_value),
    }


def describe_buff(bonus_type: str, bonus_value: float) -> str:
    """Return a short human-readable buff description."""
    pct = round(bonus_value * 100)
    labels = {
        "drachmae_gain":     f"+{pct}% all drachmae",
        "strength_rewards":  f"+{pct}% strength drachmae",
        "farm_production":   f"+{pct}% farm production",
        "creature_chance":   f"+{pct}% creature encounter chance",
        "campaign_strength": f"+{pct}% army strength",
        "relic_chance":      f"+{pct}% relic drop chance",
    }
    return labels.get(bonus_type, f"+{pct}% passive bonus")
