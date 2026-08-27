// SSE bağlantısı, artımlı çizim ve Operasyon görünümünün komut kabloları.
//
// Tel TAM durum taşıyor (`gozcu/ui/server.py::_snapshot`), çizim artımlı:
// gördüğümüz en yüksek `seq`'i tutup yalnız YENİLERİ DOM'a ekliyoruz.
// Kaydırma konumu böyle korunuyor (spec, Görev 6 Adım 3).
//
// Karar veren hiçbir şey burada yok: risk rengi, ajan rozeti, güven metni,
// rozet/durum etiketleri ve risk seviyesinin kendisi sunucudan geliyor
// (`/api/meta`'nın `risk_colors`/`risk_levels`/`agent_marks`/`badge_labels`/
// `run_state_labels` alanları, `state.badges`, `entry.risk`/`confidence`).
// Bu dosya yalnız çiziyor, `fetch` çağırıyor ve MM:SS/piksel gibi ölçek
// aritmetiği yapıyor.

import { initFeedLog, formatParams, formatTime } from "./feed.js";
import { createPlayer } from "./player.js";
import { createTrace } from "./trace.js";
import { createBench } from "./bench.js";
import { createToolToasts } from "./tooltoast.js";
import { createCharts } from "./charts.js";
import { createRiskBar } from "./riskbar.js";
import { createMemory } from "./memory.js";
import { createAgents } from "./agents.js";

const els = {
  riskBar: document.getElementById("riskBar"),
  riskBarLabel: document.getElementById("riskBarLabel"),
  chartWrap: document.getElementById("chartWrap"),
  chartEntity: document.getElementById("chartEntity"),
  chartEntityLegend: document.getElementById("chartEntityLegend"),
  chartEnergy: document.getElementById("chartEnergy"),
  chartEnergyNote: document.getElementById("chartEnergyNote"),
  moduleButtons: document.querySelectorAll(".mod-btn"),
  views: {
    ops: document.getElementById("viewOps"),
    bench: document.getElementById("viewBench"),
    trace: document.getElementById("viewTrace"),
    say: document.getElementById("viewSay"),
    memory: document.getElementById("viewMemory"),
    agents: document.getElementById("viewAgents"),
  },
  toastWrap: document.getElementById("toastWrap"),
  jsonButton: document.getElementById("jsonButton"),
  jsonModal: document.getElementById("jsonModal"),
  jsonView: document.getElementById("jsonView"),
  closeJsonModal: document.getElementById("closeJsonModal"),
  copyJsonButton: document.getElementById("copyJsonButton"),
  downloadJsonButton: document.getElementById("downloadJsonButton"),

  runIdLabel: document.getElementById("runIdLabel"),
  sourcePicker: document.getElementById("sourcePicker"),
  playerHolder: document.getElementById("playerHolder"),
  pausedBanner: document.getElementById("pausedBanner"),
  resumeButton: document.getElementById("resumeButton"),
  videoPlayer: document.getElementById("videoPlayer"),
  playPauseButton: document.getElementById("playPauseButton"),
  rewindButton: document.getElementById("rewindButton"),
  forwardButton: document.getElementById("forwardButton"),
  speedSelect: document.getElementById("speedSelect"),
  ctrlTimeLabel: document.getElementById("ctrlTimeLabel"),
  agentStatusBadge: document.getElementById("agentStatusBadge"),
  agentStatusLabel: document.getElementById("agentStatusLabel"),
  runErrorBanner: document.getElementById("runErrorBanner"),
  boxOverlay: document.getElementById("boxOverlay"),
  layerCtrl: document.getElementById("layerCtrl"),
  layerCount: document.getElementById("layerCount"),
  boxLayerButton: document.getElementById("btnLayerBox"),
  labelLayerButton: document.getElementById("btnLayerLabel"),
  timeline: document.getElementById("timeline"),
  timelineFrontier: document.getElementById("timelineFrontier"),
  timelineDeferred: document.getElementById("timelineDeferred"),
  timelineMarkers: document.getElementById("timelineMarkers"),
  timelineProgress: document.getElementById("timelineProgress"),
  riskVBar: document.getElementById("riskVBar"),

  uploadCard: document.getElementById("cardUpload"),
  videoFile: document.getElementById("videoFile"),

  gatewayCutButton: document.getElementById("gatewayCutButton"),
  gatewayRestoreButton: document.getElementById("gatewayRestoreButton"),
  stressContextButton: document.getElementById("stressContextButton"),
  stressFalseInfoButton: document.getElementById("stressFalseInfoButton"),
  stressOverreachButton: document.getElementById("stressOverreachButton"),
  annotateButton: document.getElementById("annotateButton"),
  annotateNote: document.getElementById("annotateNote"),

  pendingApproval: document.getElementById("pendingApproval"),
  navSayBadge: document.getElementById("navSayBadge"),
  pendingTool: document.getElementById("pendingTool"),
  pendingParams: document.getElementById("pendingParams"),
  approveButton: document.getElementById("approveButton"),
  rejectButton: document.getElementById("rejectButton"),

  sayForm: document.getElementById("sayForm"),
  chatLog: document.getElementById("chatLog"),
  chatIntro: document.getElementById("chatIntro"),
  sayInput: document.getElementById("sayInput"),
  sayButton: document.getElementById("sayButton"),
  sayNote: document.getElementById("sayNote"),
  micButton: document.getElementById("micButton"),

  decisionMeta: document.getElementById("decisionMeta"),
  riskGauge: document.getElementById("riskGauge"),
  riskValue: document.getElementById("riskValue"),
  riskSteps: document.getElementById("riskSteps"),
  summaryText: document.getElementById("summaryText"),
  actionsList: document.getElementById("actionsList"),

  feedList: document.getElementById("feedList"),
  feedEmpty: document.getElementById("feedEmpty"),
  eventCount: document.getElementById("eventCount"),
  eventSearch: document.getElementById("eventSearch"),
  filterChips: document.querySelectorAll(".chip[data-filter]"),

  chainDiagram: document.getElementById("chainDiagram"),
  chainDiagramText: document.getElementById("chainDiagramText"),
  reasoningToggle: document.getElementById("reasoningToggle"),
  toolWrap: document.getElementById("toolWrap"),
  handoffList: document.getElementById("handoffList"),
  handoffEmpty: document.getElementById("handoffEmpty"),
  handoffCount: document.getElementById("handoffCount"),
  windowList: document.getElementById("windowList"),
  windowEmpty: document.getElementById("windowEmpty"),
  windowCount: document.getElementById("windowCount"),
  rootCauseBody: document.getElementById("rootCauseBody"),
  rootCauseMessage: document.getElementById("rootCauseMessage"),
  toolTableBody: document.getElementById("toolTableBody"),
  toolEmpty: document.getElementById("toolEmpty"),
  toolCount: document.getElementById("toolCount"),

  benchPerceptionMessage: document.getElementById("benchPerceptionMessage"),
  benchPerceptionBlocks: document.getElementById("benchPerceptionBlocks"),
  benchDecisionTiles: document.getElementById("benchDecisionTiles"),
  benchDistChart: document.getElementById("benchDistChart"),
  benchDistLegend: document.getElementById("benchDistLegend"),
  benchDistMessage: document.getElementById("benchDistMessage"),
  benchTokenTiles: document.getElementById("benchTokenTiles"),
  benchRunStatus: document.getElementById("benchRunStatus"),
  benchRunStatusValue: document.getElementById("benchRunStatusValue"),
  benchDegradedNotice: document.getElementById("benchDegradedNotice"),
  benchPerformanceTiles: document.getElementById("benchPerformanceTiles"),
};

