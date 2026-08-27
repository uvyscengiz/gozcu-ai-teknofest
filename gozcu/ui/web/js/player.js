// Oynatıcı — kutu katmanı, zaman çizelgesi ve belirsizlik çizimi (Görev 7).
//
// KOORDİNAT UZAYI. `Detection.box` 0-1 normalize DEĞİL: tam sayı PİKSEL ve
// uzay orijinal video değil, `extract_frames`'in ölçeklediği çıkarım karesi
// (`FRAME_WIDTH = 896`, gozcu/config.py:88). `GET .../detections` bu yüzden
// `frame_size`'ı HER yanıtta taşıyor — tarayıcı ölçeği asla tahmin etmiyor.
// Katman iki ölçek çeviriyor:
//
//   box_px (çıkarım karesi uzayı) → /frame_size → 0-1
//                                 → ×(object-fit:contain'in kapladığı GERÇEK
//                                    alan) → ekran px
//
// `.video-frame`'in CSS'i (`css/styles.css`) videoyu ve `#boxOverlay`'i AYNI
// `inset:0` kutusuna oturtuyor, yani `overlay`'in `clientWidth/clientHeight`'ı
// her zaman `video`'nunkiyle birebir aynı — letterbox'ı (`object-fit:
// contain`'in videoyu ORTALAYIP bıraktığı boşluk) burada, `place()` içinde
// hesaplıyoruz; `video.clientWidth/clientHeight`'a göre değil.
//
// İKİ AYRI BELİRSİZLİK KURALI — spec §7.3, bu görevin blind-review bloker'ı,
// BİRBİRİNE KARIŞTIRILMIYOR:
//
//   1. `t > processed_until_s` (sınırın ÖTESİ): algı bütün videoyu koşu
//      BAŞLAMADAN tarıyor (`gozcu/run.py:366`), yani kutu VERİSİ zaten var —
//      normal çiziliyor. Eksik olan yorumlama (yönlendirme/epizot/risk); bu
//      bölge zaman çizelgesinde ayrı bir "henüz karar verilmedi" bandıyla
//      işaretleniyor, BOŞ bırakılmıyor.
//
//   2. Sınırın İÇİNDEKİ `deferred` pencereler: `WindowRecord.outcome`
//      "ertelendi" diyebiliyor ama `catch_up()` kayda hiçbir şey yazmadığı
//      için (`loop.py:834`) hiçbir zaman "telafi edildi" diyemiyor. Kaydı
//      tek kaynak almak, telafiden SONRA bile o saniyeleri sonsuza dek
//      belirsiz gösterirdi. Doğru kaynak CANLI DÖNGÜ: SSE durumunun
//      `pending_deferred_ts`'i (`Session.pending_deferred_ts`,
//      `server.py::_snapshot`) — bir pencere ANCAK başlangıç saniyesi hâlâ
//      bu kümedeyken belirsiz çiziliyor, küme boşalınca (`catch_up`) normal
//      çizime dönüyor. Sunucuda iş YOK, bu dosya yalnız çiziyor.
//
// Ekrandaki her kelime Türkçe; kutu etiketi ve zaman çizelgesi ipuçları da
// dahil. Hiçbir DOM düğümü `innerHTML` ile doldurulmuyor.

/** Brief'in aritmetiği, aynen: letterbox'ı hesaba katan tek dönüşüm yeri. */
function place(box, frameSize, video) {
  const [fw, fh] = frameSize;
  const scale = Math.min(video.clientWidth / video.videoWidth,
                         video.clientHeight / video.videoHeight);
  const shownW = video.videoWidth * scale;
  const shownH = video.videoHeight * scale;
  const offsetX = (video.clientWidth - shownW) / 2;
  const offsetY = (video.clientHeight - shownH) / 2;
  return {
    left: offsetX + (box[0] / fw) * shownW,
    top: offsetY + (box[1] / fh) * shownH,
    width: ((box[2] - box[0]) / fw) * shownW,
    height: ((box[3] - box[1]) / fh) * shownH,
  };
}

/**
 * `"MM:SS"` → saniye. `GET .../windows` damgaları `gozcu.agents.orchestrator.mmss`
 * ile ZATEN biçimlendirilmiş geliyor (view/server katmanı öyle yazdı); bu
 * yalnız o dizeyi zaman çizelgesi yerleşimi için SAYIYA geri çeviriyor —
 * yeni bir karar/eşik değil, biçimlendirmenin ters aritmetiği.
 */
