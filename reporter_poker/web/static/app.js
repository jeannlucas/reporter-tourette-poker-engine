"use strict";

const RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"];
const SUITS = ["s", "h", "d", "c"];
const SUIT_SYMBOLS = { s: "♠", h: "♥", d: "♦", c: "♣" };
const SUIT_COLOR = { s: "black", h: "red", d: "red", c: "black" };
const RANK_LABEL = { T: "10" };

const SLOT_ORDER = [
  "hole-0", "hole-1",
  "flop-0", "flop-1", "flop-2",
  "turn-0",
  "river-0",
];

const CATEGORY_PT = {
  HIGH_CARD: "Carta Alta",
  PAIR: "Par",
  TWO_PAIR: "Dois Pares",
  THREE_OF_A_KIND: "Trinca",
  STRAIGHT: "Sequência",
  FLUSH: "Flush",
  FULL_HOUSE: "Full House",
  FOUR_OF_A_KIND: "Quadra",
  STRAIGHT_FLUSH: "Straight Flush",
  ROYAL_FLUSH: "Royal Flush",
};

const ACTION_PT = {
  fold:  { label: "DESISTIR", cls: "fold" },
  call:  { label: "PAGAR",    cls: "call" },
  raise: { label: "AUMENTAR", cls: "raise" },
  check: { label: "MESA",     cls: "check" },
  bet:   { label: "APOSTAR",  cls: "bet" },
};

const prefersReducedMotion =
  window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Default scenario values — used when the user resets everything.
const DEFAULT_SCENARIO = {
  opponents: "1",
  pot: "100",
  to_call: "50",
  iterations: "25000",
};

const slots = Object.create(null);

// Last analysis snapshot (raw payload from /api/analyze) — needed to save.
// Also remembers the inputs used (the slots/scenario at analyze time).
let lastAnalysis = null;
let pendingTakenAction = null;
let pendingDeleteId = null;

function init() {
  for (const id of SLOT_ORDER) slots[id] = null;
  buildGrid();
  bindSlots();
  bindOcr();
  bindSaveForm();
  document.getElementById("analyze").addEventListener("click", runAnalysis);
  document.getElementById("new-hand").addEventListener("click", clearCardsOnly);
  document.getElementById("clear").addEventListener("click", resetEverything);
  document.getElementById("history-refresh").addEventListener("click", loadHistory);
  loadHistory();
}

function cardFace(card) {
  const r = card[0];
  const s = card[1];
  return (RANK_LABEL[r] || r) + SUIT_SYMBOLS[s];
}

function buildGrid() {
  const grid = document.getElementById("card-grid");
  for (const s of SUITS) {
    for (const r of RANKS) {
      const div = document.createElement("div");
      const card = r + s;
      div.className = "pick " + SUIT_COLOR[s];
      div.dataset.card = card;
      div.textContent = cardFace(card);
      div.addEventListener("click", () => pickCard(card));
      grid.appendChild(div);
    }
  }
}

function bindSlots() {
  document.querySelectorAll(".card-slot").forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.dataset.slot;
      if (slots[id]) {
        slots[id] = null;
        renderSlot(id);
        refreshUsed();
      }
    });
  });
}

function nextEmptySlot() {
  return SLOT_ORDER.find((id) => !slots[id]) || null;
}

function pickCard(card) {
  if (Object.values(slots).includes(card)) return;
  const target = nextEmptySlot();
  if (!target) return;
  slots[target] = card;
  renderSlot(target);
  refreshUsed();
}

function renderSlot(id) {
  const el = document.querySelector(`.card-slot[data-slot="${id}"]`);
  const card = slots[id];
  el.classList.remove("filled", "red", "black");
  // Restart the slot-in animation by reflowing the node.
  el.style.animation = "none";
  // eslint-disable-next-line no-unused-expressions
  el.offsetHeight;
  el.style.animation = "";
  if (card) {
    el.textContent = cardFace(card);
    el.classList.add("filled", SUIT_COLOR[card[1]]);
  } else {
    el.textContent = "";
  }
}

function refreshUsed() {
  const used = new Set(Object.values(slots).filter(Boolean));
  document.querySelectorAll(".pick").forEach((el) => {
    el.classList.toggle("used", used.has(el.dataset.card));
  });
}

