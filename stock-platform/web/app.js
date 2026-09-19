/* marketlab UI.
   Charts are hand-built SVG: no CDN, no chart library, so this page works
   offline. Colors come from the CSS custom properties in styles.css, which
   hold the validated categorical palette in fixed slot order. */

const SLOTS = 8;              // the palette has 8 slots and is never cycled
const $ = (id) => document.getElementById(id);
const state = { strategies: [], last: null, selectedRow: 0 };

const css = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const seriesColor = (i) => css(`--s${(i % SLOTS) + 1}`);

/* ---------- formatting ---------- */
const fmtPct = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`;
const fmtNum = (v, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(d);
const fmtMoney = (v) =>
  v === null || v === undefined ? "—" :
  Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
const signClass = (v) => (v === null || v === undefined ? "" : v >= 0 ? "pos" : "neg");

async function api(path, body) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({ error: `${response.status} ${response.statusText}` }));
  if (!response.ok || payload.error) throw new Error(payload.error || `request failed (${response.status})`);
  return payload;
}

function note(target, message, bad = false) {
  $(target).innerHTML = message
    ? `<div class="note${bad ? " bad" : ""}">${message}</div>`
    : "";
}

/* ---------- charts ---------- */

function svgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function niceTicks(min, max, count = 5) {
  if (min === max) return [min];
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) ticks.push(t);
  return ticks;
}

/* One reusable time-series chart.
   series: [{ name, values (nullable), color, width, dashed, band:{upper,lower} }] */
function drawChart(container, opts) {
  const {
    dates, series, height = 260, yFormat = (v) => fmtNum(v, 2),
    baseline = null, directLabels = true, tooltipFormat = null,
  } = opts;
  container.innerHTML = "";
  if (!dates || dates.length < 2) {
    container.innerHTML = '<p class="loading">not enough data to plot</p>';
    return;
  }

  const W = 1000;
  const labelRoom = directLabels && series.filter((s) => s.values).length <= 4 ? 94 : 16;
  const m = { top: 12, right: labelRoom, bottom: 26, left: 58 };
  const plotW = W - m.left - m.right;
  const plotH = height - m.top - m.bottom;

  let lo = Infinity, hi = -Infinity;
  const consider = (v) => {
    if (v === null || v === undefined || Number.isNaN(v)) return;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  };
  series.forEach((s) => {
    (s.values || []).forEach(consider);
    if (s.band) { s.band.upper.forEach(consider); s.band.lower.forEach(consider); }
  });
  if (baseline !== null) consider(baseline);
  if (!Number.isFinite(lo)) { container.innerHTML = '<p class="loading">no values to plot</p>'; return; }
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.06;
  lo -= pad; hi += pad;

  const n = dates.length;
  const x = (i) => m.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v) => m.top + plotH - ((v - lo) / (hi - lo)) * plotH;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${height}`, role: "img" });
  svg.setAttribute("aria-label", opts.ariaLabel || "time series chart");

  /* recessive grid + y axis labels */
  niceTicks(lo, hi).forEach((t) => {
    svg.appendChild(svgEl("line", {
      x1: m.left, x2: m.left + plotW, y1: y(t), y2: y(t),
      stroke: css("--grid"), "stroke-width": 1,
    }));
    const label = svgEl("text", {
      x: m.left - 8, y: y(t) + 4, "text-anchor": "end",
      fill: css("--muted"), "font-size": 11, "font-family": css("--font"),
    });
    label.textContent = yFormat(t);
    svg.appendChild(label);
  });

  if (baseline !== null) {
    svg.appendChild(svgEl("line", {
      x1: m.left, x2: m.left + plotW, y1: y(baseline), y2: y(baseline),
      stroke: css("--axis"), "stroke-width": 1.5, "stroke-dasharray": "4 4",
    }));
  }

  /* x axis labels, thinned to ~6 */
  const every = Math.max(1, Math.floor(n / 6));
  for (let i = 0; i < n; i += every) {
    const label = svgEl("text", {
      x: x(i), y: height - 8, "text-anchor": "middle",
      fill: css("--muted"), "font-size": 11, "font-family": css("--font"),
    });
    label.textContent = String(dates[i]).slice(0, 7);
    svg.appendChild(label);
  }

  /* bands first, so lines sit on top */
  series.forEach((s) => {
    if (!s.band) return;
    const pts = [];
    for (let i = 0; i < n; i++) if (s.band.upper[i] !== null) pts.push([x(i), y(s.band.upper[i])]);
    for (let i = n - 1; i >= 0; i--) if (s.band.lower[i] !== null) pts.push([x(i), y(s.band.lower[i])]);
    if (pts.length < 3) return;
    svg.appendChild(svgEl("path", {
      d: `M${pts.map((p) => p.join(",")).join("L")}Z`,
      fill: s.color, opacity: 0.1, stroke: "none",
    }));
  });

  /* lines and filled areas */
  series.forEach((s) => {
    if (!s.values) return;
    let d = "";
    let open = false;
    for (let i = 0; i < n; i++) {
      const v = s.values[i];
      if (v === null || v === undefined || Number.isNaN(v)) { open = false; continue; }
      d += `${open ? "L" : "M"}${x(i).toFixed(2)},${y(v).toFixed(2)}`;
      open = true;
    }
    if (!d) return;
    if (s.fillTo !== undefined) {
      const first = s.values.findIndex((v) => v !== null && v !== undefined);
      const last = s.values.length - 1 - [...s.values].reverse()
        .findIndex((v) => v !== null && v !== undefined);
      svg.appendChild(svgEl("path", {
        d: `${d}L${x(last).toFixed(2)},${y(s.fillTo).toFixed(2)}L${x(first).toFixed(2)},${y(s.fillTo).toFixed(2)}Z`,
        fill: s.color, opacity: 0.14, stroke: "none",
      }));
    }
    svg.appendChild(svgEl("path", {
      d, fill: "none", stroke: s.color, "stroke-width": s.width || 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
      ...(s.dashed ? { "stroke-dasharray": "5 4" } : {}),
    }));
  });

  /* direct labels: identity without relying on color alone */
  if (labelRoom > 20) {
    const placed = [];
    series.filter((s) => s.values).forEach((s) => {
      const lastIdx = s.values.length - 1 - [...s.values].reverse()
        .findIndex((v) => v !== null && v !== undefined);
      if (lastIdx < 0 || s.values[lastIdx] === null) return;
      let ly = y(s.values[lastIdx]);
      while (placed.some((p) => Math.abs(p - ly) < 13)) ly += 13;
      placed.push(ly);
      const label = svgEl("text", {
        x: m.left + plotW + 7, y: ly + 4, fill: css("--ink-2"),
        "font-size": 11.5, "font-family": css("--font"), "font-weight": 600,
      });
      label.textContent = s.name.length > 15 ? `${s.name.slice(0, 14)}…` : s.name;
      svg.appendChild(label);
    });
  }

  /* axis line */
  svg.appendChild(svgEl("line", {
    x1: m.left, x2: m.left + plotW, y1: m.top + plotH, y2: m.top + plotH,
    stroke: css("--axis"), "stroke-width": 1,
  }));

  /* hover layer: crosshair + markers + tooltip */
  const crosshair = svgEl("line", {
    y1: m.top, y2: m.top + plotH, stroke: css("--axis"),
    "stroke-width": 1, opacity: 0,
  });
  svg.appendChild(crosshair);
  const dots = series.filter((s) => s.values).map((s) => {
    const dot = svgEl("circle", {
      r: 4.5, fill: s.color, stroke: css("--surface"), "stroke-width": 2, opacity: 0,
    });
    svg.appendChild(dot);
    return { dot, s };
  });
  const hit = svgEl("rect", {
    x: m.left, y: m.top, width: plotW, height: plotH, fill: "transparent",
  });
  svg.appendChild(hit);
  container.appendChild(svg);

  const tip = document.createElement("div");
  tip.className = "tooltip";
  container.appendChild(tip);

  const onMove = (event) => {
    const box = svg.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    let i = Math.round(((px - m.left) / plotW) * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    crosshair.setAttribute("x1", x(i));
    crosshair.setAttribute("x2", x(i));
    crosshair.setAttribute("opacity", 1);
    const rows = [];
    dots.forEach(({ dot, s }) => {
      const v = s.values[i];
      if (v === null || v === undefined || Number.isNaN(v)) { dot.setAttribute("opacity", 0); return; }
      dot.setAttribute("cx", x(i));
      dot.setAttribute("cy", y(v));
      dot.setAttribute("opacity", 1);
      rows.push(`<div class="t-row"><span><span class="mark" style="background:${s.color}"></span>${s.name}</span><b>${(tooltipFormat || yFormat)(v)}</b></div>`);
    });
    tip.innerHTML = `<div class="t-date">${dates[i]}</div>${rows.join("")}`;
    tip.style.opacity = 1;
    const wrapBox = container.getBoundingClientRect();
    const left = event.clientX - wrapBox.left;
    tip.style.left = `${Math.min(Math.max(8, left + 14), wrapBox.width - tip.offsetWidth - 8)}px`;
    tip.style.top = `${Math.max(4, event.clientY - wrapBox.top - tip.offsetHeight - 12)}px`;
  };
  const onLeave = () => {
    tip.style.opacity = 0;
    crosshair.setAttribute("opacity", 0);
    dots.forEach(({ dot }) => dot.setAttribute("opacity", 0));
  };
  svg.addEventListener("pointermove", onMove);
  svg.addEventListener("pointerleave", onLeave);
}

