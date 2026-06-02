import { useState } from 'react';
import type { CellState } from '../types';
import { buildShareText } from '../lib/scoring';

interface Props {
  cellStates: CellState[];
  totalScore: number;
  date: string;
  onClose: () => void;
}

export function ShareModal({ cellStates, totalScore, date, onClose }: Props) {
  const [copied, setCopied] = useState(false);
  const text = buildShareText(cellStates, totalScore, date);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: select the textarea
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Game Over</h2>
        <div className="final-score">Score: {totalScore} / 891</div>
        <pre className="share-text">{text}</pre>
        <div className="modal-buttons">
          <button className="btn-copy" onClick={handleCopy}>
            {copied ? '✓ Copied!' : '📋 Copy'}
          </button>
          <button className="btn-close" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
