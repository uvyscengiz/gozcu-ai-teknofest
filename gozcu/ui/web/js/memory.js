// Hafıza görünümü — kütüphanenin iki sütunu (`/api/library/*`).
//
// Bu dosyada karar veren hiçbir şey yok, `feed.js`/`trace.js` ile aynı ilke:
// risk rengi `/api/meta`'nın `risk_colors`'ından geliyor, ikinci bir renk
// tablosu YOK. Boyut/tarih biçimlemesi ve DOM çizimi burada.
//
// **Örnek satır yok.** Kütüphane boşsa ekran boş görünüyor ve boşluğun
// sebebini yazıyor. Temsilî bir "geçmiş analiz" satırı, hiç koşmamış bir
// koşuyu koşmuş gibi gösterirdi.

const els = {
  docDrop: document.getElementById("docDrop"),
  docFile: document.getElementById("docFile"),
  docList: document.getElementById("docList"),
  docEmpty: document.getElementById("docEmpty"),
  docCount: document.getElementById("docCount"),

  reportList: document.getElementById("reportList"),
  reportEmpty: document.getElementById("reportEmpty"),
  reportCount: document.getElementById("reportCount"),
  refresh: document.getElementById("memRefresh"),
  backend: document.getElementById("memBackend"),

  modal: document.getElementById("libraryModal"),
  modalTitle: document.getElementById("libraryModalTitle"),
  modalView: document.getElementById("libraryView"),
  modalClose: document.getElementById("closeLibraryModal"),
  modalCopy: document.getElementById("libraryCopyButton"),
  modalDownload: document.getElementById("libraryDownloadButton"),
};