const app = {
  runId: null,
  lastSeq: -1,
  source: null,
  //: Dosya seçilir seçilmez koşu başladığı için, iki olayın (kart
  //: tıklaması ve sürükle-bırak) aynı dosyayı iki kez göndermesini
  //: bu bayrak engelliyor.
  starting: false,
  meta: { risk_levels: [], risk_colors: {}, live_run_states: [],
          stt_available: false },
  payloadFetched: false,
  //: Yük GERÇEKTEN çekildi mi. `payloadFetched` yalnız "denendi" diyor;
  //: koşu çöktüğünde çekme başarısız oluyor ve karar paneli "analiz
  //: tamamlandı" DEMEMELİ.
  payloadLoaded: false,
  //: Karar panelinin üst satırı için — ikisi de ÖLÇÜLEN değer: besleme
  //: girdisi sayısı (`state.feed`) ve koşu başından beri geçen süre
  //: (`state.elapsed_s`, `session.elapsed_s()`). Model çıkarım gecikmesi
  //: gibi bir üçüncü sayı BİLEREK yok — bu sistem onu ölçmüyor.
  feedCount: 0,
  elapsedS: null,
  //: `#jsonView` teslim edilen çıktıyı mı yoksa yokluğunun GEREKÇESİNİ mi
  //: taşıyor. Gerekçe cümlesini `.json` diye indirtmek olmayan bir teslimi
  //: iddia etmek olurdu — kopyala/indir tuşları buna göre açılıyor.
  jsonIsPayload: false,
};

// Kutu katmanı, zaman çizelgesi ve belirsizlik çizimi — Görev 7. Karar
// veren hiçbir şey burada da yok: `player.js` yalnız `/detections`,
// `/windows` ve SSE durumunu (`processed_until_s`, `pending_deferred_ts`)
// okuyup ölçek aritmetiği yapıyor.
const player = createPlayer({
  video: els.videoPlayer,
  overlay: els.boxOverlay,
  timelineEl: els.timeline,
  frontierEl: els.timelineFrontier,
  deferredEl: els.timelineDeferred,
  markersEl: els.timelineMarkers,
  progressEl: els.timelineProgress,
  boxCountEl: els.layerCount,
  riskVBarEl: els.riskVBar,
});

// Ajanlar görünümü — karar üreten hiçbir şey burada da yok: `agents.js`
// yalnız düğüm/kablo/paket çiziyor, akış bugün TEMSİLÎ (bkz. o dosyanın
// başlığındaki gerekçe ve `#agentsFlowMode` rozeti).
const agents = createAgents({
  svgEl: document.getElementById("agentsSvg"),
  modeEl: document.getElementById("agentsFlowMode"),
  legendEl: document.getElementById("agentsLegend"),
  tipEl: document.getElementById("agentsTip"),
  zoomEls: {
    inEl: document.getElementById("agentsZoomIn"),
    outEl: document.getElementById("agentsZoomOut"),
    resetEl: document.getElementById("agentsZoomReset"),
    levelEl: document.getElementById("agentsZoomLevel"),
  },
});

// Araç çağrı bildirimleri — besleme kaynağı `trace.js`'in ZATEN çektiği
// araç defteri; ikinci bir uç yok (bkz. js/tooltoast.js).
const toolToasts = createToolToasts({ wrapEl: els.toolWrap });

// Video altındaki iki canlı grafik. Zaman kancası `player.js`'ten DEĞİL
// doğrudan `<video>` olaylarından geliyor: oynatıcı bir zaman geri çağrısı
// dışa vermiyor ve grafikler için oraya bir tane eklemek, ilgisiz iki
// modülü birbirine bağlardı.
const charts = createCharts({
  wrapEl: els.chartWrap,
  entitySvg: els.chartEntity,
  entityLegendEl: els.chartEntityLegend,
  energySvg: els.chartEnergy,
  energyNoteEl: els.chartEnergyNote,
  onSeries: (payload) => riskBar.setTrack(payload.risk),
});
// Grafikler BAŞTAN tam çizili; video olayları yalnız dikey imleci
// taşıyor. Veri en baştan elimizde ve operatörden onu görmek için videoyu
// sonuna kadar izlemesini istemek, sahip olduğumuz bilgiyi saklamaktı.
els.videoPlayer.addEventListener("timeupdate", () => {
  charts.seek(els.videoPlayer.currentTime);
});
els.videoPlayer.addEventListener("seeked", () => {
  charts.seek(els.videoPlayer.currentTime);
});

// Risk durum çubuğu videonun O ANKİ karesini gösteriyor, o yüzden
// grafiklerden farklı olarak geri sarınca GERİ DÜŞÜYOR: 10. saniyeye dönüp
// hâlâ kırmızı yanmak, o anda olmayan bir tehlikeyi gösterirdi.
const riskBar = createRiskBar({
  barEl: els.riskBar,
  labelEl: els.riskBarLabel,
});
els.videoPlayer.addEventListener("timeupdate", () => {
  riskBar.seek(els.videoPlayer.currentTime);
});
els.videoPlayer.addEventListener("seeked", () => {
  riskBar.seek(els.videoPlayer.currentTime);
});

// Kısa bildirim şeridi. `.toast-wrap`/`.toast` kabuğu styles.css'te ZATEN
// vardı ama hiçbir JS onu doldurmuyordu — Hafıza görünümünün yükleme/silme
// geri bildirimi ilk kullanıcısı. `tooltoast.js`'in KARTLARI ayrı bir şey:
// orası araç çağrı defterinden besleniyor, burası tek cümlelik bir bildirim.
const TOAST_MS = 3200;

function showToast(text, kind = "") {
  if (!els.toastWrap || !text) return;
  const node = document.createElement("div");
  node.className = kind ? `toast ${kind}` : "toast";
  node.textContent = text;
  els.toastWrap.appendChild(node);
  setTimeout(() => node.remove(), TOAST_MS);
}

