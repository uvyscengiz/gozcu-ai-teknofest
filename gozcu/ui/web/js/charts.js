/* Video altındaki iki canlı çizgi grafik (Görev raporu §1).
 *
 * A. Varlık sayısı — kadrajdaki tespitler, türe ayrılmış (en çok görülen üç
 *    tür + "Diğer"). B. Piksel entropisi — triyaj katmanının kare kare
 *    ölçtüğü değişim, üstünde koşuya göreli kırmızı zirve çizgisi.
 *
 * Veri `GET /api/run/{id}/series`'ten TEK çağrıda geliyor ve koşunun
 * bitmesini beklemiyor: algı da triyaj da karar döngüsünden önce bitiyor.
 *
 * ## Grafik BAŞTAN tam çiziliyor
 *
 * İlk sürüm çizgiyi `video.currentTime`'a kadar açıyordu ("canlı" okuması
 * böyleydi). Yanlıştı: veri zaten en baştan elimizde ve operatörden onu
 * görmek için videoyu sonuna kadar izlemesini istemek, sahip olduğumuz
 * bilgiyi saklamak demek. Şimdi bütün seri ilk anda çiziliyor; videonun
 * nerede olduğunu ayrı bir DİKEY İMLEÇ söylüyor. Senkron kaybolmuyor,
 * bilgi de gizlenmiyor.
 *
 * ## Kütüphane yok
 *
 * Depoda harici bağımlılık yasağı var (README, "Harici ağ bağımlılığı
 * yok"): ne CDN, ne font, ne analitik. Bu yüzden çizim elle kuruluyor —
 * `<svg>` içinde `polyline`. İki grafiğin ihtiyacı bir grafik kütüphanesini
 * taşıyacak kadar büyük değil.
 *
 * ## Boşluk ≠ sıfır
 *
 * Entropi serisinde `null` "burayı ÖLÇEMEDİK" demek (okunamayan kare), 0
 * ise "ölçtük, hareket yoktu". `null`'ı 0'a çekmek grafiğe yalan
 * söyletirdi, o yüzden çizgi orada KOPUYOR: her ölçülmüş dizi kendi
 * `polyline`'ı oluyor. Varlık grafiğinde durum farklı — orada 0 gerçekten
 * "o türden bir şey görülmedi" ve dürüst.
 */

/* Görünüm kutusu, her çizimde elemanın GERÇEK piksel boyutuna eşitleniyor.
 *
 * İlk sürüm sabit bir `viewBox` + `preserveAspectRatio="none"` kullanıyordu:
 * grafik panele esniyordu ama esneme SVG'nin tamamına uygulanıyor, yani
 * yazılar da eziliyordu — 1000 birimlik kutu 337 piksele sıkışınca eksen
 * etiketleri yatayda üçte bire iniyor, dikeyde olduğu gibi kalıyordu.
 * `viewBox`u gerçek boyuta eşitlemek ölçeği 1:1 yapıyor ve yazı bozulmuyor.
 *
 * `let`: değerler her çizimde `syncViewBox` ile tazeleniyor. Çizim eşzamanlı
 * ve tek seferde bir grafik için koştuğundan modül kapsamında tutmak
 * güvenli; her fonksiyona ayrı bir geometri nesnesi geçirmek bu dosyayı
 * kazandığından çok büyütürdü. */
let VIEW_W = 1000;
let VIEW_H = 140;
const PAD = { top: 10, right: 10, bottom: 18, left: 34 };

/* En küçük çizim alanı. Altına düşünce eksen etiketleri üst üste biner;
 * panel gerçekten bu kadar darsa grafik kaydırılabilir kalıyor (CSS). */
const MIN_W = 320;
const MIN_H = 80;

function syncViewBox(svg) {
  const rect = svg.getBoundingClientRect();
  /* Panel gizliyken (`display:none`) ölçü 0 gelir; o durumda bir önceki
   * boyut korunuyor — 0 genişlikte ölçek `NaN` üretirdi. */
  if (rect.width > 0) VIEW_W = Math.max(MIN_W, Math.round(rect.width));
  if (rect.height > 0) VIEW_H = Math.max(MIN_H, Math.round(rect.height));
  svg.setAttribute("viewBox", `0 0 ${VIEW_W} ${VIEW_H}`);
}

/* Tür çizgilerinin renkleri — paletin kendi değişkenleri (`css/styles.css`
 * `:root`). Dördüncü renk "Diğer" kovasına düşüyor ve bilerek en sönük
 * olanı: toplanmış bir kova, adı konmuş bir türden daha az dikkat hak
 * ediyor. */
const ENTITY_COLORS = ["#2dd4bf", "#4aa8ff", "#f5a524", "#7d8fa4"];
const ENERGY_COLOR = "#4aa8ff";
const PEAK_COLOR = "#f2545b";

