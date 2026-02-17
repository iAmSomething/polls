(function () {
  const dataEl = document.getElementById("poll-data");
  if (!dataEl) return;
  const payload = JSON.parse(dataEl.textContent);
  const tracesData = payload.traces || [];
  const presidentRaw = payload.president_raw || {};
  const chartDiv = document.getElementById("chart");
  if (!chartDiv) return;

  function buildTraces() {
    const out = [];
    tracesData.forEach((p) => {
      out.push({
        x: p.actual_x, y: p.actual_y, type: "scatter", mode: "lines", name: p.party,
        legendgroup: p.party, line: { color: p.color, width: 2.7 },
        hovertemplate: "<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>"
      });
      out.push({
        x: p.forecast_x, y: p.forecast_y, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, line: { color: p.color, width: 2.2, dash: "dot" },
        hoverinfo: "skip"
      });
      out.push({
        x: [p.pred_x], y: [p.pred_y], type: "scatter", mode: "markers+text",
        legendgroup: p.party, showlegend: false,
        marker: { color: p.color, size: 10, line: { color: "#DDE8FF", width: 1 } },
        text: ["예측치"], textposition: "middle right", textfont: { color: p.color, size: 11 },
        customdata: [[p.pred_lo_80, p.pred_hi_80]],
        hovertemplate: "<b>%{fullData.legendgroup} 예측</b><br>%{y:.2f}%<br>80% 구간: %{customdata[0]:.2f}% ~ %{customdata[1]:.2f}%<extra></extra>"
      });
    });
    if (Array.isArray(presidentRaw.x) && presidentRaw.x.length) {
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
      plot_bgcolor: dark ? "#152338" : "#F8FAFD",
      font: { color: dark ? "#EAF0FA" : "#1A2332", family: "Inter, Pretendard, sans-serif" },
      margin: { l: 55, r: 20, t: 72, b: 44 },
      hovermode: compactHover ? "closest" : "x unified",
      dragmode: "pan",
      hoverlabel: {
        bgcolor: dark ? "#111A2B" : "#FFFFFF",
        bordercolor: "#8FB3FF",
        font: { color: dark ? "#EAF0FA" : "#1A2332", size: compactHover ? 11 : 13, family: "Inter, Pretendard, sans-serif" },
        align: "left",
        namelength: compactHover ? 32 : -1
      },
      xaxis: {
        gridcolor: dark ? "rgba(158,176,204,0.16)" : "rgba(71,85,105,0.18)",
        linecolor: dark ? "rgba(158,176,204,0.24)" : "rgba(100,116,139,0.35)",
        showspikes: !compactHover,
        spikemode: "across",
        spikecolor: dark ? "rgba(158,176,204,0.5)" : "rgba(71,85,105,0.5)",
        spikedash: "dot",
        spikethickness: 1,
        fixedrange: true
      },
      yaxis: {
        title: "지지율(%)",
        gridcolor: dark ? "rgba(158,176,204,0.16)" : "rgba(71,85,105,0.18)",
        zeroline: false,
        fixedrange: true
      },
      legend: {
        orientation: "h",
        x: 0,
        xanchor: "left",
        y: 1.02,
        yanchor: "bottom"
      }
    };
  }

  function renderChart() {
    Plotly.react(chartDiv, buildTraces(), buildLayout(), {
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

  function renderAndSync() {
    syncChartHeightToRanking();
    renderChart();
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

  const fbtns = [...document.querySelectorAll(".fbtn")];
  const hiddenParties = new Set();

  function applyPartyVisibility() {
    const vis = chartDiv.data.map((t) => (hiddenParties.has(t.legendgroup) ? "legendonly" : true));
    Plotly.restyle(chartDiv, { visible: vis });
    document.querySelectorAll(".rank-card").forEach((c) => {
      c.classList.toggle("muted", hiddenParties.has(c.dataset.party));
    });
  }

  function setBtnActive(key) { fbtns.forEach((b) => b.classList.toggle("active", b.dataset.range === key)); }
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

  fbtns.forEach((btn) => {
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

    const phrase = "중앙선거여론조사심의위원회";
    if (status) status.textContent = "기사 목록 불러오는 중...";

    // Primary: same-origin static JSON generated at build time.
    try {
      const local = await fetch("news_latest.json", { cache: "no-store" });
      if (local.ok) {
        const rows = await local.json();
        if (Array.isArray(rows) && rows.length) {
          grid.innerHTML = rows.slice(0, 6).map((r) => `
            <a class="news-card" href="${esc(r.url || "")}" target="_blank" rel="noopener noreferrer">
              <div class="news-date">${esc(r.date || "")}</div>
              <div class="news-title">${esc(r.title || "")}</div>
              <div class="news-source">${esc(r.source || "출처")}</div>
            </a>
          `).join("");
          if (status) status.textContent = `자동 갱신 완료 (${Math.min(rows.length, 6)}건)`;
          return;
        }
        if (Array.isArray(rows) && rows.length === 0) {
          if (status) status.textContent = "조건에 맞는 최신 기사 없음";
          return;
        }
      }
    } catch (_) {}

    const debugProxy = new URLSearchParams(window.location.search).get("newsProxy") === "1";
    if (!debugProxy) {
      if (status) status.textContent = "빌드 시점 수집 데이터 표시 중";
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
      if (status) status.textContent = "디버그 프록시 로딩 실패(정적 데이터 유지)";
      return;
    }
    const rows = parseRss(xmlText).filter((r) => stripHtml(r.title + " " + r.desc).includes(phrase)).slice(0, 6);
    if (!rows.length) {
      if (status) status.textContent = "디버그 프록시 결과 없음(정적 데이터 유지)";
      return;
    }
    grid.innerHTML = rows.map((r) => {
      const d = r.date ? r.date.toISOString().slice(0, 10) : "";
      return `<a class="news-card" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer"><div class="news-date">${esc(d)}</div><div class="news-title">${esc(r.title)}</div><div class="news-source">${esc(r.source)}</div></a>`;
    }).join("");
    if (status) status.textContent = `디버그 프록시 갱신 (${rows.length}건)`;
  }

  fetchRecentPollNews();
})();
