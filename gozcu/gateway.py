import copy
import time
from dataclasses import dataclass, field
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from gozcu import trace
from gozcu.config import (GATEWAY_API_KEY, GATEWAY_BASE_URL, GATEWAY_RETRIES,
                          GATEWAY_TIMEOUT_S, MODELS)

Tier = Literal["router", "fast", "main", "vlm", "guard", "embed", "rerank"]


class GatewayError(RuntimeError):
    """Programlama hatası — kesinti değil.

    Kesinti asla yukarı kabarcıklanmaz: her kademe bozulabilir ve tükenen
    denemeler `degraded=True` bir `Response` döndürür. Bu istisna yalnızca
    kayıtlı olmayan bir kademe adı istendiğinde atılır.
    """


# Üst sınır olmadan strict-JSON şema kod çözümü dizi alanlarında kaçak tekrara
# giriyor: uydurma etiketleri `max_tokens` tükenene kadar yineliyor, JSON hiç
# kapanmıyor ve sonraki alanlara hiç ulaşılmıyor. Görev 04'te gerçek karelerde
# gözlendi; sınır şema sertleştiricisinde duruyor ki bir dizi eklendiği an
# korumasız kalmasın.
_MAX_ARRAY_ITEMS = 8

# Strict structured-output arka uçlarının yaygın olarak reddettiği doğrulama
# anahtarları. Hepsi pydantic modelinde kalır — doğrulama gücünden hiçbir şey
# kaybedilmiyor, sadece tele çıkmıyorlar. `maxItems` bilerek listede değil:
# yukarıdaki kaçak tekrar hatasına karşı tek koruma o.
_STRIPPED_KEYWORDS = ("maxLength", "minLength", "pattern", "format",
                      "minimum", "maximum", "exclusiveMinimum",
                      "exclusiveMaximum", "multipleOf")


def strict_schema(schema: dict) -> dict:
    """JSON şemasını OpenAI **strict** structured outputs'a uygun hâle getirir.

    `Gateway.ask()` bunu kendisi uyguluyor; çağıranın hatırlaması gerekmiyor.
    Ajan modülünde yaşarken "her çağıran önce bunu çağırsın" bir kuraldı ve üç
    görev dosyası tarafından unutuldu — sertleştirme gateway'in kendi işi.

    Strict mod HER alanın `required` içinde olmasını ister; pydantic ise
    varsayılanı olan alanı listeden düşürür. Yani düz `model_json_schema()`
    gerçek gateway'de 400 üretiyor, denemeler tükeniyor, kademe `degraded`
    oluyor ve ajan HER pencere için boş dönüyor. Sistem çalışıyor görünüp
    hiçbir şey üretmiyor.

    `_STRIPPED_KEYWORDS` içindeki doğrulama anahtarları da sökülüyor; sınırlar
    pydantic modelinde kalır, kesme/kırpma Python tarafında yapılır.

    Girdi kopyalanır; çağıranın sözlüğü değişmez. İki kez uygulanması zararsız.
    """
    hardened = copy.deepcopy(schema)
    _harden(hardened)
    return hardened


