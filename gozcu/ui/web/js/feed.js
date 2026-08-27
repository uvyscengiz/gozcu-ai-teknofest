// FeedEntry çizimi — Olay Günlüğü paneli.
//
// Kural: `entry.card` DIŞINDAKİ her alan `textContent` ile yazılıyor,
// asla `innerHTML` ile. Model tarafından üretilen metin (özet, gerekçe,
// diyalog) bu alanlara giriyor ve kaçırılmadan basılırsa sayfayı bozar.
// `card` TEK istisna: sunucu (`gozcu/ui/feed.py::intervention_card`)
// onu zaten `html.escape` ile kaçırıp kendi biçimini basmış olarak
// gönderiyor — burada olduğu gibi enjekte ediliyor.
//
// Renk kararı burada YOK: `entry.risk` bir seviye adı (`"Kritik"` gibi)
// ve gösterilecek renk `/api/meta`'nın `risk_colors` alanından geliyor
// (`initFeedLog`'a `colors` olarak veriliyor). Burada yalnız o sözlükten
// okunuyor, ikinci bir renk tablosu YOK.

//: `gozcu/ui/feed.py::AGENT_MARKS` ile BİREBİR aynı rozetler — beslemenin
//: kim tarafından üretildiğini aynı sembolle işaretliyor, iki ekran
//: birbirinden ayrışmasın diye.
const AGENT_MARKS = {
  perception: "\u{1F441}", router: "\u{1F9ED}", interpreter: "\u{1F50E}",
  synthesizer: "\u{1F9E9}", risk_analyst: "⚖️", supervisor: "\u{1F399}",
  reporter: "\u{1F4C4}", operator: "\u{1F464}", system: "⚙️",
};

const PROACTIVE_MARK = "\u{1F514} [KENDİLİĞİNDEN]";

/** Saniyeyi MM:SS'e çevirir — ölçek aritmetiği, karar değil. */
export function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/**
 * Bir parametre sözlüğünü `anahtar=değer` olarak yazar.
 *
 * Görev 2 incelemesinden taşınan yükümlülük: boş sözlük boş HÜCRE değil,
 * TİRE basıyor — aksi hâlde "parametresiz çağrıldı" ile "gösterilmedi"
 * ayrımı kaybolur (`gozcu/ui/feed.py::_pairs` ile aynı kural, tarayıcıda
 * yeniden kuruldu çünkü bu görevde raw `params` sözlüğü ilk kez burada,
 * bekleyen onay çubuğunda, işlenmeden tarayıcıya ulaşıyor).
 */
export function formatParams(params) {
  if (!params || Object.keys(params).length === 0) return "—";
  return Object.entries(params).map(([key, value]) => `${key}=${value}`).join(", ");
}

function riskColorFor(level, colors) {
  if (!level) return null;
  return (colors && colors[level]) || null;
}

function buildMeta(entry, colors) {
  const meta = document.createElement("div");
  meta.className = "feed-entry-meta";

  const ts = document.createElement("span");
  ts.className = "feed-entry-ts";
  ts.textContent = formatTime(entry.ts);
  meta.appendChild(ts);

  const who = document.createElement("span");
  const mark = AGENT_MARKS[entry.agent] || "•";
  let whoText = `${mark} ${entry.agent}`;
  if (entry.target) whoText += ` → ${entry.target}`;
  who.textContent = whoText;
  meta.appendChild(who);

  if (entry.proactive) {
    const proactive = document.createElement("span");
    proactive.className = "feed-entry-proactive";
    proactive.textContent = PROACTIVE_MARK;
    meta.appendChild(proactive);
  }

  if (entry.confidence !== null && entry.confidence !== undefined) {
    const confidence = document.createElement("span");
    confidence.textContent = `güven ${entry.confidence.toFixed(2)}`.replace(".", ",");
    meta.appendChild(confidence);
  }

  if (entry.risk) {
    const risk = document.createElement("span");
    risk.textContent = entry.risk;
    const color = riskColorFor(entry.risk, colors);
    if (color) risk.style.cssText = `color:${color};font-weight:600`;
    meta.appendChild(risk);
  }

  return meta;
}

/** Tek bir `FeedEntry`'yi DOM düğümüne çevirir. */
export function createEntryElement(entry, colors) {
  const node = document.createElement("div");
  node.className = "feed-entry";
  node.dataset.seq = String(entry.seq);
  node.dataset.ts = String(entry.ts);
  node.dataset.risk = entry.risk || "";
  node.dataset.kind = entry.kind;

  if (entry.kind === "escalation" && entry.card) {
    // TEK istisna: sunucu zaten kaçırıp kendi HTML'ini üretti.
    node.classList.add("is-escalation");
    node.innerHTML = entry.card;
    return node;
  }

  if (entry.agent === "operator") node.classList.add("is-operator");

  const color = riskColorFor(entry.risk, colors);
  if (color) node.style.borderLeftColor = color;

  node.appendChild(buildMeta(entry, colors));

  const title = document.createElement("div");
  title.className = "feed-entry-title";
  title.textContent = entry.title;
  node.appendChild(title);

  if (entry.detail) {
    const detail = document.createElement("div");
    detail.className = "feed-entry-detail";
    detail.textContent = entry.detail;
    node.appendChild(detail);
  }

  return node;
}

/**
 * Olay günlüğü paneli — filtre, arama, zamana atlama (spec §8.1).
 *
 * "Önemli"/"Kritik" filtreleri UYDURULMUYOR: sunucunun zaten verdiği
 * `entry.risk` alanına bakıyor (herhangi bir seviye = önemli, `"Kritik"`
 * = kritik). Yeni bir eşik ya da ayrım İCAT EDİLMİYOR.
 */
export function initFeedLog({ listElement, emptyElement, countElement,
                              searchInput, filterButtons, onSeek }) {
  let activeFilter = "all";
  let query = "";

  function matches(node) {
    const risk = node.dataset.risk;
    if (activeFilter === "critical" && risk !== "Kritik") return false;
    if (activeFilter === "important" && !risk) return false;
    if (query && !node.textContent.toLowerCase().includes(query)) return false;
    return true;
  }

  function refresh() {
    const nodes = listElement.querySelectorAll(".feed-entry");
    let visible = 0;
    nodes.forEach((node) => {
      const show = matches(node);
      node.classList.toggle("is-hidden", !show);
      if (show) visible += 1;
    });
    if (countElement) countElement.textContent = String(nodes.length);
    if (emptyElement) emptyElement.classList.toggle("hidden", nodes.length > 0);
    return visible;
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      filterButtons.forEach((other) => other.classList.toggle("is-active", other === button));
      refresh();
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      query = searchInput.value.trim().toLowerCase();
      refresh();
    });
  }

  listElement.addEventListener("click", (event) => {
    const node = event.target.closest(".feed-entry");
    if (!node || !onSeek) return;
    const ts = Number(node.dataset.ts);
    if (Number.isFinite(ts)) onSeek(ts);
  });

  return {
    /** Yalnız YENİ girdileri ekler — kaydırma konumu korunuyor. */
    append(entry, colors) {
      const node = createEntryElement(entry, colors);
      listElement.appendChild(node);
      if (!matches(node)) node.classList.add("is-hidden");
      if (countElement) countElement.textContent =
        String(listElement.querySelectorAll(".feed-entry").length);
      if (emptyElement) emptyElement.classList.add("hidden");
    },
    refresh,
  };
}
