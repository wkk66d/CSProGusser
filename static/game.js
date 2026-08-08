/* CS2 猜选手 - 前端逻辑 */
"use strict";

// ---------- 状态 ----------
let ws = null;
let sessionId = null;
let roomCode = null;
let myName = "";
let myScore = 0;
let targetScore = 2;
let lobbyScore = 2;   // 创建房间界面的抢 N
let roundNumber = 0;
let roundActive = false;
let guessesLeft = 8;
let timeLeft = 120;
let isHost = false;
let playersList = [];          // [{session_id, name, score}]
let oppGuesses = {};           // session_id -> [ [color...], ... ]
let playerPool = [];           // 全部选手 (自动补全)
let selectedPlayerId = null;   // 自动补全选中的选手
let gameOver = false;

// ---------- DOM ----------
const $ = (id) => document.getElementById(id);

// ---------- 通信层 (HTTP 轮询) ----------
// cloudflared 隧道对 WebSocket 的支持不稳定: WS 握手能通过但数据帧可能被丢弃。
// 因此全部使用纯 HTTP 通信, 发送用 POST /api/action, 接收用 GET /api/poll。
let pollTimer = null;

function startPolling() {
  doPoll();
  pollTimer = setInterval(doPoll, 600);
}

async function doPoll() {
  try {
    const resp = await fetch(`api/poll?sid=${encodeURIComponent(sessionId || "")}`);
    const data = await resp.json();
    (data.messages || []).forEach(m => handleMessage(m));
  } catch (e) { /* 静默, 下次重试 */ }
}

async function sendHTTP(msg) {
  console.log("👉 发送:", msg.type);  // 诊断日志
  try {
    const resp = await fetch("api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...msg, sid: sessionId || "" }),
    });
    const data = await resp.json();
    console.log("👈 收到响应:", {sid: data.session_id, msgs: data.messages?.length, err: data.error});  // 诊断日志
    if (data.session_id) sessionId = data.session_id;
    (data.messages || []).forEach(m => handleMessage(m));
    if (data.error) showGuessFeedback(data.error, false);
  } catch (e) {
    console.error("HTTP 动作失败:", e);
    showConnError("无法连接服务器, 请检查服务是否运行");
  }
}

function showConnError(text) {
  const el = $("conn-error");
  if (el) { el.textContent = "⚠ " + text; el.classList.remove("hidden"); }
}
function hideConnError() {
  const el = $("conn-error");
  if (el) el.classList.add("hidden");
}

function send(msg) {
  sendHTTP(msg);
}

// ---------- 消息处理 ----------
function handleMessage(msg) {
  switch (msg.type) {
    case "room_created":
      sessionId = msg.session_id;
      roomCode = msg.code;
      isHost = true;
      showScreen("screen-wait");
      break;
    case "joined":
      sessionId = msg.session_id;
      roomCode = msg.code;
      showScreen("screen-wait");
      break;
    case "player_joined":
      $("lobby-error").textContent = "";
      break;
    case "player_left":
      break;
    case "state":
      applyState(msg.state);
      break;
    case "game_started":
      resetRoundUI();
      gameOver = false;
      $("round-overlay").classList.add("hidden");
      showScreen("screen-game");
      targetScore = msg.target_score;
      renderScores();
      break;
    case "round_start":
      roundNumber = msg.round;
      roundActive = true;
      guessesLeft = msg.max_guesses;
      timeLeft = msg.round_time;
      selectedPlayerId = null;
      oppGuesses = {};
      resetRoundUI();
      $("round-overlay").classList.add("hidden");
      renderStatus();
      renderOpponents();
      enableInput(true);
      break;
    case "timer":
      timeLeft = msg.time_left;
      renderStatus();
      break;
    case "guess_result":
      appendSelfRow(msg);
      guessesLeft = msg.guesses_left;
      renderStatus();
      showGuessFeedback(`反馈已更新 (剩余 ${guessesLeft} 次)`, true);
      break;
    case "opponent_guess":
      if (!oppGuesses[msg.player_session]) oppGuesses[msg.player_session] = [];
      oppGuesses[msg.player_session].push(msg.colors);
      renderOpponents();
      break;
    case "scores_update":
      // 立即更新比分栏 (在 round_end 弹窗前)
      if (msg.scores) {
        Object.entries(msg.scores).forEach(([sid, s]) => {
          const p = playersList.find(pp => pp.session_id === sid);
          if (p) p.score = s;
        });
        renderScores(msg.scores);
      }
      break;
    case "round_end":
      roundActive = false;
      enableInput(false);
      // 同步最新分数到本地缓存
      if (msg.scores) {
        Object.entries(msg.scores).forEach(([sid, s]) => {
          const p = playersList.find(pp => pp.session_id === sid);
          if (p) p.score = s;
        });
      }
      showRoundEnd(msg);
      break;
    case "game_over":
      gameOver = true;
      // 对局获胜: 显示醒目的"再来一局"按钮
      $("btn-rematch").classList.remove("hidden");
      $("btn-rematch").classList.add("rematch-btn");
      $("round-target-info").classList.add("hidden");
      if (msg.winner === myName) {
        $("round-result-title").textContent = "🏆 你赢了！";
      } else {
        $("round-result-title").textContent = `${msg.winner || "?"} 获胜`;
      }
      renderScores(msg.scores);
      break;
    case "mode_changed":
      targetScore = msg.target_score;
      // 同步等待界面分段按钮
      const segW = $("seg-wait");
      if (segW) {
        segW.querySelectorAll(".seg-btn").forEach(b => {
          b.classList.toggle("active", parseInt(b.dataset.score) === targetScore);
        });
      }
      break;
    case "error":
      showGuessFeedback(msg.message, false);
      break;
  }
}

