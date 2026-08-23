# Görev 06 — Yönlendirici ajanı (`gozcu/agents/router.py`)

**Sahip:** `uvyscengiz` · **Gün:** 24 Ağustos · **Süre:** ~1.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [03](03-gateway.md)

## Bağlam

Sistemin **dikkat mekanizması.** 10 saniyelik pencerelerin sinyal özetine bakıp
"burada dikkat gerektiren bir şey var mı, varsa kime gider" kararını veriyor.

İki tasarım kararı önemli:

**Görüntü görmüyor.** Sadece yapılandırılmış sinyal özeti alıyor. 8B'lik bir
modelin yetmesinin ve hızlı olmasının sebebi bu — kararların büyük çoğunluğu
burada, en ucuz modelde kapanıyor. Slayta giden manşet sayı da bu:
*"kararların %89'u en küçük modelde kapandı."*

**Tetikleyicinin model kararı olması kasıtlı.** Şartname *"sabit kurallara
dayalı basit bir pipeline yerine ... model tabanlı karar mekanizmaları içeren
bir mimari"* istiyor. Sinyal eşiği yerine model kararı koymak bunun doğrudan
kanıtı.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_gateway.py -v      # Görev 03 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit   # kademe pozisyonel
Yanit(icerik, arac_cagrilari, model, gecikme_ms, token, bozulmus)

# gozcu/models.py
Gozlem(id, ts, tespitler, sinyaller)
Sinyaller(hizlar: dict[int, float], kaybolan_trackler: list[int],
          kisi_sayisi: int, kisi_sayisi_degisim: int, toplanma: bool)
RouterKarari(karar, gerekce, guven)
```

## Ne yapacaksın

```python
mmss(ts: float) -> str                                    # 192.0 -> "03:12"
pencere_ozeti(pencere: list[Gozlem]) -> str
yonlendir(gw, pencere: list[Gozlem], acik_epizot_var: bool) -> RouterKarari
```

`mmss` burada tanımlanıp Görev 07, 14 ve 17 tarafından import ediliyor — tek
kopya olsun.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_router.py`

```python
from unittest.mock import Mock

from gozcu.agents.router import mmss, pencere_ozeti, yonlendir
from gozcu.gateway import Yanit
from gozcu.models import Gozlem, Sinyaller


def _g(ts, **kw):
    return Gozlem(ts=ts, sinyaller=Sinyaller(**kw))


def test_mmss_formats_video_time():
    assert mmss(192.0) == "03:12" and mmss(0.0) == "00:00"


def test_digest_is_text_and_carries_no_image():
    ozet = pencere_ozeti([_g(0.0, kisi_sayisi=2, hizlar={1: 3.4}),
                          _g(1.0, kaybolan_trackler=[1])])
    assert "00:00" in ozet and "2" in ozet and "3.4" in ozet
    assert "base64" not in ozet and "image" not in ozet


def test_yonlendir_parses_the_model_decision():
    gw = Mock()
    gw.sor.return_value = Yanit(
        icerik='{"karar":"acil_yukselt","gerekce":"araç devrildi","guven":0.91}')
    k = yonlendir(gw, [_g(0.0, kisi_sayisi=1)], acik_epizot_var=False)
    assert k.karar == "acil_yukselt" and k.guven == 0.91
    assert gw.sor.call_args.args[0] == "router"


def test_open_episode_state_reaches_the_prompt():
    gw = Mock(); gw.sor.return_value = Yanit(icerik='{"karar":"yoksay","gerekce":"x","guven":0.5}')
    yonlendir(gw, [_g(0.0)], acik_epizot_var=True)
    istem = gw.sor.call_args.args[1][-1]["content"]
    assert "Açık bir olay var" in istem


def test_unparseable_response_degrades_to_yoksay_not_a_crash():
    gw = Mock()
    gw.sor.return_value = Yanit(icerik="model bugün konuşmuyor")
    assert yonlendir(gw, [_g(0.0)], acik_epizot_var=False).karar == "yoksay"


def test_degraded_router_tier_degrades_to_yoksay():
    gw = Mock(); gw.sor.return_value = Yanit(bozulmus=True)
    assert yonlendir(gw, [_g(0.0)], acik_epizot_var=False).karar == "yoksay"
```

Son iki test göründüğünden önemli: bozuk JSON'da patlayan bir yönlendirici, tek
bir kötü yanıtta bütün koşuyu düşürür.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/router.py` yaz

```python
import json

from gozcu.models import Gozlem, RouterKarari

SISTEM = """Sen bir fabrika güvenlik kontrol odasının yönlendiricisisin.
Sana 10 saniyelik bir pencerenin sinyal özeti verilir. Görüntü görmezsin.
Görevin: bu pencere dikkat gerektiriyor mu, gerekiyorsa kime gitmeli.

Kararlar:
- yoksay: olağan hareket, ilgilenmeye değmez
- gorsel_incele: bir şey var ama ne olduğu sinyalden anlaşılmıyor
- epizot_ac: yeni bir olay başlıyor
- epizot_guncelle: açık olay devam ediyor
- epizot_kapat: açık olay sonuçlandı
- acil_yukselt: can güvenliği riski, operatör derhal haberdar edilmeli

Açık bir olay yokken epizot_guncelle veya epizot_kapat verme.
Sadece JSON döndür."""


def mmss(ts: float) -> str:
    return f"{int(ts) // 60:02d}:{int(ts) % 60:02d}"


def pencere_ozeti(pencere: list[Gozlem]) -> str:
    satirlar = []
    for g in pencere:
        s = g.sinyaller
        parcalar = [f"kişi={s.kisi_sayisi}"]
        if s.kisi_sayisi_degisim:
            parcalar.append(f"değişim={s.kisi_sayisi_degisim:+d}")
        if s.hizlar:
            parcalar.append("hızlar=" + ",".join(
                f"{tid}:{h:.1f}" for tid, h in s.hizlar.items()))
        if s.kaybolan_trackler:
            parcalar.append(f"kaybolan={s.kaybolan_trackler}")
        if s.toplanma:
            parcalar.append("toplanma")
        satirlar.append(f"{mmss(g.ts)} " + " ".join(parcalar))
    return "\n".join(satirlar)


def yonlendir(gw, pencere: list[Gozlem],
              acik_epizot_var: bool) -> RouterKarari:
    durum = "Açık bir olay var." if acik_epizot_var else "Açık olay yok."
    yanit = gw.sor("router", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": f"{durum}\n\n{pencere_ozeti(pencere)}"},
    ], sema=RouterKarari)

    if yanit.bozulmus:
        return RouterKarari(karar="yoksay",
                            gerekce="yönlendirici kademesi yanıt vermiyor",
                            guven=0.0)
    try:
        return RouterKarari(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001 — kötü bir karar koşuyu durdurmamalı
        return RouterKarari(karar="yoksay",
                            gerekce="yönlendirici yanıtı okunamadı",
                            guven=0.0)
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: 6 passed

### 5. Commit

```bash
git add gozcu/agents/router.py tests/test_router.py
git commit -m "feat: router agent over windowed signal digests"
```

## Doğrulama

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: **6 passed**
