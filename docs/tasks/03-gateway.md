# Görev 03 — Kademeli gateway istemcisi (`gozcu/gateway.py`)

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [00](00-test-altyapisi.md)

## Bağlam

Sistemdeki **her** model çağrısı buradan geçiyor. Modeller organizasyonun
sunucusunda, OpenAI uyumlu bir gateway'in arkasında. Yedi farklı kademe var ve
tasarımın omurgası şu: **her karar, yetecek en ucuz modele düşer.**

| Kademe | Ne için | Sıklık |
|---|---|---|
| `router` | "Bu önemli mi, kime gider?" | Yüksek |
| `hizli` | Kareler → epizot sentezi | Orta |
| `ana` | Operatör diyalogu, risk, rapor | Düşük |
| `vlm` | Tetiklenen karenin yorumu | Tetiklenince |
| `guard` | Operatöre giden metnin denetimi | Çıktı başına |
| `embed` | Epizot gömme | Epizot başına |
| `rerank` | Arama sonuçlarını sıralama | Sorgu başına |

**Bozulmuş mod tasarımın parçası, kaza değil.** Demo sırasında bağlantıyı bilerek
kesip sistemin ayakta kaldığını göstereceğiz — bu, puan cetvelinde iki ayrı
kalemden birden puan alıyor (*hata işleme* ve *beklenmedik durumlara tepki*).

## Kurulum

```bash
uv sync --extra dev
export GOZCU_GATEWAY_BASE_URL="http://<adres>:4000/v1"
export GOZCU_GATEWAY_API_KEY="<anahtar>"
```

## Ne yapacaksın

`gozcu/config.py`'a kademe ayarlarını ekle, `gozcu/gateway.py`'ı yaz.

Üreteceğin arayüz:

```python
Gateway(store=None)
  .sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit   # kademe pozisyonel
  .goem(metin) -> list[float]
  .yeniden_sirala(sorgu, adaylar: list[str]) -> list[int]    # indeks listesi
  .hata_enjekte(kademeler: set[str]) -> None
  .bozulmus_mu() -> bool

Yanit(icerik, arac_cagrilari, model, gecikme_ms, token, bozulmus)
GatewayHatasi(RuntimeError)
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_gateway.py`

```python
from unittest.mock import Mock, patch

import pytest

from gozcu.gateway import Gateway, GatewayHatasi


def test_injected_failure_marks_degraded_not_crash():
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    yanit = gw.sor("vlm", [{"role": "user", "content": "x"}])
    assert yanit.bozulmus is True and yanit.icerik == ""
    assert gw.bozulmus_mu() is True


def test_injected_failure_is_scoped_to_named_tiers():
    """Enjeksiyon sadece adı geçen kademeyi vurmalı. Sızarsa beat 6 tam
    kesinti gibi görünür, kısmi bozulma gibi değil."""
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.side_effect = RuntimeError("ağ yok")
        with pytest.raises(GatewayHatasi):
            gw.sor("ana", [{"role": "user", "content": "x"}], _deneme=1)
        c.chat.completions.create.assert_called_once()


def test_recovery_clears_degraded_flag():
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    gw.sor("vlm", [{"role": "user", "content": "x"}])
    gw.hata_enjekte(set())
    assert gw.bozulmus_mu() is False


def test_rerank_failure_falls_back_to_identity_order():
    """Reranker modelleri sohbet talimatı almaz; gateway'de 400 dönebilir.
    Bu asla yukarı kabarcıklanmamalı — arama beat 5'in ortasında çöker."""
    gw = Gateway()
    with patch.object(gw, "sor", side_effect=GatewayHatasi("rerank yok")):
        assert gw.yeniden_sirala("sorgu", ["a", "b", "c"]) == [0, 1, 2]


def test_goem_goes_through_retry_not_a_raw_call():
    gw = Gateway()
    with patch.object(gw, "_client") as c:
        c.embeddings.create.side_effect = RuntimeError("ağ yok")
        with pytest.raises(GatewayHatasi):
            gw.goem("metin", _deneme=2)
        assert c.embeddings.create.call_count == 2
```

