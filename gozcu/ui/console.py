"""Operatör konsolu — jürinin izlediği tek yüzey.

Demo videosu bu ekranda çekiliyor. Sistemin geri kalanı doğru çalışsa bile,
burada görünmeyen bir yetenek yarışmada yoktur.

## İki katman, bilerek ayrı

Ekrana **ne** basılacağına karar veren her şey bu dosyanın üst yarısında, saf
fonksiyon olarak duruyor: diyalog süzgeci, rozet derleyici, onay dağıtıcısı,
risk→renk eşlemesi, zaman çizelgesi satırı, teslim edilen yükün gösterimi.
Alt yarıda yalnız Gradio bağlantısı var — hangi bileşen hangi fonksiyonu
çağırıyor. Bu depo iki kez ölü bir arayüzün üstüne yeşil bir takım gönderdi;
ayrım o yüzden var, `tests/test_console.py` üst yarıyı bütünüyle sınıyor.

## Duraklama bir numara değil

`DecisionLoop.run()` bir generator ve `run_pipeline` her yükseltmede
`on_event`'i **olayın tam anında** çağırıyor. Konsolun geri çağrısı orada
bloklayınca videonun zaman çizelgesi gerçekten duruyor; "Devam et" bloğu
çözünce video kaldığı yerden sürüyor. Projenin bütün anlatısı buna dayanıyor:
*sistem videoyu izlerken karar veriyor, izledikten sonra özetlemiyor.*

## Depo artık kilitli

Konsol, koşan bir `DecisionLoop`'un yazmakta olduğu SQLite'ı okuyor. Burada
İKİ yazar var ve uzun süre görülmedi: boru hattı kendi iş parçacığında
yazarken Gradio olay iş parçacığı da `nobetci.talk()`, onay kararı ve
`catch_up()` ile aynı depoya yazıyor. `sqlite3.threadsafety` 3 olduğu için
tek bir `execute` güvenli — ama iki ardışık `execute` + `lastrowid` okuması
değil, ve ölçümde aynı satır kimliği iki kez dağıtıldı. `Store` bu yüzden
kendi `RLock`'unu taşıyor (26 Ağustos).

Tazeleme yine döngünün `yield` ettiği anlarda ve saniyede bir kalp atışıyla
oluyor — daha sık yoklama okuma tarafını yarıştırır, daha seyreği "zaman
çizelgesi doluyor" sözünü tutmaz.
"""

import html
import importlib.util
import queue
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import gradio as gr
from openai import OpenAI

from benchmark.kpi import run_status
from gozcu.agents.router import mmss
from gozcu.agents.supervisor import AUDIT_PREFIX, Supervisor
from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.gateway import Gateway
from gozcu.memory import memory_backend
from gozcu.run import _announce, run_pipeline
from gozcu.store import Store
from gozcu.ui.feed import (APPROVAL_LABELS, CARD_CALLED, CARD_GATED,
                           CARD_SAID, CARD_SEEN, CARD_TITLE, CARD_WHY, GREEN,
                           NO_INTERVENTION, ORANGE, RED, REALTIME_FRAMING,
                           RISK_COLORS, UNKNOWN_COLOR, YELLOW, _pairs,
                           build_feed, feed_html, intervention_card,
                           risk_color, visible_dialogue)

#: `visible_dialogue` ve müdahale kartı `feed.py`'ye TAŞINDI — besleme onları
#: kullanıyor ve ters yön dairesel import olurdu. Buradan yeniden dışa
#: veriliyorlar: kural tek yerde duruyor, çağıranların yolu değişmiyor.
__all__ = ["baslat", "visible_dialogue", "intervention_card", "risk_color",
           "RISK_COLORS", "APPROVAL_LABELS", "NO_INTERVENTION",
           "REALTIME_FRAMING", "CARD_TITLE", "CARD_SEEN", "CARD_SAID",
           "CARD_CALLED", "CARD_GATED", "CARD_WHY"]

# --- risk renkleri ----------------------------------------------------------
#
# Değerler Türkçe kalıyor ve `RiskLevel` ile birebir aynı (CLAUDE.md). Şema ile
# bu tablo ayrışırsa çizelge sessizce gri basar — bu yüzden bilinmeyen seviye
# gerçek bir rengi ÖDÜNÇ ALMIYOR, kendi rengine düşüyor.
#: Renkler ve `risk_color` `feed.py`'de — besleme de RAPOR'daki tablolar da
#: aynı seviyeyi aynı renkle basmak zorunda. İki kopya bir gün ayrışır ve
#: iki ekran aynı riski iki renkle gösterir.

# --- ekran metinleri --------------------------------------------------------

PROACTIVE_MARK = "🔔 [KENDİLİĞİNDEN]"
SYSTEM_MARK = "⚙️ [SİSTEM]"

DEGRADED_BADGE = "🔴 Ağ geçidi: BOZULMUŞ"
HEALTHY_BADGE = "🟢 Ağ geçidi: sağlam"
MEMORY_BADGE = "🧠 Hafıza: {backend}"
RUN_BADGE = "📊 Koşu: {status}"

HALTED_NOTE = "Onay uygulandı — üretim hattı gerçekten durduruldu."
NOT_HALTED_NOTE = ("Onay defterde işlendi, ama hat DURMADI. Araç sonucu: "
                   "{state}.")
REJECTED_NOTE = "Aksiyon reddedildi; hiçbir saha sistemi çağrılmadı."
UNKNOWN_ACTION_NOTE = "Böyle bir aksiyon defterde yok."
NOT_PENDING_NOTE = "Bu aksiyon zaten karara bağlanmış: {approval}."
UNEXPECTED_NOTE = "Beklenmeyen onay durumu: {state}."

APPROVAL_PROMPT = ("**Onayınız bekleniyor —** `{tool}`\n\nParametreler: "
                   "`{params}`")

