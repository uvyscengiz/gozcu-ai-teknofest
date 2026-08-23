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
for episode in loop.run(observations):
    message = nobetci.escalate(episode)    # operatöre bu düşüyor
    # operatör "Devam et" deyene kadar burada bekliyoruz
    # for döngüsü ilerleyince video kaldığı yerden devam ediyor
```

Konsolun bu duraklamayı **görünür kılması** gerekiyor. Kullanıcı analizi
başlattığında ekran donmamalı; olay anında durup "sistem seninle konuşuyor"
durumuna geçmeli. Bu proje anlatısının tamamı buna dayanıyor: *sistem videoyu
izlerken karar veriyor, izledikten sonra özetlemiyor.*

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run python app.py       # 24 Ağustos iskeleti burada açılmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/agents/nobetci.py
Supervisor(gw, store)
  .escalate(episode: Episode) -> str          # proaktif uyarı metni
  .talk(operator_metni: str) -> str       # bir diyalog turu
  .pending_approval() -> ActionRecord | None
  .approve(action_id: int, onay: bool) -> dict

# gozcu/loop.py
DecisionLoop(store, route, interpret, synthesize)
  .run(observations) -> Iterator[Episode]     # yükseltmede yield eder

# gozcu/gateway.py
Gateway.inject_failure(tiers: set[str]) -> None    # {"vlm"} = görsel katmanı kes
Gateway.is_degraded() -> bool

# gozcu/store.py
Store.episodes() -> list[Episode]     # .baslangic_ts, .ozet_tr, .on_risk, .durum
Store.handoffs() -> list[Handoff]       # .kaynak_ajan, .hedef_ajan, .neden, .guven
Store.actions() -> list[ActionRecord]
Store.dialogue() -> list[DialogueTurn]

# gozcu/agents/router.py
mmss(ts: float) -> str                # 192.0 -> "03:12"
```

Risk seviyeleri: `"Düşük"` · `"Orta"` · `"Yüksek"` · `"Kritik"`

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