const SVG_NS = "http://www.w3.org/2000/svg";

/* Boş bir grafiğin söyleyebileceği ÜÇ ayrı cümle. Üçünü tek bir "veri yok"a
 * indirmek bu ekranın en kolay yalanı olurdu: "henüz ölçülmedi" ile
 * "ölçülemedi" farklı şeyler, ikincisi birincisiymiş gibi görünmemeli.
 * Ölçüldü: koşuya bağlanır bağlanmaz seri BOŞ geliyor (algı katmanı hâlâ
 * tarıyor) ve panel "Bu koşuda entropi ölçülemedi." diyordu — düpedüz
 * yanlış bir cümle. */
const MSG_SCANNING = "Algı katmanı hâlâ tarıyor — koşu ilerledikçe dolacak.";
const MSG_NO_ENTITIES = "Bu koşuda hiç tespit kaydedilmedi.";
const MSG_NO_ENERGY = "Bu koşuda entropi ölçülemedi.";

function svgEl(name, attrs) {
  const node = document.createElementNS(SVG_NS, name);
  for (const key in attrs) node.setAttribute(key, attrs[key]);
  return node;
}

function formatClock(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/* Y ekseni etiketi: varlık sayısı tam sayı, entropi 0-1 aralığında iki
 * hane. Aynı biçimlendiriciyi ikisine de vermek "3,00 nesne" ya da "1"
 * entropi yazardı. */
function formatCount(value) {
  return String(Math.round(value));
}

function formatScore(value) {
  return value.toFixed(2).replace(".", ",");
}

/* ------------------------------------------------------------------ *
 * Ölçek
 * ------------------------------------------------------------------ */

function makeScale(tsList, maxValue) {
  const first = tsList.length ? tsList[0] : 0;
  const last = tsList.length ? tsList[tsList.length - 1] : 1;
  /* Tek noktalı (ya da tek saniyelik) bir seride `last - first` sıfır ve
   * her nokta aynı x'e düşerdi; genişlik en az 1 saniye sayılıyor. */
  const span = Math.max(last - first, 1);
  /* Tavan en az 1: baştan sona boş bir koşuda 0'a bölünürdü. Entropi zaten
   * 0-1 normalize, varlık sayısında tavan gerçek en büyük sayı. */
  const top = Math.max(maxValue, 1);
  return {
    first,
    last,
    top,
    x(ts) {
      const ratio = (ts - first) / span;
      return PAD.left + ratio * (VIEW_W - PAD.left - PAD.right);
    },
    y(value) {
      const ratio = value / top;
      return VIEW_H - PAD.bottom - ratio * (VIEW_H - PAD.top - PAD.bottom);
    },
  };
}

/* ------------------------------------------------------------------ *
 * Ortak iskelet — ızgara, eksen etiketleri
 * ------------------------------------------------------------------ */

function drawFrame(svg, scale, formatValue) {
  const gridline = (value) => {
    const y = scale.y(value);
    svg.appendChild(svgEl("line", {
      x1: PAD.left, x2: VIEW_W - PAD.right, y1: y, y2: y,
      stroke: "#23303f", "stroke-width": 1,
    }));
    const label = svgEl("text", {
      x: PAD.left - 6, y: y + 3.5, "text-anchor": "end",
      class: "chart-axis-label",
    });
    label.textContent = formatValue(value);
    svg.appendChild(label);
  };
  gridline(0);
  gridline(scale.top / 2);
  gridline(scale.top);

  /* Zaman ekseni yalnız iki uç + orta: dar bir panelde daha fazla etiket
   * üst üste biner ve okunmaz. */
  [scale.first, (scale.first + scale.last) / 2, scale.last].forEach((ts, i) => {
    const label = svgEl("text", {
      x: scale.x(ts), y: VIEW_H - 6,
      "text-anchor": i === 0 ? "start" : i === 2 ? "end" : "middle",
      class: "chart-axis-label",
    });
    label.textContent = formatClock(ts);
    svg.appendChild(label);
  });
}

/* Grafiğin ortasına tek satırlık bir cümle koyar — boş bir eksen takımının
 * NEDEN boş olduğunu söyleyen şey bu. */
function drawMessage(svg, text) {
  const label = svgEl("text", {
    x: VIEW_W / 2, y: VIEW_H / 2, "text-anchor": "middle",
    class: "chart-axis-label",
  });
  label.textContent = text;
  svg.appendChild(label);
}

/* Videonun o anki yeri — dikey imleç. Grafiğin kendisi baştan tam
 * çizildiği için "nerede olduğumuz" bilgisini taşıyan tek şey bu.
 * Seri aralığının dışındaysa (video henüz yüklenmemiş, süre serinin
 * ötesinde) çizilmiyor: yanlış yerde bir imleç, imleçsizlikten kötü. */
function drawPlayhead(svg, scale, seconds) {
  if (!Number.isFinite(seconds)) return;
  if (seconds < scale.first || seconds > scale.last) return;
  const x = scale.x(seconds);
  svg.appendChild(svgEl("line", {
    x1: x, x2: x, y1: PAD.top, y2: VIEW_H - PAD.bottom,
    class: "chart-playhead",
  }));
}

/* Ölçülmüş ardışık dizileri `polyline` olarak ekler; `null` gördüğü yerde
 * çizgiyi KOPARIR (modül başlığı: boşluk ≠ sıfır). */
function drawLine(svg, scale, tsList, values, color) {
  let run = [];
  const flush = () => {
    if (run.length === 1) {
      /* Tek başına kalmış bir ölçüm `polyline` ile görünmez (iki nokta
       * gerekir); nokta olarak çiziliyor ki ölçülmüş bir kare kaybolmasın. */
      svg.appendChild(svgEl("circle", {
        cx: run[0][0], cy: run[0][1], r: 2, fill: color,
      }));
    } else if (run.length > 1) {
      svg.appendChild(svgEl("polyline", {
        points: run.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "),
        fill: "none", stroke: color, "stroke-width": 2,
        "stroke-linejoin": "round", "stroke-linecap": "round",
      }));
    }
    run = [];
  };

  for (let i = 0; i < tsList.length; i += 1) {
    const value = values[i];
    if (value === null || value === undefined) { flush(); continue; }
    run.push([scale.x(tsList[i]), scale.y(value)]);
  }
  flush();
}

/* ------------------------------------------------------------------ *
 * A. Varlık sayısı
 * ------------------------------------------------------------------ */

function renderEntities(svg, legendEl, data, playhead, live) {
  svg.textContent = "";
  syncViewBox(svg);
  if (legendEl) legendEl.textContent = "";
  if (!data || !data.ts.length) {
    drawMessage(svg, live ? MSG_SCANNING : MSG_NO_ENTITIES);
    return;
  }

  let maxValue = 0;
  data.series.forEach((row) => row.values.forEach((v) => {
    if (v > maxValue) maxValue = v;
  }));
  const scale = makeScale(data.ts, maxValue);
  drawFrame(svg, scale, formatCount);
  drawPlayhead(svg, scale, playhead);

  data.series.forEach((row, index) => {
    const color = ENTITY_COLORS[Math.min(index, ENTITY_COLORS.length - 1)];
    drawLine(svg, scale, data.ts, row.values, color);
    if (!legendEl) return;
    const item = document.createElement("span");
    item.className = "chart-key";
    const swatch = document.createElement("i");
    swatch.style.background = color;
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(row.label));
    legendEl.appendChild(item);
  });
}

