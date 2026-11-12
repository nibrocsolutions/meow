/* Region names match COLOR_NAMES in app/puzzle.py. */
const COLOR_NAMES = ["rose", "apricot", "butter", "mint", "aqua", "periwinkle", "lilac", "peach", "sage"];

const app = document.getElementById("app");
const state = {
  screen: "boot",
  player: null,
  players: [],
  home: null,
  run: null,
  tickStart: 0,
  prefs: loadPrefs(),
  toast: "",
  hint: "",
  menu: false,
  shake: null,
  busy: false,
  waiting: "",
  draftName: "",
  rename: "",
  cursor: null,
  keys: false,
};

function loadPrefs() {
  try {
    return { shade: true, sound: false, ...JSON.parse(localStorage.getItem("meow-prefs") || "{}") };
  } catch {
    return { shade: true, sound: false };
  }
}

function savePrefs() {
  localStorage.setItem("meow-prefs", JSON.stringify({ shade: state.prefs.shade, sound: state.prefs.sound }));
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function formatTime(ms) {
  const safe = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function shownElapsed() {
  if (!state.run) return 0;
  if (state.run.status !== "playing") return state.run.elapsed_ms;
  return state.run.elapsed_ms + (Date.now() - state.tickStart);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    let message = "Something went wrong.";
    if (data && typeof data.detail === "string") message = data.detail;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

function adopt(run) {
  state.run = run;
  state.tickStart = Date.now();
  if (run.hint) state.hint = run.hint;
  if (run.message) flash(run.message);
  if (run.lost_heart) {
    buzz(false);
    const cell = state.pendingCell;
    if (cell) {
      state.shake = `${cell[0]},${cell[1]}`;
      const token = state.shake;
      setTimeout(() => {
        if (state.shake === token) state.shake = null;
      }, 400);
    }
  } else if (run.status === "won") {
    buzz(true);
  }
  state.pendingCell = null;
}

function flash(message) {
  state.toast = message;
  const token = message;
  setTimeout(() => {
    if (state.toast === token) {
      state.toast = "";
      render();
    }
  }, 2600);
}

function buzz(ok) {
  if (navigator.vibrate) navigator.vibrate(ok ? 12 : 28);
  if (!state.prefs.sound) return;
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  if (!state.audio) state.audio = new AudioCtx();
  const ctx = state.audio;
  if (ctx.state === "suspended") ctx.resume();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = ok ? 620 : 180;
  gain.gain.value = 0.04;
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + 0.09);
}

function catSvg(sleepy) {
  const eyes = sleepy
    ? `<path d="M22 37 q4 4 8 0" fill="none" stroke="var(--paper)" stroke-width="2.2" stroke-linecap="round"/>
       <path d="M34 37 q4 4 8 0" fill="none" stroke="var(--paper)" stroke-width="2.2" stroke-linecap="round"/>`
    : `<circle class="cat-eye" cx="26" cy="36" r="2.1"/>
       <circle class="cat-eye" cx="39" cy="36" r="2.1"/>
       <path class="cat-eye" d="M32 40.2 L29.7 43 L34.3 43 Z"/>`;
  return `<svg viewBox="0 0 64 64" aria-hidden="true">
    <path class="cat-body" d="M15 31 L11 13 L27 25 Z"/>
    <path class="cat-body" d="M49 31 L53 13 L37 25 Z"/>
    <ellipse class="cat-body" cx="32" cy="38" rx="18" ry="15"/>
    ${eyes}
  </svg>`;
}

function heartSvg(on) {
  return `<svg class="heart ${on ? "on" : "off"}" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="var(--heart)" d="M12 20s-7-4.4-7-9.1C5 8 6.8 6.2 9.1 6.2c1.3 0 2.4.6 2.9 1.6.5-1 1.6-1.6 2.9-1.6 2.3 0 4.1 1.8 4.1 4.7C19 15.6 12 20 12 20z"/>
  </svg>`;
}

function render() {
  document.body.classList.toggle("playing", state.screen === "play");
  if (state.waiting) {
    app.innerHTML = `<p class="waiting">${esc(state.waiting)}</p>`;
    return;
  }
  if (state.screen === "boot") {
    app.innerHTML = `<p class="boot">Loading Meow…</p>`;
    return;
  }
  if (state.screen === "name" || state.screen === "switch") {
    app.innerHTML = playerScreen();
    return;
  }
  if (state.screen === "home") {
    app.innerHTML = homeScreen();
    return;
  }
  if (state.screen === "levels") {
    app.innerHTML = levelsScreen();
    return;
  }
  if (state.screen === "stats") {
    app.innerHTML = statsScreen();
    return;
  }
  if (state.screen === "help") {
    app.innerHTML = helpScreen();
    return;
  }
  if (state.screen === "admin") {
    app.innerHTML = adminScreen();
    return;
  }
  if (state.screen === "play" && state.run) {
    app.innerHTML = playScreen();
  }
}

function playerScreen() {
  const list = state.players.map((player) => `
    <div class="player-row">
      <button class="linkish" data-action="pick-player" data-id="${player.id}">${esc(player.name)}</button>
      <button class="text-button" data-action="remove-player" data-id="${player.id}" data-name="${esc(player.name)}">Remove</button>
    </div>
  `).join("");
  return `
    <h1 class="wordmark">${catSvg(false)} Meow</h1>
    <p class="lede">Who is playing on this phone?</p>
    <form class="stack" id="name-form">
      <label class="field">Name
        <input id="player-name" maxlength="24" autocomplete="nickname" value="${esc(state.draftName)}" required>
      </label>
      <button class="primary" type="submit">Save name</button>
    </form>
    <div class="player-list stack">${list || ""}</div>
    ${state.toast ? `<p class="toast">${esc(state.toast)}</p>` : ""}
  `;
}

function homeScreen() {
  const home = state.home;
  const next = home.levels.find((level) => level.level === home.campaign_next) || home.levels[0];
  const playingCampaign = home.playing.find((item) => item.mode === "campaign" && item.level === home.campaign_next);
  const daily = home.daily.map((item) => `
    <button class="tile ${item.status === "won" ? "done" : ""}" data-action="daily" data-difficulty="${esc(item.difficulty)}">
      <strong>${esc(item.tier)}</strong>
      <small>${esc(dailyLabel(item))}</small>
    </button>
  `).join("");
  return `
    <header class="top">
      <h1 class="wordmark">${catSvg(false)} Meow</h1>
      <button class="ghost" data-action="switch">${esc(home.player.name)}</button>
    </header>
    <p class="lede">One cat in every row, column, and color. Cats can't touch.</p>
    <div class="stack">
      <button class="choice" data-action="campaign" data-level="${next.level}" data-replay="false">
        <strong>${playingCampaign ? "Continue" : "Play"} level ${next.level}</strong>
        <span>${esc(next.tier)} · ${next.size}×${next.size}${home.campaign_completed ? ` · ${home.campaign_completed} solved` : ""}</span>
      </button>
    </div>
    <h2 class="section-title">Today ${home.streak ? `· ${home.streak} day streak` : ""}</h2>
    <div class="row">${daily}</div>
    <h2 class="section-title">Endless</h2>
    <div class="row four">
      ${endlessButton("easy", "6×6")}
      ${endlessButton("normal", "7×7")}
      ${endlessButton("hard", "8×8")}
      ${endlessButton("expert", "9×9")}
    </div>
    <div class="stack">
      <button class="choice" data-action="levels"><strong>Levels</strong><span>Replay one you already opened</span></button>
      <button class="choice" data-action="help"><strong>How to play</strong><span>Four rules, then the buttons</span></button>
      <button class="choice" data-action="stats"><strong>Stats</strong><span>${home.stats.solved} solved</span></button>
    </div>
    <p class="foot">Fan-made home version of the Meowdoku rules. Not the official game, and not affiliated with Oakever Games.</p>
    ${state.toast ? `<p class="toast">${esc(state.toast)}</p>` : ""}
  `;
}

function endlessButton(difficulty, size) {
  const active = state.home.playing.find((item) => item.mode === "endless" && item.difficulty === difficulty);
  return `<button class="tile" data-action="endless" data-difficulty="${difficulty}">
    <strong>${esc(difficulty[0].toUpperCase() + difficulty.slice(1))}</strong>
    <small>${active ? "Resume" : size}</small>
  </button>`;
}

function dailyLabel(item) {
  if (item.status === "won") return item.best_ms != null ? formatTime(item.best_ms) : "Solved";
  if (item.status === "playing") return "Resume";
  if (item.status === "lost") return "Try again";
  return `${item.size}×${item.size}`;
}

function levelsScreen() {
  const buttons = state.home.levels.map((level) => `
    <button class="${esc(level.status)}" data-action="campaign" data-level="${level.level}" data-replay="${level.status === "won" ? "true" : "false"}" ${level.status === "locked" ? "disabled" : ""}>
      <strong>${level.level}</strong>
      <small>${level.status === "won" && level.best_ms != null ? formatTime(level.best_ms) : esc(level.status === "locked" ? "locked" : level.tier)}</small>
    </button>
  `).join("");
  return `
    <header class="top">
      <button class="ghost" data-action="home">Home</button>
      <h1>Levels</h1>
      <span></span>
    </header>
    <div class="level-grid" style="margin-top:16px">${buttons}</div>
  `;
}

function statsScreen() {
  const stats = state.home.stats;
  const bests = Object.entries(stats.best).filter(([, value]) => value != null);
  const rows = bests.map(([name, value]) => `<dt>Best ${esc(name)}</dt><dd>${formatTime(value)}</dd>`).join("");
  return `
    <header class="top">
      <button class="ghost" data-action="home">Home</button>
      <h1>Stats</h1>
      <span></span>
    </header>
    <div class="card stats" style="padding:16px;margin-top:16px">
      <dl>
        <dt>Solved</dt><dd>${stats.solved}</dd>
        <dt>Daily streak</dt><dd>${state.home.streak}</dd>
        <dt>Campaign</dt><dd>${state.home.campaign_completed}</dd>
        <dt>Hints</dt><dd>${stats.hints}</dd>
        <dt>Hearts lost</dt><dd>${stats.hearts_lost}</dd>
        ${rows}
      </dl>
    </div>
    <p class="foot"><a href="/admin">Backup on this Pi</a></p>
  `;
}

function helpScreen() {
  return `
    <header class="top">
      <button class="ghost" data-action="${state.run ? "back-play" : "home"}">Back</button>
      <h1>How to play</h1>
      <span></span>
    </header>
    <div class="card help-copy" style="padding:16px;margin-top:16px">
      <p>The board is split into colored regions. Place cats until every rule holds.</p>
      <ol class="rules">
        <li>Every color has exactly one cat.</li>
        <li>Every row has exactly one cat.</li>
        <li>Every column has exactly one cat.</li>
        <li>Two cats cannot touch, not even on a corner.</li>
      </ol>
      <p>Tap a cell to mark it empty. Tap the mark to try a cat. A wrong cat costs a heart. You have three. Drag across cells to mark a line of empties.</p>
      <p>A resting cat is given. It does not move. Shaded dots are cells the cats you already placed have ruled out.</p>
      <p>Hints explain the next forced step. They do not cost a heart. Undo takes back a tap, a drag, or a hint.</p>
      <p>On a keyboard, arrows move, space cycles a cell, <kbd>Z</kbd> undoes, and <kbd>H</kbd> hints.</p>
      <p class="fine">Same rules as Meowdoku. This copy runs on your Pi for the phones in the house. It is not the official app.</p>
    </div>
  `;
}

function playScreen() {
  const run = state.run;
  const hearts = Array.from({ length: run.max_hearts }, (_, index) => heartSvg(index < run.hearts)).join("");
  return `
    <header class="play-top">
      <button class="ghost" data-action="leave">Home</button>
      <h1>${esc(run.title)}</h1>
      <button class="ghost" data-action="menu" aria-label="Menu">Menu</button>
    </header>
    <div class="status-row">
      <div class="hearts" aria-label="${run.hearts} hearts left">${hearts}</div>
      <div id="timer">${formatTime(shownElapsed())}</div>
      <div aria-label="${run.placed} of ${run.needed} cats">${run.placed}/${run.needed}</div>
    </div>
    <div class="board-wrap">${boardHtml(run)}</div>
    <p class="hint" aria-live="polite">${esc(state.hint || "Tap once to mark a cell. Tap again for a cat.")}</p>
    <p class="toast" aria-live="assertive">${esc(state.toast || "")}</p>
    <div class="tools">
      <button class="tool" data-action="undo" ${run.can_undo ? "" : "disabled"}>Undo</button>
      <button class="tool" data-action="hint" ${run.status === "playing" ? "" : "disabled"}>Hint</button>
      <button class="tool" data-action="restart" ${run.status === "won" ? "disabled" : ""}>Restart</button>
    </div>
    ${state.menu ? menuSheet() : ""}
    ${run.status === "won" ? winSheet() : ""}
    ${run.status === "lost" ? loseSheet() : ""}
  `;
}

function boardHtml(run) {
  const cats = new Set(run.cats.map((cell) => cell.join(",")));
  const marks = new Set(run.marks.map((cell) => cell.join(",")));
  const starters = new Set(run.starters.map((cell) => cell.join(",")));
  const shaded = state.prefs.shade ? shadeSet(run, cats, starters) : new Set();
  const cells = [];
  for (let row = 0; row < run.size; row += 1) {
    for (let col = 0; col < run.size; col += 1) {
      const key = `${row},${col}`;
      const region = run.regions[row * run.size + col];
      const name = COLOR_NAMES[region] || "color";
      let kind = "empty";
      let inner = "";
      if (starters.has(key)) {
        kind = "given cat";
        inner = catSvg(true);
      } else if (cats.has(key)) {
        kind = "cat";
        inner = catSvg(false);
      } else if (marks.has(key)) {
        kind = "marked empty";
        inner = `<span class="mark">×</span>`;
      } else if (shaded.has(key)) {
        kind = "ruled out";
        inner = `<span class="shade"></span>`;
      }
      const cursor = state.keys && state.cursor && state.cursor.row === row && state.cursor.col === col ? " cursor" : "";
      const shake = state.shake === key ? " shake" : "";
      const edge = edgeShadow(run, row, col, region);
      cells.push(`<button type="button" class="cell${cursor}${shake}" data-region="${region}" data-r="${row}" data-c="${col}" style="${edge}" aria-label="Row ${row + 1}, column ${col + 1}, ${esc(name)}, ${kind}">${inner}</button>`);
    }
  }
  return `<div class="board" style="grid-template-columns:repeat(${run.size},1fr)">${cells.join("")}</div>`;
}

function edgeShadow(run, row, col, region) {
  const size = run.size;
  const differs = (r, c) => r < 0 || c < 0 || r >= size || c >= size || run.regions[r * size + c] !== region;
  const parts = [];
  if (differs(row - 1, col)) parts.push("inset 0 2px 0 var(--line)");
  if (row === size - 1) parts.push("inset 0 -2px 0 var(--line)");
  if (differs(row, col - 1)) parts.push("inset 2px 0 0 var(--line)");
  if (col === size - 1) parts.push("inset -2px 0 0 var(--line)");
  return parts.length ? `box-shadow:${parts.join(",")}` : "";
}

function shadeSet(run, cats, starters) {
  const blocked = new Set();
  const placed = [...cats, ...starters].map((key) => key.split(",").map(Number));
  for (const [row, col] of placed) {
    const region = run.regions[row * run.size + col];
    for (let r = 0; r < run.size; r += 1) {
      for (let c = 0; c < run.size; c += 1) {
        const sameRegion = run.regions[r * run.size + c] === region;
        const touches = Math.abs(r - row) <= 1 && Math.abs(c - col) <= 1;
        if (r === row || c === col || sameRegion || touches) blocked.add(`${r},${c}`);
      }
    }
  }
  for (const key of cats) blocked.delete(key);
  for (const key of starters) blocked.delete(key);
  return blocked;
}

function menuSheet() {
  const endless = state.run.mode === "endless"
    ? `<button class="text-button" data-action="new-endless">New ${esc(state.run.difficulty)} puzzle</button>`
    : "";
  return `
    <div class="overlay" data-action="close-menu">
      <div class="sheet menu-sheet" data-stop>
        <h2>Menu</h2>
        <button class="text-button" data-action="toggle-shade">Shade ruled-out cells: ${state.prefs.shade ? "on" : "off"}</button>
        <button class="text-button" data-action="toggle-sound">Sound: ${state.prefs.sound ? "on" : "off"}</button>
        <button class="text-button" data-action="help">How to play</button>
        ${endless}
        <button class="text-button" data-action="close-menu">Close</button>
      </div>
    </div>
  `;
}

function winSheet() {
  const run = state.run;
  const best = run.is_best ? "Best time." : run.best_ms != null ? `Best is ${formatTime(run.best_ms)}.` : "";
  let next = `<button class="primary" data-action="home">Home</button>`;
  if (run.mode === "campaign") {
    next = `<button class="primary" data-action="campaign" data-level="${run.level + 1}" data-replay="false">Level ${run.level + 1}</button>`;
  } else if (run.mode === "endless") {
    next = `<button class="primary" data-action="new-endless">Another ${esc(run.difficulty)}</button>`;
  } else {
    next = `<button class="primary" data-action="replay-daily">Play again</button>`;
  }
  return `
    <div class="overlay">
      <div class="sheet" data-stop>
        <h2>Solved</h2>
        <p>${formatTime(run.elapsed_ms)} · ${run.hints} ${run.hints === 1 ? "hint" : "hints"}. ${esc(best)}</p>
        ${next}
        <button class="text-button" data-action="home">Home</button>
      </div>
    </div>
  `;
}

function loseSheet() {
  return `
    <div class="overlay">
      <div class="sheet" data-stop>
        <h2>Out of hearts</h2>
        <p>The board is the same. The cats go back to the start.</p>
        <button class="primary" data-action="restart">Try again</button>
        ${state.run.can_undo ? `<button class="text-button" data-action="undo">Undo last cat</button>` : ""}
        <button class="text-button" data-action="home">Home</button>
      </div>
    </div>
  `;
}

function adminScreen() {
  const summary = state.adminSummary;
  const counts = summary ? `${summary.players} players, ${summary.puzzles} puzzles, ${summary.runs} runs.` : "Loading…";
  return `
    <header class="top">
      <a class="ghost" href="/">Home</a>
      <h1>Backup</h1>
      <span></span>
    </header>
    <p class="lede">${esc(counts)} This page has no password. Anyone who can open the Pi can replace the saved games.</p>
    <div class="stack">
      <button class="primary" data-action="export">Download backup</button>
      <form id="import-form" class="stack">
        <input id="import-file" type="file" accept="application/json">
        <button class="primary" type="submit">Replace from backup</button>
      </form>
    </div>
    ${state.toast ? `<p class="toast">${esc(state.toast)}</p>` : ""}
  `;
}

async function boot() {
  try {
    if (location.pathname.startsWith("/admin")) {
      state.screen = "admin";
      state.adminSummary = await api("/api/admin/summary");
      render();
      return;
    }
    const saved = Number(localStorage.getItem("meow-player") || "0");
    state.players = await api("/api/players");
    if (saved && state.players.some((player) => player.id === saved)) {
      await openHome(saved);
      return;
    }
    state.screen = state.players.length ? "switch" : "name";
    render();
  } catch (error) {
    state.screen = "name";
    state.toast = error.message || "Can't reach Meow.";
    render();
  }
}

async function openHome(playerId) {
  state.waiting = "";
  try {
    state.home = await api(`/api/home?player_id=${playerId}`);
    state.player = state.home.player;
    localStorage.setItem("meow-player", String(state.player.id));
    state.players = await api("/api/players");
    state.screen = "home";
    state.run = null;
  } catch (error) {
    if (error.status === 404) {
      localStorage.removeItem("meow-player");
      state.player = null;
      state.screen = "name";
    }
    flash(error.message || "Can't reach Meow.");
  }
  render();
}

async function openRun(body, label) {
  state.waiting = label;
  state.menu = false;
  state.hint = "";
  state.toast = "";
  render();
  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    if (run.solution) throw new Error("The board included an answer.");
    adopt(run);
    state.cursor = { row: 0, col: 0 };
    state.screen = "play";
  } catch (error) {
    flash(error.message);
    state.screen = state.home ? "home" : "name";
  } finally {
    state.waiting = "";
    render();
  }
}

async function act(path, extra = {}) {
  if (!state.run || state.busy) return;
  state.busy = true;
  try {
    const run = await api(path, {
      method: "POST",
      body: JSON.stringify({
        player_id: state.player.id,
        elapsed_ms: Math.round(shownElapsed()),
        ...extra,
      }),
    });
    adopt(run);
  } catch (error) {
    flash(error.message);
  } finally {
    state.busy = false;
    render();
  }
}

async function saveClock() {
  if (!state.run || state.run.status !== "playing" || state.busy || !state.player) return;
  const elapsed = Math.round(shownElapsed());
  try {
    const data = await api(`/api/runs/${state.run.id}/clock`, {
      method: "POST",
      body: JSON.stringify({ player_id: state.player.id, elapsed_ms: elapsed }),
    });
    if (state.run && data.elapsed_ms >= state.run.elapsed_ms && !state.busy) {
      state.run.elapsed_ms = data.elapsed_ms;
      state.tickStart = Date.now();
    }
  } catch {
    /* The next tap will send the clock again. */
  }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  if (event.target.closest("[data-stop]") && button.dataset.action === "close-menu") {
    /* A tap inside the sheet should not fall through to the overlay. */
  }
  const action = button.dataset.action;
  if (action === "close-menu") {
    state.menu = false;
    render();
    return;
  }
  if (action === "menu") {
    state.menu = true;
    render();
    return;
  }
  if (action === "toggle-shade") {
    state.prefs.shade = !state.prefs.shade;
    savePrefs();
    render();
    return;
  }
  if (action === "toggle-sound") {
    state.prefs.sound = !state.prefs.sound;
    savePrefs();
    render();
    return;
  }
  if (action === "home" || action === "leave") {
    if (state.run && state.run.status === "playing") await saveClock();
    state.menu = false;
    if (state.player) await openHome(state.player.id);
    else state.screen = "name";
    render();
    return;
  }
  if (action === "back-play") {
    state.screen = "play";
    render();
    return;
  }
  if (action === "switch") {
    state.screen = "switch";
    state.draftName = "";
    render();
    return;
  }
  if (action === "pick-player") {
    await openHome(Number(button.dataset.id));
    return;
  }
  if (action === "remove-player") {
    const name = button.dataset.name || "this player";
    if (!window.confirm(`Remove ${name}? Their saved games on this Pi go with them.`)) return;
    try {
      await api(`/api/players/${button.dataset.id}`, { method: "DELETE" });
      if (state.player && String(state.player.id) === button.dataset.id) {
        localStorage.removeItem("meow-player");
        state.player = null;
      }
      state.players = await api("/api/players");
      state.screen = state.players.length ? "switch" : "name";
    } catch (error) {
      flash(error.message);
    }
    render();
    return;
  }
  if (action === "help") {
    state.menu = false;
    state.screen = "help";
    render();
    return;
  }
  if (action === "levels") {
    state.screen = "levels";
    render();
    return;
  }
  if (action === "stats") {
    state.screen = "stats";
    render();
    return;
  }
  if (action === "campaign") {
    const level = Number(button.dataset.level);
    await openRun({
      player_id: state.player.id,
      mode: "campaign",
      level,
      replay: button.dataset.replay === "true",
    }, `Making level ${level}…`);
    return;
  }
  if (action === "daily") {
    await openRun({
      player_id: state.player.id,
      mode: "daily",
      difficulty: button.dataset.difficulty,
      replay: false,
    }, "Making today's puzzle…");
    return;
  }
  if (action === "endless" || action === "new-endless") {
    const difficulty = button.dataset.difficulty || state.run.difficulty;
    await openRun({
      player_id: state.player.id,
      mode: "endless",
      difficulty,
      replay: action === "new-endless",
    }, "Making a puzzle…");
    return;
  }
  if (action === "replay-daily") {
    await openRun({
      player_id: state.player.id,
      mode: "daily",
      difficulty: state.run.difficulty,
      replay: true,
    }, "Resetting today's puzzle…");
    return;
  }
  if (action === "undo") return act(`/api/runs/${state.run.id}/undo`);
  if (action === "hint") return act(`/api/runs/${state.run.id}/hint`);
  if (action === "restart") return act(`/api/runs/${state.run.id}/restart`);
  if (action === "export") {
    const backup = await api("/api/admin/export");
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "meow-backup.json";
    link.click();
    URL.revokeObjectURL(link.href);
  }
});

