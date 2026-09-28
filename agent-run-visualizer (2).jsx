import React, { useEffect, useRef, useState } from "react";

/* ============================================================
   AGENT RUN VISUALIZER — auto-playing "inside the agent's mind"
   Each scene is a template component receiving (t, data) so real
   backend data can be swapped into SCRIPT later. t = 0..1 local
   progress driven by one master clock. Durations in SCRIPT scale
   1:1 to real run when wired live.
   ============================================================ */

/* ---------- palette / tokens ---------- */
const C = {
  paper: "#F5F4EE",
  card: "#FFFFFF",
  ink: "#25313D",
  slate: "#7E8A96",
  line: "#E4E2D9",
  blue: "#1467B3",
  blueSoft: "#E4EEF7",
  amber: "#BC7F26",
  amberSoft: "#F6ECDC",
  green: "#2E7D5B",
  red: "#B3543C",
};

/* ---------- helpers ---------- */
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const seg = (t, a, b) => clamp01((t - a) / (b - a));
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;
const rnd = (seed) => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const fmtClock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/* ---------- sample run data (swap with real backend data later) ---------- */
const QUERY =
  "Find sales decision-makers at mid-cap semiconductor companies with strong revenue growth in North America";

const COMPANIES = [
  { name: "Veridian Microdevices", tk: "VMD", cap: "$4.2B", growth: "+23.4%", hq: "Austin, TX" },
  { name: "Northlake Photonics", tk: "NLP", cap: "$2.8B", growth: "+18.9%", hq: "Portland, OR" },
  { name: "Cassia Semiconductors", tk: "CSSA", cap: "$6.1B", growth: "+16.2%", hq: "San Jose, CA" },
  { name: "Ridgeline Analog", tk: "RDGA", cap: "$3.5B", growth: "+21.7%", hq: "Boulder, CO" },
  { name: "Tanager Circuits", tk: "TNGR", cap: "$2.3B", growth: "+19.5%", hq: "Raleigh, NC" },
  { name: "Meridian Fab Systems", tk: "MFS", cap: "$8.7B", growth: "+15.8%", hq: "Phoenix, AZ" },
];

const PEOPLE = [
  { n: "Priya Raghunathan", r: "VP Sales", co: "Veridian Microdevices" },
  { n: "Tomasz Wielgosz", r: "Chief Revenue Officer", co: "Cassia Semiconductors" },
  { n: "Danielle Okafor", r: "Head of Enterprise Sales", co: "Northlake Photonics" },
  { n: "Marcus Ehrlich", r: "Director, Business Dev.", co: "Ridgeline Analog" },
  { n: "Yuki Hamasaki", r: "VP GTM Strategy", co: "Tanager Circuits" },
  { n: "Renata Villalobos", r: "Regional Sales Director", co: "Meridian Fab Systems" },
  { n: "Callum Baird-Whyte", r: "VP Sales, Americas", co: "Cassia Semiconductors" },
  { n: "Ines Fontaine", r: "Head of Partnerships", co: "Veridian Microdevices" },
  { n: "Deshawn Merritt", r: "CRO", co: "Northlake Photonics" },
  { n: "Aoife Gallagher", r: "Sales Director, West", co: "Tanager Circuits" },
];

const TICKERS = [
  "VMD","AXIQ","NLP","KORV","CSSA","PYLT","RDGA","QMET",
  "TNGR","BRUX","MFS","HLCN","OSPR","VLTQ","CINDR","MZEN",
  "SOLV","TARN","KEPL","FENN","ORYX","LUMA","DRAV","PICO",
  "ZEPH","CRWN","ALTQ","NOVE","GRYS","TALO","WREN","ELMS",
  "IRID","COBL","SABL","MYRA","HAWX","JUNI","PLTN","VOSS",
  "REMY","CYGN","ONYX","FLNT","ARBR","SLTE","QUIL","BRNT",
];
const PASS_SET = new Set([0, 2, 4, 6, 8, 10, 13, 19, 22, 27, 33, 41]);

/* ---------- scene script: durations in ms (scale 1:1 to real run later) ---------- */
const SCRIPT = [
  { id: "intro", name: "Reading your request", dur: 3200 },
  { id: "query", name: "Formulating the search", dur: 5200, real: "6s" },
  { id: "screen", name: "Screening the market", dur: 6200, real: "10s" },
  { id: "enrich", name: "Enriching companies", dur: 3600, real: "3s" },
  { id: "clean", name: "Cleaning & shortlisting", dur: 5200, real: "15s" },
  { id: "parallel", name: "Deep research · 4 lanes", dur: 27000, real: "3m 39s" },
  { id: "export", name: "Assembling your report", dur: 4600, real: "4s" },
];
const TOTAL = SCRIPT.reduce((a, s) => a + s.dur, 0);
const REAL_TOTAL_S = 256; // 4:16 real runtime, mapped to playback for the sim clock

/* ---------- tiny SVG icons (no emoji) ---------- */
const Ic = {
  spark: (p) => (
    <svg viewBox="0 0 16 16" {...p}><path d="M8 1.5 9.6 6l4.4 1.6L9.6 9.2 8 13.7 6.4 9.2 2 7.6 6.4 6Z" fill="currentColor"/></svg>
  ),
  lens: (p) => (
    <svg viewBox="0 0 16 16" {...p}><circle cx="7" cy="7" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.7"/><path d="m10.4 10.4 3.3 3.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/></svg>
  ),
  grid: (p) => (
    <svg viewBox="0 0 16 16" {...p}><path d="M2.5 5h11M2.5 8.5h11M2.5 12h11M5.5 3v11M10.5 3v11" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
  ),
  funnel: (p) => (
    <svg viewBox="0 0 16 16" {...p}><path d="M2.5 3h11l-4.2 5v4.5l-2.6 1.2V8Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg>
  ),
  net: (p) => (
    <svg viewBox="0 0 16 16" {...p}><circle cx="8" cy="3.4" r="1.8" fill="currentColor"/><circle cx="3.4" cy="11.5" r="1.8" fill="currentColor"/><circle cx="12.6" cy="11.5" r="1.8" fill="currentColor"/><path d="M8 5.2 4.2 10m3.8-4.8 3.8 4.8M5.2 11.5h5.6" stroke="currentColor" strokeWidth="1.3"/></svg>
  ),
  doc: (p) => (
    <svg viewBox="0 0 16 16" {...p}><path d="M4 1.8h5.4L12.5 5v9.2H4Z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M5.8 8h4.8M5.8 10.6h4.8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
  ),
  check: (p) => (
    <svg viewBox="0 0 16 16" {...p}><path d="m3.2 8.4 3 3 6.6-7" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"/></svg>
  ),
  plane: (p) => (
    <svg viewBox="0 0 20 20" {...p}><path d="M2 10.2 18 3l-4.6 14-3.2-5.4L2 10.2Zm8.2 1.4L18 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round"/></svg>
  ),
  person: (p) => (
    <svg viewBox="0 0 16 16" {...p}><circle cx="8" cy="5.2" r="2.6" fill="currentColor"/><path d="M2.8 13.6c.7-2.7 2.8-4 5.2-4s4.5 1.3 5.2 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
  ),
  mail: (p) => (
    <svg viewBox="0 0 16 16" {...p}><rect x="2" y="3.6" width="12" height="8.8" rx="1.4" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="m2.6 4.6 5.4 4.2 5.4-4.2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg>
  ),
  globe: (p) => (
    <svg viewBox="0 0 16 16" {...p}><circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M2.4 8h11.2M8 2.4c-3.4 3.4-3.4 7.8 0 11.2 3.4-3.4 3.4-7.8 0-11.2Z" fill="none" stroke="currentColor" strokeWidth="1.2"/></svg>
  ),
  crawl: (p) => (
    <svg viewBox="0 0 16 16" {...p}><rect x="2.2" y="2.6" width="11.6" height="10.8" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M2.4 5.4h11.2M5 8h6M5 10.6h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
  ),
};

const PHASE_ICONS = [Ic.spark, Ic.spark, Ic.lens, Ic.grid, Ic.funnel, Ic.net, Ic.doc];

/* ============================================================
   SCENE FRAME — shared template so every scene stays uniform
   ============================================================ */
