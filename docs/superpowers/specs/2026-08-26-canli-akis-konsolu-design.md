# Canlı akış konsolu — beş sekme yerine iki

**Tarih:** 26 Ağustos 2026 · **Durum:** tasarım · **Görev:** 19

Konsol beş sekmeydi (`Canlı izleme` · `Müdahaleler` · `Nöbetçi` · `Çıktı` ·
`Ölçüm`). İki olacak: **CANLI** ve **RAPOR**.

## Neden

Beş sekme sistemin yaptığı işi **kaynağına göre** bölüyordu: devirler bir
sekmede, araç çağrıları başka bir sekmede, süpervizörün konuşması üçüncüde,
epizotlar dördüncüde. Hepsi aynı on saniyede olup bitmiş şeylerdi ve hiçbir
ekran onları **birlikte** göstermiyordu. Jüri, ajanların birbirine ne
devrettiğini görmek için sekme değiştirmek ve iki tabloyu zaman damgasından
elle eşleştirmek zorundaydı.

Bu spec akışı **oluş sırasına** çeviriyor: tek bir kolonda, videonun kendi
saatiyle damgalanmış, her satırda **hangi ajanın ürettiği** yazan bir besleme.

## Kapsam dışı

- Algı katmanının kalitesi (`frames.py`, `detect.py`, `track.py`,
  `signals.py`) — bu görev hiçbirine dokunmuyor.
- `trace.py` — stderr tanı kaydı olarak KALIYOR ve ekrana taşınmıyor.
  Beslemenin istediği şey ayrıntılı kayıt değil, olay çizelgesi.
- Ajan promptları, model kimlikleri, çıktı sözleşmesi.

# 1. Sorun: depoda oluş sırası yok

Besleme üç şeyi gerektiriyor ve bugün üçü de eksik.

**a) Küresel sıra yok.** Bir pencerenin bütün üretimi (yönlendirici kararı,
yorum, epizot, risk, konuşma, araç çağrısı) `window[0].ts` civarına düşüyor;
satır kimlikleri **tablo başına** artıyor. `ts`'e göre sıralamak beraberlik
üretiyor ve beraberliği çözecek hiçbir alan yok. Sabit bir "boru hattı
sırası" uydurmak ise ekrana yaşanmamış bir sıra bastırır: koşu sırasında
yazılan bir operatör mesajı ya da `catch_up()` telafisi yanlış yere düşer.

**b) Algı katmanının pencere özeti hiçbir tabloda yok.** `loop.py:520`
pencere başına `kişi≤2 kutu=14 [forklift,person] taban=EVET görü=bütçede`
hesaplıyor ve **yalnız stderr'e** yazıyor. `passes_floor` sonucu, görü
bütçesi seçimi ve erteleme de öyle.

**c) Ham gözlem beslemeye giremez.** `FRAME_FPS = 3.0`, yani 10 saniyelik bir
pencere ~30 `Observation` satırı. Bunları basmak ayrıntılı kayıt olur.

# 2. Çözüm

## 2.1 Küresel sıra defteri (`journal`)

`Store`'a **append-only** bir defter ekleniyor. Tipli tablolar tek gerçek
kaynak olarak KALIYOR; defter yalnız "hangi satır ne zaman yazıldı"yı
söylüyor.

```sql
CREATE TABLE IF NOT EXISTS journal (
  seq      INTEGER PRIMARY KEY AUTOINCREMENT,
  source   TEXT,      -- tablo adı
  row_id   INTEGER,
  kind     TEXT,      -- 'create' | 'update' | 'approval'
  snapshot TEXT       -- JSON; yalnız değişen türlerde, yoksa NULL
);
```

`AUTOINCREMENT` süreç boyunca artan tek bir sayaç veriyor — beraberlik yok,
tablolar arası sıra kesin.

Yazma noktaları:

| Yer | Defter satırı |
|---|---|
| `Store._insert` | `(source=<tablo>, row_id, kind='create', snapshot=NULL)` |
| `Store.update_episode` | `(source='episode', row_id, kind='update', snapshot=…)` |
| `Store.set_action_approval` | `(source='action', row_id, kind='approval', snapshot=…)` |