document.addEventListener("submit", async (event) => {
  if (event.target.id === "name-form") {
    event.preventDefault();
    const name = state.draftName.trim();
    try {
      const player = await api("/api/players", { method: "POST", body: JSON.stringify({ name }) });
      await openHome(player.id);
    } catch (error) {
      flash(error.message);
      render();
    }
    return;
  }
  if (event.target.id === "import-form") {
    event.preventDefault();
    const file = document.getElementById("import-file").files[0];
    if (!file) return;
    if (!window.confirm("Replace every saved game on this Pi with the backup?")) return;
    try {
      const text = await file.text();
      const body = JSON.parse(text);
      state.adminSummary = await api("/api/admin/import", { method: "POST", body: JSON.stringify(body) });
      flash("Backup restored.");
    } catch (error) {
      flash(error.message || "That file could not be restored.");
    }
    render();
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "player-name") state.draftName = event.target.value;
});

let gesture = null;

document.addEventListener("pointerdown", (event) => {
  const cell = event.target.closest(".cell");
  if (!cell || state.screen !== "play" || !state.run || state.run.status !== "playing" || state.busy) return;
  if (event.button !== 0) return;
  event.preventDefault();
  gesture = {
    row: Number(cell.dataset.r),
    col: Number(cell.dataset.c),
    moved: false,
    cells: [],
    seen: new Set(),
    pointer: event.pointerId,
  };
});

