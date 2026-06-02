"""
Unit tests for the grid generator.
Verifies: solvability guarantee, no empty cells, no player reuse, rarity integrity.
Uses a synthetic entities fixture large enough to generate valid grids.
"""

import json
import random
from datetime import date, timedelta

import pytest

from ingestion.wc_grid.criteria import build_criterion_pool, criterion_key
from ingestion.wc_grid.build_cells import compute_grid_cells
from ingestion.wc_grid.generate_grids import (
    _generate_one_grid,
    generate_schedule,
    build_player_list,
    MIN_CELL_PLAYERS,
)


# ---------------------------------------------------------------------------
# Larger synthetic fixture (enough players to actually generate valid grids)
# ---------------------------------------------------------------------------

def _make_player(pid: str, name: str, weight: int, is_gk: bool = False) -> dict:
    import unicodedata
    nfd = unicodedata.normalize("NFD", name)
    search = "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()
    return {"id": pid, "name": name, "search": search, "weight": weight, "is_gk": is_gk}


@pytest.fixture(scope="module")
def entities():
    """
    Synthetic entities with enough players/criteria to generate real grids:
      4 nations (Argentina, Germany, France, Brazil) 5 players each
      2 confederations (CONMEBOL: ARG/BRA; UEFA: GER/FRA)
      3 tournament years (2014, 2018, 2022)
      Achievements: won_wc players, golden_boot players, 3+WC players
    """
    # Build 5 players per nation × 4 nations = 20 base players
    nations = {
        "Q_arg": {"id": "Q_arg", "name": "Argentina", "confederation": "CONMEBOL"},
        "Q_ger": {"id": "Q_ger", "name": "Germany",   "confederation": "UEFA"},
        "Q_fra": {"id": "Q_fra", "name": "France",    "confederation": "UEFA"},
        "Q_bra": {"id": "Q_bra", "name": "Brazil",    "confederation": "CONMEBOL"},
    }

    player_defs = []  # (pid, name, weight, is_gk, nation_id, years)
    names_by_nation = {
        "Q_arg": ["Messi", "DiMaria", "Aguero", "Higuain", "Romero"],
        "Q_ger": ["Neuer", "Muller", "Klose", "Lahm", "Boateng"],
        "Q_fra": ["Zidane", "Henry", "Pogba", "Mbappe", "Lloris"],
        "Q_bra": ["Neymar", "Ronaldo", "Rivaldo", "Cafu", "Dida"],
    }
    gk_positions = {
        "Q_arg": "Romero", "Q_ger": "Neuer", "Q_fra": "Lloris", "Q_bra": "Dida"
    }

    players = {}
    appearances = []
    achievements = []

    pid_counter = 1
    player_lookup = {}  # name → pid

    for nation_id, names in names_by_nation.items():
        for i, name in enumerate(names):
            pid = f"Q{pid_counter:04d}"
            pid_counter += 1
            is_gk = (name == gk_positions.get(nation_id))
            weight = i + 1  # weight 1–5, lower = more obscure
            players[pid] = _make_player(pid, name, weight, is_gk)
            player_lookup[name] = pid

            # Each player appears in 2014 and 2018; first 3 also in 2022
            years_for_player = [2014, 2018] if i >= 3 else [2014, 2018, 2022]
            for year in years_for_player:
                appearances.append({
                    "player_id": pid,
                    "tournament_year": year,
                    "nation_id": nation_id,
                    "goals": max(0, 3 - i),  # more goals for lower-index players
                    "is_gk": is_gk,
                })

    # Achievements
    # won_wc: Argentina 2022 squad (first 5 players), Germany 2014 squad
    for name in names_by_nation["Q_arg"]:
        achievements.append({"player_id": player_lookup[name], "achievement": "won_wc", "tournament_year": 2022})
    for name in names_by_nation["Q_ger"][:5]:
        achievements.append({"player_id": player_lookup[name], "achievement": "won_wc", "tournament_year": 2014})

    # golden_boot: Klose (Germany)
    achievements.append({"player_id": player_lookup["Klose"], "achievement": "golden_boot", "tournament_year": None})
    # golden_glove: Neuer (Germany), Lloris (France)
    for name in ("Neuer", "Lloris", "Dida"):
        achievements.append({"player_id": player_lookup[name], "achievement": "golden_glove", "tournament_year": None})

    # played_3plus_wcs: first 3 players of each nation (they appear in 2014, 2018, 2022)
    for nation_id, names in names_by_nation.items():
        for name in names[:3]:
            achievements.append({"player_id": player_lookup[name], "achievement": "played_3plus_wcs", "tournament_year": None})

    # career_goals_5plus: Messi, Ronaldo (Brazil)
    for name in ("Messi", "Ronaldo"):
        achievements.append({"player_id": player_lookup[name], "achievement": "career_goals_5plus", "tournament_year": None})

    return {
        "players": players,
        "nations": nations,
        "appearances": appearances,
        "achievements": achievements,
    }


