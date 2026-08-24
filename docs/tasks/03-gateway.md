# Görev 03 — Kademeli gateway istemcisi (`gozcu/gateway.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `2db4dad`
>
> **Gateway indi.** `gozcu/gateway.py` var, `tests/test_gateway.py` 12 test
> fonksiyonu / 18 durum ile yeşil. Bu dosyayı yeniden uygulama — aşağısı ne
> yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **her kademe bozulabilir** — `ask()` kesintide artık istisna atmıyor, boş
> içerikli `degraded=True` bir `Response` döndürüyor; `is_degraded(tier)` kademe
> başına, çıplak `is_degraded()` ise "herhangi bir kademe" demek.

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [00](00-test-altyapisi.md)

## Bağlam

Sistemdeki **her** model çağrısı buradan geçiyor. Modeller organizasyonun
sunucusunda, OpenAI uyumlu bir gateway'in arkasında. Yedi farklı kademe var ve
tasarımın omurgası şu: **her karar, yetecek en ucuz modele düşer.**

| Kademe | Ne için | Sıklık |
|---|---|---|
| `router` | "Bu önemli mi, kime gider?" | Yüksek |
| `fast` | Kareler → epizot sentezi | Orta |
| `main` | Operatör diyalogu, risk, rapor | Düşük |
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
  .ask(tier, messages, schema=None, tools=None) -> Response   # tier pozisyonel
  .embed(text) -> list[float]           # bozulmuşsa []
  .rerank(query, candidates: list[str]) -> list[int]    # indeks listesi
  .inject_failure(tiers: set[str]) -> None
  .is_degraded(tier=None) -> bool       # tier verilmezse "herhangi bir kademe"

Response(content, tool_calls, model, latency_ms, tokens, degraded)
GatewayError(RuntimeError)              # sadece bilinmeyen kademe adı
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_gateway.py`

```python
from unittest.mock import Mock, patch

import pytest

from gozcu.gateway import Gateway, GatewayError

MESSAGES = [{"role": "user", "content": "x"}]
TIERS = ["router", "fast", "main", "vlm", "guard", "embed", "rerank"]


def _completion(content: str, tokens: int = 12) -> Mock:
    """OpenAI sohbet yanıtının test için yeten kadarı."""
    message = Mock(content=content, tool_calls=[])
    return Mock(choices=[Mock(message=message)], usage=Mock(total_tokens=tokens))


def test_injected_failure_marks_degraded_not_crash():
    gw = Gateway()
    gw.inject_failure({"vlm"})
    response = gw.ask("vlm", MESSAGES)
    assert response.degraded is True and response.content == ""
    assert gw.is_degraded() is True


def test_injected_failure_is_scoped_to_named_tiers():
    """Enjeksiyon sadece adı geçen kademeyi vurmalı. Sızarsa beat 6 tam
    kesinti gibi görünür, kısmi bozulma gibi değil."""
    gw = Gateway()
    gw.inject_failure({"vlm"})
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.return_value = _completion("tamam")
        response = gw.ask("main", MESSAGES, _retries=1)
        c.chat.completions.create.assert_called_once()
    assert response.degraded is False and response.content == "tamam"


@pytest.mark.parametrize("tier", TIERS)
def test_every_tier_degrades_instead_of_raising(tier):
    """Hiçbir kesinti koşuyu düşürmez: şartnamenin dört anahtarı, genişletilmiş
    katmanların hepsi çökse bile üretilebilmeli."""
    gw = Gateway()
    gw.inject_failure({tier})
    response = gw.ask(tier, MESSAGES)
    assert response.degraded is True and response.content == ""
    assert gw.is_degraded(tier) is True


def test_unknown_tier_is_a_programming_error():
    """GatewayError artık kesintiyi değil, olmayan bir kademe adını bildirir."""
    gw = Gateway()
    with pytest.raises(GatewayError):
        gw.ask("supervisor", MESSAGES)


def test_degraded_rerank_does_not_degrade_the_vision_tier():
    """Görev 05 `is_degraded("vlm")`'i 'görü katmanı çöktü' diye okuyor. rerank'ın
    beklenen 400'ü bunu latch'lerse döngü her pencereyi sonsuza dek erteler."""
    gw = Gateway()
    gw.inject_failure({"rerank"})
    gw.ask("rerank", MESSAGES)
    assert gw.is_degraded("rerank") is True
    assert gw.is_degraded("vlm") is False
    assert gw.is_degraded() is True


def test_inject_failure_replaces_the_previous_injection():
    gw = Gateway()
    gw.inject_failure({"rerank"})
    gw.ask("rerank", MESSAGES)
    gw.inject_failure({"vlm"})
    assert gw.is_degraded("rerank") is False
    assert gw.is_degraded() is False