function SceneFrame({ eyebrow, title, note, children }) {
  return (
    <div className="scene-enter" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, padding: "4px 6px 10px" }}>
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <div className="scene-title">{title}</div>
        </div>
        {note && <div className="scene-note">{note}</div>}
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>{children}</div>
    </div>
  );
}

/* ============================================================
   SCENE 0 — intro acknowledgement
   ============================================================ */
function IntroScene({ t, data }) {
  const a = easeOut(seg(t, 0.05, 0.4));
  const b = easeOut(seg(t, 0.35, 0.75));
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ maxWidth: 640, textAlign: "left" }}>
        <div
          style={{
            display: "flex", gap: 14, alignItems: "flex-start",
            opacity: a, transform: `translateY(${lerp(14, 0, a)}px)`,
          }}
        >
          <div className="agent-dot"><Ic.spark width="16" height="16" /></div>
          <div>
            <div style={{ fontSize: 15, color: C.slate, marginBottom: 6 }}>You asked</div>
            <div style={{ fontSize: 21, fontWeight: 600, lineHeight: 1.45, letterSpacing: "-0.01em" }}>
              “{data.query}”
            </div>
            <div
              style={{
                marginTop: 18, fontSize: 16, color: C.blue, fontWeight: 600,
                opacity: b, transform: `translateY(${lerp(10, 0, b)}px)`,
                display: "flex", alignItems: "center", gap: 8,
              }}
            >
              <span className="pulse-dot" />
              On it — starting the run. Watch me work.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   SCENE 1 — query flies apart into keywords, locks into slots
   ============================================================ */
const SLOTS = [
  { label: "SECTOR", derived: "Semiconductors" },
  { label: "MARKET CAP", derived: "$2B – $10B" },
  { label: "SIGNAL", derived: "Rev growth > 15%" },
  { label: "REGION", derived: "North America" },
  { label: "ROLES", derived: "VP Sales · CRO · BD" },
];
const QWORDS = QUERY.split(" ").map((w, i) => {
  const key = {
    sales: 4, "decision-makers": 4, "mid-cap": 1, semiconductor: 0,
    revenue: 2, growth: 2, North: 3, America: 3,
  };
  return { w, i, slot: key[w] ?? -1 };
});

function layoutSentence(words, width) {
  const rows = [[]];
  let x = 0;
  const wOf = (w) => w.length * 8.6 + 26;
  words.forEach((wd) => {
    const ww = wOf(wd.w);
    if (x + ww > width - 40) { rows.push([]); x = 0; }
    rows[rows.length - 1].push({ ...wd, ww });
    x += ww + 8;
  });
  const out = [];
  rows.forEach((row, r) => {
    const rowW = row.reduce((a, c) => a + c.ww + 8, -8);
    let cx = (width - rowW) / 2;
    row.forEach((wd) => { out[wd.i] = { x: cx, y: 26 + r * 46, ww: wd.ww }; cx += wd.ww + 8; });
  });
  return out;
}

function QueryScene({ t, data }) {
  const W = 880, H = 380;
  const sent = layoutSentence(QWORDS, W);
  const scatterT = easeInOut(seg(t, 0.14, 0.4));
  const lockT = easeInOut(seg(t, 0.48, 0.78));
  const derivedT = seg(t, 0.82, 0.97);
  const slotY = 236;
  const slotW = (W - 60) / 5;

  // per-slot stacking counters
  const stack = {};
  return (
    <SceneFrame eyebrow="PHASE 1 · LLM" title="Turning your words into a search plan" note={`real run: ${data.real}`}>
      <div style={{ position: "relative", width: "100%", maxWidth: W, height: H, margin: "0 auto" }}>
        {QWORDS.map((wd) => {
          const s = sent[wd.i];
          const sx = 60 + rnd(wd.i) * (W - 160);
          const sy = 30 + rnd(wd.i + 40) * 150;
          let x = lerp(s.x, sx, scatterT);
          let y = lerp(s.y, sy, scatterT);
          const wobble = Math.sin(t * 22 + wd.i * 1.7) * 7 * scatterT * (1 - lockT);
          y += wobble;
          let op = 1, isKey = wd.slot >= 0, scale = 1;
          if (!isKey) op = 1 - seg(t, 0.2, 0.42);
          else {
            stack[wd.slot] = (stack[wd.slot] || 0) + 1;
            const tx = 30 + wd.slot * slotW + 12;
            const ty = slotY + 34 + (stack[wd.slot] - 1) * 30;
            x = lerp(x, tx, lockT);
            y = lerp(y, ty, lockT);
            scale = 1 + 0.12 * scatterT * (1 - lockT);
          }
          return (
            <div
              key={wd.i}
              className={isKey ? "word key" : "word"}
              style={{ transform: `translate(${x}px,${y}px) scale(${scale})`, opacity: op }}
            >
              {wd.w}
            </div>
          );
        })}
        {SLOTS.map((sl, i) => {
          const appear = easeOut(seg(t, 0.42 + i * 0.03, 0.58 + i * 0.03));
          const dOp = easeOut(seg(derivedT, i * 0.12, 0.5 + i * 0.12));
          return (
            <div
              key={sl.label}
              className="slot"
              style={{
                left: 30 + i * slotW, top: slotY, width: slotW - 14,
                opacity: appear, transform: `translateY(${lerp(16, 0, appear)}px)`,
              }}
            >
              <div className="slot-label">{sl.label}</div>
              <div style={{ height: 60 }} />
              <div className="slot-derived" style={{ opacity: dOp, transform: `translateY(${lerp(6, 0, dOp)}px)` }}>
                <Ic.check width="11" height="11" style={{ color: C.green }} /> {sl.derived}
              </div>
            </div>
          );
        })}
      </div>
    </SceneFrame>
  );
}

/* ============================================================
   SCENE 2 — TradingView screening sweep
   ============================================================ */