İkinci test `_client`'ı stub'lıyor — **gerçek gateway'e istek atmıyor.** Aksi
halde her `pytest` koşusu organizasyonun paylaşımlı sunucusuna trafik gönderir
ve gateway çalışırken test kırmızı olur.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_gateway.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.gateway'`

### 3. `gozcu/config.py`'a ekle

Mevcut YOLO/kare ayarlarını **silme**, altına ekle:

```python
GATEWAY_BASE_URL = os.environ.get(
    "GOZCU_GATEWAY_BASE_URL", "http://localhost:4000/v1")
GATEWAY_API_KEY = os.environ.get("GOZCU_GATEWAY_API_KEY", "not-needed")

MODELLER = {
    "router": os.environ.get("GOZCU_MODEL_ROUTER", "Qwen3-8B"),
    "hizli":  os.environ.get("GOZCU_MODEL_HIZLI",  "Qwen3.6-35B-A3B"),
    "ana":    os.environ.get("GOZCU_MODEL_ANA",    "Qwen3.5-122B-A10B"),
    "vlm":    os.environ.get("GOZCU_MODEL_VLM",    "Qwen3-VL-30B-A3B"),
    "guard":  os.environ.get("GOZCU_MODEL_GUARD",  "Qwen3Guard-Gen-4B"),
    "embed":  os.environ.get("GOZCU_MODEL_EMBED",  "Qwen3-Embedding-4B"),
    "rerank": os.environ.get("GOZCU_MODEL_RERANK", "Qwen3-Reranker-4B"),
}

GATEWAY_TIMEOUT_S = float(os.environ.get("GOZCU_GATEWAY_TIMEOUT", "60"))
GATEWAY_DENEME = int(os.environ.get("GOZCU_GATEWAY_DENEME", "3"))
```

Organizasyon farklı model adları deploy ederse **tek düzenlenecek yer burası.**

### 4. `gozcu/gateway.py` yaz

