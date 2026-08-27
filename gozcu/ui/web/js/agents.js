// Ajan mimarisi görünümü — düğümler, kablolar ve üzerlerinde akan paketler.
//
// Her düğümün ne yaptığı, üstüne gelince açılan bilgi kutusunda yazıyor
// (`showTip`). Bu metinler sayfanın altında ayrı bir kart ızgarasında da
// duruyordu; ızgara KALDIRILDI ve metinler `AGENTS[].desc`'e taşındı —
// aynı cümlenin iki kopyası bir gün ayrışır ve iki yer aynı ajanı iki türlü
// anlatır (bu depoda enum'lar tam böyle ayrışmıştı).
//
// **BU SAYFADAKİ AKIŞ ŞU AN TEMSİLÎ.** Paketler rastgele seçilmiş kenarlarda
// yürüyor; hiçbir gerçek devir kaydını okumuyorlar. Bu bilerek böyle
// (kullanıcı kararı) ama ekranda GİZLENMİYOR: `#agentsFlowMode` rozeti
// "demo akışı" diyor. Gerekçe bu depoda pahalıya öğrenildi — video üstündeki
// "CANLI BENCHMARK" HUD'ı üç sayıyı temsilî değerlerle çizdiği için
// kaldırılmıştı (bkz. index.html, `.panel-stage` içindeki not). Ölçülmemiş
// bir şeyi ölçülmüş gibi göstermek, jürinin önünde cevaplanamayan bir soru
// bırakır.
//
// **Gerçek veriye bağlama noktası hazır:** `/api/run/{id}/handoffs` bugün
// `source_agent` · `target_agent` · `ts` taşıyor (`gozcu/ui/view.py::
// handoff_rows`). `pushHandoffs()` o listeyi alıp aynı kablolarda paket
// yürütür; düğüm kimlikleri bu yüzden koddaki ajan adlarıyla BİREBİR aynı
// (`gozcu/ui/feed.py::AGENT_MARKS`) — "Yönetici" gibi Türkçe bir etiketle
// eşleştirme yapılsaydı bağlama günü sessizce tutmazdı.

// =============================================================================
// Düğümler — kimlik koddaki ajan adı, etiket Türkçe
// =============================================================================
//
// `art`: `img/agents/` altındaki konsept görseli. **`null` bir eksiklik
// DEĞİL, bir ayrım:** görseli olan düğüm kutulu çiziliyor, olmayan yalnız
// bir daire. Üçü (`perception`, `interpreter`, `reporter`) kutulu ve yedek
// ikonluyken "konsept görseli unutulmuş bir ajan" gibi okunuyordu — oysa
// kadro tam. Kutu artık "bu düğümün çizimi var" demek, başka bir şey değil.
//
// `desc`: düğümün üstüne gelince açılan bilgi kutusunun metni. **Tek
// kaynak burası** — bu metinler sayfanın altında ayrı bir kart ızgarasında
// İKİNCİ KEZ yazılıydı ve iki kopya bir gün ayrışırdı; ızgara kaldırıldı.
const AGENTS = [
  { id: "perception",      label: "Algı",               art: null,
    x: 90,  y: 300,
    desc: "Video karelerini tarar, nesneleri tespit edip izler ve kare başına "
        + "sinyal üretir. Model çağırmaz — bütün video, koşu başlamadan önce "
        + "bir kez taranır." },
  { id: "orchestrator",    label: "Yönetici",           art: "img/agents/yonetici.png",
    x: 285, y: 105,
    desc: "Her pencereyi değerlendirip pahalı görü bütçesini nereye "
        + "harcayacağına karar verir: görmezden gel, incele, epizot aç ya da "
        + "yükselt." },
  { id: "interpreter",     label: "Yorumlayıcı",        art: null,
    x: 285, y: 300,
    desc: "Klibi okuyup ne olduğunu anlatır: olayın ciddiyetini (rutin / "
        + "dikkat / olay) ve klip içindeki anları çıkarır. Epizot açılışının "
        + "geçidi bu ciddiyet." },
  { id: "anomaly_analyst", label: "Anomali Analiz",     art: "img/agents/anomali-analiz.png",
    x: 480, y: 300,
    desc: "Açılan epizodu pencere pencere izler; olayı özetler, türünü "
        + "(çarpma, düşme, yangın…) ve gerçekleştiği bölgeyi belirler." },
  { id: "risk_analyst",    label: "Risk Değerlendirme", art: "img/agents/risk-degerlendirme.png",
    x: 675, y: 300,
    desc: "Olayın risk seviyesini biçer (Düşük / Orta / Yüksek / Kritik), "
        + "gerekçesini yazar ve uzun süreli hafızadan benzer geçmiş olayları "
        + "emsal olarak getirir." },
  { id: "action_planner",  label: "Karar & Aksiyon",    art: "img/agents/karar-aksiyon.png",
    x: 870, y: 300,
    desc: "Tesisin yazılı prosedürleri arasından uygulanacak olanı seçer ve "
        + "çağrılacak saha araçlarını planlar. Prosedürü uydurmaz — aday "
        + "listesi deterministik süzülüp önüne konur." },
  { id: "supervisor",      label: "Operatör Diyalog",   art: "img/agents/operator-diyalog.png",
    x: 675, y: 105,
    desc: "Kritik anda operatöre seslenir, sorularını yanıtlar ve saha "
        + "araçlarını çağırır. Yetkisi olmayan bir çağrı için önce onay "
        + "ister." },
  { id: "reporter",        label: "Raporlayıcı",        art: null,
    x: 870, y: 105,
    desc: "Koşu bitince kök neden raporunu ve şartnamenin dört anahtarlı "
        + "çıktısını (özet · olaylar · risk · aksiyonlar) hazırlar." },
  { id: "memory",          label: "Uzun Süreli Hafıza", art: "img/agents/uzun-sureli-hafiza.png",
    x: 480, y: 495,
    desc: "Geçmiş epizotları vektör olarak saklar ve emsal aramasını besler. "
        + "Ajan değil, bir alt sistem: model çalıştırmaz." },
];

