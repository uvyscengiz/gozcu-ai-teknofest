"""Sentezleyici — kare bağımsızlığının kırıldığı yer.

Bir pencerenin dağınık sinyalleri ve o pencerenin görsel yorumu tek bir
`Episode` kaydında birleşiyor: hangi fazda, kimler var, Türkçe özeti ne, ön
riski ne. Şartnamenin "sahne bütünlüğü, zamansal ilişkiler ve olay akışı"
maddesi ile "başlangıç / gelişim / sonuç" ayrımı burada karşılanıyor.

Epizot yaşam döngüsünün üç kararı üç ayrı davranış:

- `open_episode`   → **koşulsuz** yeni epizot açar
- `update_episode` → `store.open_episode()` üzerine kaynaşır (açık epizot
  yoksa yeni bir tane açar — bkz. `synthesize` içindeki asimetri notu)
- `close_episode`  → açık epizodu kapatır; **açık epizot yoksa hiçbir şey
  yapmaz**

İlk ikisinin koşulsuzluğu tesadüf değil: tek açık epizot değişmezinin bekçisi
`DecisionLoop._resolve()` ve o, açık epizot varken gelen `open_episode`'u
`update_episode`'a indirerek çalışıyor. Sentezleyici bu iş bölümünü bozarsa
değişmez de bozulur (Görev 05 notu).
"""

import json

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.router import mmss
from gozcu.models import (MAX_EPISODE_BEATS, Episode, EventBeat, Handoff,
                          Interpretation, Observation, RiskLevel)

# `Episode.summary_tr` ile aynı sınır. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani model bu sınırı aşabilir;
# kesme doğrulamadan ÖNCE Python tarafında yapılıyor.
MAX_SUMMARY = 600

PHASES = ("onset", "development", "outcome")

SYSTEM_PROMPT = """Sen bir fabrika kontrol odasının kâtibisin. Sana bir zaman
aralığındaki gözlemler ve görsel yorumlar verilir. Bunları TEK BİR OLAY
halinde birleştir.

Kurallar:
- Olayın hangi fazda olduğunu belirt — tam olarak bu değerlerden biri:
  onset (olayın başlangıcı), development (olayın gelişimi), outcome (olayın
  sonucu)
- Özet Türkçe, kısa cümlelerle, saha terminolojisiyle yazılır
- Görmediğin bir şeyi yazma. Emin değilsen "olası" de.
- Ön riski şu dördünden biri olarak ver: Düşük, Orta, Yüksek, Kritik

Sadece JSON döndür."""

# Yedek özetler. Üçü bilerek farklı: denetim kaydı ve konsol "kademe sustu",
# "kademe boş yanıt döndü" ve "yanıt okunamadı" ayrımını görebilmeli — üçü
# farklı arızalar ve farklı müdahale gerektiriyor. Aynı metni paylaşsalardı
# boş içerik guard'ı da sessizce ölü koda dönerdi: `json.loads("")` zaten
# istisna atıp okunamayan dala düşüyor ve fark hiçbir yerde görünmüyordu.
DEGRADED_SUMMARY = "Sentez katmanı yanıt vermiyor; ham gözlemler kayıtlı."
EMPTY_SUMMARY = "Sentez katmanı boş yanıt döndürdü; ham gözlemler kayıtlı."
UNREADABLE_SUMMARY = "Sentez üretilemedi; ham gözlemler kayıtlı."
FALLBACK_PHASE = "development"
FALLBACK_RISK: RiskLevel = "Orta"

#: Yedek özetli bir epizodun devam satırı. Arıza metni ("Sentez üretilemedi…")
#: bir kez prompt'a olay tarifi olarak girdi ve model onu fabrikada duran bir
#: "sentez hattı"na çevirdi (26 Ağu canlı koşu). Arıza metni bir olay tarifi
#: DEĞİLDİR ve modele öyle anlatılmaz.
#:
#: "sentezi arızalandı" ibaresi de kaldırıldı: yerine konan "Sentez kademesi"
#: notu aynı koşuda model tarafından bir bölge adı sanılıp dört saha
#: aracına parametre olarak geçirildi (bkz. `supervisor.NO_DESCRIPTION_NOTE`).
#: Bu satır artık hiçbir iç katman adı taşımıyor.
FALLBACK_CONTINUATION = ("DEVAM EDEN OLAY: (tarif üretilemedi — önceki "
                         "pencere için iç arıza oluştu; olayı aşağıdaki "
                         "gözlemlerden yeniden kur)")


