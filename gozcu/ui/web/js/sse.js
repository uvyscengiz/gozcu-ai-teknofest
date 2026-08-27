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

import { initFeedLog, formatParams } from "./feed.js";
import { createPlayer } from "./player.js";
import { createTrace } from "./trace.js";
import { createBench } from "./bench.js";

const els = {
  moduleButtons: document.querySelectorAll(".module-button"),
  views: {
    ops: document.getElementById("viewOps"),
    bench: document.getElementById("viewBench"),
    trace: document.getElementById("viewTrace"),
  },
  badgeGateway: document.getElementById("badgeGateway"),
  badgeGatewayValue: document.getElementById("badgeGatewayValue"),
  badgeMemory: document.getElementById("badgeMemory"),
  badgeMemoryValue: document.getElementById("badgeMemoryValue"),
  badgeRun: document.getElementById("badgeRun"),
  badgeRunValue: document.getElementById("badgeRunValue"),
  jsonButton: document.getElementById("jsonButton"),
  jsonModal: document.getElementById("jsonModal"),
  jsonView: document.getElementById("jsonView"),
  closeJsonModal: document.getElementById("closeJsonModal"),

  runIdLabel: document.getElementById("runIdLabel"),
  sourcePicker: document.getElementById("sourcePicker"),
  playerHolder: document.getElementById("playerHolder"),
  pausedBanner: document.getElementById("pausedBanner"),
  resumeButton: document.getElementById("resumeButton"),
  videoPlayer: document.getElementById("videoPlayer"),
  runErrorBanner: document.getElementById("runErrorBanner"),
  boxOverlay: document.getElementById("boxOverlay"),
  timeline: document.getElementById("timeline"),
  timelineFrontier: document.getElementById("timelineFrontier"),
  timelineDeferred: document.getElementById("timelineDeferred"),
  timelineMarkers: document.getElementById("timelineMarkers"),
  timelineProgress: document.getElementById("timelineProgress"),

  uploadForm: document.getElementById("uploadForm"),
  videoFile: document.getElementById("videoFile"),
  videoFileHint: document.getElementById("videoFileHint"),
  stepModeToggle: document.getElementById("stepModeToggle"),
  startButton: document.getElementById("startButton"),

  stepModeLiveToggle: document.getElementById("stepModeLiveToggle"),
  abandonButton: document.getElementById("abandonButton"),
  gatewayCutButton: document.getElementById("gatewayCutButton"),
  gatewayRestoreButton: document.getElementById("gatewayRestoreButton"),
  stressContextButton: document.getElementById("stressContextButton"),
  stressFalseInfoButton: document.getElementById("stressFalseInfoButton"),
  stressOverreachButton: document.getElementById("stressOverreachButton"),
  annotateButton: document.getElementById("annotateButton"),
  annotateNote: document.getElementById("annotateNote"),

  pendingApproval: document.getElementById("pendingApproval"),
  pendingTool: document.getElementById("pendingTool"),
  pendingParams: document.getElementById("pendingParams"),
  approveButton: document.getElementById("approveButton"),
  rejectButton: document.getElementById("rejectButton"),

  sayForm: document.getElementById("sayForm"),
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
  meta: { risk_levels: [], risk_colors: {}, live_run_states: [],
          stt_available: false },
  payloadFetched: false,
  //: Yük GERÇEKTEN çekildi mi. `payloadFetched` yalnız "denendi" diyor;
  //: koşu çöktüğünde çekme başarısız oluyor ve karar paneli "analiz
  //: tamamlandı" DEMEMELİ.
  payloadLoaded: false,
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
});

// Şeffaflık görünümü — Görev 8. Karar veren hiçbir şey burada da yok:
// `trace.js` yalnız `/handoffs`, `/actions`, `/windows`'ı çekip çiziyor.
const trace = createTrace({
  chainEl: els.chainDiagram,
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

function setBadge(el, valueEl, rawValue, suffix) {
  // `rawValue` teldeki HAM enum (`"healthy"`, `"qdrant"`, `"measured"` ...):
  // CSS renk seçicisi (`[data-state="..."]`) bunu kullanıyor. EKRANDAKİ
  // metin ise `/api/meta`'nın `badge_labels`'inden — burada bir çeviri
  // İCAT EDİLMİYOR, sunucudan gelen sözlükten okunuyor.
  //
  // `suffix` yalnız EKRANDAKİ metne ekleniyor: birleşik bir `rawValue`
  // (`"qdrant · 4"`) hem `data-state` renk seçicisini hem `badge_labels`
  // aramasını düşürür — rozet rengini kaybeder ve ham dize ekrana basılır.
  // Sayı yoksa (`null`/`undefined`) ek HİÇ basılmaz: "henüz tohumlanmadı"
  // ile "sıfır" aynı şey değil.
  el.dataset.state = rawValue || "";
  valueEl.textContent = badgeLabelFor(rawValue)
    + (suffix === null || suffix === undefined ? "" : ` · arşiv ${suffix}`);
}

function badgeLabelFor(rawValue) {
  if (!rawValue) return "—";
  return (app.meta.badge_labels && app.meta.badge_labels[rawValue]) || rawValue;
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
    button.classList.toggle("is-active", button.dataset.view === name);
  });
}

els.moduleButtons.forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