/** Clears the cards (hole + board) and the displayed result.
 *  Keeps the scenario fields (opponents, pot, to_call, iterations) intact. */
function clearCardsOnly() {
  for (const id of SLOT_ORDER) {
    slots[id] = null;
    renderSlot(id);
  }
  refreshUsed();
  showEmptyState();
  document.getElementById("error").hidden = true;
  lastAnalysis = null;
  resetSaveForm();
}

/** Full reset: clears the cards, the result, and restores default scenario. */
function resetEverything() {
  clearCardsOnly();
  document.getElementById("opponents").value = DEFAULT_SCENARIO.opponents;
  document.getElementById("pot").value = DEFAULT_SCENARIO.pot;
  document.getElementById("to_call").value = DEFAULT_SCENARIO.to_call;
  document.getElementById("iterations").value = DEFAULT_SCENARIO.iterations;
}

function showEmptyState() {
  document.getElementById("results").hidden = true;
  document.getElementById("empty-state").hidden = false;
}

function showResults() {
  document.getElementById("empty-state").hidden = true;
  const panel = document.getElementById("results");
  panel.hidden = false;
  // Re-trigger the panel-in animation on every render.
  panel.style.animation = "none";
  // eslint-disable-next-line no-unused-expressions
  panel.offsetHeight;
  panel.style.animation = "";
}

function readBoard() {
  const flop = ["flop-0", "flop-1", "flop-2"].map((id) => slots[id]);
  const turn = slots["turn-0"];
  const river = slots["river-0"];

  const flopCount = flop.filter(Boolean).length;
  if (flopCount === 0 && !turn && !river) return "";
  if (flopCount !== 3) {
    throw new Error("Preencha o flop completo (3 cartas) ou deixe-o vazio.");
  }
  if (river && !turn) {
    throw new Error("Informe o turn antes do river.");
  }

  const board = flop.slice();
  if (turn) board.push(turn);
  if (river) board.push(river);
  return board.join(" ");
}

