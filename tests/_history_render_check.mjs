// Headless smoke check for the history list renderer.
//
// Loads the real app.js inside a vm context with a minimal DOM stub, then
// invokes buildHistoryItem() against representative SavedHand payloads.
// Exits with code 1 (and prints the failing payload + stack) on any throw.
//
// This catches the kind of bug where a helper was referenced but never
// defined — the in-app try/catch would swallow the ReferenceError and the
// real cause stayed hidden.

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = path.resolve(__dirname, "../reporter_poker/web/static/app.js");

// ─── Minimal DOM stub (only what buildHistoryItem actually touches). ─────────

class FakeClassList {
  constructor() { this.s = new Set(); }
  add(...c)    { c.forEach((x) => x && this.s.add(x)); }
  remove(...c) { c.forEach((x) => this.s.delete(x)); }
  toggle(c, on) {
    if (on === undefined) on = !this.s.has(c);
    on ? this.s.add(c) : this.s.delete(c);
    return on;
  }
  contains(c) { return this.s.has(c); }
  toString()  { return [...this.s].join(" "); }
}

class FakeEl {
  constructor(tag) {
    this.tagName = (tag || "div").toUpperCase();
    this.children = [];
    this.classList = new FakeClassList();
    this.style = {};
    this.dataset = {};
    this._textContent = "";
    this._innerHTML = "";
    this._roleNodes = {};
  }
  get className() { return this.classList.toString(); }
  set className(v) {
    this.classList = new FakeClassList();
    (v || "").split(/\s+/).filter(Boolean).forEach((c) => this.classList.add(c));
  }
  get textContent() { return this._textContent; }
  set textContent(v) { this._textContent = String(v); }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(v) {
    this._innerHTML = String(v);
    this._roleNodes = {};
    const re = /data-role="([^"]+)"/g;
    let m;
    while ((m = re.exec(this._innerHTML))) {
      const node = new FakeEl("button");
      node.dataset.role = m[1];
      this._roleNodes[m[1]] = node;
    }
  }
  appendChild(child) { this.children.push(child); return child; }
  removeChild() {}
  addEventListener() {}
  removeEventListener() {}
  querySelector(sel) {
    const m = sel.match(/^\[data-role="([^"]+)"\]$/);
    return m ? this._roleNodes[m[1]] || null : null;
  }
  querySelectorAll() { return []; }
  scrollIntoView() {}
}

const document = {
  createElement: (tag) => new FakeEl(tag),
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
};

const ctx = {
  document,
  window: { matchMedia: () => ({ matches: false }) },
  console,
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  FormData: function () {},
  performance: { now: () => 0 },
  requestAnimationFrame: () => 0,
  setTimeout, clearTimeout,
  Number, String, Array, Math, Object, JSON, Set, Map, Date, Error,
};
vm.createContext(ctx);

// Disable init() so we don't try to bind to non-existent DOM elements.
const src = fs.readFileSync(APP_JS, "utf-8")
  .replace(/\ninit\(\);\s*$/m, "\n// init() disabled for headless render check");

vm.runInContext(src, ctx);

// ─── Test cases (payload shapes the backend actually returns). ───────────────

const CASES = [
  {
    name: "turn with null taken_action and notes",
    hand: {
      id: 7,
      created_at: "2026-05-26T18:20:10+00:00",
      hole_cards: "6s 8h",
      board: "Kd 4s Kh Td",
      num_opponents: 1,
      pot: 100, to_call: 50,
      street: "turn",
      win_pct: 19.3, tie_pct: 5.9, loss_pct: 74.8,
      iterations: 5000,
      hand_category: "PAIR", hand_label: "Pair",
      is_preflop: false,
      outs_count: 0, outs_cards: "",
      next_card_improve_pct: null,
      required_equity_pct: 33.33, ratio_str: "2.0:1",
      is_plus_ev: false, edge_pct: -8.0,
      suggestion: "fold",
      taken_action: null, notes: null,
    },
  },
  {
    name: "preflop with taken_action and notes",
    hand: {
      id: 8, created_at: "2026-05-26T18:25:00+00:00",
      hole_cards: "As Ad", board: "",
      num_opponents: 2, pot: 50, to_call: 20,
      street: "preflop",
      win_pct: 75.5, tie_pct: 0.5, loss_pct: 24.0,
      iterations: 25000,
      hand_category: "PAIR", hand_label: "Pocket As (preflop)",
      is_preflop: true,
      outs_count: 0, outs_cards: "",
      next_card_improve_pct: null,
      required_equity_pct: 28.57, ratio_str: "2.5:1",
      is_plus_ev: true, edge_pct: 47.18,
      suggestion: "raise",
      taken_action: "call", notes: "oponente passivo",
    },
  },
  {
    name: "river with full set of outs cards",
    hand: {
      id: 9, created_at: "2026-05-26T19:00:00+00:00",
      hole_cards: "As Ks", board: "Qs Js Ts 4c 2d",
      num_opponents: 1, pot: 300, to_call: 100,
      street: "river",
      win_pct: 99.0, tie_pct: 0.5, loss_pct: 0.5,
      iterations: 25000,
      hand_category: "ROYAL_FLUSH", hand_label: "Royal Flush",
      is_preflop: false,
      outs_count: 0, outs_cards: "",
      next_card_improve_pct: null,
      required_equity_pct: 25.0, ratio_str: "3.0:1",
      is_plus_ev: true, edge_pct: 74.5,
      suggestion: "raise",
      taken_action: "raise", notes: null,
    },
  },
  {
    name: "unknown suggestion still renders without throwing",
    hand: {
      id: 10, created_at: "2026-05-26T19:30:00+00:00",
      hole_cards: "5h 5d", board: "5c Kd 2h",
      num_opponents: 3, pot: 80, to_call: 0,
      street: "flop",
      win_pct: 92.0, tie_pct: 1.0, loss_pct: 7.0,
      iterations: 10000,
      hand_category: "THREE_OF_A_KIND", hand_label: "Three of a Kind",
      is_preflop: false,
      outs_count: 1, outs_cards: "5s",
      next_card_improve_pct: 2.13,
      required_equity_pct: 0.0, ratio_str: "free",
      is_plus_ev: true, edge_pct: 93.5,
      suggestion: "all-in",  // unknown action — must NOT crash
      taken_action: null, notes: null,
    },
  },
];

let failures = 0;
for (const c of CASES) {
  try {
    const el = ctx.buildHistoryItem(c.hand);
    if (!el || el.children.length === 0) {
      throw new Error("returned element has no children");
    }
    console.log(`OK   ${c.name} — children=${el.children.length}`);
  } catch (err) {
    failures += 1;
    console.error(`FAIL ${c.name}`);
    console.error("     payload:", JSON.stringify(c.hand));
    console.error("     error:", err && err.stack ? err.stack : err);
  }
}

if (failures > 0) {
  console.error(`\n${failures} caso(s) falharam.`);
  process.exit(1);
}
console.log(`\n${CASES.length} cenários renderizados com sucesso.`);
