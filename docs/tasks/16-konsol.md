# Görev 16 — Operatör konsolu (`gozcu/ui/console.py`)

**Sahip:** `rumeysaoru` · **Gün:** 25 Ağustos · **Süre:** ~4 saat
**Bağımlılık:** [14](14-nobetci.md) · **İskelet 24 Ağustos'ta hazır olacak**

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

**Demo videosu bu ekranda çekilecek.** Jürinin göreceği tek yüzey bu.

Sıfırdan başlamıyorsun: 24 Ağustos'ta çalışan bir **iskelet** hazır olacak —
video yükleme, zaman çizelgesi, sohbet paneli, başlat düğmesi. Senin işin onu
demo edilebilir hale getirmek.

### Mimarinin tek önemli detayı

Sistem videoyu işlerken **kritik ana geldiğinde duruyor** ve operatörle
konuşuyor. Video bitmeden. Bu, `DecisionLoop.run()`'ın bir **generator**
olmasıyla sağlanıyor:

```python
loop = DecisionLoop(store, route=..., interpret=..., synthesize=...,
                    is_degraded=lambda: gw.is_degraded("vlm"))

for event in loop.run(observations):
    message = nobetci.escalate(event.episode)   # operatöre bu düşüyor
    if event.late:
        pass   # kesinti telafisi: duyur, ama canlı kriz gibi sunma
    # operatör "Devam et" deyene kadar burada bekliyoruz
    # for döngüsü ilerleyince video kaldığı yerden devam ediyor
```

> **Görev 05 bağlama uyarısı.** `run()` `Episode` değil
> **`LoopEvent(episode, late)`** yield ediyor — `event.episode` okunacak.
> `DecisionLoop` kurulurken `is_degraded=lambda: gw.is_degraded("vlm")`
> **geçilmek zorunda**; varsayılan `lambda: False` ile kesintide atlanan
> pencereler hiç birikmez ve telafi hiç görünmez. "Bağlantı geri geldi"
> düğmesi `gw.inject_failure(set())` sonrası `loop.catch_up()` çağırsın —
> telafi edilen epizotlar oradan `late=True` ile geliyor.

Konsolun bu duraklamayı **görünür kılması** gerekiyor. Kullanıcı analizi
başlattığında ekran donmamalı; olay anında durup "sistem seninle konuşuyor"
durumuna geçmeli. Bu proje anlatısının tamamı buna dayanıyor: *sistem videoyu
izlerken karar veriyor, izledikten sonra özetlemiyor.*

### Depoda kilit yok

Konsol, çalışan bir `DecisionLoop`'un yazmakta olduğu SQLite dosyasını okuyor.
`Store`'un `close()`'u, WAL pragma'sı ya da kilidi yok; bağlantı
`check_same_thread=False` ile açılıyor. Yani güvenilecek bir eşzamanlılık
garantisi yok: tabloları döngü `yield` ettiği anlarda tazele, arka planda
sürekli yoklama yapma.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run python app.py       # 24 Ağustos iskeleti burada açılmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/agents/supervisor.py
Supervisor(gw, store)
  .escalate(episode: Episode) -> str          # proaktif uyarı metni
  .talk(operator_text: str) -> str        # bir diyalog turu
  .pending_approval() -> ActionRecord | None
  .approve(action_id: int, approved: bool) -> dict

# gozcu/loop.py
DecisionLoop(store, route, interpret, synthesize, is_degraded)
  .run(observations) -> Iterator[LoopEvent]   # yükseltmede yield eder
  .catch_up() -> Iterator[LoopEvent]          # kesinti bitince atlananları işler
LoopEvent(episode, late)                      # late=True: kesinti sonrası telafi

# gozcu/gateway.py
Gateway.inject_failure(tiers: set[str]) -> None    # {"vlm"} = görsel katmanı kes
Gateway.is_degraded(tier=None) -> bool   # tier verilmezse "herhangi bir kademe"

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

> **Görev 12 indi (`a8cf363`) — rapor SAF, depodan yüklenmiyor.**
> `generate_root_cause_report(gw, store)` bir `RootCauseReport` **döndürür** ve
> hiçbir şey kaydetmez; konsol onu çağırandan alıp ekrana basar,
> `store`'dan okumaya kalkma — orada yok. Raporun dayandığı bölümler (olay
> zinciri, aksiyon defteri, diyalog) prompta `mmss()` biçimiyle giriyor, yani
> rapordaki zamanlar **video zamanı**; konsol da aynı biçimi kullansın.

