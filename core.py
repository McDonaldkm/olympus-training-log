"""
core.py – pure-Python logic for Olympus Training PWA
NO disk I/O, NO FastAPI; stateless functions that take `state: dict` and mutate it.
"""

import datetime as dt
import random
import time

# ── Monster table (weighted probabilities) ────────────────────────────────────
MONSTERS = [
    # (display_name,                 folder_name,           probability %)
    ("Satyrs & Woodland Imps",       "Saytr",               10.00),
    ("Karkinos (Giant Crab)",        "Karkinos",            10.00),
    ("Harpies",                      "Harpies",             10.00),
    ("Sirens",                       "Sirens",              10.00),
    ("Calydonian Boar",              "Calydonin_Boar",      10.00),
    ("Stymphalian Birds",            "Stymphalian_Birds",    5.00),
    ("The Sphinx",                   "Sphinx",               5.00),
    ("Minotaur",                     "Minotaur",             5.00),
    ("Polyphemus (Cyclops)",         "Polyphemus",           5.00),
    ("Orthrus (Two-Headed Dog)",     "Orthrus",              5.00),
    ("Medusa",                       "Medusa",               3.00),
    ("Mares of Diomedes",            "Mares_of_Diomedes",    3.00),
    ("Nemean Lion",                  "Nemean_Lion",          3.00),
    ("Colchian Dragon",              "Colchian_Dragon",      3.00),
    ("Lernaean Hydra",               "Lernaean_Hydra",       3.00),
    ("Geryon",                       "Geryon",               1.40),
    ("Chimera",                      "Chimera",              1.40),
    ("Talos",                        "Talos",                1.40),
    ("Cerberus",                     "Cerberus",             1.40),
    ("Gigantes",                     "Gigantes",             1.40),
    ("Scylla & Charybdis",           "Scylla_&_Charybdis",  0.75),
    ("Echidna",                      "Echidna",              0.75),
    ("Hecatoncheires",               "Hecatoncheires",       0.75),
    ("Typhon",                       "Typhon",               0.75),
]
MONSTER_TOTAL = sum(p for _, _, p in MONSTERS)   # 100.0
GILD_CHANCE   = 0.10   # 10 % chance the badge is the "Gold" variant

OLYMPIANS = [
    ("Zeus", "⚡"), ("Hera", "👑"), ("Athena", "🦉"), ("Ares", "🛡️"),
    ("Apollo", "☀️"), ("Artemis", "🏹"), ("Hermes", "🪽"), ("Demeter", "🌾"),
    ("Poseidon", "🌊"), ("Hades", "🖤"),
]

# ── Pheidippides Journey milestones (shared by rucking, running AND walking) ──
# Ruck miles + run miles + walk miles combine into a single journey total.
RUCK_STOPS = [
    (0,   "Acropolis",
     "\"Welcome to leg-day on hard mode!\" Athena's owl hoots, 'Hoot luck, buddy.'"),
    (12,  "Eleusis",
     "Demeter offers carbs—then turns bread into a kettlebell."),
    (26,  "Megara",
     "Heracles flexes and asks you to carry his lion skin too."),
    (48,  "Corinth",
     "Pegasus brags about 'flying the route'. You call him a hoverboard."),
    (75,  "Nemea",
     "Retired Nemean Lion still judges your squat depth."),
    (99,  "Tegea",
     "Atalanta rolls golden apples—you're too tired to bend."),
    (153, "Sparta",
     "Spartan mom: 'Come back with your ruck… or get roasted.'"),
    (206, "Mantinea",
     "Artemis fires a warning arrow—your shuffle scares turtles."),
    (224, "Argos",
     "Hera's all-seeing cam logs your pothole side-step as 'cowardice'."),
    (249, "Epidaurus",
     "Asclepius offers magic salve—if you pronounce his name right."),
    (286, "Sounion",
     "Poseidon: 'Try rucking underwater next time!'"),
    (306, "Athens Return",
     "Nike crowns you, whispers 'Drop the pack before gravity charges fees.'"),
]
TRIP_MILES = RUCK_STOPS[-1][0]   # 306

# ── Drachma for lifting ────────────────────────────────────────────────────────
# Base coins awarded per recommended session (at the standard bell weight).
# Scales linearly with the bell weight used vs the session's standard (std_kg),
# clamped to 0.5×–2.0× the base.  Custom workouts earn a flat 3 coins.
BASE_WORKOUT_COINS  = 5.0
CUSTOM_WORKOUT_COINS = 3.0