// Hafıza görünümü — kütüphane (`/api/library/*`). Karar veren hiçbir şey
// burada da yok: `memory.js` yalnız iki listeyi çekip çiziyor.
const memory = createMemory({ onToast: showToast });

// Şeffaflık görünümü — Görev 8. Karar veren hiçbir şey burada da yok:
// `trace.js` yalnız `/handoffs`, `/actions`, `/windows`'ı çekip çiziyor.
const trace = createTrace({
  chainEl: els.chainDiagram,
  chainTextEl: els.chainDiagramText,
  handoffListEl: els.handoffList,
  handoffEmptyEl: els.handoffEmpty,
  handoffCountEl: els.handoffCount,
  windowListEl: els.windowList,
  windowEmptyEl: els.windowEmpty,
  windowCountEl: els.windowCount,
  toolBodyEl: els.toolTableBody,
  toolEmptyEl: els.toolEmpty,
  toolCountEl: els.toolCount,
  rootCauseBodyEl: els.rootCauseBody,
  rootCauseMessageEl: els.rootCauseMessage,
  onNewTools(rows) {
    rows.forEach((action) => toolToasts.push(action));
  },
});

// Şeffaflık sayfasının "Düşünce Sürecini Gör" anahtarı — devir
// gerekçelerini açıp kapatıyor (bkz. `trace.js::setReasoningVisible`).
els.reasoningToggle.addEventListener("change", () => {
  trace.setReasoningVisible(els.reasoningToggle.checked);
});

// Performans görünümü — Görev 9. Karar veren hiçbir şey burada da yok:
// `bench.js` yalnız `/kpi`'yi çekip çiziyor; ölçülemeyen KPI'lar
// gizlenmiyor, bozulmuş koşu ayrı bir uyarıyla damgalanıyor.
const bench = createBench({
  perceptionMessageEl: els.benchPerceptionMessage,
  perceptionBlocksEl: els.benchPerceptionBlocks,
  decisionTilesEl: els.benchDecisionTiles,
  distChartEl: els.benchDistChart,
  distLegendEl: els.benchDistLegend,
  distMessageEl: els.benchDistMessage,
  tokenTilesEl: els.benchTokenTiles,
  runStatusBadgeEl: els.benchRunStatus,
  runStatusValueEl: els.benchRunStatusValue,
  degradedNoticeEl: els.benchDegradedNotice,
  performanceTilesEl: els.benchPerformanceTiles,
});

const feedLog = initFeedLog({
  listElement: els.feedList,
  emptyElement: els.feedEmpty,
  countElement: els.eventCount,
  searchInput: els.eventSearch,
  filterButtons: els.filterChips,
  onSeek(ts) {
    if (els.videoPlayer && Number.isFinite(ts)) {
      els.videoPlayer.currentTime = ts;
    }
  },
});

// =============================================================================
// Özel oynatıcı denetimleri — oynat/duraklat, 10 sn ileri/geri, hız seçici.
// Tarayıcının yerleşik `<video controls>`'unun yerine geçiyor; burada da
// karar üretilmiyor, yalnız `videoPlayer` üzerinde ölçek aritmetiği
// (`player.js::place` ile aynı ilke).
// =============================================================================

function updatePlayPauseIcon() {
  const playing = !els.videoPlayer.paused && !els.videoPlayer.ended;
  els.playPauseButton.querySelector(".icon-play").classList.toggle("hidden", playing);
  els.playPauseButton.querySelector(".icon-pause").classList.toggle("hidden", !playing);
}

function updateCtrlTimeLabel() {
  els.ctrlTimeLabel.textContent =
    `${formatTime(els.videoPlayer.currentTime)} / ${formatTime(els.videoPlayer.duration)}`;
}

els.playPauseButton.addEventListener("click", () => {
  if (els.videoPlayer.paused || els.videoPlayer.ended) {
    els.videoPlayer.play();
  } else {
    els.videoPlayer.pause();
  }
});
els.rewindButton.addEventListener("click", () => {
  els.videoPlayer.currentTime = Math.max(0, els.videoPlayer.currentTime - 10);
});
els.forwardButton.addEventListener("click", () => {
  const duration = els.videoPlayer.duration || Infinity;
  els.videoPlayer.currentTime = Math.min(duration, els.videoPlayer.currentTime + 10);
});
els.speedSelect.addEventListener("change", () => {
  els.videoPlayer.playbackRate = Number(els.speedSelect.value) || 1;
});
/** Taşıma düğmeleri `index.html`'de `disabled` DOĞUYOR ve buraya kadar
 *  hiçbir yerde açılmıyordu: tıklama dinleyicileri bağlıydı ama devre dışı
 *  bir düğme tıklama üretmez — oynat/ileri/geri üçü de ÖLÜYDÜ ve video hiç
 *  oynatılamıyordu (ölçüldü). Açılma anı `loadedmetadata`: süre bilinmeden
 *  ileri sarma `Math.min(duration, ...)` üzerinden `NaN` yazardı. */
function setTransportEnabled(enabled) {
  [els.playPauseButton, els.rewindButton, els.forwardButton]
    .forEach((button) => { button.disabled = !enabled; });
}
els.videoPlayer.addEventListener("loadedmetadata", () => {
  setTransportEnabled(true);
});
//: Kaynak yüklenemezse düğmeler AÇILMIYOR — çalışmayan bir oynatıcının
//: açık düğmesi, tıklandığında sessizce hiçbir şey yapar.
els.videoPlayer.addEventListener("error", () => setTransportEnabled(false));

els.videoPlayer.addEventListener("play", updatePlayPauseIcon);
els.videoPlayer.addEventListener("pause", updatePlayPauseIcon);
els.videoPlayer.addEventListener("timeupdate", updateCtrlTimeLabel);
els.videoPlayer.addEventListener("loadedmetadata", updateCtrlTimeLabel);

// =============================================================================
// Yardımcılar
// =============================================================================

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch { /* gövdesiz yanıt */ }
  return { ok: response.ok, status: response.status, data };
}



function showRunError(text) {
  els.runErrorBanner.textContent = text;
  els.runErrorBanner.classList.toggle("hidden", !text);
}

// =============================================================================
// Modül anahtarı — video DOM'da kalıyor, sekme değişince oynatma kesilmiyor
// =============================================================================

function showView(name) {
  Object.entries(els.views).forEach(([key, el]) => {
    el.classList.toggle("hidden", key !== name);
  });
  els.moduleButtons.forEach((button) => {
    button.classList.toggle("on", button.dataset.view === name);
  });
  // Kütüphane AÇILIŞTA değil, GÖRÜNÜNCE tazeleniyor: iki `fetch`'i her sayfa
  // yüklemesinde harcamanın anlamı yok, üstelik liste sekme dışındayken
  // (yeni koşu bitmişken) bayatlıyor ve sekmeye dönen operatör eski listeyi
  // görürdü.
  if (name === "memory") memory.load();
  // Sekmeden çıkınca durduruluyor (`agents.js`'in kendi sözleşmesi):
  // görünmeyen bir sayfa için her karede paket yürütmek boşuna CPU.
  agents.stop();
  if (name === "agents") agents.start();
}

