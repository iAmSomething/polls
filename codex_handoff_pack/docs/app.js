(function () {
  const THEME_STORAGE_KEY = "wk_poll_theme_mode";

  function getThemeMode() {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
    return "system";
  }

  function applyTheme(mode) {
    const root = document.documentElement;
    if (mode === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", mode);
    }
    localStorage.setItem(THEME_STORAGE_KEY, mode);
    document.querySelectorAll(".theme-btn").forEach((btn) => {
      const active = btn.dataset.theme === mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function initThemeToggle() {
    const mode = getThemeMode();
    applyTheme(mode);
    document.querySelectorAll(".theme-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = btn.dataset.theme || "system";
        applyTheme(next);
        const chart = document.getElementById("chart");
        if (chart && window.Plotly && chart.data) {
          Plotly.react(chart, chart.data, buildLayout(), {
            displayModeBar: false,
            responsive: true,
            scrollZoom: false,
            doubleClick: false
          });
        }
      });
    });
  }

  function daysBetween(a, b) {
    const ms = b.getTime() - a.getTime();
    if (!Number.isFinite(ms)) return null;
    return Math.floor(ms / 86400000);
  }

  function updateFreshnessBadge() {
    const badge = document.getElementById("freshness-badge");
    const stamp = document.getElementById("stamp");
    if (!badge || !stamp) return;
    const latestRaw = stamp.dataset.latestDate || "";
    const updatedRaw = stamp.dataset.updatedAt || "";
    const latest = latestRaw ? new Date(`${latestRaw}T00:00:00+09:00`) : null;
    const updated = updatedRaw ? new Date(updatedRaw) : null;
    if (!latest || Number.isNaN(latest.getTime()) || !updated || Number.isNaN(updated.getTime())) {
      badge.textContent = "최신성 확인 불가";
      badge.className = "freshness-badge stale";
      return;
    }
    const diff = daysBetween(latest, updated);
    if (diff === null) return;
    if (diff < 0) {
      badge.className = "freshness-badge old";
      badge.textContent = `반영일이 갱신시각보다 미래 (${Math.abs(diff)}일)`;
    } else if (diff <= 3) {
      badge.className = "freshness-badge fresh";
      badge.textContent = `데이터 최신성 높음 · ${diff}일 차`;
    } else if (diff <= 10) {
      badge.className = "freshness-badge stale";
      badge.textContent = `데이터 시차 ${diff}일`;
    } else {
      badge.className = "freshness-badge old";
      badge.textContent = `데이터 시차 큼 · ${diff}일`;
    }
  }

  initThemeToggle();
  updateFreshnessBadge();
  const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initRevealAnimations() {
    const items = document.querySelectorAll(".reveal");
    if (!items.length) return;
    if (reducedMotion || !("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("in-view"));
      return;
    }
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("in-view");
        obs.unobserve(entry.target);
      });
    }, { root: null, rootMargin: "0px 0px -10% 0px", threshold: 0.15 });
    items.forEach((el) => observer.observe(el));
  }

  function animateValue(el, start, end, duration, decimals, suffix, finalText) {
    let startTime = null;
    function step(timestamp) {
      if (startTime === null) startTime = timestamp;
      const progress = timestamp - startTime;
      const percent = Math.min(progress / duration, 1);
      const value = start + percent * (end - start);
      el.textContent = `${value.toFixed(decimals)}${suffix || ""}`;
      if (progress < duration) {
        requestAnimationFrame(step);
      } else if (finalText) {
        el.textContent = finalText;
      }
    }
    requestAnimationFrame(step);
  }

  function initKpiCountUp() {
    const nodes = document.querySelectorAll(".insight-value[data-kpi-value]");
    if (!nodes.length) return;
    nodes.forEach((el) => {
      const end = Number(el.dataset.kpiValue);
      if (!Number.isFinite(end)) return;
      const decimals = Number(el.dataset.kpiDecimals || "2");
      const suffix = el.dataset.kpiSuffix || "";
      const finalText = el.textContent;
      if (reducedMotion) {
        if (finalText) el.textContent = finalText;
        return;
      }
      animateValue(el, 0, end, 800, Number.isFinite(decimals) ? decimals : 2, suffix, finalText);
    });
  }

  initRevealAnimations();
  initKpiCountUp();

  const dataEl = document.getElementById("poll-data");
  if (!dataEl) return;
  const payload = JSON.parse(dataEl.textContent);
  const tracesData = payload.traces || [];
  const presidentRaw = payload.president_raw || {};
  const latestPollResults = payload.latest_poll_results || [];
  const pollsterColorMap = payload.pollster_color_map || {};
  const partyColorMap = {};
  tracesData.forEach((t) => {
    if (t && t.party && t.color && !partyColorMap[t.party]) {
      partyColorMap[t.party] = t.color;
    }
  });
  const chartDiv = document.getElementById("chart");
  if (!chartDiv) return;
  const BAND_BASE_HALF_WIDTH = 2.2;
  const BAND_VOL_MULTIPLIER = 0.85;
  const BAND_MIN_HALF_WIDTH = 1.8;
  const BAND_MAX_HALF_WIDTH = 4.2;
  const BAND_OPACITY = 0.30;
  const BAND_CENTER_WINDOW = 7;
  const BAND_WIDTH_WINDOW = 7;

  function hexToRgba(hex, alpha) {
    const clean = String(hex || "").replace("#", "").trim();
    if (clean.length !== 6) return `rgba(70, 95, 135, ${alpha})`;
    const r = parseInt(clean.slice(0, 2), 16);
    const g = parseInt(clean.slice(2, 4), 16);
    const b = parseInt(clean.slice(4, 6), 16);
    if (![r, g, b].every((v) => Number.isFinite(v))) return `rgba(70, 95, 135, ${alpha})`;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function smoothSeries(values, windowSize) {
    const src = (values || []).map((v) => (Number.isFinite(v) ? Number(v) : null));
    const half = Math.max(1, Math.floor(windowSize / 2));
    const out = [];
    for (let i = 0; i < src.length; i++) {
      if (src[i] === null) {
        out.push(null);
        continue;
      }
      let wSum = 0;
      let vSum = 0;
      for (let j = Math.max(0, i - half); j <= Math.min(src.length - 1, i + half); j++) {
        const v = src[j];
        if (v === null) continue;
        const w = half + 1 - Math.abs(i - j);
        wSum += w;
        vSum += w * v;
      }
      out.push(wSum > 0 ? (vSum / wSum) : src[i]);
    }
    return out;
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function getPollsterColor(name) {
    const s = String(name || "").trim();
    if (!s) return "#64748B";
    const keys = Object.keys(pollsterColorMap);
    for (const k of keys) {
      if (s.includes(k)) return pollsterColorMap[k];
    }
    return "#64748B";
  }

  function buildSmoothedBand(y) {
    const raw = (y || []).map((v) => (Number.isFinite(v) ? Number(v) : null));
    const center = smoothSeries(raw, BAND_CENTER_WINDOW);
    const residualAbs = raw.map((v, i) => {
      if (v === null || center[i] === null) return null;
      return Math.abs(v - center[i]);
    });
    const localVol = smoothSeries(residualAbs, BAND_WIDTH_WINDOW);
    const halfWidth = localVol.map((v) => {
      const vol = v === null ? 0.0 : v;
      return clamp(BAND_BASE_HALF_WIDTH + BAND_VOL_MULTIPLIER * vol, BAND_MIN_HALF_WIDTH, BAND_MAX_HALF_WIDTH);
    });
    const upper = center.map((v, i) => {
      if (v === null) return null;
      return Math.min(100, v + halfWidth[i]);
    });
    const lower = center.map((v, i) => {
      if (v === null) return null;
      return Math.max(0, v - halfWidth[i]);
    });
    return { upper, lower };
  }

  function buildTraces() {
    const out = [];
    const dashStyles = ["solid", "dash", "dot", "longdash", "dashdot"];
    const markerSymbols = ["circle", "square", "triangle-up", "cross", "star"];
    tracesData.forEach((p, idx) => {
      const dash = dashStyles[idx % dashStyles.length];
      const symbol = markerSymbols[idx % markerSymbols.length];
      const band = buildSmoothedBand(p.actual_y);
      out.push({
        x: p.actual_x, y: band.upper, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        meta: "band"
      });
      out.push({
        x: p.actual_x, y: band.lower, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        fill: "tonexty", fillcolor: hexToRgba(p.color, BAND_OPACITY),
        meta: "band"
      });
      out.push({
        x: p.actual_x, y: p.actual_y, type: "scatter", mode: "lines", name: (p.display_party || p.party),
        legendgroup: p.party, line: { color: p.color, width: 2.7, dash },
        hovertemplate: "<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>"
      });
      out.push({
        x: p.forecast_x, y: p.forecast_y, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, line: { color: p.color, width: 2.2, dash: "dot" },
        hoverinfo: "skip"
      });
      out.push({
        x: [p.pred_x], y: [p.pred_y], type: "scatter", mode: "markers+text",
        legendgroup: p.party, showlegend: false, meta: (p.display_party || p.party),
        marker: { color: p.color, size: 10, symbol, line: { color: "#DDE8FF", width: 1 } },
        text: ["예측치"], textposition: "middle right", textfont: { color: p.color, size: 11 },
        customdata: [[p.pred_lo_80, p.pred_hi_80]],
        hovertemplate: "<b>%{meta} 예측</b><br>%{y:.2f}%<br>80% 구간: %{customdata[0]:.2f}% ~ %{customdata[1]:.2f}%<extra></extra>"
      });
    });
    if (Array.isArray(latestPollResults) && latestPollResults.length) {
      const top = latestPollResults[0] || {};
      const pollDate = top.date_end || null;
      const pollster = top.pollster || "최신 조사";
      const parties = Array.isArray(top.parties) ? top.parties : [];
      if (pollDate) {
        parties.forEach((row) => {
          const party = row.party;
          const displayParty = row.display_party || row.party || "";
          const val = Number(row.value);
          if (!party || !Number.isFinite(val)) return;
          const exists = tracesData.some((t) => t.party === party);
          if (!exists) return;
          const color = partyColorMap[party] || "#94A3B8";
          out.push({
            x: [pollDate],
            y: [val],
            type: "scatter",
            mode: "markers",
            showlegend: false,
            legendgroup: party,
            marker: { symbol: "diamond", size: 10, color, line: { color: "#DDE8FF", width: 1 } },
            hovertemplate: `<b>최신 여론조사</b><br>${pollster} (${pollDate})<br>${displayParty}: %{y:.1f}%<extra></extra>`
          });
        });
      }
    }
    if (Array.isArray(presidentRaw.x) && presidentRaw.x.length) {
      const approveBand = buildSmoothedBand(presidentRaw.approve || []);
      out.push({
        x: presidentRaw.x,
        y: approveBand.upper,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_approve",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: approveBand.lower,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_approve",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        fill: "tonexty",
        fillcolor: hexToRgba("#1D9BF0", BAND_OPACITY),
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: presidentRaw.approve || [],
        type: "scatter",
        mode: "lines+markers",
        name: "대통령 긍정평가(raw)",
        legendgroup: "president_raw_approve",
        line: { color: "#1D9BF0", width: 2, dash: "dash" },
        marker: { size: 4, color: "#1D9BF0" },
        hovertemplate: "<b>대통령 긍정평가(raw)</b>: %{y:.2f}%<extra></extra>"
      });
      const disapproveBand = buildSmoothedBand(presidentRaw.disapprove || []);
      out.push({
        x: presidentRaw.x,
        y: disapproveBand.upper,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_disapprove",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: disapproveBand.lower,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_disapprove",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        fill: "tonexty",
        fillcolor: hexToRgba("#D83A3A", BAND_OPACITY),
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: presidentRaw.disapprove || [],
        type: "scatter",
        mode: "lines+markers",
        name: "대통령 부정평가(raw)",
        legendgroup: "president_raw_disapprove",
        line: { color: "#D83A3A", width: 2, dash: "dash" },
        marker: { size: 4, color: "#D83A3A" },
        hovertemplate: "<b>대통령 부정평가(raw)</b>: %{y:.2f}%<extra></extra>"
      });
    }
    return out;
  }

  function isDarkMode() {
    const explicit = document.documentElement.getAttribute("data-theme");
    if (explicit === "dark") return true;
    if (explicit === "light") return false;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function isTouchDevice() {
    return (
      (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) ||
      ("ontouchstart" in window) ||
      (navigator.maxTouchPoints > 0)
    );
  }

  function isMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
  }

  function buildLayout() {
    const dark = isDarkMode();
    const compactHover = isTouchDevice() || isMobileViewport();
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: dark ? "#16191F" : "#FFFFFF",
      font: { color: dark ? "#E8EAF0" : "#111827", family: "Inter, Pretendard, sans-serif", size: 14 },
      margin: { l: 58, r: 24, t: 92, b: 48 },
      hovermode: compactHover ? "closest" : "x unified",
      dragmode: "pan",
      hoverlabel: {
        bgcolor: dark ? "#0F1217" : "#FFFFFF",
        bordercolor: dark ? "#2A2E37" : "#E1E5EB",
        font: { color: dark ? "#E8EAF0" : "#111827", size: compactHover ? 12 : 14, family: "Inter, Pretendard, sans-serif" },
        align: "left",
        namelength: compactHover ? 32 : -1
      },
      xaxis: {
        tickfont: { size: 14 },
        gridcolor: dark ? "rgba(156,163,175,0.22)" : "rgba(107,114,128,0.20)",
        linecolor: dark ? "rgba(156,163,175,0.32)" : "rgba(107,114,128,0.35)",
        showspikes: !compactHover,
        spikemode: "across",
        spikecolor: dark ? "rgba(156,163,175,0.45)" : "rgba(107,114,128,0.45)",
        spikedash: "dot",
        spikethickness: 1,
        fixedrange: true
      },
      yaxis: {
        title: "지지율(%)",
        titlefont: { size: 14 },
        tickfont: { size: 14 },
        gridcolor: dark ? "rgba(156,163,175,0.22)" : "rgba(107,114,128,0.20)",
        zeroline: false,
        fixedrange: true
      },
      legend: {
        orientation: "h",
        x: 0,
        xanchor: "left",
        y: 1.14,
        yanchor: "bottom",
        bgcolor: dark ? "rgba(22,25,31,0.96)" : "rgba(247,249,251,0.96)",
        bordercolor: dark ? "#2A2E37" : "#E1E5EB",
        borderwidth: 1,
        font: { size: 14 }
      }
    };
  }

  function getIntroRange() {
    let end = null;
    tracesData.forEach((p) => {
      if (p.pred_x) {
        const d = new Date(p.pred_x);
        if (!Number.isNaN(d.getTime()) && (!end || d > end)) end = d;
      }
    });
    if (!end) return null;
    const start = new Date(end);
    start.setMonth(start.getMonth() - 3);
    const introEnd = new Date(start);
    introEnd.setDate(introEnd.getDate() + 14);
    if (introEnd >= end) return { start, introEnd: new Date(end), end };
    return { start, introEnd, end };
  }

  function animateSeriesRevealOnce() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const range = getIntroRange();
    if (!range) return;
    const startMs = range.start.getTime();
    const introMs = range.introEnd.getTime();
    const endMs = range.end.getTime();
    if (!Number.isFinite(startMs) || !Number.isFinite(introMs) || !Number.isFinite(endMs)) return;
    if (startMs >= introMs || introMs > endMs) return;

    Plotly.relayout(chartDiv, { "xaxis.range": [range.start, range.introEnd] }).then(() => {
      Plotly.animate(
        chartDiv,
        { layout: { "xaxis.range": [range.start, range.end] } },
        {
          transition: { duration: 950, easing: "cubic-in-out" },
          frame: { duration: 950, redraw: false },
          mode: "immediate"
        }
      );
    });
  }

  function renderChart() {
    return Plotly.react(chartDiv, buildTraces(), buildLayout(), {
      displayModeBar: false,
      responsive: true,
      scrollZoom: false,
      doubleClick: false
    });
  }

  function syncChartHeightToRanking() {
    const left = document.querySelector(".main-grid > article.panel.chart-panel");
    const right = document.querySelector(".main-grid > aside.panel");
    if (!left || !right) return;
    const nonChartHeight = left.offsetHeight - chartDiv.offsetHeight;
    const target = right.offsetHeight - nonChartHeight;
    if (Number.isFinite(target) && target > 420) {
      chartDiv.style.height = `${Math.round(target)}px`;
    }
  }

  function bindMainChartHoverEmphasis() {
    if (!chartDiv || chartDiv.dataset.hoverEmphasisBound === "1" || isTouchDevice()) return;
    chartDiv.dataset.hoverEmphasisBound = "1";
    const HOVER_DISTANCE_THRESHOLD = 24;
    const HOVER_DISTANCE_AMBIGUITY_PX = 3;
    const baseLineWidths = (chartDiv.data || []).map((t) => {
      const w = t && t.line ? Number(t.line.width) : NaN;
      return Number.isFinite(w) ? w : null;
    });

    function restore() {
      const data = chartDiv.data || [];
      Plotly.restyle(chartDiv, {
        opacity: data.map(() => 1),
        "line.width": baseLineWidths
      });
    }

    chartDiv.on("plotly_hover", (ev) => {
      const candidates = (ev && Array.isArray(ev.points) ? ev.points : [])
        .filter((p) => {
          const t = (chartDiv.data || [])[p.curveNumber];
          return !!(t && t.legendgroup && t.meta !== "band" && String(t.mode || "").includes("lines"));
        })
        .sort((a, b) => {
          const da = Number.isFinite(a.distance) ? a.distance : Number.POSITIVE_INFINITY;
          const db = Number.isFinite(b.distance) ? b.distance : Number.POSITIVE_INFINITY;
          return da - db;
        });
      const point = candidates[0] || null;
      if (!point || typeof point.curveNumber !== "number") return;
      const bestDistance = Number.isFinite(point.distance) ? point.distance : Number.POSITIVE_INFINITY;
      const secondDistance = candidates.length > 1 && Number.isFinite(candidates[1].distance)
        ? candidates[1].distance
        : Number.POSITIVE_INFINITY;
      const ambiguousByDistance = Number.isFinite(secondDistance)
        && Math.abs(secondDistance - bestDistance) < HOVER_DISTANCE_AMBIGUITY_PX;
      if (
        (candidates.length > 1 && !Number.isFinite(point.distance))
        || bestDistance > HOVER_DISTANCE_THRESHOLD
        || ambiguousByDistance
      ) {
        restore();
        return;
      }
      const sourceTrace = (chartDiv.data || [])[point.curveNumber];
      if (!sourceTrace || !sourceTrace.legendgroup) return;
      const activeGroup = sourceTrace.legendgroup;
      const data = chartDiv.data || [];
      const opacities = data.map((t) => (t && t.legendgroup === activeGroup ? 1 : 0.2));
      const boostedWidths = data.map((t, idx) => {
        const base = baseLineWidths[idx];
        if (base === null) return null;
        const same = t && t.legendgroup === activeGroup;
        const isBand = t && t.meta === "band";
        const isLine = t && String(t.mode || "").includes("lines");
        if (same && !isBand && isLine) return base + 1;
        return base;
      });
      Plotly.restyle(chartDiv, { opacity: opacities, "line.width": boostedWidths });
    });

    chartDiv.on("plotly_unhover", restore);
  }

  function renderAndSync() {
    syncChartHeightToRanking();
    const shouldAnimate = !chartDiv.dataset.animated;
    const renderPromise = renderChart();
    if (renderPromise && typeof renderPromise.then === "function") {
      renderPromise.then(() => {
        bindMainChartHoverEmphasis();
        if (shouldAnimate) {
          animateSeriesRevealOnce();
          chartDiv.dataset.animated = "1";
        }
        Plotly.Plots.resize(chartDiv);
      });
      return;
    }
    if (shouldAnimate) {
      animateSeriesRevealOnce();
      chartDiv.dataset.animated = "1";
    }
    bindMainChartHoverEmphasis();
    Plotly.Plots.resize(chartDiv);
  }

  renderAndSync();
  window.addEventListener("resize", renderAndSync);
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", renderAndSync);
    else if (mq.addListener) mq.addListener(renderAndSync);
  }

  if (isTouchDevice()) {
    chartDiv.addEventListener("touchend", () => {
      setTimeout(() => Plotly.Fx.unhover(chartDiv), 0);
    }, { passive: true });
  }

  const rangeBtns = [...document.querySelectorAll(".fbtn[data-range]")];
  const bandBtn = document.getElementById("toggle-band");
  const hiddenParties = new Set();
  let showBands = true;

  function applyPartyVisibility() {
    const vis = chartDiv.data.map((t) => {
      if (hiddenParties.has(t.legendgroup)) return "legendonly";
      if (!showBands && t.meta === "band") return "legendonly";
      return true;
    });
    Plotly.restyle(chartDiv, { visible: vis });
    document.querySelectorAll(".rank-card").forEach((c) => {
      c.classList.toggle("muted", hiddenParties.has(c.dataset.party));
    });
  }

  function setBtnActive(key) {
    rangeBtns.forEach((b) => {
      const active = b.dataset.range === key;
      b.classList.toggle("active", active);
      b.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }
  function endDate() {
    let d = null;
    tracesData.forEach((p) => {
      const t = new Date(p.pred_x);
      if (!d || t > d) d = t;
    });
    return d;
  }
  function dateShift(base, months) {
    const d = new Date(base);
    d.setMonth(d.getMonth() - months);
    return d;
  }

  rangeBtns.forEach((btn) => {
    if (btn.dataset.range !== "reset") {
      btn.setAttribute("role", "button");
      btn.setAttribute("aria-pressed", btn.classList.contains("active") ? "true" : "false");
    }
    btn.addEventListener("click", () => {
      const key = btn.dataset.range;
      if (key === "reset") {
        hiddenParties.clear();
        applyPartyVisibility();
        document.querySelectorAll(".rank-card").forEach((c) => c.classList.remove("active", "muted"));
        return;
      }
      setBtnActive(key);
      const e = endDate();
      if (key === "all") {
        Plotly.relayout(chartDiv, { "xaxis.autorange": true });
        return;
      }
      const start = key === "3m" ? dateShift(e, 3) : (key === "6m" ? dateShift(e, 6) : dateShift(e, 12));
      Plotly.relayout(chartDiv, { "xaxis.range": [start, e] });
    });
  });

  if (bandBtn) {
    bandBtn.setAttribute("aria-pressed", "true");
    bandBtn.addEventListener("click", () => {
      showBands = !showBands;
      bandBtn.classList.toggle("active", showBands);
      bandBtn.textContent = showBands ? "오차 범위 표시: 켜짐" : "오차 범위 표시: 꺼짐";
      bandBtn.setAttribute("aria-pressed", showBands ? "true" : "false");
      applyPartyVisibility();
    });
  }

  const rankCards = [...document.querySelectorAll(".rank-card")];
  rankCards.forEach((card) => {
    card.addEventListener("click", () => {
      const party = card.dataset.party;
      if (hiddenParties.has(party)) hiddenParties.delete(party);
      else hiddenParties.add(party);
      applyPartyVisibility();
      card.classList.toggle("active", !hiddenParties.has(party));
    });
  });

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[ch]));
  }

  function renderLatestPollSection() {
    const section = document.getElementById("latest-poll-section");
    if (!section) return;
    if (!Array.isArray(latestPollResults) || !latestPollResults.length) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";

    const listEl = document.getElementById("latest-poll-list");
    if (listEl) {
      listEl.innerHTML = latestPollResults.slice(0, 6).map((row) => {
        const sourceUrl = esc(row.source_url || "");
        const pColor = esc(getPollsterColor(row.pollster || ""));
        const valueLines = (row.parties || [])
          .map((p) => `${esc(p.display_party || p.party)} ${Number(p.value).toFixed(1)}%`)
          .join(" · ");
        return `
          <article class="latest-poll-card">
            <div class="latest-poll-head">
              <div class="latest-poll-pollster"><span class="pollster-chip" style="background:${pColor};"></span>${esc(row.pollster || "-")}</div>
              <div class="latest-poll-date">${esc(row.date_end || "")}</div>
            </div>
            <div class="latest-poll-values">${valueLines}</div>
            ${sourceUrl ? `<a class="latest-poll-source link-out" href="${sourceUrl}" target="_blank" rel="noopener noreferrer">기사 링크</a>` : `<div class="latest-poll-source">출처 없음</div>`}
          </article>
        `;
      }).join("");
    }

    const chartEl = document.getElementById("latest-poll-chart");
    if (!chartEl) return;
    const top = latestPollResults[0] || {};
    const pieRows = (top.parties || []).filter((p) => Number.isFinite(Number(p.value)) && Number(p.value) > 0);
    const labels = pieRows.map((p) => p.display_party || p.party);
    const values = pieRows.map((p) => Number(p.value));
    const colors = pieRows.map((p) => partyColorMap[p.party] || "#94A3B8");
    const dark = isDarkMode();
    Plotly.react(
      chartEl,
      [
        {
          type: "pie",
          labels,
          values,
          hole: 0.42,
          showlegend: false,
          sort: false,
          textinfo: "label",
          marker: { colors, line: { color: dark ? "#1B2638" : "#FFFFFF", width: 1 } },
          hovertemplate: "<b>%{label}</b>: %{value:.1f}%<extra></extra>",
        }
      ],
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: dark ? "#152338" : "#F8FAFD",
        margin: { l: 20, r: 20, t: 52, b: 20 },
        font: { color: dark ? "#EAF0FA" : "#1A2332", family: "Inter, Pretendard, sans-serif" },
        title: {
          text: `${top.pollster || "최신 조사"} · ${top.date_end || ""}`,
          x: 0,
          xanchor: "left",
          font: { size: 13 }
        },
      },
      { displayModeBar: false, responsive: true }
    );
  }

  function renderForecastComparisonSection() {
    const section = document.getElementById("poll-compare-section");
    if (!section) return;
    if (!Array.isArray(latestPollResults) || !latestPollResults.length || !Array.isArray(tracesData) || !tracesData.length) {
      section.style.display = "none";
      return;
    }
    const top = latestPollResults[0] || {};
    const forecastMap = {};
    tracesData.forEach((t) => {
      if (t && t.party && Number.isFinite(Number(t.pred_y))) {
        forecastMap[t.party] = Number(t.pred_y);
      }
    });
    const rows = (top.parties || [])
      .map((p) => {
        const latest = Number(p.value);
        const pred = forecastMap[p.party];
        if (!Number.isFinite(latest) || !Number.isFinite(pred)) return null;
        return {
          party: p.party,
          display_party: p.display_party || p.party,
          latest,
          pred,
          delta: latest - pred,
          color: partyColorMap[p.party] || "#94A3B8",
        };
      })
      .filter(Boolean)
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

    if (!rows.length) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";

    const listEl = document.getElementById("poll-compare-list");
    if (listEl) {
      listEl.innerHTML = rows.map((r) => {
        const sign = r.delta > 0 ? "+" : "";
        const deltaColor = r.delta >= 0 ? "#0F9D58" : "#D83A3A";
        return `
          <article class="poll-compare-card">
            <div class="poll-compare-head">
              <div class="poll-compare-party">${esc(r.display_party || r.party)}</div>
              <div class="poll-compare-delta" style="color:${deltaColor}">${sign}${r.delta.toFixed(1)}%p</div>
            </div>
            <div class="poll-compare-meta">최신 ${r.latest.toFixed(1)}% · 예측 ${r.pred.toFixed(1)}%</div>
          </article>
        `;
      }).join("");
    }

    const chartEl = document.getElementById("poll-compare-chart");
    if (!chartEl) return;
    const dark = isDarkMode();
    const sorted = rows.slice().reverse();
    const labels = sorted.map((r) => r.display_party || r.party);

    const traces = [];
    sorted.forEach((r) => {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: [r.pred, r.latest],
        y: [r.display_party || r.party, r.display_party || r.party],
        line: { color: dark ? "rgba(234,240,250,0.35)" : "rgba(26,35,50,0.28)", width: 3 },
        hoverinfo: "skip",
        showlegend: false,
      });
    });
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "예측치",
      x: sorted.map((r) => r.pred),
      y: labels,
      marker: {
        size: 9,
        color: sorted.map((r) => r.color),
        symbol: "circle-open",
        line: { width: 2, color: sorted.map((r) => r.color) },
      },
      hovertemplate: "<b>%{y}</b><br>예측: %{x:.1f}%<extra></extra>",
    });
    traces.push({
      type: "scatter",
      mode: "markers+text",
      name: "최신 조사",
      x: sorted.map((r) => r.latest),
      y: labels,
      marker: {
        size: 10,
        color: sorted.map((r) => r.color),
        symbol: "diamond",
        line: { width: 1, color: dark ? "#EAF0FA" : "#FFFFFF" },
      },
      text: sorted.map((r) => {
        const d = r.delta;
        return `${d > 0 ? "+" : ""}${d.toFixed(1)}%p`;
      }),
      textposition: "middle right",
      textfont: { size: 11, color: dark ? "#EAF0FA" : "#1A2332" },
      hovertemplate: "<b>%{y}</b><br>최신: %{x:.1f}%<extra></extra>",
    });

    Plotly.react(
      chartEl,
      traces,
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: dark ? "#152338" : "#F8FAFD",
        margin: { l: 90, r: 20, t: 20, b: 34 },
        font: { color: dark ? "#EAF0FA" : "#1A2332", family: "Inter, Pretendard, sans-serif" },
        xaxis: {
          title: "지지율(%)",
          zeroline: true,
          zerolinecolor: dark ? "rgba(234,240,250,0.5)" : "rgba(26,35,50,0.5)",
          gridcolor: dark ? "rgba(158,176,204,0.16)" : "rgba(71,85,105,0.18)",
        },
        yaxis: { automargin: true, categoryorder: "array", categoryarray: labels },
        legend: { orientation: "h", x: 0, y: 1.08, xanchor: "left" },
      },
      { displayModeBar: false, responsive: true }
    );

    if (chartEl.dataset.hoverEmphasisBound === "1" || isTouchDevice()) return;
    chartEl.dataset.hoverEmphasisBound = "1";
    const restore = () => {
      const data = chartEl.data || [];
      const traceOpacity = data.map(() => 1);
      const markerOpacity = data.map((t) => (t && t.marker ? 1 : null));
      Plotly.restyle(chartEl, { opacity: traceOpacity, "marker.opacity": markerOpacity });
    };
    chartEl.on("plotly_hover", (ev) => {
      const point = ev && Array.isArray(ev.points) ? ev.points[0] : null;
      const selectedLabel = point ? String(point.y || "") : "";
      if (!selectedLabel) return;
      const data = chartEl.data || [];
      const traceOpacity = data.map((t) => {
        const rowLabel = Array.isArray(t.y) && t.y.length === 2 && t.y[0] === t.y[1] ? String(t.y[0]) : "";
        if (!rowLabel) return 1;
        return rowLabel === selectedLabel ? 1 : 0.2;
      });
      const markerOpacity = data.map((t) => {
        if (!t || !t.marker || !Array.isArray(t.y)) return null;
        return t.y.map((label) => (String(label) === selectedLabel ? 1 : 0.25));
      });
      Plotly.restyle(chartEl, { opacity: traceOpacity, "marker.opacity": markerOpacity });
    });
    chartEl.on("plotly_unhover", restore);
  }

  function parseRss(xmlText) {
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");
    const items = [...doc.querySelectorAll("item")];
    const rows = items.map((it) => {
      const title = (it.querySelector("title")?.textContent || "").trim();
      const link = (it.querySelector("link")?.textContent || "").trim();
      const desc = (it.querySelector("description")?.textContent || "").trim();
      const pubDateRaw = (it.querySelector("pubDate")?.textContent || "").trim();
      const source = (it.querySelector("source")?.textContent || "Google News").trim();
      const dt = pubDateRaw ? new Date(pubDateRaw) : null;
      return {
        title,
        link,
        desc,
        source,
        date: dt && !isNaN(dt.getTime()) ? dt : null
      };
    }).filter((r) => r.title && r.link);
    rows.sort((a, b) => (b.date ? b.date.getTime() : 0) - (a.date ? a.date.getTime() : 0));
    return rows;
  }

  function stripHtml(s) {
    return String(s || "").replace(/<[^>]*>/g, " ");
  }

  function parseNewsDate(row) {
    const raw = row && (row.published_at || row.date);
    if (!raw) return null;
    const dt = new Date(raw);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }

  function formatRelative(dt) {
    if (!dt) return "";
    const diffMs = Date.now() - dt.getTime();
    if (!Number.isFinite(diffMs) || diffMs < 0) return dt.toLocaleDateString("ko-KR");
    const min = Math.floor(diffMs / 60000);
    if (min < 1) return "방금 전";
    if (min < 60) return `${min}분 전`;
    const hour = Math.floor(min / 60);
    if (hour < 24) return `${hour}시간 전`;
    const day = Math.floor(hour / 24);
    return `${day}일 전`;
  }

  async function fetchViaCandidates(rssUrl) {
    const candidates = [
      `https://api.allorigins.win/raw?url=${encodeURIComponent(rssUrl)}`,
      `https://api.allorigins.win/get?url=${encodeURIComponent(rssUrl)}`,
      `https://r.jina.ai/http://${rssUrl.replace(/^https?:\/\//, "")}`
    ];
    for (const u of candidates) {
      try {
        const res = await fetch(u, { cache: "no-store" });
        if (!res.ok) continue;
        const text = await res.text();
        if (!text) continue;
        if (u.includes("/get?url=")) {
          const j = JSON.parse(text);
          const contents = j && j.contents ? String(j.contents) : "";
          if (contents.includes("<item>")) return contents;
        } else if (text.includes("<item>")) {
          return text;
        }
      } catch (_) {}
    }
    return "";
  }

  async function fetchRecentPollNews() {
    const grid = document.getElementById("news-grid");
    const status = document.getElementById("news-status");
    if (!grid) return;
    function setStatus(text, tone) {
      if (!status) return;
      status.textContent = text;
      status.classList.remove("fresh", "stale", "old");
      if (tone) status.classList.add(tone);
    }

    const phrase = "중앙선거여론조사심의위원회";
    setStatus("기사 목록 불러오는 중...", "stale");

    // Primary: same-origin static JSON generated at build time.
    try {
      const local = await fetch("news_latest.json", { cache: "no-store" });
      if (local.ok) {
        const rows = await local.json();
        if (Array.isArray(rows) && rows.length) {
          const sorted = rows
            .map((r) => ({ ...r, _dt: parseNewsDate(r) }))
            .sort((a, b) => (b._dt ? b._dt.getTime() : 0) - (a._dt ? a._dt.getTime() : 0));
          grid.innerHTML = sorted.slice(0, 6).map((r) => `
            <a class="news-card link-out" href="${esc(r.url || "")}" target="_blank" rel="noopener noreferrer">
              <div class="news-date">${esc(formatRelative(r._dt) || (r.date || ""))}</div>
              <div class="news-title">${esc(r.title || "")}</div>
              <div class="news-source">${esc(r.source || "출처")}</div>
            </a>
          `).join("");
          setStatus(`자동 갱신 완료 (${Math.min(sorted.length, 6)}건)`, "fresh");
          return;
        }
        if (Array.isArray(rows) && rows.length === 0) {
          setStatus("조건에 맞는 최신 기사 없음", "stale");
          return;
        }
      }
    } catch (_) {}

    const debugProxy = new URLSearchParams(window.location.search).get("newsProxy") === "1";
    if (!debugProxy) {
      setStatus("빌드 시점 수집 데이터 표시 중", "stale");
      return;
    }

    // Debug-only fallback path (disabled by default)
    const qStrict = encodeURIComponent(`"${phrase}"`);
    const qBroad = encodeURIComponent(`${phrase} 여론조사`);
    const rssStrict = `https://news.google.com/rss/search?q=${qStrict}&hl=ko&gl=KR&ceid=KR:ko`;
    const rssBroad = `https://news.google.com/rss/search?q=${qBroad}&hl=ko&gl=KR&ceid=KR:ko`;
    let xmlText = await fetchViaCandidates(rssStrict);
    if (!xmlText) xmlText = await fetchViaCandidates(rssBroad);
    if (!xmlText) {
      setStatus("디버그 프록시 로딩 실패(정적 데이터 유지)", "old");
      return;
    }
    const rows = parseRss(xmlText).filter((r) => stripHtml(r.title + " " + r.desc).includes(phrase)).slice(0, 6);
    if (!rows.length) {
      setStatus("디버그 프록시 결과 없음(정적 데이터 유지)", "old");
      return;
    }
    grid.innerHTML = rows.map((r) => {
      const d = r.date && !Number.isNaN(r.date.getTime()) ? formatRelative(r.date) : "";
      return `<a class="news-card link-out" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer"><div class="news-date">${esc(d)}</div><div class="news-title">${esc(r.title)}</div><div class="news-source">${esc(r.source)}</div></a>`;
    }).join("");
    setStatus(`디버그 프록시 갱신 (${rows.length}건)`, "fresh");
  }

  fetchRecentPollNews();
  renderLatestPollSection();
  renderForecastComparisonSection();
})();
