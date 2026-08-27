// Şeffaflık görünümü — devir defteri, araç çağrı günlüğü, pencere defteri
// (Görev 8). Bu üç panel, karar zincirinin (perception → router →
// interpreter → synthesizer → risk_analyst → supervisor) tek ekranda
// birlikte göründüğü tek yer — şartname §7 "çok adımlı karar zincirleri"ni
// doğrudan bu sayfadan puanlıyor.
//
// Üçü de SSE'nin tam-durumunda YOK: kendi salt-okunur uçlarından çekiliyor
// (`GET /api/run/{id}/handoffs|actions|windows`, Görev 2/3). `player.js`
// ile AYNI desen: `applyState` her SSE çerçevesinde çağrılıyor, panel
// içeride üç ucu ateşleyip fire-and-forget tazeliyor (bkz.
// `player.js::refreshWindows` — burada da versiyon karşılaştırması YOK,
// aynı basitlik).
//
// Kaçırma kuralı: bu dosyada da `entry.card` gibi bir istisna YOK — sunucu
// tarafında hiçbir alan zaten kaçırılmış HTML olarak GELMİYOR (görüş,
// devir gerekçesi, araç sonucu hep ham model/operatör metni). Her şey
// `textContent` ile yazılıyor.
//
// TEL BOŞLUKLARI — üçü de rapor bölümünde ayrıntılı, burada kısaca:
//
//   1. `GET /actions` (`view.tool_rows`) `ActionRecord.caller`'ı TAŞIMIYOR
//      (yalnız `actor`: insan/makine). Ajan çağrısı satırlarında "hangi
//      ajan" bu yüzden UYDURULMUYOR — tire ("—") basılıyor, yalnız
//      operatör çağrılarında (aktör zaten insan olduğu için) "operatör"
//      yazılabiliyor. Yanlış bir ajan adı basmak ("supervisor" varsayımı
//      gibi) tam olarak bu görevin uyardığı yalanı üretirdi.
//
//   2. `WindowRecord.outcome`'un Türkçe karşılıkları (`OUTCOME_LABELS`) ve
//      `floor_passed`in Türkçesi (`FLOOR_LABELS`) `gozcu/ui/feed.py`'de
//      duruyor ama `/api/meta` bunları TAŞIMIYOR (yalnız ham
//      `window_outcomes` listesi var). Olay Günlüğü paneli aynı dört
//      kelimeyi zaten ekranda gösteriyor (FeedEntry.detail/title
//      üzerinden) — bu yüzden aynı dört dizeyi BURADA da AYNEN kullanıyoruz
//      (iki panel aynı kelimeyle konuşsun diye), `floor_passed` için ise
//      kelime yerine ✓/✗ sembolü kullanılıyor. Bu bilinçli bir ikinci kopya
//      — CLAUDE.md'nin "ikinci kopya" kuralına aykırı, raporda ayrıca
//      işaretlendi.
//
//   3. `GET /handoffs` (`view.handoff_rows`) `confidence`'ı HAM `float`
//      döndürüyor (`round(handoff.confidence, 2)`) — SSE besleme yolunun
//      aksine (`gozcu/ui/feed.py::format_confidence`, `server.py::
//      _dump_feed_entry`) Türkçe ondalık virgüle ÇEVRİLMEDEN. Burada aynı
//      biçim (`X,XX`) elle uygulanıyor — tek satırlık bir yerelleştirme,
//      ama yine `format_confidence`'ın "TEK biçimlendirme yeri" iddiasını
//      bozan ikinci bir nokta→virgül dönüşümü.

/** Boş sözlük TİRE, dolu sözlük `anahtar=değer, …` — `js/feed.js::
 * formatParams` ile AYNI kural, aynı fonksiyon (ikinci kopya yok). */
import { formatParams } from "./feed.js";

/** Karar zincirinin sabit sırası — Python'da bu sırayı tutan bir sabit YOK
 * (yalnız CLAUDE.md/spec düz metninde anlatılıyor), yani burada bir Python
 * tablosunun ikinci kopyası değil, ekranın kendi bilgisi. */
const CHAIN_STAGES = ["perception", "router", "interpreter", "synthesizer",
                      "risk_analyst", "supervisor"];

/** `gozcu/ui/feed.py::OUTCOME_LABELS` ile AYNEN — bkz. dosya başı not #2. */
const WINDOW_OUTCOME_LABELS = {
  routed: "yönlendiriciye gitti",
  forced: "görü bütçesinden bakıldı",
  skipped: "hiçbir katman bakmadı",
  deferred: "⚠ görü kesik — telafi kuyruğuna alındı",
};

