"""
game_state.py – PlayerState dataclass and JSON save/load.

All mutable game data lives here. The engines (workout_engine, farm_engine)
accept a PlayerState and mutate it in place, then the caller saves.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any

SAVE_PATH = Path.home() / ".laurel_of_olympus.json"


# ---------------------------------------------------------------------------
# Sub-structures stored as plain dicts inside PlayerState
# ---------------------------------------------------------------------------

def _default_farm(farm_type: str, level: int = 1, col: int = 0, row: int = 0) -> Dict:
    return {"farm_type": farm_type, "level": level, "col": col, "row": row}


def _default_workout_entry(
    workout_type: str,
    drachmae_earned: float,
    date: str,
    params: Dict,
) -> Dict:
    return {
        "date": date,
        "workout_type": workout_type,
        "drachmae_earned": drachmae_earned,
        "params": params,
    }


# ---------------------------------------------------------------------------
# PlayerState
# ---------------------------------------------------------------------------

@dataclass
class PlayerState:
    # ── Currency ────────────────────────────────────────────────────────────
    drachmae: float = 0.0
    laurels: int = 0

    # ── Raw resources ────────────────────────────────────────────────────────
    grain: int = 0
    grapes: int = 0
    olives: int = 0
    honey: int = 0
    herbs: int = 0

    # ── Refined goods (processed by buildings) ───────────────────────────────
    wine: int = 0
    bread: int = 0
    olive_oil: int = 0
    mead: int = 0

    # ── Estate: list of farm dicts {"farm_type", "level", "col", "row"} ─────
    farms: List[Dict] = field(default_factory=list)

    # ── Farm production tracking ─────────────────────────────────────────────
    last_farm_date: str = ""   # ISO date of last farm production trigger

    # ── Workout tracking for diminishing-returns within one day ─────────────
    last_workout_date: str = ""
    workouts_today: int = 0

    # ── Workout counts per type (for title progress) ─────────────────────────
    workout_counts: Dict[str, int] = field(default_factory=lambda: {
        "walking": 0, "running": 0, "rucking": 0, "strength": 0
    })

    # ── Full workout history ─────────────────────────────────────────────────
    workout_log: List[Dict] = field(default_factory=list)

    # ── Laurel tracking ──────────────────────────────────────────────────────
    # Each entry: {"start": ISO, "workouts": [...dates...]}
    # A new window opens every 14 days; ≥6 workouts → laurel
    laurel_windows: List[Dict] = field(default_factory=list)

    # ── Earned titles by category ────────────────────────────────────────────
    active_titles: Dict[str, str] = field(default_factory=dict)

    # ── All unlocked title IDs (full history) ────────────────────────────────
    titles_unlocked: List[str] = field(default_factory=list)

    # ── Oracle relationship ──────────────────────────────────────────────────
    oracle_phase: int = 0    # 0=stranger … 5=Kassandra ally
    oracle_visits: int = 0   # total oracle visits (drives phase advancement)

    # ── Sanctuary (recruited creatures) ──────────────────────────────────────
    sanctuary: List[str] = field(default_factory=list)   # creature IDs
    sanctuary_capacity: int = 3

    # ── Relic inventory ──────────────────────────────────────────────────────
    relics: List[str] = field(default_factory=list)      # relic IDs
    relic_capacity: int = 10

    # ── Army (Barracks + Campaign) ────────────────────────────────────────────
    barracks_built: bool = False
    army: List[str] = field(default_factory=list)        # unit IDs (duplicates allowed)
    army_limit: int = 10
    campaigns_won: int = 0

    # ── Monster Trophies (awarded on 6-session microcycle completion) ─────────
    trophies: List[str] = field(default_factory=list)    # monster IDs (duplicates allowed)

    # ── Version for future migrations ────────────────────────────────────────
    version: int = 1

    # ── Helpers ──────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlayerState":
        """Reconstruct from a plain dict, ignoring unknown keys gracefully."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in known}
        state = cls(**filtered)
        return state

    # Convenience properties for UI display
    @property
    def total_workouts(self) -> int:
        return sum(self.workout_counts.values())

    @property
    def farms_built(self) -> int:
        return len(self.farms)

    @property
    def unique_farm_types(self) -> set:
        return {f["farm_type"] for f in self.farms}


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

def save(state: PlayerState, path: Path = SAVE_PATH) -> None:
    path.write_text(json.dumps(state.to_dict(), indent=2))


def load(path: Path = SAVE_PATH) -> PlayerState:
    if not path.exists():
        return PlayerState()
    try:
        raw = json.loads(path.read_text())
        return PlayerState.from_dict(raw)
    except Exception:
        # Corrupt save – return fresh state rather than crash
        return PlayerState()


def new_game() -> PlayerState:
    """Return a fresh PlayerState with starter farms placed on the grid."""
    state = PlayerState(drachmae=0.0)
    # No starter farms – player builds them with earned drachmae
    return state