// Kenarlar — sistemin GERÇEK karar zincirinden (`trace.js::CHAIN_STAGES`) ve
// hafıza bağlanmalarından geliyor. Uydurulmuş bir bağlantı yok: burada
// çizili olan her hat, kodda gerçekten var olan bir devir yolu.
//
// `kind`: `chain` sabit zincir, `memory` hafıza okuma/yazma, `loop` geri
// besleme. Üçü ayrı renk — hepsi aynı görünseydi hafızanın iki yönlü
// olduğu kaybolurdu.
const EDGES = [
  { from: "perception",      to: "orchestrator",    kind: "chain" },
  { from: "orchestrator",    to: "interpreter",     kind: "chain" },
  { from: "interpreter",     to: "anomaly_analyst", kind: "chain" },
  { from: "anomaly_analyst", to: "risk_analyst",    kind: "chain" },
  { from: "risk_analyst",    to: "action_planner",  kind: "chain" },
  { from: "action_planner",  to: "supervisor",      kind: "chain" },
  { from: "supervisor",      to: "reporter",        kind: "chain" },
  { from: "orchestrator",    to: "anomaly_analyst", kind: "chain" },
  { from: "anomaly_analyst", to: "memory",          kind: "memory" },
  { from: "memory",          to: "risk_analyst",    kind: "memory" },
  { from: "memory",          to: "supervisor",      kind: "memory" },
  { from: "supervisor",      to: "orchestrator",    kind: "loop" },
];

const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_W = 118;
const NODE_H = 92;

//: Paket hızı (yol uzunluğunun saniyedeki oranı değil, px/sn). Sabit hız
//: kısa ve uzun kabloda AYNI görünsün diye: yüzdeyle yürüseydi kısa hat
//: gözle takip edilemeyecek kadar hızlı olurdu.
const PACKET_SPEED_PX = 210;
//: Demo kipinde iki paket arası bekleme aralığı.
const DEMO_MIN_MS = 420;
const DEMO_MAX_MS = 1500;
//: Düğümün "az önce konuştu" parlaması ne kadar sürüyor.
const PULSE_MS = 620;

