/* Agents ekranı — ajan mimarisi ve aralarındaki GERÇEK veri akışı
 * (Görev raporu §3).
 *
 * Sekiz ajan modül kartı olarak yerleştiriliyor, aralarındaki devirler
 * (`Handoff`) kenar olarak çiziliyor ve kenarların üstünde birer sinyal
 * noktası akıyor. Rapor "statik bir görüntü olmasın" dedi; buradaki hareket
 * bir süs değil, koşunun kendi devir defterinden geliyor.
 *
 * ## Hareket UYDURULMUYOR
 *
 * Bu ekranın en kolay yalanı, boru hattı boyunca sürekli akan ışıklar
 * çizmek olurdu: mimari şemayı canlı gösterir ama hiçbir şey ölçmez.
 * Kural şu — **yalnız GERÇEKTEN devir taşımış kenarlar akıyor.** Devir
 * görmemiş kenar sönük ve hareketsiz duruyor; zincirin o adımı bu koşuda
 * hiç çalışmadıysa ekran bunu saklamıyor, gösteriyor.
 *
 * Kenar üstündeki sayı da gerçek: o yönde kaç devir yapıldığı. Akış hızı
 * sabit — devir sayısına bağlansaydı "daha hızlı akan kenar daha önemli"
 * gibi okunurdu ve devir sayısı bir önem ölçüsü değil.
 *
 * ## Zincir dışı devirler
 *
 * İskelet `trace.js::CHAIN_STAGES` — konsolun tek zincir tanımı, burada
 * İKİNCİ bir kopyası yazılmıyor. Ama gerçek devirler her zaman komşu iki
 * adım arasında olmuyor (ör. `risk_analyst → supervisor` atlaması). Onlar
 * uydurma bir düz çizgiye sıkıştırılmıyor: kavisli kendi kenarlarını
 * alıyorlar, çünkü "zinciri atladı" bilgisinin kendisi bir kanıt.
 *
 * ## Kütüphane yok
 *
 * Depoda harici bağımlılık yasağı var (README). Çizim elle kurulan `<svg>`;
 * hareket SMIL (`<animateMotion>`) — tarayıcının kendi zamanlayıcısı,
 * `requestAnimationFrame` döngüsü yok, sekme arka plandayken kendiliğinden
 * duruyor.
 */

import { CHAIN_STAGES } from "./trace.js";

const SVG_NS = "http://www.w3.org/2000/svg";

/* Raportör zincirin İÇİNDE değil: kapanış raporunu koşu bittikten sonra
 * üretiyor, yani `CHAIN_STAGES`'in bir adımı değil ama mimarinin bir
 * parçası. Ekranda son düğüm olarak duruyor. */
const CLOSING_STAGE = "reporter";

/* Görünüm kutusu ve ızgara. Dört sütun, iki satır: sekiz düğüm yılan gibi
 * diziliyor (üst satır soldan sağa, alt satır sağdan sola) — böylece
 * ardışık iki adım her zaman komşu kalıyor ve zincir kendini kesmiyor. */
const VIEW_W = 1000;
const VIEW_H = 420;
const COLS = 4;
const NODE_W = 190;
const NODE_H = 78;
const GAP_X = (VIEW_W - COLS * NODE_W) / (COLS + 1);
const ROW_Y = [40, 250];

const FLOW_SECONDS = 2.4;

function svgEl(name, attrs) {
  const node = document.createElementNS(SVG_NS, name);
  for (const key in attrs) node.setAttribute(key, attrs[key]);
  return node;
}

/* Düğümlerin ekran sırası: zincir + kapanış adımı. */
function stageOrder() {
  return CHAIN_STAGES.concat([CLOSING_STAGE]);
}

/* `index`'inci düğümün sol-üst köşesi. Yılan dizilim: tek numaralı satır
 * sağdan sola akıyor. */