async function runAnalysis() {
  const errBox = document.getElementById("error");
  const btn = document.getElementById("analyze");
  errBox.hidden = true;

  try {
    const hole = [slots["hole-0"], slots["hole-1"]];
    if (!hole[0] || !hole[1]) {
      throw new Error("Selecione as 2 cartas da sua mão.");
    }
    const board = readBoard();

    const payload = {
      hole_cards: hole.join(" "),
      board: board,
      num_opponents: parseInt(document.getElementById("opponents").value, 10),
      pot: parseFloat(document.getElementById("pot").value) || 0,
      to_call: parseFloat(document.getElementById("to_call").value) || 0,
      iterations:
        parseInt(document.getElementById("iterations").value, 10) || 25000,
    };

    setLoading(btn, true);

    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erro do servidor (${res.status})`);
    }

    const data = await res.json();
    // Remember the snapshot + the inputs used (so we can persist them later).
    lastAnalysis = {
      data,
      inputs: {
        hole_cards: payload.hole_cards,
        board: payload.board,
        num_opponents: payload.num_opponents,
        pot: payload.pot,
        to_call: payload.to_call,
      },
    };
    resetSaveForm();
    renderResults(data);
  } catch (e) {
    errBox.textContent = e.message;
    errBox.hidden = false;
  } finally {
    setLoading(btn, false);
  }
}

function setLoading(btn, loading) {
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
}

/* ── Count-up para porcentagens ─────────────────────────── */

function animateNumber(el, to, { duration = 800, suffix = "", decimals = 2 } = {}) {
  if (prefersReducedMotion) {
    el.textContent = `${to.toFixed(decimals)}${suffix}`;
    return;
  }
  const from = parseFloat((el.dataset.value || "0"));
  const start = performance.now();
  const delta = to - from;

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  function step(now) {
    const t = Math.min(1, (now - start) / duration);
    const value = from + delta * easeOutCubic(t);
    el.textContent = `${value.toFixed(decimals)}${suffix}`;
    if (t < 1) requestAnimationFrame(step);
    else el.dataset.value = String(to);
  }
  requestAnimationFrame(step);
}

/* ── Render dos resultados ─────────────────────────────── */

function renderResults(data) {
  showResults();

  // Hand pill
  const catPt = CATEGORY_PT[data.hand.category] || data.hand.category_label;
  const handLabel = data.hand.is_preflop ? `${catPt} (pré-flop)` : catPt;
  document.getElementById("r-hand").textContent = handLabel;

  // Equity bar
  const hero = data.equity.hero_pct;
  const bar = document.getElementById("r-equity-bar");
  const barWidth = Math.max(0, Math.min(100, hero));
  // Force a paint at 0 width first when going down, so the transition shows.
  requestAnimationFrame(() => { bar.style.width = `${barWidth}%`; });

  animateNumber(
    document.getElementById("r-equity-text"),
    hero,
    { suffix: "%", duration: 900 }
  );
  animateNumber(document.getElementById("r-tie"),  data.equity.tie_pct,  { suffix: "", duration: 700 });
  animateNumber(document.getElementById("r-loss"), data.equity.loss_pct, { suffix: "", duration: 700 });

  document.getElementById("r-iters").textContent =
    `${data.equity.iterations.toLocaleString("pt-BR")} simulações`;

  // Outs
  const outsCountEl = document.getElementById("r-outs-count");
  const outsStrip = document.getElementById("r-outs-strip");
  outsStrip.innerHTML = "";
  if (data.outs.count > 0) {
    outsCountEl.textContent = data.outs.count;
    const visible = data.outs.cards.slice(0, 10);
    for (const c of visible) {
      const chip = document.createElement("span");
      chip.className = `out-chip ${SUIT_COLOR[c[1]]}`;
      chip.textContent = cardFace(c);
      outsStrip.appendChild(chip);
    }
    if (data.outs.cards.length > visible.length) {
      const more = document.createElement("span");
      more.className = "out-chip more";
      more.textContent = `+${data.outs.cards.length - visible.length}`;
      outsStrip.appendChild(more);
    }
    document.getElementById("r-next").textContent =
      `${data.outs.next_card_improve_pct.toFixed(2)}%`;
  } else {
    outsCountEl.textContent = "—";
    document.getElementById("r-next").textContent = "—";
  }

  // Pot odds
  const po = data.pot_odds;
  document.getElementById("r-potodds").textContent =
    po.ratio_str === "free" ? "pagamento livre" : po.ratio_str;
  document.getElementById("r-required").textContent =
    po.ratio_str === "free" ? "0,00%" : `${po.required_equity_pct.toFixed(2)}%`;

  // Action box
  const action = ACTION_PT[data.suggestion] || {
    label: data.suggestion.toUpperCase(),
    cls: "call",
  };
  const actionEl = document.getElementById("r-action");
  const actionBox = document.getElementById("r-action-box");

  actionEl.textContent = action.label;
  actionEl.className = `action ${action.cls}`;
  actionBox.className = `action-box ${action.cls}`;

  // Re-trigger entrance animation.
  actionBox.style.animation = "none";
  // eslint-disable-next-line no-unused-expressions
  actionBox.offsetHeight;
  actionBox.style.animation = "";

  const evEl = document.getElementById("r-ev");
  if (po.ratio_str === "free") {
    evEl.textContent = "Sem custo para continuar";
    evEl.className = "ev";
  } else {
    const edge = po.edge_pct;
    const sign = edge >= 0 ? "+" : "";
    evEl.textContent = po.is_plus_ev
      ? `+EV vs pot odds · margem ${sign}${edge.toFixed(2)}%`
      : `-EV vs pot odds · margem ${sign}${edge.toFixed(2)}%`;
    evEl.className = `ev ${po.is_plus_ev ? "plus" : "minus"}`;
  }
}

/* ── OCR via Ollama ────────────────────────────────────── */

function bindOcr() {
  const drop = document.getElementById("ocr-drop");
  const fileInput = document.getElementById("ocr-file");
  if (!drop || !fileInput) return;

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) runOcr(file);
    fileInput.value = ""; // allow re-selecting the same file later
  });

  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.remove("dragover");
    })
  );
  drop.addEventListener("drop", (e) => {
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) runOcr(file);
  });

  document.addEventListener("paste", (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          e.preventDefault();
          runOcr(file);
          return;
        }
      }
    }
  });
}

function setOcrStatus(state, html) {
  const el = document.getElementById("ocr-status");
  if (!el) return;
  el.className = `ocr-status ${state || ""}`.trim();
  el.innerHTML = html;
  el.hidden = !html;
}

async function runOcr(file) {
  setOcrStatus("loading", "Lendo a imagem com o modelo de visão local…");

  try {
    const form = new FormData();
    form.append("image", file, file.name || "screenshot.png");
    const res = await fetch("/api/ocr", { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail = data.detail || `Erro do servidor (${res.status})`;
      setOcrStatus("error", `<strong>Falha na leitura.</strong> ${escapeHtml(detail)}`);
      return;
    }

    applyOcrResult(data);
    const warnHtml = (data.warnings || []).length
      ? `<ul class="warnings">${data.warnings
          .map((w) => `<li>${escapeHtml(w)}</li>`)
          .join("")}</ul>`
      : "";
    const tone = (data.warnings || []).length ? "warn" : "success";
    setOcrStatus(
      tone,
      `<strong>Leitura automática — confira as cartas antes de analisar.</strong>${warnHtml}`
    );
  } catch (e) {
    setOcrStatus("error", `<strong>Falha na leitura.</strong> ${escapeHtml(e.message)}`);
  }
}

function applyOcrResult(data) {
  // Clear current cards but DO NOT touch scenario unless OCR provided values.
  clearCardsOnly();

  const touchedSlots = [];

  // Fill hole cards first, then board, in declaration order.
  const desiredCards = [];
  for (const c of data.hole_cards || []) desiredCards.push({ kind: "hole", value: c });
  for (const c of data.board || [])      desiredCards.push({ kind: "board", value: c });

  // Walk SLOT_ORDER and assign cards in matching kinds.
  let holeIdx = 0;
  let boardIdx = 0;
  for (const card of desiredCards) {
    let target = null;
    if (card.kind === "hole" && holeIdx < 2) {
      target = SLOT_ORDER[holeIdx]; // hole-0 or hole-1
      holeIdx += 1;
    } else if (card.kind === "board") {
      // hole-0,hole-1 then flop-0..river-0; board fills from index 2 onward
      target = SLOT_ORDER[2 + boardIdx];
      boardIdx += 1;
    }
    if (!target) continue;
    if (Object.values(slots).includes(card.value)) continue; // dedupe vs already placed
    slots[target] = card.value;
    renderSlot(target);
    touchedSlots.push(target);
  }
  refreshUsed();

  // Highlight every slot OCR populated until the user touches it.
  touchedSlots.forEach((id) => {
    const el = document.querySelector(`.card-slot[data-slot="${id}"]`);
    if (!el) return;
    el.classList.add("ocr-filled");
    const clear = () => {
      el.classList.remove("ocr-filled");
      el.removeEventListener("click", clear);
    };
    el.addEventListener("click", clear);
  });

  // Scenario fields — only override when OCR actually provided a value.
  fillScenarioField("opponents", data.num_opponents);
  fillScenarioField("pot", data.pot);
  fillScenarioField("to_call", data.to_call);
}

function fillScenarioField(id, value) {
  if (value === null || value === undefined) return;
  const el = document.getElementById(id);
  if (!el) return;
  el.value = String(value);
  el.classList.add("ocr-filled");
  const clear = () => {
    el.classList.remove("ocr-filled");
    el.removeEventListener("input", clear);
    el.removeEventListener("focus", clear);
  };
  el.addEventListener("input", clear);
  el.addEventListener("focus", clear);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Format a number as a 2-decimal percentage string. Returns "—" when the
// input is not a finite number (null/undefined/NaN) so missing fields don't
// poison templated rendering.
function fmtPct(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(2) : "—";
}

/* ── Salvar mão / Histórico ────────────────────────────── */

function bindSaveForm() {
  const toggle = document.getElementById("save-toggle");
  const cancel = document.getElementById("save-cancel");
  const confirm = document.getElementById("save-confirm");
  const chips = document.getElementById("save-action-chips");

  toggle.addEventListener("click", openSaveForm);
  cancel.addEventListener("click", resetSaveForm);
  confirm.addEventListener("click", confirmSaveHand);

  chips.addEventListener("click", (e) => {
    const btn = e.target.closest(".action-chip");
    if (!btn) return;
    const action = btn.dataset.action;
    if (pendingTakenAction === action) {
      pendingTakenAction = null;
    } else {
      pendingTakenAction = action;
    }
    chips.querySelectorAll(".action-chip").forEach((el) => {
      el.classList.toggle("selected", el.dataset.action === pendingTakenAction);
    });
  });
}

function openSaveForm() {
  if (!lastAnalysis) return;
  document.getElementById("save-form").hidden = false;
  document.getElementById("save-toggle").hidden = true;
  document.getElementById("save-toast").hidden = true;
}

function resetSaveForm() {
  const form = document.getElementById("save-form");
  const toggle = document.getElementById("save-toggle");
  if (!form || !toggle) return;
  form.hidden = true;
  toggle.hidden = false;
  document.getElementById("save-notes").value = "";
  document.getElementById("save-toast").hidden = true;
  pendingTakenAction = null;
  document.querySelectorAll("#save-action-chips .action-chip").forEach((el) => {
    el.classList.remove("selected");
  });
  setLoading(document.getElementById("save-confirm"), false);
}

function buildSavePayload() {
  if (!lastAnalysis) return null;
  const { data, inputs } = lastAnalysis;
  const notes = document.getElementById("save-notes").value.trim();
  return {
    hole_cards: inputs.hole_cards,
    board: inputs.board,
    num_opponents: inputs.num_opponents,
    pot: inputs.pot,
    to_call: inputs.to_call,
    street: data.street,
    win_pct: data.equity.win_pct,
    tie_pct: data.equity.tie_pct,
    loss_pct: data.equity.loss_pct,
    iterations: data.equity.iterations,
    hand_category: data.hand.category,
    hand_label: data.hand.category_label || data.hand.label,
    is_preflop: data.hand.is_preflop,
    outs_count: data.outs.count || 0,
    outs_cards: (data.outs.cards || []).join(" "),
    next_card_improve_pct: data.outs.next_card_improve_pct,
    required_equity_pct: data.pot_odds.required_equity_pct,
    ratio_str: data.pot_odds.ratio_str,
    is_plus_ev: data.pot_odds.is_plus_ev,
    edge_pct: data.pot_odds.edge_pct,
    suggestion: data.suggestion,
    taken_action: pendingTakenAction,
    notes: notes || null,
  };
}

async function confirmSaveHand() {
  if (!lastAnalysis) return;
  const btn = document.getElementById("save-confirm");
  const toast = document.getElementById("save-toast");
  toast.hidden = true;

  const payload = buildSavePayload();
  setLoading(btn, true);

  try {
    const res = await fetch("/api/hands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Falha ao salvar (HTTP ${res.status})`);
    }

    // Hide form, show toast, refresh history.
    document.getElementById("save-form").hidden = true;
    document.getElementById("save-toggle").hidden = false;
    toast.className = "save-toast";
    toast.textContent = "Mão salva no histórico.";
    toast.hidden = false;
    pendingTakenAction = null;
    document.getElementById("save-notes").value = "";
    document.querySelectorAll("#save-action-chips .action-chip").forEach((el) => {
      el.classList.remove("selected");
    });
    loadHistory();
  } catch (e) {
    toast.className = "save-toast error";
    toast.textContent = e.message;
    toast.hidden = false;
  } finally {
    setLoading(btn, false);
  }
}

