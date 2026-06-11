// SCORING constant is injected by the server in game.html
const STORAGE_KEY = 'statline-vwerkle-v3';

let puzzleData = null;
let state = null;
let acTimer = null;
let selectedPlayer = null;  // { id, name, value, position } — set by autocomplete pick

// ── Scoring ────────────────────────────────────────────────────────────────

function scoreCategory(guessValue, targetValue, bestValue) {
  const MAX = SCORING.MAX_PER_CATEGORY;
  const EPS = SCORING.ZERO_EPSILON || 0.001;
  const denom = Math.abs(targetValue) > EPS ? Math.abs(targetValue) : EPS;
  const bestGap = Math.abs(bestValue - targetValue);
  const gap = Math.abs(guessValue - targetValue);
  const excess = Math.max(0, gap - bestGap);
  const pctOff = excess / denom;
  return Math.round(MAX * Math.max(0, 1 - pctOff));
}

function maxPerPlayer()  { return SCORING.MAX_PER_CATEGORY; }
function maxPerSport(si) { return puzzleData.sports[si].players.length * maxPerPlayer(); }
function maxTotal() {
  if (!puzzleData) return 0;
  return puzzleData.sports.reduce((sum, _, i) => sum + maxPerSport(i), 0);
}

// ── Formatting ─────────────────────────────────────────────────────────────

function fmtValue(value, fmt) {
  if (value == null) return '—';
  if (fmt === '.2f') return parseFloat(value).toFixed(2);
  if (fmt === '.3f') return parseFloat(value).toFixed(3);
  return Math.round(value).toLocaleString();
}

function scoreEmoji(score) {
  const max = maxPerPlayer();
  if (score >= max * 0.8) return '🟩';
  if (score >= max * 0.4) return '🟨';
  return '🟥';
}

function scoreClass(score) {
  const max = maxPerPlayer();
  if (score >= max * 0.8) return 'score-green';
  if (score >= max * 0.4) return 'score-yellow';
  return 'score-red';
}

// ── State ──────────────────────────────────────────────────────────────────

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function initState() {
  state = {
    gameDate:   puzzleData.date,
    gameNumber: puzzleData.game_number,
    sports: puzzleData.sports.map(s => ({
      sport:       s.sport,
      introSeen:   false,
      summarySeen: false,
      players:     s.players.map(() => null),
    })),
    finished: false,
  };
  saveState();
}

// ── Screen management ──────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

// ── Navigation helpers ─────────────────────────────────────────────────────

function currentSportIdx() {
  for (let i = 0; i < state.sports.length; i++) {
    if (!state.sports[i].summarySeen) return i;
  }
  return state.sports.length - 1;
}

function currentPlayerIdx(sportIdx) {
  return state.sports[sportIdx].players.indexOf(null);
}

function sportPlayersDone(sportIdx) {
  return state.sports[sportIdx].players.every(p => p !== null);
}

function sportScoreFromState(sportSt) {
  return sportSt.players.reduce((sum, p) => sum + (p ? p.score : 0), 0);
}

function totalScore() {
  return state.sports.reduce((sum, s) => sum + sportScoreFromState(s), 0);
}

// ── Progress dots ──────────────────────────────────────────────────────────

function buildDots(sportIdx, activePlayerIdx) {
  const players = state.sports[sportIdx].players;
  const el = document.getElementById('progress-dots');
  el.innerHTML = '';
  players.forEach((p, i) => {
    const dot = document.createElement('div');
    dot.className = 'dot';
    if (p !== null) {
      const pct = p.score / maxPerPlayer();
      dot.classList.add(pct >= 0.8 ? 'dot-green' : pct >= 0.4 ? 'dot-yellow' : 'dot-red');
    } else if (i === activePlayerIdx) {
      dot.classList.add('dot-active');
    }
    el.appendChild(dot);
  });
}

// ── Landing ────────────────────────────────────────────────────────────────

function showLanding() {
  const sports = puzzleData.sports.map(s => s.emoji).join('');
  document.getElementById('landing-sub').textContent =
    `#${puzzleData.game_number} · ${sports} · ${puzzleData.sports.length} sports`;
  showScreen('screen-landing');
}

function startGame() {
  showSportIntro(0);
}

// ── Sport intro ────────────────────────────────────────────────────────────