function applyState(state) {
  roomCode = state.code;
  targetScore = state.target_score;
  roundNumber = state.round_number;
  roundActive = state.round_active;
  gameOver = state.game_over;
  isHost = state.host_id === state.you;
  playersList = state.players;
  sessionId = state.you;
  timeLeft = state.time_left;

  renderWaitPlayers();
  renderScores();

  if (state.game_over || state.round_number > 0 || state.round_active) {
    showScreen("screen-game");
    renderStatus();
  } else {
    showScreen("screen-wait");
  }
}

// ---------- 界面切换 ----------
function showScreen(id) {
  ["screen-lobby", "screen-wait", "screen-game"].forEach(s => $(s).classList.add("hidden"));
  $(id).classList.remove("hidden");
}

// ---------- 等待界面 ----------
function renderWaitPlayers() {
  $("wait-code").textContent = roomCode;
  const box = $("wait-players");
  box.innerHTML = "";
  playersList.forEach(p => {
    const div = document.createElement("div");
    div.className = "wait-player";
    div.innerHTML = `<span class="dot"></span><span>${esc(p.name)}</span>` +
      (p.session_id === sessionId ? '<span class="host-tag" style="background:var(--accent-2)">你</span>' : "") +
      (p.session_id === isHost ? '<span class="host-tag">房主</span>' : "");
    box.appendChild(div);
  });
  // 同步抢 N 分段按钮
  const segWait = $("seg-wait");
  if (segWait) {
    segWait.querySelectorAll(".seg-btn").forEach(b => {
      b.classList.toggle("active", parseInt(b.dataset.score) === targetScore);
    });
  }
  $("btn-start").disabled = !isHost;
  $("wait-tip").textContent = isHost ? "你是房主，点击开始游戏" : "等待房主开始游戏...";
}

// ---------- 游戏界面 ----------
function renderScores(scoresObj) {
  // scoresObj: 可选, {session_id: score} — round_end 传来最新分数
  const bar = $("score-bar");
  bar.innerHTML = "";
  playersList.forEach(p => {
    const s = (scoresObj && scoresObj[p.session_id] != null) ? scoresObj[p.session_id] : p.score;
    const div = document.createElement("div");
    div.className = "score-item" + (p.session_id === sessionId ? " me" : "");
    div.innerHTML = `<span class="name">${esc(p.name)}</span>` +
      `<span class="pts">${s}</span>` +
      `<span class="target">/${targetScore}</span>`;
    bar.appendChild(div);
  });
}

function renderStatus() {
  const mm = String(Math.floor(timeLeft / 60)).padStart(1, "0");
  const ss = String(timeLeft % 60).padStart(2, "0");
  const timerEl = $("status-timer") || createTimerEl();
  timerEl.textContent = `${mm}:${ss}`;
  timerEl.classList.toggle("warn", timeLeft <= 30 && roundActive);
  const roundInfo = $("round-info");
  if (roundInfo) {
    roundInfo.innerHTML = roundActive
      ? `第 <b>${roundNumber}</b> 局 | 抢 <b>${targetScore}</b> | 猜测 <b>${guessesLeft}</b>/8`
      : `第 ${roundNumber} 局结束`;
  }
}