/* ── Histórico ─────────────────────────────────────────── */

async function loadHistory() {
  try {
    const res = await fetch("/api/hands?limit=50&offset=0");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    renderHistoryList(body);
  } catch (e) {
    renderHistoryList({ items: [], total: 0 });
    console.warn("Falha ao carregar histórico:", e.message);
  }
}

function renderHistoryList(body) {
  const list = document.getElementById("history-list");
  const empty = document.getElementById("history-empty");
  const counter = document.getElementById("history-count");

  const items = Array.isArray(body && body.items) ? body.items : [];
  // Always trust body.total when present; fall back to items length only
  // when total is missing (e.g. the catch path in loadHistory).
  const total = Number.isFinite(body && body.total) ? body.total : items.length;
  counter.textContent = total === 1 ? "1 mão salva" : `${total} mãos salvas`;

  list.innerHTML = "";
  if (items.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  // Render rows independently — a malformed row should never block the rest.
  // Use console.error with the actual Error object so the stack trace shows
  // up in DevTools (warn was hiding the root cause during the fmtPct bug).
  let rendered = 0;
  for (const hand of items) {
    try {
      list.appendChild(buildHistoryItem(hand));
      rendered += 1;
    } catch (err) {
      console.error(`[history] Falha ao renderizar mão id=${hand && hand.id}:`, err);
    }
  }
  // Soft warning when some rows were dropped — keeps the user from thinking
  // the data was lost.
  if (rendered < items.length) {
    const note = document.createElement("p");
    note.className = "history-empty";
    note.innerHTML = `<strong>${items.length - rendered}</strong> mão(s) não puderam ser exibidas por dados inconsistentes.`;
    list.appendChild(note);
  }
  pendingDeleteId = null;
}

function buildHistoryItem(hand) {
  const item = document.createElement("div");
  item.className = "history-item";
  item.dataset.id = String(hand.id);

  // Cards block
  const cardsCell = document.createElement("div");
  cardsCell.className = "history-cards";
  for (const c of parseCardList(hand.hole_cards)) cardsCell.appendChild(miniCardEl(c));
  if (hand.board && hand.board.trim()) {
    const sep = document.createElement("span");
    sep.className = "mini-card sep";
    sep.textContent = "|";
    cardsCell.appendChild(sep);
    for (const c of parseCardList(hand.board)) cardsCell.appendChild(miniCardEl(c));
  }

  // Equity block
  const equityCell = document.createElement("div");
  equityCell.className = "history-equity";
  const hero = hand.win_pct + hand.tie_pct / 2;
  const catPt = CATEGORY_PT[hand.hand_category] || hand.hand_label;
  equityCell.innerHTML = `
    <span class="pct">${fmtPct(hero)}%</span>
    <span class="sub">${escapeHtml(catPt)} · ${escapeHtml(hand.street)}</span>
  `;

  // Actions block (suggestion vs taken)
  const actionsCell = document.createElement("div");
  actionsCell.className = "history-actions";
  actionsCell.innerHTML = `
    <div class="row">
      <span class="label">Sugerido</span>
      ${tagEl(hand.suggestion)}
    </div>
    <div class="row">
      <span class="label">Tomada</span>
      ${hand.taken_action ? tagEl(hand.taken_action) : `<span class="tag none">não informada</span>`}
    </div>
  `;

  // Date
  const whenCell = document.createElement("div");
  whenCell.className = "history-when";
  whenCell.textContent = formatTimestamp(hand.created_at);

  // Controls
  const controls = document.createElement("div");
  controls.className = "history-controls";
  controls.innerHTML = `
    <button type="button" class="icon-btn" data-role="reopen" title="Reabrir esta mão para revisão">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>
        <path d="M21 3v5h-5"/>
      </svg>
    </button>
    <button type="button" class="icon-btn danger" data-role="delete" title="Excluir esta mão">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        <path d="M10 11v6"/>
        <path d="M14 11v6"/>
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
      </svg>
    </button>
  `;

  item.appendChild(cardsCell);
  item.appendChild(equityCell);
  item.appendChild(actionsCell);
  item.appendChild(whenCell);
  item.appendChild(controls);

  if (hand.notes) {
    const notes = document.createElement("div");
    notes.className = "notes";
    notes.textContent = `“${hand.notes}”`;
    item.appendChild(notes);
  }

  controls.querySelector('[data-role="reopen"]').addEventListener("click", () => reopenHand(hand));
  controls.querySelector('[data-role="delete"]').addEventListener("click", () => askDeleteHand(hand.id, controls));

  return item;
}

function parseCardList(text) {
  if (!text) return [];
  return text.trim().split(/\s+/).filter(Boolean);
}

function miniCardEl(card) {
  const el = document.createElement("span");
  el.className = `mini-card ${SUIT_COLOR[card[1]] || "black"}`;
  el.textContent = cardFace(card);
  return el;
}

function tagEl(action) {
  // Defensive: a history row can legitimately have a null/empty action
  // (e.g. taken_action when the user didn't pick one). Without this guard,
  // `action.toUpperCase()` would throw inside the inline-template literal
  // and abort rendering of every later row.
  if (action === null || action === undefined || action === "") {
    return `<span class="tag none">não informada</span>`;
  }
  const known = ACTION_PT[action];
  const label = known ? known.label : String(action).toUpperCase();
  const cls = known ? known.cls : "none";
  return `<span class="tag ${cls}">${escapeHtml(label)}</span>`;
}

function formatTimestamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function askDeleteHand(id, container) {
  if (container.querySelector(".delete-confirm")) return;
  // Hide the icon buttons (don't destroy them) and append a confirm pill.
  const buttons = Array.from(container.children);
  buttons.forEach((el) => { el.dataset.prevDisplay = el.style.display; el.style.display = "none"; });

  const confirm = document.createElement("span");
  confirm.className = "delete-confirm";
  confirm.innerHTML = `Excluir? <button type="button" class="yes">Sim</button><button type="button" class="no">Não</button>`;
  container.appendChild(confirm);

  confirm.querySelector(".yes").addEventListener("click", () => doDeleteHand(id));
  confirm.querySelector(".no").addEventListener("click", () => {
    confirm.remove();
    buttons.forEach((el) => { el.style.display = el.dataset.prevDisplay || ""; });
  });
}

async function doDeleteHand(id) {
  try {
    const res = await fetch(`/api/hands/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Falha ao excluir (HTTP ${res.status})`);
    }
  } catch (e) {
    console.warn("Erro ao excluir mão:", e.message);
  } finally {
    loadHistory();
  }
}