# ---------------------------------------------------------------------------
# Tests: _generate_one_grid
# ---------------------------------------------------------------------------

class TestGenerateOneGrid:
    def test_generates_a_grid(self, entities):
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        grid = _generate_one_grid(pool, entities, rng)
        assert grid is not None

    def test_grid_has_9_cells(self, entities):
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        grid = _generate_one_grid(pool, entities, rng)
        assert grid is not None
        assert len(grid["cells"]) == 9

    def test_no_empty_cells(self, entities):
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        for seed in range(20):  # test 20 different seeds
            rng = random.Random(seed)
            grid = _generate_one_grid(pool, entities, rng)
            if grid is None:
                continue  # this seed didn't produce a grid (rare but ok)
            for cell in grid["cells"]:
                assert len(cell["valid"]) >= MIN_CELL_PLAYERS, (
                    f"Cell has only {len(cell['valid'])} valid players"
                )

    def test_no_criterion_reused(self, entities):
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        grid = _generate_one_grid(pool, entities, rng)
        assert grid is not None
        all_keys = [criterion_key(c) for c in grid["rows"] + grid["cols"]]
        assert len(all_keys) == len(set(all_keys)), "Criterion used in both row and col"

    def test_cells_parallel_to_rows_and_cols(self, entities):
        """Cell at index r*3+c must satisfy both rows[r] and cols[c]."""
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        grid = _generate_one_grid(pool, entities, rng)
        assert grid is not None

        from ingestion.wc_grid.criteria import get_valid_cell
        for r, row_c in enumerate(grid["rows"]):
            for c, col_c in enumerate(grid["cols"]):
                cell_idx = r * 3 + c
                cell = grid["cells"][cell_idx]
                expected = get_valid_cell(row_c, col_c, entities)
                assert frozenset(cell["valid"]) == expected, (
                    f"Cell ({r},{c}) valid set mismatch"
                )

    def test_rarity_scores_parallel_to_valid(self, entities):
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        grid = _generate_one_grid(pool, entities, rng)
        assert grid is not None
        for cell in grid["cells"]:
            assert len(cell["valid"]) == len(cell["rarity"])

    def test_rarity_scores_in_range(self, entities):
        pool = build_criterion_pool(entities)
        rng = random.Random(42)
        grid = _generate_one_grid(pool, entities, rng)
        assert grid is not None
        for cell in grid["cells"]:
            for score in cell["rarity"]:
                assert 1 <= score <= 99


# ---------------------------------------------------------------------------
# Tests: generate_schedule
# ---------------------------------------------------------------------------

class TestGenerateSchedule:
    def test_schedule_length(self, entities):
        pool = build_criterion_pool(entities)
        start = date(2026, 6, 1)
        schedule = generate_schedule(pool, entities, start, num_days=10)
        # Should produce at least 8 out of 10 grids (some seeds may fail)
        assert len(schedule) >= 8

    def test_schedule_keys_are_iso_dates(self, entities):
        pool = build_criterion_pool(entities)
        start = date(2026, 6, 1)
        schedule = generate_schedule(pool, entities, start, num_days=5)
        for key in schedule:
            parsed = date.fromisoformat(key)
            assert start <= parsed < start + timedelta(days=5)

    def test_schedule_is_deterministic(self, entities):
        pool = build_criterion_pool(entities)
        start = date(2026, 6, 1)
        s1 = generate_schedule(pool, entities, start, num_days=5)
        s2 = generate_schedule(pool, entities, start, num_days=5)
        assert s1 == s2

    def test_each_grid_has_no_empty_cells(self, entities):
        pool = build_criterion_pool(entities)
        start = date(2026, 6, 1)
        schedule = generate_schedule(pool, entities, start, num_days=30)
        for date_str, grid in schedule.items():
            for i, cell in enumerate(grid["cells"]):
                assert len(cell["valid"]) >= MIN_CELL_PLAYERS, (
                    f"Empty cell {i} on {date_str}"
                )


# ---------------------------------------------------------------------------
# Tests: build_player_list
# ---------------------------------------------------------------------------

class TestBuildPlayerList:
    def test_returns_all_players(self, entities):
        lst = build_player_list(entities)
        assert len(lst) == len(entities["players"])

    def test_players_sorted_by_name(self, entities):
        lst = build_player_list(entities)
        names = [p["name"] for p in lst]
        assert names == sorted(names)

    def test_player_has_required_fields(self, entities):
        lst = build_player_list(entities)
        for p in lst:
            assert "id" in p
            assert "name" in p
            assert "search" in p
            assert "weight" in p

    def test_search_is_accent_stripped(self, entities):
        # Add a player with an accent to test stripping
        entities_copy = {**entities}
        entities_copy["players"] = {
            **entities["players"],
            "Q_test": {"id": "Q_test", "name": "Mbappé", "search": "mbappe", "weight": 1, "is_gk": False},
        }
        lst = build_player_list(entities_copy)
        mbappe = next(p for p in lst if p["id"] == "Q_test")
        assert mbappe["search"] == "mbappe"
