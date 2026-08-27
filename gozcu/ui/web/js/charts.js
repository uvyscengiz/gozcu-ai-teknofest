// Video altındaki iki canlı grafik — varlık sayısı ve piksel entropisi.
//
// İkisi de `player.js`'in kurduğu senkron ilkeyi tekrar kullanıyor:
// yalnız `ts <= video.currentTime` olan noktalar çiziliyor. Video ileri
// sarıldığında ya da bittiğinde nokta listesi zaten geriye gitmiyor —
// "kalıcı toplam" ayrı bir kip değil, aynı çizimin doğal sonucu.
//
// Veri KAYNAĞI gerçek: varlık sayısı `/api/run/{id}/detections`'ın (Görev 5)
// zaten taşıdığı `label` alanından tek seferlik tam-video çekimiyle,
// entropi `/api/run/{id}/entropy`'den (`motion.py::frame_entropy`). Hiçbir
// sayı burada uydurulmuyor; veri yoksa çizim boş kalıp bunu söylüyor.

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_W = 600;
const VIEW_H = 140;
const PAD = 6;

function el(name, attrs) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    node.setAttribute(key, String(value));
  });
  return node;
}

function emptyText(svgEl, text) {
  svgEl.appendChild(el("text", {
    x: VIEW_W / 2, y: VIEW_H / 2, class: "chart-empty-text",
    "text-anchor": "middle",
  })).textContent = text;
}

function scaleX(ts, span) {
  if (!span) return PAD;
  return PAD + (ts / span) * (VIEW_W - PAD * 2);
}

function scaleY(value, max) {
  if (!max) return VIEW_H - PAD;
  return VIEW_H - PAD - (value / max) * (VIEW_H - PAD * 2);
}

