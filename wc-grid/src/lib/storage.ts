import type { SavedGame, CellState } from '../types';

const LS_KEY = 'wc-grid-vwerkle-v1';

export function loadSavedGame(today: string): SavedGame | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const saved: SavedGame = JSON.parse(raw);
    if (saved.date !== today) return null;
    return saved;
  } catch {
    return null;
  }
}

export function saveGame(game: SavedGame): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(game));
  } catch {
    // localStorage full or disabled — silently ignore
  }
}

export function makeInitialGame(today: string): SavedGame {
  const emptyCells: CellState[] = Array.from({ length: 9 }, () => ({ status: 'empty' }));
  return {
    date: today,
    cellStates: emptyCells,
    usedPlayerIds: [],
    finished: false,
    totalScore: 0,
  };
}