**Gözlem defterlenmiyor.** `save_observation` `journal=False` ile çağırıyor.
Gerekçe iki katlı: 3 fps'te üç dakikalık bir video 540 gereksiz defter satırı
yazar, ve gözlem bir **ajan sınırını geçmiyor** — algının ham maddesi.
Beslemedeki algı satırının kaynağı `window_record` (§2.2).

### Neden anlık görüntü (`snapshot`)

Bir defter satırı okunduğunda tipli satır çözülüyor — ama **epizot
değişebiliyor**. Sentezleyici bir epizoda üç pencere boyunca kaynaşıyor ve
`summary_tr` her seferinde değişiyor. Defter satırını canlı satıra çözmek,
koşunun başındaki bir girdiye epizodun **sonunda** aldığı özeti bastırırdı —
ekran, o anda söylenmemiş bir şeyi söylemiş gibi görünürdü.

Bu yüzden **değişen türler kendi anlık görüntüsünü taşıyor**, yalnız
beslemenin bastığı alanları:

- `episode` / `update` → `{summary_tr, preliminary_risk, phase, state}`
- `action` / `approval` → `{approval}`

Değişmeyen kayıtlar (`handoff`, `interpretation`, `risk`, `dialogue`,
`correction`, `window_record`) canlı çözülüyor; onlar yazıldıktan sonra
değişmiyor, dolayısıyla kayamazlar.

`episode`'un **`create`** satırı da aynı sorunu taşıyor: epizot sonradan
güncelleniyor. Onun da anlık görüntüsü yazılıyor — `_insert` `snapshot`
parametresi kabul ediyor ve `create_episode` onu dolduruyor. Diğer bütün
`create` satırlarında `snapshot` NULL.

### Yeni okuma

```python
class JournalEntry(Base):
    seq: int
    source: str
    row_id: int
    kind: Literal["create", "update", "approval"]
    snapshot: dict | None = None

def journal(self) -> list[JournalEntry]:  # seq'e göre sıralı
```

## 2.2 Pencere kaydı (`WindowRecord`)

Algı ve triyaj özeti tipli hâle geliyor ve depoya yazılıyor.

```python
class WindowRecord(Base):
    """Bir pencerenin algı + triyaj özeti.

    Bugün aynı sayılar `loop.run()` içinde hesaplanıp yalnız `trace`e
    gidiyor. Besleme "sistem bu on saniyede ne gördü" sorusunu bu kayıttan
    cevaplıyor — 30 ham gözlemden değil.
    """
    id: int | None = None
    ts: float                  # window[0].ts
    end_ts: float              # window[-1].ts
    index: int                 # 1'den başlar
    total: int                 # koşunun pencere sayısı
    frames: int                # len(window)
    person_peak: int
    detections: int
    labels: list[str] = Field(default_factory=list)
    floor_passed: bool
    vision_budgeted: bool
    outcome: Literal["routed", "forced", "skipped"]
```

Tablo adı **`window_record`** — `window` SQLite 3.25+'ta anahtar kelime
(pencere fonksiyonları) ve tablo adı olarak kullanmak tırnak zorunluluğu
doğurur.

`DecisionLoop.run()` her pencere için bir kayıt yazıyor. `loop.py:518-527`
içindeki toplama (`peak`, `boxes`, `labels`) **tek bir yardımcıya** çekiliyor
ve hem `trace` satırı hem depo kaydı onu kullanıyor: iki gösterim ayrışırsa
ekran ile kayıt farklı şeyler söyler.

`outcome` üç dalı ayırıyor ve üçü farklı şeyler: `routed` tabandan geçti ve
yönlendiriciye gitti, `forced` taban geçemedi ama görü bütçesine seçildi,
`skipped` hiçbir katman bakmadı. "Bakılmadı" ile "bakıldı, bir şey yoktu"
aynı satıra düşemez.

## 2.3 Besleme katmanı — `gozcu/ui/feed.py`

`console.py` zaten 1140 satır. Besleme **kendi modülüne** giriyor: saf, Gradio
bilmiyor, `tests/test_feed.py` bütünüyle sınıyor.

```python
class FeedEntry(Base):
    seq: int
    ts: float                    # video saniyesi
    agent: str                   # AgentName | "operator" | "system"
    target: str | None = None    # yalnız devirde
    kind: str
    title: str                   # tek satır, Türkçe
    detail: str = ""             # Türkçe, boş olabilir
    risk: str | None = None      # RiskLevel, uygulanan yerde
    confidence: float | None = None

def build_feed(store, escalated_ids: set[int] | None = None) -> list[FeedEntry]
def feed_html(entries: list[FeedEntry]) -> str
```