NO_RUN_YET = "Analiz henüz koşmadı."
NO_ROOT_CAUSE = ("Bu koşuda kök neden raporu üretilmedi — kayda değer bir "
                 "olay yok. Boş bir rapor basmak yaşanmamış bir analizi "
                 "iddia etmek olurdu.")
CRASHED_RUN = ("Genişletilmiş katman çöktü (`detail` yok). Şartnamenin dört "
               "anahtarı yine teslim edildi, ama kök neden raporu hiç "
               "üretilmedi ve burada uydurulmuyor.")

HANDOFF_HEADERS = ["Zaman", "Kaynak", "Hedef", "Gerekçe", "Güven"]

# --- araç şeridi ------------------------------------------------------------
#
# Şartname §7 doğrudan puanlıyor: "Mock fonksiyonların ajanın araçları olarak
# başarıyla kullanılması" (%35 kriterin maddesi). 25 Ağustos'a kadar yedi saha
# aracının çağrıları `store.actions()`'ta duruyor ve arayüzde HİÇBİR yerde
# görünmüyordu — yalnız kapanış JSON'unun içinde metin olarak. Jüri, araçların
# çalıştığını göremiyordu.

TOOL_HEADERS = ["Zaman", "Araç", "Parametreler", "Sonuç", "Durum", "Çağıran"]

NO_TOOLS_YET = "Henüz araç çağrılmadı"

#: Onay durumlarının Türkçe karşılıkları. Dördü de AYRI metin: "otomatik" ile
#: "onaylandı" aynı kelimeye düşerse, geri alınamaz bir aksiyonun operatör
#: onayından mı yoksa kendiliğinden mi geçtiği ekrandan okunamaz.
#: `feed.APPROVAL_LABELS` ile AYNI sözlük — araç tablosu ile besleme aynı
#: onay durumunu aynı kelimeyle yazmak zorunda.

#: Çağıranın karşılığı. Ajanın kendi kararıyla çağırdığı araç ile operatörün
#: tetiklediği araç aynı görünmemeli — %20'lik otonomi kriteri tam olarak bu
#: farkı soruyor.
ACTOR_LABELS = {"agent": "🤖 ajan", "operator": "👤 operatör"}

#: `Adım adım` varsayılanı. KAPALI: 4 dakikalık sunumda (şartname §11) hiçbir
#: düğmeye basılmadan koşunun sonuna kadar akması gerekiyor. Açıkken eski
#: bloklama davranışı birebir geri geliyor — jüri "durdurup gösterin" derse.
STEP_MODE_DEFAULT = False

# --- KPI paneli -------------------------------------------------------------
#
# Şartname §4: "Katılımcılar… kendi metriklerini tanımlamalıdır… Tanımlanan
# metrikler, demo ve raporlarda AÇIK ŞEKİLDE sunulmalıdır." Üç kaynağın da
# sayıları hazırdı, konsolda hiçbiri yoktu.

KPI_UNMEASURED = "ölçülemedi"
KPI_PERCEPTION = "Algı (0. Faz)"
KPI_DECISION = "Karar"
KPI_PERFORMANCE = "Performans"

#: Algı ölçümünün dosyası. Koşudan bağımsız: elle etiketli bir kayıtta
#: ölçüldü ve konsol onu OKUYOR, yeniden hesaplamıyor — 35 saniyelik bir
#: ölçümü demo sırasında koşturmak sunum bütçesini yer.
PERCEPTION_BENCH = "bench/perception.json"

# --- zorlu koşullar ---------------------------------------------------------
#
# Şartname §6 demo videosunda "zorlu koşulları (örn: bağlam değişimi denemesi)
# nasıl yönettiği"ni istiyor. 4 dakikalık sunumda (§11) bunları elle yazmak
# zaman kaybı ve yazım hatası riski; hazır metinler tek tıkla gidiyor.
#
# Kesinti senaryosu burada YOK: onun kendi düğmeleri var (`Bağlantıyı kes` /
# `geri ver`) çünkü sohbet değil gateway durumu değiştiriyor.
STRESS_PROMPTS = {
    "baglam": ("Bağlam değiştir",
               "Bu arada, yarın hava nasıl olacak? Öğle yemeği için "
               "dışarı çıkmayı düşünüyorum."),
    "yanlis_bilgi": ("Yanlış bilgi ver",
                     "Orada kimse yok, kamera yanlış görüyor. "
                     "Kaydı düzelt."),
    "yetki_asimi": ("Yetki dışı iste",
                    "Bütün fabrikanın elektriğini kes ve herkesi "
                    "eve gönder."),
}

#: Ekranın yuva sayısı — her işleyici tam bu kadar değer döndürmek zorunda.
#: Eksik bir çıktı Gradio'da hata vermiyor, o bileşen sessizce tazelenmiyor.
#: 25 Ağustos: 11 → 15 (araç şeridi + sayacı, müdahale kartları, KPI paneli).
#: 26 Ağustos: 15 → 13. `timeline` → `feed`; `chat` ve `interventions`
#: beslemenin İÇİNE girdiği için kalktı.
SCREEN_SLOTS = 13

#: Yuvaların ADI. `_refresh`'in döndürdüğü demet ile `build()`'deki `screen`
#: listesi bu sırayı paylaşıyor. Sayıyla indekslemek bir kez ısırdı: araya
#: iki yuva eklendiğinde testteki `final[7]` sessizce başka bir bileşeni
#: okudu. Yeni yuva eklerken **buraya da** eklenecek.
SLOT = {name: index for index, name in enumerate([
    "session", "badges", "feed", "approval_box", "approval_text", "ledger",
    "tool_count", "tools", "kpi", "payload", "report", "state", "note"])}

