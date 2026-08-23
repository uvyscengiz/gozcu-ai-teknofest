# Görev 04 — Yorumlayıcı adaptörü (`gozcu/agents/interpreter.py`)

**Sahip:** `uvyscengiz` · **Gün:** 24 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)

## Bağlam

Mevcut `gozcu/interpret.py` çalışıyor ama **uzak gateway'e konuşamaz.** İki
sebepten:

1. Kendi `OpenAI` istemcisini `VLM_BASE_URL`'e karşı kuruyor — `Gateway`'i
   baypas ediyor. Bu yüzden `hata_enjekte({"vlm"})` gerçek VLM çağrılarını
   yönetmiyor: demo sırasında bastığımız "bağlantıyı kes" düğmesi
   **hiç kullanılmayan bir katmanı** kesiyor olurdu.
2. `interpret.py:171` görüntüyü `{"url": str(frame_path)}` diye gönderiyor —
   yerel bir dosya yolu. Uzaktaki bir gateway o dosyayı okuyamaz; görüntünün
   base64 data-URI olarak gömülmesi gerekiyor.

Bu görev arayı kapatan adaptörü yazıyor. `interpret.py` **silinmiyor** — donuk
algı katmanının parçası, prompt kurgusu ve çıktı temizleme mantığı oradan
alınıyor.

Ayrıca bu, `Yorum` kayıtlarını üreten tek yer. Onlar olmadan
`vlm_tetikleme_orani` KPI'ı hep sıfır okur.

## Kurulum

```bash
uv sync --extra dev
export GOZCU_GATEWAY_BASE_URL="http://<adres>:4000/v1"
uv run pytest tests/test_gateway.py -v      # Görev 03 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit
Yanit(icerik, arac_cagrilari, model, gecikme_ms, token, bozulmus)

# gozcu/models.py
Gozlem(id, ts, tespitler, sinyaller)
Yorum(id, gozlem_ts, aciklama, notable_event, model, gecikme_ms, token)

# gozcu/store.py
Store.kaydet_yorum(y: Yorum) -> int
```

## Ne yapacaksın

Üreteceğin arayüz:

```python
kare_data_uri(frame_path: str | Path) -> str      # "data:image/jpeg;base64,..."
yorumla(gw, store, pencere: list[Gozlem], kare_yolu) -> Yorum | None
```

`yorumla` pencerenin **orta karesini** seçer (en temsili olan), base64'ler,
`gw.sor("vlm", ...)` ile yorumlatır, `Yorum` üretip depoya yazar.
Gateway bozulmuşsa `None` döner — çağıran taraf bunu bekliyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_interpreter.py`

```python
import base64
from unittest.mock import Mock

from gozcu.agents.interpreter import kare_data_uri, yorumla
from gozcu.gateway import Yanit
from gozcu.models import Gozlem, Sinyaller
from gozcu.store import Store


def _pencere():
    return [Gozlem(ts=float(t), sinyaller=Sinyaller(kisi_sayisi=1))
            for t in range(10)]


def test_data_uri_embeds_the_image_not_a_path(tmp_path):
    p = tmp_path / "kare.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0sahte-jpeg")
    uri = kare_data_uri(p)
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff\xe0sahte-jpeg"
    assert str(p) not in uri