export function createMemory({ onToast }) {
  let meta = { risk_colors: {} };
  //: Modalda o an duran metin ve indirilecek dosya adı. İkisi de indirme
  //: tuşunun okuduğu tek kaynak — ekrandaki metinle inen dosya ayrışamaz.
  let openDoc = { name: "icerik.txt", text: "" };

  // ===========================================================================
  // Biçimleme
  // ===========================================================================

  function formatSize(bytes) {
    if (!Number.isFinite(bytes)) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // Sunucu `time.time()` (saniye) yolluyor, JS ise milisaniye bekliyor.
  // Çarpan unutulursa bütün tarihler 1970'e düşer.
  function formatStamp(seconds) {
    if (!Number.isFinite(seconds)) return "—";
    return new Date(seconds * 1000).toLocaleString("tr-TR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }

  function setCount(node, value) {
    node.textContent = String(value);
  }

  // ===========================================================================
  // Silme tuşu — İKİ ADIMLI
  // ===========================================================================
  //
  // İlk tıklama tuşu "Emin misiniz?"e çeviriyor, ikincisi siliyor. Gerekçe:
  // silme geri alınamaz ve rapor tarafında kayıp GERÇEKTEN kalıcı — operatör
  // yüklediği belgenin aslını elinde tutuyor ama bir koşu raporunun tek
  // kopyası bu, yeniden üretmek videoyu baştan analiz etmek demek.
  //
  // `window.confirm` KULLANILMIYOR: tarayıcı iletişim kutusu bütün sayfayı
  // (SSE dinleyicisi dâhil) blokluyor ve canlı bir koşu sürerken açılırsa
  // olay akışı o süre boyunca duruyor.
  //
  // Zaman aşımı şart: tuş "Emin misiniz?"de kalıcı olarak asılı kalırsa
  // operatör bir sonraki gerçek silme niyetinde onay adımını görmeden
  // siler — yani koruma tam ihtiyaç duyulduğu anda yok olur.
  const CONFIRM_MS = 4000;

  function confirmingDeleteButton(label, onConfirmed) {
    const button = document.createElement("button");
    button.className = "btn btn-sm btn-danger-ghost";
    button.type = "button";
    button.textContent = "Sil";
    button.title = `${label} — silmek için iki kez tıklayın`;

    let armed = false;
    let timer = null;

    function disarm() {
      armed = false;
      clearTimeout(timer);
      button.textContent = "Sil";
      button.classList.remove("armed");
    }

    button.addEventListener("click", () => {
      if (armed) {
        disarm();
        onConfirmed();
        return;
      }
      armed = true;
      button.textContent = "Emin misiniz?";
      button.classList.add("armed");
      timer = setTimeout(disarm, CONFIRM_MS);
    });

    return button;
  }

  // ===========================================================================
  // Modal
  // ===========================================================================

  function openModal(title, text, filename) {
    openDoc = { name: filename, text };
    els.modalTitle.textContent = title;
    els.modalView.textContent = text;
    els.modal.classList.remove("hidden");
  }

  function closeModal() {
    els.modal.classList.add("hidden");
  }

  els.modalClose.addEventListener("click", closeModal);
  els.modal.addEventListener("click", (event) => {
    if (event.target === els.modal) closeModal();
  });

  els.modalCopy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(openDoc.text);
      onToast("Panoya kopyalandı.");
    } catch {
      // `navigator.clipboard` güvenli bağlam dışında (http://<lan-ip>) YOK.
      // Sessiz kalmak tuşu ölü gösterirdi.
      onToast("Panoya kopyalanamadı — tarayıcı izin vermedi.");
    }
  });

  els.modalDownload.addEventListener("click", () => {
    const blob = new Blob([openDoc.text], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = openDoc.name;
    link.click();
    URL.revokeObjectURL(url);
  });

  // ===========================================================================
  // Sol sütun — yüklenen belgeler
  // ===========================================================================

  function documentRow(doc) {
    const row = document.createElement("div");
    row.className = "mem-row";

    const main = document.createElement("div");
    main.className = "mem-row-main";

    const name = document.createElement("div");
    name.className = "mem-row-title";
    name.textContent = doc.name;
    main.appendChild(name);

    const sub = document.createElement("div");
    sub.className = "mem-row-sub";
    sub.textContent = `${formatSize(doc.size)} · ${formatStamp(doc.uploaded_at)}`;
    main.appendChild(sub);

    // Gömme durumu SAKLANMIYOR. `false` bir arıza değil, ölçülmüş bir
    // durum: belge diskte duruyor ama ajan onu emsal olarak bulamıyor.
    // "Gömüldü" diye göstermek, bulamayacağı bir şeyi bulacak sanmaktır.
    const badge = document.createElement("span");
    badge.className = doc.embedded ? "mem-tag mem-tag-ok" : "mem-tag mem-tag-off";
    badge.textContent = doc.embedded ? "hafızada" : "gömülmedi";
    badge.title = doc.embedded
      ? "Belge epizodik hafızaya gömüldü; ajan emsal ararken bulabilir."
      : "Belge saklandı ama vektörü yazılamadı — ajan onu emsal ararken BULAMAZ.";
    sub.appendChild(badge);

    row.appendChild(main);

    const tools = document.createElement("div");
    tools.className = "mem-row-tools";

    const view = document.createElement("button");
    view.className = "btn btn-sm";
    view.type = "button";
    view.textContent = "Görüntüle";
    view.addEventListener("click", () => showDocument(doc));
    tools.appendChild(view);

    tools.appendChild(
      confirmingDeleteButton(doc.name, () => deleteDocument(doc)));

    row.appendChild(tools);
    return row;
  }

  async function showDocument(doc) {
    try {
      const response = await fetch(`/api/library/documents/${doc.id}`);
      if (!response.ok) throw new Error(String(response.status));
      const text = await response.text();
      openModal(doc.name, text, doc.name);
    } catch {
      onToast("Belge açılamadı.");
    }
  }

  async function deleteDocument(doc) {
    try {
      const response = await fetch(`/api/library/documents/${doc.id}`,
                                   { method: "DELETE" });
      if (!response.ok) throw new Error(String(response.status));
      onToast(`"${doc.name}" silindi.`);
      await loadDocuments();
    } catch {
      onToast("Belge silinemedi.");
    }
  }

  async function loadDocuments() {
    let rows = [];
    try {
      const response = await fetch("/api/library/documents");
      rows = await response.json();
    } catch {
      onToast("Belge listesi alınamadı.");
      return;
    }
    els.docList.querySelectorAll(".mem-row").forEach((node) => node.remove());
    rows.forEach((doc) => els.docList.appendChild(documentRow(doc)));
    els.docEmpty.classList.toggle("hidden", rows.length > 0);
    setCount(els.docCount, rows.length);
  }

  async function uploadFiles(fileList) {
    const files = Array.from(fileList || []);
    if (files.length === 0) return;
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      try {
        const response = await fetch("/api/library/documents",
                                     { method: "POST", body: form });
        const body = await response.json();
        if (!response.ok) {
          // Sunucunun Türkçe `detail` cümlesi olduğu gibi basılıyor —
          // burada ikinci bir hata metni YAZILMIYOR.
          onToast(body.detail || "Belge yüklenemedi.");
          continue;
        }
        onToast(body.embedded
          ? `"${body.name}" yüklendi ve hafızaya gömüldü.`
          : `"${body.name}" yüklendi — hafızaya gömülemedi.`);
      } catch {
        onToast(`"${file.name}" yüklenemedi.`);
      }
    }
    await loadDocuments();
  }

  els.docDrop.addEventListener("click", () => els.docFile.click());
  els.docDrop.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      els.docFile.click();
    }
  });
  els.docFile.addEventListener("change", async (event) => {
    await uploadFiles(event.target.files);
    // Aynı dosyayı ikinci kez seçmek `change` doğurmuyor; alan sıfırlanmazsa
    // ikinci yükleme sessizce hiç olmuyor.
    event.target.value = "";
  });

  ["dragenter", "dragover"].forEach((name) => {
    els.docDrop.addEventListener(name, (event) => {
      event.preventDefault();
      els.docDrop.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    els.docDrop.addEventListener(name, (event) => {
      event.preventDefault();
      els.docDrop.classList.remove("drag");
    });
  });
  els.docDrop.addEventListener("drop", (event) => {
    uploadFiles(event.dataTransfer && event.dataTransfer.files);
  });

  // ===========================================================================
  // Sağ sütun — geçmiş koşu raporları
  // ===========================================================================

  function reportRow(report) {
    const row = document.createElement("div");
    row.className = "mem-row";

    const main = document.createElement("div");
    main.className = "mem-row-main";

    const title = document.createElement("div");
    title.className = "mem-row-title";
    // Video adı yoksa koşu kimliği basılıyor — uydurulmuş bir ad yerine
    // gerçekten bilinen tek kimlik.
    title.textContent = report.source_name || report.run_id;
    main.appendChild(title);

    const sub = document.createElement("div");
    sub.className = "mem-row-sub";
    sub.textContent = formatStamp(report.created_at);

    if (report.risk) {
      const pill = document.createElement("span");
      pill.className = "mem-tag";
      pill.textContent = report.risk;
      const color = meta.risk_colors && meta.risk_colors[report.risk];
      if (color) {
        pill.style.color = color;
        pill.style.borderColor = color;
        pill.style.background = `${color}14`;
      }
      sub.appendChild(pill);
    }
    main.appendChild(sub);

    if (report.summary) {
      const summary = document.createElement("div");
      summary.className = "mem-row-summary";
      summary.textContent = report.summary;
      main.appendChild(summary);
    }

    row.appendChild(main);

    const tools = document.createElement("div");
    tools.className = "mem-row-tools";
    const open = document.createElement("button");
    open.className = "btn btn-sm";
    open.type = "button";
    open.textContent = "JSON";
    open.addEventListener("click", () => showReport(report));
    tools.appendChild(open);

    const label = report.source_name || report.run_id;
    tools.appendChild(
      confirmingDeleteButton(label, () => deleteReport(report, label)));

    row.appendChild(tools);

    return row;
  }

  async function deleteReport(report, label) {
    try {
      const response = await fetch(`/api/library/reports/${report.id}`,
                                   { method: "DELETE" });
      if (!response.ok) throw new Error(String(response.status));
      onToast(`"${label}" raporu silindi.`);
      await loadReports();
    } catch {
      onToast("Rapor silinemedi.");
    }
  }

  async function showReport(report) {
    try {
      const response = await fetch(`/api/library/reports/${report.id}`);
      if (!response.ok) throw new Error(String(response.status));
      const body = await response.json();
      // Modalda GÖVDE gösteriliyor (`payload`), sarmalayıcı değil: operatörün
      // aradığı şey şartnamenin dört anahtarı, kütüphanenin defter alanları
      // değil.
      openModal(report.source_name || report.run_id,
                JSON.stringify(body.payload, null, 2),
                `${report.source_name || report.run_id}.json`);
    } catch {
      onToast("Rapor açılamadı.");
    }
  }

  async function loadReports() {
    let rows = [];
    try {
      const response = await fetch("/api/library/reports");
      rows = await response.json();
    } catch {
      onToast("Rapor listesi alınamadı.");
      return;
    }
    els.reportList.querySelectorAll(".mem-row").forEach((node) => node.remove());
    rows.forEach((report) => els.reportList.appendChild(reportRow(report)));
    els.reportEmpty.classList.toggle("hidden", rows.length > 0);
    setCount(els.reportCount, rows.length);
  }

  els.refresh.addEventListener("click", () => { load(); });

  // ===========================================================================
  // Dış arayüz
  // ===========================================================================

  async function load() {
    await Promise.all([loadDocuments(), loadReports()]);
  }

  return {
    setMeta(next) { meta = next || meta; },

    // Hafıza arka ucu rozeti — `memory_backend()`'in tek kelimesi.
    // `"local"` sessiz bir düşüş: sistem sağlıklı görünüyor ama epizodik
    // hafıza süreçle birlikte yok oluyor. Bunu göstermemek, o düşüşü
    // görünmez kılmak olurdu (bkz. `gozcu/memory.py::memory_backend`).
    setBackend(backend) {
      if (!backend) { els.backend.textContent = "—"; return; }
      const remote = backend === "qdrant";
      els.backend.textContent = remote ? "hafıza: qdrant" : "hafıza: yerel";
      els.backend.dataset.state = remote ? "ok" : "warn";
      els.backend.title = remote
        ? "Epizodik hafıza takımın Qdrant koleksiyonuna yazılıyor."
        : "Qdrant anahtarı tanımlı değil — epizodik hafıza süreç içinde tutuluyor ve sunucu kapanınca siliniyor. Yüklediğiniz belgeler diskte KALIR.";
    },

    load,
  };
}
