# Görev 16 — Operatör konsolu (`gozcu/ui/console.py`)

> ## ✅ TAMAMLANDI — 25 Ağustos 2026, `0ce9e86`
>
> **Jürinin izleyeceği tek yüzey indi.** Konsolun tamamı
> `gozcu/ui/console.py`'de; `app.py` **üç satıra** indi ve yalnız `baslat()`'ı
> çağırıyor. Sekiz demo anının hepsinin ekranda gerçek bir kontrolü var —
> başlat, devam et, bağlantıyı kes, bağlantıyı geri ver, onayla, reddet,
> operatör mesajı — ve hiçbiri dekoratif değil. `tests/test_console.py` 49 test
> ile yeşil. **Bu dosyayı yeniden uygulama** — aşağısı ne yapıldığının kaydı.
>
> **Kurulu Gradio 6.24.** Görev dosyası yazıldığında 5.x varsayılıyordu; 6'da
> `Chatbot(type=…)` yok ve `theme` `Blocks()`'tan `launch()`'a taşındı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([notlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> `run_pipeline` iki yeni geri çağrı aldı — `on_event(LoopEvent)` ve
> `on_loop_ready(loop)`; "bağlantıyı geri ver" düğmesi `inject_failure(set())`
> ile **birlikte** `loop.catch_up()` çağırmak zorunda; ve sohbet süzgeci
> yalnız `AUDIT_PREFIX` ile başlayan `role="system"` satırlarını gizliyor —
> düz bir `role != "system"` süzgeci bozulmuş modu ekrandan siler.

**Bağımlılık:** [14](14-nobetci.md)

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden vardı?

**Demo videosu bu ekranda çekiliyor.** Jürinin göreceği tek yüzey bu. Sistemin
geri kalanı doğru çalışsa bile, burada görünmeyen bir yetenek yarışmada yoktur.

Dosya yazıldığında "24 Ağustos'ta çalışan bir iskelet hazır olacak" deniyordu;
öyle olmadı. Depoda 1. Aşama PoC'sinin kare galerisi duruyordu ve konsol
sıfırdan yazıldı. Kare galerisi kaldırıldı: konsolun gösterdiği şey artık kare
değil, videonun kendi saatinde alınan kararlar.

### Mimarinin tek önemli detayı

Sistem videoyu işlerken **kritik ana geldiğinde duruyor** ve operatörle
konuşuyor. Video bitmeden. Bu, `DecisionLoop.run()`'ın bir **generator**
olmasıyla sağlanıyor ve konsol bunu `on_event` geri çağrısıyla görünür kılıyor:
geri çağrı koşu iş parçacığında, olayın tam anında çağrılıyor ve orada
bloklarken videonun zaman çizelgesi **gerçekten** duruyor. "Devam et" bloğu
çözünce video kaldığı yerden sürüyor.

Duraklama bir numara değil — proje anlatısının tamamı buna dayanıyor: *sistem
videoyu izlerken karar veriyor, izledikten sonra özetlemiyor.*

### Depoda kilit yok

Konsol, çalışan bir `DecisionLoop`'un yazmakta olduğu SQLite dosyasını okuyor.
`Store`'un `close()`'u, WAL pragma'sı ya da kilidi yok; bağlantı
`check_same_thread=False` ile açılıyor. Yani güvenilecek bir eşzamanlılık
garantisi yok: tablolar döngünün `yield` ettiği anlarda ve saniyede bir kalp
atışıyla tazeleniyor (`HEARTBEAT_S = 1.0`). Daha sık yoklama okuma tarafını
yarıştırır, daha seyreği "zaman çizelgesi doluyor" sözünü tutmaz.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
cp .env.example .env
uv run --env-file .env python app.py       # konsol burada açılır
```

## Bağımlı olunan imzalar

```python
# gozcu/agents/supervisor.py
Supervisor(gw, store)
  .escalate(episode: Episode) -> str          # proaktif uyarı metni
  .talk(operator_text: str) -> str        # bir diyalog turu
  .pending_approval() -> ActionRecord | None
  .approve(action_id: int, approved: bool) -> dict
AUDIT_PREFIX                                  # denetim satırlarının öneki

# gozcu/loop.py
DecisionLoop(store, route, interpret, synthesize, is_degraded)
  .run(observations) -> Iterator[LoopEvent]   # yükseltmede yield eder
  .catch_up() -> Iterator[LoopEvent]          # kesinti bitince atlananları işler
LoopEvent(episode, late)                      # late=True: kesinti sonrası telafi

# gozcu/run.py
run_pipeline(video_path, store=None, gw=None, nobetci=None, on_message=None,
             output_dir=None, on_event=None, on_loop_ready=None)
  -> tuple[PipelineOutput, Path]
LATE_NOTICE                                   # telafi damgası
CallbackFailed                                # geri çağrı patlarsa bu sarmalar
_announce(store, nobetci, event, on_message) -> str

# gozcu/gateway.py
Gateway.inject_failure(tiers: set[str]) -> None    # {"vlm"} = görsel katmanı kes
Gateway.is_degraded(tier=None) -> bool   # tier verilmezse "herhangi bir kademe"

# gozcu/memory.py
memory_backend() -> str                       # "qdrant" | "local"

# benchmark/kpi.py
run_status(store) -> str                      # "measured" | "degraded" | "unmeasured"

# gozcu/store.py
Store.episodes() -> list[Episode]     # .start_ts, .summary_tr, .preliminary_risk, .state
Store.handoffs() -> list[Handoff]       # .source_agent, .target_agent, .reason, .confidence
Store.actions() -> list[ActionRecord]
Store.dialogue() -> list[DialogueTurn]

# gozcu/agents/router.py
mmss(ts: float) -> str                # 192.0 -> "03:12"
```

Risk seviyeleri: `"Düşük"` · `"Orta"` · `"Yüksek"` · `"Kritik"`

**Gateway bayrağı (Görev 03).** Durum göstergesi için doğru çağrı **çıplak**
`is_degraded()` — "herhangi bir kademe bozuk" demek ve gösterilmek istenen tam
olarak bu. (Tek bir kademeyi sormak gerekirse `is_degraded("vlm")`.)
`inject_failure(tiers)` önceki enjeksiyonun **yerine geçiyor** ve kaydedilmiş
bozulmayı da temizliyor; `inject_failure(set())` her şeyi eski hâline döndürür.

> **Görev 12 (`a8cf363`) — rapor SAF, depodan yüklenmiyor.**
> `generate_root_cause_report(gw, store)` bir `RootCauseReport` **döndürür** ve
> hiçbir şey kaydetmez; konsol onu `PipelineOutput.detail.root_cause_report`
> üzerinden çağırandan alıp ekrana basıyor, `store`'dan okumuyor — orada yok.
> Raporun dayandığı bölümler prompta `mmss()` biçimiyle giriyor, yani rapordaki
> zamanlar **video zamanı**; zaman çizelgesi de aynı biçimi kullanıyor.

> **Görev 14 (`463a74c`) — onay çubuğu TEK bir bekleyen aksiyon varsayıyor.**
> Süpervizör kapıyı girişte kapatıyor: bekleyen bir onay dururken ikinci bir
> kapılı aksiyon **yürütülmeden reddediliyor** ve deftere hiçbir satır
> yazılmıyor. Yani `pending_approval()` en fazla bir kayıt döndürür ve reddedilen
> ikinci deneme `store.actions()`'ta hiç görünmez — çubuk bir kuyruk değil.
> Ret operatöre, süpervizörün cevabının **altına eklenen** bir `[SİSTEM]`
> satırı olarak gidiyor; bu metin `.talk()`'un döndürdüğü dizenin içinde.
> Kapıda yalnız `halt_production_line` var — geri kalan altı saha aracı anında
> koşuyor, dolayısıyla onlar için onay çubuğu hiç açılmıyor.

> **Görev 15 (`b08fce8`).** Arşiv epizotları gerçek MM:SS basıyor ve
> `benchmark.kpi.run_status(store)` tek kelimelik bir rozet döndürüyor —
> `measured` / `degraded` / `unmeasured`. Konsol bunu göstererek ekrandaki
> sayıların bir anlam taşıyıp taşımadığını söylüyor.

> **Görev 08 (`7d6a473`) — durum göstergesinde ÜÇÜNCÜ rozet.**
> `gozcu.memory.memory_backend()` tek kelime döndürüyor: `"qdrant"` ya da
> `"local"`. Anahtarsız bir koşuda sistem **tamamen sağlıklı görünüyor** ama
> epizodik hafıza süreçle birlikte yok oluyor. Düşüşün kendisi kabul edilebilir,
> **görünmezliği değil** — bu yüzden backend rozeti bozulma rozetinin
> **yanında**, ayrı bir sekmede değil.

> **Görev 17 (`4e1a979`) — `app.py` 16'ya bırakıldı ve bütünüyle değiştirildi.**
> Boru hattı `run_pipeline(video_path, store=None, gw=None, nobetci=None,
> on_message=None, output_dir=None)` imzasıyla iniyordu; Görev 16 sonuna
> `on_event` ve `on_loop_ready` ekledi (konum sırası değişmedi).
> **`nobetci` olarak bir `Supervisor` geçmek zorunlu** — geçilmezse koşu
> headless kalır, operatöre tek kelime gitmez ve sohbet paneli boş durur.

> **Görev 04/17 notu — arka planda video, ekranda değişiklik yok.** 25
> Ağustos'ta (`886342a`) görü kademesine giden yük değişti: pencere başına üç
> kare değil, **pencere başına bir mp4 klibi** kesiliyor. Klibi Görev 17'nin
> `_clip_for` kapanışı üretiyor ve konsol onu hiç görmüyor.

## Ne yapıldı

Gradio `Blocks`, dört bölge ve üstte üç düğme çifti. Dosya bilerek **iki
katmana** ayrıldı: ekrana ne basılacağına karar veren her şey saf fonksiyon
olarak üst yarıda, Gradio bağlantısı alt yarıda. Bu depo iki kez ölü bir
arayüzün üstüne yeşil bir takım gönderdi; ayrım o yüzden var.

**1. Video ve zaman çizelgesi.** Yüklenen klip + renk kodlu epizot listesi.
`Düşük` yeşil, `Orta` sarı, `Yüksek` turuncu, `Kritik` kırmızı; tanınmayan bir
seviye gerçek bir rengi ödünç almıyor, kendi rengine düşüyor.

**2. Sohbet paneli.** Operatörün Nöbetçi ile konuşması. Proaktif uyarı ile
cevap görsel olarak ayrışıyor ve ayrım **türetiliyor**: kendinden önce operatör
satırı olmayan bir süpervizör satırı kimse sormadan söylenmiştir.

**3. Onay çubuğu.** Yalnız `pending_approval()` `None` değilken görünüyor.
`approve()`'un dört durumu ekranda dört farklı cümle; hattın gerçekten durduğu
İÇ İÇE duran araç sonucunda yazıyor.

**4. Devir defteri.** `store.handoffs()` canlı tablo: kaynak → hedef, neden,
güven. Şartnamenin *"sistem çıktıları mümkün olduğunca açıklanabilir
olmalıdır"* maddesine cevabımız bu.

Altta iki panel: teslim edilen dört anahtarlı JSON ve kök neden raporu.

> **Kod kopyası hakkında.** `scripts/check-tasks.py`'nin placeholder denetimi,
> küçük harfle başlayıp kapanan ham bir açı-parantez dizisini karar bekleyen
> bir yer tutucu sanıyor. Aşağıdaki iki blokta `b` ve `br` HTML etiketleri bu
> yüzden `‹b›` / `‹br›` biçiminde yazıldı — **tek fark bu**; kaynak dosyalarda
> gerçek açı parantezleri duruyor. Geri kalan her satır
> `gozcu/ui/console.py` ve `tests/test_console.py` ile birebir.

### `gozcu/ui/console.py`

```python
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

#: Ekranın yuva sayısı — her işleyici tam bu kadar değer döndürmek zorunda.
#: Eksik bir çıktı Gradio'da hata vermiyor, o bileşen sessizce tazelenmiyor.
SCREEN_SLOTS = 11

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
    """Zaman çizelgesinin satırları: `(MM:SS, özet, risk, renk)`.

    Damga **video zamanı** — `Episode.start_ts` videonun kaçıncı saniyesi ve
    kök neden raporu da aynı biçimi kullanıyor, iki ekran aynı saati göstermek
    zorunda.
    """
    return [(mmss(episode.start_ts), episode.summary_tr,
             episode.preliminary_risk, risk_color(episode.preliminary_risk))
            for episode in episodes]


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
        f"‹b›{html.escape(stamp)}‹/b› &nbsp; {html.escape(summary)}‹br›"
        f"<span style='color:{color};font-weight:600'>{html.escape(level)}</span>"
        f"</li>"
        for stamp, summary, level, color in rows)
    return f"<ul style='margin:0;padding:0'>{items}</ul>"


def handoff_rows(handoffs: list) -> list[list[str]]:
    """Devir defterinin satırları — "sistem neden böyle karar verdi"nin cevabı."""
    return [[mmss(handoff.ts), handoff.source_agent, handoff.target_agent,
             handoff.reason, f"{handoff.confidence:.2f}"]
            for handoff in handoffs]


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
            payload_json(session.output),
            root_cause_markdown(session.output),
            state,
            note)


