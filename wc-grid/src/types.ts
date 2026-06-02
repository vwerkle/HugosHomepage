export interface Player {
  id: string;
  name: string;
  search: string;
  weight: number;
}

export interface Criterion {
  type: string;
  value: string | number | boolean;
  label: string;
}

export interface CellData {
  valid: string[];
  rarity: number[];
}

export interface DayGrid {
  rows: Criterion[];
  cols: Criterion[];
  cells: CellData[];  // row-major: cell[r*3+c]
}

export interface Bundle {
  players: Player[];
  grids: Record<string, DayGrid>;
  meta: {
    generated: string;
    start: string;
    days: number;
    player_count: number;
    grid_count: number;
  };
}

export type CellStatus = 'empty' | 'correct' | 'wrong';

export interface CellState {
  status: CellStatus;
  playerId?: string;
  playerName?: string;
  rarityScore?: number;
}

export interface SavedGame {
  date: string;
  cellStates: CellState[];
  usedPlayerIds: string[];
  finished: boolean;
  totalScore: number;
}
