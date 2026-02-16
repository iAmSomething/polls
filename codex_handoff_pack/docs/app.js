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
        hovertemplate: "%{fullData.name}: %{y:.2f}%<extra></extra>"
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
        hoverinfo: "skip"
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
    xaxis: { gridcolor: "rgba(255,255,255,0.08)", linecolor: "rgba(255,255,255,0.12)" },
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
})();
