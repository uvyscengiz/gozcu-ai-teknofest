// Performans görünümü (Görev 9) — `benchmark/kpi.py::collect`'in ölçtüğü
// ALTI KPI'nın hepsi: `decision_distribution`, `vlm_trigger_rate`,
// `vision_tokens`, `correction_propagation`, `timestamp_drift_s`,
// `turkish_output_rate`. Görsel prototipin (PoC) kare/sn, VRAM, GPU
// sıcaklığı, model çıkarım gecikmesi kartları BİLEREK YOK — bu sistem
// onları hiç ölçmüyor; o kartları çizmek sayı UYDURMAK olurdu.
//
// Üç dürüstlük kuralı bu dosyanın var oluş nedeni:
//
//   1. Ölçülemeyen bir KPI "ölçülemedi" YAZAR — asla gizlenmez, asla 0
//      basılmaz. `view.pct(None)` sunucuda zaten `KPI_UNMEASURED` ("ölçülemedi")
//      döndürüyor; bu dosya o dizeyi OLDUĞU GİBİ basıyor, `display:none`
//      ya da satırı atlamak YOK. `.is-unmeasured` yalnız GÖRSEL biçim
//      (solukluk) — satır her koşulda DOM'da kalıyor.
//
//   2. Algı bloğu (`bench/perception.json`) koşudan BAĞIMSIZ — sayfa ilk
//      açıldığında (henüz koşu yokken) bile dolu geliyor. `GET
//      /api/run/none/kpi` bunu Görev 3'ten beri veriyor; `setRunId(null)`
//      çağrılınca `runId` `"none"`'a düşüyor, algı bloğu hep çekiliyor.
//
//   3. Bozulmuş bir koşu (`badges.run === "degraded"`) KPI'ları GİZLEMEZ,
//      AYRI bir uyarı şeridiyle DAMGALAR — bu kesinti hikâyesi demo
//      beat 6, jürinin görmesi gereken şey.
//
// Karar veren hiçbir şey burada yok: rozet etiketi (`badge_labels`), kova
// Türkçesi (`decision_bucket_labels`) ve ölçülemedi sözcüğü
// (`kpi_unmeasured`) hepsi `/api/meta`'dan — ikinci bir elle yazılmış
// kopya YOK (`trace.js`/`sse.js` ile AYNI ilke).

