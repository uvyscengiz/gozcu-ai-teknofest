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
// Görev 8 düzeltme turu — üç tel boşluğu bulunup RAPORLANMIŞTI, ilk turda
// server'a dokunulmamıştı ("client-only" kısıtı); ikinci turda kısıt
// kaldırıldı ve üçü de sunucu tarafında kapatıldı (bkz. `task-8-report.md`,
// "Fix round 1/5"):
//
//   1. `view.tool_rows` artık `ActionRecord.caller`'ı taşıyor. Ajan
//      çağrılarında GERÇEK ajan adı (`action.caller`) gösteriliyor —
//      risk_analyst'ın kendi soruşturma araçları artık süpervizöre
//      yazılmıyor. Operatör çağrılarında `caller` GÖSTERİLMİYOR (bkz.
//      `callerFor` altındaki not): alan operatör satırlarında anlamlı
//      değil, ekran onu "operatör" ile sabit tutuyor.
//
//   2. `/api/meta` artık `window_outcome_labels`'ı (`gozcu/ui/feed.py::
//      OUTCOME_LABELS` ile birebir, testte doğrulanmış) taşıyor — burada
//      ikinci bir kopya YOK, `agent_marks`/`risk_colors` ile AYNI ilke.
//      `floor_passed`/`vision_budgeted` hâlâ ✓/✗ sembolüyle (kelime
//      gerekmiyor, `FLOOR_LABELS` taşınmadı — ihtiyaç olursa ayrı turda).
//
//   3. `view.handoff_rows` artık `confidence`'ı `format_confidence`'tan
//      geçirip BİTMİŞ Türkçe dize olarak veriyor — burada ikinci bir
//      nokta→virgül dönüşümü YOK, sunucudan gelen dize olduğu gibi basılıyor.

/** Boş sözlük TİRE, dolu sözlük `anahtar=değer, …` — `js/feed.js::
 * formatParams` ile AYNI kural, aynı fonksiyon (ikinci kopya yok). */
import { formatParams } from "./feed.js";

/** Karar zincirinin sabit sırası — Python'da bu sırayı tutan bir sabit YOK
 * (yalnız CLAUDE.md/spec düz metninde anlatılıyor), yani burada bir Python
 * tablosunun ikinci kopyası değil, ekranın kendi bilgisi. */
const CHAIN_STAGES = ["perception", "router", "interpreter", "synthesizer",
                      "risk_analyst", "supervisor"];

/** `caller` yalnız AJAN çağrılarında anlamlı (bkz. `gozcu/models.py::
 * ActionRecord` docstring). Operatör onayladığında `call_tool` `caller`
 * parametresini almadan varsayılanına (`"supervisor"`) düşüyor
 * (`gozcu/agents/supervisor.py::apply_approval` → `registry.call_tool`,
 * pipeline kodu — bu görevin kapsamı DIŞINDA) — yani operatör satırında
 * `action.caller` alanı YANILTICI, gerçek bir bilgi taşımıyor. Ekran bu
 * yüzden operatör satırlarında `action.caller`'ı OKUMUYOR, sabit "operatör"
 * basıyor; yalnız ajan satırlarında gerçek değeri gösteriyor.
 *
 * Ham enum değeri (`action.actor_raw`) eşleşme için kullanılıyor, böylece
 * Türkçe rozet değişirse bu kod sessizce kırılmaz. Bkz. Badge desenini
 * (`sse.js::setBadge` — `data-state` ham değer, `textContent` rozet). */
