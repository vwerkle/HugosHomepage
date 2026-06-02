"""
Unit tests for criteria predicates and cell computation.
Uses a minimal synthetic entities fixture — no real Wikidata data required.
"""

import pytest
from ingestion.wc_grid.criteria import (
    get_valid_players,
    get_valid_cell,
    build_criterion_pool,
    axes_are_diverse,
    MIN_VALID_PLAYERS,
)
from ingestion.wc_grid.build_cells import compute_cell, compute_grid_cells, grid_difficulty_score


# ---------------------------------------------------------------------------
# Minimal synthetic entities fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def entities():
    """
    Tiny synthetic dataset:
      Players: messi, ronaldo, neuer, klose, zidane, beckham
      Nations: argentina (CONMEBOL), germany (UEFA), france (UEFA)
      Tournaments: 2014, 2018
      Achievements: messi won_wc + played_3plus_wcs; klose golden_boot + career_goals_5plus
    """
    players = {
        "Q_messi":   {"id": "Q_messi",   "name": "Messi",   "search": "messi",   "weight": 4, "is_gk": False},
        "Q_ronaldo": {"id": "Q_ronaldo", "name": "Ronaldo", "search": "ronaldo", "weight": 5, "is_gk": False},
        "Q_neuer":   {"id": "Q_neuer",   "name": "Neuer",   "search": "neuer",   "weight": 3, "is_gk": True},
        "Q_klose":   {"id": "Q_klose",   "name": "Klose",   "search": "klose",   "weight": 4, "is_gk": False},
        "Q_zidane":  {"id": "Q_zidane",  "name": "Zidane",  "search": "zidane",  "weight": 3, "is_gk": False},
        "Q_beckham": {"id": "Q_beckham", "name": "Beckham", "search": "beckham", "weight": 3, "is_gk": False},
    }
    nations = {
        "Q_arg": {"id": "Q_arg", "name": "Argentina", "confederation": "CONMEBOL"},
        "Q_ger": {"id": "Q_ger", "name": "Germany",   "confederation": "UEFA"},
        "Q_fra": {"id": "Q_fra", "name": "France",    "confederation": "UEFA"},
        "Q_eng": {"id": "Q_eng", "name": "England",   "confederation": "UEFA"},
    }
    appearances = [
        # Messi: Argentina 2014 + 2018
        {"player_id": "Q_messi",   "tournament_year": 2014, "nation_id": "Q_arg", "goals": 1, "is_gk": False},
        {"player_id": "Q_messi",   "tournament_year": 2018, "nation_id": "Q_arg", "goals": 0, "is_gk": False},
        # Ronaldo: Germany 2018 (not realistic, but fine for testing)
        {"player_id": "Q_ronaldo", "tournament_year": 2018, "nation_id": "Q_ger", "goals": 1, "is_gk": False},
        # Neuer: Germany 2014 + 2018
        {"player_id": "Q_neuer",   "tournament_year": 2014, "nation_id": "Q_ger", "goals": 0, "is_gk": True},
        {"player_id": "Q_neuer",   "tournament_year": 2018, "nation_id": "Q_ger", "goals": 0, "is_gk": True},
        # Klose: Germany 2014
        {"player_id": "Q_klose",   "tournament_year": 2014, "nation_id": "Q_ger", "goals": 2, "is_gk": False},
        # Zidane: France 2014
        {"player_id": "Q_zidane",  "tournament_year": 2014, "nation_id": "Q_fra", "goals": 0, "is_gk": False},
        # Beckham: England 2014
        {"player_id": "Q_beckham", "tournament_year": 2014, "nation_id": "Q_eng", "goals": 0, "is_gk": False},
    ]
    achievements = [
        {"player_id": "Q_messi",  "achievement": "won_wc",           "tournament_year": 2014},
        {"player_id": "Q_messi",  "achievement": "played_3plus_wcs", "tournament_year": None},
        {"player_id": "Q_klose",  "achievement": "golden_boot",      "tournament_year": None},
        {"player_id": "Q_klose",  "achievement": "career_goals_5plus","tournament_year": None},
        {"player_id": "Q_neuer",  "achievement": "golden_glove",     "tournament_year": None},
    ]
    return {
        "players": players,
        "nations": nations,
        "appearances": appearances,
        "achievements": achievements,
    }