function renderLegend(target, entries) {
  $(target).innerHTML = entries.map((e) =>
    `<span><span class="swatch ${e.line ? "line" : ""}" style="background:${e.color}"></span>${e.name}</span>`
  ).join("");
}

/* ---------- strategy picker ---------- */

function renderStrategies() {
  const grid = $("strategy-grid");
  grid.innerHTML = "";
  const defaults = new Set(["sma_crossover", "rsi_reversion", "macd_cross", "donchian"]);
  state.strategies.filter((s) => s.key !== "buy_and_hold").forEach((s) => {
    const card = document.createElement("div");
    card.className = "strategy-card";
    card.dataset.key = s.key;
    const params = s.params.map((p) => {
      if (p.kind === "bool") {
        return `<div class="field"><label for="p-${s.key}-${p.name}">${p.label}</label>
          <input type="checkbox" id="p-${s.key}-${p.name}" data-param="${p.name}" ${p.default ? "checked" : ""}></div>`;
      }
      return `<div class="field"><label for="p-${s.key}-${p.name}">${p.label}</label>
        <input type="number" id="p-${s.key}-${p.name}" data-param="${p.name}" value="${p.default}"
          min="${p.min}" max="${p.max}" step="${p.step}"></div>`;
    }).join("");
    card.innerHTML = `
      <label class="name"><input type="checkbox" class="pick" ${defaults.has(s.key) ? "checked" : ""}>
        ${s.label}</label>
      <div class="summary">${s.summary}</div>
      <div class="params">${params}</div>`;
    const sync = () => card.classList.toggle("on", card.querySelector(".pick").checked);
    card.querySelector(".pick").addEventListener("change", sync);
    sync();
    grid.appendChild(card);
  });

  const select = $("sweep-strategy");
  select.innerHTML = state.strategies
    .filter((s) => s.params.length)
    .map((s) => `<option value="${s.key}">${s.label}</option>`).join("");
  select.addEventListener("change", suggestGrid);
  suggestGrid();
}