function showSportIntro(sportIdx) {
  const sp = puzzleData.sports[sportIdx];
  document.getElementById('intro-sport-label').textContent = `${sp.emoji} ${sp.sport_label}`;

  const container = document.getElementById('intro-players');
  container.innerHTML = '';
  sp.players.forEach(player => {
    const cat = player.category;
    const card = document.createElement('div');
    card.className = 'intro-player-card';
    card.innerHTML = `
      <div class="intro-position-label">${escHtml(player.position_label)}</div>
      <div class="intro-player-name">${escHtml(player.target_name)}</div>
      <div class="intro-stat-row">
        <span class="intro-stat-label">${escHtml(cat.label)}</span>
        <span class="intro-stat-value">${fmtValue(cat.target_value, cat.fmt)}</span>
      </div>
    `;
    container.appendChild(card);
  });

  document.getElementById('intro-start-btn').onclick = () => {
    state.sports[sportIdx].introSeen = true;
    saveState();
    showGuess(sportIdx, 0);
  };

  showScreen('screen-sport-intro');
}

// ── Guess ──────────────────────────────────────────────────────────────────

function showGuess(sportIdx, playerIdx) {
  selectedPlayer = null;
  const sp = puzzleData.sports[sportIdx];
  const player = sp.players[playerIdx];
  const cat = player.category;

  buildDots(sportIdx, playerIdx);
  document.getElementById('guess-sport-label').textContent = `${sp.emoji} ${sp.sport_label}`;
  document.getElementById('guess-round-counter').textContent =
    `${playerIdx + 1} / ${sp.players.length}`;
  document.getElementById('guess-player-context').textContent =
    `${player.position_label} · ${player.target_name}`;
  document.getElementById('guess-cat-label').textContent = cat.label;
  document.getElementById('guess-target-value').textContent = fmtValue(cat.target_value, cat.fmt);
  document.getElementById('guess-prompt').textContent =
    `Name a player with ${cat.label} close to ${fmtValue(cat.target_value, cat.fmt)}`;

  const input = document.getElementById('guess-input');
  input.value = '';
  input.disabled = false;
  clearAC();

  const selDisplay = document.getElementById('selected-player-display');
  selDisplay.textContent = '';
  selDisplay.style.display = 'none';
  document.getElementById('submit-btn').disabled = true;

  showScreen('screen-guess');
  setTimeout(() => input.focus(), 80);
}

// ── Autocomplete ───────────────────────────────────────────────────────────

function excludedIds(sportIdx) {
  const sp = puzzleData.sports[sportIdx];
  const targetIds = sp.players.map(p => p.target_id);
  const guessedIds = state.sports[sportIdx].players
    .filter(p => p !== null)
    .map(p => p.guessed_id);
  return new Set([...targetIds, ...guessedIds]);
}

function clearAC() {
  const dd = document.getElementById('autocomplete-dropdown');
  dd.innerHTML = '';
  dd.style.display = 'none';
}

async function fetchAC(sportIdx, playerIdx, query) {
  const sp = puzzleData.sports[sportIdx];
  const player = sp.players[playerIdx];
  const cat = player.category;
  try {
    const url = `/statline/api/autocomplete?sport=${encodeURIComponent(sp.sport)}&category=${encodeURIComponent(cat.key)}&q=${encodeURIComponent(query)}`;
    const resp = await fetch(url);
    const data = await resp.json();
    const excl = excludedIds(sportIdx);
    return data.filter(p => !excl.has(p.id));
  } catch { return []; }
}

function renderAC(results, sportIdx, playerIdx) {
  const dd = document.getElementById('autocomplete-dropdown');
  if (!results.length) { dd.innerHTML = ''; dd.style.display = 'none'; return; }
  dd.innerHTML = '';
  dd.style.display = 'block';
  results.slice(0, 8).forEach(p => {
    const item = document.createElement('div');
    item.className = 'ac-item';
    item.innerHTML = `
      <span class="ac-name">${escHtml(p.name)}</span>
      <span class="ac-pos">${escHtml(p.position)}</span>
    `;
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      selectPlayer(p, sportIdx, playerIdx);
    });
    dd.appendChild(item);
  });
}

