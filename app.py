from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import json, core, datetime as dt
from laurel_of_olympus import game_state as gs
from laurel_of_olympus import workout_engine, farm_engine, event_engine
from laurel_of_olympus import oracle_engine, title_engine
from laurel_of_olympus import creature_engine, relic_engine, buff_engine
from laurel_of_olympus import army_engine, trophy_engine

BASE   = Path(__file__).parent
DATA   = BASE / "data.json"
STATIC = BASE / "static"

# ---------- file helpers ----------
def _load() -> dict:
    if DATA.exists():
        d = json.loads(DATA.read_text())
        # ── migrate: backfill fields added in later versions ──
        d.setdefault("total_ruck_miles",
                     sum(r.get("distance_miles", 0)
                         for r in d.get("ruck_log", [])
                         if isinstance(r, dict)))
        d.setdefault("total_run_miles",
                     sum(r.get("distance_miles", 0)
                         for r in d.get("run_log", [])
                         if isinstance(r, dict)))
        d.setdefault("walk_log", [])
        d.setdefault("total_walk_miles",
                     sum(r.get("distance_miles", 0)
                         for r in d.get("walk_log", [])
                         if isinstance(r, dict)))
        d.setdefault("run_log", [])
        d.setdefault("week_log", {})
        # journey_miles = combined ruck + run + walk
        d.setdefault("journey_miles",
                     d["total_ruck_miles"] + d["total_run_miles"] + d["total_walk_miles"])
        mc = d.setdefault("microcycle", {})
        mc.setdefault("start_date",         str(dt.date.today()))
        mc.setdefault("badge_given",         False)
        mc.setdefault("id",                  0)
        mc.setdefault("sessions_completed",  0)
        # purge corrupted list entries
        d["ruck_log"] = [r for r in d.get("ruck_log", []) if isinstance(r, dict)]
        d["run_log"]  = [r for r in d.get("run_log",  []) if isinstance(r, dict)]
        d.setdefault("custom_tracks", [])
        return d
    d = core.default_state()
    DATA.write_text(json.dumps(d, indent=2))
    return d

def _save(d: dict) -> None:
    DATA.write_text(json.dumps(d, indent=2))

# ---------- FastAPI ----------
app = FastAPI(title="Olympus Training Log API")

# ──  root / PWA ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html")

