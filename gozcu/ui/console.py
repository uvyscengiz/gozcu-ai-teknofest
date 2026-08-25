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

## Depoda kilit yok

Konsol, koşan bir `DecisionLoop`'un yazmakta olduğu SQLite'ı okuyor;
`Store`'un WAL'ı ya da kilidi yok. Tablolar bu yüzden döngünün `yield` ettiği
anlarda ve saniyede bir kalp atışıyla tazeleniyor — daha sık yoklama okuma
tarafını yarıştırır, daha seyreği "zaman çizelgesi doluyor" sözünü tutmaz.
"""

import html
import importlib.util
import queue
import subprocess
import threading
import time
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

__all__ = ["baslat"]

# --- risk renkleri ----------------------------------------------------------
#
# Değerler Türkçe kalıyor ve `RiskLevel` ile birebir aynı (CLAUDE.md). Şema ile
# bu tablo ayrışırsa çizelge sessizce gri basar — bu yüzden bilinmeyen seviye
# gerçek bir rengi ÖDÜNÇ ALMIYOR, kendi rengine düşüyor.
GREEN = "#2e7d32"
YELLOW = "#f9a825"
ORANGE = "#ef6c00"
RED = "#c62828"
UNKNOWN_COLOR = "#546e7a"

RISK_COLORS = {"Düşük": GREEN, "Orta": YELLOW, "Yüksek": ORANGE,
               "Kritik": RED}

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

TIMELINE_EMPTY = "Henüz kayda değer olay yok."
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
APPROVAL_LABELS = {
    "not_required": "otomatik",
    "pending": "⏸ onay bekliyor",
    "approved": "✓ onaylandı",
    "rejected": "✗ reddedildi",
}

#: Çağıranın karşılığı. Ajanın kendi kararıyla çağırdığı araç ile operatörün
#: tetiklediği araç aynı görünmemeli — %20'lik otonomi kriteri tam olarak bu
#: farkı soruyor.
ACTOR_LABELS = {"agent": "🤖 ajan", "operator": "👤 operatör"}

#: Ekranın yuva sayısı — her işleyici tam bu kadar değer döndürmek zorunda.
#: Eksik bir çıktı Gradio'da hata vermiyor, o bileşen sessizce tazelenmiyor.
#: 25 Ağustos: 11 → 13 (araç şeridi tablosu + sayacı).
SCREEN_SLOTS = 13

#: Yuvaların ADI. `_refresh`'in döndürdüğü demet ile `build()`'deki `screen`
#: listesi bu sırayı paylaşıyor. Sayıyla indekslemek bir kez ısırdı: araya
#: iki yuva eklendiğinde testteki `final[7]` sessizce başka bir bileşeni
#: okudu. Yeni yuva eklerken **buraya da** eklenecek.
SLOT = {name: index for index, name in enumerate([
    "session", "badges", "timeline", "chat", "approval_box",
    "approval_text", "ledger", "tool_count", "tools", "payload",
    "report", "state", "note"])}

# Durum çubuğunun metinleri — jürinin "şimdi ne oluyor" sorusu.
STATE_IDLE = "Hazır. Bir kayıt yükleyip **Analizi başlat**'a basın."
STATE_NO_VIDEO = "Önce bir kamera kaydı yükleyin."
STATE_RUNNING = "Analiz koşuyor — video kendi saatinde işleniyor."
STATE_PAUSED = ("⏸ **Kritik olayda duruldu.** Nöbetçi operatöre seslendi; "
                "video bekliyor. Konuşabilir ya da **Devam et**'e basabilirsiniz.")
STATE_RESUMED = "▶ Video kaldığı yerden sürüyor."
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


# =============================================================================
# Saf katman — ekrana ne basılacağı
# =============================================================================

def risk_color(level: str) -> str:
    """Risk seviyesinin rengi; tanınmayan seviye kendi rengine düşer."""
    return RISK_COLORS.get(level, UNKNOWN_COLOR)


def visible_dialogue(turns: list) -> list:
    """Sohbet panelinde gösterilecek diyalog satırları.

    **Yalnız `[denetim]` ile BAŞLAYAN `role="system"` satırları süzülüyor.**
    Onlar denetim hükmünün kaydı, operatöre söylenmiş bir söz değil.

    Düz bir `role != "system"` süzgeci ise bozulmuş modu ekrandan siler:
    `Supervisor._fault`'un DEGRADED/EMPTY/UNFINISHED cevapları, `run.py`'nin
    `LATE_NOTICE` damgası ve bekleyen onay bildirimi hep `system` satırı — ve
    demo beat 6'da jürinin görmesi gereken şey tam olarak bunlar.
    """
    return [turn for turn in turns
            if not (turn.role == "system"
                    and turn.text.startswith(AUDIT_PREFIX))]


def chat_messages(turns: list) -> list[dict]:
    """Diyaloğu `gr.Chatbot`'un mesaj biçimine çevirir.

    Proaktif uyarı ile cevap görsel olarak ayrışıyor ve ayrım **türetiliyor**,
    saklanan bir bayrağa dayanmıyor: `talk()` önce operatör satırını yazıyor,
    `escalate()` hiçbir şey sormadan konuşuyor. Yani kendinden önce operatör
    satırı olmayan bir süpervizör satırı kimse sormadan söylenmiştir.
    """
    messages: list[dict] = []
    previous_role: str | None = None
    for turn in visible_dialogue(turns):
        if turn.role == "operator":
            messages.append({"role": "user", "content": turn.text})
        elif turn.role == "system":
            messages.append({"role": "assistant",
                             "content": f"{SYSTEM_MARK} {turn.text}"})
        else:
            mark = "" if previous_role == "operator" else f"{PROACTIVE_MARK} "
            messages.append({"role": "assistant",
                             "content": f"{mark}{turn.text}"})
        previous_role = turn.role
    return messages


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


def timeline_rows(episodes: list) -> list[tuple[str, str, str, str]]:
    """Zaman çizelgesinin satırları: `(MM:SS, metin, risk, renk)`.

    Damga **video zamanı** — kök neden raporu da aynı biçimi kullanıyor, iki
    ekran aynı saati göstermek zorunda.

    Epizot kendi içinde bir zaman çizelgesi taşıyor: satırlar **an başına**
    açılıyor, çünkü tek satıra düşürülürse operatör 10 saniyelik bir
    pencerede olayın seyrini değil yalnız pencerenin sınırını görür. An
    listesi boş olan epizot tek satır kalıyor, damgası pencere başlangıcı —
    teslim edilen `events[]` ile aynı kural (bkz. `gozcu.report._events`).
    """
    rows: list[tuple[str, str, str, str]] = []
    for episode in episodes:
        color = risk_color(episode.preliminary_risk)
        if not episode.beats:
            rows.append((mmss(episode.start_ts), episode.summary_tr,
                         episode.preliminary_risk, color))
            continue
        rows.extend((mmss(beat.ts), beat.text, episode.preliminary_risk, color)
                    for beat in sorted(episode.beats, key=lambda b: b.ts))
    return rows


def timeline_html(episodes: list) -> str:
    """Videonun yanındaki renk kodlu epizot listesi.

    Gradio'nun video sürgüsüne renkli işaret koyacak bir ilkeli yok; liste
    aynı bilgiyi taşıyor ve okunması daha kolay. Özet metni modelden geliyor,
    bu yüzden HTML olarak kaçırılıyor — ham basılırsa sayfayı bozar.
    """
    rows = timeline_rows(episodes)
    if not rows:
        return f"<p style='opacity:.7'>{TIMELINE_EMPTY}</p>"
    items = "".join(
        f"<li style='border-left:6px solid {color};padding:.35rem .6rem;"
        f"margin:.3rem 0;list-style:none'>"
        f"<b>{html.escape(stamp)}</b> &nbsp; {html.escape(summary)}<br>"
        f"<span style='color:{color};font-weight:600'>{html.escape(level)}</span>"
        f"</li>"
        for stamp, summary, level, color in rows)
    return f"<ul style='margin:0;padding:0'>{items}</ul>"


def handoff_rows(handoffs: list) -> list[list[str]]:
    """Devir defterinin satırları — "sistem neden böyle karar verdi"nin cevabı."""
    return [[mmss(handoff.ts), handoff.source_agent, handoff.target_agent,
             handoff.reason, f"{handoff.confidence:.2f}"]
            for handoff in handoffs]


def _pairs(mapping: dict, limit: int = 3) -> str:
    """Sözlüğü `anahtar=değer` olarak yazar; boşsa tire.

    Boş bırakmak yerine tire: boş bir hücre "parametresiz çağrıldı" ile
    "gösterilmedi" arasındaki farkı yutar.
    """
    if not mapping:
        return "—"
    items = list(mapping.items())[:limit]
    text = ", ".join(f"{key}={value}" for key, value in items)
    return text + (" …" if len(mapping) > limit else "")


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
        # Telafi ile canlı döngü aynı `deferred` listesine dokunuyor; kuyruğu
        # aynı anda iki taraf boşaltmasın.
        self.lock = threading.Lock()
        self.finished = False


def _pending(session: Session):
    return session.nobetci.pending_approval()


def _refresh(session: Session, state: str, note: str = ""):
    """Ekranın tamamını depodan yeniden çizer.

    Tek bir yerden çiziliyor: her düğmenin kendi kısmi tazelemesi olsaydı bir
    düğme çizelgeyi, bir başkası defteri güncellemeyi unuturdu.
    """
    pending = _pending(session)
    return (session,
            status_badges(session.gw, session.store),
            timeline_html(session.store.episodes()),
            chat_messages(session.store.dialogue()),
            gr.update(visible=pending is not None),
            approval_text(pending),
            handoff_rows(session.store.handoffs()),
            tool_summary(session.store.actions()),
            tool_rows(session.store.actions()),
            payload_json(session.output),
            root_cause_markdown(session.output),
            state,
            note)


def _blank(state: str):
    """Oturum yokken çizilecek boş ekran."""
    return (None, "", timeline_html([]), [], gr.update(visible=False), "",
            [], tool_summary([]), [], NO_RUN_YET, NO_RUN_YET, state, "")


def _analyse(video_path, session: Session):
    """**Analizi başlat** — koşuyu arka planda sürer, ekranı akıtır.

    `run_pipeline` ayrı bir iş parçacığında koşuyor ama duraklama numara
    değil: `on_event` o iş parçacığında, olayın tam anında çağrılıyor ve
    `resume` beklenirken videonun zaman çizelgesi gerçekten duruyor.
    """
    if not video_path:
        yield _blank(STATE_NO_VIDEO)
        return

    session = Session()

    def on_loop_ready(loop) -> None:
        session.loop = loop

    def on_event(event) -> None:
        session.events.append(event)
        session.resume.clear()
        session.signals.put("event")
        session.resume.wait()          # operatör "Devam et" diyene kadar

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
        yield _refresh(session, STATE_PAUSED)

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
    """Konsolun `Blocks` ağacı. Kurar, başlatmaz — test ve `baslat()` ortak."""
    with gr.Blocks(title="Gözcü — Operatör Konsolu") as demo:
        session = gr.State(None)

        gr.Markdown("# Gözcü — Operatör Konsolu")
        badges = gr.Markdown("")
        state_box = gr.Markdown(STATE_IDLE)

        with gr.Row():
            with gr.Column(scale=3):
                video = gr.Video(label="Kamera kaydı")
                with gr.Row():
                    start_btn = gr.Button("Analizi başlat", variant="primary")
                    resume_btn = gr.Button("Devam et")
                with gr.Row():
                    cut_btn = gr.Button("Bağlantıyı kes", variant="stop")
                    restore_btn = gr.Button("Bağlantıyı geri ver")
            with gr.Column(scale=2):
                gr.Markdown("### Zaman çizelgesi")
                timeline = gr.HTML(timeline_html([]))

        with gr.Row():
            with gr.Column(scale=3):
                gr.Markdown("### Nöbetçi ile konuşma")
                # Gradio 6'da `type` yok: sohbet zaten yalnız
                # `{"role": ..., "content": ...}` sözlüklerini kabul ediyor.
                chat = gr.Chatbot(height=360, label="Sohbet")
                with gr.Row():
                    operator_text = gr.Textbox(
                        placeholder="Operatör mesajı…", show_label=False,
                        scale=5)
                    send_btn = gr.Button("Gönder", scale=1)
            with gr.Column(scale=2):
                with gr.Group(visible=False) as approval_box:
                    gr.Markdown("### Onay bekleniyor")
                    approval_box_text = gr.Markdown("")
                    with gr.Row():
                        approve_btn = gr.Button("Onayla", variant="primary")
                        reject_btn = gr.Button("Reddet", variant="stop")
                approval_note = gr.Markdown("")
                gr.Markdown("### Devir defteri")
                ledger = gr.Dataframe(headers=HANDOFF_HEADERS, value=[],
                                      interactive=False, wrap=True)

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Çağrılan saha araçları")
                tool_count = gr.Markdown(tool_summary([]))
                tools = gr.Dataframe(headers=TOOL_HEADERS, value=[],
                                     interactive=False, wrap=True)

        with gr.Row():
            with gr.Column():
                gr.Markdown("### Teslim edilen yük (dört anahtar)")
                payload = gr.Code(value=NO_RUN_YET, language="json",
                                  label="JSON")
            with gr.Column():
                gr.Markdown("### Kök neden raporu")
                report = gr.Markdown(NO_RUN_YET)

        # Her olay ekranın TAMAMINI tazeliyor; kısmi tazeleme bir düğmenin
        # çizelgeyi, bir başkasının defteri unutmasıyla biterdi.
        screen = [session, badges, timeline, chat, approval_box,
                  approval_box_text, ledger, tool_count, tools, payload,
                  report, state_box, approval_note]

        start_btn.click(_analyse, [video, session], screen)
        resume_btn.click(_resume, session, screen)
        cut_btn.click(_cut_link, session, screen)
        restore_btn.click(_restore_link, session, screen)
        send_btn.click(_say, [operator_text, session], screen).then(
            lambda: "", None, operator_text)
        operator_text.submit(_say, [operator_text, session], screen).then(
            lambda: "", None, operator_text)
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