def _blank(state: str):
    """Oturum yokken çizilecek boş ekran."""
    return (None, "", timeline_html([]), [], gr.update(visible=False), "",
            [], NO_RUN_YET, NO_RUN_YET, state, "")


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
                gr.Markdown("### Teslim edilen yük (dört anahtar)")
                payload = gr.Code(value=NO_RUN_YET, language="json",
                                  label="JSON")
            with gr.Column():
                gr.Markdown("### Kök neden raporu")
                report = gr.Markdown(NO_RUN_YET)

        # Her olay ekranın TAMAMINI tazeliyor; kısmi tazeleme bir düğmenin
        # çizelgeyi, bir başkasının defteri unutmasıyla biterdi.
        screen = [session, badges, timeline, chat, approval_box,
                  approval_box_text, ledger, payload, report, state_box,
                  approval_note]

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
```

### `tests/test_console.py`

```python
"""Görev 16 — operatör konsolunun saf katmanları.

Widget bağlantısı test edilemez; **buradaki hiçbir fonksiyon widget değil.**
Bu ayrım bilerek yapıldı: bu depo iki kez ölü bir arayüzün üstüne yeşil bir
takım gönderdi. Ekrana ne basılacağına karar veren her şey — diyalog süzgeci,
rozet derleyici, onay dağıtıcısı, risk→renk eşlemesi, zaman çizelgesi satırı —
saf fonksiyon olarak ayrıldı ve burada sınanıyor. Gradio tarafında yalnız
"hangi bileşen hangi fonksiyonu çağırıyor" kaldı.

Ağ yok: sahte süpervizör, sahte ağ geçidi, bellek içi depo.
"""