`build_feed` defteri `seq` sırasında geziyor, tipli tabloları **bir kez**
sözlüğe okuyor ve her defter satırını bir `FeedEntry`'ye çeviriyor.
**Tanınmayan `source` atlanıyor, tahmin edilmiyor** — yeni bir tablo eklenip
eşleme unutulursa besleme uydurmak yerine susar.

### Ajan atfı

| Defter satırı | Ajan | Satır |
|---|---|---|
| `window_record` create | `perception` | `12 kare · kişi≤2 · forklift,person · taban=EVET` |
| `handoff` create | `source_agent` → `target_agent` | ok satırı + gerekçe + güven |
| `interpretation` create | `interpreter` | açıklama; anlar alt satır |
| `episode` create | `synthesizer` | `Olay açıldı` + özet + ön risk |
| `episode` update | `synthesizer` | `Olaya eklendi` + anlık görüntü özeti |
| `risk` create | `risk_analyst` | seviye + gerekçe + önerilen aksiyonlar |
| `dialogue` create, `supervisor` | `supervisor` | konuşma; kendiliğinden olan işaretli |
| `dialogue` create, `operator` | `operator` | operatör mesajı |
| `dialogue` create, `system` | `system` | sistem bildirimi |
| `action` create, `actor=agent` | `supervisor` | araç + parametre + sonuç |
| `action` create, `actor=operator` | `operator` | aynı, operatör tetikli |
| `action` approval | `operator` | `✓ onaylandı` / `✗ reddedildi` |
| `correction` create | `supervisor` | alan, eski→yeni, gerekçe |

Yedi ajan adı `AgentName` içinde zaten tanımlı; besleme yeni bir ad
uydurmuyor. `operator` ve `system` ajan DEĞİL ve ayrı işaretleniyor —
otonomi kriteri (%20) tam olarak "bunu ajan mı yaptı, insan mı" diye soruyor.

### Denetim satırları

`visible_dialogue`'un kuralı **aynen** taşınıyor: `role="system"` **ve**
`AUDIT_PREFIX` ile BAŞLAYAN satırlar beslemede görünmüyor. Diğer bütün
`system` satırları görünüyor — bozulmuş mod cevapları, `LATE_NOTICE` damgası
ve bekleyen onay bildirimi demo beat 6'nın kendisi.

`visible_dialogue` `console.py`'da kalıyor ve `feed.py` onu içe aktarıyor;
kural tek yerde duruyor.

### Yükseltme kartı beslemenin içinde

`intervention_card` SİLİNMİYOR — beslemenin içinde, **olduğu anda**
basılıyor. Çapa: yükseltilen epizodun o andaki defter satırı. `escalated_ids`
`Session.escalated_ids()`'ten geliyor; `None` geçilirse hiçbir kart
basılmıyor (bugünkü kural: "bilmiyorum"un güvenli yorumu susmaktır).

### Sıralama sözleşmesi

`build_feed` **`seq` artan** sırada döndürüyor — yani gerçek yazılma sırası.
`ts` gösteriliyor ama sıralamıyor: telafi (`catch_up`) sonradan yazılan bir
kaydı önceki bir video saniyesine koyabiliyor ve besleme **yaşanan** sırayı
göstermek zorunda, video saatine göre yeniden dizilmiş bir sırayı değil.
Damga zaten hangi saniyeye ait olduğunu söylüyor.

## 2.4 Ekran

### Kaydırma sorunu ve `column-reverse`

Besleme `gr.HTML` ve ekran kalp atışında (`HEARTBEAT_S = 1.0`) **bütünüyle**
yeniden çiziliyor. `max-height` + `overflow-y:auto` bir kutu, her yeniden
çizimde kaydırmayı başa atar — saniyede bir tepeye zıplayan bir kutu
okunamaz.

Çözüm sohbet kayıtlarının bilinen kalıbı: kap `display:flex;
flex-direction:column-reverse`, girdiler DOM'a **yeniden eskiye** yazılıyor.
Tarayıcı kaydırmayı flex başlangıcına sabitliyor — görsel olarak **alt** — ve
yeniden çizimde orada kalıyor. Okuyucu eskiden yeniye yukarıdan aşağı
görüyor, görüş en yeni girdide sabit duruyor, hiçbir betik gerekmiyor.

