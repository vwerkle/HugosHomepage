"""
Generate daily 3x3 WC Grid puzzles and write the static bundle.

Algorithm:
  1. Load entities from data/wc_grid/entities.json
  2. Build criterion pool (filtered to usable criteria)
  3. For each date in the schedule, pick a random valid 3x3 grid:
     - 3 row criteria, 3 col criteria (no overlap, diverse types)
     - All 9 cells must have >= MIN_CELL_PLAYERS valid players
     - Average cell size must be in [MIN_AVG, MAX_AVG]
  4. Pre-compute valid player sets and rarity scores per cell
  5. Write wc-grid/public/data/bundle.json

Usage:
    python -m ingestion.wc_grid.generate_grids              # 400 days from today
    python -m ingestion.wc_grid.generate_grids --days 30   # 30 days
    python -m ingestion.wc_grid.generate_grids --start 2026-06-01 --days 400
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from .build_cells import compute_grid_cells, grid_difficulty_score
from .criteria import (
    axes_are_diverse,
    build_criterion_pool,
    criterion_key,
)

ENTITIES_FILE = Path("data/wc_grid/entities.json")
BUNDLE_OUT = Path("wc-grid/public/data/bundle.json")

MIN_CELL_PLAYERS = 2   # reject grids where any cell has fewer valid players
MAX_CELL_PLAYERS = 300 # cells with huge valid sets are trivially easy; warn but allow
MIN_AVG = 3            # average valid players per cell — lower bound
MAX_AVG = 200          # average valid players per cell — upper bound
MAX_TRIES = 5000       # attempts per date before giving up


def _split_pool(pool: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split the criterion pool into:
      - nation_pool: criteria keyed on a player's national team (type=nation only)
      - event_pool: everything else — position, role, achievement, confederation

    Grid generation keeps pure nation criteria on one axis and event criteria on
    the other, preventing impossible nation × nation cells (a player can only
    represent one national team).
    """
    nation_pool = [c for c in pool if c["type"] == "nation"]
    event_pool  = [c for c in pool if c["type"] != "nation"]
    return nation_pool, event_pool


def _generate_one_grid(
    pool: list[dict],
    entities: dict,
    rng: random.Random,
) -> dict | None:
    """
    Try up to MAX_TRIES times to find a valid 3x3 grid.

    Strategy: keep nation/confederation criteria on one axis (rows XOR cols),
    event criteria on the other. This avoids impossible nation×nation cells.
    With ~50% probability, nations go on rows; otherwise on cols.
    """
    nation_pool, event_pool = _split_pool(pool)

    # Need at least 3 nation criteria and 3 event criteria
    if len(nation_pool) < 3 or len(event_pool) < 3:
        return None

    for _ in range(MAX_TRIES):
        # Alternate which axis holds nations for variety
        if rng.random() < 0.5:
            rows = rng.sample(nation_pool, 3)
            cols = rng.sample(event_pool, 3)
        else:
            rows = rng.sample(event_pool, 3)
            cols = rng.sample(nation_pool, 3)

        # No criterion used twice (shouldn't happen since pools are disjoint,
        # but guard against it anyway)
        row_keys = {criterion_key(c) for c in rows}
        col_keys = {criterion_key(c) for c in cols}
        if row_keys & col_keys:
            continue

        # Enforce axis type diversity (no two confederations on same axis, etc.)
        if not axes_are_diverse(rows, cols):
            continue

        cells = compute_grid_cells(rows, cols, entities)
        if cells is None:
            continue

        cell_sizes = [len(c["valid"]) for c in cells]
        if min(cell_sizes) < MIN_CELL_PLAYERS:
            continue

        avg = sum(cell_sizes) / len(cell_sizes)
        if avg < MIN_AVG or avg > MAX_AVG:
            continue

        return {
            "rows": rows,
            "cols": cols,
            "cells": cells,
        }

    return None


def generate_schedule(
    pool: list[dict],
    entities: dict,
    start: date,
    num_days: int,
) -> dict[str, dict]:
    """
    Generate a date-keyed grid schedule.
    Seed per date = SHA-256 first 8 bytes of "WCGrid-{date_str}" for reproducibility.
    """
    import hashlib

    schedule: dict[str, dict] = {}
    failures = 0

    for i in range(num_days):
        day = start + timedelta(days=i)
        date_str = day.isoformat()

        seed_bytes = hashlib.sha256(f"WCGrid-{date_str}".encode()).digest()
        seed = int.from_bytes(seed_bytes[:8], "big")
        rng = random.Random(seed)

        grid = _generate_one_grid(pool, entities, rng)
        if grid is None:
            print(f"  WARNING: could not generate grid for {date_str} after {MAX_TRIES} tries")
            failures += 1
            continue

        # Serialize: strip internal-only keys (valid is already serializable)
        schedule[date_str] = {
            "rows": grid["rows"],
            "cols": grid["cols"],
            "cells": grid["cells"],
        }

    if failures:
        print(f"  {failures}/{num_days} dates have no grid (criteria pool too small?)")

    return schedule


def build_player_list(entities: dict) -> list[dict]:
    """Slim player list for the client (id, name, search, weight)."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "search": p["search"],
            "weight": p["weight"],
        }
        for p in sorted(entities["players"].values(), key=lambda p: p["name"])
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None,
                        help="Start date YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=400,
                        help="Number of days to generate (default: 400)")
    parser.add_argument("--min-cell", type=int, default=MIN_CELL_PLAYERS)
    parser.add_argument("--min-avg",  type=float, default=MIN_AVG)
    parser.add_argument("--max-avg",  type=float, default=MAX_AVG)
    args = parser.parse_args()

    if not ENTITIES_FILE.exists():
        print(f"ERROR: {ENTITIES_FILE} not found. Run transform.py first.", file=sys.stderr)
        sys.exit(1)

    with open(ENTITIES_FILE, encoding="utf-8") as f:
        entities = json.load(f)

    print(f"Loaded {len(entities['players'])} players, "
          f"{len(entities['appearances'])} appearances, "
          f"{len(entities['achievements'])} achievements")

    pool = build_criterion_pool(entities)
    print(f"Criterion pool: {len(pool)} criteria")
    for ctype in ("nation", "tournament", "confederation", "achievement",
                  "is_gk", "position", "is_captain"):
        n = sum(1 for c in pool if c["type"] == ctype)
        if n:
            print(f"  {ctype}: {n}")

    start = date.fromisoformat(args.start) if args.start else date.today()
    print(f"Generating {args.days} grids starting {start}...")

    schedule = generate_schedule(pool, entities, start, args.days)
    print(f"Generated {len(schedule)}/{args.days} grids")

    players_list = build_player_list(entities)

    bundle = {
        "players": players_list,
        "grids": schedule,
        "meta": {
            "generated": date.today().isoformat(),
            "start": start.isoformat(),
            "days": args.days,
            "player_count": len(players_list),
            "grid_count": len(schedule),
        },
    }

    BUNDLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(BUNDLE_OUT, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = BUNDLE_OUT.stat().st_size / 1024
    print(f"Wrote {BUNDLE_OUT} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