# ── Training templates ────────────────────────────────────────────────────────
# std_kg = conventional female kettlebell standard for the main movement
# (per bell for bilateral movements such as double-KB front squat / deadlift).
TEMPLATES = {
    "hermes_power_forge": {
        "name": "Hermes' Power Forge (2-week / 6 sessions)",
        "sessions": [
            {   # Wk-1 Day-1  Lower Push
                "main":     "Double-KB Front Squat 5×5 @ RPE 7",
                "std_kg":   12,
                "accessory": [
                    "Bulgarian Split Squat 3×8 /leg",
                    "TRX Row 3×10",
                    "20-lb-vest Glute-Bridge March 3×40 s",
                ],
                "finisher": "30 s Goblet-Squat Pulse / 30 s rest × 4",
            },
            {   # Wk-1 Day-2  Upper
                "main":     "Single-Arm Clean + Press 5×5 /side",
                "std_kg":   12,
                "accessory": [
                    "Single-KB Floor Press 3×10 /side",
                    "Bent-Over Row 3×8 /side",
                    "TRX Face-Pull + Y-Raise superset 3×12 each",
                ],
                "finisher": "KB Hollow-Body OH Hold 20 s on / 10 s off × 4",
            },
            {   # Wk-1 Day-3  Lower Hinge
                "main":     "Double-KB Deadlift 6×6 @ RPE 7",
                "std_kg":   16,
                "accessory": [
                    "Alternating KB Swing EMOM 8 (12 reps)",
                    "TRX Hamstring Curl 3×15",
                    "Suitcase Carry 4×20 m /side",
                ],
                "finisher": "20-lb-vest Step-Ups 30 s / 15 s × 5",
            },
            {   # Wk-2 Day-1  Lower Push Progression
                "main":     "Double-KB Front Squat 6×4 (↑ load)",
                "std_kg":   16,
                "accessory": [
                    "Goblet Box-Squat Pulse 3×12",
                    "TRX Single-Leg Hip Thrust 3×10 /leg",
                    "Front-Rack Squat-Hold 3×30 s",
                ],
                "finisher": "Tabata Alternating Swings (4 min)",
            },
            {   # Wk-2 Day-2  Upper Progression
                "main":     "Clean + Push-Press Ladder (1-2-3-2-1) × 3",
                "std_kg":   12,
                "accessory": [
                    "Renegade Row 3×8 /side",
                    "TRX Atomic Push-Up 3×10",
                    "KB Windmill 3×6 /side",
                ],
                "finisher": "Farmer-Carry March 45 s / 15 s × 4",
            },
            {   # Wk-2 Day-3  Lower Hinge Progression
                "main":     "Tempo KB RDL (3-s eccentric) 4×8",
                "std_kg":   16,
                "accessory": [
                    "High Pull EMOM 10 (6 /side)",
                    "Weighted Step-Up 3×12 /leg",
                    "Plank Pull-Through 3×30 s",
                ],
                "finisher": "Swing-Sprint: 10 Swings + 50 m run × 5",
            },
        ],
    },

    "ares_battle_conditioning": {
        "name": "Ares' Battle Conditioning (2-week / 6 sessions)",
        "sessions": [
            {   # Wk-1 Day-1  Swing Power
                "main":     "KB Swing EMOM 20 min (15 reps/min)",
                "std_kg":   16,
                "accessory": [
                    "Goblet Squat 3×12",
                    "Push-Up 3×15",
                    "Dead Bug 3×10 /side",
                ],
                "finisher": "30 Swings every minute on the minute × 5",
            },
            {   # Wk-1 Day-2  Clean & Press Complex
                "main":     "KB Clean + Press Complex 5×(5+5) /side",
                "std_kg":   12,
                "accessory": [
                    "Bent-Over Row 3×10 /side",
                    "Lateral Lunge 3×8 /side",
                    "Hollow-Body Rock 3×20",
                ],
                "finisher": "5 Cleans + 5 Presses + 5 Squats /side × 3 (no rest)",
            },
            {   # Wk-1 Day-3  Snatch Intervals
                "main":     "KB Snatch Intervals 8 × 1 min (max reps, switch at will)",
                "std_kg":   12,
                "accessory": [
                    "Hip Hinge Drill 3×10",
                    "TRX Row 3×12",
                    "Pallof Press 3×10 /side",
                ],
                "finisher": "100 Snatches for time (any split)",
            },
            {   # Wk-2 Day-1  Swing Ladder
                "main":     "Double-KB Swing Ladder: 5-10-15-10-5 (rest = set time) × 3",
                "std_kg":   16,
                "accessory": [
                    "Goblet Squat 4×10 (heavier)",
                    "Single-Leg Deadlift 3×8 /side",
                    "Plank 3×45 s",
                ],
                "finisher": "200 Swings for time",
            },
            {   # Wk-2 Day-2  Long Cycle
                "main":     "KB Long Cycle Clean & Jerk 2×5 min (switch hands each min)",
                "std_kg":   12,
                "accessory": [
                    "Press 3×6 /side (strict)",
                    "Renegade Row 3×6 /side",
                    "Ab Wheel Rollout 3×8",
                ],
                "finisher": "Max C&J in 5 min (one hand, no switching)",
            },
            {   # Wk-2 Day-3  Snatch Test Prep
                "main":     "KB Snatch 10 min test-pace (switch every 60 s)",
                "std_kg":   12,
                "accessory": [
                    "High Pull 3×8 /side",
                    "Swing 3×20",
                    "Wrist Mobility 2×2 min",
                ],
                "finisher": "Swing Tabata 8 rounds (20 s on / 10 s off)",
            },
        ],
    },

    "athena_tactical_strength": {
        "name": "Athena's Tactical Strength (2-week / 6 sessions)",
        "sessions": [
            {   # Wk-1 Day-1  TGU Foundation
                "main":     "Turkish Get-Up 5×3 /side (light — perfect form)",
                "std_kg":   8,
                "accessory": [
                    "Windmill 3×5 /side",
                    "Arm Bar 2×60 s /side",
                    "Hip Bridge 3×15",
                ],
                "finisher": "TGU + 5 Swings /side × 3 (flow circuit)",
            },
            {   # Wk-1 Day-2  Strict Press
                "main":     "Strict Military Press 5×5 /side @ RPE 7",
                "std_kg":   12,
                "accessory": [
                    "Bent-Over Row 4×8 /side",
                    "TRX Face-Pull 3×15",
                    "Suitcase Carry 3×30 m /side",
                ],
                "finisher": "Max strict press /side in 3 min (moderate bell)",
            },
            {   # Wk-1 Day-3  Bent Press & Hinge
                "main":     "Bent Press 4×3 /side (technical focus)",
                "std_kg":   12,
                "accessory": [
                    "Single-Leg RDL 3×8 /side",
                    "Goblet Squat 3×10",
                    "Bottoms-Up Press 3×5 /side",
                ],
                "finisher": "Get-Up Sit-Up × 10 /side + 10 Swings × 3",
            },
            {   # Wk-2 Day-1  TGU Ladder
                "main":     "TGU Ladder (1-2-3-2-1 /side) × 2 (add load from Wk-1)",
                "std_kg":   12,
                "accessory": [
                    "Windmill 3×6 /side (heavier)",
                    "Half-Kneeling Press 3×8 /side",
                    "Dead Bug 3×12",
                ],
                "finisher": "TGU AMRAP in 8 min (alternating sides)",
            },
            {   # Wk-2 Day-2  Push-Press + Floor Press
                "main":     "Push-Press 5×5 /side + KB Floor Press 3×8 /side (superset)",
                "std_kg":   12,
                "accessory": [
                    "Chest-Supported Row 3×10",
                    "Overhead Carry 4×20 m /side",
                    "Copenhagen Plank 3×20 s /side",
                ],
                "finisher": "5 Push-Press + 5 Floor Press /side × 4 (no rest)",
            },
            {   # Wk-2 Day-3  Windmill + TGU Complex
                "main":     "Windmill + TGU Complex: 5 Windmills → 1 TGU /side × 4",
                "std_kg":   12,
                "accessory": [
                    "Bottoms-Up Carry 3×20 m /side",
                    "Bent Press 3×3 /side",
                    "Thoracic Rotation Drill 2×10 /side",
                ],
                "finisher": "Heavy TGU 1/side every 2 min × 6",
            },
        ],
    },

    "apollo_endurance_forge": {
        "name": "Apollo's Endurance Forge (2-week / 6 sessions)",
        "sessions": [
            {   # Wk-1 Day-1  Volume Squat
                "main":     "Double-KB Front Squat 4×10 @ RPE 6",
                "std_kg":   12,
                "accessory": [
                    "Step-Up 3×15 /leg",
                    "TRX Squat Jump 3×12",
                    "Lateral Band Walk 3×20 /side",
                ],
                "finisher": "Goblet Squat 50 reps for time (1 weight)",
            },
            {   # Wk-1 Day-2  Clean Volume
                "main":     "KB Clean 5×8 /side (focus: linkage, no arm-curling)",
                "std_kg":   12,
                "accessory": [
                    "KB Row 4×10 /side",
                    "Push-Up 3×20",
                    "Plank Shoulder Tap 3×20",
                ],
                "finisher": "Ladder: 1-2-3-4-5 Clean /side, no rest between rungs",
            },
            {   # Wk-1 Day-3  Swing Intervals
                "main":     "Swing Intervals 30 s on / 30 s off × 15 rounds",
                "std_kg":   16,
                "accessory": [
                    "Box Jump 3×8",
                    "Hip Flexor Stretch 2×60 s /side",
                    "Single-Leg Balance 2×45 s /side",
                ],
                "finisher": "300 Swings — every time you put it down, 10 Push-Ups",
            },
            {   # Wk-2 Day-1  Goblet Volume
                "main":     "Goblet Squat 5×15 (heavier than Wk-1)",
                "std_kg":   16,
                "accessory": [
                    "Reverse Lunge 4×10 /leg",
                    "TRX Row 4×15",
                    "Side Plank 3×30 s /side",
                ],
                "finisher": "Goblet + Swing alternating: 10 each × 6 (no rest)",
            },
            {   # Wk-2 Day-2  Push-Press Ladder
                "main":     "Push-Press Ladder (1-2-3-4-5 /side) × 4",
                "std_kg":   12,
                "accessory": [
                    "Single-Arm Row 4×12 /side",
                    "Face-Pull 3×20",
                    "Carry Medley: Rack → OH → Farmer 20 m each",
                ],
                "finisher": "AMRAP in 5 min: 5 Push-Press + 5 Row /side",
            },
            {   # Wk-2 Day-3  200 Swing Challenge
                "main":     "200 KB Swings EMOM — 10 reps at the top of every minute",
                "std_kg":   16,
                "accessory": [
                    "Hip Hinge Mobility 2×10",
                    "Glute Bridge Hold 3×30 s",
                    "Dead Bug 3×10 /side",
                ],
                "finisher": "Max swings in 4 min (go until form breaks)",
            },
        ],
    },

    "poseidon_wave_protocol": {
        "name": "Poseidon's Wave Protocol (2-week / 6 sessions)",
        "sessions": [
            {   # Wk-1 Day-1  Wave Deadlift
                "main":     "Wave-Load KB Deadlift: (3 @ heavy, 2 @ heavier, 1 @ heaviest) × 3 waves",
                "std_kg":   16,
                "accessory": [
                    "Romanian Deadlift 3×8 /side",
                    "Reverse Hyper (body weight) 3×15",
                    "Pallof Press 3×8 /side",
                ],
                "finisher": "Single-Leg RDL 10 /side + 10 Swings × 3 (no rest)",
            },
            {   # Wk-1 Day-2  Wave Press
                "main":     "Wave-Load Strict Press: (5, 3, 2 /side) × 2 waves",
                "std_kg":   12,
                "accessory": [
                    "Pull-Up or TRX Row 4×8",
                    "Lateral Raise 3×15",
                    "Overhead Carry 3×30 m /side",
                ],
                "finisher": "Push-Press max reps in 3 min (one bell, switch once)",
            },
            {   # Wk-1 Day-3  Wave Swing
                "main":     "Swing Wave: 10-20-30-20-10 (rest = equal work time) × 2",
                "std_kg":   16,
                "accessory": [
                    "Goblet Squat 3×10",
                    "Hip Flexor Mobilization 2×90 s /side",
                    "Single-Leg Glute Bridge 3×12 /side",
                ],
                "finisher": "30 s max swings / 30 s rest × 10 rounds",
            },
            {   # Wk-2 Day-1  Heavy Wave Deadlift
                "main":     "Heavy Wave KB DL: (2 @ near-max, 1 @ max) × 4 waves",
                "std_kg":   20,
                "accessory": [
                    "Suitcase Deadlift 3×5 /side (heavy)",
                    "Nordic Hamstring Curl (eccentric) 3×5",
                    "Bird Dog 3×10 /side",
                ],
                "finisher": "Heavy Swing 5 × 10 with 90 s rest",
            },
            {   # Wk-2 Day-2  Heavy Wave Press
                "main":     "Heavy Wave Press: (3, 2, 1 /side) × 3 waves (add load)",
                "std_kg":   16,
                "accessory": [
                    "Weighted Pull-Up or TRX Archer Row 4×5",
                    "KB Windmill 3×5 /side",
                    "Farmer Carry 4×30 m (heavy)",
                ],
                "finisher": "5 Strict + 5 Push-Press /side × 4 (no rest between)",
            },
            {   # Wk-2 Day-3  Full-Body Wave Complex
                "main":     "Wave Complex /side: (Swing + Clean + Press + Squat) × 3-2-1 × 3",
                "std_kg":   12,
                "accessory": [
                    "Turkish Get-Up 2×2 /side",
                    "Mobility Flow (hip + thoracic) 2×5 min",
                    "Dead Hang 3×30 s",
                ],
                "finisher": "Descending ladder: 10-8-6-4-2 of complex /side (no rest)",
            },
        ],
    },

    "hades_iron_temple": {
        "name": "Hades' Iron Temple (2-week / 6 sessions)",
        "sessions": [
            {   # Wk-1 Day-1  Heavy Squat
                "main":     "Double-KB Front Squat 6×3 @ RPE 8–9",
                "std_kg":   20,
                "accessory": [
                    "Pause Goblet Squat (3-s hold) 3×5",
                    "Single-Leg Press (wall-sit variant) 3×30 s /leg",
                    "Ab Wheel Rollout 3×8",
                ],
                "finisher": "Heavy Goblet Hold (max weight) 3×45 s",
            },
            {   # Wk-1 Day-2  Heavy Floor Press
                "main":     "Single-KB Floor Press 5×5 /side (heaviest possible)",
                "std_kg":   16,
                "accessory": [
                    "Chest-Supported Row 4×6 (heavy)",
                    "Triceps Extension 3×10",
                    "Rear-Delt Fly 3×15",
                ],
                "finisher": "Floor Press Max Set /side (no set-down to failure)",
            },
            {   # Wk-1 Day-3  Heavy Hinge
                "main":     "Double-KB Deadlift 5×3 @ RPE 9 (near-maximal)",
                "std_kg":   24,
                "accessory": [
                    "Banded Good Morning 3×12",
                    "Copenhagen Plank 3×25 s /side",
                    "GHR or Nordic Curl 3×5",
                ],
                "finisher": "Heavy Swing 10 × 5 EMOM (competition-pace)",
            },
            {   # Wk-2 Day-1  Squat + Pause
                "main":     "Double-KB Front Squat 5×2 (↑ load from Wk-1) + 3-s pause",
                "std_kg":   24,
                "accessory": [
                    "Rear-Foot-Elevated Split Squat 3×5 /leg (heavy)",
                    "Glute-Ham Walkout 3×10",
                    "Hanging Knee Raise 3×10",
                ],
                "finisher": "Double-KB Front Squat × 3 reps on the minute × 8",
            },
            {   # Wk-2 Day-2  Strict Press Max
                "main":     "Strict Press 5×3 /side (heavier than Wk-1) — no leg drive",
                "std_kg":   16,
                "accessory": [
                    "Weighted Pull-Up or TRX One-Arm Row 4×4 /side",
                    "Bottoms-Up Press 3×3 /side",
                    "Prone Y-T-W Raise 3×10 each",
                ],
                "finisher": "Strict Press 1RM attempt /side (3 warm-up singles → PR)",
            },
            {   # Wk-2 Day-3  Total Grind
                "main":     "Heavy Complex /side: (DL + Clean + Press + Squat) 5×3",
                "std_kg":   16,
                "accessory": [
                    "Turkish Get-Up 3×1 /side (heaviest manageable)",
                    "Farmers Carry 3×40 m (max load)",
                    "Core Anti-Rotation Hold 3×30 s /side",
                ],
                "finisher": "1 rep every 30 s of the complex /side × 10 min",
            },
        ],
    },
}