```python
import time
from dataclasses import dataclass, field
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from gozcu.config import (GATEWAY_API_KEY, GATEWAY_BASE_URL, GATEWAY_DENEME,
                          GATEWAY_TIMEOUT_S, MODELLER)

Kademe = Literal["router", "hizli", "ana", "vlm", "guard", "embed", "rerank"]

# Kaybedip çalışmaya devam edebileceğimiz kademeler. router ve ana bunda yok:
# onlarsız anlamlı bir sistem yok, sessizce sakatlanmış bir ajandansa
# gürültülü bir hata iyidir.
BOZULABILIR = {"vlm", "hizli", "rerank"}


class GatewayHatasi(RuntimeError):
    """Bir kademe her denemeden sonra yanıt vermedi ve bozulmuş modu yok."""


@dataclass
class Yanit:
    icerik: str = ""
    arac_cagrilari: list[dict] = field(default_factory=list)
    model: str = ""
    gecikme_ms: int = 0
    token: int = 0
    bozulmus: bool = False


class Gateway:
    def __init__(self, store=None) -> None:
        self.store = store
        self._client = OpenAI(base_url=GATEWAY_BASE_URL,
                              api_key=GATEWAY_API_KEY,
                              timeout=GATEWAY_TIMEOUT_S)
        self._enjekte: set[str] = set()
        self._bozuk: set[str] = set()

    def hata_enjekte(self, kademeler: set[str]) -> None:
        self._enjekte = set(kademeler)
        if not kademeler:
            self._bozuk.clear()

    def bozulmus_mu(self) -> bool:
        return bool(self._bozuk)

    def _dene(self, kademe: str, cagri, denemeler: int):
        son_hata: Exception | None = None
        for i in range(denemeler):
            if kademe in self._enjekte:
                son_hata = GatewayHatasi(f"enjekte edilmiş hata: {kademe}")
                break
            try:
                return cagri()
            except Exception as exc:  # noqa: BLE001 — her taşıma hatası tekrar denenir
                son_hata = exc
                if i < denemeler - 1:
                    time.sleep(0.5 * (2 ** i))
        return son_hata

    def sor(self, kademe: str, mesajlar: list[dict],
            sema: type[BaseModel] | None = None,
            araclar: list[dict] | None = None,
            _deneme: int | None = None) -> Yanit:
        model = MODELLER[kademe]
        t0 = time.monotonic()

        def cagri():
            istek: dict = {"model": model, "messages": mesajlar}
            if sema is not None:
                istek["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": sema.__name__,
                                    "schema": sema.model_json_schema(),
                                    "strict": True}}
            if araclar:
                istek["tools"] = araclar
            return self._client.chat.completions.create(**istek)

        sonuc = self._dene(kademe, cagri,
                           _deneme if _deneme is not None else GATEWAY_DENEME)

        if isinstance(sonuc, Exception):
            if kademe in BOZULABILIR:
                self._bozuk.add(kademe)
                return Yanit(model=model, bozulmus=True)
            raise GatewayHatasi(f"{kademe} kademesi yanıt vermedi") from sonuc

        msg = sonuc.choices[0].message
        self._bozuk.discard(kademe)
        return Yanit(
            icerik=msg.content or "",
            arac_cagrilari=[t.model_dump() for t in (msg.tool_calls or [])],
            model=model,
            gecikme_ms=int((time.monotonic() - t0) * 1000),
            token=getattr(sonuc.usage, "total_tokens", 0) or 0)

    def goem(self, metin: str, _deneme: int | None = None) -> list[float]:
        sonuc = self._dene(
            "embed",
            lambda: self._client.embeddings.create(model=MODELLER["embed"],
                                                   input=metin),
            _deneme if _deneme is not None else GATEWAY_DENEME)
        if isinstance(sonuc, Exception):
            raise GatewayHatasi("embed kademesi yanıt vermedi") from sonuc
        return list(sonuc.data[0].embedding)

    def yeniden_sirala(self, sorgu: str, adaylar: list[str]) -> list[int]:
        """Adayların indekslerini en alakalıdan başlayarak döndürür.

        Reranker modelleri çift skorlar, talimat takip etmez — gerçek gateway'de
        400 veya çöp dönmesi beklenir. Bu yüzden her başarısızlık sessizce
        kimlik sırasına düşer: kosinüs sıralaması zaten makul ve puan
        cetvelinde reranker'ın ayrı bir karşılığı yok.
        """
        varsayilan = list(range(len(adaylar)))
        istek = "\n".join(f"[{i}] {m}" for i, m in enumerate(adaylar))
        try:
            yanit = self.sor("rerank", [
                {"role": "user",
                 "content": f"Sorgu: {sorgu}\n\nAdaylar:\n{istek}\n\n"
                            "En alakalıdan en alakasıza indeksleri virgülle sırala."},
            ])
            if yanit.bozulmus:
                return varsayilan
            sira = [int(p) for p in yanit.icerik.replace(" ", "").split(",")
                    if p.isdigit() and int(p) < len(adaylar)]
            return sira or varsayilan
        except Exception:  # noqa: BLE001
            return varsayilan
```

### 5. Yeşil olduğunu gör

```bash
uv run pytest tests/test_gateway.py -v
```
Beklenen: 5 passed

### 6. Commit

```bash
git add gozcu/gateway.py gozcu/config.py tests/test_gateway.py
git commit -m "feat: tiered gateway client with scoped degraded mode"
```

## Doğrulama

```bash
uv run pytest tests/test_gateway.py -v
```
Beklenen: **5 passed** — ve testler çalışırken gateway'e gerçek istek gitmemeli.