@app.get("/static/{path:path}")
def statics(path: str):
    file_path = STATIC / path
    if not file_path.exists():
        raise HTTPException(404)
    resp = FileResponse(file_path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

@app.get("/img/{path:path}")
def images(path: str):
    """Serve monster art, ruck postcards, and other project images."""
    file_path = BASE / path
    if not file_path.exists():
        raise HTTPException(404)
    return FileResponse(file_path)

# ──  read-only JSON API ────────────────────────────────────────────────────────
@app.get("/api/state")
def get_state():
    return _load()

@app.get("/api/workout/today")
def get_today():
    return core.get_today_workout(_load())

@app.get("/api/movements")
def get_movements():
    """Return the full movement registry for the cycle builder."""
    return core.get_movements()

@app.get("/api/tracks")
def get_tracks():
    state  = _load()
    tracks = {k: v["name"] for k, v in core.TEMPLATES.items()}
    # Append user-built custom tracks
    for ct in state.get("custom_tracks", []):
        n = len(ct.get("sessions", []))
        tracks[f"custom_{ct['id']}"] = f"⚒ {ct['name']} ({n} sessions)"
    return tracks

@app.get("/api/tracks/{key}")
def get_track_detail(key: str):
    """Return full track data (all sessions) for the preview modal."""
    if key.startswith("custom_"):
        state    = _load()
        track_id = key[7:]
        detail   = core.get_custom_track_detail(state, track_id)
        if detail is None:
            raise HTTPException(404, f"Custom track not found: {key}")
        return {"key": key, "name": detail["name"], "sessions": detail["sessions"]}
    detail = core.get_track_detail(key)
    if detail is None:
        raise HTTPException(404, f"Unknown track: {key}")
    return detail

# ──  mutating endpoints ────────────────────────────────────────────────────────
@app.post("/api/track/select")
async def select_track(req: Request):
    payload = await req.json()
    key = payload.get("key", "").strip()
    # Validate: must be a built-in template or an existing custom track
    if not key.startswith("custom_") and key not in core.TEMPLATES:
        raise HTTPException(400, f"Unknown track: {key}")
    state = _load()
    if key.startswith("custom_"):
        track_id = key[7:]
        if core.get_custom_track_detail(state, track_id) is None:
            raise HTTPException(404, f"Custom track not found: {key}")
    msg = core.init_track(state, key)
    _save(state)
    return {"status": "ok", "msg": msg, "state": state}

def _maybe_award_trophy(kb_state: dict) -> dict | None:
    """
    If the kettlebell microcycle just completed (badge_given is True and the
    newest badge is a monster badge), award the corresponding trophy to the
    estate and return the enriched trophy dict; otherwise return None.
    """
    mc = kb_state.get("microcycle", {})
    if not mc.get("badge_given"):
        return None
    # Find the newest monster badge
    badges = kb_state.get("badges", [])
    for badge in reversed(badges):
        if badge.get("type") == "monster":
            monster_id = badge.get("monster_id")
            if monster_id:
                estate = gs.load(ESTATE_SAVE)
                trophy = trophy_engine.award_trophy(estate, monster_id)
                gs.save(estate, ESTATE_SAVE)
                return trophy
            break
    return None


@app.post("/api/workout/recommended")
async def log_recommended(req: Request):
    weights_lbs = None
    try:
        p = await req.json()
        weights_lbs = p.get("weights_lbs")   # dict: {main, acc_0, acc_1, acc_2, finisher}
    except Exception:
        pass   # body may be absent or non-JSON — that's fine
    state = _load()
    was_badge_given = state["microcycle"].get("badge_given", False)
    msg   = core.log_rec(state, weights_lbs=weights_lbs)
    _save(state)
    trophy = None
    if not was_badge_given:
        trophy = _maybe_award_trophy(state)
    return {"status": "ok", "msg": msg, "state": state, "trophy": trophy}

@app.post("/api/workout/custom")
async def log_custom(req: Request):
    payload = await req.json()
    text    = payload.get("text", "").strip()
    if not text:
        raise HTTPException(400, "Empty workout description")
    state = _load()
    was_badge_given = state["microcycle"].get("badge_given", False)
    msg   = core.log_custom(state, text)
    _save(state)
    trophy = None
    if not was_badge_given:
        trophy = _maybe_award_trophy(state)
    return {"status": "ok", "msg": msg, "state": state, "trophy": trophy}

@app.post("/api/ruck")
async def log_ruck(req: Request):
    p = await req.json()
    try:
        miles  = float(p["miles"])
        pounds = float(p["pounds"])
    except (KeyError, ValueError):
        raise HTTPException(400, "miles and pounds must be numeric")
    if miles <= 0:
        raise HTTPException(400, "miles must be positive")
    state = _load()
    msg   = core.log_ruck(state, miles, pounds)
    _save(state)
    return {"status": "ok", "msg": msg, "state": state}

@app.post("/api/walk")
async def log_walk(req: Request):
    p = await req.json()
    try:
        miles = float(p["miles"])
    except (KeyError, ValueError):
        raise HTTPException(400, "miles must be numeric")
    if miles <= 0:
        raise HTTPException(400, "miles must be positive")
    state = _load()
    msg   = core.log_walk(state, miles)
    _save(state)
    return {"status": "ok", "msg": msg, "state": state}

@app.post("/api/run")
async def log_run(req: Request):
    p = await req.json()
    try:
        miles = float(p["miles"])
    except (KeyError, ValueError):
        raise HTTPException(400, "miles must be numeric")
    if miles <= 0:
        raise HTTPException(400, "miles must be positive")
    pace = p.get("pace_min_per_mile")
    if pace is not None:
        try:
            pace = float(pace)
        except (TypeError, ValueError):
            pace = None
    state = _load()
    msg   = core.log_run(state, miles, pace)
    _save(state)
    return {"status": "ok", "msg": msg, "state": state}

# ──  custom tracks ──────────────────────────────────────────────────────────────

@app.post("/api/tracks/custom")
async def save_custom_track(req: Request):
    """Save a new user-built training cycle."""
    p        = await req.json()
    name     = (p.get("name") or "").strip()
    sessions = p.get("sessions", [])
    if not name:
        raise HTTPException(400, "Track name is required.")
    if not sessions:
        raise HTTPException(400, "At least one session is required.")
    state = _load()
    try:
        track = core.save_custom_track(state, name, sessions)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _save(state)
    return {"status": "ok", "track": track, "state": state}


@app.delete("/api/tracks/custom/{track_id}")
def delete_custom_track(track_id: str):
    """Delete a user-built training cycle by id."""
    state = _load()
    found = core.delete_custom_track(state, track_id)
    if not found:
        raise HTTPException(404, f"Custom track not found: {track_id}")
    _save(state)
    return {"status": "ok", "state": state}

# ── Estate (Laurel of Olympus RPG) ─────────────────────────────────────────────

ESTATE_SAVE = Path.home() / ".laurel_of_olympus.json"

@app.get("/api/estate/state")
def get_estate_state():
    return gs.load(ESTATE_SAVE).to_dict()

@app.post("/api/estate/simulate-workout")
async def estate_simulate_workout(req: Request):
    p = await req.json()
    workout_type = p.get("workout_type", "strength")
    kwargs = {k: v for k, v in p.items() if k != "workout_type"}
    # Provide sensible defaults so the call always succeeds
    if workout_type == "strength" and "volume" not in kwargs:
        kwargs["volume"] = 5000.0
    elif workout_type in ("walking", "running", "rucking") and "miles" not in kwargs:
        kwargs["miles"] = 2.0

    state = gs.load(ESTATE_SAVE)

    # ── Compute passive buffs from sanctuary + relics ────────────────────────
    buffs = buff_engine.get_all_buffs(state)

    events = workout_engine.process_workout(state, workout_type, buffs=buffs, **kwargs)
    farm_events = farm_engine.produce_farms(state, buffs=buffs)
    events.extend(farm_events)

    # ── Title checks (run before event priority chain) ───────────────────────
    newly_unlocked = title_engine.check_and_unlock_titles(state)
    for tid in newly_unlocked:
        events.append(f"  🏅 Title unlocked: {tid.replace('_', ' ').title()}")

    # ── Creature encounter (outdoor workouts only, 5% base) ──────────────────
    encounter_chance = buff_engine.effective_creature_chance(buffs, 0.05)
    creature_encounter = creature_engine.maybe_creature_encounter(
        workout_type, chance=encounter_chance
    )

    # ── Event priority chain (only one popup per workout) ────────────────────
    # 1. Ultra-rare: Kassandra Breaks Composure (0.1%, phase ≥ 4)
    narrative_event = oracle_engine.maybe_kassandra_break(state, chance=0.001)
    if narrative_event:
        # Kassandra break also unlocks "favorite_of_kassandra"
        if "favorite_of_kassandra" not in state.titles_unlocked:
            state.titles_unlocked.append("favorite_of_kassandra")
            state.active_titles["legendary"] = "favorite_of_kassandra"
            events.append("  🌟 Title unlocked: Favorite of Kassandra")
    else:
        # 2. Oracle visit (10%)
        narrative_event = oracle_engine.maybe_oracle_visit(state, chance=0.10)
        if narrative_event is None:
            # 3. Regular flavour event — base 20% + event_chance buff
            flavour_chance = buff_engine.effective_event_chance(buffs, 0.20)
            narrative_event = event_engine.maybe_trigger_event(
                state.to_dict(), chance=flavour_chance
            )

    gs.save(state, ESTATE_SAVE)
    return {
        "status":             "ok",
        "events":             events,
        "state":              state.to_dict(),
        "event":              narrative_event,       # None or event dict
        "creature_encounter": creature_encounter,    # None or creature dict
    }


@app.get("/api/estate/prophecy")
def get_prophecy_scroll():
    """Return the full Prophecy Scroll payload (titles + oracle phase + combined title)."""
    state = gs.load(ESTATE_SAVE)
    scroll = title_engine.get_prophecy_scroll(state)
    gs.save(state, ESTATE_SAVE)  # persist any newly unlocked titles
    return scroll


# ── Creature / Sanctuary endpoints ─────────────────────────────────────────────

@app.get("/api/estate/sanctuary")
def get_sanctuary():
    """Return sanctuary contents and all creature definitions."""
    state = gs.load(ESTATE_SAVE)
    return {
        "sanctuary":          creature_engine.get_sanctuary_details(state),
        "capacity":           state.sanctuary_capacity,
        "sanctuary_ids":      state.sanctuary,
        "all_creatures":      creature_engine.get_all_creatures(),
        "buffs":              creature_engine.get_sanctuary_buffs(state),
    }


@app.post("/api/estate/creature/recruit")
async def recruit_creature(req: Request):
    p = await req.json()
    creature_id = p.get("creature_id", "").strip()
    if not creature_id:
        raise HTTPException(400, "creature_id is required")
    state = gs.load(ESTATE_SAVE)
    ok, msg = creature_engine.recruit_creature(state, creature_id)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "state": state.to_dict()}