els.moduleButtons.forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

//: Panel içindeki "Ayrıntılı panel →" / "Tam görünüm →" kısayolları da
//: aynı anahtarı kullanıyor; yoksa tuşlar ölü kalıyordu.
document.querySelectorAll("[data-goto]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.goto));
});

document.addEventListener("keydown", (event) => {
  if (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA") return;
  if (event.key === "1") showView("ops");
  if (event.key === "2") showView("bench");
  if (event.key === "3") showView("trace");
  if (event.key === "5") showView("memory");
  if (event.key === "4") showView("say");
  if (event.key === "6") showView("agents");
  if (event.key === "b" || event.key === "B") els.boxLayerButton.click();
});

// =============================================================================
// Katman tuşları — çizimi değil yalnız GÖRÜNÜRLÜĞÜ değiştiriyor
// =============================================================================

function wireLayerToggle(button, className) {
  button.addEventListener("click", () => {
    const off = els.boxOverlay.classList.toggle(className);
    button.classList.toggle("on", !off);
  });
}

wireLayerToggle(els.boxLayerButton, "no-boxes");
wireLayerToggle(els.labelLayerButton, "no-labels");

// =============================================================================
// Açılış durumu (`/api/status`) — yalnız model kimliği ve canlı koşuya
// yeniden bağlanma. AĞ GEÇİDİ/HAFIZA/KOŞU rozetleri üst bardan kaldırıldı;
// `status.gateway`/`status.memory` ve SSE `badges` telde DURUYOR, üst bar
// artık onları çizmiyor.
// =============================================================================

async function loadInitialStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    // `status.memory` = `memory_backend()`. Hafıza görünümünün rozeti bunu
    // basıyor: `"local"` sessiz bir düşüş ve görünmez kalmamalı.
    memory.setBackend(status.memory);
    reattachIfLive(status);
  } catch { /* sunucu henüz ayakta değilse rozetler "—" kalır */ }
}

// =============================================================================
// Yeniden bağlanma — canlı koşunun ortasında sayfa yenilenirse
//
// `app.runId` sayfada YAŞIYOR: bir Cmd-R onu sıfırlıyordu ve konsol öksüz
// kalıyordu — SSE açılmıyor, her komut sessizce geri dönüyor, "Analizi
// Başlat" ise `409 "Bir koşu zaten sürüyor."` alıyordu. Koşan iş parçacığı
// durdurulamadığı için geri dönüş de yoktu. Sunucu `GET /api/status`'ta
// `run_id`/`run_state`/`step_mode` taşıyor; açılışta koşu HÂLÂ CANLIYSA
// yükleme akışının yaptığı kablolamanın aynısı yapılıyor.
//
// Canlılık koşulu SUNUCUDAN (`/api/meta.live_run_states`): bitmiş bir
// koşuya geri bağlanmak kaynak seçiciyi gizler ve operatörün bir sonraki
// videoyu başlatmasını engellerdi.
// =============================================================================

function isLiveRunState(state) {
  return (app.meta.live_run_states || []).includes(state);
}

function reattachIfLive(status) {
  if (!status || !status.run_id || !isLiveRunState(status.run_state)) return;
  attachRun(status.run_id);
}

async function loadMeta() {
  // `agentMarkFor`/`runStateLabelFor` hepsi bu nesneye
  // bakıyor — meta yüklenmeden önce çağrılırlarsa ham değere düşüyorlar,
  // asla uydurmuyorlar.
  try {
    const response = await fetch("/api/meta");
    app.meta = await response.json();
  } catch {
    app.meta = { risk_levels: [], risk_colors: {}, agent_marks: {},
                 badge_labels: {}, run_state_labels: {}, stt_available: false };
  }
  buildRiskSteps();
  trace.setMeta(app.meta);
  bench.setMeta(app.meta);
  // Risk çubuğu da renklerini SUNUCUDAN alıyor — `gozcu/ui/feed.py::
  // RISK_COLORS`. JS'te ikinci bir renk tablosu yazılmıyor.
  riskBar.setMeta(app.meta);
  agents.setMeta(app.meta);
  memory.setMeta(app.meta);
  updateMicAvailability();
}

// =============================================================================
// Bas-konuş (STT) düğmesi — `faster-whisper` kurulu değilse SUNUCU söylüyor
// (`/api/meta.stt_available`), buton bir kayıt denemeden ÖNCE devre dışı
// çiziliyor; tahmin JS'te YOK (Görev 10).
// =============================================================================

function updateMicAvailability() {
  els.micButton.dataset.unavailable = app.meta.stt_available ? "" : "true";
  if (!app.meta.stt_available) {
    els.micButton.disabled = true;
    els.micButton.title = "Yerel konuşma tanıma kurulu değil.";
  } else {
    els.micButton.disabled = !app.runId;
    els.micButton.title = "Basılı tutup konuşun";
  }
}

function runStateLabelFor(state) {
  return (app.meta.run_state_labels && app.meta.run_state_labels[state]) || state;
}

function buildRiskSteps() {
  els.riskSteps.innerHTML = "";
  app.meta.risk_levels.forEach((level) => {
    const step = document.createElement("i");
    step.dataset.level = level;
    els.riskSteps.appendChild(step);
  });
}

// =============================================================================
// Risk göstergesi — DÖRT kademe, renk `/api/meta.risk_colors`'tan (Adım 5)
// =============================================================================

function renderRisk(level) {
  els.riskValue.textContent = level || "—";
  const color = level ? app.meta.risk_colors[level] : null;
  //: "Kritik"in ayrı bir görsel ağırlığı var (styles.css eki); rengi hâlâ
  //: sunucudan geliyor, buradaki tek karar seviyeyi DOM'a yazmak.
  els.riskGauge.dataset.level = level || "none";
  els.riskGauge.style.borderColor = color || "";
  els.riskGauge.style.background = color ? `${color}14` : "";
  els.riskValue.style.color = color || "";

  const levels = app.meta.risk_levels;
  const activeIndex = level ? levels.indexOf(level) : -1;
  els.riskSteps.querySelectorAll("i").forEach((step, index) => {
    const stepLevel = step.dataset.level;
    step.style.background = index <= activeIndex
      ? (app.meta.risk_colors[stepLevel] || "")
      : "";
  });
}

let lastKnownRisk = null;

function trackRiskFromEntries(entries) {
  for (const entry of entries) {
    if (entry.risk) lastKnownRisk = entry.risk;
  }
}