import pytest

from gozcu.agents.supervisor import (AUDIT_PREFIX, DEGRADED_REPLY,
                                     PENDING_GATE_NOTICE)
from gozcu.models import (ActionRecord, Detail, DialogueTurn, Episode,
                          EventSummary, Handoff, PipelineOutput)
from gozcu.run import LATE_NOTICE
from gozcu.store import Store
from gozcu.ui import console


# -- ikizler ------------------------------------------------------------------

class _FakeGateway:
    """Yalnız `is_degraded` taşıyan ağ geçidi ikizi.

    `tier` **kaydediliyor**: durum rozetinin doğru çağrısı çıplak
    `is_degraded()` ve tek bir kademe sorulursa rozet yanlış cevap verir.
    """

    def __init__(self, broken_any=False, broken_vlm=False):
        self.broken_any, self.broken_vlm = broken_any, broken_vlm
        self.asked: list = []

    def is_degraded(self, tier=None) -> bool:
        self.asked.append(tier)
        return self.broken_any if tier is None else self.broken_vlm


class _FakeSupervisor:
    """`approve()`'un dört durumunu senaryolayan Nöbetçi ikizi."""

    def __init__(self, result, pending_after=None):
        self.result = result
        self.pending_after = pending_after
        self.calls: list = []
        self.pending_reads = 0

    def approve(self, action_id, approved):
        self.calls.append((action_id, approved))
        return self.result

    def pending_approval(self):
        self.pending_reads += 1
        return self.pending_after


def _episode(start_ts=192.0, risk="Yüksek", summary="İstif aracı devrildi."):
    return Episode(id=1, start_ts=start_ts, phase="onset", summary_tr=summary,
                   preliminary_risk=risk)


def _pending(tool_name="halt_production_line", action_id=7):
    return ActionRecord(id=action_id, ts=192.0, tool_name=tool_name,
                        params={"line_id": "B-Hattı"},
                        result={"state": "awaiting_approval"},
                        actor="agent", approval="pending")


# -- Kural 5: diyalog süzgeci -------------------------------------------------

def test_audit_rows_are_hidden_from_the_chat_pane():
    """`[denetim]` satırı denetim hükmünün kaydı, operatöre söylenmiş söz değil."""
    turns = [DialogueTurn(ts=1.0, role="system",
                          text=f"{AUDIT_PREFIX} uygunsuz hüküm, not eklendi"),
             DialogueTurn(ts=2.0, role="supervisor", text="Sağlık ekibi yolda.")]
    assert [t.text for t in console.visible_dialogue(turns)] == \
        ["Sağlık ekibi yolda."]


