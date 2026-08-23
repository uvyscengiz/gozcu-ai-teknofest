# Görev 05 — Olay anında karar döngüsü (`gozcu/loop.py`)

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md)

## Bağlam

**Bu dosya projenin en önemli mimari tercihini kod haline getiriyor.**

Yüklenen bir videoyu işlemenin iki yolu var:

- **Önce izle, sonra özetle.** Video baştan sona işlenir, sonunda rapor çıkar,
  aksiyonlar rapordan sonra konuşulur. Bu bir *özetleme* sistemidir — ortada
  karar anı yoktur, sadece bitmiş bir metin vardır. Şartnamenin puanladığı
  *çok adımlı karar zincirleri*, *dinamik araç seçimi* ve *inisiyatif alma*
  kalemlerinin üçü de bu şekilde ulaşılamaz.
- **Videonun kendi saatinde karar ver.** Sistem zaman çizelgesinde ilerler,
  kritik ana geldiğinde **orada durur**: riski biçer, sorgular yapar, operatöre
  seslenir, aksiyonu çağırır. Video henüz bitmemiştir.

İkincisini yapıyoruz. Ve bunun gerçekten olması için döngünün **duraklayabilmesi**
gerekiyor — senkron bir `for` döngüsü baştan sona koşarsa, diyalog yine olaydan
sonra gerçekleşmiş olur ve reddettiğimiz şeklin aynısına düşeriz.

Çözüm: `calistir` bir **generator**. Yükseltme anında `yield` ediyor, çağıran
taraf operatörle konuşup `next()` ile devam ettiriyor. Tek iş parçacığı, kilit
yok, ~15 satır.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_store.py -v      # Görev 02 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/models.py
Gozlem(id, ts, tespitler, sinyaller)
Sinyaller(hizlar, kaybolan_trackler, kisi_sayisi, kisi_sayisi_degisim, toplanma)
RouterKarari(karar, gerekce, guven)   # karar: yoksay|gorsel_incele|epizot_ac|
                                      #        epizot_guncelle|epizot_kapat|acil_yukselt
Epizot(id, baslangic_ts, bitis_ts, faz, ozet_tr, katilimcilar, on_risk, durum)
Devir(id, ts, kaynak_ajan, hedef_ajan, neden, guven, payload_ref)

# gozcu/store.py
Store.kaydet_devir(d) -> int
```

## Ne yapacaksın

```python
PENCERE_S = 10.0
TABAN_HIZ = 1.0

pencereler(gozlemler, pencere_s=PENCERE_S) -> Iterator[list[Gozlem]]
taban_gecti(pencere: list[Gozlem]) -> bool
KararDongusu(store, yonlendir, yorumla, sentezle)
  .calistir(gozlemler) -> Iterator[Epizot]      # yükseltmede yield eder
```

Bütün geri çağrılar dışarıdan enjekte ediliyor — bu modül hiçbir ajan olmadan
test edilebiliyor.

**Sentezleyici geri çağrısının imzası:** `sentezle(pencere, yorum, karar) -> Epizot | None`.
`karar` parametresi zorunlu: `epizot_ac` yeni epizot açar, `epizot_guncelle`
açık epizota kaynaşır, `epizot_kapat` kapatır. Bu olmadan üç karar da yeni
epizot açar ve tek bir kaza N kopya epizot olur.

**Dispeçer karelere değil pencerelere bakıyor.** 10 dakikalık videoda kare başına
yönlendirme ~600 model çağrısı demek; pencerelerle ~60. Altında da yerel bir
taban var: hiçbir şeyin kıpırdamadığı pencere modele hiç gitmiyor.

Bu tabanın "kural tabanlı" olmadığının savunması net: **hareket sensörü kuralı,
alarm kararı değildir.** Taban *ne zaman soracağını* belirliyor; *neyin önemli
olduğuna* model karar veriyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_loop.py`

