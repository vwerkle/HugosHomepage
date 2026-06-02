/**
 * Strip diacritics from a string for accent-insensitive search.
 * "Mbappé" → "mbappe", "Müller" → "muller"
 */
export function normalize(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}
