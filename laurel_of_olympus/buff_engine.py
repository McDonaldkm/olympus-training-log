"""
buff_engine.py – Aggregate passive buffs from Sanctuary creatures, Relics, and Trophies.

This module is the single source of truth for the player's current combined
passive bonuses.  Both farm_engine and workout_engine receive the merged buffs
dict so they can scale their outputs accordingly.

Public API:
  get_all_buffs(state) -> dict
      Merge creature (sanctuary), relic, and trophy buffs into one dict.
      Creature/relic multipliers are combined multiplicatively.
      Trophy bonuses stack additively then are applied as a single multiplier.

  apply_farm_buff(buffs, farm_type, base_amount) -> int
      Apply the relevant farm multiplier to a raw production amount.

  apply_workout_buff(buffs, workout_type, base_reward) -> float
      Apply the relevant workout multiplier to a raw drachmae reward.

  effective_event_chance(buffs, base_chance) -> float
      Return the general event probability after adding any event_chance bonus.

  effective_creature_chance(buffs, base_chance) -> float
      Return the creature-spawn probability, combining event_chance and
      creature_encounter_chance (trophy) bonuses.

  effective_relic_chance(buffs, base_chance) -> float
      Return the relic-drop probability after adding relic_drop_chance bonus.
"""

from __future__ import annotations

from laurel_of_olympus.game_state import PlayerState
from laurel_of_olympus import creature_engine, relic_engine, trophy_engine


def get_all_buffs(state: PlayerState) -> dict:
    """
    Merge sanctuary creature buffs, relic buffs, and trophy buffs.

    Creature + relic keys:
      For multiplier keys: buffs multiply together.
      For additive keys ("event_chance", "laurel_bonus"): values sum.

    Trophy keys (additive percentage totals from trophy_engine):
      drachmae_gain      -> workout_all      (multiplicative on top)
      strength_rewards   -> workout_strength (multiplicative on top)
      farm_production    -> all_farms        (multiplicative on top)
      campaign_strength  -> army_strength    (multiplicative on top)
      creature_chance    -> creature_encounter_chance (additive)
      relic_chance       -> relic_drop_chance         (additive)
    """
    c_buffs = creature_engine.get_sanctuary_buffs(state)
    r_buffs = relic_engine.get_relic_buffs(state)
    t_buffs = trophy_engine.get_trophy_buffs(state)

    # Merge creature + relic buffs (existing logic)
    merged: dict = dict(c_buffs)
    for key, val in r_buffs.items():
        if key in ("event_chance", "laurel_bonus"):
            merged[key] = merged.get(key, 0) + val
        else:
            merged[key] = merged.get(key, 1.0) * val

    # Apply trophy buffs on top (additive stacking -> single multiplier)
    if t_buffs.get("drachmae_gain", 0.0):
        merged["workout_all"] = merged.get("workout_all", 1.0) * (1.0 + t_buffs["drachmae_gain"])

    if t_buffs.get("strength_rewards", 0.0):
        merged["workout_strength"] = merged.get("workout_strength", 1.0) * (1.0 + t_buffs["strength_rewards"])

    if t_buffs.get("farm_production", 0.0):
        merged["all_farms"] = merged.get("all_farms", 1.0) * (1.0 + t_buffs["farm_production"])

    if t_buffs.get("campaign_strength", 0.0):
        merged["army_strength"] = merged.get("army_strength", 1.0) * (1.0 + t_buffs["campaign_strength"])

    # Additive chance bonuses (separate keys so callers can use them explicitly)
    merged["creature_encounter_chance"] = t_buffs.get("creature_chance", 0.0)
    merged["relic_drop_chance"]         = t_buffs.get("relic_chance", 0.0)

    return merged


def apply_farm_buff(buffs: dict, farm_type: str, base_amount: int) -> int:
    """
    Scale farm production by specific-farm and all-farm multipliers.
    Always returns at least 1 if base_amount > 0.
    """
    specific = buffs.get(f"farm_{farm_type}", 1.0)
    all_farm = buffs.get("all_farms", 1.0)
    result   = base_amount * specific * all_farm
    return max(base_amount, round(result)) if base_amount > 0 else 0


def apply_workout_buff(buffs: dict, workout_type: str, base_reward: float) -> float:
    """
    Scale a workout drachmae reward by the relevant workout multiplier.

    Applies both the type-specific multiplier (e.g. "workout_running") and the
    all-workout multiplier ("workout_all") from drachmae_gain / all_rewards buffs.
    Both are combined multiplicatively.
    """
    type_mult = buffs.get(f"workout_{workout_type}", 1.0)
    all_mult  = buffs.get("workout_all", 1.0)
    return round(base_reward * type_mult * all_mult, 2)


def effective_event_chance(buffs: dict, base_chance: float) -> float:
    """Add any event_chance bonus from relics/creatures to the base probability."""
    return min(1.0, base_chance + buffs.get("event_chance", 0.0))


def effective_creature_chance(buffs: dict, base_chance: float) -> float:
    """
    Combine general event_chance and trophy creature_encounter_chance bonuses
    with the base spawn probability.
    """
    bonus = buffs.get("event_chance", 0.0) + buffs.get("creature_encounter_chance", 0.0)
    return min(1.0, base_chance + bonus)


def effective_relic_chance(buffs: dict, base_chance: float) -> float:
    """Add relic_drop_chance trophy bonus to the base relic-drop probability."""
    return min(1.0, base_chance + buffs.get("relic_drop_chance", 0.0))