function pointsAttr(points) {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

const ENTITY_COLORS = ["var(--accent)", "var(--info)", "var(--warn)", "var(--muted)"];
const OTHER_LABEL = "Diğer";
const TOP_N = 3;

// =============================================================================
// Varlık sayısı — en çok görülen 3 tür + "Diğer"
// =============================================================================

export function createEntityChart({ video, svgEl, legendEl }) {
  if (!svgEl) return { setRunId() {} };

  let runId = null;
  let duration = 0;
  let rows = [];         // [{ts, label}] — bütün video, tek seferlik çekim
  let topLabels = [];
  let hasOther = false;
  let pendingFetch = false;

  function computeBuckets() {
    const counts = new Map();
    for (const row of rows) counts.set(row.label, (counts.get(row.label) || 0) + 1);
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    topLabels = sorted.slice(0, TOP_N).map(([label]) => label);
    hasOther = sorted.length > TOP_N;
  }

  function bucketFor(label) {
    return topLabels.includes(label) ? label : OTHER_LABEL;
  }

  function renderLegend(buckets) {
    if (!legendEl) return;
    legendEl.replaceChildren(...buckets.map((label, index) => {
      const span = document.createElement("span");
      span.className = "chart-legend-item";
      const swatch = document.createElement("i");
      swatch.className = "chart-legend-swatch";
      swatch.style.background = ENTITY_COLORS[index] || "var(--muted)";
      span.append(swatch, document.createTextNode(label));
      return span;
    }));
  }

  function render() {
    svgEl.textContent = "";
    if (rows.length === 0 || !duration) {
      emptyText(svgEl, "Varlık ölçülemedi");
      return;
    }
    const buckets = hasOther ? [...topLabels, OTHER_LABEL] : topLabels;
    renderLegend(buckets);

    const cutoff = video.currentTime || 0;
    const timestamps = [...new Set(
      rows.filter((row) => row.ts <= cutoff).map((row) => row.ts))].sort((a, b) => a - b);
    if (timestamps.length === 0) return;

    const perBucketPerTs = new Map(buckets.map((bucket) => [bucket, new Map()]));
    for (const row of rows) {
      if (row.ts > cutoff) continue;
      const map = perBucketPerTs.get(bucketFor(row.label));
      map.set(row.ts, (map.get(row.ts) || 0) + 1);
    }
    let maxCount = 1;
    for (const map of perBucketPerTs.values()) {
      for (const count of map.values()) maxCount = Math.max(maxCount, count);
    }

    buckets.forEach((bucket, index) => {
      const map = perBucketPerTs.get(bucket);
      const points = timestamps.map((ts) => ({
        x: scaleX(ts, duration),
        y: scaleY(map.get(ts) || 0, maxCount),
      }));
      svgEl.appendChild(el("polyline", {
        points: pointsAttr(points), fill: "none",
        stroke: ENTITY_COLORS[index] || "var(--muted)", "stroke-width": 1.8,
      }));
    });
  }

  async function fetchData() {
    if (runId === null || !duration) return;
    try {
      const response = await fetch(`/api/run/${runId}/detections?from=0&to=${duration}`);
      if (!response.ok) return;
      const data = await response.json();
      rows = data.items.map((item) => ({ ts: item.ts, label: item.label }));
      computeBuckets();
      render();
    } catch { /* çekilemezse önceki çizim kalır */ }
  }

  video.addEventListener("loadedmetadata", () => {
    duration = video.duration || 0;
    if (pendingFetch) { pendingFetch = false; fetchData(); }
  });
  video.addEventListener("timeupdate", render);
  video.addEventListener("seeked", render);

  return {
    setRunId(id) {
      runId = id;
      rows = [];
      topLabels = [];
      hasOther = false;
      duration = video.duration || 0;
      if (duration) fetchData(); else pendingFetch = true;
      render();
    },
  };
}

// =============================================================================
// Piksel entropisi — tepe noktalarında yatay eşik çizgisi
// =============================================================================

export function createEntropyChart({ video, svgEl }) {
  if (!svgEl) return { setRunId() {} };

  let runId = null;
  let items = [];        // [{ts, value}] — bütün video
  let threshold = null;

  function render() {
    svgEl.textContent = "";
    if (items.length === 0) {
      emptyText(svgEl, "Entropi ölçülemedi");
      return;
    }
    const cutoff = video.currentTime || 0;
    const visible = items.filter((item) => item.ts <= cutoff);
    if (visible.length === 0) return;

    const span = video.duration || items[items.length - 1].ts || 1;
    const maxValue = Math.max(...items.map((item) => item.value),
                              threshold || 0, 0.001);

    const points = visible.map((item) => ({
      x: scaleX(item.ts, span), y: scaleY(item.value, maxValue),
    }));
    svgEl.appendChild(el("polyline", {
      points: pointsAttr(points), fill: "none",
      stroke: "var(--accent)", "stroke-width": 1.8,
    }));

    // Eşik `/api/run/{id}/entropy`'nin GERÇEK dağılımından geliyor
    // (ortalama + 1,5×std) — sabit bir sayı burada uydurulmuyor.
    if (threshold !== null) {
      const y = scaleY(threshold, maxValue);
      svgEl.appendChild(el("line", {
        x1: PAD, x2: VIEW_W - PAD, y1: y, y2: y,
        stroke: "var(--crit)", "stroke-width": 1.2, "stroke-dasharray": "4 3",
      }));
    }
  }

  async function fetchData() {
    if (runId === null) return;
    try {
      const response = await fetch(`/api/run/${runId}/entropy`);
      if (!response.ok) return;
      const data = await response.json();
      items = data.items;
      threshold = data.threshold;
      render();
    } catch { /* çekilemezse önceki çizim kalır */ }
  }

  video.addEventListener("timeupdate", render);
  video.addEventListener("seeked", render);
  video.addEventListener("loadedmetadata", render);

  return {
    setRunId(id) {
      runId = id;
      items = [];
      threshold = null;
      fetchData();
      render();
    },
  };
}