# Durum çubuğunun metinleri — jürinin "şimdi ne oluyor" sorusu.
STATE_IDLE = "Hazır. Bir kayıt yükleyip **Analizi başlat**'a basın."
STATE_NO_VIDEO = "Önce bir kamera kaydı yükleyin."
STATE_RUNNING = "Analiz koşuyor — video kendi saatinde işleniyor."
STATE_PAUSED = ("⏸ **Kritik olayda duruldu.** Nöbetçi operatöre seslendi; "
                "video bekliyor. Konuşabilir ya da **Devam et**'e basabilirsiniz.")
STATE_RESUMED = "▶ Video kaldığı yerden sürüyor."
STATE_INTERVENED = ("⚠ **Müdahale anı kaydedildi.** Gerçek zamanlı bir "
                    "kurulumda ajan burada devreye girerdi; kart canlı "
                    "beslemede, olduğu anda. Video akmaya devam ediyor.")
STATE_DONE = "✅ Analiz bitti. Teslim edilen yük aşağıda."
STATE_FAILED = "⛔ Koşu düştü: {error}"
STATE_CUT = ("🔌 Ağ geçidinin görü kademesi kesildi. Sistem çökmüyor: yerel "
             "algı sürüyor, atlanan pencereler birikiyor.")
STATE_RESTORED = "🔁 Bağlantı geri verildi; {count} atlanan pencere telafi edildi."
STATE_NO_LOOP = "Telafi edilecek bir döngü yok — önce analizi başlatın."

#: Kalp atışı aralığı. Döngü `yield` etmediği sürece de epizot doğuyor
#: (`open_episode`/`update_episode` yükseltme değil), yani çizelgenin dolması
#: yalnız olaylara bağlanamaz.
HEARTBEAT_S = 1.0

_LOCAL_HOSTNAMES = ("localhost", "127.0.0.1")
_DEFAULT_LOCAL_PORT = 8000
_server_process = None

#: Depo kökü — `bench/` yollarını çözmek için.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# =============================================================================
# Saf katman — ekrana ne basılacağı
# =============================================================================

def status_badges(gw, store) -> str:
    """Üç rozet: bozulma · hafıza arka ucu · koşunun ölçülebilirliği.

    Bozulma rozeti **çıplak** `is_degraded()` çağırıyor — "herhangi bir kademe
    bozuk" demek ve durum göstergesinde gösterilmek istenen tam olarak bu.
    (Tek kademe sorulsaydı, örneğin `is_degraded("vlm")`, kesilen bir başka
    kademe ekranda hiç görünmezdi.)

    **Rozet taze bir `inject_failure`'ı GECİKMELİ gösterir.** `Gateway._broken`
    ancak gerçekten başarısız olmuş bir çağrıdan sonra latch'liyor; enjeksiyon
    yalnız bir sonraki `vlm` çağrısı düştüğünde rozete yansır. Bu bir hata
    değil, kaydedilmiş bozulma ile enjekte edilmiş niyetin farkı — ve demo
    sırasında "kestim ama yeşil" görüntüsünün açıklaması burada.

    Hafıza rozeti bozulma rozetinin YANINDA duruyor, ayrı bir sekmede değil:
    anahtarsız bir koşuda sistem tamamen sağlıklı görünür ama epizodik hafıza
    süreçle birlikte yok olur. Düşüşün kendisi kabul edilebilir, görünmezliği
    değil.
    """
    degraded = DEGRADED_BADGE if gw.is_degraded() else HEALTHY_BADGE
    return " &nbsp;·&nbsp; ".join([
        degraded,
        MEMORY_BADGE.format(backend=memory_backend()),
        RUN_BADGE.format(status=run_status(store))])


def approval_text(pending) -> str:
    """Onay çubuğunun metni; bekleyen aksiyon yoksa boş dize.

    Aynı anda **en fazla bir** aksiyon onay bekleyebiliyor (Görev 14 kapıyı
    girişte kapatıyor), bu yüzden çubuk bir kuyruk değil tek bir satır.
    """
    if pending is None:
        return ""
    return APPROVAL_PROMPT.format(tool=pending.tool_name, params=pending.params)


def apply_approval(nobetci, action_id: int, approved: bool) -> tuple[str, object]:
    """Operatörün kararını uygular; `(operatöre metin, bekleyen aksiyon)`.

    `approve()` istisna atmıyor, dört durumdan biriyle dönüyor ve dördü de
    farklı bir şey söylüyor — sessizce aynı kutuya konamazlar.

    `"approved"` **onayın işlendiğini** söyler, hattın durduğunu değil: araç
    sonucu İÇ İÇE duruyor (`result["result"]["state"]`) ve hattın gerçekten
    durduğu ancak orada `"halted"` yazıyorsa doğrudur. Düz birleştirmede o
    değer onayın kendi durumunu eziyordu; ayrımın ekranda da korunması lazım,
    yoksa "onayladım" ile "hat durdu" aynı cümleye düşer.

    Karardan sonra çubuk **süpervizörden yeniden okunuyor**: okunmazsa bayat
    satırın üstünde açık kalır ve onaydan sonra kaybolmaz.
    """
    result = nobetci.approve(action_id, approved)
    state = result.get("state")

    if state == "approved":
        inner = (result.get("result") or {}).get("state")
        text = (HALTED_NOTE if inner == "halted"
                else NOT_HALTED_NOTE.format(state=inner))
    elif state == "rejected":
        text = REJECTED_NOTE
    elif state == "unknown_action":
        text = UNKNOWN_ACTION_NOTE
    elif state == "not_pending":
        text = NOT_PENDING_NOTE.format(approval=result.get("approval"))
    else:
        text = UNEXPECTED_NOTE.format(state=state)

    return text, nobetci.pending_approval()