TRACK_KEYS      = list(TEMPLATES.keys())
SESSIONS_NEEDED = 6      # workouts per 2-week cycle
WK_TARGET       = 3      # any activities per calendar week for a laurel

# ── Movement registry ─────────────────────────────────────────────────────────
# (slug, display_name, category, std_kg_female, sets_reps_hint)
# std_kg = 0 for barbell and bodyweight movements (user sets own load).
_MOVEMENT_TABLE = [
    # KB — Swing
    ("kb_swing",            "KB Swing",               "swing",     16, "5×15"),
    ("kb_double_swing",     "Double KB Swing",         "swing",     16, "5×10"),
    ("kb_american_swing",   "American Swing",          "swing",     12, "EMOM 10"),
    # KB — Snatch
    ("kb_snatch",           "KB Snatch",               "snatch",    12, "10×6/side"),
    ("kb_half_snatch",      "KB Half Snatch",          "snatch",    12, "3×8/side"),
    # KB — Clean
    ("kb_clean",            "KB Clean",                "clean",     12, "5×5/side"),
    ("kb_double_clean",     "Double KB Clean",         "clean",     12, "5×5"),
    # KB — Press
    ("kb_press",            "KB Press",                "press",     12, "5×5/side"),
    ("kb_push_press",       "KB Push-Press",           "press",     12, "5×5/side"),
    ("kb_jerk",             "KB Jerk",                 "press",     12, "2×5 min"),
    ("kb_long_cycle",       "Long Cycle C&J",          "press",     12, "2×5 min"),
    ("kb_floor_press",      "KB Floor Press",          "press",     12, "3×8/side"),
    ("kb_clean_press",      "KB Clean + Press",        "press",     12, "5×5/side"),
    ("kb_bottoms_up_press", "Bottoms-Up Press",        "press",      8, "3×5/side"),
    # KB — Squat
    ("kb_goblet_squat",     "Goblet Squat",            "squat",     16, "4×10"),
    ("kb_front_squat",      "Double KB Front Squat",   "squat",     12, "5×5"),
    ("kb_split_squat",      "KB Split Squat",          "squat",     12, "3×8/leg"),
    # KB — Hinge
    ("kb_deadlift",         "KB Deadlift",             "hinge",     16, "5×5"),
    ("kb_rdl",              "KB RDL",                  "hinge",     16, "4×8/side"),
    ("kb_suitcase_dl",      "Suitcase Deadlift",       "hinge",     16, "3×5/side"),
    ("kb_sl_rdl",           "Single-Leg RDL",          "hinge",     12, "3×8/side"),
    ("kb_high_pull",        "KB High Pull",            "hinge",     16, "3×8/side"),
    # KB — Get-Up / Windmill
    ("kb_tgu",              "Turkish Get-Up",          "get_up",     8, "5×3/side"),
    ("kb_windmill",         "KB Windmill",             "get_up",    12, "3×5/side"),
    ("kb_bent_press",       "Bent Press",              "get_up",    12, "4×3/side"),
    # KB — Row
    ("kb_row",              "KB Row",                  "row",       12, "4×8/side"),
    ("kb_renegade_row",     "Renegade Row",            "row",       12, "3×6/side"),
    # KB — Carry
    ("kb_farmer_carry",     "Farmer Carry",            "carry",     16, "4×30 m"),
    ("kb_rack_carry",       "Rack Carry",              "carry",     12, "3×30 m/side"),
    ("kb_oh_carry",         "Overhead Carry",          "carry",     12, "3×20 m/side"),
    ("kb_suitcase_carry",   "Suitcase Carry",          "carry",     16, "4×20 m/side"),
    ("kb_bu_carry",         "Bottoms-Up Carry",        "carry",      8, "3×20 m/side"),
    # Barbell
    ("bb_squat",            "Barbell Back Squat",      "barbell",    0, "5×5"),
    ("bb_front_squat",      "Barbell Front Squat",     "barbell",    0, "4×5"),
    ("bb_deadlift",         "Barbell Deadlift",        "barbell",    0, "5×3"),
    ("bb_rdl",              "Barbell RDL",             "barbell",    0, "4×8"),
    ("bb_ohp",              "Overhead Press",          "barbell",    0, "5×5"),
    ("bb_bench",            "Bench Press",             "barbell",    0, "5×5"),
    ("bb_row",              "Barbell Row",             "barbell",    0, "4×8"),
    ("bb_power_clean",      "Power Clean",             "barbell",    0, "5×3"),
    # Bodyweight
    ("bw_push_up",          "Push-Up",                 "bodyweight", 0, "3×15"),
    ("bw_pull_up",          "Pull-Up",                 "bodyweight", 0, "4×5"),
    ("bw_dip",              "Dip",                     "bodyweight", 0, "3×10"),
    ("bw_lunge",            "Lunge",                   "bodyweight", 0, "3×10/leg"),
    ("bw_step_up",          "Step-Up",                 "bodyweight", 0, "3×12/leg"),
    ("bw_box_jump",         "Box Jump",                "bodyweight", 0, "3×8"),
    ("bw_burpee",           "Burpee",                  "bodyweight", 0, "3×10"),
    ("bw_plank",            "Plank",                   "bodyweight", 0, "3×45 s"),
    ("bw_dead_bug",         "Dead Bug",                "bodyweight", 0, "3×10/side"),
    ("bw_hollow_rock",      "Hollow Rock",             "bodyweight", 0, "3×20"),
    ("bw_ab_wheel",         "Ab Wheel Rollout",        "bodyweight", 0, "3×8"),
    ("bw_nordic_curl",      "Nordic Curl",             "bodyweight", 0, "3×5 (ecc)"),
    ("bw_bulgarian",        "Bulgarian Split Squat",   "bodyweight", 0, "3×8/leg"),
    ("bw_hip_bridge",       "Glute Bridge",            "bodyweight", 0, "3×15"),
    ("bw_pallof",           "Pallof Press",            "bodyweight", 0, "3×10/side"),
]