function clearChildren(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

/** Bir KPI hücresi. `value` HER ZAMAN sunucudan gelen bitmiş dize —
 * burada sayı biçimlendirilmiyor. `unmeasuredWord` `/api/meta.
 * kpi_unmeasured`'dan: yalnız SOLUKLUK sınıfını tetiklemek için metin
 * karşılaştırması, gösterimi DEĞİŞTİRMİYOR (metin aynen basılıyor). */
function kpiTile(label, value, unmeasuredWord) {
  const tile = document.createElement("div");
  tile.className = "kpi-tile" + (value === unmeasuredWord ? " is-unmeasured" : "");

  const labelEl = document.createElement("span");
  labelEl.className = "kpi-tile-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("b");
  valueEl.className = "kpi-tile-value";
  valueEl.textContent = value;

  tile.append(labelEl, valueEl);
  return tile;
}

// =============================================================================
// Algı (0. Faz) — koşudan BAĞIMSIZ
// =============================================================================

function renderPerception(perception, els, unmeasuredWord) {
  els.messageEl.textContent = perception.message || "";
  clearChildren(els.blocksEl);
  (perception.blocks || []).forEach((block) => {
    els.blocksEl.appendChild(kpiTile(block.label, block.value, unmeasuredWord));
  });
}

// =============================================================================
// Karar — VLM tetikleme, Türkçe kalma, düzeltme yayılımı, görü token'ı,
// yönlendirici karar dağılımı
// =============================================================================

function renderDecisionTiles(decision, tilesEl, unmeasuredWord) {
  clearChildren(tilesEl);
  tilesEl.appendChild(kpiTile("VLM tetikleme oranı (hedef: <%5)",
    decision.vlm_trigger_rate, unmeasuredWord));
  tilesEl.appendChild(kpiTile("Türkçe kalma oranı (hedef: %100)",
    decision.turkish_output_rate, unmeasuredWord));
  tilesEl.appendChild(kpiTile("Düzeltme yayılımı (hedef: %100)",
    decision.correction_propagation, unmeasuredWord));
}

/** "%42,3" içinden yalnız ÇUBUK GENİŞLİĞİ için sayıyı çıkarır — basılan
 * METİN her zaman sunucudan gelen dizenin kendisi, burada değişmiyor.
 * Ayrıştırılamazsa `null`: çubuk çizilmez, uydurulmaz. */
function shareWidthPercent(text) {
  const match = /^%(-?[\d.,]+)/.exec(text || "");
  if (!match) return null;
  const n = parseFloat(match[1].replace(",", "."));
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : null;
}

function renderDistribution(distribution, els, wireMeta) {
  const labels = wireMeta.decision_bucket_labels || {};
  clearChildren(els.chartEl);
  clearChildren(els.legendEl);

  // Sözleşme (`view.kpi_payload`): ya beş kovalı bir sözlük, ya da
  // `KPI_UNMEASURED` dizesinin kendisi — hiç yönlendirici kararı yoksa.
  if (typeof distribution === "string") {
    els.messageEl.textContent = distribution;
    return;
  }
  els.messageEl.textContent = "";

  // Kovaların çizim SIRASI da `/api/meta.decision_bucket_labels`'tan —
  // `benchmark.kpi.DECISION_BUCKETS`'ın elle kopyalanmış bir ikinci
  // listesi burada YOK (fix round 1: önceki sürüm `DISTRIBUTION_ORDER`
  // adında sabit bir dizi tutuyordu; bir kova eklenip
  // `DECISION_BUCKET_LABELS`'a işlense bile bu dizi güncellenmezse yeni
  // kova SESSİZCE hiç çizilmezdi — tam da bu görevin önlemesi gereken
  // gizli-KPI hatası). Sunucu `dict(view.DECISION_BUCKET_LABELS)`
  // gönderiyor; JSON nesne anahtar sırası korunur, `Object.keys` bu
  // yüzden Python tanım sırasıyla AYNI sırayı veriyor.
  const bucketOrder = Object.keys(labels).length
    ? Object.keys(labels) : Object.keys(distribution);
  // Meta henüz gelmediyse (yarış durumu — `/kpi` `/api/meta`'dan önce
  // dönerse) `labels` boş kalır; o zaman GERÇEK VERİDEN (`distribution`'ın
  // kendi anahtarları) düşülüyor — kovalar yine de GİZLENMİYOR, yalnız
  // Türkçe etiket bir sonraki `refresh()`'e kadar ham anahtara düşüyor.
  bucketOrder.forEach((bucket) => {
    const value = distribution[bucket];
    if (value === undefined) return;

    const width = shareWidthPercent(value);
    const seg = document.createElement("div");
    seg.className = "dist-seg";
    seg.dataset.bucket = bucket;
    seg.style.width = `${width === null ? 0 : width}%`;
    seg.title = `${labels[bucket] || bucket}: ${value}`;
    els.chartEl.appendChild(seg);

    const item = document.createElement("span");
    item.className = "dl-item";
    const swatch = document.createElement("i");
    swatch.className = "dl-swatch";
    swatch.dataset.bucket = bucket;
    const text = document.createElement("span");
    text.textContent = `${labels[bucket] || bucket} `;
    const valueEl = document.createElement("span");
    valueEl.className = "dl-value";
    valueEl.textContent = value;
    item.append(swatch, text, valueEl);
    els.legendEl.appendChild(item);
  });
}

function renderTokenTiles(visionTokens, tilesEl, unmeasuredWord) {
  clearChildren(tilesEl);
  if (typeof visionTokens === "string") {
    tilesEl.appendChild(kpiTile("Görü token sayısı", visionTokens, unmeasuredWord));
    return;
  }
  Object.entries(visionTokens).forEach(([model, tokens]) => {
    tilesEl.appendChild(kpiTile(model, `${tokens} token`, unmeasuredWord));
  });
}

// =============================================================================
// Performans — koşu ölçülebilirliği + devir/aksiyon sayaçları. Bozulmuş
// koşu GİZLENMEZ, ayrı bir şeritle DAMGALANIR (Adım 4).
// =============================================================================

// `degraded` kovası `confidence == 0.0`'dan geliyor (`benchmark/kpi.py::
// decision_distribution`); bunu üreten TEK yer `gozcu/agents/router.py::
// _fallback` — yönlendiricinin KENDİ gateway çağrısı yanıt vermediğinde
// ("yönlendirici kademesi yanıt vermiyor") ya da yanıtı ayrıştırılamadığında
// ("yönlendirici yanıtı okunamadı"). Görü (VLM) kademesiyle İLGİSİ YOK —
// yönlendirici görü kademesine hiç dokunmuyor. (fix round 1: önceki sürüm
// burada "görü kademesi kesikken" diyordu; bu, jürinin izlediği tam anda
// yanlış alt sistemi suçlayan, operatöre görünen bir metin hatasıydı.)
const DEGRADED_NOTICE = "Bu koşu bozulmuş sayılıyor: yönlendirici "
  + "kararlarının beşte birinden fazlası kesintiden geldi — yönlendiricinin "
  + "kendi gateway çağrısı yanıt vermedi ya da yanıtı okunamadı. Aşağıdaki "
  + "karar/performans sayıları bu yüzden manşet olarak OKUNMAMALI — "
  + "kesintinin kendisi ölçüldü.";
const UNMEASURED_NOTICE = "Bu koşuda henüz yönlendirici kararı yok — "
  + "ölçülecek bir şey oluşmadı.";

function renderRunStatusNotice(runStatus, els, wireMeta) {
  els.badgeEl.dataset.state = runStatus || "";
  els.badgeValueEl.textContent = (wireMeta.badge_labels
    && wireMeta.badge_labels[runStatus]) || runStatus || "—";

  const isDegraded = runStatus === "degraded";
  const isUnmeasured = runStatus === "unmeasured";
  els.noticeEl.classList.toggle("hidden", !(isDegraded || isUnmeasured));
  els.noticeEl.dataset.status = runStatus || "";
  els.noticeEl.textContent = isDegraded ? DEGRADED_NOTICE
    : isUnmeasured ? UNMEASURED_NOTICE : "";
}

function renderPerformanceTiles(performance, tilesEl, unmeasuredWord) {
  clearChildren(tilesEl);
  tilesEl.appendChild(kpiTile("Epizot", String(performance.episodes), unmeasuredWord));
  tilesEl.appendChild(kpiTile("Devir", String(performance.handoffs), unmeasuredWord));
  tilesEl.appendChild(kpiTile("Aksiyon", String(performance.actions), unmeasuredWord));
  tilesEl.appendChild(kpiTile("Geçen süre (sn)", performance.elapsed_s, unmeasuredWord));
  tilesEl.appendChild(kpiTile("Zaman damgası sapması (sn)",
    performance.timestamp_drift_s, unmeasuredWord));
}

// =============================================================================
// Dış arayüz — `trace.js`/`player.js` ile AYNI desen: `applyState` her
// SSE çerçevesinde çağrılıyor, panel kendi salt-okunur ucunu (`/kpi`)
// fire-and-forget tazeliyor.
// =============================================================================

export function createBench({ perceptionMessageEl, perceptionBlocksEl,
                              decisionTilesEl, distChartEl, distLegendEl,
                              distMessageEl, tokenTilesEl,
                              runStatusBadgeEl, runStatusValueEl,
                              degradedNoticeEl, performanceTilesEl }) {
  // Koşu başlamadan önce de algı bloğunu göstermek için `"none"` —
  // `GET /api/run/none/kpi` sunucuda oturumsuz boş bir depoya düşüyor
  // (Görev 3, `get_kpi`), 404 VERMİYOR.
  let runId = "none";
  let wireMeta = { badge_labels: {}, decision_bucket_labels: {}, kpi_unmeasured: "" };

  async function refresh() {
    try {
      const response = await fetch(`/api/run/${runId}/kpi`);
      if (!response.ok) return;
      const payload = await response.json();
      const unmeasuredWord = wireMeta.kpi_unmeasured;

      renderPerception(payload.perception,
        { messageEl: perceptionMessageEl, blocksEl: perceptionBlocksEl },
        unmeasuredWord);

      renderDecisionTiles(payload.decision, decisionTilesEl, unmeasuredWord);
      renderDistribution(payload.decision.distribution,
        { chartEl: distChartEl, legendEl: distLegendEl, messageEl: distMessageEl },
        wireMeta);
      renderTokenTiles(payload.decision.vision_tokens, tokenTilesEl, unmeasuredWord);

      renderRunStatusNotice(payload.performance.run_status,
        { badgeEl: runStatusBadgeEl, badgeValueEl: runStatusValueEl,
          noticeEl: degradedNoticeEl },
        wireMeta);
      renderPerformanceTiles(payload.performance, performanceTilesEl, unmeasuredWord);
    } catch { /* çekilemezse önceki panel kalır — sessizce, koşuyu düşürmez */ }
  }

  return {
    /** Meta koşudan ÖNCE gelir — algı bloğu bu yüzden burada da çekiliyor. */
    setMeta(meta) {
      wireMeta = meta || wireMeta;
      refresh();
    },

    setRunId(id) {
      runId = id || "none";
      refresh();
    },

    /** Her SSE `state` çerçevesinde çağrılıyor. */
    applyState(state, meta) {
      wireMeta = meta || wireMeta;
      refresh();
    },
  };
}