function nodeBox(index) {
  const row = Math.floor(index / COLS);
  const inRow = index % COLS;
  const col = row % 2 === 0 ? inRow : COLS - 1 - inRow;
  return {
    x: GAP_X + col * (NODE_W + GAP_X),
    y: ROW_Y[row] || ROW_Y[ROW_Y.length - 1],
    w: NODE_W,
    h: NODE_H,
  };
}

function centreOf(box) {
  return { x: box.x + box.w / 2, y: box.y + box.h / 2 };
}

/* İki düğüm arasındaki yol. Komşu düğümler düz bir çizgiyle, uzaktakiler
 * kavisle bağlanıyor — düz çizgi araya giren kartların üstünden geçer ve
 * hangi düğümü bağladığı okunmaz olurdu. */
function edgePath(fromIndex, toIndex) {
  const a = centreOf(nodeBox(fromIndex));
  const b = centreOf(nodeBox(toIndex));
  if (Math.abs(toIndex - fromIndex) === 1) {
    return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
  }
  /* Kavis: iki nokta arasındaki orta noktayı dikeyde iterek. İtme miktarı
   * atlanan adım sayısıyla büyüyor ki iç içe iki atlama üst üste binmesin. */
  const lift = 40 + 26 * Math.abs(toIndex - fromIndex);
  const midX = (a.x + b.x) / 2;
  const midY = (a.y + b.y) / 2 - lift;
  return `M ${a.x} ${a.y} Q ${midX} ${midY} ${b.x} ${b.y}`;
}

/* ------------------------------------------------------------------ *
 * Çizim
 * ------------------------------------------------------------------ */

function drawNode(svg, stage, index, meta, active) {
  const box = nodeBox(index);
  const group = svgEl("g", {
    class: `agent-node${active ? " on" : ""}`,
  });
  group.appendChild(svgEl("rect", {
    x: box.x, y: box.y, width: box.w, height: box.h, rx: 10,
  }));

  const mark = svgEl("text", {
    x: box.x + 18, y: box.y + 34, class: "agent-node-mark",
  });
  mark.textContent = (meta.agent_marks || {})[stage] || "•";
  group.appendChild(mark);

  const title = svgEl("text", {
    x: box.x + 44, y: box.y + 32, class: "agent-node-title",
  });
  /* Başlık Türkçe, sunucudan (`gozcu/ui/feed.py::AGENT_LABELS`); burada
   * ikinci bir çeviri tablosu yok. Karşılığı yoksa ham kimlik yazılıyor —
   * uydurulmuyor. */
  title.textContent = (meta.agent_labels || {})[stage] || stage;
  group.appendChild(title);

  const id = svgEl("text", {
    x: box.x + 44, y: box.y + 52, class: "agent-node-id",
  });
  id.textContent = stage;
  group.appendChild(id);

  const state = svgEl("text", {
    x: box.x + box.w - 14, y: box.y + 52, "text-anchor": "end",
    class: "agent-node-state",
  });
  /* "Bu koşuda çalıştı mı" sorusunun cevabı. Hiç devir görmemiş bir ajanı
   * çalışmış gibi göstermek bu ekranın işini bitirirdi. */
  state.textContent = active ? "etkin" : "sessiz";
  group.appendChild(state);

  svg.appendChild(group);
}