```python
from gozcu.loop import KararDongusu, pencereler, taban_gecti
from gozcu.models import Epizot, Gozlem, RouterKarari, Sinyaller, Tespit
from gozcu.store import Store


def _gozlem(ts, kisi=0, hiz=None):
    return Gozlem(ts=ts,
                  tespitler=[Tespit(sinif="person", guven=0.9,
                                    kutu=(0, 0, 1, 1), track_id=1)] * kisi,
                  sinyaller=Sinyaller(kisi_sayisi=kisi, hizlar=hiz or {}))


def _epizot(ts=0.0):
    return Epizot(baslangic_ts=ts, faz="gelisim", ozet_tr="x", on_risk="Kritik")


def _dongu(store, yonlendir, sentezle=None, yorumla=None):
    return KararDongusu(store, yonlendir=yonlendir,
                        yorumla=yorumla or (lambda p: None),
                        sentezle=sentezle or (lambda p, y, k: _epizot(p[0].ts)))


def test_pencereler_groups_by_ten_seconds():
    g = [_gozlem(float(t)) for t in range(25)]
    assert [len(p) for p in pencereler(g)] == [10, 10, 5]


def test_taban_blocks_a_completely_still_window():
    assert taban_gecti([_gozlem(float(t)) for t in range(10)]) is False
    assert taban_gecti([_gozlem(float(t), kisi=2) for t in range(10)]) is True


def test_router_is_not_called_for_windows_below_the_floor():
    cagrilar = []
    d = _dongu(Store(":memory:"),
               lambda p: cagrilar.append(p) or RouterKarari(
                   karar="yoksay", gerekce="x", guven=0.5))
    list(d.calistir([_gozlem(float(t)) for t in range(20)]))
    assert cagrilar == []


def test_escalation_yields_an_episode_before_the_video_ends():
    """§3a'nın bekçisi. Biri döngüyü 'topla-sonra-karar-ver' haline
    çevirirse bu test kırmızıya döner."""
    gozlemler = [_gozlem(float(t), kisi=2) for t in range(30)]

    def yonlendir(p):
        return RouterKarari(
            karar="acil_yukselt" if p[0].ts < 10 else "yoksay",
            gerekce="x", guven=0.9)

    d = _dongu(Store(":memory:"), yonlendir)
    ilk = next(d.calistir(gozlemler))
    assert isinstance(ilk, Epizot)
    assert ilk.baslangic_ts < gozlemler[-1].ts


def test_escalation_synthesises_an_episode_first():
    """Yükseltilecek bir epizot yoksa risk analizi tutunacak bir şey bulamaz."""
    cagrilar = []
    d = _dongu(Store(":memory:"),
               lambda p: RouterKarari(karar="acil_yukselt", gerekce="x",
                                      guven=0.9),
               sentezle=lambda p, y, k: cagrilar.append(k) or _epizot(p[0].ts))
    next(d.calistir([_gozlem(float(t), kisi=2) for t in range(10)]))
    assert cagrilar == ["epizot_ac"]


def test_the_decision_is_passed_through_to_the_synthesiser():
    kararlar = []
    sirasi = iter(["epizot_ac", "epizot_guncelle", "epizot_kapat"])
    d = _dongu(Store(":memory:"),
               lambda p: RouterKarari(karar=next(sirasi), gerekce="x",
                                      guven=0.9),
               sentezle=lambda p, y, k: kararlar.append(k) or _epizot(p[0].ts))
    list(d.calistir([_gozlem(float(t), kisi=1) for t in range(30)]))
    assert kararlar == ["epizot_ac", "epizot_guncelle", "epizot_kapat"]


def test_every_routing_decision_is_written_to_the_handoff_ledger():
    store = Store(":memory:")
    d = _dongu(store, lambda p: RouterKarari(karar="yoksay", gerekce="sakin",
                                             guven=0.8))
    list(d.calistir([_gozlem(float(t), kisi=1) for t in range(20)]))
    assert len(store.devirler()) == 2
    assert store.devirler()[0].kaynak_ajan == "yonlendirici"


def test_ledger_timestamps_are_video_relative_not_wall_clock():
    store = Store(":memory:")
    d = _dongu(store, lambda p: RouterKarari(karar="yoksay", gerekce="x",
                                             guven=0.8))
    list(d.calistir([_gozlem(float(t), kisi=1) for t in range(20)]))
    assert [dv.ts for dv in store.devirler()] == [0.0, 10.0]
```

