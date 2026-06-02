const STORAGE_KEY = 'moneyline-vwerkle-v1';

let gameData = null;
let state = null;

function scoreGuess(question, guess, actual) {
  if (actual === 0) return guess === 0 ? 100 : 0;
  if (guess === actual) return 100;

  // Percentage questions: score on absolute point difference, not relative error.
  // Being off by 1.7pp (e.g. 5 vs 6.7) should score ~95.
  if (/percent|%/i.test(question)) {
    const absDiff = Math.abs(guess - actual);
    return Math.max(0, Math.min(99, Math.round(100 - absDiff * 3)));
  }

  // Regular numbers: soften the penalty for small actuals so that being off by
  // a couple units on a "5 rounds" question isn't catastrophic.
  const pctError = Math.abs(guess - actual) / Math.abs(actual) * 100;
  const mult = Math.abs(actual) <= 50 ? 1.0
             : Math.abs(actual) <= 500 ? 1.5
             : 2.0;
  return Math.max(0, Math.min(99, Math.round(100 - pctError * mult)));
}

function fmt(n) {
  return Number(n).toLocaleString();
}

function scoreEmoji(score) {
  if (score >= 80) return '🟩';
  if (score >= 40) return '🟨';
  return '🟥';
}

function scoreClass(score) {
  if (score >= 80) return 'score-green';
  if (score >= 40) return 'score-yellow';
  return 'score-red';
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

// ── Landing ────────────────────────────────────────────────────────────────
function showLanding() {
  document.getElementById('landing-sub').textContent = `#${gameData.game_number} · ${gameData.rounds.length} rounds`;
  showScreen('screen-landing');
}

function startGame() {
  showQuestion();
}

// ── Question ───────────────────────────────────────────────────────────────
function buildDots() {
  const idx = state.results.length;
  const total = gameData.rounds.length;
  const el = document.getElementById('progress-dots');
  el.innerHTML = '';
  for (let i = 0; i < total; i++) {
    const dot = document.createElement('div');
    dot.className = 'dot';
    if (i < idx) {
      const s = state.results[i].score;
      dot.classList.add(s >= 80 ? 'dot-green' : s >= 40 ? 'dot-yellow' : 'dot-red');
    } else if (i === idx) {
      dot.classList.add('dot-active');
    }
    el.appendChild(dot);
  }
}

function showQuestion() {
  const idx = state.results.length;
  const round = gameData.rounds[idx];

  buildDots();
  document.getElementById('q-number').textContent = `${idx + 1} / ${gameData.rounds.length}`;
  document.getElementById('q-category').textContent = round.category;
  document.getElementById('q-text').textContent = round.question;

  const input = document.getElementById('guess-input');
  input.value = '';
  document.getElementById('guess-formatted').textContent = '';
  document.getElementById('submit-btn').disabled = false;

  showScreen('screen-question');
  setTimeout(() => input.focus(), 50);
}

function submitGuess() {
  const input = document.getElementById('guess-input');
  const raw = input.value.replace(/,/g, '').trim();
  if (raw === '' || isNaN(raw)) { input.focus(); return; }

  const guess = parseFloat(raw);
  const idx = state.results.length;
  const round = gameData.rounds[idx];
  const score = scoreGuess(round.question, guess, round.actual_value);

  state.results.push({
    round_number: round.round_number,
    category: round.category,
    question: round.question,
    guess,
    actual: round.actual_value,
    score,
  });
  saveState();
  showResult(state.results[state.results.length - 1]);
}

// ── Result card ────────────────────────────────────────────────────────────
function showResult(result) {
  const isLast = state.results.length === gameData.rounds.length;

  const scoreEl = document.getElementById('result-score');
  scoreEl.textContent = `${result.score}/100`;
  scoreEl.className = `result-score ${scoreClass(result.score)}`;

  document.getElementById('result-question').textContent = result.question;
  document.getElementById('result-your-guess').textContent = fmt(result.guess);
  document.getElementById('result-actual').textContent = fmt(result.actual);

  const nextBtn = document.getElementById('next-btn');
  nextBtn.textContent = isLast ? 'See Results' : 'Next';
  nextBtn.onclick = isLast ? finishGame : showQuestion;

  showScreen('screen-result');
}

// ── Final results ──────────────────────────────────────────────────────────
function finishGame() {
  const total = state.results.reduce((s, r) => s + r.score, 0);
  state.finished = true;
  state.totalScore = total;
  saveState();
  showFinalResults();
}

function showFinalResults() {
  const total = state.totalScore ?? state.results.reduce((s, r) => s + r.score, 0);
  const max = gameData.rounds.length * 100;

  document.getElementById('final-game-number').textContent = `Moneyline #${state.gameNumber}`;
  document.getElementById('final-score').textContent = `${total} / ${max}`;

  const list = document.getElementById('rounds-list');
  list.innerHTML = '';
  state.results.forEach(r => {
    const row = document.createElement('div');
    row.className = 'round-row';
    row.innerHTML = `
      <span class="round-emoji">${scoreEmoji(r.score)}</span>
      <span class="round-category">${r.category}</span>
      <span class="round-guesses">${fmt(r.guess)} → ${fmt(r.actual)}</span>
      <span class="round-score ${scoreClass(r.score)}">${r.score}/100</span>
    `;
    list.appendChild(row);
  });

  showScreen('screen-final');
}

// ── Share ──────────────────────────────────────────────────────────────────
function share() {
  const total = state.totalScore ?? state.results.reduce((s, r) => s + r.score, 0);
  const max = gameData.rounds.length * 100;
  const emojis = state.results.map(r => scoreEmoji(r.score)).join('');
  const text = `🏈 Moneyline #${state.gameNumber}\n${total}/${max}\n\n${emojis}\n\nvwerkle.com/moneyline`;

  if (navigator.share) {
    navigator.share({ text }).catch(() => copyToClipboard(text));
  } else {
    copyToClipboard(text);
  }
}

function copyToClipboard(text) {
  const btn = document.getElementById('share-btn');
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Share Results'; }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Share Results'; }, 2000);
  });
}

// ── Input formatting ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('guess-input').addEventListener('input', () => {
    const raw = document.getElementById('guess-input').value.replace(/,/g, '');
    const num = parseFloat(raw);
    document.getElementById('guess-formatted').textContent =
      raw !== '' && !isNaN(num) ? fmt(num) : '';
  });

  document.getElementById('guess-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') submitGuess();
  });
});

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  try {
    const resp = await fetch('/moneyline/api/daily-game');
    if (!resp.ok) throw new Error('API error');
    gameData = await resp.json();
  } catch {
    showScreen('screen-error');
    return;
  }

  state = loadState();

  if (state && state.gameNumber === gameData.game_number) {
    if (state.finished) { showFinalResults(); return; }
    if (state.results.length > 0) { showQuestion(); return; }
  } else {
    state = {
      gameNumber: gameData.game_number,
      results: [],
      finished: false,
    };
    saveState();
  }

  showLanding();
}

init();