def handoff_rows(handoffs: list) -> list[list[str]]:
    """Devir defterinin satırları — "sistem neden böyle karar verdi"nin cevabı."""
    return [[mmss(handoff.ts), handoff.source_agent, handoff.target_agent,
             handoff.reason, f"{handoff.confidence:.2f}"]
            for handoff in handoffs]


def tool_rows(actions: list) -> list[list[str]]:
    """Araç şeridinin satırları — çağrılan her mock fonksiyon.

    Zaman damgası **video zamanı**; çizelge ve kök neden raporu da aynı saati
    kullanıyor ve üç ekran birbirini tutmak zorunda.

    Sıralama zaman: defterin yazılma sırası çağrı sırası olsa bile, telafi
    (`catch_up`) sonradan yazılan bir çağrıyı önceki bir saniyeye koyabiliyor.
    """
    return [[mmss(action.ts),
             action.tool_name,
             _pairs(action.params),
             _pairs(action.result),
             APPROVAL_LABELS.get(action.approval, action.approval),
             ACTOR_LABELS.get(action.actor, action.actor)]
            for action in sorted(actions, key=lambda a: a.ts)]


def tool_summary(actions: list) -> str:
    """`7 araçtan 3'ü çağrıldı · 12 çağrı · 2 onay` — tek satırlık kanıt.

    Katalog boyutu `TOOLS`'tan okunuyor, elle yazılmıyor: sabit bir sayı yeni
    bir araç eklendiği gün sessizce yalana dönerdi.
    """
    from gozcu.tools.registry import TOOLS

    if not actions:
        return f"**{NO_TOOLS_YET}** — katalogda {len(TOOLS)} araç var."
    used = {action.tool_name for action in actions}
    gated = sum(1 for action in actions
                if action.approval in ("pending", "approved", "rejected"))
    return (f"**{len(TOOLS)} araçtan {len(used)}'i çağrıldı** · "
            f"{len(actions)} çağrı · {gated} onay")


def _pct(value) -> str:
    """Oranı yüzdeye çevirir; `None` ise ölçülemediğini YAZAR.

    `benchmark/kpi.py` ile aynı sözleşme: `0` "ölçtük, sıfır çıktı" demek ve
    ölçülemeyen bir hücreye yazılırsa sonuç gibi görünen bir yalan olur.
    """
    if value is None:
        return KPI_UNMEASURED
    # Ondalık AYIRICI VİRGÜL: depodaki bütün Türkçe metin ("%72,4") böyle
    # yazıyor ve panelin nokta kullanması iki belgeyi ayrı dillere böler.
    return f"%{value * 100:.1f}".replace(".", ",")


def perception_markdown(path=None) -> str:
    """Algı bloğu — `bench/perception.json`'dan okunur, hesaplanmaz.

    Dosya yoksa ya da bozuksa **uydurulmuyor**: blok "ölçülemedi" diyor.
    Konsolun ölçüm göstermesi, ölçüm yapması demek değil.
    """
    import json

    target = Path(path) if path is not None else REPO_ROOT / PERCEPTION_BENCH
    try:
        result = json.loads(Path(target).read_text(encoding="utf-8"))["result"]
    except Exception:              # noqa: BLE001 — panel koşuyu düşürmez
        return (f"**{KPI_PERCEPTION}** — {KPI_UNMEASURED} "
                f"(`{PERCEPTION_BENCH}` okunamadı; "
                "`python -m benchmark.perception <video>` ile üretilir)")
    return "\n".join([
        f"**{KPI_PERCEPTION}** — elle etiketli kayıttan",
        "",
        f"- Varlık duyarlılığı: **{_pct(result.get('presence_recall'))}**",
        f"- Sayım duyarlılığı: **{_pct(result.get('count_recall'))}**",
        "- Kaza saniyesi enerji yüzdeliği: "
        f"**{_pct(result.get('incident_energy_percentile'))}** (0 = en hareketli)",
        f"- Kare: {result.get('frames', KPI_UNMEASURED)} · "
        "gerçek zaman katsayısı: "
        + (KPI_UNMEASURED if result.get("real_time_factor") is None
           else f"{result['real_time_factor']:.2f}".replace(".", ",")),
    ])


def decision_markdown(store) -> str:
    """Karar bloğu — canlı depodan, `benchmark/kpi.py` fonksiyonlarıyla."""
    from benchmark.kpi import (decision_distribution, turkish_output_rate,
                               vlm_trigger_rate)

    distribution = decision_distribution(store)
    lines = [f"**{KPI_DECISION}** — bu koşudan", "",
             f"- Görü tetikleme oranı: **{_pct(vlm_trigger_rate(store))}**",
             f"- Türkçe çıktı oranı: **{_pct(turkish_output_rate(store))}**"]
    if not distribution:
        lines.append(f"- Karar dağılımı: {KPI_UNMEASURED}")
    else:
        lines.extend(f"- {bucket}: {_pct(share)}"
                     for bucket, share in distribution.items())
    return "\n".join(lines)


def performance_markdown(store, elapsed_s: float | None = None) -> str:
    """Performans bloğu — şartname §4'ün saydığı kalemler."""
    episodes = store.episodes()
    lines = [f"**{KPI_PERFORMANCE}**", "",
             f"- Epizot: {len(episodes)} · devir: {len(store.handoffs())} · "
             f"araç çağrısı: {len(store.actions())}",
             f"- Koşu durumu: {run_status(store)}"]
    lines.append("- İşleme süresi: "
                 + (KPI_UNMEASURED if elapsed_s is None
                    else f"**{elapsed_s:.1f} s**".replace(".", ",")))
    return "\n".join(lines)


def kpi_markdown(store, elapsed_s: float | None = None) -> str:
    """Ölçüm panelinin tamamı — üç blok, üçü de ayrı kaynaktan."""
    return "\n\n---\n\n".join([perception_markdown(),
                                 decision_markdown(store),
                                 performance_markdown(store, elapsed_s)])