function suggestGrid() {
  const key = $("sweep-strategy").value;
  const strategy = state.strategies.find((s) => s.key === key);
  if (!strategy) return;
  const parts = strategy.params
    .filter((p) => p.kind !== "bool")
    .slice(0, 2)
    .map((p) => {
      const d = Number(p.default) || 10;
      const steps = [0.5, 0.75, 1, 1.5, 2]
        .map((f) => (p.kind === "int" ? Math.max(2, Math.round(d * f)) : +(d * f).toFixed(2)))
        .filter((v, i, arr) => arr.indexOf(v) === i);
      return `${p.name}=${steps.join(",")}`;
    });
  $("sweep-grid").value = parts.join(" ");
}

function selectedStrategies() {
  return [...document.querySelectorAll(".strategy-card")]
    .filter((card) => card.querySelector(".pick").checked)
    .map((card) => {
      const params = {};
      card.querySelectorAll("[data-param]").forEach((input) => {
        params[input.dataset.param] =
          input.type === "checkbox" ? input.checked : Number(input.value);
      });
      return { key: card.dataset.key, params };
    });
}

function dataRequest() {
  const source = $("source").value;
  return {
    source,
    symbol: source === "csv" ? ($("csv").value.split("/").pop() || "CSV") : $("symbol").value.trim().toUpperCase(),
    csv_path: $("csv").value.trim() || null,
    start: $("start").value || null,
    end: $("end").value || null,
  };
}