def get_movements() -> list:
    """Return the full movement registry as a list of dicts."""
    return [
        {"slug": s, "name": n, "category": c, "std_kg": kg, "hint": h}
        for s, n, c, kg, h in _MOVEMENT_TABLE
    ]

# ── Default state ─────────────────────────────────────────────────────────────
def default_state() -> dict:
    return {
        "track": TRACK_KEYS[0],
        "microcycle": {
            "id": 0,
            "sessions_completed": 0,
            "start_date": str(dt.date.today()),
            "badge_given": False,
        },
        "workouts":          [],   # list[{date, type, details, coins, weight_kg?}]
        "ruck_log":          [],   # list[{date, distance_miles, weight_lbs, coins}]
        "run_log":           [],   # list[{date, distance_miles, coins, pace_min_per_mile?}]
        "walk_log":          [],   # list[{date, distance_miles, coins}]
        "badges":            [],   # list of badge records
        "treasury":          0.0,  # drachma accumulated (lift + ruck + run + walk)
        "total_ruck_miles":  0.0,  # lifetime ruck distance
        "total_run_miles":   0.0,  # lifetime run distance
        "total_walk_miles":  0.0,  # lifetime walk distance
        "journey_miles":     0.0,  # combined ruck + run + walk (used for milestone checks)
        "week_log":          {},   # {"(year, week)": count} — any activity
        "custom_tracks":     [],   # list of user-built track dicts
        "templates":         {k: v["name"] for k, v in TEMPLATES.items()},
    }