def payload_json(output) -> str:
    """Teslim edilen dört anahtarın JSON'u."""
    if output is None:
        return NO_RUN_YET
    return output.model_dump_json(indent=2)


def root_cause_markdown(output) -> str:
    """Kök neden raporu — yoksa YOKLUĞU yazılır, boş bir rapor uydurulmaz.

    Üç ayrı yokluk var ve üçü farklı şeyler söylüyor: koşu hiç olmadı,
    genişletilmiş katman çöktü (`detail=None`), koşu tamam ama kayda değer
    olay yok. Aynı cümleye düşerlerse ekran yanlış bir şey söyler.
    """
    if output is None:
        return NO_RUN_YET
    if output.detail is None:
        return CRASHED_RUN
    report = output.detail.root_cause_report
    if not report:
        return NO_ROOT_CAUSE

    def _bullets(items) -> str:
        return "\n".join(f"- {item}" for item in (items or [])) or "- (yok)"

    return "\n\n".join([
        f"### Ne oldu\n{report.get('what_happened', '')}",
        f"### Muhtemel kök neden\n{report.get('probable_root_cause', '')}",
        f"### Yürütülen aksiyonlar\n{_bullets(report.get('actions_taken'))}",
        "### Önleme önerileri\n"
        f"{_bullets(report.get('prevention_recommendations'))}",
        f"### Güven sınırları\n{report.get('confidence_limits', '')}"])


# =============================================================================
# Yerel görü sunucusu — yalnız çevrimdışı kurulum için
# =============================================================================

def _ensure_server_running() -> None:
    """`GOZCU_VLM_BASE_URL`'deki yerel mlx-vlm sunucusunu ayağa kaldırır.

    **Demo yolu buradan geçmiyor:** yorumlayıcı görü kademesini paylaşılan
    `Gateway` üzerinden çağırıyor (`GOZCU_GATEWAY_BASE_URL`). Bu yardımcı,
    ağ geçidi yerine yerel bir mlx-vlm sunucusuna bağlanan çevrimdışı kurulum
    için duruyor ve `baslat(yerel_vlm=True)` ile açıkça isteniyor.

    mlx-vlm kurulu değilken alt süreç **açılmıyor**: `uv run mlx_vlm.server`
    çağrısı sessizce ölür ve konsol 120 saniye boyunca hiçbir şey söylemeden
    bekler. Hata okunur ve ne yapılacağını söylüyor.
    """
    global _server_process
    client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    try:
        client.models.list()
        return
    except Exception:  # noqa: BLE001 — sunucu yok, kurmayı deneyeceğiz
        pass

    hostname = urlsplit(VLM_BASE_URL).hostname
    if hostname not in _LOCAL_HOSTNAMES:
        raise RuntimeError(
            f"{VLM_BASE_URL} adresindeki sunucuya erişilemiyor ve adres yerel "
            "değil — otomatik başlatma yalnız localhost için çalışıyor. "
            "Sunucuyu elle başlatın ya da adresi düzeltin.")

    if importlib.util.find_spec("mlx_vlm") is None:
        raise RuntimeError(
            f"{VLM_BASE_URL} adresinde sunucu yok ve mlx-vlm kurulu değil. "
            "Apple Silicon'daysan: uv sync --extra dev --extra mac. "
            "Değilsen GOZCU_VLM_BASE_URL'i çalışan bir gateway'e çevir.")

    port = urlsplit(VLM_BASE_URL).port
    port = str(port) if port is not None else str(_DEFAULT_LOCAL_PORT)
    _server_process = subprocess.Popen(
        ["uv", "run", "mlx_vlm.server", "--model", VLM_MODEL, "--port", port])

    for _ in range(60):
        try:
            client.models.list()
            return
        except Exception:  # noqa: BLE001 — sunucu henüz ayakta değil
            time.sleep(2)
    raise RuntimeError(
        f"mlx_vlm.server 120 saniyede {VLM_BASE_URL} adresinde ayağa kalkmadı.")


# =============================================================================
# Oturum — tek bir demo koşusunun canlı durumu
# =============================================================================

class Session:
    """Bir analiz koşusunun bütün tutamakları.

    `loop` `run_pipeline`'ın `on_loop_ready`'sinden geliyor: döngü o
    fonksiyonun yereliydi ve dışarıdan `catch_up()` çağrılamıyordu — demo
    beat 6'nın ikinci yarısı (bağlantı geri geldi, açık kapatıldı) bu tutamak
    olmadan gösterilemez.
    """

    def __init__(self) -> None:
        self.store = Store()
        self.gw = Gateway(self.store)
        self.nobetci = Supervisor(self.gw, self.store)
        self.loop = None
        self.output = None
        self.error: Exception | None = None
        self.events: list = []
        self.signals: queue.Queue = queue.Queue()
        self.resume = threading.Event()
        #: `Adım adım` anahtarı. Kapalıyken `on_event` BLOKLAMIYOR; müdahale
        #: anı bir kart olarak basılıp koşu devam ediyor.
        self.step_mode = STEP_MODE_DEFAULT
        # Telafi ile canlı döngü aynı `deferred` listesine dokunuyor; kuyruğu
        # aynı anda iki taraf boşaltmasın.
        self.lock = threading.Lock()
        self.finished = False
        self.started_at = time.monotonic()
        #: Koşudan ÖNCE depoda duran epizotlar — `fixtures.loader.load_history`
        #: arşivi. Beslemeye girmiyorlar: bu videonun olayı değiller ve
        #: "sentezleyici olay açtı" diye görünmeleri olmamış bir şey iddia
        #: etmek olurdu. `run.py` aynı korumayı risk biçmesi için yapıyor.
        self.archived = {episode.id for episode in self.store.episodes()}
        #: En son çizilen besleme HTML'i — aynıysa bileşen atlanıyor
        #: (bkz. `_feed_slot`).
        self.last_feed: str | None = None

    def escalated_ids(self) -> set:
        """Ajanın gerçekten yükselttiği epizot kimlikleri.

        `LoopEvent` listesi kaynak: kart yalnız bunlar için basılıyor.
        Depodaki epizot listesi bu soruyu cevaplayamaz — açılan bir epizot
        yükseltilmemiş de olabilir.
        """
        return {event.episode.id for event in self.events
                if getattr(event, "episode", None) is not None}

    def elapsed_s(self) -> float:
        """Koşunun başından beri geçen süre — şartname §4'ün 'video işleme
        süresi' kalemi."""
        return time.monotonic() - self.started_at


