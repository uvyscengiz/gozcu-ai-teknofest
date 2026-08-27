// Araç çağrı bildirimleri — sağ alt köşede yığılan kartlar (Görev 21 görsel
// turu). Besleme kaynağı UYDURMA DEĞİL: `trace.js` her SSE çerçevesinde
// `/api/run/{id}/actions` defterini çekiyor, bu modül o defterde YENİ beliren
// satırları alıyor. Araç şeridiyle (`.tool-table`) aynı gerçeğin ikinci,
// geçici görünümü — ikinci bir veri yolu yok.
//
// Kart neden doğrudan TAMAMLANMIŞ doğuyor:
//   Defter (`gozcu/models.py::ActionRecord`) yalnız BİTMİŞ bir çağrıyı taşıyor
//   — `result` yazılmadan satır oluşmuyor. Yani telde "şu an çalışıyor" diye
//   bir olay YOK. Kartı önce dönen bir iğle (`.tool-spin`) gösterip sonra
//   çeviren mockup davranışı, ölçülmemiş bir süreyi canlandırmak olurdu:
//   ekran bir aracın o anda çalıştığını İDDİA ederdi. `.tool-spin` bu yüzden
//   bu konsolda kullanılmıyor; kart `.tool-check` ile ve "Tamamlandı"
//   başlığıyla açılıp kendiliğinden kapanıyor.
//
// Yığın sınırı (`MAX_VISIBLE`) uzun bir koşuda ekranın araç kartlarıyla
// dolmasını engelliyor: en eski kart yenisi gelince hemen düşüyor.

import { formatParams } from "./feed.js";

/** Aynı anda ekranda duran en fazla kart. */
const MAX_VISIBLE = 3;
/** Kart ekranda ne kadar kalıyor. */
const HOLD_MS = 4200;
/** Solma süresi — CSS'te bir `.tool-card.out` sınıfı YOK, bu yüzden geçiş
 *  satır içi veriliyor (referansın da yaptığı şey). */
const FADE_MS = 320;
/** `.tool-args` tek satır: uzun parametre sözlüğü kartı taşırmasın. */
const ARGS_MAX_CHARS = 88;

const CHECK_SVG = '<svg viewBox="0 0 20 20" class="tool-check" aria-hidden="true">'
  + '<path d="m3 10.5 4 4 10-10" fill="none" stroke="currentColor" '
  + 'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function truncate(text, limit) {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

/** Bir araç kartı. Metinlerin hepsi `textContent` ile yazılıyor (`trace.js`
 *  ile aynı kural); tek `innerHTML` sabit ve veri taşımayan onay işareti. */
function buildCard(action) {
  const card = document.createElement("div");
  card.className = "tool-card done";

  const icon = document.createElement("span");
  icon.innerHTML = CHECK_SVG;
  card.appendChild(icon.firstChild);

  const body = document.createElement("div");
  body.className = "tool-body";

  const cap = document.createElement("div");
  cap.className = "tool-cap";
  cap.textContent = "Tamamlandı";
  body.appendChild(cap);

  const fn = document.createElement("div");
  fn.className = "tool-fn";
  fn.textContent = `${action.tool}()`;
  body.appendChild(fn);

  // `formatParams` boş sözlüğe TİRE veriyor (`feed.js`) — tire bir bilgi
  // taşımıyor, o durumda satır hiç çizilmiyor.
  const args = formatParams(action.params);
  if (args && args !== "—") {
    const argsEl = document.createElement("div");
    argsEl.className = "tool-args";
    argsEl.textContent = truncate(args, ARGS_MAX_CHARS);
    body.appendChild(argsEl);
  }

  card.appendChild(body);
  return card;
}

export function createToolToasts({ wrapEl }) {
  if (!wrapEl) return { push() {}, reset() {} };

  const timers = new Set();

  function dismiss(card) {
    if (!card.isConnected) return;
    card.style.transition = `opacity ${FADE_MS}ms, transform ${FADE_MS}ms`;
    card.style.opacity = "0";
    card.style.transform = "translateX(24px)";
    const timer = setTimeout(() => {
      timers.delete(timer);
      card.remove();
    }, FADE_MS);
    timers.add(timer);
  }

  function trim() {
    // `.tool-wrap` `column-reverse`: DOM'daki İLK çocuk en eski kart.
    while (wrapEl.children.length > MAX_VISIBLE) {
      wrapEl.firstElementChild.remove();
    }
  }

  return {
    /** Deftere YENİ düşmüş bir araç çağrısı — `trace.js::renderTools`'tan. */
    push(action) {
      const card = buildCard(action);
      wrapEl.appendChild(card);
      trim();
      const timer = setTimeout(() => {
        timers.delete(timer);
        dismiss(card);
      }, HOLD_MS);
      timers.add(timer);
    },

    /** Koşu değişince ekranda önceki koşunun kartı kalmasın. */
    reset() {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
      while (wrapEl.firstChild) wrapEl.removeChild(wrapEl.firstChild);
    },
  };
}