// =============================================================================
// Bekleyen onay çubuğu — `pending.params` HAM sözlük, tire kuralı burada
// =============================================================================

function renderPending(pending) {
  const isPending = pending !== null && pending !== undefined;
  els.pendingApproval.classList.toggle("hidden", !isPending);
  //: Onay çubuğu artık ayrı bir sekmede. Operatör başka sekmedeyken
  //: bekleyen onayı kaçırmasın diye gezinme rozeti gerçek bekleme
  //: durumunu yansıtıyor — uydurma bir sayı değil, aynı bayrak.
  els.navSayBadge.classList.toggle("hidden", !isPending);
  if (!isPending) {
    els.pendingTool.dataset.actionId = "";
    return;
  }
  els.pendingTool.textContent = pending.tool;
  els.pendingTool.dataset.actionId = String(pending.action_id);
  els.pendingParams.textContent = formatParams(pending.params);
}

// =============================================================================
// Koşu tamamlanınca dört anahtarı çek — `summary`/`risk`/`actions`
// =============================================================================

// =============================================================================
// Aksiyon önerileri — satır kabuğu mockup'tan, İÇERİK backend'den
//
// `.action-prio` rozeti BİLEREK yok: `PipelineOutput.actions` düz bir dize
// listesi (`gozcu/models.py`), öncelik alanı YOK. "NORMAL"/"KRİTİK" diye bir
// rozet basmak modelin söylemediği bir şeyi söylemek olurdu.
//
// Onay yerel bir işaretleme: hiçbir yere `POST` edilmiyor. Ajanın yetki
// isteyen çağrısının GERÇEK onayı ayrı bir yer — sohbet panelindeki
// `#pendingApproval` çubuğu (`/api/run/{id}/approve`).
// =============================================================================

function renderActionRow(text) {
  const item = document.createElement("div");
  item.className = "action-item";

  const textEl = document.createElement("span");
  textEl.className = "action-text";
  textEl.textContent = text;

  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.className = "action-confirm";
  confirm.textContent = "Onayla";
  confirm.setAttribute("aria-pressed", "false");
  confirm.addEventListener("click", () => {
    const done = item.classList.toggle("done");
    confirm.textContent = done ? "Onaylandı" : "Onayla";
    confirm.setAttribute("aria-pressed", done ? "true" : "false");
  });

  item.append(textEl, confirm);
  return item;
}

function renderActions(actions) {
  els.actionsList.textContent = "";
  if (!actions || actions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-hint";
    empty.textContent = "Aksiyon önerisi yok.";
    els.actionsList.appendChild(empty);
    return;
  }
  actions.forEach((action) => els.actionsList.appendChild(renderActionRow(action)));
}

// =============================================================================
// Karar panelinin üst satırı — yalnız ÖLÇÜLEN iki sayı
//
// Olay sayısı besleme defterinin satır sayısı (`#eventCount` ile AYNI sayı,
// aynı kaynaktan), geçen süre `session.elapsed_s()`. Mockup'ın buradaki
// "gecikme: 240 ms" hücresi TAŞINMADI — bu sistem model çıkarım gecikmesini
// hiç ölçmüyor; ölçülmeyeni söyleyen üst şerit hücreleri de kaldırıldı.
// =============================================================================

// Durum cümlesi (`app.payloadLoaded ? … : runStateLabelFor(…)`) İKİ yerde
// yazılıyor ve İKİSİNDE de dokunulmadan bırakıldı — panelin gerçek koşu
// durumunu söylemesi ayrı bir kural ve ayrı bir testi var
// (`test_the_decision_panel_always_says_the_real_run_state`). Ölçülen sayılar
// o cümlenin ARDINA ekleniyor, yerine geçmiyor.
function appendDecisionMetrics() {
  const parts = [`${app.feedCount} olay`];
  if (Number.isFinite(app.elapsedS)) {
    // Ondalık ayırıcı virgül — sunucunun her sayıda yaptığı şeyin aynısı
    // (`view.pct`/`kpi_payload`: `.replace(".", ",")`).
    parts.push(`${app.elapsedS.toFixed(1).replace(".", ",")} sn`);
  }
  els.decisionMeta.textContent += ` · ${parts.join(" · ")}`;
}

async function loadFinalPayload() {
  if (app.payloadFetched || !app.runId) return;
  app.payloadFetched = true;
  try {
    const response = await fetch(`/api/run/${app.runId}/payload`);
    if (!response.ok) return;
    const payload = await response.json();
    els.summaryText.textContent = payload.summary;
    renderRisk(payload.risk);
    renderActions(payload.actions);
    app.payloadLoaded = true;
    els.decisionMeta.textContent = "analiz tamamlandı";
    appendDecisionMetrics();
  } catch { /* çekilemezse panel bir önceki hâlde kalır */ }
}

// =============================================================================
// Tam durum çizimi — SSE'nin her `state` çerçevesinde çağrılıyor
// =============================================================================