class _SynthesisResponse(BaseModel):
    """Hızlı kademeden beklenen çıktı.

    `phase` bilerek `str` — `Literal` olsaydı modelin uydurduğu bir faz bütün
    kaydı doğrulama hatasına düşürürdü; burada okunup `PHASES`'e çekiliyor.
    Uzunluk sınırı modelde kalır, şemadan çıkar (bkz. `strict_schema`).
    """

    model_config = ConfigDict(extra="forbid")

    phase: str
    summary_tr: str = Field(max_length=MAX_SUMMARY)
    participants: list[str] = Field(default_factory=list)
    preliminary_risk: RiskLevel

    #: **Şemanın DIŞINDA** — `PrivateAttr` `model_json_schema()`'e girmiyor.
    #: Sıradan bir alan olsaydı modele "bunu da doldur" diye giderdi ve
    #: uydurulmuş bir kaynak etiketi, korumak istediğimiz ayrımı yok ederdi.
    _source: str = PrivateAttr(default="model")

    @property
    def summary_source(self) -> str:
        """Özet modelden mi geldi (`"model"`) yoksa bir arıza metni mi
        (`"fallback"`)."""
        return self._source


def _fallback(summary_tr: str) -> _SynthesisResponse:
    """Sentez okunamadığında pencere yine de bir epizota dönüşür.

    Boş dönmek pencereyi tamamen kaybetmek demek: ham gözlemler depoda kalır
    ama şartnamenin `events[]` listesinde o an hiç yaşanmamış görünür.
    """
    response = _SynthesisResponse(phase=FALLBACK_PHASE, summary_tr=summary_tr,
                                  preliminary_risk=FALLBACK_RISK)
    response._source = "fallback"
    return response


def _digest(window: list[Observation],
            interpretation: Interpretation | None,
            previous: Episode | None) -> str:
    """Modele gidecek düz metin — gözlem başına bir satır.

    Görsel yorum kendi zaman damgasıyla ekleniyor: `Interpretation.observation_ts`
    pencerenin ORTA damgası, `window[0].ts` değil (Görev 04). Devam eden bir
    olay varsa özeti en başa konuyor ki model her pencereyi sıfırdan
    anlatmasın — kaynaşmanın süreklilik tarafı bu satıra bağlı.
    """
    lines = [f"{mmss(observation.ts)} "
             f"kişi={observation.signals.person_count} "
             f"hızlar={observation.signals.velocities or '-'}"
             for observation in window]
    if interpretation is not None:
        lines.append(f"{mmss(interpretation.observation_ts)} GÖRSEL: "
                     f"{interpretation.description}")
    if previous is not None:
        line = (FALLBACK_CONTINUATION
                if previous.summary_source == "fallback"
                else f"DEVAM EDEN OLAY: {previous.summary_tr}")
        lines.insert(0, line)
    return "\n".join(lines)


def _absolute_beats(interpretation: Interpretation | None,
                    window_start: float) -> list[EventBeat]:
    """Yorumun klip içi anlarını MUTLAK video zamanına çevirir.

    Çevirinin tek yeri burası. `window_start` pencerenin İLK damgası —
    `Interpretation.observation_ts` değil: o pencerenin ORTA damgası (Görev
    04) ve klip pencerenin başından kesiliyor. İkisi karışırsa her an yarım
    pencere kayar.
    """
    if interpretation is None:
        return []
    return [EventBeat(ts=window_start + beat.offset_s, text=beat.text)
            for beat in interpretation.beats]