def _harden(node) -> None:
    if isinstance(node, dict):
        for keyword in _STRIPPED_KEYWORDS:
            node.pop(keyword, None)
        if node.get("type") == "array":
            node.setdefault("maxItems", _MAX_ARRAY_ITEMS)
        if "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])
        for value in list(node.values()):
            _harden(value)
    elif isinstance(node, list):
        for value in node:
            _harden(value)


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

    def _attempt(self, tier: str, _call, attempts: int, label: str = ""):
        """Her deneme AYRI kaydediliyor.

        Sessizliğin kaynağı buydu: `GATEWAY_TIMEOUT_S` 1800 s ve bu döngü onu
        `attempts` kez deniyor. Tek bir asılı çağrı, hiçbir satır yazmadan
        saatlerce bekleyebiliyordu — ekranda "takıldı"dan ayırt edilemez.
        Artık her deneme kendi `step()`'i, yani kalp atışı da var.
        """
        last_error: Exception | None = None
        for i in range(attempts):
            if tier in self._injected:
                last_error = GatewayError(f"enjekte edilmiş hata: {tier}")
                trace.event(f"{tier}.enjekte", "kesinti enjekte edildi")
                break
            try:
                # Ad DIŞ adımdan farklı olmalı: ikisi de `vlm.ask` olsaydı
                # süre toplayan bir okuma her çağrıyı İKİ kez sayardı — bir
                # kez oldu ve `vlm.ask 167 s` diye okundu, gerçeği 83,6 s'ti.
                with trace.step(f"{tier}.deneme",
                                f"{i + 1}/{attempts} "
                                f"zaman aşımı={GATEWAY_TIMEOUT_S:.0f}s"):
                    return _call()
            except Exception as exc:  # noqa: BLE001 — her taşıma hatası tekrar denenir
                last_error = exc
                if i < attempts - 1:
                    backoff = 0.5 * (2 ** i)
                    trace.event(f"{tier}.bekle", f"{backoff:.1f}s sonra yeniden")
                    time.sleep(backoff)
        return last_error

    def ask(self, tier: str, messages: list[dict],
            schema: type[BaseModel] | None = None,
            tools: list[dict] | None = None,
            max_tokens: int | None = None,
            temperature: float | None = None,
            _retries: int | None = None) -> Response:
        """`max_tokens` / `temperature` verilmezse istekte hiç görünmez.

        Görü kademesinin bir token tavanına ihtiyacı var: üst sınır olmadan
        strict-JSON şema kod çözümü kaçak tekrara girip `max_tokens` tükenene
        kadar yineliyor ve JSON hiç kapanmıyor. Bunları geçirecek bir yol
        yoktu; varsayılanlar `None` olduğu için mevcut çağrı yerlerinin
        gövdesi bir bit bile değişmiyor.

        Verilen şema `strict_schema()`'den geçirilir — çağıranın hatırlaması
        gerekmez. Şemalı istek bütün denemeleri tüketirse **şemasız** son bir
        deneme yapılır: organizasyonun gateway'ini kimse görmedi, şema
        desteğinin ne kadar katı olduğunu bilmiyoruz ve reddedilen bir şema
        kesintiden ayırt edilemeyip kademeyi sonsuza dek `degraded` bırakırdı.
        Prompt'la istenen JSON'a düşmek tam kaybı kurtarılabilir bir hâle
        çeviriyor; kademe yalnızca yedek de başarısız olursa bozuk sayılır.
        """
        if tier not in MODELS:
            raise GatewayError(f"bilinmeyen kademe: {tier}")
        model = MODELS[tier]
        t0 = time.monotonic()

        def _call(with_schema: bool = True):
            request: dict = {"model": model, "messages": messages}
            if schema is not None and with_schema:
                request["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__,
                                    "schema": strict_schema(
                                        schema.model_json_schema()),
                                    "strict": True}}
            if tools:
                request["tools"] = tools
            if max_tokens is not None:
                request["max_tokens"] = max_tokens
            if temperature is not None:
                request["temperature"] = temperature
            return self._client.chat.completions.create(**request)

        # Yükün boyutu kayda giriyor: görü kademesine giden klip base64
        # olarak gömülüyor ve megabaytlarca olabiliyor — yavaşlığın en olası
        # tek sebebi bu ve sayı görünmeden tahmin edilemiyor.
        payload = sum(len(str(m.get("content", ""))) for m in messages)
        attempts = _retries if _retries is not None else GATEWAY_RETRIES
        with trace.step(f"{tier}.ask",
                        f"model={model} yük={payload / 1e6:.2f}MB "
                        f"şema={'var' if schema else 'yok'}"):
            result = self._attempt(tier, _call, attempts, label="ask")

            if isinstance(result, Exception) and schema is not None:
                trace.event(f"{tier}.yedek", "şemalı denemeler bitti, şemasız")
                result = self._attempt(tier, lambda: _call(with_schema=False),
                                       1, label="ask-şemasız")

            if isinstance(result, Exception):
                self._broken.add(tier)
                trace.event(f"{tier}.BOZUK",
                            f"{type(result).__name__}: {result}")
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
        with trace.step("embed.ask", f"{len(text)} karakter"):
            result = self._attempt(
                "embed",
                lambda: self._client.embeddings.create(model=MODELS["embed"],
                                                       input=text),
                _retries if _retries is not None else GATEWAY_RETRIES,
                label="embed")
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
            # Dönen sıra her adayı TAM OLARAK BİR KEZ içermeli. Model kısmi
            # ya da tekrarlı cevap veriyor (reranker'lar talimat takip
            # etmiyor); süzülmezse aday sessizce düşer ya da iki kez görünür.
            # Modelin verdiği sıra korunur, geri kalanlar özgün sıralarıyla
            # sona eklenir.
            seen: dict[int, None] = {}
            for part in response.content.replace(" ", "").split(","):
                if part.isdigit() and int(part) < len(candidates):
                    seen.setdefault(int(part), None)
            if not seen:
                return fallback
            return list(seen) + [i for i in fallback if i not in seen]
        except Exception:  # noqa: BLE001
            return fallback