def test_recovery_clears_degraded_flag():
    gw = Gateway()
    gw.inject_failure({"vlm"})
    gw.ask("vlm", MESSAGES)
    gw.inject_failure(set())
    assert gw.is_degraded() is False


def test_a_later_success_clears_that_tiers_degradation():
    gw = Gateway()
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.side_effect = RuntimeError("ağ yok")
        assert gw.ask("vlm", MESSAGES, _retries=1).degraded is True
        assert gw.is_degraded("vlm") is True
        c.chat.completions.create.side_effect = None
        c.chat.completions.create.return_value = _completion("tamam")
        response = gw.ask("vlm", MESSAGES, _retries=1)
    assert response.degraded is False and response.content == "tamam"
    assert gw.is_degraded("vlm") is False and gw.is_degraded() is False


def test_rerank_failure_falls_back_to_identity_order():
    """Reranker modelleri sohbet talimatı almaz; gateway'de 400 dönebilir.
    Bu asla yukarı kabarcıklanmamalı — arama beat 5'in ortasında çöker."""
    gw = Gateway()
    with patch.object(gw, "ask", side_effect=GatewayError("rerank yok")):
        assert gw.rerank("query", ["a", "b", "c"]) == [0, 1, 2]


def test_rerank_falls_back_when_its_tier_is_degraded():
    gw = Gateway()
    gw.inject_failure({"rerank"})
    assert gw.rerank("query", ["a", "b", "c"]) == [0, 1, 2]


def test_embed_goes_through_retry_not_a_raw_call():
    gw = Gateway()
    with patch.object(gw, "_client") as c, patch("gozcu.gateway.time.sleep"):
        c.embeddings.create.side_effect = RuntimeError("ağ yok")
        assert gw.embed("text", _retries=2) == []
        assert c.embeddings.create.call_count == 2


def test_embed_returns_an_empty_vector_when_degraded():
    """Görev 08 boş vektörü 'sonuç yok' diye okuyor — burada patlamak yok."""
    gw = Gateway()
    gw.inject_failure({"embed"})
    assert gw.embed("text") == []
    assert gw.is_degraded("embed") is True
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

# Model kimliklerinin yaşadığı tek yer (CLAUDE.md). scripts/gen-litellm-config.py
# bu tabloyu kendi içinde tekrar tanımlamak yerine buradan import ediyor;
# organizasyon başka adlar deploy ederse düzenlenecek tek yer bu sözlük ya da
# GOZCU_MODEL_* ortam değişkenleri.
MODELS = {
    "router": os.environ.get("GOZCU_MODEL_ROUTER", "Qwen3-8B"),
    "fast": os.environ.get("GOZCU_MODEL_FAST", "Qwen3.6-35B-A3B"),
    "main": os.environ.get("GOZCU_MODEL_MAIN", "Qwen3.5-122B-A10B"),
    "vlm": os.environ.get("GOZCU_MODEL_VLM", "Qwen3-VL-30B-A3B"),
    "guard": os.environ.get("GOZCU_MODEL_GUARD", "Qwen3Guard-Gen-4B"),
    "embed": os.environ.get("GOZCU_MODEL_EMBED", "Qwen3-Embedding-4B"),
    "rerank": os.environ.get("GOZCU_MODEL_RERANK", "Qwen3-Reranker-4B"),
}

GATEWAY_TIMEOUT_S = float(os.environ.get("GOZCU_GATEWAY_TIMEOUT", "60"))
GATEWAY_RETRIES = int(os.environ.get("GOZCU_GATEWAY_RETRIES", "3"))
```

Organizasyon farklı model adları deploy ederse **tek düzenlenecek yer burası.**
`scripts/gen-litellm-config.py` yedi adı artık burdan import ediyor — kendi
içinde tekrar tanımlamıyor.

### 4. `gozcu/gateway.py` yaz

```python
import time
from dataclasses import dataclass, field
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from gozcu.config import (GATEWAY_API_KEY, GATEWAY_BASE_URL, GATEWAY_RETRIES,
                          GATEWAY_TIMEOUT_S, MODELS)

Tier = Literal["router", "fast", "main", "vlm", "guard", "embed", "rerank"]


class GatewayError(RuntimeError):
    """Programlama hatası — kesinti değil.

    Kesinti asla yukarı kabarcıklanmaz: her kademe bozulabilir ve tükenen
    denemeler `degraded=True` bir `Response` döndürür. Bu istisna yalnızca
    kayıtlı olmayan bir kademe adı istendiğinde atılır.
    """


@dataclass
class Response:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    tokens: int = 0
    degraded: bool = False