function selectPlayer(player, sportIdx, playerIdx) {
  selectedPlayer = player;
  document.getElementById('guess-input').value = player.name;
  clearAC();
  const display = document.getElementById('selected-player-display');
  display.textContent = player.name;
  display.style.display = 'block';
  document.getElementById('submit-btn').disabled = false;
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Submit ─────────────────────────────────────────────────────────────────

function submitGuess() {
  if (!selectedPlayer) return;

  const sportIdx  = currentSportIdx();
  const playerIdx = currentPlayerIdx(sportIdx);
  const player    = puzzleData.sports[sportIdx].players[playerIdx];
  const cat       = player.category;
  const score     = scoreCategory(selectedPlayer.value, cat.target_value, cat.best_value);

  state.sports[sportIdx].players[playerIdx] = {
    guessed_id:    selectedPlayer.id,
    guessed_name:  selectedPlayer.name,
    guessed_value: selectedPlayer.value,
    score,
  };
  saveState();
  showPlayerResult(sportIdx, playerIdx);
}

// ── Player result ──────────────────────────────────────────────────────────

function showPlayerResult(sportIdx, playerIdx) {
  const sp     = puzzleData.sports[sportIdx];
  const player = sp.players[playerIdx];
  const cat    = player.category;
  const result = state.sports[sportIdx].players[playerIdx];
  const max    = maxPerPlayer();
  const allDone = sportPlayersDone(sportIdx);

  document.getElementById('catres-sport-label').textContent = `${sp.emoji} ${sp.sport_label}`;
  document.getElementById('catres-cat-label').textContent =
    `${player.position_label} · ${cat.label}`;

  const scoreEl = document.getElementById('catres-score');
  scoreEl.textContent = `${result.score}/${max}`;
  scoreEl.className   = `result-score ${scoreClass(result.score)}`;

  document.getElementById('catres-guess-name').textContent  = result.guessed_name;
  document.getElementById('catres-guess-value').textContent = fmtValue(result.guessed_value, cat.fmt);
  document.getElementById('catres-target-name').textContent  = player.target_name;
  document.getElementById('catres-target-value').textContent = fmtValue(cat.target_value, cat.fmt);
  document.getElementById('catres-best-name').textContent   = cat.best_player_name || '—';
  document.getElementById('catres-best-value').textContent  = fmtValue(cat.best_value, cat.fmt);

  const nextBtn = document.getElementById('catres-next-btn');
  if (allDone) {
    nextBtn.textContent = `${sp.emoji} Sport Results`;
    nextBtn.onclick = () => showSportSummary(sportIdx);
  } else {
    nextBtn.textContent = 'Next';
    nextBtn.onclick = () => showGuess(sportIdx, playerIdx + 1);
  }

  showScreen('screen-cat-result');
}

// ── Sport summary ──────────────────────────────────────────────────────────

function showSportSummary(sportIdx) {
  const sp      = puzzleData.sports[sportIdx];
  const sportSt = state.sports[sportIdx];
  const score   = sportScoreFromState(sportSt);
  const max     = maxPerSport(sportIdx);
  const isLast  = sportIdx === puzzleData.sports.length - 1;

  document.getElementById('summary-sport-label').textContent = `${sp.emoji} ${sp.sport_label}`;

  const scoreEl = document.getElementById('summary-score');
  scoreEl.textContent = `${score} / ${max}`;
  scoreEl.className = `final-total-score ${scoreClass(score / sp.players.length)}`;

  const list = document.getElementById('summary-cat-list');
  list.innerHTML = '';
  sp.players.forEach((player, pi) => {
    const res = sportSt.players[pi];
    const cat = player.category;

    const header = document.createElement('div');
    header.className = 'summary-player-header';
    header.textContent = `${player.position_label}: ${player.target_name}`;
    list.appendChild(header);

    const row = document.createElement('div');
    row.className = 'round-row';
    row.innerHTML = `
      <span class="round-emoji">${scoreEmoji(res.score)}</span>
      <span class="round-category">${escHtml(cat.label)}</span>
      <span class="round-guesses">${escHtml(res.guessed_name)}: ${fmtValue(res.guessed_value, cat.fmt)} → ${fmtValue(cat.target_value, cat.fmt)}</span>
      <span class="round-score ${scoreClass(res.score)}">${res.score}/${maxPerPlayer()}</span>
    `;
    list.appendChild(row);
  });

  const shareBtn = document.getElementById('summary-share-btn');
  shareBtn.textContent = `Share ${sp.emoji}`;
  shareBtn.onclick = () => shareSport(sportIdx);

  const contBtn = document.getElementById('summary-continue-btn');
  if (isLast) {
    contBtn.textContent = 'See Final Results';
    contBtn.onclick = () => {
      state.sports[sportIdx].summarySeen = true;
      state.finished = true;
      saveState();
      showFinalResults();
    };
  } else {
    const next = puzzleData.sports[sportIdx + 1];
    contBtn.textContent = `Continue to ${next.emoji} ${next.sport_label}`;
    contBtn.onclick = () => {
      state.sports[sportIdx].summarySeen = true;
      saveState();
      showSportIntro(sportIdx + 1);
    };
  }

  showScreen('screen-sport-summary');
}

// ── Final results ──────────────────────────────────────────────────────────

function showFinalResults() {
  const total = totalScore();
  const max   = maxTotal();

  document.getElementById('final-game-label').textContent =
    `${puzzleData.sports.map(s => s.emoji).join('')} Statline #${state.gameNumber}`;
  document.getElementById('final-score').textContent = `${total} / ${max}`;

  const list = document.getElementById('final-sports-list');
  list.innerHTML = '';

  puzzleData.sports.forEach((sp, si) => {
    const sportSt  = state.sports[si];
    const spScore  = sportScoreFromState(sportSt);
    const spMax    = maxPerSport(si);

    const header = document.createElement('div');
    header.className = 'final-sport-header';
    header.innerHTML = `
      <span>${sp.emoji} ${escHtml(sp.sport_label)}</span>
      <span class="${scoreClass(spScore / sp.players.length)}">${spScore}/${spMax}</span>
    `;
    list.appendChild(header);

    sp.players.forEach((player, pi) => {
      const res = sportSt.players[pi];
      const cat = player.category;
      const row = document.createElement('div');
      row.className = 'round-row';
      row.innerHTML = `
        <span class="round-emoji">${scoreEmoji(res.score)}</span>
        <span class="round-category">${escHtml(player.position_label)}: ${escHtml(cat.label)}</span>
        <span class="round-guesses">${escHtml(res.guessed_name)}: ${fmtValue(res.guessed_value, cat.fmt)} → ${fmtValue(cat.target_value, cat.fmt)}</span>
        <span class="round-score ${scoreClass(res.score)}">${res.score}/${maxPerPlayer()}</span>
      `;
      list.appendChild(row);
    });
  });

  showScreen('screen-final');
}

// ── Share ──────────────────────────────────────────────────────────────────

function buildShareText(indices) {
  const idxs = indices !== undefined ? indices : puzzleData.sports.map((_, i) => i);
  const header = `${idxs.map(i => puzzleData.sports[i].emoji).join('')} Statline #${state.gameNumber}`;
  const score  = idxs.reduce((sum, i) => sum + sportScoreFromState(state.sports[i]), 0);
  const max    = idxs.reduce((sum, i) => sum + maxPerSport(i), 0);
  const lines  = idxs.map(i => {
    const sp = puzzleData.sports[i];
    const emojis = state.sports[i].players.map(p => scoreEmoji(p.score)).join('');
    const spScore = sportScoreFromState(state.sports[i]);
    return `${sp.emoji} ${emojis} ${spScore}/${maxPerSport(i)}`;
  });
  return `${header}\n${score}/${max}\n\n${lines.join('\n')}\n\nvwerkle.com/statline`;
}

function shareSport(sportIdx) {
  const done = puzzleData.sports.map((_, i) => i).filter(i => sportPlayersDone(i));
  doShare(buildShareText(done), document.getElementById('summary-share-btn'));
}

function share() {
  doShare(buildShareText(), document.getElementById('share-btn'));
}

function doShare(text, btn) {
  if (navigator.share) {
    navigator.share({ text }).catch(() => copyToClipboard(text, btn));
  } else {
    copyToClipboard(text, btn);
  }
}

function copyToClipboard(text, btn) {
  const orig = btn.textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 2000);
  });
}