function reopenHand(hand) {
  // 1. Populate slots from saved hole + board strings.
  clearCardsOnly();
  const holeCards = parseCardList(hand.hole_cards);
  const boardCards = parseCardList(hand.board);
  let slotIdx = 0;
  for (const c of holeCards.slice(0, 2)) {
    slots[SLOT_ORDER[slotIdx++]] = c;
  }
  // hole cards take indices 0-1; board starts at index 2.
  slotIdx = 2;
  for (const c of boardCards) {
    if (slotIdx >= SLOT_ORDER.length) break;
    slots[SLOT_ORDER[slotIdx++]] = c;
  }
  for (const id of SLOT_ORDER) renderSlot(id);
  refreshUsed();

  // 2. Populate scenario fields.
  document.getElementById("opponents").value = String(hand.num_opponents);
  document.getElementById("pot").value = String(hand.pot);
  document.getElementById("to_call").value = String(hand.to_call);
  document.getElementById("iterations").value = String(hand.iterations || 25000);

  // 3. Render the saved result snapshot directly (no re-simulation).
  const synthetic = {
    street: hand.street,
    hole_cards: holeCards,
    board: boardCards,
    hand: {
      category: hand.hand_category,
      category_label: hand.hand_label,
      label: hand.hand_label,
      is_preflop: hand.is_preflop,
    },
    equity: {
      win_pct: hand.win_pct,
      tie_pct: hand.tie_pct,
      loss_pct: hand.loss_pct,
      iterations: hand.iterations,
      hero_pct: hand.win_pct + hand.tie_pct / 2,
    },
    outs: {
      count: hand.outs_count,
      cards: parseCardList(hand.outs_cards),
      next_card_improve_pct: hand.next_card_improve_pct,
      current_category: hand.hand_category,
    },
    pot_odds: {
      required_equity_pct: hand.required_equity_pct,
      ratio_str: hand.ratio_str,
      is_plus_ev: hand.is_plus_ev,
      edge_pct: hand.edge_pct,
    },
    suggestion: hand.suggestion,
  };
  lastAnalysis = {
    data: synthetic,
    inputs: {
      hole_cards: hand.hole_cards,
      board: hand.board,
      num_opponents: hand.num_opponents,
      pot: hand.pot,
      to_call: hand.to_call,
    },
  };
  renderResults(synthetic);

  // 4. Scroll the result panel into view (without smooth on reduced motion).
  const results = document.getElementById("results");
  if (results) {
    results.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start",
    });
  }
}

init();
