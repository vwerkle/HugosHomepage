import type { CellState } from '../types';

interface Props {
  cellIndex: number;
  state: CellState;
  isActive: boolean;
  isFinished: boolean;
  onClick: () => void;
}

export function Cell({ state, isActive, isFinished, onClick }: Props) {
  const canClick = state.status === 'empty' && !isFinished;

  let className = 'cell';
  if (state.status === 'correct') className += ' cell-correct';
  else if (state.status === 'wrong') className += ' cell-wrong';
  else if (isActive) className += ' cell-active';
  else if (canClick) className += ' cell-empty';
  else className += ' cell-empty cell-locked';

  return (
    <div
      className={className}
      onClick={canClick ? onClick : undefined}
      role={canClick ? 'button' : undefined}
      tabIndex={canClick ? 0 : undefined}
      onKeyDown={canClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      {state.status === 'correct' && (
        <>
          <div className="cell-player">{state.playerName}</div>
          <div className="cell-score">{state.rarityScore}</div>
        </>
      )}
      {state.status === 'wrong' && (
        <>
          <div className="cell-wrong-mark">✗</div>
          <div className="cell-player cell-player-wrong">{state.playerName}</div>
        </>
      )}
      {state.status === 'empty' && !isActive && (
        <div className="cell-placeholder">?</div>
      )}
      {state.status === 'empty' && isActive && (
        <div className="cell-placeholder cell-placeholder-active">…</div>
      )}
    </div>
  );
}