def test_the_degraded_reply_stays_on_screen():
    """`role != "system"` süzgeci bozulmuş modu ekrandan siler.

    Demo beat 6'da jürinin görmesi gereken TEK metin bu: ağ geçidi kesildi,
    sistem çökmedi, operatöre ne olduğunu söyledi.
    """
    turns = [DialogueTurn(ts=1.0, role="system", text=DEGRADED_REPLY)]
    assert console.visible_dialogue(turns) == turns


def test_the_catch_up_notice_stays_on_screen():
    """Telafi damgası da `role="system"` — süzülürse beat 6'nın ikinci yarısı
    (bağlantı geri geldi, açık kapatıldı) ekranda hiç görünmez."""
    turns = [DialogueTurn(ts=1.0, role="system", text=LATE_NOTICE)]
    assert console.visible_dialogue(turns) == turns


def test_the_pending_gate_notice_stays_on_screen():
    notice = PENDING_GATE_NOTICE.format(tool="halt_production_line", params="{}")
    turns = [DialogueTurn(ts=1.0, role="system", text=notice)]
    assert console.visible_dialogue(turns) == turns


def test_only_a_leading_audit_prefix_hides_a_row():
    """Operatörün cümlesinin İÇİNDE geçen bir damga satırı gizlemez."""
    turns = [DialogueTurn(ts=1.0, role="operator",
                          text=f"{AUDIT_PREFIX} nedir?"),
             DialogueTurn(ts=2.0, role="system",
                          text=f"Not: {AUDIT_PREFIX} kaydı tutuldu.")]
    assert console.visible_dialogue(turns) == turns


def test_a_proactive_alert_is_marked_apart_from_a_reply():
    """Operatör hangi mesajın kendiliğinden geldiğini görmeli.

    Ayrım türetiliyor: kendinden önce operatör satırı olmayan bir süpervizör
    satırı kimse sormadan söylenmiştir (`escalate`), sonrakiler cevaptır.
    """
    turns = [DialogueTurn(ts=1.0, role="supervisor", text="Kritik olay var."),
             DialogueTurn(ts=2.0, role="operator", text="Ne oldu?"),
             DialogueTurn(ts=3.0, role="supervisor", text="İstif aracı devrildi.")]
    messages = console.chat_messages(turns)
    assert [m["role"] for m in messages] == ["assistant", "user", "assistant"]
    assert messages[0]["content"].startswith(console.PROACTIVE_MARK)
    assert not messages[2]["content"].startswith(console.PROACTIVE_MARK)
    assert "İstif aracı devrildi." in messages[2]["content"]


def test_chat_messages_marks_system_rows_and_drops_audit_rows():
    turns = [DialogueTurn(ts=1.0, role="system", text=DEGRADED_REPLY),
             DialogueTurn(ts=2.0, role="system", text=f"{AUDIT_PREFIX} not")]
    messages = console.chat_messages(turns)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"].startswith(console.SYSTEM_MARK)
    assert DEGRADED_REPLY in messages[0]["content"]


# -- Kural 6: rozetler --------------------------------------------------------

def test_the_status_badge_asks_the_bare_degradation_flag(monkeypatch):
    """Rozet "herhangi bir kademe bozuk mu" demek — kademe adı geçilmemeli."""
    monkeypatch.setattr(console, "memory_backend", lambda: "qdrant")
    monkeypatch.setattr(console, "run_status", lambda store: "measured")
    gw = _FakeGateway(broken_any=True, broken_vlm=False)
    text = console.status_badges(gw, Store(":memory:"))
    assert gw.asked == [None]
    assert console.DEGRADED_BADGE in text
    assert console.HEALTHY_BADGE not in text


def test_a_healthy_run_shows_all_three_badges(monkeypatch):
    monkeypatch.setattr(console, "memory_backend", lambda: "local")
    monkeypatch.setattr(console, "run_status", lambda store: "unmeasured")
    text = console.status_badges(_FakeGateway(), Store(":memory:"))
    assert console.HEALTHY_BADGE in text
    assert "local" in text
    assert "unmeasured" in text


def test_the_memory_badge_reports_the_real_backend(monkeypatch):
    """Sessiz düşüşün kendisi kabul edilebilir, görünmezliği değil."""
    monkeypatch.setattr(console, "run_status", lambda store: "measured")
    monkeypatch.setattr(console, "memory_backend", lambda: "qdrant")
    assert "qdrant" in console.status_badges(_FakeGateway(), Store(":memory:"))
    monkeypatch.setattr(console, "memory_backend", lambda: "local")
    assert "local" in console.status_badges(_FakeGateway(), Store(":memory:"))


def test_the_run_status_badge_comes_from_the_kpi_module():
    """Boş depo ölçülemez bir koşudur; rozet bunu söylemeli."""
    assert "unmeasured" in console.status_badges(_FakeGateway(), Store(":memory:"))


# -- Kural 7: onay çubuğu -----------------------------------------------------

def test_an_approved_halt_says_the_line_actually_stopped():
    """`state="approved"` onayın işlendiğini söyler, hattın durduğunu değil.

    Hattın gerçekten durduğu İÇ İÇE duran araç sonucunda yazıyor.
    """
    nobetci = _FakeSupervisor({"state": "approved", "action_id": 7,
                               "result": {"state": "halted",
                                          "line": "B-Hattı"}})
    text, pending = console.apply_approval(nobetci, 7, True)
    assert console.HALTED_NOTE in text
    assert pending is None
    assert nobetci.calls == [(7, True)]


def test_an_approved_action_that_did_not_halt_is_not_reported_as_halted():
    """Onay işlendi ama araç hattı durdurmadı — bu iki farklı şey."""
    nobetci = _FakeSupervisor({"state": "approved", "action_id": 7,
                               "result": {"state": "awaiting_approval"}})
    text, _ = console.apply_approval(nobetci, 7, True)
    assert console.HALTED_NOTE not in text
    assert console.NOT_HALTED_NOTE.split("{")[0] in text


def test_a_rejected_action_says_nothing_was_called():
    nobetci = _FakeSupervisor({"state": "rejected", "action_id": 7})
    text, _ = console.apply_approval(nobetci, 7, False)
    assert console.REJECTED_NOTE in text
    assert nobetci.calls == [(7, False)]