@app.post("/api/estate/creature/release")
async def release_creature(req: Request):
    p = await req.json()
    creature_id = p.get("creature_id", "").strip()
    if not creature_id:
        raise HTTPException(400, "creature_id is required")
    state = gs.load(ESTATE_SAVE)
    ok, msg, reward = creature_engine.release_creature(state, creature_id)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "reward": reward, "state": state.to_dict()}


# ── Relic endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/estate/relics")
def get_relics():
    """Return relic inventory and all relic definitions."""
    state = gs.load(ESTATE_SAVE)
    return {
        "inventory":     relic_engine.get_inventory_details(state),
        "capacity":      state.relic_capacity,
        "relic_ids":     state.relics,
        "all_relics":    relic_engine.get_all_relics(),
        "buffs":         relic_engine.get_relic_buffs(state),
    }


@app.post("/api/estate/relic/add")
async def add_relic(req: Request):
    p = await req.json()
    relic_id = p.get("relic_id", "").strip()
    if not relic_id:
        raise HTTPException(400, "relic_id is required")
    state = gs.load(ESTATE_SAVE)
    ok, msg = relic_engine.add_relic(state, relic_id)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "state": state.to_dict()}


@app.post("/api/estate/relic/remove")
async def remove_relic(req: Request):
    p = await req.json()
    relic_id = p.get("relic_id", "").strip()
    if not relic_id:
        raise HTTPException(400, "relic_id is required")
    state = gs.load(ESTATE_SAVE)
    ok, msg = relic_engine.remove_relic(state, relic_id)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "state": state.to_dict()}