### CANLI — tek kolon

Yukarıdan aşağı: video · kontrol satırı (`Analizi başlat`, `Adım adım`,
`Devam et`, `Bağlantıyı kes` / `geri ver`) · §6 zorlu koşul düğmeleri ·
operatör kutusu · onay kutusu (`Onayla` / `Reddet`) · **besleme**.

Video ve kontroller **sabit yukarıda**, besleme altta kendi içinde kayıyor:
tek kolon isteği ile videonun görünür kalması bu şekilde birlikte sağlanıyor.

### RAPOR

Teslim edilen dört anahtarın JSON'u · kök neden raporu · §4 KPI paneli ·
altında iki denetim tablosu: devir defteri (`HANDOFF_HEADERS`) ve araç
tablosu (`TOOL_HEADERS`) + `tool_summary` sayacı.

Tablolar beslemeyi TEKRARLAMAK için değil duruyor: besleme anlatı, tablolar
tam kayıt. Şartname §7 "mock fonksiyonların araç olarak başarıyla
kullanılması"nı doğrudan puanlıyor ve jüri sayılabilir bir tablo istiyor.

Rozet şeridi ve durum çubuğu iki sekmenin de DIŞINDA — bugünkü gibi.

### Yuvalar

`SCREEN_SLOTS` 15 → **13**. `timeline` → `feed` oluyor; `chat` ve
`interventions` beslemeye katıldığı için kalkıyor.

```
session · badges · feed · approval_box · approval_text · ledger ·
tool_count · tools · kpi · payload · report · state · note
```

`SLOT` sözlüğü aynı commit'te güncelleniyor — `tests/test_console.py` o
haritayla indeksliyor ve sayıyla indekslemek bir kez ısırdı.

# 3. Değişen dosyalar

| Dosya | Değişiklik |
|---|---|
| `gozcu/models.py` | `WindowRecord`, `JournalEntry` eklenir |
| `gozcu/store.py` | `journal` + `window_record` tabloları; `_insert` defterler; `update_episode` / `set_action_approval` / `create_episode` anlık görüntü yazar; `journal()`, `save_window()`, `window_records()` |
| `gozcu/loop.py` | pencere toplaması yardımcıya çekilir; `run()` her pencere için `WindowRecord` yazar |
| `gozcu/ui/feed.py` | **yeni** — `FeedEntry`, `build_feed`, `feed_html` |
| `gozcu/ui/console.py` | `build()` iki sekme; `SCREEN_SLOTS` 13; `_refresh`/`_blank`; `timeline_html`/`timeline_rows`/`chat_messages` silinir |
| `tests/test_feed.py` | **yeni** |
| `tests/test_console.py` | sekme ve yuva testleri; `chat_messages` testleri beslemeye taşınır |
| `tests/test_store.py` | defter sırası, anlık görüntü, gözlemin defterlenmemesi |
| `tests/test_loop.py` | pencere kaydı yazılıyor mu, `outcome` üç dal |

`report.py`, `run.py`, ajanlar, `benchmark/` **değişmiyor** — defter tipli
tabloların yanına ekleniyor, yerine değil, ve mevcut bütün okumalar aynen
çalışıyor.

# 4. Hata davranışı

- **Bozuk defter satırı** (silinmiş satıra işaret eden `row_id`) atlanıyor;
  besleme çökmüyor. Bir tanı yüzeyi ölçtüğü koşuyu öldürmemeli — `trace.py`
  ile aynı sözleşme.
- **Boş besleme** kendi metnini yazıyor (`Henüz kayda değer olay yok.`),
  boş bir kutu değil.
- **Tanınmayan `source`** susarak atlanıyor.
- **Tanınmayan risk seviyesi** `UNKNOWN_COLOR`'a düşüyor, gerçek bir rengi
  ödünç almıyor — bugünkü `risk_color` kuralı.

# 5. Doğrulama

```bash
.venv/bin/pytest tests/ -q
uv run python scripts/check-tasks.py
```

Ek olarak elle: `uv run --env-file .env python app.py` ile bir video koşusu —
beslemede en az bir `perception` satırı, bir `router → interpreter` deviri,
bir `synthesizer` epizodu, bir `risk_analyst` değerlendirmesi ve bir araç
çağrısı **oluş sırasında** görünmeli.
