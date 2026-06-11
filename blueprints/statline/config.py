TIMEZONE = "America/New_York"
GAME_EPOCH = "2026-06-01"   # day 1; game_number = days since epoch + 1

SCORING = {
    "MAX_PER_CATEGORY": 100,
    "ZERO_EPSILON": 0.001,   # denominator guard when target stat == 0
}

AUTOCOMPLETE_MAX = 20

# ── Sport / position / category definitions ────────────────────────────────
# Adding a new sport: add an entry to SPORTS with the same shape, drop a CSV,
# and add its column mappings to CSV_COLUMNS. No engine or route changes needed.

SPORTS = {
    "baseball": {
        "label": "Baseball",
        "emoji": "⚾",
        "positions": ["SP", "Hitter"],
        "random_position": ["SP", "Hitter"],  # 3rd slot: randomly SP or Hitter each day
        "SP": {
            "label": "Starting Pitcher",
            "threshold": {"col": "gs", "min": 150},
            "categories": [
                {"key": "era",  "label": "ERA",        "fmt": ".2f"},
                {"key": "wins", "label": "Wins",       "fmt": "d"},
                {"key": "so",   "label": "Strikeouts", "fmt": "d"},
            ],
        },
        "Hitter": {
            "label": "Hitter",
            "threshold": {"col": "ab", "min": 2000},
            "categories": [
                {"key": "h",  "label": "Hits",      "fmt": "d"},
                {"key": "hr", "label": "Home Runs", "fmt": "d"},
            ],
        },
    },
    "football": {
        "label": "Football",
        "emoji": "🏈",
        "positions": ["QB", "RB", "WRTE"],
        "QB": {
            "label": "Quarterback",
            "threshold": {"col": "gs", "min": 13},
            "categories": [
                {"key": "pass_yds", "label": "Pass Yards", "fmt": "d"},
                {"key": "int",      "label": "INTs",        "fmt": "d"},
                {"key": "pass_td",  "label": "Pass TDs",    "fmt": "d"},
            ],
        },
        "RB": {
            "label": "Running Back",
            "threshold": {"col": "carries", "min": 300},
            "categories": [
                {"key": "rush_yds", "label": "Rush Yards",      "fmt": "d"},
                {"key": "rush_td",  "label": "Rush TDs",        "fmt": "d"},
                {"key": "rec_yds",  "label": "Receiving Yards", "fmt": "d"},
            ],
        },
        "WRTE": {
            "label": "WR / TE",
            "threshold": {"col": "rec", "min": 350},
            "categories": [
                {"key": "rec",     "label": "Receptions",      "fmt": "d"},
                {"key": "rec_td",  "label": "Receiving TDs",   "fmt": "d"},
                {"key": "rec_yds", "label": "Receiving Yards", "fmt": "d"},
            ],
        },
    },
}

# ── CSV column mappings ────────────────────────────────────────────────────
# Keys are logical names used throughout the engine.
# Values are the actual column headers in your CSV exports.
# Rename any value to match your export without touching engine code.

CSV_COLUMNS = {
    "baseball": {
        "id":       "player_id",
        "name":     "player_name",
        "position": "position",    # "SP" or "Hitter"
        # SP stats
        "gs":       "gs",
        "wins":     "wins",
        "so":       "so",
        "era":      "era",
        # Hitter stats
        "ab":       "ab",
        "h":        "h",
        "hr":       "hr",
        "sb":       "sb",
    },
    "football": {
        "id":       "player_id",
        "name":     "player_name",
        "position": "position",    # "QB", "RB", or "WRTE"
        # QB stats
        "pass_att": "pass_att",
        "pass_yds": "pass_yds",
        "pass_td":  "pass_td",
        "int":      "int",
        "gs":       "gs",          # career games started (QBs only, used for threshold)
        # RB stats
        "carries":  "carries",
        "rush_yds": "rush_yds",
        "rush_td":  "rush_td",
        # WR/TE stats (RBs may also have these)
        "rec":      "rec",
        "rec_yds":  "rec_yds",
        "rec_td":   "rec_td",
    },
}