/* ------------------------------------------------------------------ *
 * B. Piksel entropisi + zirve çizgisi
 * ------------------------------------------------------------------ */

function renderEnergy(svg, noteEl, data, playhead, live) {
  svg.textContent = "";
  syncViewBox(svg);
  if (!data || !data.ts.length) {
    /* İKİ AYRI durum, iki ayrı cümle. Koşu sürerken seri boşsa triyaj
     * katmanı henüz sıra gelmemiş demektir; koşu bittiğinde hâlâ boşsa
     * gerçekten kanıt bulunamamıştır. Düz bir sıfır çizgisi ikisinde de
     * "hiç hareket yoktu" diye yalan söylerdi. */
    drawMessage(svg, live ? MSG_SCANNING : MSG_NO_ENERGY);
    if (noteEl) noteEl.textContent = "";
    return;
  }

  const scale = makeScale(data.ts, 1);
  drawFrame(svg, scale, formatScore);
  drawPlayhead(svg, scale, playhead);

  if (data.threshold !== null && data.threshold !== undefined) {
    const y = scale.y(data.threshold);
    svg.appendChild(svgEl("line", {
      x1: PAD.left, x2: VIEW_W - PAD.right, y1: y, y2: y,
      stroke: PEAK_COLOR, "stroke-width": 1.5, "stroke-dasharray": "6 4",
    }));
    /* Zirvelerin HEPSİ işaretleniyor. İlk sürüm yalnız videonun geldiği
     * yere kadarını çiziyordu; oysa zirve tam da operatörün ATLAMAK
     * isteyeceği yer — ileriyi göstermemek, ekranın en işe yarar
     * bilgisini saklamaktı. */
    data.peaks.forEach((ts) => {
      svg.appendChild(svgEl("circle", {
        cx: scale.x(ts), cy: scale.y(1) - 2, r: 3, fill: PEAK_COLOR,
      }));
    });
  }

  drawLine(svg, scale, data.ts, data.values, ENERGY_COLOR);

  if (noteEl) {
    noteEl.textContent = data.threshold === null || data.threshold === undefined
      ? "Bu koşuda hiçbir kare diğerlerinden ayrılmadı — zirve yok."
      : `Zirve eşiği ${formatScore(data.threshold)} · `
        + `${data.peaks.length} zirve karesi`;
  }
}

