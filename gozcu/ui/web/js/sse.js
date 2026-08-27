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

  pendingApproval: document.getElementById("pendingApproval"),
  pendingTool: document.getElementById("pendingTool"),
  pendingParams: document.getElementById("pendingParams"),
  approveButton: document.getElementById("approveButton"),
  rejectButton: document.getElementById("rejectButton"),

  sayForm: document.getElementById("sayForm"),
  sayInput: document.getElementById("sayInput"),
  sayButton: document.getElementById("sayButton"),
  sayNote: document.getElementById("sayNote"),

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
};

const app = {
  runId: null,
  lastSeq: -1,
  source: null,
  meta: { risk_levels: [], risk_colors: {} },
  payloadFetched: false,
};

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

function setBadge(el, valueEl, rawValue) {
  // `rawValue` teldeki HAM enum (`"healthy"`, `"qdrant"`, `"measured"` ...):
  // CSS renk seçicisi (`[data-state="..."]`) bunu kullanıyor. EKRANDAKİ
  // metin ise `/api/meta`'nın `badge_labels`'inden — burada bir çeviri
  // İCAT EDİLMİYOR, sunucudan gelen sözlükten okunuyor.
  el.dataset.state = rawValue || "";
  valueEl.textContent = badgeLabelFor(rawValue);
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
    setBadge(els.badgeMemory, els.badgeMemoryValue, status.memory);
    if (status.gateway) {
      setBadge(els.badgeGateway, els.badgeGatewayValue, status.gateway);
    }
  } catch { /* sunucu henüz ayakta değilse rozetler "—" kalır */ }
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
                 badge_labels: {}, run_state_labels: {} };
  }
  buildRiskSteps();
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
    els.decisionMeta.textContent = "analiz tamamlandı";
  } catch { /* çekilemezse panel bir önceki hâlde kalır */ }
}

// =============================================================================
// Tam durum çizimi — SSE'nin her `state` çerçevesinde çağrılıyor
// =============================================================================

function renderState(state) {
  setBadge(els.badgeGateway, els.badgeGatewayValue, state.badges.gateway);
  setBadge(els.badgeMemory, els.badgeMemoryValue, state.badges.memory);
  setBadge(els.badgeRun, els.badgeRunValue, state.badges.run);

  const isPaused = state.run_state === "paused";
  els.pausedBanner.classList.toggle("hidden", !isPaused);
  if (isPaused && !els.videoPlayer.paused) els.videoPlayer.pause();

  renderPending(state.pending);

  const running = state.run_state === "running" || state.run_state === "paused"
    || state.run_state === "intervened";
  els.stepModeLiveToggle.disabled = state.run_state === "abandoned"
    || state.run_state === "done" || state.run_state === "failed";
  els.abandonButton.disabled = !running;
  els.gatewayCutButton.disabled = !running;
  els.gatewayRestoreButton.disabled = !running;
  els.stressContextButton.disabled = !running;
  els.stressFalseInfoButton.disabled = !running;
  els.stressOverreachButton.disabled = !running;
  els.sayInput.disabled = !app.runId;
  els.sayButton.disabled = !app.runId;
  els.jsonButton.disabled = !app.runId;

  trackRiskFromEntries(state.feed);
  if (state.run_state === "done" || state.run_state === "failed") {
    loadFinalPayload();
  } else {
    renderRisk(lastKnownRisk);
    els.decisionMeta.textContent = runStateLabelFor(state.run_state);
  }

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
  app.lastSeq = -1;
  app.payloadFetched = false;
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
    app.runId = runId;
    els.runIdLabel.textContent = runId;
    els.sourcePicker.classList.add("hidden");
    els.playerHolder.classList.remove("hidden");
    els.videoPlayer.src = `/api/run/${runId}/video`;
    els.videoPlayer.load();
    els.stepModeLiveToggle.checked = els.stepModeToggle.checked;
    els.stepModeLiveToggle.disabled = false;
    connect(runId);
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
// JSON modalı — teslim edilen dört anahtarı olduğu gibi gösterir
// =============================================================================

els.jsonButton.addEventListener("click", async () => {
  if (!app.runId) return;
  try {
    const response = await fetch(`/api/run/${app.runId}/payload`);
    const data = await response.json();
    els.jsonView.textContent = JSON.stringify(data, null, 2);
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

loadMeta();
loadInitialStatus();
renderRisk(null);