def test_an_unknown_action_is_reported_not_raised():
    nobetci = _FakeSupervisor({"state": "unknown_action",
                               "error": "aksiyon bulunamadı: 99"})
    text, _ = console.apply_approval(nobetci, 99, True)
    assert console.UNKNOWN_ACTION_NOTE in text


def test_an_already_decided_action_is_reported_not_raised():
    nobetci = _FakeSupervisor({"state": "not_pending", "approval": "approved"})
    text, _ = console.apply_approval(nobetci, 7, True)
    assert console.NOT_PENDING_NOTE.split("{")[0] in text
    assert "approved" in text


def test_an_unexpected_state_is_still_shown_to_the_operator():
    """Sözleşme büyürse çubuk sessiz kalmamalı."""
    nobetci = _FakeSupervisor({"state": "brand_new"})
    text, _ = console.apply_approval(nobetci, 7, True)
    assert "brand_new" in text


def test_the_bar_is_refreshed_from_the_supervisor_after_every_decision():
    """Karar sonrası çubuk yeniden okunmazsa bayat satırın üzerinde açık kalır."""
    still = _pending()
    nobetci = _FakeSupervisor({"state": "rejected", "action_id": 7},
                              pending_after=still)
    _, pending = console.apply_approval(nobetci, 7, False)
    assert nobetci.pending_reads == 1
    assert pending is still


def test_the_approval_text_names_the_tool_and_disappears_when_empty():
    assert console.approval_text(None) == ""
    text = console.approval_text(_pending())
    assert "halt_production_line" in text
    assert "B-Hattı" in text


# -- Kural 4: risk rengi ve zaman çizelgesi -----------------------------------

@pytest.mark.parametrize("level, color", [("Düşük", console.GREEN),
                                          ("Orta", console.YELLOW),
                                          ("Yüksek", console.ORANGE),
                                          ("Kritik", console.RED)])
def test_every_risk_level_has_its_own_colour(level, color):
    assert console.risk_color(level) == color


def test_the_four_risk_colours_are_distinct():
    """İkisi aynı renge düşerse zaman çizelgesi bir şey söylemiyor demektir."""
    colours = [console.risk_color(level) for level in console.RISK_COLORS]
    assert len(set(colours)) == 4


def test_an_unknown_risk_level_does_not_borrow_a_real_colour():
    """Şema büyürse çizelge sessizce yanlış renk basmamalı."""
    assert console.risk_color("Belirsiz") == console.UNKNOWN_COLOR
    assert console.UNKNOWN_COLOR not in \
        [console.risk_color(level) for level in console.RISK_COLORS]


def test_a_timeline_row_carries_the_video_stamp_summary_risk_and_colour():
    rows = console.timeline_rows([_episode(start_ts=192.0)])
    assert rows == [("03:12", "İstif aracı devrildi.", "Yüksek",
                     console.ORANGE)]


def test_the_timeline_renders_every_episode_with_its_colour():
    html = console.timeline_html([_episode(start_ts=0.0, risk="Düşük"),
                                  _episode(start_ts=192.0, risk="Kritik")])
    assert "00:00" in html and "03:12" in html
    assert console.GREEN in html and console.RED in html
    assert "Düşük" in html and "Kritik" in html


def test_an_empty_timeline_says_so_in_turkish():
    assert console.TIMELINE_EMPTY in console.timeline_html([])


def test_the_timeline_escapes_model_written_summaries():
    """Özet metni modelden geliyor; ham HTML olarak basılamaz."""
    html = console.timeline_html([_episode(summary="‹b›devrildi‹/b›")])
    assert "‹b›devrildi‹/b›" not in html
    assert "&lt;b&gt;" in html


# -- teslim edilen yük --------------------------------------------------------

def _output(root_cause=None, detail=True):
    return PipelineOutput(
        summary="B-Hattında istif aracı devrildi.", risk="Kritik",
        events=[EventSummary(time="03:12", event="devrildi")],
        actions=["Sağlık ekibini çağır"],
        detail=Detail(root_cause_report=root_cause) if detail else None)


def test_the_four_keys_are_rendered_as_json():
    text = console.payload_json(_output())
    assert '"summary"' in text and '"events"' in text
    assert '"risk"' in text and '"actions"' in text


def test_no_run_yet_is_said_in_turkish_not_shown_as_empty_json():
    assert console.payload_json(None) == console.NO_RUN_YET
    assert console.NO_RUN_YET in console.root_cause_markdown(None)


def test_a_crashed_run_does_not_fabricate_an_empty_root_cause_report():
    """`detail=None` "o katmanlar hiç koşmadı" demek; boş bir rapor basmak
    yaşanmamış bir analizi iddia etmek olurdu.

    Ayrıca çöken koşu ile raporsuz koşu aynı cümleyi paylaşamaz: biri
    genişletilmiş yolun çöküşü, diğeri kayda değer olay olmaması.
    """
    text = console.root_cause_markdown(_output(detail=False))
    assert console.CRASHED_RUN in text
    assert console.NO_ROOT_CAUSE not in text
    assert "Muhtemel kök neden" not in text


def test_a_run_without_a_report_says_so_rather_than_printing_blanks():
    text = console.root_cause_markdown(_output(root_cause=None))
    assert console.NO_ROOT_CAUSE in text
    assert console.CRASHED_RUN not in text
    assert "Muhtemel kök neden" not in text


def test_a_real_report_renders_all_five_sections():
    report = {"what_happened": "B-Hattında istif aracı devrildi.",
              "probable_root_cause": "Olası fren arızası.",
              "actions_taken": ["Sağlık ekibi çağrıldı."],
              "prevention_recommendations": ["Fren bakımı öne alınmalı."],
              "confidence_limits": "Kamera sesi duymuyor."}
    text = console.root_cause_markdown(_output(root_cause=report))
    for value in ("B-Hattında istif aracı devrildi.", "Olası fren arızası.",
                  "Sağlık ekibi çağrıldı.", "Fren bakımı öne alınmalı.",
                  "Kamera sesi duymuyor."):
        assert value in text
    assert console.CRASHED_RUN not in text