function ScreenScene({ t, data }) {
  const cols = 8, rows = 6, cw = 92, ch = 46;
  const W = cols * cw, H = rows * ch;
  const sweep = lerp(-0.08, 1.1, easeInOut(seg(t, 0.08, 0.9)));
  const sweepX = sweep * W;
  let passed = 0;
  TICKERS.forEach((_, i) => {
    const x = (i % cols) * cw + cw / 2;
    if (x < sweepX && PASS_SET.has(i)) passed++;
  });
  const shownMatches = Math.min(37, Math.round((passed / PASS_SET.size) * 37));
  return (
    <SceneFrame eyebrow="PHASE 2 · TRADINGVIEW" title="Sweeping 412 symbols against your criteria" note={`real run: ${data.real}`}>
      <div style={{ display: "flex", gap: 26, justifyContent: "center", alignItems: "flex-start", paddingTop: 6 }}>
        <div style={{ position: "relative", width: W, height: H, overflow: "hidden", borderRadius: 14 }}>
          {TICKERS.map((tk, i) => {
            const x = (i % cols) * cw, y = Math.floor(i / cols) * ch;
            const swept = x + cw / 2 < sweepX;
            const pass = PASS_SET.has(i);
            const cls = !swept ? "tick" : pass ? "tick pass" : "tick fail";
            return (
              <div key={tk} className={cls} style={{ left: x + 4, top: y + 4, width: cw - 8, height: ch - 8 }}>
                <span>{tk}</span>
                {swept && pass && <Ic.check width="11" height="11" style={{ color: C.blue }} />}
              </div>
            );
          })}
          <div className="sweep" style={{ transform: `translateX(${sweepX - 34}px)`, opacity: sweep > 0 && sweep < 1.02 ? 1 : 0 }}>
            <div className="sweep-lens"><Ic.lens width="15" height="15" /></div>
          </div>
        </div>
        <div style={{ width: 190, display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="mini-card">
            <div className="eyebrow">CRITERIA</div>
            {["Cap $2–10B", "Rev growth > 15%", "Avg vol > 500k", "US + Canada listed"].map((c, i) => (
              <div key={c} className="crit" style={{ opacity: easeOut(seg(t, 0.05 + i * 0.06, 0.2 + i * 0.06)) }}>
                <span className="crit-dot" /> {c}
              </div>
            ))}
          </div>
          <div className="mini-card" style={{ textAlign: "center" }}>
            <div className="big-num">{shownMatches}</div>
            <div style={{ fontSize: 13, color: C.slate }}>matches of 412 screened</div>
          </div>
        </div>
      </div>
    </SceneFrame>
  );
}

/* ============================================================
   SCENE 3 — enrichment table fills live
   ============================================================ */
function EnrichScene({ t, data }) {
  const cells = ["name", "tk", "cap", "growth", "hq"];
  const total = COMPANIES.length * cells.length;
  const filled = Math.floor(easeInOut(seg(t, 0.08, 0.92)) * total);
  return (
    <SceneFrame eyebrow="PHASE 3 · YFINANCE + FINANCEDATABASE" title="Filling in the numbers, company by company" note={`real run: ${data.real}`}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <div style={{ display: "flex", gap: 10, marginBottom: 12, justifyContent: "center" }}>
          {["yfinance", "FinanceDatabase"].map((s, i) => (
            <div key={s} className="src-chip" style={{ animationDelay: `${i * 0.6}s` }}>
              <Ic.globe width="12" height="12" /> {s}
            </div>
          ))}
        </div>
        <div className="table">
          <div className="trow thead">
            {["Company", "Ticker", "Mkt cap", "Rev growth", "HQ"].map((h) => <div key={h}>{h}</div>)}
          </div>
          {COMPANIES.map((co, r) => (
            <div key={co.tk} className="trow">
              {cells.map((cKey, cI) => {
                const idx = r * cells.length + cI;
                const on = idx < filled;
                const fresh = idx === filled - 1;
                return (
                  <div key={cKey} className={fresh ? "tcell fresh" : "tcell"} style={{ opacity: on ? 1 : 0 }}>
                    <span style={cKey === "growth" ? { color: C.green, fontWeight: 600 } : cKey === "cap" || cKey === "tk" ? { fontFamily: "'JetBrains Mono', monospace", fontSize: 13 } : {}}>
                      {co[cKey]}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </SceneFrame>
  );
}

/* ============================================================
   SCENE 4 — cleaning & shortlisting: rows drop out with reasons
   ============================================================ */
const DROPS = { 1: "duplicate", 4: "outside ICP", 6: "missing financials", 8: "below cap floor" };
const CLEAN_ROWS = [
  "Veridian Microdevices", "Veridian Microdevices ", "Northlake Photonics", "Cassia Semiconductors",
  "Halcyon Instruments", "Ridgeline Analog", "Corvid Displays", "Tanager Circuits",
  "Pico Materials", "Meridian Fab Systems",
];
function CleanScene({ t, data }) {
  const rowH = 42;
  const dropKeys = Object.keys(DROPS).map(Number);
  const dropProg = {};
  dropKeys.forEach((k, i) => { dropProg[k] = easeInOut(seg(t, 0.14 + i * 0.14, 0.32 + i * 0.14)); });
  const doneT = easeOut(seg(t, 0.82, 0.97));
  return (
    <SceneFrame eyebrow="PHASE 4 · CLEANING" title="Keeping only the companies worth your time" note={`real run: ${data.real} · warming up shortlister`}>
      <div style={{ display: "flex", gap: 30, justifyContent: "center", alignItems: "flex-start" }}>
        <div style={{ position: "relative", width: 480, height: CLEAN_ROWS.length * rowH }}>
          {CLEAN_ROWS.map((name, i) => {
            const dp = dropProg[i] ?? 0;
            let removedAbove = 0;
            dropKeys.forEach((k) => { if (k < i) removedAbove += dropProg[k]; });
            const y = i * rowH - removedAbove * rowH;
            const isDrop = i in DROPS;
            return (
              <div
                key={i}
                className={isDrop && dp > 0.05 ? "crow dropping" : "crow"}
                style={{
                  transform: `translate(${dp * 300}px, ${y}px) rotate(${dp * 4}deg)`,
                  opacity: 1 - dp,
                }}
              >
                <span className="crow-dot" style={{ background: isDrop ? C.red : C.blue }} />
                <span style={{ flex: 1 }}>{name}</span>
                {isDrop && <span className="reason" style={{ opacity: seg(t, 0.06, 0.16) }}>{DROPS[i]}</span>}
              </div>
            );
          })}
        </div>
        <div className="mini-card" style={{ width: 180, textAlign: "center", marginTop: 40 }}>
          <div className="big-num" style={{ color: C.blue }}>
            {Math.round(lerp(37, 12, easeInOut(seg(t, 0.1, 0.85))))}
          </div>
          <div style={{ fontSize: 13, color: C.slate }}>companies remaining</div>
          <div className="done-chip" style={{ opacity: doneT, transform: `scale(${lerp(0.8, 1, doneT)})` }}>
            <Ic.check width="12" height="12" /> 12 shortlisted
          </div>
        </div>
      </div>
    </SceneFrame>
  );
}

/* ============================================================
   SCENE 5 — the centerpiece: four parallel research lanes
   ============================================================ */
const SERP_QUERIES = [
  '"Veridian Microdevices" VP sales linkedin',
  "Cassia Semiconductors leadership team",
  '"Northlake Photonics" chief revenue officer',
  "Ridgeline Analog sales director site:linkedin.com",
  "Tanager Circuits go-to-market team",
  '"Meridian Fab Systems" enterprise sales',
];
const CRAWL_SITES = [
  "veridianmicro.com/team", "cassiasemi.com/about/leadership", "northlakephotonics.com/company",
  "ridgelineanalog.com/people", "tanagercircuits.com/team", "meridianfab.com/leadership",
];
const AGENT_LOG = [
  "Warming up contact finder — loading models (36s)…",
  "Verifying profile: Priya Raghunathan · VP Sales, Veridian",
  "Trying email pattern first.last@cassiasemi.com…",
  "SerpAPI: scanning 3 result pages for Northlake leadership",
  "BrightData: crawling team page — 14 profiles found",
  "Cross-referencing titles against your target roles",
  "De-duplicating 9 overlapping profiles across sources",
  "Rate limit hit on LinkedIn — backing off 8s, retrying",
  "Confidence-scoring 51 contacts so far…",
  "Final sweep: filling gaps for 4 shortlist companies",
];

function Lane({ icon: Icon, name, count, unit, children }) {
  return (
    <div className="lane">
      <div className="lane-head">
        <span className="lane-ic"><Icon width="13" height="13" /></span>
        <span style={{ flex: 1 }}>{name}</span>
        <span className="lane-count">{count} <em>{unit}</em></span>
      </div>
      <div className="lane-body">{children}</div>
    </div>
  );
}

function ParallelScene({ t, data }) {
  const contacts = Math.floor(58 * easeInOut(seg(t, 0.04, 0.965)));
  const simSec = 37 + t * 219; // this phase covers 37s..256s of the real run
  const cyc = (period, offset = 0) => Math.floor(((t * 27 + offset) / period)) ; // seconds-based cycles
  const cycT = (period, offset = 0) => ((t * 27 + offset) % period) / period;

  // LinkedIn lane: current person card
  const li = cyc(2.3) % PEOPLE.length;
  const liT = cycT(2.3);
  const person = PEOPLE[li];

  // Contact finder lane
  const cf = cyc(2.7, 1.1) % PEOPLE.length;
  const cfT = cycT(2.7, 1.1);
  const cfP = PEOPLE[cf];
  const patterns = [
    `${cfP.n.split(" ")[0][0].toLowerCase()}.${cfP.n.split(" ")[1].toLowerCase()}@…`,
    `${cfP.n.split(" ")[0].toLowerCase()}.${cfP.n.split(" ")[1][0].toLowerCase()}@…`,
    `${cfP.n.split(" ")[0].toLowerCase()}@…`,
  ];
  const lockIdx = cf % 3;

  // Serp lane
  const sq = cyc(3.0, 0.4) % SERP_QUERIES.length;
  const sqT = cycT(3.0, 0.4);

  // BrightData lane
  const bd = cyc(2.9, 2.0) % CRAWL_SITES.length;
  const bdT = cycT(2.9, 2.0);

  const logIdx = Math.min(AGENT_LOG.length - 1, Math.floor(t * AGENT_LOG.length * 1.02));

  const laneCounts = {
    li: Math.floor(31 * easeInOut(seg(t, 0.03, 0.95))),
    cf: Math.floor(24 * easeInOut(seg(t, 0.08, 0.96))),
    sp: Math.floor(112 * easeInOut(seg(t, 0.02, 0.9))),
    bd: Math.floor(46 * easeInOut(seg(t, 0.05, 0.93))),
  };

  return (
    <SceneFrame
      eyebrow="PHASE 5 · PARALLEL DEEP RESEARCH"
      title="Four researchers working at once — this is where the minutes go"
      note={`real run: ${data.real} · 91% of total`}
    >
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, maxWidth: 940, margin: "0 auto" }}>
        <Lane icon={Ic.person} name="LinkedIn verify" count={laneCounts.li} unit="verified">
          <div className="pcard" key={li}>
            <div className={liT > 0.55 ? "avatar ok" : "avatar"}>
              {liT > 0.55 ? <Ic.check width="12" height="12" /> : <Ic.person width="12" height="12" />}
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="pname">{person.n}</div>
              <div className="prole">{person.r}</div>
              <div className="pco">{person.co}</div>
            </div>
          </div>
          <div className="lane-sub">{liT > 0.55 ? "profile confirmed" : "matching name + title…"}</div>
        </Lane>

        <Lane icon={Ic.mail} name="Contact finder" count={laneCounts.cf} unit="emails">
          <div className="pname" style={{ marginBottom: 6 }}>{cfP.n.split(" ")[0]} {cfP.n.split(" ")[1]}</div>
          {patterns.map((p, i) => {
            const on = cfT > 0.2 + i * 0.18;
            const locked = cfT > 0.78 && i === lockIdx;
            return (
              <div key={i} className={locked ? "pat locked" : "pat"} style={{ opacity: on ? (cfT > 0.78 && i !== lockIdx ? 0.28 : 1) : 0 }}>
                {p} {locked && <Ic.check width="10" height="10" />}
              </div>
            );
          })}
          <div className="lane-sub">{cfT > 0.78 ? "pattern verified" : "testing patterns…"}</div>
        </Lane>

        <Lane icon={Ic.lens} name="SerpAPI search" count={laneCounts.sp} unit="results">
          <div className="serp-q" key={sq}>{SERP_QUERIES[sq]}</div>
          {[0, 1, 2].map((i) => (
            <div key={i} className="serp-r" style={{ opacity: sqT > 0.3 + i * 0.18 ? 1 : 0, width: `${86 - i * 14}%` }}>
              <span className="serp-fav" />
              <span className="serp-line" />
            </div>
          ))}
          <div className="lane-sub">reading page {1 + (sq % 3)} of 3</div>
        </Lane>

        <Lane icon={Ic.crawl} name="BrightData crawl" count={laneCounts.bd} unit="pages">
          <div className="crawl-url" key={bd}>{CRAWL_SITES[bd]}</div>
          <div className="crawl-frame">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="crawl-line" style={{ width: `${88 - i * 16}%`, opacity: bdT > 0.15 + i * 0.16 ? 1 : 0.15 }} />
            ))}
            <div className="crawl-scan" style={{ transform: `translateY(${bdT * 44}px)` }} />
          </div>
          <div className="lane-sub">{bdT > 0.8 ? `extracted ${2 + (bd % 3)} contacts` : "parsing markup…"}</div>
        </Lane>
      </div>

      <div className="hive" style={{ maxWidth: 940 }}>
        <div className="jar">
          <div className="jar-count">
            <span className="big-num" style={{ color: C.amber, fontSize: 40 }}>{contacts}</span>
            <span style={{ fontSize: 13, color: C.slate }}>/ 58 contacts collected</span>
          </div>
          <div className="jar-dots">
            {Array.from({ length: 58 }).map((_, i) => (
              <span key={i} className={i < contacts ? "cdot on" : "cdot"} style={{ transitionDelay: `${(i % 6) * 40}ms` }} />
            ))}
          </div>
        </div>
        <div className="log">
          <div className="eyebrow" style={{ marginBottom: 6 }}>AGENT LOG · {fmtClock(simSec)} elapsed</div>
          <div className="log-line" key={logIdx}>{AGENT_LOG[logIdx]}</div>
          <div className="log-prev">{logIdx > 0 ? AGENT_LOG[logIdx - 1] : "Lanes started in parallel"}</div>
        </div>
      </div>
    </SceneFrame>
  );
}

/* ============================================================
   SCENE 6 — pieces assemble into the report
   ============================================================ */
function ExportScene({ t, data }) {
  const converge = easeInOut(seg(t, 0.05, 0.55));
  const docT = easeOut(seg(t, 0.45, 0.7));
  const chipT = easeOut(seg(t, 0.72, 0.92));
  const frags = [
    { label: "58 contacts", ic: Ic.person, x0: -260, y0: -70, r0: -9 },
    { label: "12 companies", ic: Ic.grid, x0: 250, y0: -110, r0: 8 },
    { label: "Market notes", ic: Ic.doc, x0: -210, y0: 130, r0: 6 },
    { label: "Source links", ic: Ic.globe, x0: 240, y0: 120, r0: -7 },
  ];
  return (
    <SceneFrame eyebrow="PHASE 6 · EXPORT" title="Stapling it all into one report" note={`real run: ${data.real}`}>
      <div style={{ position: "relative", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div className="report" style={{ transform: `scale(${lerp(0.85, 1, docT)})`, opacity: lerp(0.35, 1, docT) }}>
          <div className="report-ribbon" style={{ transform: `scaleX(${docT})` }} />
          <div style={{ fontWeight: 700, fontSize: 17, letterSpacing: "-0.01em" }}>GTM Prospect Report</div>
          <div style={{ fontSize: 12.5, color: C.slate, marginTop: 4 }}>Mid-cap semiconductors · North America</div>
          <div className="report-lines">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} style={{ width: `${92 - i * 12}%`, opacity: seg(docT, 0.3 + i * 0.15, 0.6 + i * 0.15) }} />
            ))}
          </div>
        </div>
        {frags.map((f, i) => {
          const p = clamp01(converge * 1.1 - i * 0.04);
          const e = easeInOut(p);
          return (
            <div
              key={f.label}
              className="frag"
              style={{
                transform: `translate(${lerp(f.x0, 0, e)}px, ${lerp(f.y0, 10, e)}px) rotate(${lerp(f.r0, 0, e)}deg) scale(${lerp(1, 0.4, seg(e, 0.75, 1))})`,
                opacity: 1 - seg(e, 0.8, 1),
              }}
            >
              <f.ic width="13" height="13" style={{ color: C.blue }} /> {f.label}
            </div>
          );
        })}
        <div className="file-chip" style={{ opacity: chipT, transform: `translateY(${lerp(14, 0, chipT)}px)` }}>
          <Ic.check width="13" height="13" style={{ color: C.green }} /> gtm_prospects_aug04.xlsx · ready
        </div>
      </div>
    </SceneFrame>
  );
}

/* ============================================================
   SUMMARY CARD
   ============================================================ */
function Summary({ onReplay }) {
  const stats = [
    { v: "58", l: "LinkedIn contacts" },
    { v: "12", l: "target companies" },
    { v: "4", l: "data sources" },
    { v: "4:16", l: "total runtime" },
  ];
  return (
    <div className="scene-enter" style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div className="summary">
        <div className="agent-dot" style={{ margin: "0 auto 14px" }}><Ic.check width="16" height="16" /></div>
        <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em" }}>Run complete</div>
        <div style={{ fontSize: 14.5, color: C.slate, marginTop: 6 }}>
          Verified contact list and market notes are in your report.
        </div>
        <div className="stat-row">
          {stats.map((s, i) => (
            <div key={s.l} className="stat" style={{ animationDelay: `${0.15 + i * 0.12}s` }}>
              <div className="stat-v">{s.v}</div>
              <div className="stat-l">{s.l}</div>
            </div>
          ))}
        </div>
        <button className="replay" onClick={onReplay}>
          <Ic.spark width="13" height="13" /> Watch the run again
        </button>
      </div>
    </div>
  );
}

/* ============================================================
   STATUS TRAIL — the route the agent walks (bottom)
   ============================================================ */
function Trail({ ms }) {
  const overall = clamp01(ms / TOTAL);
  let acc = 0;
  const stops = SCRIPT.map((s, i) => {
    const start = acc; acc += s.dur;
    return { ...s, frac: (start + s.dur / 2) / TOTAL, startFrac: start / TOTAL, i };
  });
  const active = stops.findIndex((s) => ms < s.startFrac * TOTAL + s.dur) === -1
    ? SCRIPT.length - 1
    : stops.filter((s) => ms >= s.startFrac * TOTAL).length - 1;
  const finishedAll = ms >= TOTAL;
  const W = 900, y = 26;
  const px = 40 + overall * (W - 80);
  return (
    <div className="trail-wrap">
      <svg width="100%" viewBox={`0 0 ${W} 64`} style={{ maxWidth: W, display: "block", margin: "0 auto", overflow: "visible" }}>
        <line x1="40" y1={y} x2={W - 40} y2={y} stroke={C.line} strokeWidth="2" strokeDasharray="1 7" strokeLinecap="round" />
        <line x1="40" y1={y} x2={px} y2={y} stroke={C.blue} strokeWidth="2" strokeDasharray="1 7" strokeLinecap="round" />
        {stops.map((s, i) => {
          const cx = 40 + s.frac * (W - 80);
          const Icon = PHASE_ICONS[i];
          const done = overall >= s.startFrac + s.dur / TOTAL;
          const cur = i === active && ms < TOTAL;
          return (
            <g key={s.id} transform={`translate(${cx},${y})`}>
              <circle r={cur ? 13 : 10} fill={done || cur ? C.blue : C.card} stroke={done || cur ? C.blue : C.line} strokeWidth="1.6" />
              <g transform="translate(-7,-7)" style={{ color: done || cur ? "#fff" : C.slate }}>
                <Icon width="14" height="14" />
              </g>
              {cur && <circle r="17" fill="none" stroke={C.blue} strokeWidth="1.4" opacity="0.4" className="ring" />}
              {(cur || (finishedAll && i === SCRIPT.length - 1)) && (
                <text y="34" textAnchor="middle" fontSize="11" fill={C.ink} fontWeight="700">
                  {s.name}
                </text>
              )}
            </g>
          );
        })}
        <g transform={`translate(${px}, ${y - 20})`} style={{ color: C.blue, transition: "none" }}>
          <Ic.plane width="18" height="18" />
        </g>
      </svg>
    </div>
  );
}

/* ============================================================
   APP — master clock + scene router
   ============================================================ */
export function AgentRunVisualizerDemo() {
  const [ms, setMs] = useState(0);
  const rafRef = useRef(null);

  useEffect(() => {
    let last = performance.now();
    const loop = (now) => {
      const dt = Math.min(64, now - last);
      last = now;
      setMs((m) => (m >= TOTAL ? m : Math.min(TOTAL, m + dt)));
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // resolve scene + local t
  let acc = 0, sceneIdx = SCRIPT.length - 1, localT = 1;
  for (let i = 0; i < SCRIPT.length; i++) {
    if (ms < acc + SCRIPT[i].dur) { sceneIdx = i; localT = (ms - acc) / SCRIPT[i].dur; break; }
    acc += SCRIPT[i].dur;
  }
  const finished = ms >= TOTAL;
  const scene = SCRIPT[sceneIdx];
  const simSec = (ms / TOTAL) * REAL_TOTAL_S;

  const SCENES = {
    intro: (p) => <IntroScene {...p} data={{ query: QUERY }} />,
    query: (p) => <QueryScene {...p} data={scene} />,
    screen: (p) => <ScreenScene {...p} data={scene} />,
    enrich: (p) => <EnrichScene {...p} data={scene} />,
    clean: (p) => <CleanScene {...p} data={scene} />,
    parallel: (p) => <ParallelScene {...p} data={scene} />,
    export: (p) => <ExportScene {...p} data={scene} />,
  };

  return (
    <div className="root">
      <style>{CSS}</style>
      <div className="frame">
        <header className="top">
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <div className="agent-dot sm"><Ic.spark width="13" height="13" /></div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>Prospect Scout</div>
              <div style={{ fontSize: 12, color: C.slate }}>LinkedIn contact finder · market research agent</div>
            </div>
          </div>
          <div className="clock">
            <span className="pulse-dot" style={{ opacity: finished ? 0 : 1 }} />
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>
              {finished ? "4:16" : fmtClock(simSec)} <em style={{ color: C.slate, fontStyle: "normal" }}>/ 4:16 run</em>
            </span>
          </div>
        </header>

        <main className="stage" key={finished ? "done" : sceneIdx}>
          {finished ? <Summary onReplay={() => setMs(0)} /> : SCENES[scene.id]({ t: localT })}
        </main>

        <Trail ms={ms} />
      </div>
    </div>
  );
}

const LIVE_PHASE_ICONS = {
  query_formulator: Ic.spark,
  screener_fetch: Ic.lens,
  yfinance_enricher: Ic.grid,
  cleaner: Ic.funnel,
  linkedin_verifier: Ic.net,
  excel_exporter_node: Ic.doc,
};

const formatDuration = (value) => {
  if (value == null || Number.isNaN(value)) return '?';
  if (value < 1000) return `${Math.round(value)}ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};

const liveDuration = (startedAt, endedAt, now) => {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : now;
  return Math.max(0, end - start);
};

function ConnectionBadge({ status }) {
  return (
    <span className={`live-connection ${status}`}>
      <span className="pulse-dot" />
      {status}
    </span>
  );
}

function PhaseTimeline({ phases, now }) {
  return (
    <div className="live-phases">
      {phases.map((phase, index) => {
        const Icon = LIVE_PHASE_ICONS[phase.id] || Ic.spark;
        const elapsed = phase.durationMs ?? liveDuration(phase.startedAt, phase.endedAt, now);
        return (
          <div className={`live-phase ${phase.status}`} key={phase.id}>
            <div className="live-phase-rail">
              <span className="live-phase-icon"><Icon width="14" height="14" /></span>
              {index < phases.length - 1 && <span className="live-phase-line" />}
            </div>
            <div className="live-phase-copy">
              <span>{phase.label}</span>
              <em>{phase.status === 'pending' ? 'waiting' : formatDuration(elapsed)}</em>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CompanyLane({ lane, now, onInspect }) {
  const elapsed = lane.durationMs ?? liveDuration(lane.startedAt, lane.endedAt, now);
  const activeTools = Object.values(lane.activeTools || {});
  const recentNodes = (lane.nodes || []).slice(-4);

  return (
    <article className={`live-lane ${lane.status}`}>
      <header className="live-lane-head">
        <div>
          <span className="live-lane-kicker">{lane.currentBranch?.replaceAll('_', ' ') || 'company research'}</span>
          <h3>{lane.name}</h3>
        </div>
        <span className="live-lane-time">{formatDuration(elapsed)}</span>
      </header>

      <div className="live-node-focus">
        <span className={`live-node-orb ${lane.status}`}><Ic.spark width="13" height="13" /></span>
        <div>
          <strong>{lane.currentNode || (lane.status === 'done' ? 'Complete' : 'Waiting for node event')}</strong>
          <span>{lane.lastMessage || 'Sub-agent initialized'}</span>
        </div>
      </div>

      <div className="live-metrics">
        <span><strong>{lane.snapshotCount ?? lane.contacts?.length ?? 0}</strong> contacts</span>
        <span><strong>{lane.toolCount || 0}</strong> tools</span>
        <span><strong>{lane.llmCount || 0}</strong> LLM calls</span>
      </div>

      <div className="live-node-history">
        {recentNodes.length ? recentNodes.map((node) => (
          <div className={`live-node-row ${node.status}`} key={node.id}>
            <span>{node.name}</span>
            <em>{formatDuration(node.durationMs ?? liveDuration(node.startedAt, node.endedAt, now))}</em>
          </div>
        )) : <div className="live-empty-row">Awaiting correlated node events?</div>}
      </div>

      {activeTools.length > 0 && (
        <div className="live-tool-row">
          <span className="pulse-dot" /> {activeTools.join(', ')}
        </div>
      )}

      {lane.error && <div className="live-error">{lane.error}</div>}

      <button className="live-inspect" onClick={() => onInspect(lane.events?.at(-1))} disabled={!lane.events?.length}>
        Inspect latest event
      </button>
    </article>
  );
}

function EventDrawer({ events, selected, onSelect, onClose }) {
  return (
    <aside className="live-drawer" aria-label="Structured event inspector">
      <header>
        <div>
          <span>Sanitized telemetry</span>
          <strong>Event inspector</strong>
        </div>
        <button onClick={onClose} aria-label="Close event inspector">?</button>
      </header>
      <div className="live-drawer-body">
        <div className="live-event-list">
          {events.slice(-80).reverse().map((event) => (
            <button className={selected?.id === event.id ? 'selected' : ''} key={event.id} onClick={() => onSelect(event)}>
              <span>{event.eventType}</span>
              <em>{event.company || event.agent || 'pipeline'}</em>
            </button>
          ))}
        </div>
        <pre>{selected ? JSON.stringify(selected, null, 2) : 'Select an event to inspect its redacted payload.'}</pre>
      </div>
    </aside>
  );
}

export default function AgentRunVisualizer({ telemetry }) {
  const [now, setNow] = useState(Date.now());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const state = telemetry || { connection: 'connecting', run: null, phases: [], companies: {}, events: [] };
  const integrity = state.telemetryIntegrity || state.run?.telemetryIntegrity || null;
  const lanes = Object.values(state.companies || {}).sort((a, b) => {
    if (a.status === 'running' && b.status !== 'running') return -1;
    if (b.status === 'running' && a.status !== 'running') return 1;
    return (a.startedAt || '').localeCompare(b.startedAt || '');
  });
  const runElapsed = state.run ? liveDuration(state.run.startedAt, state.run.endedAt, now) : null;

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);

  const inspect = (event) => {
    if (!event) return;
    setSelectedEvent(event);
    setDrawerOpen(true);
  };

  return (
    <div className="root live-root">
      <style>{CSS + LIVE_CSS}</style>
      <div className="frame live-frame">
        <header className="top">
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <div className="agent-dot sm"><Ic.spark width="13" height="13" /></div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>Shortlister Agent</div>
              <div style={{ fontSize: 12, color: C.slate }}>Live graph + synchronized LinkedIn sub-agents</div>
            </div>
          </div>
          <div className="live-top-actions">
            <ConnectionBadge status={state.connection} />
            <span className="clock">{formatDuration(runElapsed)} <em>{state.run?.status || 'idle'}</em></span>
            <button className="live-events-button" onClick={() => setDrawerOpen(true)}>{state.events?.length || 0} events</button>
          </div>
        </header>

        {!state.run ? (
          <main className="live-idle">
            <div className="agent-dot"><Ic.spark width="16" height="16" /></div>
            <h2>Waiting for a Shortlister run</h2>
            <p>Start the agent from the Pipeline tab. Live JSONL events will appear here as nodes switch.</p>
          </main>
        ) : (
          <main className="live-stage">
            <section className="live-overview">
              <div>
                <span className="live-eyebrow">RUN {state.run.id}</span>
                <h2>{state.run.status === 'running' ? 'Agent execution in progress' : state.run.status === 'done' ? 'Run complete' : 'Run stopped with an error'}</h2>
                <p>{state.run.query || 'Waiting for pipeline_start query metadata?'}</p>
              </div>
              <div className={`live-run-status ${state.run.status}`}>
                <span className="pulse-dot" /> {state.run.status}
              </div>
            </section>

            <PhaseTimeline phases={state.phases || []} now={now} />

            <section className="live-company-section">
              <div className="live-section-title">
                <div>
                  <span className="live-eyebrow">PARALLEL LINKEDIN RESEARCH</span>
                  <h2>{lanes.length ? `${lanes.length} company sub-agents tracked` : 'Company lanes will appear during phase 5'}</h2>
                </div>
                <span>{lanes.filter((lane) => lane.status === 'running').length} active</span>
              </div>
              {lanes.length > 0 && (
                <div className="live-lanes">
                  {lanes.map((lane) => <CompanyLane key={lane.name} lane={lane} now={now} onInspect={inspect} />)}
                </div>
              )}
            </section>

            {integrity && !integrity.isValid && (
              <div className="live-sync-warning" role="alert">
                <strong>Pipeline completed with telemetry synchronization gaps</strong>
                <span>{integrity.mismatches.join(' · ')}</span>
              </div>
            )}

            {state.run.error && <div className="live-run-error">{state.run.error}</div>}
          </main>
        )}
      </div>

      {drawerOpen && (
        <EventDrawer
          events={state.events || []}
          selected={selectedEvent}
          onSelect={setSelectedEvent}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </div>
  );
}

/* ============================================================
   STYLES
   ============================================================ */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

.root {
  min-height: 100dvh; background: ${C.paper}; color: ${C.ink};
  font-family: 'Outfit', system-ui, sans-serif;
  display: flex; align-items: center; justify-content: center; padding: 18px 12px;
}
.root * { box-sizing: border-box; }
.frame { width: 100%; max-width: 1020px; display: flex; flex-direction: column; gap: 8px; }

.top { display: flex; justify-content: space-between; align-items: center; padding: 2px 6px 8px; }
.clock { display: flex; align-items: center; gap: 8px; background: ${C.card}; border: 1px solid ${C.line};
  padding: 7px 13px; border-radius: 99px; }

.agent-dot { width: 34px; height: 34px; border-radius: 12px; background: ${C.blue}; color: #fff;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  box-shadow: 0 6px 14px -6px rgba(20,103,179,.55); }
.agent-dot.sm { width: 30px; height: 30px; border-radius: 10px; }

.pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: ${C.blue}; display: inline-block;
  animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: .45; } }

.stage { background: ${C.card}; border: 1px solid ${C.line}; border-radius: 22px;
  height: 520px; padding: 20px 24px; overflow: hidden; position: relative;
  box-shadow: 0 24px 50px -30px rgba(37,49,61,.18); }

.scene-enter { animation: sceneIn .55s cubic-bezier(.16,1,.3,1); }
@keyframes sceneIn { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }

.eyebrow { font-size: 11px; letter-spacing: .14em; font-weight: 700; color: ${C.blue}; }
.scene-title { font-size: 20px; font-weight: 700; letter-spacing: -0.015em; margin-top: 2px; }
.scene-note { margin-left: auto; font-size: 12px; color: ${C.slate}; background: ${C.paper};
  border: 1px solid ${C.line}; padding: 4px 10px; border-radius: 99px; white-space: nowrap; }

/* scene 1 */
.word { position: absolute; left: 0; top: 0; padding: 5px 11px; border-radius: 9px; font-size: 15px;
  background: ${C.paper}; border: 1px solid ${C.line}; color: ${C.slate}; white-space: nowrap;
  will-change: transform, opacity; }
.word.key { background: ${C.blueSoft}; border-color: rgba(20,103,179,.35); color: ${C.blue}; font-weight: 600; z-index: 2; }
.slot { position: absolute; border: 1.5px dashed rgba(20,103,179,.4); border-radius: 14px; padding: 10px 12px;
  background: rgba(228,238,247,.35); }
.slot-label { font-size: 10px; letter-spacing: .13em; font-weight: 700; color: ${C.slate}; }
.slot-derived { font-size: 12px; font-weight: 600; color: ${C.ink}; display: flex; align-items: center; gap: 5px;
  margin-top: 6px; }

/* scene 2 */
.tick { position: absolute; border-radius: 9px; border: 1px solid ${C.line}; background: ${C.paper};
  display: flex; align-items: center; justify-content: center; gap: 5px;
  font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: ${C.ink};
  transition: all .35s cubic-bezier(.16,1,.3,1); }
.tick.pass { background: ${C.blueSoft}; border-color: rgba(20,103,179,.45); color: ${C.blue}; font-weight: 600;
  transform: scale(1.04); }
.tick.fail { opacity: .28; transform: scale(.96); }
.sweep { position: absolute; top: 0; bottom: 0; width: 68px; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(20,103,179,.14), transparent); }
.sweep-lens { position: absolute; top: -4px; left: 50%; transform: translateX(-50%); width: 30px; height: 30px;
  border-radius: 50%; background: ${C.blue}; color: #fff; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 14px -5px rgba(20,103,179,.6); }
.mini-card { background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 14px; padding: 13px 15px; }
.crit { display: flex; align-items: center; gap: 8px; font-size: 13px; margin-top: 8px; color: ${C.ink}; }
.crit-dot { width: 6px; height: 6px; border-radius: 50%; background: ${C.blue}; flex-shrink: 0; }
.big-num { font-family: 'JetBrains Mono', monospace; font-size: 34px; font-weight: 600; line-height: 1.1; }

/* scene 3 */
.src-chip { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; color: ${C.blue};
  background: ${C.blueSoft}; border: 1px solid rgba(20,103,179,.3); padding: 5px 12px; border-radius: 99px;
  animation: bob 2.4s ease-in-out infinite; }
@keyframes bob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
.table { border: 1px solid ${C.line}; border-radius: 14px; overflow: hidden; }
.trow { display: grid; grid-template-columns: 2.1fr .8fr 1fr 1.1fr 1.2fr; }
.trow + .trow { border-top: 1px solid ${C.line}; }
.thead { background: ${C.paper}; font-size: 11px; letter-spacing: .08em; font-weight: 700; color: ${C.slate};
  text-transform: uppercase; }
.thead > div { padding: 9px 14px; }
.tcell { padding: 10px 14px; font-size: 14px; transition: opacity .3s; }
.tcell.fresh span { animation: cellIn .4s cubic-bezier(.16,1,.3,1); display: inline-block; }
@keyframes cellIn { from { transform: translateY(7px); opacity: 0; } to { transform: none; opacity: 1; } }

/* scene 4 */
.crow { position: absolute; left: 0; width: 100%; display: flex; align-items: center; gap: 10px;
  background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 11px; padding: 8px 14px;
  font-size: 14.5px; will-change: transform, opacity; transition: transform .12s linear; }
.crow-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.reason { font-size: 11px; font-weight: 700; letter-spacing: .05em; color: ${C.red}; background: #F7E8E2;
  padding: 3px 9px; border-radius: 99px; text-transform: uppercase; }
.done-chip { margin-top: 12px; display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700;
  color: ${C.green}; background: #E6F1EA; padding: 6px 13px; border-radius: 99px; }

/* scene 5 */
.lane { background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 15px; padding: 11px 12px;
  min-height: 168px; display: flex; flex-direction: column; }
.lane-head { display: flex; align-items: center; gap: 7px; font-size: 12.5px; font-weight: 700; margin-bottom: 9px; }
.lane-ic { width: 24px; height: 24px; border-radius: 8px; background: ${C.blueSoft}; color: ${C.blue};
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.lane-count { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: ${C.blue}; }
.lane-count em { font-style: normal; font-size: 10px; color: ${C.slate}; }
.lane-body { flex: 1; }
.lane-sub { font-size: 11px; color: ${C.slate}; margin-top: 8px; }
.pcard { display: flex; gap: 9px; align-items: flex-start; background: ${C.card}; border: 1px solid ${C.line};
  border-radius: 11px; padding: 8px 10px; animation: sceneIn .4s cubic-bezier(.16,1,.3,1); }
.avatar { width: 26px; height: 26px; border-radius: 50%; background: ${C.line}; color: ${C.slate};
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: all .3s; }
.avatar.ok { background: ${C.blue}; color: #fff; }
.pname { font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prole { font-size: 11.5px; color: ${C.ink}; }
.pco { font-size: 10.5px; color: ${C.slate}; }
.pat { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; padding: 4px 8px; border-radius: 7px;
  background: ${C.card}; border: 1px solid ${C.line}; margin-top: 5px; display: flex; align-items: center; gap: 5px;
  transition: opacity .25s; }
.pat.locked { border-color: rgba(46,125,91,.5); color: ${C.green}; font-weight: 600; }
.serp-q { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: ${C.ink}; background: ${C.card};
  border: 1px solid ${C.line}; border-radius: 8px; padding: 6px 8px; margin-bottom: 8px;
  animation: sceneIn .35s ease; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.serp-r { display: flex; align-items: center; gap: 6px; margin-top: 6px; transition: opacity .3s; }
.serp-fav { width: 10px; height: 10px; border-radius: 3px; background: ${C.blue}; opacity: .55; flex-shrink: 0; }
.serp-line { height: 7px; flex: 1; border-radius: 4px; background: ${C.line}; }
.crawl-url { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: ${C.blue}; margin-bottom: 7px;
  animation: sceneIn .35s ease; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.crawl-frame { position: relative; background: ${C.card}; border: 1px solid ${C.line}; border-radius: 9px;
  padding: 9px 10px 11px; overflow: hidden; }
.crawl-line { height: 7px; border-radius: 4px; background: ${C.line}; margin-top: 6px; transition: opacity .3s; }
.crawl-line:first-child { margin-top: 0; }
.crawl-scan { position: absolute; left: 0; right: 0; top: 4px; height: 12px;
  background: linear-gradient(180deg, rgba(20,103,179,.16), transparent); }
.hive { margin: 14px auto 0; display: grid; grid-template-columns: 1.1fr 1fr; gap: 12px; }
.jar { background: ${C.amberSoft}; border: 1px solid rgba(188,127,38,.3); border-radius: 15px; padding: 12px 16px; }
.jar-count { display: flex; align-items: baseline; gap: 9px; }
.jar-dots { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.cdot { width: 9px; height: 9px; border-radius: 50%; background: rgba(188,127,38,.18);
  transition: all .4s cubic-bezier(.34,1.56,.64,1); transform: scale(.6); }
.cdot.on { background: ${C.amber}; transform: scale(1); }
.log { background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 15px; padding: 12px 16px; }
.log-line { font-size: 13.5px; font-weight: 600; animation: sceneIn .4s ease; }
.log-prev { font-size: 12px; color: ${C.slate}; margin-top: 5px; opacity: .8; }

/* scene 6 */
.report { width: 300px; background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 16px;
  padding: 22px 22px 26px; box-shadow: 0 20px 44px -24px rgba(37,49,61,.3); position: relative; overflow: hidden; }
.report-ribbon { position: absolute; top: 0; left: 0; right: 0; height: 6px; background: ${C.blue};
  transform-origin: left; }
.report-lines { margin-top: 16px; }
.report-lines > div { height: 8px; border-radius: 4px; background: ${C.line}; margin-top: 8px; transition: opacity .3s; }
.frag { position: absolute; display: flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 600;
  background: ${C.card}; border: 1px solid ${C.line}; border-radius: 11px; padding: 8px 13px;
  box-shadow: 0 10px 22px -12px rgba(37,49,61,.28); will-change: transform, opacity; }
.file-chip { position: absolute; bottom: 26px; display: flex; align-items: center; gap: 7px; font-size: 13.5px;
  font-weight: 700; background: ${C.card}; border: 1px solid ${C.line}; border-radius: 99px; padding: 9px 17px;
  box-shadow: 0 12px 26px -14px rgba(37,49,61,.3); }

/* summary */
.summary { text-align: center; max-width: 460px; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 24px 0 26px; }
.stat { background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 14px; padding: 14px 8px;
  animation: sceneIn .5s cubic-bezier(.16,1,.3,1) both; }
.stat-v { font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 600; color: ${C.blue}; }
.stat-l { font-size: 11.5px; color: ${C.slate}; margin-top: 3px; }
.replay { display: inline-flex; align-items: center; gap: 8px; font-family: inherit; font-size: 14px; font-weight: 700;
  color: #fff; background: ${C.blue}; border: none; border-radius: 99px; padding: 11px 22px; cursor: pointer;
  transition: transform .15s, box-shadow .15s; box-shadow: 0 10px 22px -10px rgba(20,103,179,.6); }
.replay:hover { transform: translateY(-1px); }
.replay:active { transform: scale(.97); }

/* trail */
.trail-wrap { padding: 10px 6px 2px; }
.ring { animation: ringPulse 1.8s ease-out infinite; transform-origin: center; }
@keyframes ringPulse { 0% { transform: scale(.7); opacity: .5; } 100% { transform: scale(1.35); opacity: 0; } }

@media (max-width: 860px) {
  .stage { height: auto; min-height: 560px; padding: 16px; }
  .hive, .stat-row { grid-template-columns: 1fr 1fr; }
  .trail-wrap text { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .pulse-dot, .src-chip, .ring, .scene-enter, .stat, .pcard, .serp-q, .crawl-url, .log-line { animation: none !important; }
}
`;

const LIVE_CSS = `
.live-root { min-height: 640px; }
.live-frame { min-height: 640px; overflow: hidden; border-radius: 22px !important; }
.live-root .agent-dot, .live-root .pulse-dot, .live-connection, .live-run-status, .live-events-button, .live-inspect,
.live-phase, .live-phase-icon, .live-lane, .live-node-focus, .live-node-orb, .live-metrics span, .live-error,
.live-run-error, .live-drawer, .live-event-list button { border-radius: 10px !important; }
.live-root .agent-dot, .live-root .pulse-dot { border-radius: 50% !important; }
.live-top-actions { display: flex; align-items: center; gap: 10px; }
.live-connection, .live-run-status { display: inline-flex; align-items: center; gap: 7px; text-transform: capitalize; font-size: 11px; font-weight: 700; color: ${C.slate}; }
.live-connection.connected .pulse-dot, .live-run-status.running .pulse-dot { background: ${C.green}; }
.live-connection.reconnecting .pulse-dot { background: ${C.amber}; }
.clock em { color: ${C.slate}; font-style: normal; margin-left: 4px; text-transform: capitalize; }
.live-events-button, .live-inspect { border: 1px solid ${C.line}; background: ${C.card}; color: ${C.ink}; border-radius: 9px; padding: 7px 10px; font: 600 11px inherit; cursor: pointer; }
.live-events-button:hover, .live-inspect:hover { border-color: ${C.blue}; color: ${C.blue}; }
.live-idle { min-height: 520px; display: grid; place-content: center; justify-items: center; text-align: center; padding: 30px; }
.live-idle h2 { margin: 16px 0 6px; font-size: 22px; }
.live-idle p { max-width: 470px; color: ${C.slate}; line-height: 1.6; }
.live-stage { padding: 24px; background: ${C.paper}; min-height: 560px; }
.live-overview, .live-section-title { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.live-overview h2, .live-section-title h2 { margin: 5px 0 7px; font-size: 20px; letter-spacing: -.02em; }
.live-overview p { margin: 0; color: ${C.slate}; max-width: 820px; line-height: 1.5; white-space: pre-line; }
.live-eyebrow, .live-lane-kicker { font-size: 10px; letter-spacing: .11em; text-transform: uppercase; color: ${C.blue}; font-weight: 800; }
.live-phases { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; margin: 22px 0; }
.live-phase { position: relative; min-width: 0; background: ${C.card}; border: 1px solid ${C.line}; border-radius: 13px; padding: 12px; display: flex; gap: 9px; transition: .2s ease; }
.live-phase.running { border-color: ${C.blue}; box-shadow: 0 10px 24px -18px rgba(20,103,179,.8); }
.live-phase.done { background: ${C.blueSoft}; border-color: rgba(20,103,179,.3); }
.live-phase-rail { display: flex; flex-direction: column; align-items: center; }
.live-phase-icon { width: 26px; height: 26px; border-radius: 9px; display: grid; place-items: center; background: ${C.paper}; color: ${C.slate}; }
.live-phase.running .live-phase-icon, .live-phase.done .live-phase-icon { background: ${C.blue}; color: white; }
.live-phase-copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.live-phase-copy span { font-size: 11.5px; font-weight: 700; line-height: 1.25; }
.live-phase-copy em { font-size: 10.5px; color: ${C.slate}; font-style: normal; }
.live-company-section { border-top: 1px solid ${C.line}; padding-top: 20px; }
.live-section-title > span { font: 700 11px 'JetBrains Mono', monospace; color: ${C.slate}; }
.live-lanes { display: grid; grid-template-columns: repeat(auto-fit, minmax(255px, 1fr)); gap: 12px; margin-top: 14px; align-items: start; }
.live-lane { background: ${C.card}; border: 1px solid ${C.line}; border-radius: 15px; padding: 14px; box-shadow: 0 14px 30px -25px rgba(37,49,61,.45); }
.live-lane.running { border-color: rgba(20,103,179,.35); }
.live-lane.done { border-color: rgba(46,125,91,.35); }
.live-lane.error { border-color: ${C.red}; }
.live-lane-head { display: flex; justify-content: space-between; gap: 10px; }
.live-lane-head h3 { margin: 3px 0 0; font-size: 14px; line-height: 1.25; }
.live-lane-time { font: 700 11px 'JetBrains Mono', monospace; color: ${C.slate}; white-space: nowrap; }
.live-node-focus { display: flex; gap: 10px; align-items: center; background: ${C.paper}; border: 1px solid ${C.line}; border-radius: 12px; padding: 10px; margin: 13px 0 10px; }
.live-node-focus > div { min-width: 0; }
.live-node-focus strong, .live-node-focus span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.live-node-focus strong { font-size: 12.5px; }
.live-node-focus span { font-size: 10.5px; color: ${C.slate}; margin-top: 3px; }
.live-node-orb { width: 28px; height: 28px; border-radius: 9px; background: ${C.blue}; color: white; display: grid; place-items: center; flex: none; }
.live-node-orb.done { background: ${C.green}; }
.live-node-orb.error { background: ${C.red}; }
.live-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.live-metrics span { text-align: center; border: 1px solid ${C.line}; border-radius: 9px; padding: 7px 3px; color: ${C.slate}; font-size: 9.5px; }
.live-metrics strong { display: block; color: ${C.ink}; font: 700 14px 'JetBrains Mono', monospace; }
.live-node-history { margin: 10px 0; }
.live-node-row, .live-empty-row { display: flex; justify-content: space-between; gap: 8px; padding: 5px 2px; border-bottom: 1px dashed ${C.line}; font-size: 10.5px; }
.live-node-row em { color: ${C.slate}; font-style: normal; font-family: 'JetBrains Mono', monospace; }
.live-node-row.running span { color: ${C.blue}; font-weight: 700; }
.live-empty-row { color: ${C.slate}; }
.live-tool-row { color: ${C.blue}; font-size: 10.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.live-error, .live-run-error { color: ${C.red}; background: rgba(179,84,60,.08); border: 1px solid rgba(179,84,60,.3); border-radius: 9px; padding: 8px; font-size: 10.5px; margin-top: 8px; }
.live-sync-warning { color: #8a4b08; background: #fff7e8; border: 1px solid #e8bd72; border-radius: 11px; padding: 11px 13px; margin-top: 14px; display: grid; gap: 4px; font-size: 11px; }
.live-sync-warning strong { font-size: 12px; }
.live-inspect { width: 100%; margin-top: 10px; }
.live-inspect:disabled { opacity: .45; cursor: default; }
.live-drawer { position: fixed; z-index: 100; inset: 18px 18px 18px auto; width: min(720px, calc(100vw - 36px)); background: ${C.card}; border: 1px solid ${C.line}; border-radius: 16px; box-shadow: 0 30px 80px rgba(37,49,61,.28); display: flex; flex-direction: column; overflow: hidden; }
.live-drawer > header { display: flex; justify-content: space-between; align-items: center; padding: 15px 17px; border-bottom: 1px solid ${C.line}; }
.live-drawer header span, .live-drawer header strong { display: block; }
.live-drawer header span { color: ${C.slate}; font-size: 10px; text-transform: uppercase; letter-spacing: .1em; }
.live-drawer header button { border: 0; background: transparent; font-size: 25px; cursor: pointer; color: ${C.slate}; }
.live-drawer-body { display: grid; grid-template-columns: 210px 1fr; min-height: 0; flex: 1; }
.live-event-list { border-right: 1px solid ${C.line}; overflow: auto; padding: 8px; }
.live-event-list button { display: block; width: 100%; border: 0; border-radius: 8px; background: transparent; text-align: left; padding: 8px; cursor: pointer; }
.live-event-list button.selected { background: ${C.blueSoft}; }
.live-event-list span, .live-event-list em { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.live-event-list span { color: ${C.ink}; font-size: 11px; font-weight: 700; }
.live-event-list em { color: ${C.slate}; font-size: 9.5px; font-style: normal; margin-top: 2px; }
.live-drawer pre { margin: 0; padding: 15px; overflow: auto; background: ${C.paper}; color: ${C.ink}; font: 10.5px/1.55 'JetBrains Mono', monospace; white-space: pre-wrap; word-break: break-word; }
@media (max-width: 950px) { .live-phases { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 650px) { .live-stage { padding: 14px; } .live-phases { grid-template-columns: 1fr 1fr; } .live-top-actions .live-connection { display: none; } .live-drawer-body { grid-template-columns: 1fr; } .live-event-list { max-height: 180px; border-right: 0; border-bottom: 1px solid ${C.line}; } }
`;