# ── Trophy endpoints ────────────────────────────────────────────────────────

@app.get("/api/estate/trophies")
def get_trophies():
    """Return trophy inventory, all trophy definitions, and stacked buff totals."""
    state = gs.load(ESTATE_SAVE)
    t_buffs = trophy_engine.get_trophy_buffs(state)
    buff_labels = {
        btype: trophy_engine.describe_buff(btype, bval)
        for btype, bval in t_buffs.items()
    }
    return {
        "inventory":    trophy_engine.get_trophy_inventory(state),
        "trophy_ids":   state.trophies,
        "all_trophies": trophy_engine.get_all_trophies(),
        "buffs":        t_buffs,
        "buff_labels":  buff_labels,
    }


# ── Army / Barracks endpoints ───────────────────────────────────────────────────

@app.get("/api/estate/army")
def get_army():
    """Return army details, all unit defs, all regions, barracks status, strength."""
    state = gs.load(ESTATE_SAVE)
    buffs = buff_engine.get_all_buffs(state)
    return {
        "barracks_built": state.barracks_built,
        "barracks_cost":  army_engine.BARRACKS_COST,
        "army":           army_engine.get_army_details(state),
        "army_ids":       state.army,
        "army_limit":     state.army_limit,
        "army_strength":  army_engine.get_army_strength(state, buffs),
        "campaigns_won":  state.campaigns_won,
        "all_units":      army_engine.get_all_units(),
        "all_regions":    army_engine.get_all_regions(),
        "buffs":          buffs,
    }


@app.post("/api/estate/barracks/build")
async def build_barracks(req: Request):
    state = gs.load(ESTATE_SAVE)
    ok, msg = army_engine.build_barracks(state)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "state": state.to_dict()}


@app.post("/api/estate/army/recruit")
async def recruit_unit(req: Request):
    p = await req.json()
    unit_id = p.get("unit_id", "").strip()
    if not unit_id:
        raise HTTPException(400, "unit_id is required")
    state = gs.load(ESTATE_SAVE)
    ok, msg = army_engine.recruit_unit(state, unit_id)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "state": state.to_dict()}


@app.post("/api/estate/army/disband")
async def disband_unit(req: Request):
    p = await req.json()
    unit_id = p.get("unit_id", "").strip()
    if not unit_id:
        raise HTTPException(400, "unit_id is required")
    state = gs.load(ESTATE_SAVE)
    ok, msg = army_engine.disband_unit(state, unit_id)
    if not ok:
        raise HTTPException(400, msg)
    gs.save(state, ESTATE_SAVE)
    return {"status": "ok", "msg": msg, "state": state.to_dict()}


@app.post("/api/estate/campaign/launch")
async def launch_campaign(req: Request):
    p = await req.json()
    region_id = p.get("region_id", "").strip()
    if not region_id:
        raise HTTPException(400, "region_id is required")

    state = gs.load(ESTATE_SAVE)
    buffs = buff_engine.get_all_buffs(state)

    result = army_engine.launch_campaign(state, region_id, buffs=buffs)

    # If engine returned an error string, propagate as 400
    if "error" in result:
        raise HTTPException(400, result["error"])

    # Auto-add relic reward to inventory if found and space available
    if result.get("relic_reward"):
        relic_id = result["relic_reward"]["id"]
        ok_relic, _ = relic_engine.add_relic(state, relic_id)
        if not ok_relic:
            # Inventory full — mark relic as not added so frontend can inform player
            result["relic_reward"]["not_added"] = True

    # Award champion_of_the_gods title if 20 campaigns won
    if (
        state.campaigns_won >= 20
        and "champion_of_the_gods" not in state.titles_unlocked
    ):
        state.titles_unlocked.append("champion_of_the_gods")
        state.active_titles["legendary"] = "champion_of_the_gods"
        result["title_unlocked"] = "Champion of the Gods"

    gs.save(state, ESTATE_SAVE)

    # creature_reward (if any) is returned to the frontend as an encounter dict;
    # the frontend shows the encounter dialog so the player can recruit or release.
    return {
        "status":           "ok",
        "result":           result,
        "creature_encounter": result.get("creature_reward"),
        "state":            state.to_dict(),
    }