function createTimerEl() {
  const statusBar = document.querySelector(".status-bar");
  if (!statusBar) return null;
  const left = document.createElement("div");
  left.className = "status-left";
  left.innerHTML = `<span id="round-info"></span>`;
  const right = document.createElement("div");
  right.className = "status-right";
  right.innerHTML = `<span class="timer" id="status-timer"></span>`;
  statusBar.innerHTML = "";
  statusBar.appendChild(left);
  statusBar.appendChild(right);
  return $("status-timer");
}

function resetRoundUI() {
  $("self-tbody").innerHTML = "";
  $("self-empty").classList.remove("hidden");
  oppGuesses = {};
  $("guess-input").value = "";
  selectedPlayerId = null;
}

function enableInput(on) {
  $("guess-input").disabled = !on;
  $("btn-guess").disabled = !on;
}

// ---------- 自己的猜测表格 ----------
function appendSelfRow(result) {
  $("self-empty").classList.add("hidden");
  const tbody = $("self-tbody");
  const tr = document.createElement("tr");
  if (result.correct) tr.className = "correct";

  const fb = result.feedback;
  const values = [
    fb["国家"].value, fb["战队"].value, fb["年龄"].value, fb["Major"].value,
    fb["位置"].value, fb["最高Top"].value,
  ];
  const arrows = [
    fb["国家"].arrow, fb["战队"].arrow, fb["年龄"].arrow, fb["Major"].arrow,
    fb["位置"].arrow, fb["最高Top"].arrow,
  ];
  const colors = [
    fb["国家"].color, fb["战队"].color, fb["年龄"].color, fb["Major"].color,
    fb["位置"].color, fb["最高Top"].color,
  ];

  tr.innerHTML = `<td class="nick">${esc(result.guess_nickname)}</td>`;
  for (let i = 0; i < 6; i++) {
    const td = document.createElement("td");
    td.innerHTML = `<span class="cell ${colors[i]}">${esc(values[i])}` +
      (arrows[i] ? `<span class="arrow">${arrows[i]}</span>` : "") + `</span>`;
    tr.appendChild(td);
  }
  tbody.appendChild(tr);
  tbody.scrollTop = tbody.scrollHeight;
}

// ---------- 对手颜色块 ----------
const OPP_HEADERS = ["选手", "国家", "战队", "年龄", "Major", "位置", "最高Top"];

function renderOpponents() {
  const container = $("opp-container");
  container.innerHTML = "";
  const opps = playersList.filter(p => p.session_id !== sessionId);
  const me = playersList.find(p => p.session_id === sessionId);

  if (opps.length === 0) {
    $("opp-empty").classList.remove("hidden");
    return;
  }
  $("opp-empty").classList.add("hidden");

  // 根据对手数量调整块大小
  const blockScale = opps.length >= 4 ? 14 : opps.length >= 3 ? 17 : 20;

  opps.forEach(p => {
    const section = document.createElement("div");
    section.className = "opp-section";
    const nameRow = document.createElement("div");
    nameRow.className = "opp-name";
    nameRow.innerHTML = `<span class="opp-name-text">${esc(p.name)}</span>` +
      `<span class="opp-guess-count">${(oppGuesses[p.session_id] || []).length} 次</span>`;
    section.appendChild(nameRow);

    // 列标题 (7 列: 选手 + 6 属性)
    const headerRow = document.createElement("div");
    headerRow.className = "opp-row opp-header-row";
    OPP_HEADERS.forEach(h => {
      const hd = document.createElement("div");
      hd.className = "opp-header";
      hd.textContent = h;
      headerRow.appendChild(hd);
    });
    section.appendChild(headerRow);

    const grid = document.createElement("div");
    grid.className = "opp-grid";
    const guesses = oppGuesses[p.session_id] || [];
    if (guesses.length === 0) {
      const note = document.createElement("div");
      note.className = "opp-empty-note";
      note.textContent = "尚未猜测";
      grid.appendChild(note);
    } else {
      guesses.forEach((colors, gi) => {
        const row = document.createElement("div");
        row.className = "opp-row";
        // 第一列: 猜测序号 (对应"选手"列)
        const num = document.createElement("div");
        num.className = "opp-num";
        num.textContent = gi + 1;
        row.appendChild(num);
        // 后 6 列: 颜色块
        colors.forEach(c => {
          const block = document.createElement("div");
          block.className = `opp-block ${c}`;
          block.style.minHeight = blockScale + "px";
          row.appendChild(block);
        });
        grid.appendChild(row);
      });
    }
    section.appendChild(grid);
    container.appendChild(section);
  });
}