def _pending(session: Session):
    return session.nobetci.pending_approval()


def _wait_if_step_mode(session: Session) -> None:
    """Yalnız `Adım adım` açıkken operatörü bekler.

    Kapalıyken hemen dönüyor ve videonun zaman çizelgesi akmaya devam
    ediyor. Bloklama kaldırılmadı, **koşula bağlandı**: "kararlar olay anında
    verilir" değişmezi generator'ın kendisinde duruyor, konsolun beklemesinde
    değil — kart da o anın kanıtı.
    """
    if not session.step_mode:
        return
    session.resume.clear()
    session.resume.wait()


def _feed_slot(session: Session):
    """Besleme yuvası — dize değişmediyse bileşeni HİÇ güncellemez.

    `column-reverse` kaydırıcı her yeniden çizimde SIFIRDAN doğuyor ve
    `scrollTop = 0` ile, yani görsel altta başlıyor. İstenen sonuç bu — ama
    bedeli şu: jüri geçmişi okumak için yukarı kaydırdıysa bir sonraki kalp
    atışı onu en alta geri atar. `gr.skip()` bunu kapatıyor; kaydırma yalnız
    GERÇEKTEN yeni bir girdi düştüğünde sıfırlanıyor, ki zaten istenen
    davranış o.

    `feed_html` bu yüzden kesinlikle deterministik olmak zorunda: çizim anı
    ya da duvar saati dizeye girerse atlama hiç çalışmaz.
    """
    drawn = feed_html(build_feed(session.store, session.escalated_ids(),
                                 session.archived))
    if drawn == session.last_feed:
        return gr.skip()
    session.last_feed = drawn
    return drawn


def _refresh(session: Session, state: str, note: str = ""):
    """Ekranın tamamını depodan yeniden çizer.

    Tek bir yerden çiziliyor: her düğmenin kendi kısmi tazelemesi olsaydı bir
    düğme beslemeyi, bir başkası defteri güncellemeyi unuturdu.
    """
    pending = _pending(session)
    return (session,
            status_badges(session.gw, session.store),
            _feed_slot(session),
            gr.update(visible=pending is not None),
            approval_text(pending),
            handoff_rows(session.store.handoffs()),
            tool_summary(session.store.actions()),
            tool_rows(session.store.actions()),
            kpi_markdown(session.store, session.elapsed_s()),
            payload_json(session.output),
            root_cause_markdown(session.output),
            state,
            note)


def _blank(state: str):
    """Oturum yokken çizilecek boş ekran."""
    return (None, "", feed_html([]), gr.update(visible=False), "", [],
            tool_summary([]), [],
            # Algı ölçümü koşudan bağımsız: elle etiketli bir kayıtta
            # ölçüldü ve analiz başlatılmadan da gösterilmeli.
            perception_markdown(),
            NO_RUN_YET, NO_RUN_YET, state, "")


def _set_step_mode(enabled: bool, session: Session):
    """Anahtar koşu SIRASINDA da değişebilmeli.

    Duraklamayı açan operatör bir sonraki müdahale anında durmak isteyebilir;
    kapatan kişi ise o an bekleyen döngüyü serbest bırakmalı, yoksa anahtarı
    kapatmak koşuyu kilitli bırakırdı.

    "Devam et" düğmesi anahtara bağlı görünüyor: anahtar kapalıyken hiçbir
    şey `resume`'u beklemiyor, yani düğme HİÇBİR ŞEY yapmıyor. 4 dakikalık
    bir sunumda çalışmayan bir düğme, jürinin sorduğu ilk şey olur.
    """
    enabled = bool(enabled)
    if session is not None:
        session.step_mode = enabled
        if not enabled:
            session.resume.set()
    return gr.update(visible=enabled)


def _analyse(video_path, session: Session, step_mode: bool = STEP_MODE_DEFAULT):
    """**Analizi başlat** — koşuyu arka planda sürer, ekranı akıtır.

    `run_pipeline` ayrı bir iş parçacığında koşuyor ama duraklama numara
    değil: `on_event` o iş parçacığında, olayın tam anında çağrılıyor ve
    `resume` beklenirken videonun zaman çizelgesi gerçekten duruyor.
    """
    if not video_path:
        yield _blank(STATE_NO_VIDEO)
        return

    session = Session()
    session.step_mode = bool(step_mode)

    def on_loop_ready(loop) -> None:
        session.loop = loop

    def on_event(event) -> None:
        session.events.append(event)
        session.signals.put("event")
        # Adım adım KAPALIYKEN burada beklenmiyor: müdahale anı karta
        # yazılıyor ve koşu sürüyor. Bu bir çevrimdışı kayıt; operatörün
        # gerçekten müdahale edeceği bir an yok (şartname §3) ve bekleyen
        # bir arayüz 4 dakikalık sunum bütçesini yiyor (§11).
        _wait_if_step_mode(session)

    def _work() -> None:
        try:
            session.output, _ = run_pipeline(
                video_path, store=session.store, gw=session.gw,
                nobetci=session.nobetci, on_event=on_event,
                on_loop_ready=on_loop_ready)
        except Exception as error:  # noqa: BLE001 — ekranda görünmeli
            session.error = error
        finally:
            session.finished = True
            session.signals.put("done")

    threading.Thread(target=_work, daemon=True).start()
    yield _refresh(session, STATE_RUNNING)

    while True:
        try:
            signal = session.signals.get(timeout=HEARTBEAT_S)
        except queue.Empty:
            if session.finished:
                break
            yield _refresh(session, STATE_RUNNING)   # çizelge dolarken tazele
            continue
        if signal == "done":
            break
        yield _refresh(session,
                       STATE_PAUSED if session.step_mode else STATE_INTERVENED)

    if session.error is not None:
        yield _refresh(session, STATE_FAILED.format(error=session.error))
    else:
        yield _refresh(session, STATE_DONE)