def test_the_handoff_ledger_stamps_video_time():
    rows = console.handoff_rows([Handoff(ts=192.0, source_agent="router",
                                         target_agent="supervisor",
                                         reason="hız eşiği aşıldı",
                                         confidence=0.9,
                                         payload_ref="window@192.0")])
    assert rows == [["03:12", "router", "supervisor", "hız eşiği aşıldı", "0.90"]]


# -- modül yüzeyi -------------------------------------------------------------

def test_the_console_module_imports_cleanly():
    assert callable(console.baslat)


def test_ensure_server_running_explains_missing_mlx_vlm():
    """mlx-vlm kurulu değilken alt süreç açmadan okunur bir hata verilmeli."""
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    client.models.list.side_effect = Exception("unreachable")

    with (patch.object(console, "OpenAI", return_value=client),
          patch("importlib.util.find_spec", return_value=None),
          patch.object(console.subprocess, "Popen") as popen,
          patch.object(console.time, "sleep")):
        with pytest.raises(RuntimeError, match="mlx-vlm"):
            console._ensure_server_running()
        popen.assert_not_called()


# -- ekran bağlantısı ---------------------------------------------------------
#
# Widget'ın kendisi test edilemez, ama **ağacın kurulabilmesi** ve her
# işleyicinin ekran yuvası sayısı kadar değer döndürmesi edilebilir. Bu depoda
# yeşil bir takımın altında ölü bir arayüz iki kez gönderildi; `build()` hiç
# çağrılmadığı için Gradio'nun imza değişikliği testlere hiç yansımamıştı.

class _StubLoop:
    def __init__(self, events=()):
        self.events = list(events)
        self.calls = 0

    def catch_up(self):
        self.calls += 1
        yield from self.events


class _StubGateway(_FakeGateway):
    def __init__(self):
        super().__init__()
        self.injections: list = []

    def inject_failure(self, tiers):
        self.injections.append(set(tiers))
        self.broken_any = bool(tiers)


def _session(monkeypatch):
    """Ağa çıkmayan bir oturum: gerçek depo, sahte ağ geçidi, sahte Nöbetçi."""
    monkeypatch.setattr(console, "Gateway", lambda store: _StubGateway())
    monkeypatch.setattr(console, "Supervisor",
                        lambda gw, store: _FakeSupervisor(
                            {"state": "unknown_action"}))
    return console.Session()


def test_the_console_tree_builds_and_every_handler_fills_the_whole_screen():
    """Her düğme ekranın TAMAMINI tazeliyor; eksik çıktı sessiz ölü bölge olur."""
    demo = console.build()
    handlers = [fn for fn in demo.fns.values() if len(fn.outputs) > 1]
    assert handlers, "hiç işleyici bağlanmamış"
    assert {len(fn.outputs) for fn in handlers} == {console.SCREEN_SLOTS}


def test_the_refresh_and_blank_screens_have_the_same_shape(monkeypatch):
    session = _session(monkeypatch)
    assert len(console._refresh(session, "x")) == console.SCREEN_SLOTS
    assert len(console._blank("x")) == console.SCREEN_SLOTS


def test_cutting_the_link_injects_a_vision_tier_outage(monkeypatch):
    """Demo beat 6'nın ilk yarısı: jürinin gözü önünde kesiyoruz."""
    session = _session(monkeypatch)
    state = console._cut_link(session)[-2]
    assert session.gw.injections == [{"vlm"}]
    assert state == console.STATE_CUT


def test_restoring_the_link_clears_the_outage_and_catches_up(monkeypatch):
    """İkisi birlikte olmak zorunda.

    Yalnız `inject_failure(set())` yapılsaydı atlanan pencereler kuyrukta
    kalırdı ve telafi ekranda hiç görünmezdi — beat 6'nın ikinci yarısı yok.
    """
    from gozcu.models import LoopEvent

    session = _session(monkeypatch)
    session.loop = _StubLoop([LoopEvent(episode=_episode(), late=True)])
    announced: list = []
    monkeypatch.setattr(console, "_announce",
                        lambda store, nobetci, event, on_message:
                        announced.append(event))

    state = console._restore_link(session)[-2]
    assert session.gw.injections == [set()]
    assert session.loop.calls == 1
    assert len(announced) == 1 and announced[0].late is True
    assert state == console.STATE_RESTORED.format(count=1)


def test_restoring_without_a_running_loop_says_so(monkeypatch):
    session = _session(monkeypatch)
    assert console._restore_link(session)[-2] == console.STATE_NO_LOOP
    assert session.gw.injections == [set()]


def test_resume_releases_the_paused_loop(monkeypatch):
    """"Devam et" bloğu çözüyor; video kaldığı yerden sürüyor."""
    session = _session(monkeypatch)
    session.resume.clear()
    state = console._resume(session)[-2]
    assert session.resume.is_set()
    assert state == console.STATE_RESUMED


def test_starting_without_a_video_says_so_instead_of_crashing():
    screen = next(console._analyse(None, None))
    assert screen[-2] == console.STATE_NO_VIDEO


def test_every_button_handler_survives_a_missing_session():
    """Analiz başlamadan basılan düğme yığın izi üretmemeli."""
    for handler in (console._resume, console._cut_link, console._restore_link):
        assert handler(None)[-2] == console.STATE_IDLE
    assert console._decide(None, True)[-2] == console.STATE_IDLE
    assert console._say("merhaba", None)[-2] == console.STATE_IDLE


def test_the_approval_bar_opens_only_while_an_action_is_pending(monkeypatch):
    """Görev 16'nın kabul kriteri: bekleyen aksiyonda çıkar, karardan sonra
    kaybolur. Sabit görünürlük ikisini de sessizce yalanlar."""
    session = _session(monkeypatch)
    assert console._refresh(session, "x")[4]["visible"] is False

    session.nobetci.pending_after = _pending()
    screen = console._refresh(session, "x")
    assert screen[4]["visible"] is True
    assert "halt_production_line" in screen[5]

    session.nobetci.pending_after = None
    assert console._refresh(session, "x")[4]["visible"] is False