document.addEventListener("pointermove", (event) => {
  if (!gesture || event.pointerId !== gesture.pointer) return;
  const element = document.elementFromPoint(event.clientX, event.clientY);
  const cell = element && element.closest ? element.closest(".cell") : null;
  if (!cell) return;
  const row = Number(cell.dataset.r);
  const col = Number(cell.dataset.c);
  if (row === gesture.row && col === gesture.col) return;
  gesture.moved = true;
  const key = `${row},${col}`;
  if (!gesture.seen.has(key)) {
    gesture.seen.add(key);
    gesture.cells.push([row, col]);
  }
});

async function finishGesture(event) {
  if (!gesture || (event && event.pointerId !== gesture.pointer)) return;
  const done = gesture;
  gesture = null;
  if (!state.run) return;
  if (done.moved) {
    const start = `${done.row},${done.col}`;
    if (!done.seen.has(start)) done.cells.unshift([done.row, done.col]);
    await act(`/api/runs/${state.run.id}/marks`, { cells: done.cells });
    return;
  }
  state.pendingCell = [done.row, done.col];
  state.cursor = { row: done.row, col: done.col };
  await act(`/api/runs/${state.run.id}/tap`, { row: done.row, col: done.col });
}

document.addEventListener("pointerup", finishGesture);
document.addEventListener("pointercancel", () => { gesture = null; });