def _merge_beats(existing: list[EventBeat],
                 fresh: list[EventBeat]) -> list[EventBeat]:
    """Devam eden bir epizoda yeni anları EKLER, üzerine yazmaz.

    Üzerine yazmak tam olarak düzeltmeye çalıştığımız hatayı geri getirir:
    olayın başladığı an, bir sonraki pencere epizodu güncellediğinde kaybolur
    ve teslim edilen `events[]` yine tek bir ana çöker.

    Eklemenin bedeli sınırsız büyüme; iki fren var. Aynı an iki kez
    yazılmıyor (kaynaşma aynı pencereyi tekrar okuyabiliyor) ve liste
    `MAX_EPISODE_BEATS`'te duruyor — baş+son korunarak: yalnız-baş kuralı
    ölçülen arızaya yol açtı (bkz. taşma dalı), bu yüzden tavan artık hem
    olayın nasıl başladığını hem de en güncel gelişmeyi garanti ediyor.
    """
    merged = list(existing)
    seen = {(round(beat.ts, 1), beat.text) for beat in merged}
    for beat in fresh:
        key = (round(beat.ts, 1), beat.text)
        if key in seen:
            continue
        seen.add(key)
        merged.append(beat)
    merged.sort(key=lambda beat: beat.ts)
    if len(merged) <= MAX_EPISODE_BEATS:
        return merged
    # Baş + son (spec §4): baş olayın nasıl başladığını, son ise epizot ne
    # kadar uzarsa uzasın EN GÜNCEL gelişmenin listede olmasını garanti eder.
    # Yalnız-baş kuralının ölçülen arızası: 00:00'da açılan epizotta tavan
    # park hâlindeki kamyonla doldu ve kaza `events[]`ten düştü (26 Ağu).
    # İki dilim çakışamaz: kural yalnız len > MAX'ta tetikleniyor.
    half = MAX_EPISODE_BEATS // 2
    return merged[:half] + merged[-half:]


def _parse(content: str) -> _SynthesisResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

    İçeriğin iyi biçimli JSON olduğu varsayılmıyor: `ask()` şemalı istek
    tükendiğinde şemasız bir son deneme yapıyor (Görev 03), dolayısıyla geri
    düz metin de gelebilir.

    Kesme doğrulamadan ÖNCE: şemada `maxLength` olmadığı için model 600'ü
    aşabilir ve ham hâliyle pydantic'e verilirse gerçek bir epizot sentezi
    kabuğa çökerdi. Kesme mantığı yorumlayıcıdan geliyor — sarkan yarım
    kelimeyi de buduyor.
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    summary = data.get("summary_tr")
    if isinstance(summary, str):
        data["summary_tr"] = _sanitize_text(summary, MAX_SUMMARY)

    try:
        parsed = _SynthesisResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None

    if parsed.phase not in PHASES:
        parsed.phase = FALLBACK_PHASE
    return parsed


def _ask_synthesis(gw, window: list[Observation],
                   interpretation: Interpretation | None,
                   previous: Episode | None) -> _SynthesisResponse:
    """Hızlı kademeye sorar; okunamayan her şey yedek özete düşer.

    İki guard da açık. Bozulmuş yanıt bir gün boş olmayan bir gövdeyle
    gelirse (ör. önbellekten dönen bayat sentez) `degraded` kontrolü olmadan
    o bayat özet canlı sentez gibi kaydedilir; boş içerik ise `json.loads("")`
    tesadüfen istisna attığı için "okunamadı" diye raporlanırdı — kademe
    aslında hiçbir şey söylememişken.
    """
    response = gw.ask("fast", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _digest(window, interpretation, previous)},
    ], schema=_SynthesisResponse)

    if response.degraded:
        return _fallback(DEGRADED_SUMMARY)
    if not (response.content or "").strip():
        return _fallback(EMPTY_SUMMARY)

    parsed = _parse(response.content)
    return parsed if parsed is not None else _fallback(UNREADABLE_SUMMARY)