# ── Public API ────────────────────────────────────────────────────────────────

def _get_custom_track(state: dict, track_key: str) -> dict | None:
    """Return the custom track dict for a 'custom_<id>' key, or None."""
    if not track_key or not track_key.startswith("custom_"):
        return None
    track_id = track_key[7:]   # strip "custom_" prefix
    for ct in state.get("custom_tracks", []):
        if str(ct.get("id", "")) == str(track_id):
            return ct
    return None


def get_today_workout(state: dict) -> dict:
    """Return structured data for the current session (no mutation)."""
    track = state.get("track")
    if not track:
        return {"status": "no_track", "message": "No track selected."}

    # ── Custom track ──────────────────────────────────────────────────────────
    if track.startswith("custom_"):
        ct = _get_custom_track(state, track)
        if ct is None:
            return {"status": "no_track",
                    "message": "Custom track not found. Please select a new track."}
        sessions_needed = len(ct["sessions"])
        mc  = state["microcycle"]
        idx = mc["sessions_completed"]
        if idx >= sessions_needed:
            return {"status": "cycle_complete",
                    "message": "Cycle complete! Log a custom workout or start a new track."}
        sess = ct["sessions"][idx]
        return {
            "status":         "active",
            "session_num":    idx + 1,
            "total_sessions": sessions_needed,
            "main":           sess.get("main", ""),
            "std_kg":         float(sess.get("std_kg", 16) or 16),
            "accessory":      sess.get("accessory", []),
            "finisher":       sess.get("finisher", ""),
            "track_name":     ct["name"],
        }

    # ── Built-in template track ───────────────────────────────────────────────
    if track not in TEMPLATES:
        return {"status": "no_track", "message": "No track selected."}
    mc  = state["microcycle"]
    idx = mc["sessions_completed"]
    if idx >= SESSIONS_NEEDED:
        return {"status": "cycle_complete",
                "message": "Cycle complete! Log a custom workout or start a new track."}
    sess = TEMPLATES[track]["sessions"][idx]
    return {
        "status":         "active",
        "session_num":    idx + 1,
        "total_sessions": SESSIONS_NEEDED,
        "main":           sess["main"],
        "std_kg":         sess.get("std_kg", 16),   # standard bell weight for drachma scaling
        "accessory":      sess["accessory"],
        "finisher":       sess["finisher"],
        "track_name":     TEMPLATES[track]["name"],
    }