// ---------- 自动补全 ----------
let suggestMatches = [];    // 当前匹配列表
let suggestIndex = -1;      // 当前高亮项

// 数字↔字母归一化 (与服务端一致: 0↔o 1↔i 3↔e 4↔a 5↔s 7↔t)
const LEET_PAIRS = [["0","o"],["1","i"],["3","e"],["4","a"],["5","s"],["7","t"]];
function normalizeNick(s) {
  s = s.toLowerCase();
  LEET_PAIRS.forEach(([d, l]) => { s = s.replaceAll(d, "\x00").replaceAll(l, "\x00"); });
  return s.replace(/\x00/g, "_");  // 所有互通字符归一为 _
}

async function loadPlayerPool() {
  try {
    // 相对路径, 兼容子路径部署 (如 nginx 反代到 /csprog/)
    const resp = await fetch("api/players");
    playerPool = await resp.json();
  } catch (e) {
    console.error("加载选手池失败", e);
  }
}

function renderSuggestions(query) {
  const box = $("guess-suggest");
  const q = query.trim().toLowerCase();
  if (!q || !roundActive) {
    box.classList.add("hidden");
    box.innerHTML = "";
    suggestMatches = [];
    suggestIndex = -1;
    return;
  }
  const qNorm = normalizeNick(q);
  // 打分: 首字母匹配100 > 归一化首字母90 > 包含50 > 归一化包含40
  const scored = [];
  playerPool.forEach(p => {
    const nick = p.nickname.toLowerCase();
    const nickNorm = normalizeNick(nick);
    let score = 0;
    if (nick.startsWith(q)) score = 100;
    else if (nickNorm.startsWith(qNorm)) score = 90;
    else if (q.length >= 2 && nick.includes(q)) score = 50;
    else if (q.length >= 2 && nickNorm.includes(qNorm)) score = 40;
    if (score > 0) scored.push({ ...p, _score: score });
  });
  scored.sort((a, b) => b._score - a._score || a.nickname.length - b.nickname.length || a.nickname.localeCompare(b.nickname));
  suggestMatches = scored.slice(0, 8);

  if (suggestMatches.length === 0) {
    suggestIndex = -1;
    box.innerHTML = `<div class="suggest-item"><span>未找到选手</span></div>`;
    box.classList.remove("hidden");
    return;
  }
  suggestIndex = 0;
  box.innerHTML = "";
  suggestMatches.forEach((p, i) => {
    const item = document.createElement("div");
    item.className = "suggest-item" + (i === suggestIndex ? " active" : "");
    item.innerHTML = `<span>${esc(p.nickname)}</span>` +
      `<span class="meta">${esc(p.team)} · ${esc(p.country)}</span>`;
    item.onclick = () => selectSuggestion(p);
    item.onmousedown = (e) => e.preventDefault();
    box.appendChild(item);
  });
  box.classList.remove("hidden");
}

function highlightSuggestion(index) {
  const items = document.querySelectorAll("#guess-suggest .suggest-item");
  if (items.length === 0) return;
  suggestIndex = Math.max(0, Math.min(index, items.length - 1));
  items.forEach((el, i) => el.classList.toggle("active", i === suggestIndex));
  items[suggestIndex].scrollIntoView({ block: "nearest" });
}

function selectSuggestion(p) {
  $("guess-input").value = p.nickname;
  selectedPlayerId = p.id;
  $("guess-suggest").classList.add("hidden");
}

// ---------- 猜测反馈信息 ----------
function showGuessFeedback(text, ok) {
  const el = $("guess-feedback");
  el.textContent = text;
  el.className = "guess-feedback " + (ok ? "ok" : "err");
  setTimeout(() => { if (el.textContent === text) el.textContent = ""; }, 4000);
}

// ---------- 回合结束 ----------
function showRoundEnd(msg) {
  $("btn-rematch").classList.add("hidden");
  $("btn-rematch").classList.remove("rematch-btn");
  $("round-target-info").classList.remove("hidden");
  const title = $("round-result-title");
  if (msg.reason === "correct") {
    const w = playersList.find(p => p.session_id === msg.winner);
    title.textContent = w ? `${w.name} 猜中了！` : "有人猜中了！";
  } else if (msg.reason === "timeout") {
    title.textContent = "⏰ 时间耗尽";
  } else {
    title.textContent = "猜测次数耗尽";
  }
  const t = msg.target;
  $("round-target-info").innerHTML =
    `🎯 目标选手: <b>${esc(t.nickname)}</b> (${esc(t.full_name || "")})<br>` +
    `🇺🇳 国家: ${esc(t.country)} | 战队: ${esc(t.team)}<br>` +
    `年龄: ${t.age} | Major: ${t.major_count} | 位置: ${esc(t.role)} | 最高Top: ${esc(t.peak_top)}`;
  const scores = Object.entries(msg.scores)
    .map(([sid, s]) => {
      const p = playersList.find(pp => pp.session_id === sid);
      return `${esc(p ? p.name : "?")}: ${s}`;
    })
    .join(" | ");
  $("round-scores").textContent = "比分 " + scores;
  renderScores(msg.scores); // 传入最新比分
  $("round-overlay").classList.remove("hidden");
}