def test_yorumla_sends_through_the_vlm_tier(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    gw = Mock()
    gw.sor.return_value = Yanit(
        icerik='{"aciklama":"İstif aracı yan yattı.","notable_event":null}',
        model="vlm-test", gecikme_ms=420, token=180)
    y = yorumla(gw, Store(":memory:"), _pencere(), lambda ts: p)
    assert gw.sor.call_args.args[0] == "vlm"
    assert y.aciklama == "İstif aracı yan yattı."
    assert y.gecikme_ms == 420 and y.token == 180


def test_yorumla_picks_the_middle_frame_of_the_window(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    istenen = []
    gw = Mock(); gw.sor.return_value = Yanit(icerik='{"aciklama":"x"}')
    yorumla(gw, Store(":memory:"), _pencere(),
            lambda ts: istenen.append(ts) or p)
    assert istenen == [5.0]


def test_yorumla_returns_none_when_the_vlm_tier_is_degraded(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    gw = Mock(); gw.sor.return_value = Yanit(bozulmus=True)
    store = Store(":memory:")
    assert yorumla(gw, store, _pencere(), lambda ts: p) is None
    assert store.yorumlar() == []


def test_yorum_is_persisted_with_the_window_timestamp(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    gw = Mock(); gw.sor.return_value = Yanit(icerik='{"aciklama":"tamam"}')
    store = Store(":memory:")
    yorumla(gw, store, _pencere(), lambda ts: p)
    assert store.yorumlar()[0].gozlem_ts == 5.0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/interpreter.py` yaz

`gozcu/agents/__init__.py` (boş) da gerekiyor.

```python
import base64
import json
import mimetypes
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gozcu.models import Gozlem, Yorum

SISTEM = """Sen bir fabrika güvenlik kamerasının görüntüsünü inceleyen
gözlemcisin. Sana bir kare ve o karedeki tespit/sinyal özeti verilir.

Kurallar:
- Sadece GÖRDÜĞÜNÜ yaz. Emin değilsen "olası" de.
- Türkçe, tek-iki kısa cümle, saha terminolojisi
- Dikkat çekici bir şey yoksa notable_event null olsun
- Kişi kimliği, yaş, cinsiyet tahmini YAPMA

Sadece JSON döndür."""


class _Yorumlama(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aciklama: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)


def kare_data_uri(frame_path: str | Path) -> str:
    p = Path(frame_path)
    tur = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    veri = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{tur};base64,{veri}"


def _baglam(pencere: list[Gozlem]) -> str:
    siniflar = sorted({t.sinif for g in pencere for t in g.tespitler})
    orta = pencere[len(pencere) // 2]
    s = orta.sinyaller
    parcalar = [f"tespitler: {', '.join(siniflar) or 'yok'}",
                f"kişi sayısı: {s.kisi_sayisi}"]
    if s.hizlar:
        parcalar.append("hızlar: " + ", ".join(
            f"{tid}:{h:.1f}" for tid, h in s.hizlar.items()))
    if s.kaybolan_trackler:
        parcalar.append(f"kadraj dışına çıkan: {s.kaybolan_trackler}")
    return " | ".join(parcalar)


def yorumla(gw, store, pencere: list[Gozlem], kare_yolu) -> Yorum | None:
    """kare_yolu: bir ts alıp o ana ait kare dosya yolunu döndüren çağrılabilir."""
    if not pencere:
        return None

    orta = pencere[len(pencere) // 2]
    yol = kare_yolu(orta.ts)
    if yol is None:
        return None

    yanit = gw.sor("vlm", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": [
            {"type": "text",
             "text": f"Sinyaller — {_baglam(pencere)}\n\nBu karede ne oluyor?"},
            {"type": "image_url",
             "image_url": {"url": kare_data_uri(yol)}},
        ]},
    ], sema=_Yorumlama)

    if yanit.bozulmus:
        return None

    try:
        cozum = _Yorumlama(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001 — bozuk JSON bir koşuyu düşürmemeli
        return None

    yorum = Yorum(gozlem_ts=orta.ts, aciklama=cozum.aciklama,
                  notable_event=cozum.notable_event, model=yanit.model,
                  gecikme_ms=yanit.gecikme_ms, token=yanit.token)
    yorum.id = store.kaydet_yorum(yorum)
    return yorum
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: 5 passed

### 5. Commit

```bash
git add gozcu/agents/__init__.py gozcu/agents/interpreter.py tests/test_interpreter.py
git commit -m "feat: VLM interpreter adapter with base64 frames over the gateway"
```

## Doğrulama

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: **5 passed**