def get_track_detail(key: str) -> dict | None:
    """Return full track template with all sessions for preview (no mutation)."""
    if key not in TEMPLATES:
        return None
    t = TEMPLATES[key]
    return {
        "key":      key,
        "name":     t["name"],
        "sessions": t["sessions"],
    }


def get_custom_track_detail(state: dict, track_id: str) -> dict | None:
    """Return a user's custom track by id (no mutation)."""
    for ct in state.get("custom_tracks", []):
        if str(ct.get("id", "")) == str(track_id):
            return ct
    return None


def init_track(state: dict, key: str) -> str:
    """Start a new micro-cycle on the given track (built-in or custom)."""
    if key.startswith("custom_"):
        ct = _get_custom_track(state, key)
        if ct is None:
            return f"Custom track not found: {key}"
        state["track"] = key
        state["microcycle"] = {
            "id":                  state["microcycle"]["id"] + 1,
            "sessions_completed":  0,
            "start_date":          str(dt.date.today()),
            "badge_given":         False,
        }
        return f"Started {ct['name']}"
    if key not in TEMPLATES:
        return f"Unknown track: {key}"
    state["track"] = key
    state["microcycle"] = {
        "id":                  state["microcycle"]["id"] + 1,
        "sessions_completed":  0,
        "start_date":          str(dt.date.today()),
        "badge_given":         False,
    }
    return f"Started {TEMPLATES[key]['name']}"