class Gateway:
    """Yedi kademeli, OpenAI uyumlu gateway istemcisi.

    Bozulmuş mod tasarımın parçası, kaza değil: **hiçbir kademe kesintisi bir
    koşuyu düşürmez.** CLAUDE.md şartnamenin dört anahtarının (`summary`,
    `events`, `risk`, `actions`) genişletilmiş katmanlar çökse bile
    üretilmesini istiyor; bu yüzden `ask()` kesintide istisna atmak yerine boş
    içerikli, `degraded=True` bir yanıt döndürür.
    """

    def __init__(self, store=None) -> None:
        self.store = store
        self._client = OpenAI(base_url=GATEWAY_BASE_URL,
                              api_key=GATEWAY_API_KEY,
                              timeout=GATEWAY_TIMEOUT_S)
        self._injected: set[str] = set()
        self._broken: set[str] = set()

    def inject_failure(self, tiers: set[str]) -> None:
        """Demo için kesinti enjekte eder; önceki enjeksiyonun yerine geçer.

        Kaydedilmiş bozulma da temizlenir — yoksa bir önceki demodan kalan
        bayat kademe adı yeni enjeksiyonun kapsamını sessizce genişletir.
        """
        self._injected = set(tiers)
        self._broken.clear()

    def is_degraded(self, tier: str | None = None) -> bool:
        """Kademe verilirse o kademe, verilmezse herhangi bir kademe bozuk mu.

        Kademe başına olması şart: rerank'ın beklenen 400'ü global bir bayrağı
        latch'lerse Görev 05'in döngüsü bunu 'görü katmanı çöktü' diye okur ve
        her pencereyi sonsuza dek erteler.
        """
        if tier is None:
            return bool(self._broken)
        return tier in self._broken

    def _attempt(self, tier: str, _call, attempts: int):
        last_error: Exception | None = None
        for i in range(attempts):
            if tier in self._injected:
                last_error = GatewayError(f"enjekte edilmiş hata: {tier}")
                break
            try:
                return _call()
            except Exception as exc:  # noqa: BLE001 — her taşıma hatası tekrar denenir
                last_error = exc
                if i < attempts - 1:
                    time.sleep(0.5 * (2 ** i))
        return last_error

    def ask(self, tier: str, messages: list[dict],
            schema: type[BaseModel] | None = None,
            tools: list[dict] | None = None,
            _retries: int | None = None) -> Response:
        if tier not in MODELS:
            raise GatewayError(f"bilinmeyen kademe: {tier}")
        model = MODELS[tier]
        t0 = time.monotonic()

        def _call():
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

        result = self._attempt(
            tier, _call, _retries if _retries is not None else GATEWAY_RETRIES)

        if isinstance(result, Exception):
            self._broken.add(tier)
            return Response(model=model, degraded=True,
                            latency_ms=int((time.monotonic() - t0) * 1000))

        msg = result.choices[0].message
        self._broken.discard(tier)
        return Response(
            content=msg.content or "",
            tool_calls=[t.model_dump() for t in (msg.tool_calls or [])],
            model=model,
            latency_ms=int((time.monotonic() - t0) * 1000),
            tokens=getattr(result.usage, "total_tokens", 0) or 0)

    def embed(self, text: str, _retries: int | None = None) -> list[float]:
        """Metnin gömme vektörü; kademe bozuksa boş liste.

        Boş vektör Görev 08'in hafıza aramasında 'sonuç yok' demek — gömme
        kademesinin kesintisi de bir koşuyu düşürmemeli.
        """
        result = self._attempt(
            "embed",
            lambda: self._client.embeddings.create(model=MODELS["embed"],
                                                   input=text),
            _retries if _retries is not None else GATEWAY_RETRIES)
        if isinstance(result, Exception):
            self._broken.add("embed")
            return []
        self._broken.discard("embed")
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
Beklenen: 18 passed — 12 test fonksiyonu, biri yedi kademe üzerinde
parametrize edilmiş.

### 6. Commit

```bash
git add gozcu/gateway.py gozcu/config.py tests/test_gateway.py \
        scripts/gen-litellm-config.py .env.example
git commit -m "feat: tiered gateway client with per-tier degradation"
```

## Doğrulama

```bash
uv run pytest tests/test_gateway.py -v
```
Beklenen: **18 passed** — ve testler çalışırken gateway'e gerçek istek
gitmemeli.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`ask()` kesintide istisna atmıyor.** Görev dosyasının ilk hâli yalnızca
  `vlm` / `fast` / `rerank` kademelerinin bozulmasına izin veriyor, gerisinde
  `GatewayError` fırlatıyordu. Artık **her kademe bozuluyor**: tükenen
  denemeler `content=""`, `tool_calls=[]`, `degraded=True` bir `Response`
  döndürüyor. Çağıran tarafın ihtiyacı olan şey `try/except GatewayError`
  **değil**, bir **boş içerik guard'ı**. Gerekçe CLAUDE.md'nin çıktı
  sözleşmesi: şartnamenin dört anahtarı genişletilmiş katmanlar çökse bile
  üretilmeli — `main` ya da `router` kesintisinde patlayan bir istemci bunu
  imkânsız kılıyordu.