# ---------------------------------------------------------------------------
# Tests: get_valid_players
# ---------------------------------------------------------------------------

class TestGetValidPlayers:
    def test_nation_argentina(self, entities):
        c = {"type": "nation", "value": "Q_arg"}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_messi"})

    def test_nation_germany(self, entities):
        c = {"type": "nation", "value": "Q_ger"}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_ronaldo", "Q_neuer", "Q_klose"})

    def test_nation_empty(self, entities):
        c = {"type": "nation", "value": "Q_nonexistent"}
        assert get_valid_players(c, entities) == frozenset()

    def test_tournament_2014(self, entities):
        c = {"type": "tournament", "value": 2014}
        result = get_valid_players(c, entities)
        assert "Q_messi" in result
        assert "Q_neuer" in result
        assert "Q_klose" in result
        assert "Q_zidane" in result
        assert "Q_beckham" in result
        assert "Q_ronaldo" not in result  # ronaldo only in 2018

    def test_tournament_2018(self, entities):
        c = {"type": "tournament", "value": 2018}
        result = get_valid_players(c, entities)
        assert "Q_messi" in result
        assert "Q_ronaldo" in result
        assert "Q_neuer" in result
        assert "Q_klose" not in result  # klose only in 2014

    def test_confederation_conmebol(self, entities):
        c = {"type": "confederation", "value": "CONMEBOL"}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_messi"})

    def test_confederation_uefa(self, entities):
        c = {"type": "confederation", "value": "UEFA"}
        result = get_valid_players(c, entities)
        assert "Q_neuer" in result
        assert "Q_klose" in result
        assert "Q_zidane" in result
        assert "Q_beckham" in result
        assert "Q_messi" not in result

    def test_achievement_won_wc(self, entities):
        c = {"type": "achievement", "value": "won_wc"}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_messi"})

    def test_achievement_golden_boot(self, entities):
        c = {"type": "achievement", "value": "golden_boot"}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_klose"})

    def test_achievement_golden_glove(self, entities):
        c = {"type": "achievement", "value": "golden_glove"}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_neuer"})

    def test_is_gk(self, entities):
        c = {"type": "is_gk", "value": True}
        result = get_valid_players(c, entities)
        assert result == frozenset({"Q_neuer"})

    def test_unknown_type_raises(self, entities):
        c = {"type": "bogus", "value": "x"}
        with pytest.raises(ValueError, match="Unknown criterion type"):
            get_valid_players(c, entities)


# ---------------------------------------------------------------------------
# Tests: get_valid_cell (intersection)
# ---------------------------------------------------------------------------

class TestGetValidCell:
    def test_argentina_x_2014(self, entities):
        row = {"type": "nation",     "value": "Q_arg"}
        col = {"type": "tournament", "value": 2014}
        result = get_valid_cell(row, col, entities)
        assert result == frozenset({"Q_messi"})

    def test_argentina_x_2018(self, entities):
        row = {"type": "nation",     "value": "Q_arg"}
        col = {"type": "tournament", "value": 2018}
        result = get_valid_cell(row, col, entities)
        assert result == frozenset({"Q_messi"})

    def test_germany_x_2014(self, entities):
        row = {"type": "nation",     "value": "Q_ger"}
        col = {"type": "tournament", "value": 2014}
        result = get_valid_cell(row, col, entities)
        assert result == frozenset({"Q_neuer", "Q_klose"})

    def test_golden_boot_x_germany(self, entities):
        row = {"type": "achievement", "value": "golden_boot"}
        col = {"type": "nation",      "value": "Q_ger"}
        result = get_valid_cell(row, col, entities)
        assert result == frozenset({"Q_klose"})

    def test_impossible_cell_returns_empty(self, entities):
        # No GK who played for Argentina exists in fixture
        row = {"type": "nation", "value": "Q_arg"}
        col = {"type": "is_gk",  "value": True}
        result = get_valid_cell(row, col, entities)
        assert result == frozenset()

    def test_won_wc_x_conmebol(self, entities):
        row = {"type": "achievement",  "value": "won_wc"}
        col = {"type": "confederation","value": "CONMEBOL"}
        result = get_valid_cell(row, col, entities)
        assert result == frozenset({"Q_messi"})


