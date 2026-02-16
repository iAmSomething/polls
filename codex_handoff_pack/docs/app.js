(function () {
  const dataEl = document.getElementById("poll-data");
  if (!dataEl) return;
  const payload = JSON.parse(dataEl.textContent);
  const tracesData = payload.traces || [];
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
    return out;
  }

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.02)",
    font: { color: "#E6ECF5", family: "Inter, Pretendard, sans-serif" },
    margin: { l: 55, r: 20, t: 10, b: 44 },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "#0B1F3A",
      bordercolor: "#8FB3FF",
      font: { color: "#F7FAFF", size: 14, family: "Inter, Pretendard, sans-serif" },
      align: "left",
      namelength: -1
    },
    xaxis: {
      gridcolor: "rgba(255,255,255,0.08)",
      linecolor: "rgba(255,255,255,0.12)",
      showspikes: true,
      spikemode: "across",
      spikecolor: "rgba(255,255,255,0.35)",
      spikedash: "dot",
      spikethickness: 1
    },
    yaxis: { title: "지지율(%)", gridcolor: "rgba(255,255,255,0.08)", zeroline: false },
    legend: { orientation: "h", y: 1.08, x: 0 }
  };

  Plotly.newPlot(chartDiv, buildTraces(), layout, { displayModeBar: false, responsive: true });

  const fbtns = [...document.querySelectorAll(".fbtn")];
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
        const op = chartDiv.data.map(() => 1);
        Plotly.restyle(chartDiv, "opacity", op);
        document.querySelectorAll(".rank-card").forEach((c) => c.classList.remove("active"));
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
      const op = chartDiv.data.map((t) => (t.legendgroup === party ? 1 : 0.15));
      Plotly.restyle(chartDiv, "opacity", op);
      rankCards.forEach((c) => c.classList.toggle("active", c.dataset.party === party));
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
      }
    } catch (_) {}

    const qStrict = encodeURIComponent(`"${phrase}"`);
    const qBroad = encodeURIComponent(`${phrase} 여론조사`);
    const rssStrict = `https://news.google.com/rss/search?q=${qStrict}&hl=ko&gl=KR&ceid=KR:ko`;
    const rssBroad = `https://news.google.com/rss/search?q=${qBroad}&hl=ko&gl=KR&ceid=KR:ko`;

    let xmlText = await fetchViaCandidates(rssStrict);
    if (!xmlText) xmlText = await fetchViaCandidates(rssBroad);
    if (!xmlText) {
      if (status) status.textContent = "자동 기사 로딩 실패(프록시 차단 가능). 잠시 후 새로고침 해주세요.";
      return;
    }

    const rows = parseRss(xmlText)
      .filter((r) => stripHtml(r.title + " " + r.desc).includes(phrase))
      .slice(0, 6);
    if (!rows.length) {
      if (status) status.textContent = "조건에 맞는 최신 기사가 없습니다.";
      return;
    }

    grid.innerHTML = rows.map((r) => {
      const d = r.date ? r.date.toISOString().slice(0, 10) : "";
      return `
        <a class="news-card" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer">
          <div class="news-date">${esc(d)}</div>
          <div class="news-title">${esc(r.title)}</div>
          <div class="news-source">${esc(r.source)}</div>
        </a>
      `;
    }).join("");
    if (status) status.textContent = `자동 갱신 완료 (${rows.length}건)`;
  }

  fetchRecentPollNews();
})();
