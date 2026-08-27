/* Risk analiz durum çubuğu (Görev raporu §2).
 *
 * Videonun köşesinde duran dikey, üç bölmeli küçük bir çubuk: o anki karenin
 * risk durumunu yakıyor. Termometre gibi — aşağıdan yukarı doluyor.
 *
 * ## Üç bölme, DÖRT seviye
 *
 * Rapor üç kademeli bir çubuk istedi; sistemin risk sözleşmesi ise dört
 * kademeli (`RiskLevel`: Düşük · Orta · Yüksek · Kritik, CLAUDE.md). İkisi
 * çelişmiyor çünkü ayrı şeyler: **bölme sayısı bir çizim kararı, seviyenin
 * adı sistemin kararı.** Çubuk üç bölme dolduruyor, altındaki etiket
 * seviyenin GERÇEK adını yazıyor — "Kritik" ekranda "Yüksek" diye
 * görünmüyor. Dördü üçe katlayıp etiketi de katlamak, bu ekranın en ağır
 * sözcüğünü sessizce yutardı.
 *
 * Bölme eşlemesi: Düşük → 1 (yeşil) · Orta → 2 (sarı) · Yüksek ve Kritik
 * → 3 (kırmızı). Kritik'in ayrı ağırlığı renkte değil, `data-level`
 * özniteliğinde yaşıyor (`styles.css` ona ayrı bir vurgu veriyor).
 *
 * ## Renk sunucudan geliyor
 *
 * İkinci bir renk tablosu YOK. `app.meta.risk_colors` — `gozcu/ui/feed.py::
 * RISK_COLORS`'ın teldeki kopyası — kullanılıyor; besleme kartlarını,
 * zaman çizelgesi işaretlerini ve bu çubuğu aynı sözlük boyuyor. Elle
 * yazılmış bir kopya bir gün ayrışır ve aynı riski iki ekran iki renkle
 * gösterir.
 *
 * ## Boş çubuk "güvenli" DEĞİL
 *
 * Değerlendirme gelmemişken çubuk sönük duruyor ve etiket "—" yazıyor.
 * Yeşil yakmak "bakıldı, güvenli" derdi; oysa doğrusu "bu ana henüz
 * bakılmadı". Aynı kural konsolun her yerinde geçerli.
 */

/* Seviye → kaç bölme yanacak. Anahtarlar `RiskLevel`'ın Türkçe değerleri
 * ve şemadakiyle BİREBİR aynı olmak zorunda (CLAUDE.md: enum değerleri
 * ayrışırsa sistem sessizce ölür). */
const BANDS = { "Düşük": 1, "Orta": 2, "Yüksek": 3, "Kritik": 3 };

export function createRiskBar({ barEl, labelEl }) {
  /* `[{ts, level}]`, video saatine göre sıralı — `gozcu/ui/series.py::
   * risk_track`. */
  let track = [];
  let colors = {};
  let shown = null;
  /* Videonun o anki saati. Kapanışın İÇİNDE: modül kapsamında olsaydı iki
   * çubuk örneği aynı saati paylaşırdı. */
  let currentTime = 0;

  /* `at` saniyesindeki YÜRÜRLÜKTEKİ değerlendirme: o ana kadarki SON
   * kayıt. Risk bir anlık ölçüm değil bir DURUM — 12. saniyede "Yüksek"
   * denmişse 13. saniyede yeni bir kayıt yoksa durum hâlâ "Yüksek"tir.
   * Yalnız tam eşleşen damgayı aramak çubuğu iki değerlendirme arasında
   * söndürürdü. */
  function levelAt(at) {
    let current = null;
    for (const row of track) {
      if (row.ts > at) break;
      current = row.level;
    }
    return current;
  }

  function paint(level) {
    const cells = barEl.querySelectorAll(".riskbar-cell");
    const band = level ? (BANDS[level] || 0) : 0;
    const color = level ? colors[level] : null;
    cells.forEach((cell) => {
      const cellBand = Number(cell.dataset.band);
      /* Termometre: seçilen bölmeye KADAR olan her bölme doluyor. Yalnız
       * tek bölmeyi boyamak bir seviye göstergesi değil, bir nokta olurdu. */
      cell.style.background = cellBand <= band && color ? color : "";
    });
    barEl.dataset.level = level || "none";
    if (labelEl) labelEl.textContent = level || "—";
    if (labelEl) labelEl.style.color = color || "";
    shown = level;
  }

  return {
    setMeta(meta) {
      colors = (meta && meta.risk_colors) || {};
    },

    /* Seriyle birlikte gelen risk izini alıyor (`GET .../series`). */
    setTrack(rows) {
      track = Array.isArray(rows) ? rows : [];
      barEl.classList.remove("hidden");
      paint(levelAt(currentTime));
    },

    /* Video her ilerlediğinde çağrılıyor. Çubuk grafiklerden FARKLI
     * davranıyor: onlar geri sarınca çizileni korur (rapor "kalıcı" dedi),
     * çubuk ise o ANIN durumunu gösterdiği için geri sarınca geri düşer —
     * 10. saniyeye dönüp hâlâ kırmızı yanmak, o anda olmayan bir tehlikeyi
     * gösterirdi. */
    seek(seconds) {
      currentTime = Number.isFinite(seconds) ? seconds : 0;
      const level = levelAt(currentTime);
      if (level !== shown) paint(level);
    },

    reset() {
      track = [];
      currentTime = 0;
      barEl.classList.add("hidden");
      paint(null);
    },
  };
}