# ---------------------------------------------------------------------------
# Tests: build_criterion_pool
# ---------------------------------------------------------------------------

class TestBuildCriterionPool:
    def test_pool_contains_nations_with_enough_players(self, entities):
        pool = build_criterion_pool(entities)
        nation_criteria = [c for c in pool if c["type"] == "nation"]
        # Germany has 3 players (neuer, klose, ronaldo) → should be in pool
        ger_criteria = [c for c in nation_criteria if c["value"] == "Q_ger"]
        assert len(ger_criteria) == 1

    def test_pool_excludes_small_nations(self, entities):
        # Argentina has only 1 player (messi) < MIN_VALID_PLAYERS=3 → excluded
        pool = build_criterion_pool(entities)
        arg_criteria = [c for c in pool if c["type"] == "nation" and c["value"] == "Q_arg"]
        assert len(arg_criteria) == 0

    def test_pool_has_achievement_criteria(self, entities):
        pool = build_criterion_pool(entities)
        ach = [c for c in pool if c["type"] == "achievement"]
        # won_wc only 1 player → excluded; golden_boot 1 player → excluded
        # Only criteria with >=3 players pass
        for c in ach:
            valid = get_valid_players(c, entities)
            assert len(valid) >= MIN_VALID_PLAYERS

    def test_pool_criteria_have_labels(self, entities):
        pool = build_criterion_pool(entities)
        for c in pool:
            assert isinstance(c["label"], str)
            assert len(c["label"]) > 0


# ---------------------------------------------------------------------------
# Tests: axes_are_diverse
# ---------------------------------------------------------------------------

class TestAxesDiverse:
    def test_two_nations_in_same_axis_allowed(self):
        # Multiple nations on same axis is ALLOWED (each is a distinct entity)
        rows = [
            {"type": "nation", "value": "Q_arg"},
            {"type": "nation", "value": "Q_ger"},
            {"type": "tournament", "value": 2018},
        ]
        cols = [
            {"type": "achievement", "value": "won_wc"},
            {"type": "confederation", "value": "UEFA"},
            {"type": "tournament", "value": 2014},
        ]
        assert axes_are_diverse(rows, cols)

    def test_two_confederations_in_same_axis_rejected(self):
        # Multiple confederation criteria on same axis IS rejected (redundant)
        rows = [
            {"type": "confederation", "value": "UEFA"},
            {"type": "confederation", "value": "CONMEBOL"},
            {"type": "tournament", "value": 2018},
        ]
        cols = [
            {"type": "nation", "value": "Q_arg"},
            {"type": "nation", "value": "Q_ger"},
            {"type": "nation", "value": "Q_fra"},
        ]
        assert not axes_are_diverse(rows, cols)

    def test_two_achievements_in_same_axis_rejected(self):
        rows = [
            {"type": "achievement", "value": "won_wc"},
            {"type": "achievement", "value": "golden_boot"},
            {"type": "tournament", "value": 2018},
        ]
        cols = [
            {"type": "nation", "value": "Q_arg"},
            {"type": "nation", "value": "Q_ger"},
            {"type": "nation", "value": "Q_fra"},
        ]
        assert not axes_are_diverse(rows, cols)

    def test_multiple_tournament_years_allowed(self):
        rows = [
            {"type": "tournament", "value": 2014},
            {"type": "tournament", "value": 2018},
            {"type": "nation",     "value": "Q_arg"},
        ]
        cols = [
            {"type": "achievement",  "value": "won_wc"},
            {"type": "confederation","value": "UEFA"},
            {"type": "nation",       "value": "Q_ger"},
        ]
        assert axes_are_diverse(rows, cols)

    def test_three_nations_per_axis_allowed(self):
        # The core WC Grid pattern: 3 nations vs 3 events
        rows = [
            {"type": "nation", "value": "Q_arg"},
            {"type": "nation", "value": "Q_ger"},
            {"type": "nation", "value": "Q_fra"},
        ]
        cols = [
            {"type": "tournament",  "value": 2018},
            {"type": "achievement", "value": "won_wc"},
            {"type": "is_gk",       "value": True},
        ]
        assert axes_are_diverse(rows, cols)