function parseMmss(text) {
  if (typeof text !== "string" || !text.includes(":")) return null;
  const [mm, ss] = text.split(":").map(Number);
  if (!Number.isFinite(mm) || !Number.isFinite(ss)) return null;
  return mm * 60 + ss;
}

// Bir gözlemi geçerli saymak için `video.currentTime`'a en yakın olması
// gereken pencere — algı ~3 fps aktığı için bir tolerans gerekiyor. Bir
// eşik/etiket DEĞİL, yalnız görsel yumuşatma.
const MATCH_EPSILON_S = 0.75;
// Bir çekimde istenen aralık — ağ isteği sıklığını düşürüyor, pencere
// uzunluğuyla (WINDOW_S) ilgisi yok.
const FETCH_SPAN_S = 12;
const FETCH_LOOKBACK_S = 2;

export function createPlayer({ video, overlay, timelineEl, frontierEl,
                               deferredEl, markersEl, progressEl, boxCountEl,
                               riskVBarEl }) {
  const st = {
    runId: null,
    frameSize: null,
    detFrom: null,
    detTo: null,
    detItems: [],
    detFetching: false,
    duration: 0,
    processedUntil: 0,
    pendingDeferred: new Set(),
    windows: [],       // [{ tsSec, endSec, outcome }] — /windows'tan, saniyeye çevrilmiş
  };

  // ===========================================================================
  // Kutu katmanı
  // ===========================================================================

  /** Video üstündeki nesne sayacı. Sayı UYDURULMUYOR: `drawBoxesAt`'ın o an
   *  DOM'a gerçekten koyduğu kutu adedi. Algı kapalıysa, o saniyeye eşleşen
   *  kare yoksa ya da koşu yoksa `0 nesne` yazıyor — "—" değil, çünkü burada
   *  ölçüm YAPILMADI değil, ölçüldü ve SIFIR çıktı. */
  function setBoxCount(count) {
    if (boxCountEl) boxCountEl.textContent = `${count} nesne`;
  }

  function clearBoxes() {
    overlay.textContent = "";
    setBoxCount(0);
  }

  function drawBoxesAt(ts) {
    if (!st.frameSize || !video.videoWidth || !video.videoHeight) {
      clearBoxes();
      return;
    }
    let bestTs = null;
    let bestDiff = Infinity;
    for (const item of st.detItems) {
      const diff = Math.abs(item.ts - ts);
      if (diff < bestDiff) { bestDiff = diff; bestTs = item.ts; }
    }
    clearBoxes();
    if (bestTs === null || bestDiff > MATCH_EPSILON_S) return;
    let drawn = 0;
    for (const item of st.detItems) {
      if (item.ts !== bestTs) continue;
      drawn += 1;
      const rect = place(item.box, st.frameSize, video);
      const box = document.createElement("div");
      box.className = "bbox";
      box.style.left = `${rect.left}px`;
      box.style.top = `${rect.top}px`;
      box.style.width = `${Math.max(rect.width, 0)}px`;
      box.style.height = `${Math.max(rect.height, 0)}px`;
      const label = document.createElement("span");
      label.className = "bbox-label";
      const pct = Math.round((item.confidence || 0) * 100);
      label.textContent = `${item.label} ${pct}%`;
      box.appendChild(label);
      overlay.appendChild(box);
    }
    setBoxCount(drawn);
  }

  async function ensureDetections(ts) {
    if (st.runId === null) return;
    const covered = st.detFrom !== null && ts >= st.detFrom
      && ts <= st.detTo - MATCH_EPSILON_S;
    if (covered || st.detFetching) return;
    st.detFetching = true;
    const from = Math.max(0, ts - FETCH_LOOKBACK_S);
    const to = ts + FETCH_SPAN_S;
    try {
      const response = await fetch(
        `/api/run/${st.runId}/detections?from=${from}&to=${to}`);
      if (response.ok) {
        const data = await response.json();
        st.frameSize = data.frame_size;
        st.detItems = data.items;
        st.detFrom = from;
        st.detTo = to;
      }
    } catch { /* ağ hatasında bir önceki önbellek kalır */ }
    st.detFetching = false;
  }

  async function onTimeTick() {
    if (st.runId === null) return;
    const ts = video.currentTime;
    await ensureDetections(ts);
    drawBoxesAt(ts);
    renderProgress();
    renderRiskVBar(ts);
  }

  // ===========================================================================
  // Dikey risk göstergesi — o ana kadarki EN SON risk kararı
  // ===========================================================================
  //
  // `feed.py`de `kind:"risk"` girdileri `.ts` ve `.risk` taşıyor (satır
  // 503-513) — ikinci bir risk kaynağı YOK, `renderMarkers`'ın okuduğu
  // AYNI `state.feed`. 4 gerçek seviye (Düşük/Orta/Yüksek/Kritik) 3 görsel
  // banda eşleniyor: Yüksek ve Kritik AYNI (kırmızı) bantta — yeni bir
  // seviye uydurulmuyor, yalnız görsel olarak birleştiriliyor.

  const RISK_BAND_RANK = { low: 1, medium: 2, high: 3 };

  function riskBandFor(level) {
    if (level === "Düşük") return "low";
    if (level === "Orta") return "medium";
    if (level === "Yüksek" || level === "Kritik") return "high";
    return null;
  }

  function riskAt(ts) {
    let latest = null;
    for (const entry of lastFeed) {
      if (entry.kind !== "risk" || entry.ts > ts) continue;
      if (!latest || entry.ts > latest.ts) latest = entry;
    }
    return latest ? latest.risk : null;
  }

  /** Termometre dolumu: `renderRisk`'in (sse.js) yatay 4 kademesindeki
   *  "index <= activeIndex" ilkesinin dikey/3-bantlı hâli — banttan DÜŞÜK
   *  ya da EŞİT olan bütün segmentler yanıyor, tek bir nokta değil. */
  function renderRiskVBar(ts) {
    if (!riskVBarEl) return;
    const level = riskAt(ts);
    const band = riskBandFor(level);
    riskVBarEl.classList.toggle("hidden", !band);
    const rank = band ? RISK_BAND_RANK[band] : 0;
    riskVBarEl.querySelectorAll(".rv-seg").forEach((seg) => {
      seg.dataset.active = RISK_BAND_RANK[seg.dataset.band] <= rank ? "true" : "false";
    });
    riskVBarEl.title = level
      ? `O andaki risk seviyesi: ${level}` : "O andaki risk seviyesi";
  }

  // ===========================================================================
  // Zaman çizelgesi — işaretçiler + belirsizlik bantları
  // ===========================================================================

  function renderProgress() {
    if (!st.duration) return;
    const ratio = Math.min(1, Math.max(0, video.currentTime / st.duration));
    progressEl.style.width = `${ratio * 100}%`;
  }

  function renderFrontier() {
    if (!st.duration) {
      frontierEl.classList.add("hidden");
      return;
    }
    const beyond = st.duration - st.processedUntil;
    if (beyond <= 0.5) {
      frontierEl.classList.add("hidden");
      frontierEl.style.width = "0";
      return;
    }
    frontierEl.classList.remove("hidden");
    frontierEl.style.width = `${(beyond / st.duration) * 100}%`;
  }

  function renderDeferredSegments() {
    deferredEl.textContent = "";
    if (!st.duration) return;
    // `GET .../windows` damgaları `mmss()` ile SANİYEYE KIRPILMIŞ geliyor
    // (`int(ts)`, gozcu/agents/orchestrator.py:252) ama `pending_deferred_ts`
    // `Session.pending_deferred_ts()`'ten HAM float (`window[0].ts`) — aynı
    // pencerenin aynı alanı, iki farklı hassasiyette. Eşleştirme bu yüzden
    // `Math.floor` ile mmss'in kırpmasını taklit ediyor; tam float eşitliği
    // fraksiyonlu gözlem zamanlarında (ör. 10.333 s) hiç tutmazdı.
    const pendingFloors = new Set(
      [...st.pendingDeferred].map((value) => Math.floor(value)));
    for (const win of st.windows) {
      if (win.outcome !== "deferred" || !pendingFloors.has(win.tsSec)) continue;
      const left = (win.tsSec / st.duration) * 100;
      const width = Math.max(0, ((win.endSec - win.tsSec) / st.duration) * 100);
      const segment = document.createElement("div");
      segment.className = "segment";
      segment.style.left = `${left}%`;
      segment.style.width = `${width}%`;
      segment.title = "Bu pencere görü kesintisi yüzünden ertelendi — "
        + "telafi henüz tamamlanmadı, sonucu belirsiz.";
      deferredEl.appendChild(segment);
    }
  }

  function markerClassFor(entry) {
    return entry.kind === "escalation" ? "marker is-escalation" : "marker";
  }

  // Zaman çizelgesi YALNIZ olay taşıyan girdileri işaretliyor — plan §8.1'in
  // istediği tam olarak bu: `Episode.start_ts`/`EventBeat.ts` (ikisi de
  // sunucuda `entry.ts`'e zaten damgalanmış, bkz.
  // gozcu/ui/feed.py::_episode_entry). `gozcu/ui/feed.py` `window`
  // (algı satırı), `handoff`, `interpretation`, `risk`, `dialogue`,
  // `approval`, `action`, `window_update` gibi başka `kind`'lar da yazıyor —
  // hepsi beslemede (Olay Günlüğü) zaten görünür, ama bu ekran jüri
  // demosunun SÜREKLİ açık kaldığı ekran: her ajan devrine bir nokta koymak
  // "olay nerede oldu" sorusunu cevaplayan tek öğeyi gürültüye boğar.
  //
  // Bilerek İZİN LİSTESİ (deny-list DEĞİL): `feed.py`'ye yeni bir `kind`
  // eklenirse burada sessizce işaretlenmeye BAŞLAMASIN — yalnız bu listeye
  // BİLİNÇLİ eklenen bir tür zaman çizelgesine çıkar.
  const TIMELINE_MARKER_KINDS = new Set(["episode", "episode_update", "escalation"]);

  function renderMarkers(feed) {
    markersEl.textContent = "";
    if (!st.duration) return;
    for (const entry of feed) {
      if (!TIMELINE_MARKER_KINDS.has(entry.kind)) continue;
      const marker = document.createElement("div");
      marker.className = markerClassFor(entry);
      marker.style.left = `${(entry.ts / st.duration) * 100}%`;
      marker.title = `${entry.title} — tıklayınca video bu ana atlar`;
      if (entry.risk) {
        const color = meta.risk_colors && meta.risk_colors[entry.risk];
        if (color) marker.style.background = color;
      }
      marker.addEventListener("click", (event) => {
        event.stopPropagation();
        video.currentTime = entry.ts;
      });
      markersEl.appendChild(marker);
    }
  }

  timelineEl.addEventListener("click", (event) => {
    if (!st.duration) return;
    const rect = timelineEl.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    video.currentTime = ratio * st.duration;
  });

  async function refreshWindows() {
    if (st.runId === null) return;
    try {
      const response = await fetch(`/api/run/${st.runId}/windows`);
      if (!response.ok) return;
      const rows = await response.json();
      st.windows = rows.map((row) => ({
        tsSec: parseMmss(row.ts),
        endSec: parseMmss(row.end_ts),
        outcome: row.outcome,
      })).filter((row) => row.tsSec !== null && row.endSec !== null);
    } catch { /* çekilemezse önceki liste kalır */ }
  }

  // ===========================================================================
  // Dış arayüz
  // ===========================================================================

  let meta = { risk_colors: {} };

  function onLoadedMetadata() {
    st.duration = video.duration || 0;
    renderFrontier();
    renderMarkers(lastFeed);
    renderDeferredSegments();
    onTimeTick();
  }
  video.addEventListener("loadedmetadata", onLoadedMetadata);
  video.addEventListener("timeupdate", onTimeTick);
  video.addEventListener("seeked", onTimeTick);

  // Pencere/oynatıcı boyutu değişince (ör. tarayıcı yeniden boyutlanınca)
  // kutular AYNI karede kalsa da ekran pikselleri kayar — yeniden çiziyoruz.
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => drawBoxesAt(video.currentTime));
    observer.observe(video);
  }

  let lastFeed = [];

  return {
    setRunId(runId) {
      st.runId = runId;
      st.frameSize = null;
      st.detFrom = null;
      st.detTo = null;
      st.detItems = [];
      st.duration = 0;
      st.processedUntil = 0;
      st.pendingDeferred = new Set();
      st.windows = [];
      lastFeed = [];
      clearBoxes();
      frontierEl.classList.add("hidden");
      deferredEl.textContent = "";
      markersEl.textContent = "";
      progressEl.style.width = "0";
      if (riskVBarEl) riskVBarEl.classList.add("hidden");
    },

    /** Her SSE `state` çerçevesinde çağrılıyor — sse.js::renderState. */
    applyState(state, wireMeta) {
      meta = wireMeta || meta;
      lastFeed = state.feed;
      st.processedUntil = state.processed_until_s || 0;
      st.pendingDeferred = new Set(state.pending_deferred_ts || []);
      if (!st.duration) st.duration = video.duration || 0;
      renderFrontier();
      renderMarkers(state.feed);
      renderRiskVBar(video.currentTime);
      refreshWindows().then(renderDeferredSegments);
    },
  };
}