// ---------- 工具 ----------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ---------- 事件绑定 ----------
function bindEvents() {
  // 防御: 确保所有元素存在 (避免单个缺失导致全部按钮失效)
  const required = ["btn-create", "btn-join", "input-code", "input-name",
    "btn-start", "btn-leave", "seg-create", "seg-wait", "btn-rematch", "guess-input", "btn-guess"];
  for (const id of required) {
    if (!$(id)) console.error(`页面缺少元素 #${id}`);
  }

  // 大厅
  $("btn-create").onclick = () => {
    console.log("🖱️ 点击创建房间");  // 诊断日志
    const name = $("input-name").value.trim();
    if (!name) { $("lobby-error").textContent = "请输入昵称"; return; }
    myName = name;
    send({ type: "create_room", name, target_score: lobbyScore });
  };
  $("btn-join").onclick = () => {
    console.log("🖱️ 点击加入房间");  // 诊断日志
    const name = $("input-name").value.trim();
    const code = $("input-code").value.trim().toUpperCase();
    if (!name) { $("lobby-error").textContent = "请输入昵称"; return; }
    if (!code) { $("lobby-error").textContent = "请输入房间码"; return; }
    myName = name;
    send({ type: "join_room", code, name });
  };
  $("input-code").onkeydown = (e) => { if (e.key === "Enter") $("btn-join").click(); };
  $("input-name").onkeydown = (e) => { if (e.key === "Enter") $("btn-create").click(); };

  // 等待界面
  $("btn-start").onclick = () => {
    send({ type: "start_game" });
  };
  $("btn-leave").onclick = () => location.reload();

  // 分段按钮组: 抢 N 选择
  function bindSeg(groupId, onSelect) {
    const group = $(groupId);
    if (!group) return;
    group.querySelectorAll(".seg-btn").forEach(btn => {
      btn.onclick = () => {
        group.querySelectorAll(".seg-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        onSelect(parseInt(btn.dataset.score));
      };
    });
  }
  bindSeg("seg-create", v => { lobbyScore = v; });
  bindSeg("seg-wait", v => {
    targetScore = v;
    send({ type: "set_mode", target_score: v });
  });

  // 游戏界面
  $("btn-rematch").onclick = () => { send({ type: "rematch" }); };

  $("guess-input").oninput = (e) => {
    selectedPlayerId = null;
    renderSuggestions(e.target.value);
  };
  $("guess-input").onkeydown = (e) => {
    const box = $("guess-suggest");
    const visible = !box.classList.contains("hidden") && suggestMatches.length > 0;
    if (e.key === "ArrowDown") {
      if (visible) { e.preventDefault(); highlightSuggestion(suggestIndex + 1); }
    } else if (e.key === "ArrowUp") {
      if (visible) { e.preventDefault(); highlightSuggestion(suggestIndex - 1); }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (visible && suggestIndex >= 0) {
        // 回车选中当前高亮的匹配
        selectSuggestion(suggestMatches[suggestIndex]);
      }
      submitGuess();
    } else if (e.key === "Escape") {
      box.classList.add("hidden");
    }
  };
  $("guess-input").onblur = () => {
    setTimeout(() => $("guess-suggest").classList.add("hidden"), 200);
  };
  $("btn-guess").onclick = submitGuess;
}

function submitGuess() {
  if (!roundActive) return;
  if (!selectedPlayerId) {
    showGuessFeedback("请从下拉列表选择选手", false);
    return;
  }
  send({ type: "guess", player_id: selectedPlayerId });
  // 提交后自动清空输入栏
  $("guess-input").value = "";
  selectedPlayerId = null;
  $("guess-suggest").classList.add("hidden");
}

// ---------- 启动 ----------
startPolling();   // HTTP 轮询 (cloudflared 隧道中最可靠)
loadPlayerPool();
bindEvents();