def synthesize(gw, store, window: list[Observation],
               interpretation: Interpretation | None,
               decision: str, on_close=None) -> Episode | None:
    """Gözlem penceresini bir `Episode`'a dönüştürür.

    `decision == "open_episode"`   → koşulsuz yeni epizot
    `decision == "update_episode"` → açık epizota kaynaşır
    `decision == "close_episode"`  → açık epizodu kapatır ve varsa
    `on_close(episode)` çağrılır (gömme geri çağrısı, Görev 08).

    Açık epizot yokken gelen karar iki farklı şey demek — **iki dal bilerek
    ayrı:**

    - `update_episode`: döngü depo boşken de kaynaşma yönlendirebiliyor
      (Görev 06 notu: prompt yasaklıyor ama hiçbir şey düzeltmiyor). Kaynaşacak
      bir şey yoksa pencereyi kaybetmektense epizot AÇILIR.
    - `close_episode`: kapanacak bir şey yok. Burada epizot üretmek tam olarak
      **yaşanmamış bir olay uydurmak** olur — üstelik `state="closed"` ile,
      yani doğrudan şartnamenin `events[]` listesine ve Görev 08'in gömme
      hafızasına. Üst üste iki kapanış kararı (`_resolve()` yalnızca
      `open_episode`'u indiriyor) tam olarak bunu üretiyordu. Bu dal
      NO-OP: ne epizot, ne devir teslim, ne geri çağrı, ne de model çağrısı.

    İki dalı "sadeleştirip" birleştirmek hayalet epizot hatasını geri getirir.
    """
    if not window:
        return None

    open_episode = store.open_episode() if decision != "open_episode" else None
    if decision == "close_episode" and open_episode is None:
        return None

    synthesis = _ask_synthesis(gw, window, interpretation, open_episode)
    closing = decision == "close_episode"
    end_ts = window[-1].ts

    # Anlar epizoda MUTLAK video zamanıyla giriyor; `start_ts` pencerenin
    # sınırı olarak kalıyor (bkz. `Episode.event_ts`).
    beats = _absolute_beats(interpretation, window[0].ts)

    if open_episode is None:
        episode = Episode(start_ts=window[0].ts, end_ts=end_ts,
                          phase=synthesis.phase,
                          summary_tr=synthesis.summary_tr,
                          participants=synthesis.participants,
                          preliminary_risk=synthesis.preliminary_risk,
                          state="open", beats=beats,
                          summary_source=synthesis.summary_source)
        episode.id = store.create_episode(episode)
    else:
        fields = {"end_ts": end_ts, "summary_tr": synthesis.summary_tr,
                  "participants": synthesis.participants,
                  "preliminary_risk": synthesis.preliminary_risk,
                  "beats": _merge_beats(open_episode.beats, beats),
                  "summary_source": synthesis.summary_source,
                  "phase": "outcome" if closing else synthesis.phase}
        # Yedek, model kaydını EZMEZ (spec §1): son penceresi arızalanan bir
        # epizot, ömrü boyunca taşıdığı model özetini kapanış anında bir arıza
        # metnine kaybederdi — ve gömme koruması onu arşivden tamamen düşürürdü.
        # participants/preliminary_risk de korunuyor: yedek yanıt onları
        # varsayılandan ([], "Orta") doldurur, yani ezmek aynı bilgiyi siler.
        if (synthesis.summary_source == "fallback"
                and open_episode.summary_source == "model"):
            for key in ("summary_tr", "summary_source", "participants",
                        "preliminary_risk"):
                fields.pop(key, None)
        if closing:
            fields["state"] = "closed"
        store.update_episode(open_episode.id, **fields)
        episode = next(e for e in store.episodes() if e.id == open_episode.id)

    # Devir teslimin saati GEÇERLİ pencerenin ilk damgası, epizodun `start_ts`'i
    # değil: uzun bir olayda ikincisi defterin saatini olayın başında dondurur
    # ve zaman çizelgesi (Görev 15/16) devirleri yanlış ana yazar.
    store.save_handoff(Handoff(ts=window[0].ts,
                               source_agent="synthesizer",
                               target_agent="risk_analyst",
                               reason=f"{decision} → episode {episode.id}",
                               confidence=0.8,
                               payload_ref=f"episode:{episode.id}"))

    if closing and on_close is not None:
        on_close(episode)

    return episode
