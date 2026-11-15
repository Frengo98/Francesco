const state = { data: { players: [], matches: [], historicalMatchCount: 0, lastUpdated: null }, token: sessionStorage.getItem("adminToken") || "" };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const historicalFields = [
  ["appearances", "Presenze"], ["goals", "Gol"], ["assists", "Assist"], ["ownGoals", "Autogol"],
  ["mvp", "MVP"], ["wins", "Vittorie"], ["losses", "Sconfitte"], ["draws", "Pareggi"],
];
let toastTimer;
let entryPlayerSignature = null;
let historicalSignature = null;
const playerSort = { key: "totalScore", direction: "desc" };
const latestMatchSort = { key: "totalScore", direction: "desc" };

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers["X-Admin-Token"] = state.token;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/login") {
      state.token = "";
      sessionStorage.removeItem("adminToken");
      renderAccess();
    }
    throw new Error(result.error || "Si è verificato un errore.");
  }
  return result;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
}

function renderAccess() {
  const isAdmin = Boolean(state.token);
  $("#access-label").textContent = isAdmin ? "Modalità amministratore" : "Sola visualizzazione";
  $("#login-open").classList.toggle("hidden", isAdmin);
  $("#logout").classList.toggle("hidden", !isAdmin);
  $("#management").classList.toggle("hidden", !isAdmin);
}

function formatDate(value, options = { day: "2-digit", month: "short", year: "numeric" }) {
  if (!value) return "";
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  return new Intl.DateTimeFormat("it-IT", options).format(date);
}

function renderUpdatedAt() {
  $("#last-updated").textContent = state.data.lastUpdated
    ? new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" }).format(new Date(state.data.lastUpdated))
    : "Nessun aggiornamento";
}

function sortRankingItems(items, sort) {
  const nameOf = (item) => item.name || `${item.firstName} ${item.lastName}`;
  return [...items].sort((first, second) => {
    const firstName = nameOf(first);
    const secondName = nameOf(second);
    const comparison = sort.key === "name"
      ? firstName.localeCompare(secondName, "it")
      : Number((sort.key === "position" ? first.position : first.statistics[sort.key]) || 0)
        - Number((sort.key === "position" ? second.position : second.statistics[sort.key]) || 0);
    const direction = sort.direction === "asc" ? 1 : -1;
    return comparison * direction || firstName.localeCompare(secondName, "it");
  });
}

function updateSortIndicators(table, sort) {
  table.querySelectorAll("th[data-sort]").forEach((heading) => {
    const button = heading.querySelector("[data-sort]");
    const active = button.dataset.sort === sort.key;
    heading.setAttribute("aria-sort", active ? (sort.direction === "asc" ? "ascending" : "descending") : "none");
    button.querySelector(".sort-indicator").textContent = active
      ? (sort.direction === "asc" ? " ↑" : " ↓")
      : " ↕";
  });
}

function toggleSort(sort, key) {
  if (sort.key === key) {
    sort.direction = sort.direction === "asc" ? "desc" : "asc";
  } else {
    sort.key = key;
    sort.direction = key === "name" ? "asc" : "desc";
  }
}

function renderSummary() {
  const players = state.data.players;
  const matches = state.data.matches;
  const historicalMatchCount = state.data.historicalMatchCount || 0;
  $("#match-count").textContent = historicalMatchCount + matches.length;
  $("#player-count").textContent = players.length;
  $("#goal-count").textContent = players.reduce((total, player) => total + Number(player.statistics.goals), 0);
  $("#assist-count").textContent = players.reduce((total, player) => total + Number(player.statistics.assists), 0);
  $("#match-caption").textContent = historicalMatchCount
    ? `${historicalMatchCount} pregresse · ${matches.length} registrate`
    : `${matches.length} ${matches.length === 1 ? "partita" : "partite"}`;
  renderUpdatedAt();
}

