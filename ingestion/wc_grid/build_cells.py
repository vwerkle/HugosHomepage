"""
Pre-compute valid player sets and rarity scores for every cell in a 3x3 grid.

A grid has 3 row criteria and 3 column criteria.
Cell (r, c) is valid iff: get_valid_cell(row[r], col[c]) is non-empty.

Rarity score for choosing player P in cell (r, c):
  score = round(100 * (1 - rank / total))
  where rank = player's position (0-indexed, ascending by weight) among valid players,
  and total = number of valid players in that cell.
  Higher weight (more WC appearances) → lower rarity score.
  Minimum score is 1 (the most famous player), maximum is 99 (most obscure in cell).
"""

from __future__ import annotations

from .criteria import get_valid_cell


def compute_cell(
    criterion_row: dict,
    criterion_col: dict,
    entities: dict,
) -> dict:
    """
    Compute a single cell: valid player IDs sorted by rarity (most obscure first),
    alongside their rarity scores.

    Returns:
        {
          "valid": ["Q456", "Q789", ...],   # player IDs, obscure→famous
          "rarity": [99, 72, ...]            # parallel rarity scores
        }
    """
    players = entities["players"]
    valid_ids = get_valid_cell(criterion_row, criterion_col, entities)

    # Sort by weight ascending (low weight = fewer WC apps = more obscure)
    sorted_ids = sorted(valid_ids, key=lambda pid: players[pid].get("weight", 0))
    total = len(sorted_ids)

    rarity_scores = []
    for rank, _pid in enumerate(sorted_ids):
        if total == 1:
            score = 99
        else:
            score = max(1, round(99 * (1 - rank / (total - 1))))
        rarity_scores.append(score)

    return {
        "valid": sorted_ids,
        "rarity": rarity_scores,
    }


def compute_grid_cells(
    row_criteria: list[dict],
    col_criteria: list[dict],
    entities: dict,
) -> list[dict] | None:
    """
    Compute all 9 cells for a 3x3 grid.

    Returns list of 9 cell dicts (row-major order) if every cell has >=1 valid player,
    or None if any cell is empty (grid is invalid).
    """
    cells = []
    for r, row_c in enumerate(row_criteria):
        for c, col_c in enumerate(col_criteria):
            cell = compute_cell(row_c, col_c, entities)
            if not cell["valid"]:
                return None  # reject this grid
            cells.append(cell)
    return cells


def grid_difficulty_score(cells: list[dict]) -> float:
    """
    Average cell size across all 9 cells.
    Targets: 5–80 valid players per cell.
    Returns the average; caller filters to desired range.
    """
    return sum(len(c["valid"]) for c in cells) / len(cells)