document.addEventListener("keydown", (event) => {
  if (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA") return;
  if (event.key === "1") showView("ops");
  if (event.key === "2") showView("bench");
  if (event.key === "3") showView("trace");
});

// =============================================================================
// Durum rozetleri (`/api/status` koşudan önce, sonra SSE `badges`'i devralır)
// =============================================================================

async function loadInitialStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    setBadge(els.badgeMemory, els.badgeMemoryValue, status.memory,
             status.archive);
    if (status.gateway) {
      setBadge(els.badgeGateway, els.badgeGatewayValue, status.gateway);
    }
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
  els.stepModeLiveToggle.checked = Boolean(status.step_mode);
  els.stepModeLiveToggle.disabled = false;
  attachRun(status.run_id);
}

async function loadMeta() {
  // `badgeLabelFor`/`agentMarkFor`/`runStateLabelFor` hepsi bu nesneye
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

async function loadFinalPayload() {
  if (app.payloadFetched || !app.runId) return;
  app.payloadFetched = true;
  try {
    const response = await fetch(`/api/run/${app.runId}/payload`);
    if (!response.ok) return;
    const payload = await response.json();
    els.summaryText.textContent = payload.summary;
    renderRisk(payload.risk);
    els.actionsList.innerHTML = "";
    if (!payload.actions || payload.actions.length === 0) {
      const empty = document.createElement("li");
      empty.className = "empty-hint";
      empty.style.listStyle = "none";
      empty.textContent = "Aksiyon önerisi yok.";
      els.actionsList.appendChild(empty);
    } else {
      payload.actions.forEach((action) => {
        const item = document.createElement("li");
        item.textContent = action;
        els.actionsList.appendChild(item);
      });
    }
    app.payloadLoaded = true;
    els.decisionMeta.textContent = "analiz tamamlandı";
  } catch { /* çekilemezse panel bir önceki hâlde kalır */ }
}

// =============================================================================
// Tam durum çizimi — SSE'nin her `state` çerçevesinde çağrılıyor
// =============================================================================

function renderState(state) {
  setBadge(els.badgeGateway, els.badgeGatewayValue, state.badges.gateway);
  setBadge(els.badgeMemory, els.badgeMemoryValue, state.badges.memory,
           state.badges.archive);
  setBadge(els.badgeRun, els.badgeRunValue, state.badges.run);

  const isPaused = state.run_state === "paused";
  els.pausedBanner.classList.toggle("hidden", !isPaused);
  if (isPaused && !els.videoPlayer.paused) els.videoPlayer.pause();

  renderPending(state.pending);

  const running = isLiveRunState(state.run_state);
  els.stepModeLiveToggle.disabled = state.run_state === "abandoned"
    || state.run_state === "done" || state.run_state === "failed";
  els.abandonButton.disabled = !running;
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
  // `running` (canlılık) trace'e AKTARILIYOR: koşu sürerken kök neden
  // sorusu hiç sorulmuyor (bkz. `trace.js::refreshRootCause`). Karar
  // burada bir kez veriliyor, orada yeniden hesaplanmıyor.
  trace.applyState(state, app.meta, running);
  bench.applyState(state, app.meta);

  trackRiskFromEntries(state.feed);
  if (state.run_state === "done" || state.run_state === "failed") {
    loadFinalPayload();
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
  els.playerHolder.classList.remove("hidden");
  player.setRunId(runId);
  trace.setRunId(runId);
  bench.setRunId(runId);
  els.videoPlayer.src = `/api/run/${runId}/video`;
  els.videoPlayer.load();
  connect(runId);
}

// =============================================================================
// Koşu başlatma
// =============================================================================

els.videoFile.addEventListener("change", () => {
  const file = els.videoFile.files[0];
  els.videoFileHint.textContent = file ? file.name : "Dosya seçin — mp4 · avi · mkv · mov";
});

els.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = els.videoFile.files[0];
  if (!file) return;

  els.startButton.disabled = true;
  showRunError("");

  const body = new FormData();
  body.append("video", file);
  body.append("step_mode", els.stepModeToggle.checked ? "true" : "false");

  try {
    const response = await fetch("/api/run", { method: "POST", body });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      showRunError(detail.detail || "Koşu başlatılamadı.");
      els.startButton.disabled = false;
      return;
    }
    const { run_id: runId } = await response.json();
    els.stepModeLiveToggle.checked = els.stepModeToggle.checked;
    els.stepModeLiveToggle.disabled = false;
    attachRun(runId);
  } catch {
    showRunError("Koşu başlatılamadı — sunucuya ulaşılamıyor.");
    els.startButton.disabled = false;
  }
});

// =============================================================================
// Komutlar — hepsi ince `POST` sarmalayıcıları, sonucu SSE'den okunuyor
// =============================================================================

els.resumeButton.addEventListener("click", async () => {
  if (!app.runId) return;
  await postJSON(`/api/run/${app.runId}/resume`);
});

els.abandonButton.addEventListener("click", async () => {
  if (!app.runId) return;
  await postJSON(`/api/run/${app.runId}/abandon`);
});

els.stepModeLiveToggle.addEventListener("change", async () => {
  if (!app.runId) return;
  const { ok } = await postJSON(`/api/run/${app.runId}/step-mode`,
    { enabled: els.stepModeLiveToggle.checked });
  if (!ok) els.stepModeLiveToggle.checked = !els.stepModeLiveToggle.checked;
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
    els.jsonView.textContent = response.ok
      ? JSON.stringify(data, null, 2)
      : ((data && data.detail) || "Çıktı okunamadı.");
  } catch {
    els.jsonView.textContent = "Çıktı okunamadı.";
  }
  els.jsonModal.classList.remove("hidden");
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