/* ---------- rendering results ---------- */

function renderSnapshot(meta, analysis) {
  $("snapshot-panel").hidden = false;
  const tiles = [
    ["Last close", fmtNum(analysis.last_close), `${meta.last_date} · ${meta.bars} bars`],
    ["1-year return", fmtPct(analysis.return_1y), "close to close", analysis.return_1y],
    ["vs 200-day MA", fmtPct(analysis.pct_from_sma_200), "above is a trend signal", analysis.pct_from_sma_200],
    ["RSI (14)", fmtNum(analysis.rsi_14, 1), "30 oversold · 70 overbought"],
    ["Annualised vol", fmtPct(analysis.volatility_annualised), "last 252 bars, 252-day basis"],
    ["Drawdown now", fmtPct(analysis.current_drawdown), `worst here ${fmtPct(analysis.max_drawdown_in_window)}`, analysis.current_drawdown],
  ];
  $("tiles").innerHTML = tiles.map(([k, v, s, sign]) =>
    `<div class="tile"><div class="k">${k}</div>
     <div class="v ${sign === undefined ? "" : signClass(sign)}">${v}</div>
     <div class="s">${s}</div></div>`).join("");
}

function renderPriceChart(meta, chart) {
  $("price-panel").hidden = false;
  $("price-title").textContent = `${meta.symbol} price`;
  const series = [
    { name: "Close", values: chart.close, color: seriesColor(0), width: 2,
      band: { upper: chart.bb_upper, lower: chart.bb_lower } },
    { name: "SMA 50", values: chart.sma_50, color: seriesColor(1), width: 1.75 },
    { name: "SMA 200", values: chart.sma_200, color: seriesColor(2), width: 1.75, dashed: true },
  ];
  renderLegend("price-legend", [
    { name: "Close", color: seriesColor(0), line: true },
    { name: "SMA 50", color: seriesColor(1), line: true },
    { name: "SMA 200", color: seriesColor(2), line: true },
    { name: "Bollinger 20 · 2sd", color: seriesColor(0) },
  ]);
  drawChart($("price-chart"), {
    dates: chart.dates, series, height: 300,
    yFormat: (v) => fmtNum(v, v > 1000 ? 0 : 2),
    ariaLabel: `${meta.symbol} closing price with moving averages`,
  });
}

function renderEquity(payload) {
  const ranked = payload.ranking;
  const byName = new Map(payload.results.map((r) => [r.strategy, r]));
  const shown = ranked.slice(0, SLOTS);
  const series = shown.map((row, i) => {
    const result = byName.get(row.strategy);
    return {
      name: row.strategy, values: result.series.equity, color: seriesColor(i), width: 2,
      key: row.key,
    };
  });
  $("equity-panel").hidden = false;
  renderLegend("equity-legend", series.map((s) => ({ name: s.name, color: s.color, line: true })));
  const dates = payload.results[0].series.dates;
  drawChart($("equity-chart"), {
    dates, series, height: 300, baseline: payload.config.initial_cash,
    yFormat: (v) => fmtMoney(v), ariaLabel: "equity curve per strategy",
  });
  drawChart($("drawdown-chart"), {
    dates, height: 200, baseline: 0,
    series: shown.map((row, i) => ({
      name: row.strategy, values: byName.get(row.strategy).series.drawdown,
      color: seriesColor(i), width: 1.75,
      fillTo: shown.length === 1 ? 0 : undefined,
    })),
    yFormat: (v) => fmtPct(v, 0), ariaLabel: "drawdown per strategy",
  });
}