function renderPlayers() {
  const query = $("#player-search").value.trim().toLocaleLowerCase("it");
  const scoreOrder = [...state.data.players].sort(
    (first, second) => Number(second.statistics.totalScore) - Number(first.statistics.totalScore),
  );
  const positions = new Map();
  let previousScore = null;
  let currentPosition = 0;
  scoreOrder.forEach((player, index) => {
    const score = Number(player.statistics.totalScore);
    if (score !== previousScore) currentPosition = index + 1;
    positions.set(player.id, currentPosition);
    previousScore = score;
  });
  const players = sortRankingItems(
    state.data.players
      .filter((player) => `${player.firstName} ${player.lastName}`.toLocaleLowerCase("it").includes(query))
      .map((player) => ({ ...player, position: positions.get(player.id) })),
    playerSort,
  );
  updateSortIndicators($("#players-ranking"), playerSort);
  const table = $("#players-table");
  if (!players.length) {
    table.innerHTML = `<tr><td class="table-empty" colspan="12">${state.data.players.length ? "Nessun giocatore corrisponde alla ricerca." : "Nessun giocatore inserito."}</td></tr>`;
    return;
  }
  table.innerHTML = players.map((player) => {
    const stats = player.statistics;
    const initials = `${player.firstName[0] || ""}${player.lastName[0] || ""}`.toUpperCase();
    const rankClass = player.position <= 3 ? ` rank-${player.position}` : "";
    return `<tr>
      <td><span class="rank-badge${rankClass}" aria-label="Posizione ${player.position}">${player.position}°</span></td>
      <td><button class="player-link" type="button" data-player-id="${escapeHtml(player.id)}"><span class="player-avatar">${escapeHtml(initials)}</span>${escapeHtml(player.firstName)} ${escapeHtml(player.lastName)}</button></td>
      <td>${stats.appearances}</td><td>${stats.goals}</td><td>${stats.assists}</td><td>${stats.ownGoals}</td><td>${stats.mvp}</td>
      <td>${stats.wins}</td><td>${stats.losses}</td><td>${stats.draws}</td><td>${stats.totalScore}</td><td>›</td>
    </tr>`;
  }).join("");
}

function renderEntryList() {
  const signature = state.data.players.map((player) => player.id).join(",");
  if (signature === entryPlayerSignature) return;
  entryPlayerSignature = signature;
  const list = $("#entry-list");
  if (!state.data.players.length) {
    list.innerHTML = '<p class="empty-note">Aggiungi prima i giocatori alla rosa.</p>';
    return;
  }
  list.innerHTML = `<div class="entry-labels"><span>Giocatore</span><span>Squadra</span><span>Gol</span><span>Ass.</span><span>Aut.</span><span>MVP</span></div>` +
    state.data.players.map((player) => `<div class="entry-row" data-player-id="${escapeHtml(player.id)}">
      <label class="entry-player"><input class="entry-selected" type="checkbox"><span>${escapeHtml(player.firstName)} ${escapeHtml(player.lastName)}</span></label>
      <select class="entry-team" aria-label="Squadra di ${escapeHtml(player.firstName)} ${escapeHtml(player.lastName)}"><option value="A">Squadra A</option><option value="B">Squadra B</option></select>
      <input class="entry-goals" type="number" min="0" value="0" aria-label="Gol">
      <input class="entry-assists" type="number" min="0" value="0" aria-label="Assist">
      <input class="entry-own-goals" type="number" min="0" value="0" aria-label="Autogol">
      <label class="mvp-cell"><input class="entry-mvp" type="radio" name="match-mvp" aria-label="MVP">★</label>
    </div>`).join("");
}

