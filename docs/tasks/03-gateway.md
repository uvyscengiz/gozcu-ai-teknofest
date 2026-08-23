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
  .ask(tier, messages, schema=None, tools=None) -> Response   # kademe pozisyonel
  .embed(text) -> list[float]
  .rerank(query, candidates: list[str]) -> list[int]    # indeks listesi
  .inject_failure(tiers: set[str]) -> None
  .is_degraded() -> bool

Response(content, tool_calls, model, latency_ms, tokens, degraded)
GatewayError(RuntimeError)
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_gateway.py`

```python
from unittest.mock import Mock, patch

import pytest

from gozcu.gateway import Gateway, GatewayError


def test_injected_failure_marks_degraded_not_crash():
    gw = Gateway()
    gw.inject_failure({"vlm"})
    response = gw.ask("vlm", [{"role": "user", "content": "x"}])
    assert response.degraded is True and response.content == ""
    assert gw.is_degraded() is True


def test_injected_failure_is_scoped_to_named_tiers():
    """Enjeksiyon sadece adı geçen kademeyi vurmalı. Sızarsa beat 6 tam
    kesinti gibi görünür, kısmi bozulma gibi değil."""
    gw = Gateway()
    gw.inject_failure({"vlm"})
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.side_effect = RuntimeError("ağ yok")
        with pytest.raises(GatewayError):
            gw.ask("main", [{"role": "user", "content": "x"}], _deneme=1)
        c.chat.completions.create.assert_called_once()


def test_recovery_clears_degraded_flag():
    gw = Gateway()
    gw.inject_failure({"vlm"})
    gw.ask("vlm", [{"role": "user", "content": "x"}])
    gw.inject_failure(set())
    assert gw.is_degraded() is False


def test_rerank_failure_falls_back_to_identity_order():
    """Reranker modelleri sohbet talimatı almaz; gateway'de 400 dönebilir.
    Bu asla yukarı kabarcıklanmamalı — arama beat 5'in ortasında çöker."""
    gw = Gateway()
    with patch.object(gw, "ask", side_effect=GatewayError("rerank yok")):
        assert gw.rerank("query", ["a", "b", "c"]) == [0, 1, 2]


def test_goem_goes_through_retry_not_a_raw_call():
    gw = Gateway()
    with patch.object(gw, "_client") as c:
        c.embeddings.create.side_effect = RuntimeError("ağ yok")
        with pytest.raises(GatewayError):
            gw.embed("text", _deneme=2)
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

MODELS = {
    "router": os.environ.get("GOZCU_MODEL_ROUTER", "Qwen3-8B"),
    "fast":  os.environ.get("GOZCU_MODEL_FAST",  "Qwen3.6-35B-A3B"),
    "main":    os.environ.get("GOZCU_MODEL_MAIN",    "Qwen3.5-122B-A10B"),
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
                          GATEWAY_TIMEOUT_S, MODELS)

Tier = Literal["router", "fast", "main", "vlm", "guard", "embed", "rerank"]

# Kaybedip çalışmaya devam edebileceğimiz kademeler. router ve ana bunda yok:
# onlarsız anlamlı bir sistem yok, sessizce sakatlanmış bir ajandansa
# gürültülü bir hata iyidir.
DEGRADABLE = {"vlm", "fast", "rerank"}


class GatewayError(RuntimeError):
    """Bir kademe her denemeden sonra yanıt vermedi ve bozulmuş modu yok."""


@dataclass
class Response:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    tokens: int = 0
    degraded: bool = False


class Gateway:
    def __init__(self, store=None) -> None:
        self.store = store
        self._client = OpenAI(base_url=GATEWAY_BASE_URL,
                              api_key=GATEWAY_API_KEY,
                              timeout=GATEWAY_TIMEOUT_S)
        self._enjekte: set[str] = set()
        self._bozuk: set[str] = set()

    def inject_failure(self, tiers: set[str]) -> None:
        self._enjekte = set(tiers)
        if not tiers:
            self._bozuk.clear()

    def is_degraded(self) -> bool:
        return bool(self._bozuk)

    def _attempt(self, tier: str, cagri, attempts: int):
        last_error: Exception | None = None
        for i in range(attempts):
            if tier in self._enjekte:
                last_error = GatewayError(f"enjekte edilmiş hata: {tier}")
                break
            try:
                return cagri()
            except Exception as exc:  # noqa: BLE001 — her taşıma hatası tekrar denenir
                last_error = exc
                if i < attempts - 1:
                    time.sleep(0.5 * (2 ** i))
        return last_error

    def ask(self, tier: str, messages: list[dict],
            schema: type[BaseModel] | None = None,
            tools: list[dict] | None = None,
            _deneme: int | None = None) -> Response:
        model = MODELS[tier]
        t0 = time.monotonic()

        def cagri():
            request: dict = {"model": model, "messages": messages}
            if schema is not None:
                request["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__,
                                    "schema": schema.model_json_schema(),
                                    "strict": True}}
            if tools:
                request["tools"] = tools
            return self._client.chat.completions.create(**request)

        result = self._attempt(tier, cagri,
                           _deneme if _deneme is not None else GATEWAY_DENEME)

        if isinstance(result, Exception):
            if tier in DEGRADABLE:
                self._bozuk.add(tier)
                return Response(model=model, degraded=True)
            raise GatewayError(f"{tier} kademesi yanıt vermedi") from result

        msg = result.choices[0].message
        self._bozuk.discard(tier)
        return Response(
            content=msg.content or "",
            tool_calls=[t.model_dump() for t in (msg.tool_calls or [])],
            model=model,
            latency_ms=int((time.monotonic() - t0) * 1000),
            tokens=getattr(result.usage, "total_tokens", 0) or 0)

    def embed(self, text: str, _deneme: int | None = None) -> list[float]:
        result = self._attempt(
            "embed",
            lambda: self._client.embeddings.create(model=MODELS["embed"],
                                                   input=text),
            _deneme if _deneme is not None else GATEWAY_DENEME)
        if isinstance(result, Exception):
            raise GatewayError("embed kademesi yanıt vermedi") from result
        return list(result.data[0].embedding)

    def rerank(self, query: str, candidates: list[str]) -> list[int]:
        """Adayların indekslerini en alakalıdan başlayarak döndürür.

        Reranker modelleri çift skorlar, talimat takip etmez — gerçek gateway'de
        400 veya çöp dönmesi beklenir. Bu yüzden her başarısızlık sessizce
        kimlik sırasına düşer: kosinüs sıralaması zaten makul ve puan
        cetvelinde reranker'ın ayrı bir karşılığı yok.
        """
        fallback = list(range(len(candidates)))
        request = "\n".join(f"[{i}] {m}" for i, m in enumerate(candidates))
        try:
            response = self.ask("rerank", [
                {"role": "user",
                 "content": f"Sorgu: {query}\n\nAdaylar:\n{request}\n\n"
                            "En alakalıdan en alakasıza indeksleri virgülle sırala."},
            ])
            if response.degraded:
                return fallback
            order = [int(p) for p in response.content.replace(" ", "").split(",")
                    if p.isdigit() and int(p) < len(candidates)]
            return order or fallback
        except Exception:  # noqa: BLE001
            return fallback
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