//: Şemanın kendi koordinat uzayı — `index.html`'deki `viewBox` ile AYNI
//: olmak zorunda. Yakınlaştırma bu dikdörtgeni küçültüp büyüterek çalışıyor.
const BASE_W = 960;
const BASE_H = 560;
//: Yakınlaştırma sınırları. Alt sınır 1'in altında: dar bir ekranda şemanın
//: tamamını görebilmek de bir "zoom" ihtiyacı.
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 4;
//: Tuş başına adım. Tekerlek de aynı adımı kullanıyor — iki yol farklı
//: hızda yakınlaşsaydı aynı jest iki türlü davranırdı.
const ZOOM_STEP = 1.25;

export function createAgents({ svgEl, modeEl, legendEl, tipEl, zoomEls }) {
  if (!svgEl) {
    return { start() {}, stop() {}, pushHandoffs() {} };
  }

  const nodeById = new Map(AGENTS.map((a) => [a.id, a]));
  const paths = new Map();       // "from>to" -> <path>
  const nodeGroups = new Map();  // id -> <g>
  const packets = [];
  let running = false;
  let frame = null;
  let demoTimer = null;
  let lastTime = 0;

  // ===========================================================================
  // Çizim
  // ===========================================================================

  function el(name, attrs) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      node.setAttribute(key, String(value));
    });
    return node;
  }

  function edgeKey(from, to) { return `${from}>${to}`; }

  // ===========================================================================
  // Yakınlaştırma ve kaydırma
  // ===========================================================================
  //
  // `viewBox`'ı değiştirerek çalışıyor, `transform: scale()` ile DEĞİL:
  // ölçek `viewBox`'tan gelince çizgi kalınlıkları ve yazı boyutu şemayla
  // birlikte büyüyor, yani yakınlaşınca kablolar incecik kalmıyor. Paketler
  // de etkilenmiyor — `getPointAtLength` kullanıcı biriminde çalışıyor ve
  // `viewBox` onu değiştirmiyor.

  const view = { zoom: 1, x: 0, y: 0 };
  let panning = null;

  /** Ekran koordinatını şemanın kendi uzayına çevirir.
   *
   *  `getScreenCTM()` kullanılıyor, elle letterbox aritmetiği DEĞİL:
   *  `preserveAspectRatio="xMidYMid meet"` şemayı kutunun içinde ortalayıp
   *  kenarda boşluk bırakıyor ve o boşluk hesaba katılmazsa imleç altındaki
   *  nokta kayar. Tarayıcı bu dönüşümü zaten tutuyor. */
  function toUserSpace(clientX, clientY) {
    const matrix = svgEl.getScreenCTM();
    if (!matrix) return null;
    return new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
  }

  function applyView() {
    const width = BASE_W / view.zoom;
    const height = BASE_H / view.zoom;
    // Kaydırmayı sınırla: şema tamamen kadraj dışına sürüklenip ekran boş
    // kalmasın. Uzaklaşmışken (`zoom < 1`) sınır ters işaretli, o yüzden
    // aralık iki uçtan da hesaplanıyor.
    const limitX = BASE_W - width;
    const limitY = BASE_H - height;
    view.x = Math.min(Math.max(view.x, Math.min(0, limitX)), Math.max(0, limitX));
    view.y = Math.min(Math.max(view.y, Math.min(0, limitY)), Math.max(0, limitY));
    svgEl.setAttribute("viewBox", `${view.x} ${view.y} ${width} ${height}`);
    if (zoomEls && zoomEls.levelEl) {
      zoomEls.levelEl.textContent = `%${Math.round(view.zoom * 100)}`;
    }
  }

  /** `factor` kadar yakınlaştırır; verilen ekran noktası SABİT kalır.
   *
   *  Sabitleme olmadan tekerlek her zaman şemanın ortasına yakınlaşırdı ve
   *  kenardaki bir düğümü büyütmek için önce onu ortaya sürüklemek
   *  gerekirdi. */
  function zoomBy(factor, clientX, clientY) {
    const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.zoom * factor));
    if (next === view.zoom) return;

    const before = toUserSpace(clientX, clientY);
    view.zoom = next;
    applyView();
    const after = toUserSpace(clientX, clientY);
    if (before && after) {
      view.x += before.x - after.x;
      view.y += before.y - after.y;
      applyView();
    }
    hideTip();
  }

  /** Tuşlarla yakınlaşırken sabit nokta sahnenin ORTASI. */
  function zoomFromCentre(factor) {
    const box = svgEl.getBoundingClientRect();
    zoomBy(factor, box.left + box.width / 2, box.top + box.height / 2);
  }

  function resetView() {
    view.zoom = 1;
    view.x = 0;
    view.y = 0;
    applyView();
    hideTip();
  }

  svgEl.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP,
           event.clientX, event.clientY);
  }, { passive: false });   // `preventDefault` pasif dinleyicide yok sayılır

  svgEl.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    panning = { x: event.clientX, y: event.clientY };
    // Yakalama İSTEĞE BAĞLI bir iyileştirme: imleç sahnenin dışına çıksa da
    // sürükleme sürsün diye. Geçersiz/eskimiş bir `pointerId`'de istisna
    // atıyor ve sarmalanmazsa kaydırma o istisnayla tamamen ölürdü —
    // yakalama olmadan da kaydırma çalışır, yalnız sahne dışında kopar.
    try { svgEl.setPointerCapture(event.pointerId); } catch { /* yakalama yok */ }
    svgEl.classList.add("is-panning");
    hideTip();
  });

  svgEl.addEventListener("pointermove", (event) => {
    if (!panning) return;
    // Delta kullanıcı uzayında ölçülüyor: ekran pikseli ile şema birimi
    // arasındaki oran yakınlaştırmaya göre değişiyor ve ham piksel farkı
    // kullanılsaydı sürükleme yakınlaşınca hızlanırdı.
    const from = toUserSpace(panning.x, panning.y);
    const to = toUserSpace(event.clientX, event.clientY);
    if (!from || !to) return;
    view.x -= to.x - from.x;
    view.y -= to.y - from.y;
    panning = { x: event.clientX, y: event.clientY };
    applyView();
  });

  function endPan(event) {
    if (!panning) return;
    panning = null;
    svgEl.classList.remove("is-panning");
    try {
      if (svgEl.hasPointerCapture(event.pointerId)) {
        svgEl.releasePointerCapture(event.pointerId);
      }
    } catch { /* yakalanmamıştı */ }
  }
  svgEl.addEventListener("pointerup", endPan);
  svgEl.addEventListener("pointercancel", endPan);

  if (zoomEls) {
    if (zoomEls.inEl) {
      zoomEls.inEl.addEventListener("click", () => zoomFromCentre(ZOOM_STEP));
    }
    if (zoomEls.outEl) {
      zoomEls.outEl.addEventListener("click", () => zoomFromCentre(1 / ZOOM_STEP));
    }
    if (zoomEls.resetEl) zoomEls.resetEl.addEventListener("click", resetView);
  }

  // ===========================================================================
  // Bilgi kutusu — düğümün üstüne gelince
  // ===========================================================================
  //
  // Konum SVG koordinatlarından DEĞİL, `getBoundingClientRect()`'ten
  // hesaplanıyor: `<svg>` bir `viewBox` ile ölçekleniyor ve ekran pikseli ile
  // kullanıcı birimi arasındaki oran pencere genişliğine göre değişiyor —
  // ham `agent.x` kullanılsaydı balon dar ekranda düğümden kayardı.

  //: Balonun sahne kenarına en fazla yaklaşabileceği mesafe.
  const TIP_MARGIN = 8;

  function showTip(agent, group) {
    // Sürükleyerek kaydırırken imleç düğümlerin üstünden geçiyor ve balon
    // arka arkaya açılıp kapanarak titriyordu.
    if (!tipEl || panning) return;
    tipEl.replaceChildren();

    const name = document.createElement("div");
    name.className = "ag-tip-name";
    name.textContent = agent.label;
    // Koddaki İngilizce kimlik de görünüyor: devir defteri (Şeffaflık) onu
    // basıyor ve iki ekranı eşleştirebilmek gerekiyor.
    const id = document.createElement("span");
    id.className = "ag-tip-id";
    id.textContent = agent.id;
    name.appendChild(id);

    const desc = document.createElement("p");
    desc.className = "ag-tip-desc";
    desc.textContent = agent.desc;

    tipEl.append(name, desc);
    tipEl.classList.remove("hidden");

    const stage = tipEl.offsetParent || svgEl.parentElement;
    const stageBox = stage.getBoundingClientRect();
    const nodeBox = group.getBoundingClientRect();
    const tipBox = tipEl.getBoundingClientRect();

    // Yatayda düğümün ortasına hizalı, sahnenin dışına taşmayacak şekilde.
    const centre = nodeBox.left + nodeBox.width / 2 - stageBox.left;
    const maxLeft = stageBox.width - tipBox.width - TIP_MARGIN;
    tipEl.style.left =
      `${Math.max(TIP_MARGIN, Math.min(centre - tipBox.width / 2, maxLeft))}px`;

    // Dikeyde ÜSTÜNE; yukarıda yer yoksa altına — üst sıradaki düğümlerde
    // balon sahnenin dışına çıkıp kırpılıyordu.
    const above = nodeBox.top - stageBox.top - tipBox.height - TIP_MARGIN;
    tipEl.style.top = above >= TIP_MARGIN
      ? `${above}px`
      : `${nodeBox.bottom - stageBox.top + TIP_MARGIN}px`;
  }

  function hideTip() {
    if (tipEl) tipEl.classList.add("hidden");
  }

  /** İki düğüm arasındaki kablo. Düz çizgi DEĞİL: hafif bir yay, çünkü
   *  `orchestrator → anomaly_analyst` ile `interpreter → anomaly_analyst`
   *  düz çizildiğinde üst üste biniyor ve iki ayrı yol tek hat görünüyor. */
  function cablePath(a, b) {
    const midX = (a.x + b.x) / 2;
    const midY = (a.y + b.y) / 2;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const length = Math.hypot(dx, dy) || 1;
    // Dikey normal boyunca kaydırma — yayın yönü hattın yönüne bağlı.
    const bow = Math.min(46, length * 0.16);
    const cx = midX + (-dy / length) * bow;
    const cy = midY + (dx / length) * bow;
    return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
  }

  function buildCables(layer) {
    EDGES.forEach((edge) => {
      const a = nodeById.get(edge.from);
      const b = nodeById.get(edge.to);
      if (!a || !b) return;
      const d = cablePath(a, b);

      // İki katman: altta kalın ve soluk "kılıf", üstte ince canlı hat.
      // Tek hatla çizildiğinde kablolar düğümlerin arasında kayboluyordu.
      layer.appendChild(el("path", {
        d, class: "ag-cable-shell", fill: "none",
      }));
      const line = el("path", {
        d, fill: "none",
        class: `ag-cable ag-cable-${edge.kind}`,
      });
      layer.appendChild(line);
      paths.set(edgeKey(edge.from, edge.to), line);
    });
  }

  /** Kutulu düğüm: konsept görseli OLAN ajanlar. */
  function buildBoxedNode(group, agent) {
    group.appendChild(el("rect", {
      class: "ag-node-halo",
      x: -6, y: -6, width: NODE_W + 12, height: NODE_H + 12, rx: 18,
    }));
    const box = el("rect", {
      class: "ag-node-box",
      x: 0, y: 0, width: NODE_W, height: NODE_H, rx: 14,
    });
    group.appendChild(box);

    const art = el("image", {
      class: "ag-node-art",
      href: agent.art, x: (NODE_W - 52) / 2, y: 10, width: 52, height: 52,
      preserveAspectRatio: "xMidYMid meet",
    });
    // Görsel yüklenemezse düğüm KUTUSUZ daireye düşüyor — kutuyu bırakıp
    // içine yedek ikon koymak, tam da kaldırdığımız "görseli eksik ajan"
    // görüntüsünü geri getirirdi. Kutu = "çizimi var", istisnasız.
    art.addEventListener("error", () => {
      art.remove();
      box.remove();
      group.querySelector(".ag-node-halo").remove();
      buildDotNode(group);
    });
    group.appendChild(art);
  }

  /** Kutusuz düğüm: konsept görseli OLMAYAN aşamalar — yalnız bir daire. */
  function buildDotNode(group) {
    const dot = el("g", { class: "ag-node-dot" });
    dot.appendChild(el("circle", {
      cx: NODE_W / 2, cy: 36, r: 18, fill: "none",
      stroke: "currentColor", "stroke-width": 2,
    }));
    dot.appendChild(el("circle", {
      cx: NODE_W / 2, cy: 36, r: 6, fill: "currentColor",
    }));
    group.insertBefore(dot, group.firstChild);
  }

  function buildNode(agent) {
    const group = el("g", {
      class: agent.art ? "ag-node" : "ag-node is-dot",
      transform: `translate(${agent.x - NODE_W / 2} ${agent.y - NODE_H / 2})`,
      // `<title>` DEĞİL: özel bilgi kutusu zaten açılıyor ve tarayıcının
      // kendi gecikmeli balonu onun üstüne İKİNCİ bir kutu olarak binerdi.
      // `aria-label` erişilebilir adı görsel bir balon üretmeden veriyor.
      role: "img",
      "aria-label": `${agent.label} — ${agent.id}. ${agent.desc}`,
    });

    if (agent.art) buildBoxedNode(group, agent); else buildDotNode(group);

    const label = el("text", {
      class: "ag-node-label", x: NODE_W / 2, y: 78, "text-anchor": "middle",
    });
    label.textContent = agent.label;
    group.appendChild(label);

    // Bilgi kutusu üstüne gelince açılıyor. Fare olayları düğümün BOŞ
    // alanında da tutsun diye şeffaf bir vurma alanı: `<g>` kendi başına
    // yalnız çizili piksellerde olay almıyor ve kutunun köşelerinde balon
    // titreşiyordu.
    group.appendChild(el("rect", {
      class: "ag-node-hit", x: -6, y: -6,
      width: NODE_W + 12, height: NODE_H + 12, fill: "transparent",
    }));
    group.addEventListener("mouseenter", () => showTip(agent, group));
    group.addEventListener("mouseleave", hideTip);

    nodeGroups.set(agent.id, group);
    return group;
  }

  function build() {
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
    const cableLayer = el("g", { class: "ag-cables" });
    const nodeLayer = el("g", { class: "ag-nodes" });
    const packetLayer = el("g", { class: "ag-packets" });
    svgEl.appendChild(cableLayer);
    svgEl.appendChild(packetLayer);   // paketler kablonun ÜSTÜNDE, düğümün ALTINDA
    svgEl.appendChild(nodeLayer);

    buildCables(cableLayer);
    AGENTS.forEach((agent) => nodeLayer.appendChild(buildNode(agent)));
    return packetLayer;
  }

  const packetLayer = build();
  // `viewBox`'ı ve yüzde göstergesini başlangıç durumuna yazıyor — gösterge
  // ilk yakınlaştırmaya kadar boş kalmasın.
  applyView();

  // ===========================================================================
  // Paketler
  // ===========================================================================

  function pulse(agentId) {
    const group = nodeGroups.get(agentId);
    if (!group) return;
    group.classList.add("live");
    setTimeout(() => group.classList.remove("live"), PULSE_MS);
  }

  /** Bir kenarda paket yürütür. Kenar tanımlı değilse SESSİZCE düşüyor:
   *  gerçek devir verisi bağlandığında (`pushHandoffs`) kodda karşılığı
   *  olmayan bir devir gelebilir ve bu ekranı çökertmemeli. */
  function sendPacket(from, to, kind) {
    const path = paths.get(edgeKey(from, to)) || paths.get(edgeKey(to, from));
    if (!path) return false;

    const dot = el("circle", { class: `ag-packet ag-packet-${kind || "chain"}`, r: 4.5 });
    packetLayer.appendChild(dot);
    packets.push({
      dot, path,
      length: path.getTotalLength(),
      travelled: 0,
      // Ters yönde çizilmiş bir kabloyu kullanıyorsak paket geriye doğru
      // yürümeli; yoksa ok yönü ile veri yönü çelişir.
      reverse: !paths.has(edgeKey(from, to)),
      target: to,
    });
    pulse(from);
    return true;
  }

  function step(now) {
    if (!running) return;
    const delta = lastTime ? (now - lastTime) / 1000 : 0;
    lastTime = now;

    for (let i = packets.length - 1; i >= 0; i--) {
      const packet = packets[i];
      packet.travelled += PACKET_SPEED_PX * delta;
      if (packet.travelled >= packet.length) {
        packet.dot.remove();
        packets.splice(i, 1);
        pulse(packet.target);
        continue;
      }
      const at = packet.reverse
        ? packet.length - packet.travelled
        : packet.travelled;
      const point = packet.path.getPointAtLength(at);
      packet.dot.setAttribute("cx", point.x);
      packet.dot.setAttribute("cy", point.y);
    }

    frame = requestAnimationFrame(step);
  }

  // ===========================================================================
  // Demo kipi — rastgele kenar seçer
  // ===========================================================================

  function scheduleDemo() {
    const wait = DEMO_MIN_MS + Math.random() * (DEMO_MAX_MS - DEMO_MIN_MS);
    demoTimer = setTimeout(() => {
      if (!running) return;
      const edge = EDGES[Math.floor(Math.random() * EDGES.length)];
      sendPacket(edge.from, edge.to, edge.kind);
      scheduleDemo();
    }, wait);
  }

  function renderLegend() {
    if (!legendEl) return;
    const items = [
      ["chain", "karar zinciri"],
      ["memory", "hafıza okuma / yazma"],
      ["loop", "geri besleme"],
    ];
    legendEl.replaceChildren(...items.map(([kind, text]) => {
      const span = document.createElement("span");
      span.className = "ag-legend-item";
      const swatch = document.createElement("i");
      swatch.className = `ag-legend-swatch ag-legend-${kind}`;
      span.appendChild(swatch);
      span.appendChild(document.createTextNode(text));
      return span;
    }));
  }

  renderLegend();

  if (modeEl) {
    // Rozet metni akışın NE OLDUĞUNU söylüyor. Sayfa açıldığında akış
    // temsilî ve bu cümle onu saklamıyor.
    modeEl.textContent = "demo akışı";
    modeEl.dataset.state = "demo";
    modeEl.title = "Kablolardaki hareket TEMSİLÎ — rastgele seçilmiş "
      + "kenarlarda yürüyor, gerçek devir kaydı okumuyor. Gerçek devirler "
      + "Şeffaflık sayfasındaki Devir Defteri'nde.";
  }

  return {
    start() {
      if (running) return;
      running = true;
      lastTime = 0;
      frame = requestAnimationFrame(step);
      scheduleDemo();
    },

    /** Sekmeden çıkınca durduruluyor: görünmeyen bir sayfa için her karede
     *  `getPointAtLength` çağırmak boşuna CPU — ve dizüstünde fanı çalıştırıp
     *  demo sırasında dikkat dağıtır. */
    stop() {
      running = false;
      if (frame) cancelAnimationFrame(frame);
      clearTimeout(demoTimer);
      frame = null;
      demoTimer = null;
      packets.splice(0).forEach((packet) => packet.dot.remove());
      // Sekme değişirken imleç düğümün üstündeyse `mouseleave` hiç gelmiyor
      // ve balon gizli sayfada asılı kalıyor — geri dönüldüğünde açık
      // buluyoruz.
      hideTip();
    },

    /** GERÇEK devir kayıtlarını akışa çevirir — bugün ÇAĞRILMIYOR.
     *
     *  Bağlama günü tek iş: `/api/run/{id}/handoffs`'tan gelen satırları
     *  buraya vermek ve `modeEl`'i "canlı devirler" yapmak. İmza şimdiden
     *  o uçtaki alan adlarıyla (`source`/`target`) uyumlu tutuldu.
     */
    pushHandoffs(rows) {
      (rows || []).forEach((row) => sendPacket(row.source, row.target, "chain"));
    },
  };
}
