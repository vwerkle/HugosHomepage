import type { CellData, CellState } from '../types';

/**
 * Given a player ID and a cell's valid/rarity arrays, return the rarity score (1–99).
 * Returns 0 if the player is not in the valid set (shouldn't happen after validation).
 */
export function getRarityScore(playerId: string, cell: CellData): number {
  const idx = cell.valid.indexOf(playerId);
  if (idx === -1) return 0;
  return cell.rarity[idx];
}

/**
 * Total score across all correctly guessed cells.
 */
export function computeTotalScore(cellStates: CellState[]): number {
  return cellStates.reduce((sum, cs) => {
    return cs.status === 'correct' ? sum + (cs.rarityScore ?? 0) : sum;
  }, 0);
}

/**
 * Emoji for share grid: based on rarity score of correct guesses.
 */
export function cellEmoji(cs: CellState): string {
  if (cs.status === 'empty') return '⬜';
  if (cs.status === 'wrong') return '❌';
  const score = cs.rarityScore ?? 0;
  if (score >= 66) return '🟩';
  if (score >= 33) return '🟨';
  return '🟥';
}

/**
 * Generate the share text for the emoji grid.
 */
export function buildShareText(cellStates: CellState[], totalScore: number, date: string): string {
  const emojiRows = [0, 1, 2].map(r =>
    [0, 1, 2].map(c => cellEmoji(cellStates[r * 3 + c])).join('')
  );
  return [
    `⚽ WC Grid ${date}`,
    `Score: ${totalScore}/891`,
    '',
    ...emojiRows,
    '',
    'vwerkle.com/wc-grid',
  ].join('\n');
}