function drawEdge(svg, fromIndex, toIndex, count) {
  const path = edgePath(fromIndex, toIndex);
  const live = count > 0;

  svg.appendChild(svgEl("path", {
    d: path, fill: "none",
    class: `agent-edge${live ? " on" : ""}`,
  }));
  if (!live) return;

  /* Akan sinyal. `<animateMotion>` yolun kendisini `path` özniteliğiyle
   * alıyor — `<mpath>` + `xlink:href` yerine: ikincisi her kenara benzersiz
   * bir kimlik uydurmayı gerektirirdi ve ekran her tazelendiğinde o
   * kimlikler çakışırdı. */
  const dot = svgEl("circle", { r: 4, class: "agent-flow" });
  dot.appendChild(svgEl("animateMotion", {
    dur: `${FLOW_SECONDS}s`, repeatCount: "indefinite", path,
  }));
  svg.appendChild(dot);

  /* Kenarın ortasına devir sayısı. Yolun orta noktasını ölçmek yerine iki
   * ucun ortası alınıyor; kavisli kenarda birkaç piksel kayıyor ama
   * `getPointAtLength` düğüm DOM'a girmeden çalışmıyor. */
  const a = centreOf(nodeBox(fromIndex));
  const b = centreOf(nodeBox(toIndex));
  const label = svgEl("text", {
    x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 8,
    "text-anchor": "middle", class: "agent-edge-count",
  });
  label.textContent = String(count);
  svg.appendChild(label);
}

/* ------------------------------------------------------------------ *
 * Dışa açılan yüz
 * ------------------------------------------------------------------ */

export function createAgents({ svgEl: canvas, emptyEl, countEl }) {
  let meta = {};
  let runId = null;
  let handoffs = [];

  /* `"kaynak→hedef"` → devir sayısı. */
  function edgeCounts() {
    const counts = new Map();
    for (const row of handoffs) {
      const key = `${row.source}→${row.target}`;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return counts;
  }

  function render() {
    canvas.textContent = "";
    const order = stageOrder();
    const indexOf = new Map(order.map((stage, i) => [stage, i]));
    const counts = edgeCounts();

    /* Etkin ajan: en az bir devrin ucunda görünen. */
    const active = new Set();
    for (const row of handoffs) {
      active.add(row.source);
      active.add(row.target);
    }

    /* Önce iskelet: zincirin komşu adımları, devir görmemişse sönük.
     * Sonra gerçek kenarlar — iskelette olmayanlar da dahil. */
    const drawn = new Set();
    for (let i = 0; i < order.length - 1; i += 1) {
      const key = `${order[i]}→${order[i + 1]}`;
      drawEdge(canvas, i, i + 1, counts.get(key) || 0);
      drawn.add(key);
    }
    counts.forEach((count, key) => {
      if (drawn.has(key)) return;
      const [source, target] = key.split("→");
      const from = indexOf.get(source);
      const to = indexOf.get(target);
      /* Tanımadığımız bir ajan adı (ör. `operator`) zincirde yok; onu
       * bir yere iliştirmek yerine atlıyoruz — devir defteri Şeffaflık
       * sayfasında zaten tam hâliyle duruyor. */
      if (from === undefined || to === undefined) return;
      drawEdge(canvas, from, to, count);
    });

    order.forEach((stage, index) => {
      drawNode(canvas, stage, index, meta, active.has(stage));
    });

    if (countEl) {
      countEl.textContent = `${handoffs.length} devir`;
    }
    if (emptyEl) {
      /* Devir yokken şema yine çiziliyor (mimari koşudan bağımsız), ama
       * altında ne görüldüğü yazıyor: "henüz devir yok" ile "bu ajanlar
       * hiç çalışmadı" farklı cümleler değil — ikisi de aynı şeyi söylüyor
       * ve söylenmesi gerekiyor. */
      emptyEl.classList.toggle("hidden", handoffs.length > 0);
    }
  }

  async function refresh() {
    if (!runId) return;
    try {
      const response = await fetch(`/api/run/${runId}/handoffs`);
      if (!response.ok) return;
      handoffs = await response.json();
    } catch (error) {
      return;                 /* çekilemezse önceki defter ekranda kalır */
    }
    render();
  }

  return {
    setMeta(wireMeta) {
      meta = wireMeta || {};
      render();
    },

    setRunId(id) {
      runId = id;
      handoffs = [];
      render();
      refresh();
    },

    /* Her SSE `state` çerçevesinde: devir defteri koşu ilerledikçe
     * büyüyor, ekran da onunla büyümeli. */
    applyState() {
      refresh();
    },
  };
}