> **Görev 14 indi (`463a74c`) — onay çubuğu TEK bir bekleyen aksiyon varsayabilir.**
> Süpervizör kapıyı girişte kapatıyor: bekleyen bir onay dururken ikinci bir
> kapılı aksiyon **yürütülmeden reddediliyor** ve deftere hiçbir satır
> yazılmıyor. Yani `pending_approval()` en fazla bir kayıt döndürür ve reddedilen
> ikinci deneme `store.actions()`'ta hiç görünmez — çubuğu bir kuyruk gibi
> tasarlama. Ret operatöre, süpervizörün cevabının **altına eklenen** bir
> `[SİSTEM]` satırı olarak gider (neyin beklediğini adıyla söyler); bu metin
> `.talk()`'un döndürdüğü dizenin içindedir, ayrı bir kanal değil.
>
> **`[denetim]` ile başlayan `role="system"` diyalog satırlarını sohbet
> panelinden SÜZ.** Bunlar denetim hükmünün kaydı, operatöre söylenmiş bir söz
> değil; `store.dialogue()` onları da döndürüyor. Kapıda yalnız
> `halt_production_line` var — geri kalan altı saha aracı anında koşuyor,
> dolayısıyla onlar için onay çubuğu hiç açılmaz.

## Ne yapacaksın

Gradio `Blocks`, dört bölge:

**1. Video ve zaman çizelgesi.** Yüklenen klip + epizot işaretleri, risk
seviyesine göre renkli. `Düşük` yeşil, `Orta` sarı, `Yüksek` turuncu,
`Kritik` kırmızı.

**2. Sohbet paneli.** Operatörün Nöbetçi ile konuşması. Her tur `n.talk()`.
Sistemin proaktif mesajları da (`n.escalate()` çıktısı) buraya düşüyor, ama
görsel olarak ayrışsın — operatör hangi mesajın kendiliğinden geldiğini
görmeli.

**3. Onay çubuğu.** Sadece `n.pending_approval()` `None` değilken görünür. İki
düğme: **Onayla** ve **Reddet**, ikisi de `n.approve(id, True/False)`. Onay
verildikten sonra çubuk **kaybolmalı** — kaybolmuyorsa Görev 14'te bug var,
Üveys'e haber ver.

**4. Devir defteri.** `store.handoffs()` canlı tablo: kaynak → hedef, neden,
güven. Şartnamenin *"sistem çıktıları mümkün olduğunca açıklanabilir
olmalıdır"* maddesine cevabımız bu — "sistem neden böyle karar verdi" sorusunun
cevabı ekranda izlenebiliyor.

Üstte üç düğme:

- **Analizi başlat** — `DecisionLoop`'nu koşturur, yükseltmede durur
- **Devam et** — duraklamış döngüyü ilerletir
- **Bağlantıyı kes** — `gw.inject_failure({"vlm"})`. Demo'da bunu jürinin gözü
  önünde basıyoruz; sistem çökmemeli, bozulmuş modda uyarı vermeye devam
  etmeli. Bağlantı geri geldiğinde `gw.inject_failure(set())`.

## Kabul kriterleri

- [ ] Bir klip yüklenip analiz başlatılabiliyor
- [ ] Analiz sırasında ekran donmuyor, zaman çizelgesi doluyor
- [ ] Kritik olayda **döngü duruyor** ve Nöbetçi'nin mesajı sohbete düşüyor
- [ ] Operatör o sırada yazabiliyor ve cevap alabiliyor
- [ ] "Devam et" döngüyü kaldığı yerden ilerletiyor
- [ ] Onay çubuğu bekleyen aksiyonda çıkıyor, onaydan sonra kayboluyor
- [ ] Devir defteri dolarak akıyor
- [ ] "Bağlantıyı kes" basıldığında sistem çökmüyor, durum bildiriliyor
- [ ] Video bitince JSON çıktısı ve kök neden raporu görünüyor

## Doğrulama

Bu görevin otomatik testi yok — arayüz. Doğrulaması gözle:

```bash
uv run python app.py
```

Yukarıdaki dokuz maddeyi tek tek dene. Hepsi tutuyorsa görev bitmiştir.

**`app.py`'a dokunma** — o Görev 17'ye ait ve Üveys'te. Sen sadece
`gozcu/ui/console.py` içinde çalışıyorsun; `app.py` zaten oraya çağrı yapıyor.

## Commit

```bash
git add gozcu/ui/console.py
git commit -m "feat: operator console with approval bar and handoff ledger"
```

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
Bu görev demo videosunun çekileceği yüzey, tıkanırsan hemen söyle.
