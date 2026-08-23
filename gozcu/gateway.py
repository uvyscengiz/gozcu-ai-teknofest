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