Son test önemsiz görünüyor ama değil: defterdeki zaman damgaları süreç
uptime'ı olursa (`time.monotonic()`), jüri kanıt defterini açtığında anlamsız
sayılar görür. Video-göreli olmalı.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.loop'`

### 3. `gozcu/loop.py` yaz

```python
from collections.abc import Callable, Iterator

from gozcu.models import Devir, Epizot, Gozlem, RouterKarari
from gozcu.store import Store

PENCERE_S = 10.0
TABAN_HIZ = 1.0

HEDEF = {"gorsel_incele": "yorumlayici",
         "epizot_ac": "sentezleyici",
         "epizot_guncelle": "sentezleyici",
         "epizot_kapat": "sentezleyici",
         "acil_yukselt": "nobetci"}


def pencereler(gozlemler: list[Gozlem],
               pencere_s: float = PENCERE_S) -> Iterator[list[Gozlem]]:
    if not gozlemler:
        return
    basla, kova = gozlemler[0].ts, []
    for g in gozlemler:
        if g.ts - basla >= pencere_s:
            yield kova
            basla, kova = g.ts, []
        kova.append(g)
    if kova:
        yield kova


def taban_gecti(pencere: list[Gozlem]) -> bool:
    """Ucuz yerel taban: *ne zaman soracağını* belirler, *neyin önemli
    olduğunu* değil. Hareket sensörü kuralı, alarm kararı değildir."""
    for g in pencere:
        s = g.sinyaller
        if s.kisi_sayisi > 0 or s.kaybolan_trackler or s.toplanma:
            return True
        if any(h >= TABAN_HIZ for h in s.hizlar.values()):
            return True
    return False


class KararDongusu:
    def __init__(self, store: Store,
                 yonlendir: Callable[[list[Gozlem]], RouterKarari],
                 yorumla: Callable[[list[Gozlem]], object],
                 sentezle: Callable[[list[Gozlem], object, str], Epizot | None]
                 ) -> None:
        self.store = store
        self.yonlendir = yonlendir
        self.yorumla = yorumla
        self.sentezle = sentezle

    def _devir(self, hedef: str, ts: float, neden: str, guven: float) -> None:
        self.store.kaydet_devir(Devir(ts=ts, kaynak_ajan="yonlendirici",
                                      hedef_ajan=hedef, neden=neden,
                                      guven=guven, payload_ref=f"pencere@{ts}"))

    def calistir(self, gozlemler: list[Gozlem]) -> Iterator[Epizot]:
        """Videonun zaman çizelgesinde ilerler. Yükseltme gerektiren her anda
        epizotu yield eder ve ORADA DURUR — çağıran taraf operatörle konuşup
        döngüyü devam ettirir. §3a tam olarak budur."""
        for pencere in pencereler(gozlemler):
            ts = pencere[0].ts
            if not taban_gecti(pencere):
                continue

            karar = self.yonlendir(pencere)
            self._devir(HEDEF.get(karar.karar, "algi"), ts,
                        karar.gerekce, karar.guven)

            if karar.karar == "yoksay":
                continue

            yorum = self.yorumla(pencere) if karar.karar in (
                "gorsel_incele", "epizot_ac", "epizot_guncelle",
                "acil_yukselt") else None

            if karar.karar in ("epizot_ac", "epizot_guncelle", "epizot_kapat"):
                self.sentezle(pencere, yorum, karar.karar)

            elif karar.karar == "acil_yukselt":
                # Yükseltmenin tutunacağı bir epizot olmalı; yoksa risk
                # analizi hangi epizota yazacağını bilemez.
                epizot = self.sentezle(pencere, yorum, "epizot_ac")
                if epizot is not None:
                    # Video bitmedi. Çağıran taraf burada operatörle konuşuyor.
                    yield epizot
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: 8 passed

### 5. Commit

```bash
git add gozcu/loop.py tests/test_loop.py
git commit -m "feat: in-flight decision loop that pauses at escalation"
```

## Doğrulama

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: **8 passed**

## Çağıran taraf nasıl kullanacak (Görev 16 ve 17 için)

```python
for epizot in dongu.calistir(gozlemler):
    nobetci.yukselt(epizot)      # operatör burada konuşuyor, döngü duruyor
    # operatör "devam" deyince for döngüsü kendiliğinden ilerliyor
```
