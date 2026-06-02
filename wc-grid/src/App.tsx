import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import type { Bundle, CellState, DayGrid, Player } from './types';
import { Cell } from './components/Cell';
import { PlayerSearch } from './components/PlayerSearch';
import { ShareModal } from './components/ShareModal';
import { loadSavedGame, saveGame, makeInitialGame } from './lib/storage';
import { getRarityScore, computeTotalScore } from './lib/scoring';
import './App.css';

const BUNDLE_URL = `${import.meta.env.BASE_URL}data/bundle.json`;

function getTodayString(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [grid, setGrid] = useState<DayGrid | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cellStates, setCellStates] = useState<CellState[]>([]);
  const [usedPlayerIds, setUsedPlayerIds] = useState<Set<string>>(new Set());
  const [activeCell, setActiveCell] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [totalScore, setTotalScore] = useState(0);
  const [showShare, setShowShare] = useState(false);
  const today = useRef(getTodayString()).current;

  useEffect(() => {
    fetch(BUNDLE_URL)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Bundle>;
      })
      .then(data => {
        setBundle(data);
        const dayGrid = data.grids[today];
        if (!dayGrid) {
          setLoadError(`No puzzle for ${today}. Please regenerate the bundle.`);
          return;
        }
        setGrid(dayGrid);
        const saved = loadSavedGame(today);
        if (saved) {
          setCellStates(saved.cellStates);
          setUsedPlayerIds(new Set(saved.usedPlayerIds));
          setFinished(saved.finished);
          setTotalScore(saved.totalScore);
        } else {
          setCellStates(makeInitialGame(today).cellStates);
        }
      })
      .catch(err => setLoadError(`Failed to load puzzle: ${err.message}`));
  }, [today]);

  const handleCellClick = useCallback((cellIdx: number) => {
    if (finished || cellStates[cellIdx]?.status !== 'empty') return;
    setActiveCell(prev => prev === cellIdx ? null : cellIdx);
  }, [finished, cellStates]);

  const handlePlayerSelect = useCallback((player: Player) => {
    if (activeCell === null || !grid) return;

    const cell = grid.cells[activeCell];
    const isCorrect = cell.valid.includes(player.id) && !usedPlayerIds.has(player.id);
    const rarityScore = isCorrect ? getRarityScore(player.id, cell) : 0;

    const newUsed = new Set(usedPlayerIds);
    if (isCorrect) newUsed.add(player.id);
    setUsedPlayerIds(newUsed);

    setCellStates(prev => {
      const next = [...prev];
      next[activeCell] = {
        status: isCorrect ? 'correct' : 'wrong',
        playerId: player.id,
        playerName: player.name,
        rarityScore: isCorrect ? rarityScore : undefined,
      };
      const allFilled = next.every(cs => cs.status !== 'empty');
      const newScore = computeTotalScore(next);
      setTotalScore(newScore);
      if (allFilled) { setFinished(true); setShowShare(true); }
      saveGame({ date: today, cellStates: next, usedPlayerIds: [...newUsed], finished: allFilled, totalScore: newScore });
      return next;
    });

    setActiveCell(null);
  }, [activeCell, grid, usedPlayerIds, today]);

  const handleSearchCancel = useCallback(() => setActiveCell(null), []);

  if (loadError) return (
    <div className="app">
      <header className="app-header"><h1>⚽ WC Grid</h1></header>
      <div className="status-message error">{loadError}</div>
    </div>
  );

  if (!bundle || !grid) return (
    <div className="app">
      <header className="app-header"><h1>⚽ WC Grid</h1></header>
      <div className="status-message">Loading puzzle…</div>
    </div>
  );

  return (
    <div className="app" onClick={activeCell !== null ? () => setActiveCell(null) : undefined}>
      <header className="app-header">
        <div className="header-left">
          <h1>⚽ WC Grid</h1>
          <span className="header-date">{today}</span>
        </div>
        <div className="header-right">
          <span className="score-display">{totalScore} pts</span>
          {finished && (
            <button className="btn-share" onClick={e => { e.stopPropagation(); setShowShare(true); }}>
              Share
            </button>
          )}
        </div>
      </header>

      <main className="game-area" onClick={e => e.stopPropagation()}>
        <div className="grid-wrapper">
          <div className="corner" />
          {grid.cols.map((col, c) => (
            <div key={c} className="col-header">{col.label}</div>
          ))}
          {grid.rows.map((row, r) => (
            <Fragment key={r}>
              <div className="row-header">{row.label}</div>
              {grid.cols.map((_col, c) => {
                const cellIdx = r * 3 + c;
                return (
                  <Cell
                    key={cellIdx}
                    cellIndex={cellIdx}
                    state={cellStates[cellIdx] ?? { status: 'empty' }}
                    isActive={activeCell === cellIdx}
                    isFinished={finished}
                    onClick={() => handleCellClick(cellIdx)}
                  />
                );
              })}
            </Fragment>
          ))}
        </div>

        {activeCell !== null && (
          <div className="search-area" onClick={e => e.stopPropagation()}>
            <PlayerSearch
              players={bundle.players}
              usedPlayerIds={usedPlayerIds}
              onSelect={handlePlayerSelect}
              onCancel={handleSearchCancel}
            />
          </div>
        )}

        {!finished && (
          <p className="instructions">
            Click a cell and type a player name. One guess per cell.
            Obscure picks score higher (max 99 pts/cell, 891 total).
          </p>
        )}
      </main>

      {showShare && (
        <ShareModal
          cellStates={cellStates}
          totalScore={totalScore}
          date={today}
          onClose={() => setShowShare(false)}
        />
      )}
    </div>
  );
}