const COLUMNS = [
  ["strategy", "Strategy", (r) => r.strategy, null],
  ["cagr", "CAGR", (r) => fmtPct(r.metrics.cagr), (r) => r.metrics.cagr],
  ["total_return", "Total", (r) => fmtPct(r.metrics.total_return), (r) => r.metrics.total_return],
  ["sharpe", "Sharpe", (r) => fmtNum(r.metrics.sharpe), (r) => r.metrics.sharpe],
  ["sortino", "Sortino", (r) => fmtNum(r.metrics.sortino), (r) => r.metrics.sortino],
  ["max_drawdown", "Max DD", (r) => fmtPct(r.metrics.max_drawdown), (r) => r.metrics.max_drawdown],
  ["calmar", "Calmar", (r) => fmtNum(r.metrics.calmar), (r) => r.metrics.calmar],
  ["volatility", "Vol", (r) => fmtPct(r.metrics.volatility), (r) => r.metrics.volatility],
  ["trades", "Trades", (r) => r.metrics.trades ?? "—", (r) => r.metrics.trades],
  ["win_rate", "Win %", (r) => fmtPct(r.metrics.win_rate, 0), (r) => r.metrics.win_rate],
  ["profit_factor", "PF", (r) => fmtNum(r.metrics.profit_factor), (r) => r.metrics.profit_factor],
  ["exposure", "In market", (r) => fmtPct(r.metrics.exposure, 0), (r) => r.metrics.exposure],
  ["total_costs", "Costs", (r) => fmtMoney(r.metrics.total_costs), (r) => r.metrics.total_costs],
];

let sortState = { key: null, dir: -1 };

function renderTable(payload) {
  $("table-panel").hidden = false;
  const rows = [...payload.ranking];
  const colorOf = new Map(payload.ranking.slice(0, SLOTS).map((r, i) => [r.strategy, seriesColor(i)]));
  if (sortState.key) {
    const col = COLUMNS.find((c) => c[0] === sortState.key);
    rows.sort((a, b) => {
      const av = col[3] ? col[3](a) : a.strategy;
      const bv = col[3] ? col[3](b) : b.strategy;
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      return (av > bv ? 1 : av < bv ? -1 : 0) * sortState.dir;
    });
  }
  const head = `<thead><tr>${COLUMNS.map(([key, label]) =>
    `<th data-key="${key}"${sortState.key === key ? ` aria-sort="${sortState.dir === 1 ? "ascending" : "descending"}"` : ""}>${label}</th>`
  ).join("")}</tr></thead>`;
  const body = `<tbody>${rows.map((r) => `<tr data-strategy="${r.strategy}">
    ${COLUMNS.map(([key, , render], i) => {
      const value = render(r);
      const cls = ["cagr", "total_return"].includes(key) ? signClass(r.metrics[key]) : "";
      const mark = i === 0 && colorOf.has(r.strategy)
        ? `<span class="mark" style="background:${colorOf.get(r.strategy)}"></span>` : "";
      return `<td class="${cls}">${mark}${value}</td>`;
    }).join("")}</tr>`).join("")}</tbody>`;
  const table = $("results-table");
  table.innerHTML = head + body;
  table.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
    const key = th.dataset.key;
    sortState = { key, dir: sortState.key === key ? -sortState.dir : -1 };
    renderTable(payload);
  }));
  table.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => {
    renderTrades(payload, tr.dataset.strategy);
  }));

  const warnings = new Set(payload.results.flatMap((r) => r.warnings));
  const config = payload.config;
  const lines = [
    `<strong>Assumptions:</strong> ${config.fee_bps} bps commission + ${config.slippage_bps} bps
     slippage per side, fills at ${config.execution.replace("_", " ")}, Sharpe against a
     ${fmtPct(config.rf_annual, 1)} risk-free rate, 252 bars per year.`,
  ];
  // The palette has a fixed number of slots and is never cycled, so the charts
  // show the leaders and this table carries the rest.
  if (payload.ranking.length > SLOTS) {
    lines.push(`Charting the top ${SLOTS} of ${payload.ranking.length} strategies by
      ${$("rank").selectedOptions[0].textContent.toLowerCase()} — every one of them is in
      the table below, and the coloured squares mark the charted ones.`);
  }
  lines.push(...[...warnings].map((w) => `⚠ ${w}`));
  note("result-warnings", lines.join("<br>"));
  renderTrades(payload, payload.ranking[0].strategy);
}