function renderState(state) {
  // Karar üst satırının iki ölçülen sayısı — çizimden ÖNCE, çünkü
  // `loadFinalPayload` de bunları okuyor.
  app.feedCount = state.feed.length;
  app.elapsedS = Number.isFinite(state.elapsed_s) ? state.elapsed_s : null;


  const isPaused = state.run_state === "paused";
  els.pausedBanner.classList.toggle("hidden", !isPaused);
  if (isPaused && !els.videoPlayer.paused) els.videoPlayer.pause();

  renderPending(state.pending);

  const running = isLiveRunState(state.run_state);
  els.agentStatusBadge.dataset.state = running ? "running" : "idle";
  els.agentStatusLabel.textContent = running ? "sürüyor" : "hazır";
  els.gatewayCutButton.disabled = !running;
  els.gatewayRestoreButton.disabled = !running;
  els.stressContextButton.disabled = !running;
  els.stressFalseInfoButton.disabled = !running;
  els.stressOverreachButton.disabled = !running;
  // Açıklamalı kayıt koşu BİTİNCE üretiliyor: `annotate_run` diskteki
  // bütün kareleri yeniden çiziyor, koşu sürerken kareler daha yazılıyor.
  els.annotateButton.disabled = !app.runId || running;
  els.sayInput.disabled = !app.runId;
  els.sayButton.disabled = !app.runId;
  els.jsonButton.disabled = !app.runId;
  updateMicAvailability();

  player.applyState(state, app.meta);
  // Grafikler de durumu görüyor: boş bir serinin "henüz ölçülmedi" mi
  // "ölçülemedi" mi olduğu koşunun canlılığına bağlı, ve seri henüz
  // hazır değilse yeniden çekiliyor (algı katmanı koşuya bağlanma anından
  // sonra bitiyor, ilk çekim boş dönebiliyor).
  charts.applyState(state, running);
  agents.applyState(state);
  // `running` (canlılık) trace'e AKTARILIYOR: koşu sürerken kök neden
  // sorusu hiç sorulmuyor (bkz. `trace.js::refreshRootCause`). Karar
  // burada bir kez veriliyor, orada yeniden hesaplanmıyor.
  trace.applyState(state, app.meta, running);
  bench.applyState(state, app.meta);

  renderChat(state.feed);
  trackRiskFromEntries(state.feed);
  if (state.run_state === "done" || state.run_state === "failed") {
    loadFinalPayload();
    // Koşu bitti: seri son hâliyle bir kez daha çekiliyor. Grafik burada
    // TAMAMEN AÇILMIYOR — açılma videonun saatine bağlı (Görev raporu §1)
    // ve boru hattı videodan hızlı bitiyor. Koşu bitti diye tüm zaman
    // çizelgesini basmak, operatöre henüz izlemediği saniyeleri gösterir
    // ve grafiğin videoyla senkron olma iddiasını bozardı.
    charts.load(app.runId);
  } else {
    renderRisk(lastKnownRisk);
  }
  // Karar paneli HER ZAMAN gerçek durumu söylüyor. Eskiden yalnız `else`
  // dalında yazılıyordu: koşu ÇÖKTÜĞÜNDE yük çekilemiyor ve panel son
  // değerinde ("sürüyor"/"müdahale edildi") DONUYORDU — afiş "hata",
  // JSON modalı "koşmadı" derken üçüncü bir cümle. "analiz tamamlandı"
  // yalnız yük GERÇEKTEN geldiyse yazılıyor (`app.payloadLoaded`).
  els.decisionMeta.textContent = app.payloadLoaded
    ? "analiz tamamlandı" : runStateLabelFor(state.run_state);
  appendDecisionMetrics();

  if (state.run_state === "failed") {
    showRunError("Koşu hata ile sonuçlandı — ayrıntı için JSON çıktısına bakın.");
  } else if (state.run_state === "abandoned") {
    showRunError("Koşu terk edildi — çıktı atıldı.");
  } else {
    showRunError("");
  }
}

// =============================================================================
// SSE bağlantısı
// =============================================================================

function connect(runId) {
  if (app.source) app.source.close();
  // KOŞU BAŞINA durum burada sıfırlanıyor — `player.js`/`trace.js`
  // `setRunId`'lerinde bunu zaten yapıyor, bu modül yapmıyordu: ikinci
  // koşunun girdileri birincinin altına ekleniyor, risk göstergesi de
  // önceki koşunun son seviyesinde kalıyordu.
  app.lastSeq = -1;
  app.payloadFetched = false;
  app.payloadLoaded = false;
  lastKnownRisk = null;
  feedLog.reset();
  renderRisk(null);
  const source = new EventSource(`/api/run/${runId}/events`);
  app.source = source;
  source.addEventListener("state", (message) => {
    const state = JSON.parse(message.data);
    for (const entry of state.feed) {
      if (entry.seq > app.lastSeq) {
        feedLog.append(entry, app.meta);
        app.lastSeq = entry.seq;
      }
    }
    renderState(state);
  });
  source.onerror = () => {
    // `EventSource` kendi kendine yeniden bağlanıyor (tarayıcı yerleşiği);
    // burada ekstra bir şey yapmıyoruz — bağlantı koptuğunda son bilinen
    // durum ekranda kalır, "koşu bitti" gibi yanlış bir şey İDDİA ETMİYORUZ.
  };
}

// =============================================================================
// Koşuya bağlanma — yükleme akışı ile yeniden bağlanma AYNI kabloyu kullanıyor
// =============================================================================

function attachRun(runId) {
  app.runId = runId;
  els.runIdLabel.textContent = runId;
  els.sourcePicker.classList.add("hidden");
  //: Oynatıcıyı görünür kılan sınıf `.on` — `styles.css` `.video-holder`u
  //: `display: none` doğuruyor ve YALNIZ `.on` ile açıyor. Burada
  //: `remove("hidden")` yazıyordu: `#playerHolder`da öyle bir sınıf hiç
  //: yok, yani çağrı boşa gidiyordu ve VİDEO HİÇ GÖRÜNMÜYORDU (ölçüldü).
  //: `hidden` de temizleniyor — iki mekanizmadan biri gelecekte eklenirse
  //: diğerini sessizce iptal etmesin.
  els.playerHolder.classList.remove("hidden");
  els.playerHolder.classList.add("on");
  // Katman şeridi bir koşu bağlanana kadar gizli duruyordu ve HİÇBİR yerde
  // açılmıyordu: `#btnLayerBox`/`#btnLayerLabel` kabloluydu ama görünmezdi.
  // Nesne sayacı da (`#layerCount`) bu şeridin içinde.
  els.layerCtrl.classList.remove("hidden");
  // Önceki koşunun araç kartları yeni koşunun köşesinde kalmasın.
  toolToasts.reset();
  player.setRunId(runId);
  // Grafikler koşunun BİTMESİNİ beklemiyor: algı da triyaj da karar
  // döngüsünden önce bitiyor, yani seri ilk saniyeden itibaren hazır.
  // Yeni koşu: oynatıcı yeniden yüklenene kadar taşıma kapalı.
  setTransportEnabled(false);
  charts.reset();
  charts.load(runId);
  riskBar.reset();
  chatShown = 0;
  agents.setRunId(runId);
  trace.setRunId(runId);
  bench.setRunId(runId);
  entityChart.setRunId(runId);
  entropyChart.setRunId(runId);
  els.videoPlayer.src = `/api/run/${runId}/video`;
  els.videoPlayer.load();
  connect(runId);
}

// =============================================================================
// Koşu başlatma
// =============================================================================

function acceptFile(file) {
  //: Ayrı bir "Analizi Başlat" tuşu YOK: dosya geldiği anda koşu başlıyor.
  //: `starting` bayrağı çift tetiklemeyi (kart tıklaması + bırakma) engelliyor.
  if (!file || app.starting) return;
  startRun(file);
}

els.videoFile.addEventListener("change", () => acceptFile(els.videoFile.files[0]));

//: Büyük "Video Yükle" kartı gizli dosya girdisinin yüzü — kart tıklanabilir
//: görünüyor, tıklanmazsa dosya seçmenin başka yolu yok.
els.uploadCard.addEventListener("click", () => els.videoFile.click());

//: Kartın kendi metni "sürükleyip bırakın" diyor; söz veriliyorsa çalışmalı.
["dragenter", "dragover"].forEach((name) => {
  els.sourcePicker.addEventListener(name, (event) => {
    event.preventDefault();
    els.sourcePicker.classList.add("is-dragging");
  });
});
["dragleave", "drop"].forEach((name) => {
  els.sourcePicker.addEventListener(name, () =>
    els.sourcePicker.classList.remove("is-dragging"));
});
els.sourcePicker.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = event.dataTransfer.files[0];
  if (!file) return;
  els.videoFile.files = event.dataTransfer.files;
  acceptFile(file);
});