def log_rec(state: dict, weights_lbs: dict | None = None) -> str:
    """Log the next recommended session.

    weights_lbs – dict of per-movement bell weights in lbs, e.g.:
        {"main": 35, "acc_0": 26, "acc_1": None, "finisher": 25}
    Keys: "main", "acc_0", "acc_1", "acc_2", "finisher".
    Only non-zero values are stored.

    Drachma scales on the MAIN lift weight vs the session's std_kg
    (clamped 0.5×–2.0×, so 2.50–10.00 per session).
    Skipping weight entry awards the flat BASE_WORKOUT_COINS.
    """
    track = state.get("track")
    if not track:
        return "No active track. Please select a track first."
    mc  = state["microcycle"]
    idx = mc["sessions_completed"]

    # Resolve session template (custom vs built-in)
    if track.startswith("custom_"):
        ct = _get_custom_track(state, track)
        if ct is None:
            return "Custom track not found. Please select a new track."
        sessions_needed = len(ct["sessions"])
        if idx >= sessions_needed:
            return "Cycle already complete. Log custom or start a new track."
        tpl    = ct["sessions"][idx]
        std_kg = float(tpl.get("std_kg", 16) or 16)
    else:
        if track not in TEMPLATES:
            return "No active track. Please select a track first."
        if idx >= SESSIONS_NEEDED:
            return "Cycle already complete. Log custom or start a new track."
        tpl    = TEMPLATES[track]["sessions"][idx]
        std_kg = tpl.get("std_kg", 16)

    main_lbs = float((weights_lbs or {}).get("main") or 0)
    if main_lbs > 0:
        main_kg = main_lbs * 0.453592
        ratio   = min(max(main_kg / std_kg, 0.5), 2.0)
        coins   = round(BASE_WORKOUT_COINS * ratio, 2)
    else:
        coins = BASE_WORKOUT_COINS

    # Store only movements that had a weight entered
    stored_weights: dict = {}
    if weights_lbs:
        for k, v in weights_lbs.items():
            try:
                f = float(v or 0)
                if f > 0:
                    stored_weights[k] = f
            except (TypeError, ValueError):
                pass

    entry: dict = {
        "date":    str(dt.date.today()),
        "type":    "recommended",
        "details": tpl["main"],
        "std_kg":  std_kg,
        "coins":   coins,
    }
    if stored_weights:
        entry["weights_lbs"] = stored_weights

    state["workouts"].append(entry)
    state["treasury"] = round(state.get("treasury", 0.0) + coins, 2)
    mc["sessions_completed"] += 1
    _increment_weekly_streak(state)
    _maybe_award_cycle_badge(state)

    if main_lbs > 0:
        return f"⚔️ Logged: {tpl['main']} @ {int(main_lbs)} lbs — earned 🪙 {coins:.2f} Drachma"
    return f"⚔️ Logged: {tpl['main']} — earned 🪙 {coins:.2f} Drachma"


def log_custom(state: dict, text: str) -> str:
    """Log a free-text custom workout (earns a flat CUSTOM_WORKOUT_COINS)."""
    coins = CUSTOM_WORKOUT_COINS
    state["workouts"].append({
        "date":    str(dt.date.today()),
        "type":    "custom",
        "details": text,
        "coins":   coins,
    })
    state["treasury"] = round(state.get("treasury", 0.0) + coins, 2)
    state["microcycle"]["sessions_completed"] += 1
    _increment_weekly_streak(state)
    _maybe_award_cycle_badge(state)
    return f"⚔️ Custom workout logged — earned 🪙 {coins:.2f} Drachma"


def log_ruck(state: dict, miles: float, pounds: float) -> str:
    """Log a ruck session, award drachma, check journey milestones."""
    coins         = round(miles * (1 + 0.01 * pounds), 2)
    prev_journey  = state.get("journey_miles",
                              state.get("total_ruck_miles", 0.0))
    new_journey   = prev_journey + miles

    state["ruck_log"].append({
        "date":           str(dt.date.today()),
        "distance_miles": miles,
        "weight_lbs":     pounds,
        "coins":          coins,
    })
    state["treasury"]        = round(state.get("treasury", 0.0) + coins, 2)
    state["total_ruck_miles"] = state.get("total_ruck_miles", 0.0) + miles
    state["journey_miles"]    = new_journey

    _check_journey_milestone(state, prev_journey, new_journey)
    _increment_weekly_streak(state)   # rucks count toward weekly laurels
    return (f"🪙 Earned {coins:.2f} Drachma.  "
            f"Journey: {new_journey:.1f} mi.")


def log_run(state: dict, miles: float, pace: float | None = None) -> str:
    """Log a run, award base-rate drachma (no weight bonus), check journey milestones."""
    coins        = round(miles * 1.0, 2)   # base rate; ruck earns more with weight
    prev_journey = state.get("journey_miles",
                             state.get("total_ruck_miles", 0.0))
    new_journey  = prev_journey + miles

    entry: dict = {
        "date":           str(dt.date.today()),
        "distance_miles": miles,
        "coins":          coins,
    }
    if pace is not None:
        entry["pace_min_per_mile"] = pace

    state.setdefault("run_log", []).append(entry)
    state["treasury"]       = round(state.get("treasury", 0.0) + coins, 2)
    state["total_run_miles"] = state.get("total_run_miles", 0.0) + miles
    state["journey_miles"]   = new_journey

    _check_journey_milestone(state, prev_journey, new_journey)
    _increment_weekly_streak(state)   # runs count toward weekly laurels
    return (f"🏃 Ran {miles:.1f} mi — earned {coins:.2f} Drachma.  "
            f"Journey: {new_journey:.1f} mi.")


def log_walk(state: dict, miles: float) -> str:
    """Log a walk, award half the run rate, count toward the journey."""
    coins        = round(miles * 0.5, 2)   # walks earn half vs running
    prev_journey = state.get("journey_miles", 0.0)
    new_journey  = prev_journey + miles

    state.setdefault("walk_log", []).append({
        "date":           str(dt.date.today()),
        "distance_miles": miles,
        "coins":          coins,
    })
    state["treasury"]        = round(state.get("treasury", 0.0) + coins, 2)
    state["total_walk_miles"] = state.get("total_walk_miles", 0.0) + miles
    state["journey_miles"]    = new_journey

    _check_journey_milestone(state, prev_journey, new_journey)
    _increment_weekly_streak(state)   # walks count toward weekly laurels
    return (f"🚶 Walked {miles:.1f} mi — earned {coins:.2f} Drachma.  "
            f"Journey: {new_journey:.1f} mi.")