// ── Resume ─────────────────────────────────────────────────────────────────

function resumeGame() {
  if (state.finished) { showFinalResults(); return; }
  const si = currentSportIdx();
  const s  = state.sports[si];
  if (sportPlayersDone(si)) { showSportSummary(si); return; }
  if (!s.introSeen)         { showSportIntro(si);   return; }
  showGuess(si, currentPlayerIdx(si));
}

// ── Input events ───────────────────────────────────────────────────────────

function setupInputHandlers() {
  const input = document.getElementById('guess-input');

  input.addEventListener('input', () => {
    const q = input.value.trim();
    selectedPlayer = null;
    document.getElementById('submit-btn').disabled = true;
    document.getElementById('selected-player-display').style.display = 'none';
    clearTimeout(acTimer);

    if (q.length < 2) { clearAC(); return; }

    acTimer = setTimeout(async () => {
      const si = currentSportIdx();
      const pi = currentPlayerIdx(si);
      if (pi < 0) return;
      const results = await fetchAC(si, pi, q);
      renderAC(results, si, pi);
    }, 200);
  });

  input.addEventListener('blur', () => setTimeout(clearAC, 150));

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && selectedPlayer) { e.preventDefault(); submitGuess(); }
    if (e.key === 'Escape') clearAC();
  });
}

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  try {
    const resp = await fetch('/statline/api/puzzle');
    if (!resp.ok) throw new Error('API error');
    puzzleData = await resp.json();
    if (!puzzleData.sports || puzzleData.sports.length === 0) throw new Error('No sports in puzzle');
  } catch {
    showScreen('screen-error');
    return;
  }

  setupInputHandlers();

  state = loadState();
  if (state && state.gameDate === puzzleData.date) {
    resumeGame();
    return;
  }

  initState();
  showLanding();
}

init();
