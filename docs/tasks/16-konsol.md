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
konuşuyor. Video bitmeden. Bu, `KararDongusu.calistir()`'ın bir **generator**
olmasıyla sağlanıyor:

```python
for epizot in dongu.calistir(gozlemler):
    mesaj = nobetci.yukselt(epizot)    # operatöre bu düşüyor
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
Nobetci(gw, store)
  .yukselt(epizot: Epizot) -> str          # proaktif uyarı metni
  .konus(operator_metni: str) -> str       # bir diyalog turu
  .bekleyen_onay() -> AksiyonKaydi | None
  .onayla(aksiyon_id: int, onay: bool) -> dict

# gozcu/loop.py
KararDongusu(store, yonlendir, yorumla, sentezle)
  .calistir(gozlemler) -> Iterator[Epizot]     # yükseltmede yield eder

# gozcu/gateway.py
Gateway.hata_enjekte(kademeler: set[str]) -> None    # {"vlm"} = görsel katmanı kes
Gateway.bozulmus_mu() -> bool

# gozcu/store.py
Store.epizotlar() -> list[Epizot]     # .baslangic_ts, .ozet_tr, .on_risk, .durum
Store.devirler() -> list[Devir]       # .kaynak_ajan, .hedef_ajan, .neden, .guven
Store.aksiyonlar() -> list[AksiyonKaydi]
Store.diyalog() -> list[DiyalogSatiri]

# gozcu/agents/router.py
mmss(ts: float) -> str                # 192.0 -> "03:12"
```

Risk seviyeleri: `"Düşük"` · `"Orta"` · `"Yüksek"` · `"Kritik"`

## Ne yapacaksın

Gradio `Blocks`, dört bölge:

**1. Video ve zaman çizelgesi.** Yüklenen klip + epizot işaretleri, risk
seviyesine göre renkli. `Düşük` yeşil, `Orta` sarı, `Yüksek` turuncu,
`Kritik` kırmızı.

**2. Sohbet paneli.** Operatörün Nöbetçi ile konuşması. Her tur `n.konus()`.
Sistemin proaktif mesajları da (`n.yukselt()` çıktısı) buraya düşüyor, ama
görsel olarak ayrışsın — operatör hangi mesajın kendiliğinden geldiğini
görmeli.

**3. Onay çubuğu.** Sadece `n.bekleyen_onay()` `None` değilken görünür. İki
düğme: **Onayla** ve **Reddet**, ikisi de `n.onayla(id, True/False)`. Onay
verildikten sonra çubuk **kaybolmalı** — kaybolmuyorsa Görev 14'te bug var,
Üveys'e haber ver.

**4. Devir defteri.** `store.devirler()` canlı tablo: kaynak → hedef, neden,
güven. Şartnamenin *"sistem çıktıları mümkün olduğunca açıklanabilir
olmalıdır"* maddesine cevabımız bu — "sistem neden böyle karar verdi" sorusunun
cevabı ekranda izlenebiliyor.

Üstte üç düğme:

- **Analizi başlat** — `KararDongusu`'nu koşturur, yükseltmede durur
- **Devam et** — duraklamış döngüyü ilerletir
- **Bağlantıyı kes** — `gw.hata_enjekte({"vlm"})`. Demo'da bunu jürinin gözü
  önünde basıyoruz; sistem çökmemeli, bozulmuş modda uyarı vermeye devam
  etmeli. Bağlantı geri geldiğinde `gw.hata_enjekte(set())`.

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