# ── Internal helpers ──────────────────────────────────────────────────────────

def _maybe_award_cycle_badge(state: dict) -> None:
    """Award monster trophy when all sessions in the cycle are completed."""
    mc = state["microcycle"]
    if mc["badge_given"]:
        return
    # Determine how many sessions this cycle requires
    track = state.get("track", "")
    if track.startswith("custom_"):
        ct = _get_custom_track(state, track)
        sessions_needed = len(ct["sessions"]) if ct else SESSIONS_NEEDED
    else:
        sessions_needed = SESSIONS_NEEDED
    if mc["sessions_completed"] < sessions_needed:
        return
    _award_monster_badge(state)
    mc["badge_given"] = True


def _increment_weekly_streak(state: dict) -> None:
    """Award an Olympian Laurel after WK_TARGET activities in a calendar week.
    Any activity type (lift, ruck, run) counts."""
    today    = dt.date.today().isocalendar()[:2]   # (year, week_number)
    week_key = str(today)
    state.setdefault("week_log", {})
    count = state["week_log"].get(week_key, 0) + 1
    state["week_log"][week_key] = count
    if count == WK_TARGET:
        god, icon = random.choice(OLYMPIANS)
        state["badges"].append({
            "date":       str(dt.date.today()),
            "name":       f"{icon} {god} Laurel",
            "type":       "laurel",
            "image_path": None,
        })


def _check_journey_milestone(state: dict,
                              prev_miles: float,
                              new_miles:  float) -> None:
    """Award Pheidippides way-point postcards for every waypoint crossed.
    Journey miles = ruck + run combined. Loop-aware."""
    if TRIP_MILES <= 0:
        return

    prev_loop = int(prev_miles // TRIP_MILES)
    new_loop  = int(new_miles  // TRIP_MILES)

    # Build set of already-earned (loop, city) pairs to prevent duplicates
    earned: set = set()
    for b in state["badges"]:
        if b.get("type") == "ruck_quest":
            earned.add((b.get("loop", 0), b.get("stop", "")))

    for loop in range(prev_loop, new_loop + 1):
        base = loop * TRIP_MILES
        for offset, city, caption in RUCK_STOPS:
            abs_mark = base + offset
            if prev_miles <= abs_mark <= new_miles and (loop, city) not in earned:
                slug = city.replace(" ", "_")
                state["badges"].append({
                    "type":       "ruck_quest",
                    "loop":       loop,
                    "stop":       city,
                    "name":       f"📜 {city} Way-Point",
                    "date":       str(dt.date.today()),
                    "caption":    caption,
                    "image_path": f"Pheidippides/{slug}.png",
                })


def _pick_monster() -> tuple:
    """Return (display_name, folder_name) using weighted random selection."""
    r   = random.uniform(0, MONSTER_TOTAL)
    cum = 0.0
    for name, folder, prob in MONSTERS:
        cum += prob
        if r <= cum:
            return name, folder
    return MONSTERS[-1][:2]   # fallback


def _award_monster_badge(state: dict) -> None:
    """Add a randomly-selected monster trophy (10 % chance of gilded variant)."""
    name, folder = _pick_monster()
    gilded   = random.random() < GILD_CHANCE
    variant  = "Gold" if gilded else "Vibrant"
    img_path = f"{folder}/{variant}/{folder}.png"
    state["badges"].append({
        "date":       str(dt.date.today()),
        "name":       name + (" ★" if gilded else ""),
        "type":       "monster",
        "monster_id": folder,
        "image_path": img_path,
    })


# ── Custom track management ───────────────────────────────────────────────────

def save_custom_track(state: dict, name: str, sessions: list) -> dict:
    """Validate and persist a new custom training track.

    Returns the saved track dict (with generated id).
    Raises ValueError for invalid inputs.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Track name cannot be empty.")
    if not sessions or len(sessions) < 1:
        raise ValueError("A cycle must have at least 1 session.")
    if len(sessions) > 6:
        raise ValueError("A cycle can have at most 6 sessions.")

    cleaned: list = []
    for i, s in enumerate(sessions):
        main = str(s.get("main", "")).strip()
        if not main:
            raise ValueError(f"Session {i + 1} needs a main movement.")
        acc      = [str(a).strip() for a in s.get("accessory", []) if str(a).strip()]
        finisher = str(s.get("finisher", "")).strip()
        try:
            std_kg = float(s.get("std_kg", 16) or 16)
        except (TypeError, ValueError):
            std_kg = 16.0
        cleaned.append({
            "main":      main,
            "std_kg":    std_kg,
            "accessory": acc,
            "finisher":  finisher,
        })

    track_id = str(int(time.time() * 1000))
    track: dict = {"id": track_id, "name": name, "sessions": cleaned}
    state.setdefault("custom_tracks", []).append(track)
    return track


def delete_custom_track(state: dict, track_id: str) -> bool:
    """Remove a custom track by id. Returns True if found and removed."""
    tracks     = state.get("custom_tracks", [])
    new_tracks = [t for t in tracks if str(t.get("id", "")) != str(track_id)]
    if len(new_tracks) == len(tracks):
        return False
    state["custom_tracks"] = new_tracks
    # If this was the active track, fall back to the first built-in track
    if state.get("track") == f"custom_{track_id}":
        state["track"] = TRACK_KEYS[0]
    return True