function renderTrades(payload, strategyName) {
  const result = payload.results.find((r) => r.strategy === strategyName);
  if (!result) return;
  $("trades-panel").hidden = false;
  $("trades-title").textContent = `Trades — ${strategyName} (${result.trades.length})`;
  if (!result.trades.length) {
    $("trades-table").innerHTML = "<tbody><tr><td>no trades</td></tr></tbody>";
    return;
  }
  const head = `<thead><tr><th>Side</th><th>Entry</th><th>Price</th><th>Exit</th><th>Price</th>
    <th>Bars</th><th>Return</th><th>P&amp;L</th><th>Costs</th></tr></thead>`;
  const body = result.trades.map((t) => `<tr>
    <td>${t.direction}</td><td>${t.entry_date}</td><td>${fmtNum(t.entry_price)}</td>
    <td>${t.exit_date}</td><td>${fmtNum(t.exit_price)}</td><td>${t.bars_held}</td>
    <td class="${signClass(t.return_pct)}">${fmtPct(t.return_pct, 2)}</td>
    <td class="${signClass(t.pnl)}">${fmtMoney(t.pnl)}</td><td>${fmtNum(t.costs)}</td></tr>`).join("");
  $("trades-table").innerHTML = `${head}<tbody>${body}</tbody>`;
}

/* ---------- actions ---------- */

function backtestRequest() {
  return {
    ...dataRequest(),
    strategies: selectedStrategies(),
    initial_cash: Number($("cash").value),
    fee_bps: Number($("fee").value),
    slippage_bps: Number($("slip").value),
    execution: $("execution").value,
    rf_annual: Number($("rf").value),
    rank_by: $("rank").value,
  };
}