async function startRun(file) {
  app.starting = true;
  showRunError("");

  const body = new FormData();
  body.append("video", file);
  //: Adım adım kipi arayüzden kaldırıldı — sunucudaki uç nokta duruyor,
  //: konsol koşuyu her zaman kesintisiz başlatıyor.
  body.append("step_mode", "false");

  try {
    const response = await fetch("/api/run", { method: "POST", body });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      showRunError(detail.detail || "Koşu başlatılamadı.");
      return;
    }
    const { run_id: runId } = await response.json();
    attachRun(runId);
  } catch {
    showRunError("Koşu başlatılamadı — sunucuya ulaşılamıyor.");
  } finally {
    app.starting = false;
    //: Aynı dosya art arda seçilebilsin diye girdi sıfırlanıyor; aksi hâlde
    //: `change` ikinci kez ateşlenmiyor.
    els.videoFile.value = "";
  }
}

// =============================================================================
// Komutlar — hepsi ince `POST` sarmalayıcıları, sonucu SSE'den okunuyor
// =============================================================================

els.resumeButton.addEventListener("click", async () => {
  if (!app.runId) return;
  await postJSON(`/api/run/${app.runId}/resume`);
});



els.gatewayCutButton.addEventListener("click", async () => {
  if (!app.runId) return;
  await postJSON(`/api/run/${app.runId}/gateway/cut`);
});

els.gatewayRestoreButton.addEventListener("click", async () => {
  if (!app.runId) return;
  await postJSON(`/api/run/${app.runId}/gateway/restore`);
});

function wireStressButton(button, key) {
  button.addEventListener("click", async () => {
    if (!app.runId) return;
    await postJSON(`/api/run/${app.runId}/stress/${key}`);
  });
}
wireStressButton(els.stressContextButton, "baglam");
wireStressButton(els.stressFalseInfoButton, "yanlis_bilgi");
wireStressButton(els.stressOverreachButton, "yetki_asimi");

// =============================================================================
// Açıklamalı kayıt — İSTEK ÜZERİNE (`POST .../annotate`)
//
// `annotate_run` bütün kareleri yeniden çiziyor ve bir kalp atışına sığmıyor
// (`gozcu/annotate.py:129`) — bu yüzden koşuyla birlikte DEĞİL, bu düğmeyle.
// Uç Görev 5'ten beri hazırdı ve testi de vardı, ama hiçbir düğme onu
// çağırmıyordu: emekliye ayrılan konsolda olan bir yetenek yenisinde
// kaybolmuştu.
// =============================================================================

els.annotateButton.addEventListener("click", async () => {
  if (!app.runId) return;
  els.annotateButton.disabled = true;
  els.annotateNote.textContent = "Açıklamalı kayıt üretiliyor…";
  const { ok, data } = await postJSON(`/api/run/${app.runId}/annotate`);
  if (!ok) {
    // Hata koşuyu DÜŞÜRMÜYOR (sunucu `409` + Türkçe `detail`), ekranda
    // görünüyor — cümle sunucudan, burada uydurulmuyor.
    els.annotateNote.textContent = (data && data.detail)
      || "Açıklamalı kayıt üretilemedi.";
    els.annotateButton.disabled = false;
    return;
  }
  els.annotateNote.textContent = "Açıklamalı kayıt oynatılıyor — kutular kareye çizili.";
  // Kutular artık kareye BASILI: canlı katman da çizseydi aynı kutu iki
  // kez görünürdü.
  els.boxOverlay.classList.add("hidden");
  // Katman tuşları ve nesne sayacı artık hiçbir şeyi denetlemiyor: kutular
  // karenin kendisine BASILI. Şeridi açık bırakmak ölü tuş göstermek olurdu.
  els.layerCtrl.classList.add("hidden");
  els.videoPlayer.src = data.path;
  els.videoPlayer.load();
});

els.approveButton.addEventListener("click", async () => {
  if (!app.runId) return;
  const actionId = Number(els.pendingTool.dataset.actionId);
  await submitApproval(actionId, true);
});
els.rejectButton.addEventListener("click", async () => {
  if (!app.runId) return;
  const actionId = Number(els.pendingTool.dataset.actionId);
  await submitApproval(actionId, false);
});

async function submitApproval(actionId, approved) {
  const { data } = await postJSON(`/api/run/${app.runId}/approve`,
    { action_id: actionId, approved });
  if (data && data.note) {
    els.sayNote.textContent = data.note;
  }
}

/** Operatörle ajanın konuşmasını "Operatöre Söyle" sayfasına çiziyor.
 *
 *  Bu kutu işaretlemede vardı, baloncuk stilleri de (`.chat-user`,
 *  `.chat-bot`, `.chat-ask`, `.chat-sys`) — ama hiçbir yerden
 *  DOLDURULMUYORDU. Operatör mesajını buraya yazıp cevabı başka sayfadaki
 *  olay günlüğünde aramak zorunda kalıyordu; ekranın kendi tanıtım cümlesi
 *  bile "sağdaki Olay Günlüğü'ne düşer" diyordu.
 *
 *  Kaynak beslemenin KENDİSİ (`state.feed`), ikinci bir uç yok: diyalog
 *  turları oraya zaten `kind: "dialogue"` olarak düşüyor.
 */
const CHAT_BUBBLE = { operator: "chat-user", supervisor: "chat-bot" };
let chatShown = 0;

function renderChat(feed) {
  if (!els.chatLog) return;
  const turns = feed.filter((entry) => entry.kind === "dialogue");
  //: Aynı listeyi her çerçevede yeniden kurmak, operatör yukarı kaydırmışken
  //: onu sürekli dibe atardı. Yalnız YENİ tur geldiğinde çiziliyor.
  if (turns.length === chatShown) return;
  chatShown = turns.length;

  if (els.chatIntro) els.chatIntro.classList.toggle("hidden", turns.length > 0);
  els.chatLog.querySelectorAll(".chat-turn").forEach((node) => node.remove());

  for (const turn of turns) {
    const bubble = document.createElement("div");
    //: Proaktif seslenişin ayrı bir kabuğu var: ajan KENDİLİĞİNDEN
    //: konuştuğunda bu, operatörün sorusuna verilen cevaptan farklı bir
    //: şey ve ekranda da farklı görünmeli.
    const shell = turn.agent === "supervisor" && turn.proactive
      ? "chat-ask"
      : CHAT_BUBBLE[turn.agent] || "chat-sys";
    bubble.className = `chat-msg chat-turn ${shell}`;
    bubble.textContent = turn.title || "";
    els.chatLog.appendChild(bubble);
  }
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

els.sayForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!app.runId) return;
  const text = els.sayInput.value.trim();
  if (!text) return;
  els.sayInput.value = "";
  await postJSON(`/api/run/${app.runId}/say`, { text });
});