/* ------------------------------------------------------------------ *
 * Dışa açılan yüz
 * ------------------------------------------------------------------ */

export function createCharts({ wrapEl, entitySvg, entityLegendEl,
                               energySvg, energyNoteEl, onSeries }) {
  let data = null;
  /* Videonun o anki saati — YALNIZ dikey imleci konumlandırıyor. Çizginin
   * ne kadarının çizileceğine artık karar vermiyor: seri baştan tam
   * çiziliyor (bkz. modül başlığı). */
  let playhead = 0;
  /* Koşu hâlâ canlı mı. Boş bir serinin "henüz ölçülmedi" mi "ölçülemedi"
   * mi olduğunu ayıran tek bilgi bu. */
  let live = false;
  let runId = null;
  /* Üst üste binen çekimleri engelliyor: SSE çerçeveleri sık gelebiliyor ve
   * her biri yeni bir istek açsaydı seri hazır olana kadar sunucuya
   * gereksiz yük binerdi. */
  let fetching = false;

  function paint() {
    renderEntities(entitySvg, entityLegendEl, data && data.entities,
                   playhead, live);
    renderEnergy(energySvg, energyNoteEl, data && data.energy, playhead,
                 live);
  }

  /* Panel genişliği değişince `viewBox` da değişmeli, yoksa ölçek 1:1
   * olmaktan çıkar ve yazılar yeniden ezilir. */
  if (typeof ResizeObserver !== "undefined" && wrapEl) {
    new ResizeObserver(() => { if (data) paint(); }).observe(wrapEl);
  }

  function isEmpty() {
    return !data || !data.entities.ts.length || !data.energy.ts.length;
  }

  return {
    /* Seriyi çeker. Koşu sürerken de çağrılabilir; uç koşunun bitmesini
     * beklemiyor. */
    async load(id) {
      if (!id) return;
      runId = id;
      if (fetching) return;
      fetching = true;
      try {
        const response = await fetch(`/api/run/${id}/series`);
        if (response.ok) data = await response.json();
      } catch (error) {
        /* Grafik bir karar yüzeyi değil; çekilemezse konsolun geri kalanı
         * çalışmaya devam etmeli. */
      } finally {
        fetching = false;
      }
      if (wrapEl) wrapEl.classList.remove("hidden");
      /* Risk durum çubuğu (Görev raporu §2) AYNI yanıttan besleniyor.
       * Kendi isteğini açsaydı tarayıcı aynı koşunun iki parçasını iki
       * ayrı anda çeker ve çubuk grafiklerden farklı bir saniyeyi
       * gösterebilirdi — tek çağrı kuralının sebebi bu. */
      if (data && onSeries) onSeries(data);
      paint();
    },

    /* Her SSE `state` çerçevesinde çağrılıyor.
     *
     * İki iş yapıyor. (a) Koşunun canlı olup olmadığını taşıyor — boş bir
     * serinin hangi cümleyi yazacağı buna bağlı. (b) Seri HENÜZ boşsa
     * yeniden çekiyor: algı katmanı karar döngüsünden önce bitiyor ama
     * koşuya bağlanma anından ÖNCE bitmiş olmuyor, yani ilk çekim boş
     * dönebiliyor (ölçüldü). Tek seferlik bir çekim grafiği koşunun
     * sonuna kadar boş bırakırdı. */
    applyState(state, isLive) {
      live = !!isLive;
      if (isEmpty() && live) this.load(runId);
      else paint();
    },

    /* Video ilerledikçe çağrılıyor. Yalnız imleci taşıyor — grafik zaten
     * tam çizili, o yüzden geri sarmak da bir şey silmiyor. */
    seek(seconds) {
      if (!data) return;
      const next = Number.isFinite(seconds) ? seconds : 0;
      /* Yarım saniyeden küçük oynamalar yeniden çizdirmiyor: `timeupdate`
       * saniyede birkaç kez ateşliyor ve her birinde iki grafiği baştan
       * kurmak boşuna iş. */
      if (Math.abs(next - playhead) < 0.5) return;
      playhead = next;
      paint();
    },

    reset() {
      data = null;
      playhead = 0;
      live = false;
      runId = null;
      if (wrapEl) wrapEl.classList.add("hidden");
      entitySvg.textContent = "";
      energySvg.textContent = "";
      if (entityLegendEl) entityLegendEl.textContent = "";
      if (energyNoteEl) energyNoteEl.textContent = "";
    },
  };
}