document.addEventListener("keydown", async (event) => {
  if (state.screen !== "play" || !state.run || event.metaKey || event.ctrlKey || event.altKey) return;
  const target = event.target;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
  if (state.menu || state.run.status !== "playing") return;
  if (target && target.closest && target.closest("button, a") && event.key !== "z" && event.key !== "Z" && event.key !== "h" && event.key !== "H") {
    return;
  }
  state.keys = true;
  if (!state.cursor) state.cursor = { row: 0, col: 0 };
  const key = event.key.toLowerCase();
  if (key === "arrowup") state.cursor.row = Math.max(0, state.cursor.row - 1);
  else if (key === "arrowdown") state.cursor.row = Math.min(state.run.size - 1, state.cursor.row + 1);
  else if (key === "arrowleft") state.cursor.col = Math.max(0, state.cursor.col - 1);
  else if (key === "arrowright") state.cursor.col = Math.min(state.run.size - 1, state.cursor.col + 1);
  else if (key === " " || key === "enter") {
    event.preventDefault();
    state.pendingCell = [state.cursor.row, state.cursor.col];
    await act(`/api/runs/${state.run.id}/tap`, { row: state.cursor.row, col: state.cursor.col });
    return;
  } else if (key === "z") {
    await act(`/api/runs/${state.run.id}/undo`);
    return;
  } else if (key === "h") {
    await act(`/api/runs/${state.run.id}/hint`);
    return;
  } else return;
  event.preventDefault();
  render();
});

setInterval(() => {
  const node = document.getElementById("timer");
  if (!node || state.screen !== "play") return;
  node.textContent = formatTime(shownElapsed());
}, 250);

setInterval(() => {
  if (state.screen === "play") saveClock();
}, 8000);

window.addEventListener("pagehide", () => {
  if (!state.run || !state.player || state.run.status !== "playing") return;
  const payload = JSON.stringify({
    player_id: state.player.id,
    elapsed_ms: Math.round(shownElapsed()),
  });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      `/api/runs/${state.run.id}/clock`,
      new Blob([payload], { type: "application/json" }),
    );
  }
});

boot();