// =============================================================================
// Bas-konuş (STT) — basılı tutulunca kaydediyor, bırakılınca `/api/stt`'ye
// gönderiyor. Dönen metin sohbet kutusuna YAZILIYOR, GÖNDERİLMİYOR: yanlış
// duyulmuş bir komutun operatör onayı olmadan ajana ulaşması bu sistemde
// geri alınamaz — bu yüzden gönderme her zaman ayrı, operatörün kendi
// tıkladığı bir adım olarak kalıyor (Görev 10, Adım 5).
// =============================================================================

let mediaRecorder = null;
let recordedChunks = [];

function micIsSupported() {
  return typeof MediaRecorder !== "undefined"
    && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
}

async function startRecording() {
  if (els.micButton.disabled || mediaRecorder) return;
  if (!micIsSupported()) {
    els.sayNote.textContent = "Bu tarayıcı mikrofon kaydını desteklemiyor.";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    const recorder = new MediaRecorder(stream);
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      void sendRecording(recorder.mimeType);
    });
    mediaRecorder = recorder;
    recorder.start();
    els.micButton.classList.add("is-recording");
    els.sayNote.textContent = "Dinleniyor…";
  } catch {
    els.sayNote.textContent = "Mikrofona erişilemedi.";
    mediaRecorder = null;
  }
}

function stopRecording() {
  if (!mediaRecorder) return;
  els.micButton.classList.remove("is-recording");
  if (mediaRecorder.state !== "inactive") mediaRecorder.stop();
  mediaRecorder = null;
}

async function sendRecording(mimeType) {
  const chunks = recordedChunks;
  recordedChunks = [];
  if (chunks.length === 0) {
    els.sayNote.textContent = "";
    return;
  }
  const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
  els.sayNote.textContent = "Metne çevriliyor…";
  const body = new FormData();
  body.append("audio", blob, "kayit.webm");
  try {
    const response = await fetch("/api/stt", { method: "POST", body });
    if (response.status === 501) {
      app.meta.stt_available = false;
      updateMicAvailability();
      const detail = await response.json().catch(() => ({}));
      els.sayNote.textContent = detail.detail || "Yerel konuşma tanıma kurulu değil.";
      return;
    }
    if (!response.ok) {
      els.sayNote.textContent = "Ses metne çevrilemedi.";
      return;
    }
    const { text } = await response.json();
    if (text) {
      // Kutuya YAZILIYOR, GÖNDERİLMİYOR — operatör görüp kendi gönderiyor.
      els.sayInput.value = els.sayInput.value
        ? `${els.sayInput.value} ${text}` : text;
      els.sayNote.textContent = "";
    } else {
      els.sayNote.textContent = "Konuşma anlaşılamadı.";
    }
    els.sayInput.focus();
  } catch {
    els.sayNote.textContent = "Ses metne çevrilemedi — sunucuya ulaşılamıyor.";
  }
}

els.micButton.addEventListener("mousedown", startRecording);
els.micButton.addEventListener("mouseup", stopRecording);
els.micButton.addEventListener("mouseleave", stopRecording);
els.micButton.addEventListener("touchstart", (event) => {
  event.preventDefault();
  startRecording();
});
els.micButton.addEventListener("touchend", stopRecording);
els.micButton.addEventListener("touchcancel", stopRecording);

// =============================================================================
// JSON modalı — teslim edilen dört anahtarı olduğu gibi gösterir
// =============================================================================

els.jsonButton.addEventListener("click", async () => {
  if (!app.runId) return;
  try {
    const response = await fetch(`/api/run/${app.runId}/payload`);
    const data = await response.json();
    // Yük yoksa gövde bir `detail` cümlesidir, JSON çıktısı DEĞİL —
    // `{"detail": "..."}` diye basmak "teslim edilen çıktı bu" demekti.
    // Cümle koşunun durumuna göre sunucuda seçiliyor
    // (`view.payload_absence_message`), burada uydurulmuyor.
    app.jsonIsPayload = response.ok;
    els.jsonView.textContent = response.ok
      ? JSON.stringify(data, null, 2)
      : ((data && data.detail) || "Çıktı okunamadı.");
  } catch {
    app.jsonIsPayload = false;
    els.jsonView.textContent = "Çıktı okunamadı.";
  }
  // Yük yoksa gövde bir GEREKÇE cümlesi — kopyalanabilir ama `.json` diye
  // indirilemez; ikisi de kapanıyor, tuşlar ölü görünmüyor, KAPALI görünüyor.
  els.copyJsonButton.disabled = !app.jsonIsPayload;
  els.downloadJsonButton.disabled = !app.jsonIsPayload;
  els.jsonModal.classList.remove("hidden");
});

/** Geri bildirim için ayrı bir kutu AÇMIYORUZ: tuşun kendi etiketi kısa
 *  süre sonucu söylüyor, sonra eski hâline dönüyor. */
function flashButtonLabel(button, text) {
  const original = button.dataset.label || button.textContent;
  button.dataset.label = original;
  button.textContent = text;
  setTimeout(() => { button.textContent = button.dataset.label || original; }, 1600);
}

els.copyJsonButton.addEventListener("click", async () => {
  const text = els.jsonView.textContent;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    flashButtonLabel(els.copyJsonButton, "Kopyalandı");
  } catch {
    // `navigator.clipboard` güvensiz bağlamda ya da izinsiz yok — tuş
    // "oldu" DEMİYOR, metin zaten seçilebilir durumda.
    flashButtonLabel(els.copyJsonButton, "Kopyalanamadı");
  }
});

els.downloadJsonButton.addEventListener("click", () => {
  const text = els.jsonView.textContent;
  if (!text || !app.jsonIsPayload) return;
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  // Dosya adı koşunun KENDİ kimliği — indirilen çıktı hangi koşuya ait,
  // dosya adından okunabilsin.
  link.download = `gozcu-${app.runId || "kosu"}.json`;
  link.click();
  // Hemen serbest bırakmak bazı tarayıcılarda indirmeyi yarıda kesiyor.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
els.closeJsonModal.addEventListener("click", () => els.jsonModal.classList.add("hidden"));
els.jsonModal.addEventListener("click", (event) => {
  if (event.target === els.jsonModal) els.jsonModal.classList.add("hidden");
});

// =============================================================================
// Açılış
// =============================================================================

// `loadMeta` ÖNCE bitmeli: `reattachIfLive` canlılık kümesini
// (`meta.live_run_states`) ondan okuyor — sırasız çağrılsalardı yeniden
// bağlanma boş bir kümeye bakıp hiç bağlanmazdı.
async function boot() {
  renderRisk(null);
  await loadMeta();
  await loadInitialStatus();
}

boot();