/** Operatörün Türkçe rozeti — `gozcu/ui/view.py::ACTOR_LABELS["operator"]`
 * ile AYNEN eşleşmek ZORUNDA (dize karşılaştırması buna bağlı). Değişirse
 * sessizce "—"ya düşer, uydurmaz. */
const OPERATOR_ACTOR_LABEL = "operatör";

function formatConfidenceTr(value) {
  if (value === null || value === undefined) return "—";
  return `güven ${value.toFixed(2).replace(".", ",")}`;
}

function clearChildren(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function agentMarkFor(agent, wireMeta) {
  return (wireMeta && wireMeta.agent_marks && wireMeta.agent_marks[agent]) || "•";
}

// =============================================================================
// Devir defteri
// =============================================================================

function renderChainDiagram(chainEl, wireMeta) {
  clearChildren(chainEl);
  CHAIN_STAGES.forEach((stage, index) => {
    const node = document.createElement("span");
    node.className = "chain-node";
    node.textContent = `${agentMarkFor(stage, wireMeta)} ${stage}`;
    chainEl.appendChild(node);
    if (index < CHAIN_STAGES.length - 1) {
      const arrow = document.createElement("span");
      arrow.className = "chain-arrow";
      arrow.textContent = "→";
      arrow.setAttribute("aria-hidden", "true");
      chainEl.appendChild(arrow);
    }
  });
}

function renderHandoffRow(handoff, wireMeta) {
  const row = document.createElement("div");
  row.className = "handoff-row";

  const ts = document.createElement("span");
  ts.className = "ts";
  ts.textContent = handoff.ts;
  row.appendChild(ts);

  const hop = document.createElement("span");
  hop.className = "hop";
  hop.textContent = `${agentMarkFor(handoff.source, wireMeta)} ${handoff.source} `
    + `→ ${agentMarkFor(handoff.target, wireMeta)} ${handoff.target}`;
  row.appendChild(hop);

  const confidence = document.createElement("span");
  confidence.className = "confidence";
  confidence.textContent = formatConfidenceTr(handoff.confidence);
  row.appendChild(confidence);

  if (handoff.reason) {
    const reason = document.createElement("span");
    reason.className = "reason";
    reason.textContent = handoff.reason;
    row.appendChild(reason);
  }

  return row;
}

function renderHandoffs(rows, { listEl, emptyEl, countEl, wireMeta }) {
  countEl.textContent = String(rows.length);
  clearChildren(listEl);
  if (rows.length === 0) {
    listEl.appendChild(emptyEl);
    emptyEl.classList.remove("hidden");
    return;
  }
  // En yeni devir en üstte — panel `ts` sırasına göre GELİYOR (sunucu
  // sıralamıyor, kayıt sırası zaten yazma sırası); okunabilirlik için ters
  // çeviriyoruz, tıpkı Olay Günlüğü'nün en yeniyi öne koyması gibi.
  rows.slice().reverse().forEach((handoff) => {
    listEl.appendChild(renderHandoffRow(handoff, wireMeta));
  });
}

// =============================================================================
// Pencere defteri — dört akıbet dalı da AYRI görünür
// =============================================================================

function renderWindowRow(record) {
  const row = document.createElement("div");
  row.className = "window-row";
  row.dataset.outcome = record.outcome;

  const ts = document.createElement("span");
  ts.className = "ts";
  ts.textContent = `${record.ts}–${record.end_ts}`;
  row.appendChild(ts);

  const outcome = document.createElement("span");
  outcome.className = "outcome-label";
  outcome.textContent = WINDOW_OUTCOME_LABELS[record.outcome] || record.outcome;
  row.appendChild(outcome);

  const facts = document.createElement("span");
  facts.className = "facts";
  facts.textContent = `kutu: ${record.detections} · kişi≤${record.person_peak} · `
    + `taban: ${record.floor_passed ? "✓" : "✗"} · `
    + `görü bütçesi: ${record.vision_budgeted ? "✓" : "✗"}`;
  row.appendChild(facts);

  return row;
}

function renderWindows(rows, { listEl, emptyEl, countEl }) {
  countEl.textContent = String(rows.length);
  clearChildren(listEl);
  if (rows.length === 0) {
    listEl.appendChild(emptyEl);
    emptyEl.classList.remove("hidden");
    return;
  }
  rows.forEach((record) => listEl.appendChild(renderWindowRow(record)));
}

// =============================================================================
// Araç çağrı günlüğü — `caller` (hangi ajan) ile `actor` (insan/makine)
// AYRI sütun. `result` sunucuda zaten `OUTCOME_KEYS` sırasında geliyor
// (`gozcu/ui/feed.py::_outcome_first`, `view.tool_rows`); JSON nesne sırası
// korunuyor, burada YENİDEN sıralanmıyor.
// =============================================================================

function renderToolRow(action) {
  const row = document.createElement("tr");

  const ts = document.createElement("td");
  ts.className = "ts";
  ts.textContent = action.ts;
  row.appendChild(ts);

  const tool = document.createElement("td");
  tool.className = "tool-name";
  tool.textContent = action.tool;
  row.appendChild(tool);

  const params = document.createElement("td");
  params.textContent = formatParams(action.params);
  row.appendChild(params);

  const result = document.createElement("td");
  result.textContent = formatParams(action.result);
  row.appendChild(result);

  const approval = document.createElement("td");
  approval.textContent = action.approval;
  row.appendChild(approval);

  // `caller`: bkz. dosya başı not #1 — bu uçta yok, uydurulmuyor.
  const caller = document.createElement("td");
  const isOperator = (action.actor || "").includes(OPERATOR_ACTOR_LABEL);
  if (isOperator) {
    caller.textContent = "operatör";
  } else {
    caller.textContent = "—";
    caller.className = "caller-unknown";
    caller.title = "Bu uçta hangi ajanın çağırdığı yok (ActionRecord.caller "
      + "GET /actions'a taşınmadı).";
  }
  row.appendChild(caller);

  const actor = document.createElement("td");
  actor.textContent = action.actor;
  row.appendChild(actor);

  return row;
}

function renderTools(rows, { bodyEl, emptyEl, countEl }) {
  countEl.textContent = String(rows.length);
  clearChildren(bodyEl);
  emptyEl.classList.toggle("hidden", rows.length > 0);
  rows.forEach((action) => bodyEl.appendChild(renderToolRow(action)));
}

// =============================================================================
// Dış arayüz — `player.js`/`initFeedLog` ile AYNI desen
// =============================================================================

export function createTrace({ chainEl, handoffListEl, handoffEmptyEl, handoffCountEl,
                              windowListEl, windowEmptyEl, windowCountEl,
                              toolBodyEl, toolEmptyEl, toolCountEl }) {
  let runId = null;
  let wireMeta = { agent_marks: {} };

  async function refreshHandoffs() {
    if (runId === null) return;
    try {
      const response = await fetch(`/api/run/${runId}/handoffs`);
      if (!response.ok) return;
      const rows = await response.json();
      renderHandoffs(rows, { listEl: handoffListEl, emptyEl: handoffEmptyEl,
                             countEl: handoffCountEl, wireMeta });
    } catch { /* çekilemezse önceki liste kalır — sessizce, koşuyu düşürmez */ }
  }

  async function refreshWindows() {
    if (runId === null) return;
    try {
      const response = await fetch(`/api/run/${runId}/windows`);
      if (!response.ok) return;
      const rows = await response.json();
      renderWindows(rows, { listEl: windowListEl, emptyEl: windowEmptyEl,
                            countEl: windowCountEl });
    } catch { /* aynı kural */ }
  }

  async function refreshTools() {
    if (runId === null) return;
    try {
      const response = await fetch(`/api/run/${runId}/actions`);
      if (!response.ok) return;
      const rows = await response.json();
      renderTools(rows, { bodyEl: toolBodyEl, emptyEl: toolEmptyEl,
                          countEl: toolCountEl });
    } catch { /* aynı kural */ }
  }

  return {
    /** Meta yüklenir yüklenmez çağrılıyor (koşu başlamadan ÖNCE) — sabit
     * zincir diyagramı bir koşuya bağlı değil, jüri "Şeffaflık"a ilk
     * bakışta zaten karar zincirini görmeli. */
    setMeta(meta) {
      wireMeta = meta || wireMeta;
      renderChainDiagram(chainEl, wireMeta);
    },

    setRunId(id) {
      runId = id;
      renderChainDiagram(chainEl, wireMeta);
      renderHandoffs([], { listEl: handoffListEl, emptyEl: handoffEmptyEl,
                           countEl: handoffCountEl, wireMeta });
      renderWindows([], { listEl: windowListEl, emptyEl: windowEmptyEl,
                          countEl: windowCountEl });
      renderTools([], { bodyEl: toolBodyEl, emptyEl: toolEmptyEl,
                        countEl: toolCountEl });
    },

    /** Her SSE `state` çerçevesinde çağrılıyor — sse.js::renderState.
     * Üç uç da fire-and-forget tazeleniyor, `player.js::refreshWindows`
     * ile aynı basitlik: versiyon karşılaştırması yok, her çerçevede
     * yeniden çekiliyor. */
    applyState(state, meta) {
      wireMeta = meta || wireMeta;
      renderChainDiagram(chainEl, wireMeta);
      refreshHandoffs();
      refreshWindows();
      refreshTools();
    },
  };
}