function renderHistoricalEditor() {
  const signature = JSON.stringify({
    matchCount: state.data.historicalMatchCount || 0,
    players: state.data.players.map((player) => ({
      id: player.id,
      firstName: player.firstName,
      lastName: player.lastName,
      historicalStatistics: player.historicalStatistics,
    })),
  });
  if (signature === historicalSignature) return;
  historicalSignature = signature;

  $("#historical-form").elements.matchCount.value = state.data.historicalMatchCount || 0;
  const list = $("#historical-list");
  if (!state.data.players.length) {
    list.innerHTML = '<p class="empty-note">Aggiungi prima i giocatori alla rosa.</p>';
    return;
  }
  list.innerHTML = `<table class="historical-table">
    <thead><tr><th>Giocatore</th>${historicalFields.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead>
    <tbody>${state.data.players.map((player) => `<tr data-player-id="${escapeHtml(player.id)}">
      <td>${escapeHtml(player.firstName)} ${escapeHtml(player.lastName)}</td>
      ${historicalFields.map(([field, label]) => `<td><input type="number" min="0" step="1" required value="${Number(player.historicalStatistics && player.historicalStatistics[field]) || 0}" data-stat="${field}" aria-label="${label} di ${escapeHtml(player.firstName)} ${escapeHtml(player.lastName)}"></td>`).join("")}
    </tr>`).join("")}</tbody>
  </table>`;
}

function renderMatches() {
  const matches = [...state.data.matches].sort((a, b) => b.date.localeCompare(a.date));
  const container = $("#matches-list");
  if (!matches.length) {
    const message = state.data.historicalMatchCount
      ? `Le ${state.data.historicalMatchCount} partite pregresse sono incluse nei totali, senza dettaglio per singola gara.`
      : "Le partite registrate appariranno qui.";
    container.innerHTML = `<div class="empty-state"><span>◷</span><p>${message}</p></div>`;
    return;
  }
  container.innerHTML = matches.map((match) => {
    const teams = ["A", "B"].map((team) => {
      const entries = match.entries.filter((entry) => entry.team === team);
      const players = entries.length
        ? entries.map((entry) => `<li class="match-player">
            <span class="match-player-name">${escapeHtml(entry.playerName)}${entry.mvp ? ' <span class="mvp-tag">★ MVP</span>' : ""}</span>
            <span class="match-player-stats">Gol ${entry.goals} · Assist ${entry.assists} · Autogol ${entry.ownGoals}</span>
          </li>`).join("")
        : '<li class="match-team-empty">Nessun giocatore</li>';
      return `<section class="match-team">
        <h3>Squadra ${team}</h3>
        <ul class="match-player-list">${players}</ul>
      </section>`;
    }).join("");
    return `<article class="match-card">
      <div class="match-card-top"><span>${escapeHtml(formatDate(match.date))}</span><span>${match.entries.length} ${match.entries.length === 1 ? "presenza" : "presenze"}</span></div>
      <div class="match-score">${match.scoreA}<span>Squadra A&nbsp; — &nbsp;Squadra B</span>${match.scoreB}</div>
      <div class="match-teams">${teams}</div>
    </article>`;
  }).join("");
}