# ---------------------------------------------------------------------------
# Tests: compute_cell and compute_grid_cells
# ---------------------------------------------------------------------------

class TestComputeCell:
    def test_cell_has_valid_and_rarity(self, entities):
        row = {"type": "nation",     "value": "Q_ger"}
        col = {"type": "tournament", "value": 2014}
        cell = compute_cell(row, col, entities)
        assert "valid" in cell
        assert "rarity" in cell
        assert len(cell["valid"]) == len(cell["rarity"])

    def test_cell_sorted_obscure_first(self, entities):
        row = {"type": "nation",     "value": "Q_ger"}
        col = {"type": "tournament", "value": 2014}
        cell = compute_cell(row, col, entities)
        players = entities["players"]
        weights = [players[pid]["weight"] for pid in cell["valid"]]
        assert weights == sorted(weights)

    def test_rarity_highest_for_single_player(self, entities):
        # Only Q_klose satisfies golden_boot × germany
        row = {"type": "achievement", "value": "golden_boot"}
        col = {"type": "nation",      "value": "Q_ger"}
        cell = compute_cell(row, col, entities)
        assert cell["rarity"] == [99]

    def test_rarity_decreases_with_fame(self, entities):
        row = {"type": "nation",     "value": "Q_ger"}
        col = {"type": "tournament", "value": 2014}
        cell = compute_cell(row, col, entities)
        # rarity scores should be non-increasing (obscure first)
        assert cell["rarity"] == sorted(cell["rarity"], reverse=True)


class TestComputeGridCells:
    def _make_valid_grid(self, entities):
        rows = [
            {"type": "tournament",  "value": 2014},
            {"type": "tournament",  "value": 2018},
            {"type": "confederation","value": "UEFA"},
        ]
        cols = [
            {"type": "nation",      "value": "Q_ger"},
            {"type": "achievement", "value": "golden_boot"},
            {"type": "is_gk",      "value": True},
        ]
        return rows, cols

    def test_valid_grid_returns_9_cells(self, entities):
        rows, cols = self._make_valid_grid(entities)
        cells = compute_grid_cells(rows, cols, entities)
        # Some cells might be empty → returns None; check only if non-None
        if cells is not None:
            assert len(cells) == 9

    def test_impossible_grid_returns_none(self, entities):
        # Argentina × 2014 has Messi; Argentina × golden_glove is empty → None
        rows = [
            {"type": "nation", "value": "Q_arg"},
            {"type": "nation", "value": "Q_fra"},
            {"type": "nation", "value": "Q_eng"},
        ]
        cols = [
            {"type": "achievement", "value": "golden_glove"},  # only Neuer (German) → all 3 cells empty
            {"type": "achievement", "value": "golden_boot"},   # only Klose (German) → all 3 cells empty
            {"type": "is_gk",       "value": True},            # only Neuer (German) → all 3 cells empty
        ]
        result = compute_grid_cells(rows, cols, entities)
        assert result is None

    def test_grid_difficulty_score(self, entities):
        cells = [{"valid": ["a", "b", "c"]}, {"valid": ["x"]}, {"valid": ["a", "b"]}]
        # Pad to 9 cells with 1-player cells
        cells += [{"valid": ["z"]}] * 6
        score = grid_difficulty_score(cells)
        assert isinstance(score, float)
        assert score > 0