- **`GatewayError` artık sadece "bilinmeyen kademe" demek.** Fırlarsa bir
  kademe adı yanlış yazılmış demektir; kesinti değil, programlama hatası. Onu
  kesinti işleme diye yakalayan kod ölü koddur.
- **`is_degraded(tier)` kademe başına.** Çıplak `is_degraded()` "herhangi bir
  kademe bozuk" demek ve konsol / KPI göstergesi için. Kademe başına olması
  şarttı: `rerank`'ın 400'ü **beklenen** davranış, global bir bayrağı
  latch'lerse Görev 05 bunu "görü katmanı çöktü" diye okuyup her pencereyi
  sonsuza dek erteliyordu. Görü kontrolü `is_degraded("vlm")` yazılacak.
- **`embed()` bozulmuşsa `[]` döndürüyor**, istisna atmıyor. Görev 08 boş
  vektörü "sonuç yok" diye okumalı — boş vektöre karşı kosinüs hesaplamamalı.
- **`rerank()` TAM bir permütasyon döndürüyor.** Reranker'lar talimat takip
  etmiyor: kısmi ya da tekrarlı indeks listeleri geliyor. Dönen sıra artık
  süzülüyor — modelin verdiği sıra önde, atlanan indeksler özgün sıralarıyla
  sona ekleniyor, tekrarlar düşürülüyor. Yani çağıran taraf aday listesinin
  tamamını güvenle indeksleyebilir; hiçbir aday sessizce düşmez ya da iki kez
  görünmez ([Görev 08](08-hafiza.md)).
- **`MODELS` yalnızca `gozcu/config.py`'da yaşıyor.**
  `scripts/gen-litellm-config.py` onu import ediyor; `pyproject.toml`
  `package = false` dediği için script başında repo kökünü `sys.path.insert`
  ile ekliyor, yoksa doğrudan koşturulduğunda `ModuleNotFoundError` alıyor.
- **Gerçek takma adlar artık `gozcu/config.py`'da** (24 Ağustos, `08305b5`).
  Önceki yedi ad tahmindi ve **hepsi yanlıştı**; düzeltme tek dosyalık bir
  düzenleme oldu, çünkü model kimlikleri yalnız `config.py`'da yaşıyor. Her ad
  `GOZCU_MODEL_*` ortam değişkeniyle hâlâ eziliyor.
- **Bilinmeyen bir model adı REDDEDİLMİYOR, sessizce `llm-fast`'e
  yönlendiriliyor.** 404 yok, 400 yok, uyarı yok: bir harf hatası hata değil,
  **makul görünen çöp** üretir — örneğin bir görü çağrısı bir metin modeline
  gider ve sistem "çalışıyor" gibi görünür. Bu görevin ilk hâlindeki "sessiz
  400" uyarısı fazla iyimsermiş; 400 en azından duyulur. Ayrıntı:
  [EVREN saha notları](../06-references/evren-gateway.md).
- **`ask()` Görev 04'te isteğe bağlı `max_tokens` / `temperature` kazandı.**
  Verilmezlerse istekte hiç görünmüyorlar, yani eski çağrı yerlerinin gövdesi
  değişmedi. Görü kademesinin token tavanına ihtiyacı vardı: üst sınır olmadan
  strict-JSON kod çözümü kaçak tekrara girip JSON'u hiç kapatmıyor.
- **Şema sertleştirmesi `ask()`'in içinde yaşıyor** (`gozcu/gateway.py`;
  `gozcu.agents.interpreter` yalnızca yeniden dışa veriyor). `Gateway.ask()`'e
  düz bir pydantic modeli ver; `strict_schema()`'i kimse elle çağırmıyor —
  "her çağıran önce şunu çağırsın" bir kuraldı ve üç görev dosyası tarafından
  unutuldu. Sonucu: `maxLength`, `minimum`/`maximum` ve `pattern` artık tele
  hiç çıkmıyor — yani **her ajan doğrulamadan ÖNCE kendi değerlerini
  temizlemek zorunda**. Ayrıca `ask()` şemalı istek bütün denemeleri
  tükettiğinde **şemasız** bir son deneme yapıyor; dolayısıyla dönen içerik
  iyi biçimli JSON olmayabilir ve ayrıştırıcılar bunu varsaymamalı. Kademe
  yalnızca bu yedek de başarısız olursa `degraded` sayılıyor.
- **`Gateway.__init__(store=…)` hâlâ kabul ediliyor ve kullanılmıyor.**
  `self.store` olarak duruyor; ileride telemetri deposu bağlanacaksa yer hazır,
  bugün hiçbir şey okumuyor.