function renderLatestMatch() {
  const latestMatch = state.data.matches.reduce(
    (latest, match) => !latest || match.date >= latest.date ? match : latest,
    null,
  );
  const caption = $("#latest-match-caption");
  const table = $("#latest-match-ranking");
  const body = $("#latest-match-players");
  updateSortIndicators(table, latestMatchSort);
  if (!latestMatch) {
    caption.textContent = "Nessuna partita registrata";
    const message = state.data.historicalMatchCount
      ? "I totali pregressi sono aggregati; registra una partita nel dettaglio per creare la mini classifica."
      : "Registra una partita per visualizzare la mini classifica.";
    body.innerHTML = `<tr><td class="table-empty" colspan="10">${message}</td></tr>`;
    return;
  }

  caption.textContent = `${formatDate(latestMatch.date)} · ${latestMatch.scoreA} – ${latestMatch.scoreB}`;
  const scoreA = Number(latestMatch.scoreA);
  const scoreB = Number(latestMatch.scoreB);
  const entries = latestMatch.entries.map((entry) => {
    const draw = scoreA === scoreB;
    const win = !draw && ((scoreA > scoreB && entry.team === "A") || (scoreB > scoreA && entry.team === "B"));
    const statistics = {
      appearances: 1,
      goals: Number(entry.goals),
      assists: Number(entry.assists),
      ownGoals: Number(entry.ownGoals),
      mvp: Number(Boolean(entry.mvp)),
      wins: Number(win),
      losses: Number(!draw && !win),
      draws: Number(draw),
    };
    statistics.totalScore = 3 * statistics.wins + 2 * statistics.mvp + statistics.draws;
    return { name: entry.playerName, statistics };
  });
  body.innerHTML = sortRankingItems(entries, latestMatchSort).map((entry) => {
    const stats = entry.statistics;
    return `<tr><td>${escapeHtml(entry.name)}</td><td>${stats.appearances}</td><td>${stats.goals}</td><td>${stats.assists}</td><td>${stats.ownGoals}</td><td>${stats.mvp}</td><td>${stats.wins}</td><td>${stats.losses}</td><td>${stats.draws}</td><td>${stats.totalScore}</td></tr>`;
  }).join("");
}

function showPlayerHistory(playerId) {
  const player = state.data.players.find((item) => item.id === playerId);
  if (!player) return;
  $("#history-title").textContent = `${player.firstName} ${player.lastName}`;
  const stats = player.statistics;
  $("#history-summary").innerHTML = [
    ["Presenze", stats.appearances], ["Gol", stats.goals], ["Assist", stats.assists],
    ["Autogol", stats.ownGoals], ["MVP", stats.mvp], ["Vittorie", stats.wins],
    ["Sconfitte", stats.losses], ["Pareggi", stats.draws], ["Punteggio totale", stats.totalScore],
  ].map(([label, value]) => `<span class="history-chip">${label} <strong>${value}</strong></span>`).join("");
  const matches = state.data.matches.filter((match) => match.entries.some((entry) => entry.playerId === playerId)).sort((a, b) => b.date.localeCompare(a.date));
  $("#history-table").innerHTML = matches.length ? matches.map((match) => {
    const entry = match.entries.find((item) => item.playerId === playerId);
    return `<tr><td>${escapeHtml(formatDate(match.date))}</td><td>${match.scoreA} – ${match.scoreB}</td><td>Squadra ${escapeHtml(entry.team)}</td><td>${entry.goals}</td><td>${entry.assists}</td><td>${entry.ownGoals}</td><td>${entry.mvp ? '<span class="mvp-tag">★ MVP</span>' : "—"}</td></tr>`;
  }).join("") : `<tr><td class="table-empty" colspan="7">${state.data.historicalMatchCount ? "I totali pregressi sono aggregati e non hanno dettaglio partita per partita." : "Nessuna partita registrata."}</td></tr>`;
  $("#player-history").classList.remove("hidden");
  $("#player-history").scrollIntoView({ behavior: "smooth", block: "start" });
}

function render() {
  renderAccess();
  renderSummary();
  renderPlayers();
  renderLatestMatch();
  if (state.token) {
    renderEntryList();
    renderHistoricalEditor();
  }
  renderMatches();
}

async function loadData() {
  state.data = await request("/api/data");
  render();
}

