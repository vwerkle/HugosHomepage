import { useEffect, useRef, useState } from 'react';
import type { Player } from '../types';
import { normalize } from '../lib/normalize';

interface Props {
  players: Player[];
  usedPlayerIds: Set<string>;
  onSelect: (player: Player) => void;
  onCancel: () => void;
}

const MAX_RESULTS = 50;

export function PlayerSearch({ players, usedPlayerIds, onSelect, onCancel }: Props) {
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const normalizedQuery = normalize(query.trim());
  const filtered = normalizedQuery.length < 1
    ? []
    : players
        .filter(p => !usedPlayerIds.has(p.id) && p.search.includes(normalizedQuery))
        .slice(0, MAX_RESULTS);

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape') { onCancel(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlighted(h => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted(h => Math.max(h - 1, 0));
    } else if (e.key === 'Enter' && filtered[highlighted]) {
      onSelect(filtered[highlighted]);
    }
  }

  useEffect(() => {
    setHighlighted(0);
  }, [query]);

  useEffect(() => {
    const el = listRef.current?.children[highlighted] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlighted]);

  return (
    <div className="player-search">
      <input
        ref={inputRef}
        className="search-input"
        placeholder="Type a player name…"
        value={query}
        onChange={e => setQuery(e.target.value)}
        onKeyDown={handleKey}
      />
      {filtered.length > 0 && (
        <ul ref={listRef} className="search-dropdown">
          {filtered.map((p, i) => (
            <li
              key={p.id}
              className={i === highlighted ? 'highlighted' : ''}
              onMouseEnter={() => setHighlighted(i)}
              onMouseDown={e => { e.preventDefault(); onSelect(p); }}
            >
              {p.name}
            </li>
          ))}
        </ul>
      )}
      {normalizedQuery.length > 0 && filtered.length === 0 && (
        <div className="search-empty">No players found</div>
      )}
    </div>
  );
}