async function runBacktest() {
  const button = $("run");
  const picked = selectedStrategies();
  if (!picked.length) {
    note("data-note", "Pick at least one strategy — buy-and-hold alone is the benchmark, not a test.", true);
    return;
  }
  button.disabled = true;
  note("data-note", "running…");
  try {
    const payload = await api("/api/backtest", backtestRequest());
    state.last = payload;
    const meta = payload.meta;
    let message = `<strong>${meta.symbol}</strong> · ${meta.first_date} → ${meta.last_date} ·
      ${meta.bars} bars · source ${meta.source}`;
    if (meta.synthetic) message += "<br>⚠ Synthetic data: a seeded random walk, not a real security.";
    if (meta.adjustment_warning) message += `<br>⚠ ${meta.adjustment_warning}`;
    note("data-note", message, Boolean(meta.synthetic));
    renderSnapshot(meta, { ...payload.chart, ...summaryFromChart(payload) });
    renderPriceChart(meta, payload.chart);
    renderEquity(payload);
    renderTable(payload);
  } catch (error) {
    note("data-note", `<strong>Failed:</strong> ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
}

/* The backtest response carries the chart series; derive the snapshot tiles
   from an /api/analysis call so the numbers come from one place. */
async function loadAnalysis() {
  const request = dataRequest();
  const query = new URLSearchParams(
    Object.entries(request).filter(([, v]) => v !== null && v !== "")
  );
  const payload = await api(`/api/analysis?${query}`);
  state.analysis = payload.analysis;
  renderSnapshot(payload.meta, payload.analysis);
  renderPriceChart(payload.meta, payload.chart);
  return payload;
}

function summaryFromChart() {
  return state.analysis || {};
}

async function loadAndRun() {
  note("data-note", "loading data…");
  try {
    await loadAnalysis();
  } catch (error) {
    note("data-note", `<strong>Could not load data:</strong> ${error.message}`, true);
    return;
  }
  await runBacktest();
}

async function runSweep() {
  const button = $("sweep-run");
  const grid = {};
  $("sweep-grid").value.trim().split(/\s+/).filter(Boolean).forEach((part) => {
    const [name, values] = part.split("=");
    if (name && values) grid[name] = values.split(",").map(Number).filter((v) => !Number.isNaN(v));
  });
  if (!Object.keys(grid).length) {
    $("sweep-out").innerHTML = '<div class="note bad">Grid looks empty. Use <code>fast=10,20 slow=100,200</code>.</div>';
    return;
  }
  button.disabled = true;
  $("sweep-out").innerHTML = '<p class="loading">sweeping…</p>';
  try {
    const payload = await api("/api/sweep", {
      ...dataRequest(),
      key: $("sweep-strategy").value,
      grid,
      metric: $("sweep-metric").value,
      in_sample_fraction: Number($("sweep-split").value),
      initial_cash: Number($("cash").value),
      fee_bps: Number($("fee").value),
      slippage_bps: Number($("slip").value),
      execution: $("execution").value,
    });
    const metric = payload.metric;
    const rows = payload.results.map((r) => {
      const params = Object.entries(r.params)
        .filter(([k]) => k !== "allow_short").map(([k, v]) => `${k}=${v}`).join(", ");
      const is = r.in_sample, oos = r.out_of_sample || {};
      const held = is[metric] !== null && oos[metric] !== null && oos[metric] !== undefined
        && Math.sign(oos[metric]) === Math.sign(is[metric]);
      return `<tr><td>${params}</td>
        <td>${fmtNum(is[metric])}</td>
        <td class="${signClass(oos[metric])}">${fmtNum(oos[metric])}</td>
        <td>${fmtPct(is.cagr)}</td><td class="${signClass(oos.cagr)}">${fmtPct(oos.cagr)}</td>
        <td>${fmtPct(is.max_drawdown)}</td><td>${fmtPct(oos.max_drawdown)}</td>
        <td>${is.trades}</td>
        <td>${held ? "held up" : "did not hold"}</td></tr>`;
    }).join("");
    $("sweep-out").innerHTML = `
      <div class="note"><strong>${payload.strategy}</strong> · ${payload.combinations_tested}
        combinations · split at ${payload.split_date} (${payload.in_sample_bars} in-sample /
        ${payload.out_of_sample_bars} out-of-sample)<br>${payload.caveat}</div>
      <div class="scroll"><table><thead><tr>
        <th>Params</th><th>IS ${metric}</th><th>OOS ${metric}</th><th>IS CAGR</th>
        <th>OOS CAGR</th><th>IS max DD</th><th>OOS max DD</th><th>IS trades</th><th>Verdict</th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (error) {
    $("sweep-out").innerHTML = `<div class="note bad">Sweep failed: ${error.message}</div>`;
  } finally {
    button.disabled = false;
  }
}

async function runDoctor() {
  $("doctor-panel").classList.remove("hidden");
  $("doctor-out").textContent = "probing…";
  try {
    const report = await api("/api/doctor");
    $("doctor-out").textContent = JSON.stringify(report, null, 2);
  } catch (error) {
    $("doctor-out").textContent = `failed: ${error.message}`;
  }
}

/* ---------- boot ---------- */

async function boot() {
  $("end").value = new Date().toISOString().slice(0, 10);
  $("source").addEventListener("change", () => {
    const source = $("source").value;
    $("csv-field").classList.toggle("hidden", source !== "csv");
    $("symbol-field").classList.toggle("hidden", source === "csv");
    if (source === "demo") $("symbol").value = "SYNTHETIC-DEMO";
  });
  $("load").addEventListener("click", loadAndRun);
  $("run").addEventListener("click", runBacktest);
  $("sweep-run").addEventListener("click", runSweep);
  $("doctor-btn").addEventListener("click", runDoctor);

  try {
    const health = await api("/api/health");
    $("status").innerHTML = health.api_key_configured
      ? `API key <b>configured</b> · transport <b>${health.transport}</b> · end-of-day data.
         Use “Test API key” to confirm it answers.`
      : `<b>No API key configured.</b> Put <code>MARKETSTACK_API_KEY=…</code> in
         <code>stock-platform/.env</code>, or pick the demo source below.`;
    if (!health.api_key_configured) $("source").value = "demo";
  } catch (error) {
    $("status").textContent = `server not reachable: ${error.message}`;
  }
  try {
    const payload = await api("/api/strategies");
    state.strategies = payload.strategies;
    renderStrategies();
  } catch (error) {
    $("strategy-grid").innerHTML = `<div class="note bad">Could not load strategies: ${error.message}</div>`;
  }
}

boot();