function callerFor(action) {
  const isOperator = action.actor_raw === "operator";
  return isOperator ? "operatör" : (action.caller || "—");
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

  // `handoff.confidence` sunucudan ZATEN Türkçe virgüllü bitmiş dize
  // olarak geliyor (`view.handoff_rows` → `format_confidence`) — burada
  // ikinci bir biçim yok, olduğu gibi basılıyor.
  const confidence = document.createElement("span");
  confidence.className = "confidence";
  confidence.textContent = handoff.confidence;
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

function renderWindowRow(record, wireMeta) {
  const row = document.createElement("div");
  row.className = "window-row";
  row.dataset.outcome = record.outcome;

  const ts = document.createElement("span");
  ts.className = "ts";
  ts.textContent = `${record.ts}–${record.end_ts}`;
  row.appendChild(ts);

  // Türkçe karşılık `/api/meta`'nın `window_outcome_labels`'inden
  // (`gozcu/ui/feed.py::OUTCOME_LABELS` ile birebir) — ikinci bir kopya
  // burada YOK. Meta henüz gelmediyse (yarış durumu) ham enume düşer,
  // uydurmaz.
  const outcome = document.createElement("span");
  outcome.className = "outcome-label";
  const labels = (wireMeta && wireMeta.window_outcome_labels) || {};
  outcome.textContent = labels[record.outcome] || record.outcome;
  row.appendChild(outcome);

  const facts = document.createElement("span");
  facts.className = "facts";
  facts.textContent = `kutu: ${record.detections} · kişi≤${record.person_peak} · `
    + `taban: ${record.floor_passed ? "✓" : "✗"} · `
    + `görü bütçesi: ${record.vision_budgeted ? "✓" : "✗"}`;
  row.appendChild(facts);

  return row;
}

function renderWindows(rows, { listEl, emptyEl, countEl, wireMeta }) {
  countEl.textContent = String(rows.length);
  clearChildren(listEl);
  if (rows.length === 0) {
    listEl.appendChild(emptyEl);
    emptyEl.classList.remove("hidden");
    return;
  }
  rows.forEach((record) => listEl.appendChild(renderWindowRow(record, wireMeta)));
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

  // `caller`: bkz. `callerFor` — ajan satırlarında gerçek ajan adı,
  // operatör satırlarında sabit "operatör" (alan orada anlamlı değil).
  const caller = document.createElement("td");
  caller.textContent = callerFor(action);
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
// Kök neden raporu — VARSA beş bölüm, YOKSA yokluğunun NEDENİ
//
// Üç yokluk üç ayrı cümle: koşu hiç olmadı (`no_run`), genişletilmiş katman
// çöktü (`crashed`), koşu tamam ama kayda değer olay yok
// (`no_notable_event`). Görev 2'nin kararı bu ayrımın çökmemesini şart
// koşmuştu. Ayrımı BURADA yapmıyoruz: durumu da cümlesini de `GET
// .../root-cause` veriyor (`view.root_cause_state`/`ROOT_CAUSE_MESSAGES`),
// ekran yalnız basıyor. Bölüm başlıkları da `/api/meta`'nın
// `root_cause_field_labels`'inden — `window_outcome_labels` ile aynı ilke.
// =============================================================================

function renderRootCauseSection(field, value, { labels, emptyItem }) {
  const section = document.createElement("div");
  section.className = "root-cause-section";

  const head = document.createElement("h3");
  head.textContent = labels[field] || field;
  section.appendChild(head);

  if (Array.isArray(value)) {
    const list = document.createElement("ul");
    const items = value.length > 0 ? value : [emptyItem];
    items.forEach((entry) => {
      const item = document.createElement("li");
      item.textContent = entry;
      list.appendChild(item);
    });
    section.appendChild(list);
  } else {
    const paragraph = document.createElement("p");
    // Boş bir alan boş bir satır olarak DEĞİL, "(yok)" olarak basılıyor —
    // `feed.js`'in tire kuralıyla aynı jest: boşluk bir şey söylemiyor.
    paragraph.textContent = value || emptyItem;
    section.appendChild(paragraph);
  }
  return section;
}

function renderRootCause(data, { bodyEl, messageEl, wireMeta }) {
  bodyEl.dataset.state = (data && data.state) || "";
  clearChildren(bodyEl);

  if (!data || !data.report) {
    // Cümle SUNUCUDAN: üç yokluğun hangisi olduğunu ekran çıkarmıyor.
    // `data === null` KOŞU SIFIRLAMASI (`setRunId`) demek, "cümle yok"
    // değil — o durumda metne DOKUNULMUYOR, yoksa panel bir an bomboş
    // kalırdı; ilk tazelemede sunucunun cümlesi geliyor zaten.
    if (data) messageEl.textContent = data.message || "";
    messageEl.classList.remove("hidden");
    bodyEl.appendChild(messageEl);
    return;
  }

  const labels = (wireMeta && wireMeta.root_cause_field_labels) || {};
  const emptyItem = (wireMeta && wireMeta.root_cause_empty_item) || "—";
  // Sıra `labels`'ten: sunucu bölümleri anlamlı bir sırada gönderiyor
  // (sözlük ekleme sırasını koruyor). Meta gelmediyse rapor anahtarlarına
  // düşülüyor — ham anahtar basılır, ama bir cümle UYDURULMAZ.
  const fields = Object.keys(labels).length > 0
    ? Object.keys(labels) : Object.keys(data.report);
  fields.forEach((field) => bodyEl.appendChild(
    renderRootCauseSection(field, data.report[field], { labels, emptyItem })));
}

// =============================================================================
// Dış arayüz — `player.js`/`initFeedLog` ile AYNI desen
// =============================================================================

export function createTrace({ chainEl, handoffListEl, handoffEmptyEl, handoffCountEl,
                              windowListEl, windowEmptyEl, windowCountEl,
                              toolBodyEl, toolEmptyEl, toolCountEl,
                              rootCauseBodyEl, rootCauseMessageEl }) {
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
                            countEl: windowCountEl, wireMeta });
    } catch { /* aynı kural */ }
  }

  async function refreshRootCause(isLive) {
    if (runId === null) return;
    if (isLive) {
      // Koşu SÜRERKEN kök neden sorusu HİÇ SORULMUYOR. Sorulsaydı cevap
      // `"no_run"` olurdu (`output` daha `None`) ve panel koşunun tam
      // ortasında "Analiz henüz koşmadı." basardı — ekranın yalanı,
      // üstelik üç yokluğun birbirine karışmasını önlemek için var olan
      // panelde. Python'daki DÖRT durum bir koşunun BİTMİŞ hâline bakıyor;
      // "şu anda sürüyor" onlardan biri değil, o yüzden beşinci bir durum
      // eklenmiyor — soru erteleniyor ve sunucunun hazır cümlesi basılıyor.
      const pending = (wireMeta && wireMeta.root_cause_pending_message) || "";
      // Meta gelmediyse metne DOKUNULMUYOR: boş bir panel de bir şey
      // söylemez, ama yanlış bir şey söylemekten iyidir demek yerine
      // önceki cümleyi bırakıyoruz — bir sonraki çerçevede meta gelir.
      if (!pending) return;
      renderRootCause({ state: null, message: pending, report: null },
                      { bodyEl: rootCauseBodyEl, messageEl: rootCauseMessageEl,
                        wireMeta });
      return;
    }
    try {
      const response = await fetch(`/api/run/${runId}/root-cause`);
      if (!response.ok) return;
      renderRootCause(await response.json(), { bodyEl: rootCauseBodyEl,
                                               messageEl: rootCauseMessageEl,
                                               wireMeta });
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
                          countEl: windowCountEl, wireMeta });
      renderTools([], { bodyEl: toolBodyEl, emptyEl: toolEmptyEl,
                        countEl: toolCountEl });
      renderRootCause(null, { bodyEl: rootCauseBodyEl,
                              messageEl: rootCauseMessageEl, wireMeta });
    },

    /** Her SSE `state` çerçevesinde çağrılıyor — sse.js::renderState.
     * Üç uç da fire-and-forget tazeleniyor, `player.js::refreshWindows`
     * ile aynı basitlik: versiyon karşılaştırması yok, her çerçevede
     * yeniden çekiliyor.
     *
     * `isLive` PARAMETRE, burada hesaplanmıyor: canlılık kararının tek
     * uygulaması `sse.js::isLiveRunState` (kümenin kendisi de sunucudan,
     * `meta.live_run_states`). İkinci bir `includes` burada da yazılsaydı
     * kural iki yerde yaşardı. */
    applyState(state, meta, isLive) {
      wireMeta = meta || wireMeta;
      renderChainDiagram(chainEl, wireMeta);
      refreshHandoffs();
      refreshWindows();
      refreshTools();
      refreshRootCause(isLive);
    },
  };
}