$("#login-open").addEventListener("click", () => $("#login-dialog").showModal());
$("#login-close").addEventListener("click", () => $("#login-dialog").close());
$("#logout").addEventListener("click", () => {
  state.token = "";
  sessionStorage.removeItem("adminToken");
  renderAccess();
  showToast("Sei uscito dalla modalità gestione.");
});
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const loginForm = event.currentTarget;
  const form = new FormData(loginForm);
  $("#login-error").textContent = "";
  try {
    const result = await request("/api/login", { method: "POST", body: JSON.stringify({ password: form.get("password") }) });
    state.token = result.token;
    sessionStorage.setItem("adminToken", state.token);
    loginForm.reset();
    $("#login-dialog").close();
    renderAccess();
    renderEntryList();
    renderHistoricalEditor();
    showToast("Accesso effettuato. Puoi aggiornare i dati.");
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});
$("#player-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const playerForm = event.currentTarget;
  const form = new FormData(event.currentTarget);
  try {
    state.data = await request("/api/players", { method: "POST", body: JSON.stringify({ firstName: form.get("firstName"), lastName: form.get("lastName") }) });
    playerForm.reset();
    render();
    showToast("Giocatore aggiunto alla rosa.");
  } catch (error) { showToast(error.message, true); }
});
$("#match-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const matchForm = event.currentTarget;
  const form = new FormData(matchForm);
  const entries = [...document.querySelectorAll(".entry-row")].filter((row) => row.querySelector(".entry-selected").checked).map((row) => ({
    playerId: row.dataset.playerId,
    team: row.querySelector(".entry-team").value,
    goals: row.querySelector(".entry-goals").value,
    assists: row.querySelector(".entry-assists").value,
    ownGoals: row.querySelector(".entry-own-goals").value,
    mvp: row.querySelector(".entry-mvp").checked,
  }));
  try {
    state.data = await request("/api/matches", { method: "POST", body: JSON.stringify({
      date: form.get("date"), scoreA: form.get("scoreA"), scoreB: form.get("scoreB"), entries,
    }) });
    matchForm.reset();
    matchForm.elements.date.value = new Date().toISOString().slice(0, 10);
    matchForm.elements.scoreA.value = 0;
    matchForm.elements.scoreB.value = 0;
    render();
    showToast("Partita registrata e file Excel aggiornato.");
  } catch (error) { showToast(error.message, true); }
});
$("#historical-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const players = [...$("#historical-list").querySelectorAll("tbody tr[data-player-id]")].map((row) => ({
    playerId: row.dataset.playerId,
    ...Object.fromEntries(historicalFields.map(([field]) => [
      field,
      row.querySelector(`[data-stat="${field}"]`).value,
    ])),
  }));
  const inconsistentPlayer = players.find((player) => (
    Number(player.appearances) !== Number(player.wins) + Number(player.losses) + Number(player.draws)
  ));
  if (inconsistentPlayer) {
    const player = state.data.players.find((item) => item.id === inconsistentPlayer.playerId);
    showToast(
      `Le presenze di ${player.firstName} ${player.lastName} devono coincidere con vittorie, sconfitte e pareggi.`,
      true,
    );
    return;
  }
  try {
    state.data = await request("/api/historical", {
      method: "POST",
      body: JSON.stringify({ matchCount: form.get("matchCount"), players }),
    });
    render();
    showToast("Totali pregressi aggiornati.");
  } catch (error) { showToast(error.message, true); }
});
$("#players-ranking").addEventListener("click", (event) => {
  const button = event.target.closest("[data-sort]");
  if (!button) return;
  toggleSort(playerSort, button.dataset.sort);
  renderPlayers();
});
$("#latest-match-ranking").addEventListener("click", (event) => {
  const button = event.target.closest("[data-sort]");
  if (!button) return;
  toggleSort(latestMatchSort, button.dataset.sort);
  renderLatestMatch();
});
$("#players-table").addEventListener("click", (event) => {
  const button = event.target.closest("[data-player-id]");
  if (button) showPlayerHistory(button.dataset.playerId);
});
$("#player-search").addEventListener("input", renderPlayers);
$("#close-history").addEventListener("click", () => $("#player-history").classList.add("hidden"));
$("#match-form").elements.date.value = new Date().toISOString().slice(0, 10);

loadData().catch((error) => {
  showToast(error.message, true);
  $("#last-updated").textContent = "Server non raggiungibile";
});
window.setInterval(() => loadData().catch(() => {}), 30000);