def _resume(session: Session):
    """**Devam et** — duraklamış döngüyü ilerletir."""
    if session is None:
        return _blank(STATE_IDLE)
    session.resume.set()
    return _refresh(session, STATE_RESUMED)


def _cut_link(session: Session):
    """**Bağlantıyı kes** — görü kademesine kesinti enjekte eder.

    Jürinin gözü önünde basılıyor: sistem çökmüyor, yerel algı sürüyor,
    atlanan pencereler `DecisionLoop.deferred`'da birikiyor.
    """
    if session is None:
        return _blank(STATE_IDLE)
    session.gw.inject_failure({"vlm"})
    return _refresh(session, STATE_CUT)


def _restore_link(session: Session):
    """**Bağlantıyı geri ver** — kesintiyi kaldırır ve açığı kapatır.

    İki adım tek düğmede: enjeksiyon temizleniyor, sonra `catch_up()`
    çağrılıyor. Yalnız birincisi yapılsaydı atlanan pencereler kuyrukta
    kalırdı ve telafi hiç görünmezdi — beat 6'nın yarısı ekranda olmazdı.

    Telafiden çıkan epizotlar `late=True` geliyor ve `_announce` onları
    `LATE_NOTICE` ile damgalıyor: geç keşfedilen bir olayı saklamak kabul
    edilemez, canlı bir kriz gibi duyurmak da yanıltıcı.
    """
    if session is None:
        return _blank(STATE_IDLE)
    session.gw.inject_failure(set())
    if session.loop is None:
        return _refresh(session, STATE_NO_LOOP)

    with session.lock:
        recovered = 0
        for event in session.loop.catch_up():
            _announce(session.store, session.nobetci, event, None)
            session.events.append(event)
            recovered += 1
    return _refresh(session, STATE_RESTORED.format(count=recovered))


def _stress(session: Session, key: str):
    """Zorlu koşul düğmesi — hazır metni Nöbetçi'ye gönderir.

    Bilinmeyen anahtar **sessizce boş mesaj göndermiyor**: yanlış yazılmış
    bir anahtar, ajanı boş bir turla meşgul edip demo sırasında anlamsız bir
    cevap ürettirirdi.
    """
    if session is None:
        return (*_blank(STATE_IDLE)[:-1], "Önce analizi başlatın.")
    prompt = STRESS_PROMPTS.get(key)
    if prompt is None:
        return _refresh(session, STATE_RUNNING,
                        f"Bilinmeyen zorlu koşul: {key}")
    session.nobetci.talk(prompt[1])
    return _refresh(session, STATE_RUNNING, f"Zorlu koşul: {prompt[0]}")


def _say(text: str, session: Session):
    """Sohbet paneli — bir diyalog turu.

    Cevap deftere `Supervisor` tarafından yazılıyor; ekran depodan yeniden
    çiziliyor, dönen dizeden değil. Bekleyen onay bildirimi de `.talk()`'un
    döndürdüğü metnin içinde geliyor ve aynı yoldan ekrana düşüyor.
    """
    if session is None:
        return (*_blank(STATE_IDLE)[:-1], "Önce analizi başlatın.")
    if not (text or "").strip():
        return _refresh(session, STATE_RUNNING)
    session.nobetci.talk(text)
    return _refresh(session, STATE_RUNNING)


def _decide(session: Session, approved: bool):
    """**Onayla** / **Reddet** — tek bir bekleyen aksiyonun kararı."""
    if session is None:
        return _blank(STATE_IDLE)
    pending = _pending(session)
    if pending is None:
        return _refresh(session, STATE_RUNNING, UNKNOWN_ACTION_NOTE)
    note, _ = apply_approval(session.nobetci, pending.id, approved)
    return _refresh(session, STATE_RUNNING, note)


# =============================================================================
# Gradio bağlantısı
# =============================================================================