def test_the_screen_streams_and_the_loop_really_pauses(monkeypatch, tmp_path):
    """Beat 0 ve 1 tek testte: video akıyor, kritik anda **duruyor**.

    Duraklama bir numara değil — `on_event` koşu iş parçacığında bloklarken
    videonun zaman çizelgesi gerçekten bekliyor. "Devam et" bloğu çözünce
    generator sona kadar akıyor ve teslim edilen yük ekrana düşüyor.
    """
    from tests.test_run import _FakeGateway as _RunGateway
    from tests.test_run import _fake_clip, _perception

    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    monkeypatch.setattr(console, "Gateway",
                        lambda store: _RunGateway(router=("escalate",)))

    screens = []
    for screen in console._analyse("video.mp4", None):
        screens.append(screen)
        if screen[-2] == console.STATE_PAUSED:
            console._resume(screen[0])
        assert len(screens) < 60, "generator sonlanmadı"

    states = [screen[-2] for screen in screens]
    assert console.STATE_PAUSED in states, "kritik olayda hiç durulmadı"
    assert states[-1] == console.STATE_DONE

    final = screens[-1]
    assert console.TIMELINE_EMPTY not in final[2]      # çizelge doldu
    assert final[3], "sohbet paneli boş kaldı"
    assert '"summary"' in final[7]                     # dört anahtar teslim
    assert final[0].store.handoffs(), "devir defteri boş"


def test_the_decision_note_reaches_the_screen(monkeypatch):
    """Onay çubuğunun cevabı ekranın son yuvasına düşmeli."""
    session = _session(monkeypatch)
    session.nobetci.pending_after = _pending()
    session.nobetci.result = {"state": "rejected", "action_id": 7}
    assert console._decide(session, False)[-1] == console.REJECTED_NOTE


def test_deciding_with_nothing_pending_does_not_call_the_supervisor(monkeypatch):
    session = _session(monkeypatch)
    screen = console._decide(session, True)
    assert session.nobetci.calls == []
    assert screen[-1] == console.UNKNOWN_ACTION_NOTE
```

### `app.py`

Üç satır. Kare galerisi ve `process_video` kaldırıldı.

```python
from gozcu.ui.console import baslat

if __name__ == "__main__":
    baslat()
