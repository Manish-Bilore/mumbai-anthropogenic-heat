/* Shared helpers for the Mumbai heat story (/) and viewer (/map/).
   Tile fields are y{year}_h{NN}; hNN is the hour ENDING (NN+1):00 IST
   (see scripts/14_export_diurnal.py). */
window.HEAT = (() => {
  const YEARS = [2026, 2030, 2035, 2040];
  const pad = (n) => String(n).padStart(2, "0");
  const field = (y, i) => `y${y}_h${pad(i)}`;
  const hourEnd = (i) => `${pad(i + 1)}:00`;
  const hourSpan = (i) => `${pad(i)}:00–${pad(i + 1)}:00`;
  const PEAK = 17; // hour ending 18:00

  // Q_f, W/m². Skewed (median ~30, p99 ~150 at peak), so breaks are roughly geometric.
  // Multi-hue, lightness falls steadily: pale lavender-blue (little), periwinkle, purple, magenta, crimson, deep red (a lot).
  const RAMP_QF = [[0, "rgba(246,243,238,0)"], [0.5, "#e8e8f4"], [5, "#bcbde9"], [15, "#8c86d6"],
                   [30, "#8a4fb0"], [50, "#a8367f"], [80, "#b8263f"], [150, "#8c1020"]];
  // ΔQ_f since 2026, W/m²
  const RAMP_DQ = [[0, "rgba(246,243,238,0)"], [0.25, "#e8e8f4"], [1, "#bcbde9"], [3, "#8c86d6"],
                   [6, "#8a4fb0"], [12, "#a8367f"], [25, "#b8263f"], [60, "#8c1020"]];

  function rampExpr(ramp, valueExpr) {
    const e = ["interpolate", ["linear"], valueExpr];
    ramp.forEach(([v, c]) => e.push(v, c));
    return e;
  }
  const qfExpr = (y, i) => rampExpr(RAMP_QF, ["coalesce", ["get", field(y, i)], 0]);
  const dqExpr = (y, i) => rampExpr(RAMP_DQ,
    ["-", ["coalesce", ["get", field(y, i)], 0], ["coalesce", ["get", field(2026, i)], 0]]);

  // Year identity is ordinal, so it borrows the heat ramp: later = hotter.
  const YEAR_LIGHT = { 2026: "#8c86d6", 2030: "#8a4fb0", 2035: "#a8367f", 2040: "#b8263f" };
  const YEAR_DARK = YEAR_LIGHT; // kept as an alias; the site is light-themed

  const PLACES = [
    // [name, lon, lat, minZoom, kind]
    ["Colaba", 72.8156, 18.9067, 10.4],
    ["Fort", 72.8347, 18.9340, 11.6],
    ["Byculla", 72.8333, 18.9790, 11.6],
    ["Worli", 72.8170, 19.0130, 10.8],
    ["Lower Parel", 72.8300, 18.9965, 11.8],
    ["Dadar", 72.8430, 19.0190, 10.4],
    ["Dharavi", 72.8540, 19.0410, 11.4],
    ["Bandra", 72.8360, 19.0600, 10.4],
    ["BKC", 72.8650, 19.0660, 11.4],
    ["Kurla", 72.8820, 19.0720, 10.8],
    ["Chembur", 72.8990, 19.0560, 10.4],
    ["Ghatkopar", 72.9100, 19.0860, 10.8],
    ["Santacruz", 72.8420, 19.0810, 11.6],
    ["Airport", 72.8679, 19.0930, 11.4],
    ["Andheri", 72.8460, 19.1190, 10.4],
    ["Powai", 72.9050, 19.1200, 10.4],
    ["Vikhroli", 72.9300, 19.1080, 11.4],
    ["Goregaon", 72.8490, 19.1640, 10.8],
    ["Malad", 72.8480, 19.1870, 11.2],
    ["Kandivali", 72.8500, 19.2060, 11.4],
    ["Borivali", 72.8570, 19.2300, 10.4],
    ["Bhandup", 72.9380, 19.1440, 11.2],
    ["Mulund", 72.9560, 19.1720, 10.4],
    ["Aarey", 72.8790, 19.1560, 10.8, "green"],
    ["Sanjay Gandhi National Park", 72.9050, 19.2150, 10.2, "green"],
  ];

  function addPlaces(map, maplibregl) {
    const markers = PLACES.map(([name, lon, lat, minZ, kind]) => {
      const el = document.createElement("div");
      el.className = "place-label" + (kind ? " " + kind : "");
      el.textContent = name;
      el.setAttribute("aria-hidden", "true");
      const m = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([lon, lat]).addTo(map);
      return { el, minZ };
    });
    const sync = () => {
      const z = map.getZoom();
      markers.forEach(({ el, minZ }) => { el.style.opacity = z >= minZ ? 1 : 0; });
    };
    map.on("zoom", sync); sync();
    return { setVisible(v) { markers.forEach(({ el }) => { el.style.visibility = v ? "visible" : "hidden"; }); } };
  }

  // ---------- diurnal chart (SVG, no library) ----------
  // series: [{id, label, values[24], color, width, dash, opacity}]
  // x position for index i is hour-ending i+1, so the axis reads 1..24.
  let tipEl;
  function tip() {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "chart-tip"; document.body.appendChild(tipEl); }
    return tipEl;
  }

  function diurnal(container, opts = {}) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "dchart");
    svg.setAttribute("role", "img");
    container.appendChild(svg);
    const M = Object.assign({ l: 30, r: 10, t: 10, b: 20 }, opts.margin || {});
    let state = { series: [], hour: PEAK, yMax: null, marks: [] };
    let W = 300, H = 120;

    const x = (i) => M.l + (i / 23) * (W - M.l - M.r);
    const idxFromX = (px) => Math.max(0, Math.min(23, Math.round(((px - M.l) / (W - M.l - M.r)) * 23)));
    const yMax = () => state.yMax || Math.ceil(Math.max(10, ...state.series.flatMap((s) => s.values)) / 10) * 10;
    const y = (v) => H - M.b - (v / yMax()) * (H - M.t - M.b);

    function render() {
      const r = container.getBoundingClientRect();
      W = Math.max(160, r.width); H = Math.max(70, r.height);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      const ym = yMax();
      const step = ym > 60 ? 20 : 10;
      let g = `<g class="grid">`;
      for (let v = 0; v <= ym; v += step) g += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/>`;
      g += `</g><g class="axis">`;
      for (let v = 0; v <= ym; v += step) g += `<text x="${M.l - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text>`;
      [0, 6, 12, 18, 24].forEach((h) => {
        const i = Math.max(0, h - 1);
        g += `<text x="${x(i)}" y="${H - 4}" text-anchor="middle">${pad(h)}</text>`;
      });
      g += `</g>`;
      (state.marks || []).forEach((m) => {
        g += `<line x1="${x(m.i)}" x2="${x(m.i)}" y1="${M.t}" y2="${H - M.b}" stroke="${m.color}" stroke-dasharray="2 3" opacity=".7"/>` +
             `<text class="series-label" x="${x(m.i) + (m.anchor === "end" ? -4 : 4)}" y="${M.t + 9}" text-anchor="${m.anchor || "start"}" fill="${m.color}">${m.label}</text>`;
      });
      state.series.forEach((s) => {
        const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
        g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" stroke-linejoin="round" stroke-linecap="round"` +
             `${s.dash ? ` stroke-dasharray="${s.dash}"` : ""} opacity="${s.opacity ?? 1}"/>`;
        if (s.label && s.endLabel) {
          const v = s.values[23];
          g += `<text class="series-label" x="${W - M.r + 4}" y="${y(v) + 3}" fill="${s.color}">${s.label}</text>`;
        }
      });
      if (state.hour != null) {
        const main = state.series.find((s) => s.main) || state.series[state.series.length - 1];
        const cx = x(state.hour);
        g += `<line class="cursor" x1="${cx}" x2="${cx}" y1="${M.t}" y2="${H - M.b}"/>`;
        if (main) {
          const v = main.values[state.hour];
          g += `<circle cx="${cx}" cy="${y(v)}" r="4.5" fill="${main.color}" stroke="${opts.surface || "#fffdf9"}" stroke-width="2"/>`;
        }
      }
      g += `<rect class="hit" x="${M.l}" y="0" width="${W - M.l - M.r}" height="${H}"/>`;
      svg.innerHTML = g;
      svg.setAttribute("aria-label", opts.ariaLabel || "Diurnal anthropogenic heat curve");
    }

    function showTip(ev, i) {
      const t = tip();
      const rows = state.series.filter((s) => s.label).map((s) =>
        `<div class="row"><span><span class="sw" style="background:${s.color}"></span>${s.label}</span><span class="num">${s.values[i].toFixed(1)}</span></div>`).join("");
      t.innerHTML = `<div class="eyebrow" style="opacity:.7;margin-bottom:4px">${hourSpan(i)} · W/m²</div>${rows}`;
      const w = t.offsetWidth || 170;
      let left = ev.clientX + 14; if (left + w > innerWidth - 8) left = ev.clientX - w - 14;
      t.style.left = left + "px"; t.style.top = Math.max(8, ev.clientY - 70) + "px";
      t.classList.add("on");
    }
    const hideTip = () => tip().classList.remove("on");

    let dragging = false;
    const pos = (ev) => { const r = svg.getBoundingClientRect(); return (ev.clientX - r.left) * (W / r.width); };
    svg.addEventListener("pointermove", (ev) => {
      const i = idxFromX(pos(ev));
      if (ev.pointerType === "mouse") showTip(ev, i);
      if (dragging && opts.onScrub) opts.onScrub(i);
    });
    svg.addEventListener("pointerleave", hideTip);
    svg.addEventListener("pointerdown", (ev) => {
      if (!opts.onScrub) return;
      dragging = true; svg.setPointerCapture(ev.pointerId); opts.onScrub(idxFromX(pos(ev)));
    });
    const end = () => { dragging = false; };
    svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end);

    new ResizeObserver(render).observe(container);
    return {
      set(patch) { Object.assign(state, patch); render(); },
      get state() { return state; },
    };
  }

  // Tween a number in an element; used only when the model year changes.
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  function tweenNumber(el, to, { dp = 1, dur = 700, fmt } = {}) {
    const from = parseFloat(el.dataset.v ?? to);
    el.dataset.v = to;
    const f = fmt || ((v) => v.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp }));
    if (reduce.matches || from === to) { el.textContent = f(to); return; }
    const t0 = performance.now();
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = f(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function colorAt(ramp, v) {
    for (let k = 1; k < ramp.length; k++) if (v <= ramp[k][0]) return ramp[k][1];
    return ramp[ramp.length - 1][1];
  }

  return { YEARS, PEAK, pad, field, hourEnd, hourSpan, RAMP_QF, RAMP_DQ, qfExpr, dqExpr,
           YEAR_DARK, YEAR_LIGHT, PLACES, addPlaces, diurnal, tweenNumber, colorAt, reduce };
})();