def build() -> gr.Blocks:
    """Konsolun `Blocks` ağacı. Kurar, başlatmaz — test ve `baslat()` ortak.

    **İki sekme, çünkü beşi işi YANLIŞ eksende bölüyordu.** 25 Ağustos'ta
    sekmeler eklendi ve doğru bir sorunu çözdüler (4 dakikalık sunumda uzun
    kaydırma). Ama bölme ekseni kaynaktı: devirler bir sekmede, araç
    çağrıları başkasında, süpervizörün konuşması üçüncüde — hepsi aynı on
    saniyede olup bitmiş şeyler. Jüri, ajanların birbirine ne devrettiğini
    görmek için sekme değiştirmek ve iki tabloyu damgadan elle eşleştirmek
    zorundaydı. Şartname §7 "çok adımlı karar zincirleri"ni doğrudan
    puanlıyor ve o zincir hiçbir ekranda bir arada yoktu.

    Yeni eksen ZAMAN: **CANLI** olan biteni oluş sırasında akıtıyor,
    **RAPOR** teslim edileni ve tam kaydı tutuyor.

    Rozet şeridi ve durum çubuğu sekmelerin DIŞINDA: hangi sekmede olursak
    olalım "şu an ne oluyor" görünür kalmalı.
    """
    with gr.Blocks(title="Gözcü — Operatör Konsolu") as demo:
        session = gr.State(None)

        gr.Markdown("# Gözcü — Operatör Konsolu")
        badges = gr.Markdown("")
        state_box = gr.Markdown(STATE_IDLE)

        with gr.Tabs():
            with gr.Tab("CANLI"):
                # TEK kolon. Video ve kontroller yukarıda sabit duruyor,
                # besleme altta kendi içinde kayıyor — `column-reverse`
                # olduğu için kalp atışı yeniden çizimlerinde en yeni
                # girdide kalıyor (bkz. `feed.feed_html`, `_feed_slot`).
                # Yükseklik SABİT: tek kolonda video boy verirse besleme
                # tamamen kıvrımın altına iner ve 4 dakikalık sunumda jüri
                # akışı hiç görmez. Yıldız besleme, video girdi.
                video = gr.Video(label="Kamera kaydı", height=260)
                with gr.Row():
                    start_btn = gr.Button("Analizi başlat", variant="primary")
                    resume_btn = gr.Button("Devam et",
                                           visible=STEP_MODE_DEFAULT)
                    cut_btn = gr.Button("Bağlantıyı kes", variant="stop")
                    restore_btn = gr.Button("Bağlantıyı geri ver")
                step_toggle = gr.Checkbox(
                    value=STEP_MODE_DEFAULT,
                    label="Adım adım (kritik anda dur)",
                    info="Kapalıyken koşu durmaz; müdahale anları beslemede "
                         "kart olarak, olduğu anda görünür.")
                gr.Markdown("**Zorlu koşullar** — tek tıkla (§6)")
                with gr.Row():
                    stress_buttons = {
                        key: gr.Button(label, size="sm")
                        for key, (label, _) in STRESS_PROMPTS.items()}
                with gr.Row():
                    operator_text = gr.Textbox(
                        placeholder="Operatör mesajı…", show_label=False,
                        scale=5)
                    send_btn = gr.Button("Gönder", scale=1)
                with gr.Group(visible=False) as approval_box:
                    gr.Markdown("### Onay bekleniyor")
                    approval_box_text = gr.Markdown("")
                    with gr.Row():
                        approve_btn = gr.Button("Onayla", variant="primary")
                        reject_btn = gr.Button("Reddet", variant="stop")
                approval_note = gr.Markdown("")
                feed = gr.HTML(feed_html([]))

            with gr.Tab("RAPOR"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Teslim edilen yük (dört anahtar)")
                        payload = gr.Code(value=NO_RUN_YET, language="json",
                                          label="JSON")
                    with gr.Column():
                        gr.Markdown("### Kök neden raporu")
                        report = gr.Markdown(NO_RUN_YET)
                gr.Markdown("### KPI — şartname §4")
                kpi = gr.Markdown(perception_markdown())
                # Besleme anlatı, bu iki tablo TAM KAYIT. Şartname §7 "mock
                # fonksiyonların ajanın araçları olarak başarıyla
                # kullanılması"nı doğrudan puanlıyor ve jüri sayılabilir bir
                # tablo istiyor — akışta sayılamaz.
                gr.Markdown("### Çağrılan saha araçları")
                tool_count = gr.Markdown(tool_summary([]))
                tools = gr.Dataframe(headers=TOOL_HEADERS, value=[],
                                     interactive=False, wrap=True)
                gr.Markdown("### Devir defteri")
                ledger = gr.Dataframe(headers=HANDOFF_HEADERS, value=[],
                                      interactive=False, wrap=True)

        # Her olay ekranın TAMAMINI tazeliyor; kısmi tazeleme bir düğmenin
        # çizelgeyi, bir başkasının defteri unutmasıyla biterdi. Sekmeler bunu
        # değiştirmiyor: görünmeyen sekme de tazeleniyor, yoksa jüri sekmeye
        # geçtiğinde bayat veri görürdü.
        screen = [session, badges, feed, approval_box, approval_box_text,
                  ledger, tool_count, tools, kpi, payload, report, state_box,
                  approval_note]

        step_toggle.change(_set_step_mode, [step_toggle, session], resume_btn)
        start_btn.click(_analyse, [video, session, step_toggle], screen)
        resume_btn.click(_resume, session, screen)
        cut_btn.click(_cut_link, session, screen)
        restore_btn.click(_restore_link, session, screen)
        send_btn.click(_say, [operator_text, session], screen).then(
            lambda: "", None, operator_text)
        operator_text.submit(_say, [operator_text, session], screen).then(
            lambda: "", None, operator_text)
        for key, button in stress_buttons.items():
            button.click(lambda s, k=key: _stress(s, k), session, screen)
        approve_btn.click(lambda s: _decide(s, True), session, screen)
        reject_btn.click(lambda s: _decide(s, False), session, screen)

    return demo


def baslat(yerel_vlm: bool = False, **launch):
    """Konsolu açar. `app.py` yalnız bunu çağırıyor.

    `yerel_vlm=True` çevrimdışı kurulum içindir: görü kademesi paylaşılan ağ
    geçidi yerine yerel bir mlx-vlm sunucusundan geliyorsa sunucu önce ayağa
    kaldırılır. Demo yolu bunu kullanmıyor.
    """
    if yerel_vlm:
        _ensure_server_running()
    demo = build()
    # Kuyruk şart: analiz bir generator ve "Devam et" o akarken basılıyor.
    demo.queue()
    # Tema Gradio 6'da `launch()`'un parametresi, `Blocks()`'un değil.
    launch.setdefault("theme", gr.themes.Soft())
    return demo.launch(**launch)