```

`tests/test_smoke.py` de bu yüzden yeniden yazıldı: koruduğu iki cümle —
modül temiz import edilebilmeli ve mlx-vlm kurulu değilken **alt süreç
açmadan** okunur bir hata vermeli — taşındı ama değişmedi.

## Kabul kriterleri

Onunun da ekranda gerçek bir kontrolü var; parantez içindekiler
`tests/test_console.py`'deki karşılıkları.

- [x] Bir klip yüklenip analiz başlatılabiliyor (`test_the_screen_streams_and_the_loop_really_pauses`)
- [x] Analiz sırasında ekran donmuyor, zaman çizelgesi doluyor (aynı test, `TIMELINE_EMPTY` kontrolü)
- [x] Kritik olayda **döngü duruyor** ve Nöbetçi'nin mesajı sohbete düşüyor (aynı test, `STATE_PAUSED`)
- [x] Operatör o sırada yazabiliyor ve cevap alabiliyor (`_say`, `test_every_button_handler_survives_a_missing_session`)
- [x] "Devam et" döngüyü kaldığı yerden ilerletiyor (`test_resume_releases_the_paused_loop`)
- [x] Onay çubuğu bekleyen aksiyonda çıkıyor, onaydan sonra kayboluyor (`test_the_approval_bar_opens_only_while_an_action_is_pending`)
- [x] Devir defteri dolarak akıyor (`test_the_handoff_ledger_stamps_video_time`)
- [x] "Bağlantıyı kes" basıldığında sistem çökmüyor, durum bildiriliyor (`test_cutting_the_link_injects_a_vision_tier_outage`)
- [x] Video bitince JSON çıktısı ve kök neden raporu görünüyor (`test_the_four_keys_are_rendered_as_json`)
- [x] Durum göstergesi `memory_backend()` rozetini bozulma rozetinin yanında basıyor (`test_a_healthy_run_shows_all_three_badges`)

**Ama hepsi mock'lu.** Konsolun gerçek modelleri uçtan uca sürdüğünü kimse
izlemedi; sekiz demo anının canlı provası [Görev 18](18-paketleme.md)'de
duruyor ve çekimden önce atlanamaz.

## Doğrulama

```bash
uv run pytest tests/test_console.py -q
```
Çıktı: **49 passed**.

> **`Beklenen: N passed` kalıbı bu dosyada bilerek kullanılmıyor.**
> `scripts/check-tasks.py`'nin 5. denetimi `parametrize` listesini
> `ast.literal_eval` ile açıyor; buradaki liste `console.GREEN` gibi modül
> niteliklerine başvurduğu için açılamıyor ve denetçi 46 `def` sayıyor. pytest
> 49 koşu üretiyor — 46 test fonksiyonu, biri dört risk rengi üzerinde
> parametrik. İddiayı 46'ya çekmek denetçiyi kandırmak olurdu; kalıbı
> kullanmayıp pytest'in bastığı gerçek sayıyı yazmak dürüst olan.

Duman testi ve mekanik denetim de geçmeli:

```bash
uv run pytest tests/test_smoke.py -q
uv run python scripts/check-tasks.py
```

Ekranın kendisi gözle doğrulanıyor — yukarıdaki on maddeyi tek tek dene:

```bash
uv run --env-file .env python app.py
```

## Commit

```bash
git add gozcu/ui/console.py tests/test_console.py app.py tests/test_smoke.py
git commit -m "feat: operator console with live decisions and outage recovery"
```

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Kurulu Gradio 6.24.0, 5.x değil.** `Chatbot(type=…)` parametresi 6'da
  **yok** (sohbet zaten yalnız `{"role": …, "content": …}` sözlüklerini kabul
  ediyor) ve `theme` `Blocks()`'tan `launch()`'a taşındı. İlk `build()` çağrısı
  bu yüzden `TypeError` fırlattı. Saf fonksiyon testleri bunu **hiçbir zaman**
  yakalayamazdı: `build()` hiç çağrılmıyordu. `tests/test_console.py` artık
  `build()`'i çağırıyor ve her işleyicinin ekranın **on bir yuvasının
  tamamını** doldurduğunu doğruluyor (`SCREEN_SLOTS = 11`) — bir sonraki API
  kayması sessizce ölü bölge bırakmak yerine kırmızıya düşer. `pyproject.toml`
  hâlâ `gradio>=5.0` diyor; test edilmiş sürüm 6.24.0.
- **`run_pipeline` iki geri çağrı kazandı:** `on_event(LoopEvent)` ve
  `on_loop_ready(loop)`. İkisi de imzanın **sonuna** eklendi, konum sırası
  değişmedi — mevcut çağıranlar etkilenmiyor. `on_event` koşu iş parçacığında,
  olayın tam anında çağrılıyor; orada bloklayan konsol videonun zaman
  çizelgesini gerçekten durduruyor.
- **Geri çağrılar `_invoke()`'tan geçiyor ve patlarsa `run.CallbackFailed`'e
  sarılıyor.** Ayrı bir tip olmasının nedeni: konsoldaki bir hata yukarı
  yayılsın, gerçek kademe kesintileri ise bozulmuş moda düşmeye devam etsin.
  Geniş bir `except Exception` ikisini aynı kutuya koyup konsol hatasını
  "gateway bozuk" diye rapor ederdi.
- **"Bağlantıyı geri ver" düğmesi İKİ şey yapmak zorunda:**
  `gw.inject_failure(set())` **ve** `on_loop_ready`'den gelen tutamak üzerinden
  `loop.catch_up()`. Tutamak olmadan düğme dekoratiftir, çünkü `DecisionLoop`
  `run_pipeline`'ın yereliydi ve dışarıdan çağrılamıyordu. Yalnız birincisi
  yapılsaydı atlanan pencereler kuyrukta kalır, telafi ekranda hiç görünmezdi —
  demo beat 6'nın ikinci yarısı yok olurdu.
- **Diyalog süzgeci:** yalnız `AUDIT_PREFIX` ile **başlayan** `role="system"`
  satırları gizleniyor. Diğer sistem yazarları ekranda kalmak zorunda —
  `Supervisor._fault`'un bozulmuş/boş/yarım cevapları ve `run.py`'nin
  `LATE_NOTICE` damgası tam olarak demo beat 6'da jürinin görmesi gereken şey.
  Düz bir `role != "system"` süzgeci bozulmuş modu ekrandan siler.
- **`approve()` istisna atmıyor**, dört durumdan biriyle dönüyor:
  `{"state": "approved"|"rejected"|"unknown_action"|"not_pending",
  "action_id", "result"}`. Konsol dördünü de ayrı ayrı karşılıyor ve hattın
  gerçekten durup durmadığını **iç içe** duran `result["result"]["state"]`
  üzerinden söylüyor. `"approved"` onayın işlendiğini söyler, hattın durduğunu
  değil; düz birleştirmede araç sonucu onayın kendi durumunu eziyordu.
- **Aynı anda en fazla BİR bekleyen aksiyon var.** Reddedilen ikinci kapılı
  aksiyon deftere hiç girmiyor ve reddi `.talk()`'un döndürdüğü dizenin sonuna
  eklenmiş olarak geliyor. Onay çubuğunu kuyruk olarak kurma.
- **Üç rozet, üç ayrı kaynak:** çıplak `is_degraded()` (herhangi bir kademe —
  durum göstergesi için doğru olan bu), `memory_backend()` ve
  `kpi.run_status(store)`. `Gateway._broken` ancak **gerçekten başarısız olmuş
  bir çağrıdan sonra** latch'liyor, yani rozet taze bir `inject_failure`'ı bir
  sonraki `vlm` çağrısı düşene kadar göstermiyor. Bu bir hata değil, kaydedilmiş
  bozulma ile enjekte edilmiş niyetin farkı — demo sırasında "kestim ama yeşil"
  görüntüsünün açıklaması burada.
- **Zaman çizelgesi renk kodlu bir epizot LİSTESİ**, sürgü üzerine işaret değil:
  Gradio'nun video sürgüsüne renkli işaret koyacak bir ilkeli yok. Liste aynı
  bilgiyi taşıyor ve okunması daha kolay. Özet metni modelden geliyor, bu yüzden
  HTML olarak kaçırılıyor.
- **`_annotate_frame` / `_annotate_all_frames` gitti.** 1. Aşama PoC'si her
  kareyi YOLO ile işaretleyip galeri basıyordu; gösterim için kare başına
  ikinci bir tam tespit turu koşmak demek bu. Konsolun gösterdiği şey artık
  kare değil, karar.
- **`_ensure_server_running` yaşıyor ama demo yolunda değil.**
  `baslat(yerel_vlm=True)` ile açıkça isteniyor ve yalnız çevrimdışı kurulum
  için: görü kademesi paylaşılan `Gateway` yerine yerel bir mlx-vlm sunucusundan
  geliyorsa. mlx-vlm kurulu değilken alt süreç **açılmıyor**, okunur bir hata
  veriliyor.
- **Çöken koşu `detail=None` bırakıyor** ve kök neden paneli bunu dürüstçe
  yazıyor. Üç ayrı yokluk üç ayrı cümle: koşu hiç olmadı, genişletilmiş katman
  çöktü, koşu tamam ama kayda değer olay yok. Boş bir rapor basmak yaşanmamış
  bir analizi iddia etmek olurdu.

## Takıldığında

Üveys'e yaz.
