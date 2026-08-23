# Görev 14 — Nöbetçi süpervizör (`gozcu/agents/supervisor.py`)

> ## ✅ TAMAMLANDI — 24 Ağustos 2026, `463a74c`
>
> **Nöbetçi süpervizör indi.** `gozcu/agents/supervisor.py` var;
> `tests/test_supervisor.py` 39 test ile yeşil. Bu dosyayı yeniden uygulama —
> aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **promptun araç kataloğu ŞEMADAN TÜRETİLİYOR** — elle yazılan bir araç adı bir
> kez ayrıştı ve düzeltme kaskadı hiç tetiklenmedi; **aynı anda YALNIZ BİR onay
> yuvası var** — bekleyen bir onay dururken ikinci kapılı aksiyon reddediliyor ve
> deftere hiç düşmüyor; ve **diyalog satırları da düzeltmeler de VİDEO zamanını
> taşıyor**, `0.0` değil.

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~4 saat
**Bağımlılık:** [08](08-hafiza.md), [10](10-saha-araclari.md), [11](11-risk-analisti.md), [12](12-raportor.md), [13](13-guard.md)
**Puanın %20'si burada yaşıyor — projedeki en yüksek getirili tek dosya**

## Bağlam

Operatörün konuştuğu ajan. Şartnamenin "Otonomi ve Zeka" kalemi (%20) kelimesi
kelimesine şunları istiyor ve dördü de bu dosyada karşılanıyor:

| Şartname kriteri | Bu dosyada nerede |
|---|---|
| *"diyalog sırasında inisiyatif alma"* | `escalate()` — kimse sormadan operatöre seslenir |
| *"doğru soruları sorma"* | Belirsizlik notu — kameradan göremediğini sorar |
| *"beklenmedik durumlara (bağlam değişimi) tepki"* | `talk()` açık olayı isteme ekler |
| *"doğal ve insansı akış"* | Sistem promptu + Türkçe üslup |

Süpervizörün kendi araçları (`search_timeline`, `correct_observation`,
`request_risk_assessment`, `generate_root_cause_report`) yedi saha aracının **yanına**
ekleniyor — böylece iki tür arasında seçim yapmak model için tek bir karar
oluyor ve *"dinamik araç seçimi"* gerçekten gözlenebiliyor.

### Üç ince nokta

**Düzeltme kaskadı.** Operatör bir şeyi düzelttiğinde `duzeltme` tablosuna
yazmak yetmiyor — epizot özeti de güncellenmeli ve risk analizi yeniden
koşmalı. Aksi halde "düzeltme her yere yayılır" iddiası prompt umuduna kalır ve
`correction_propagation` KPI'ı %0 okur.

**Onay akışı.** Operatör bir aksiyonu onayladığında aracı yeniden `call_tool` ile
çağırırsan **yeni bir bekleyen kayıt** doğar ve onay çubuğu hiç kapanmaz.
`approval="approved"` geçirmek ve orijinal satırı `set_action_approval` ile
güncellemek zorunlu. [Görev 10](10-saha-araclari.md) (`198801e`) bu ikinci
çağrıyı artık **gerçek** kılıyor: onaylı çağrı hattı gerçekten durduruyor ve
`state: "halted"` dönüyor (`awaiting_approval` anahtarını hiç taşımıyor).
Modelin kendi gönderdiği `approved` bayrağı **yok sayılıyor** — onayın tek
kaynağı defter, yani ajan kendi hat durdurmasını onaylayamıyor.

**Belirsizlik notu.** Beat 2 — *"yerdeki kişi hareket ediyor mu, göremiyorum"* —
promptta bir cümleye bırakılırsa güvenilir tetiklenmez. Sinyallerden gerçek bir
belirsizlik notu üretip yükseltme mesajına koyuyoruz: kadraj dışına çıkan track
varsa ajan neyi göremediğini biliyor ve sorusu kendiliğinden geliyor.

### Depodan devraldığın boşluk (Görev 02)

`pending_approval()` tam olarak bir bekleyen kayıt bulmayı varsayıyor; depoda
bunu zorlayan hiçbir şey yok. `ActionRecord.approval` düz bir alan — aynı anda
birden çok satır `"pending"` durumunda durabilir, süpervizör bunu ya baştan
engellemeli ya da düzgün ele almalı. Ayrıca `set_action_approval` bilinmeyen bir
`action_id`'de çıplak `TypeError` atıyor (`fetchone()[0]`, `None` kontrolü yok).

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/ -v      # 08, 09, 11, 12, 13 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/tools/registry.py
TOOL_SCHEMAS: list[dict]
NEEDS_APPROVAL: set[str] = {"halt_production_line"}
call_tool(store, tool_name, params, actor="agent", approval=None, ts=0.0) -> dict
  # ts: VİDEONUN zamanı, duvar saati değil. Geçilmezse defter sıfırla dolar.

# gozcu/memory.py
search_timeline(gw, store, query, top_k=5, exclude_id=None) -> list[Episode]
  # exclude_id: sorgu metni bir epizottan geliyorsa o epizodu ele. Nöbetçinin
  # sorgusu operatörün serbest metni olduğu için burada gerekmiyor.

# gozcu/agents/risk.py
assess_risk(gw, store, episode: Episode) -> RiskAssessment

# gozcu/agents/reporter.py
generate_root_cause_report(gw, store) -> RootCauseReport

# gozcu/guard.py
screen(gw, text: str, critical: bool = False) -> str
screen_text(gw, text: str, critical: bool = False) -> Screening
#   Screening(text, verdict, note); .screened yalnız gerçek bir hükümde True

# gozcu/store.py
Store.save_dialogue, Store.save_correction, Store.update_episode,
Store.open_episode, Store.episodes, Store.actions, Store.set_action_approval

# gozcu/agents/router.py
mmss(ts: float) -> str
```

> **Görev 10 bağlama uyarısı.** `call_tool`'un `ts`'i **videonun zamanı.**
> Kararlar olay anında veriliyor; defterdeki damga da o an olmalı. Süpervizör
> hangi videoyu, hangi saniyede konuştuğunu bilen taraf: `escalate()` epizodun
> `start_ts`'ini tutuyor ve araç çağrıları onunla yazılıyor. Geçilmezse
> [Görev 17](17-cikti-sozlesmesi.md)'nin `detail.action_ledger`'ı tamamen
> `0.0` damgalarla teslim edilir.

> **Görev 11 indi (`dd803fd`) — `proposed_actions` yalnızca ÖNERİDİR.** Risk
> analisti salt okur: kendisine sadece `READ_TOOLS` şemaları sunuluyor ve
> başka bir araç çağrısı yürütme anında reddediliyor. Yani `RiskAssessment`
> sana ulaştığında **hiçbir müdahale aracı çalışmamıştır** — hat durmamış,
> sağlık ekibi sevk edilmemiştir. Her yazma aracının yürütülmesi ve onay kapısı
> bu görevin işi; öneriyi bir olmuş bitmiş iş sanma.

> **Görev 12 indi (`a8cf363`) — defter satırları kök neden raporuna OLDUĞU
> GİBİ giriyor, `approval` durumuyla birlikte.** Raportör `store.actions()`'ı
> budamadan yazıyor: onaylanmış bir `halt_production_line` çağrısı raporda
> `[approved]` damgasıyla kanıt olarak görünüyor; onay bekleyen ya da reddedilen
> bir çağrı da kendi durumuyla. Yani iki fazlı onay hikâyesi raporun kendisinden
> okunabiliyor — ama yalnızca `call_tool` üzerinden geçen çağrılar için.
> Deftere düşmeyen bir onay raporda hiç olmamış sayılır.

> **Görev 13 indi (`ec0eca6`) — `screen()` imzası DEĞİŞMEDİ, ama yanında bir
> kardeşi var.** Gösterilecek metinden başka bir şey istemiyorsan `screen()`
> aynen kullanılabilir. Hükmün kendisi diyaloğa ya da denetim kaydına girecekse
> `screen_text()` kullan: `Screening(text, verdict, note)` döndürüyor ve
> `.screened` yalnız model gerçekten bir hüküm verdiğinde `True` — kesintide ve
> okunamayan hükümde metin geçer ama "temiz" sayılmaz. Kritik uyarı hâlâ modele
> hiç gitmiyor.
>
> **Tuzak (kapandı, `463a74c`) — geç import edilen denetim yamalanamıyordu.**
> İlk taslakta gövde `screen`'i `_turn_loop` içinde **geç import** ediyordu, yani
> modül seviyesinde `screen` diye bir öznitelik hiç oluşmuyordu;
> `unittest.mock.patch` var olmayan özniteliği yamalamayı reddeder ve test
> `AttributeError` ile düşerdi. Teslim edilen gövde `screen_text`'i dosyanın
> **tepesinden** import ediyor ve testler
> `patch("gozcu.agents.supervisor.screen_text")` hedefini kullanıyor.

**Bozulmuş yanıt guard'ı (Görev 03).** `gw.ask()` kesintide istisna atmıyor;
`content=""`, `tool_calls=[]` olan `degraded=True` bir `Response` dönüyor.
Bozulmuş yanıt hiçbir şeye ayrışmaz — `tool_calls[0]` erişimi ve JSON
ayrıştırma boş yanıta karşı korunmalı, yoksa operatöre boş mesaj gider ya da
`IndexError` alırsın. `except GatewayError` bunu yakalamaz.

## Ne yapacaksın

```python
Supervisor(gw, store)
  .ts: float                                # videonun anı; diyalog ve
                                            # düzeltmeler bununla damgalanır
  .history: list[dict]                      # model mesaj geçmişi
  .last_screening: Screening | None         # son denetim hükmü
  .escalate(episode: Episode) -> str        # proaktif açılış — beat 1
  .talk(operator_text: str) -> str          # bir diyalog turu
  .pending_approval() -> ActionRecord | None  # en fazla bir tane olabilir
  .approve(action_id: int, approved: bool) -> dict
      # {"state": "approved"|"rejected"|"unknown_action"|"not_pending",
      #  "action_id": int, "result": {...}} — asla istisna atmaz

uncertainty_note(signals: Signals) -> str   # ölçülemeyeni operatöre söyler
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_supervisor.py`

```python
"""Görev 14 — Nöbetçi süpervizör.

Puanın %20'si burada, ve bu dosyanın testleri üç iddiayı koruyor:

**Prompt ile şema ayrışamaz.** Prompt bir araç adı sayıyorsa o ad şemada
gerçekten var olmalı — aksi hâlde model var olmayan bir aracı çağırır, kaskad
hiç tetiklenmez ve KPI sıfır okur. Bir test bunu yapısal olarak kilitliyor.

**Aynı anda tek bir onay bekleyebilir.** İkinci bir bekleyen satır, birincisini
kalıcı olarak görünmez kılıyordu. Süpervizör ikinci kapılı aksiyonu reddediyor
ve operatöre nedenini söylüyor.

**Kesinti operatöre boş mesaj olarak gitmez.** Bozulmuş yanıt, boş yanıt ve
sonuçlanmayan araç turu üç ayrı Türkçe metne düşüyor.

`gw.ask.call_args_list` üzerinden prompt içeriği doğrulanamaz: süpervizör
`self.history` listesini canlı olarak büyütüyor ve `call_args` o listeye
**referans** tutuyor. Bu yüzden `_setup` her çağrıda mesajların bir kopyasını
donduruyor ve testler `gw.prompts` üzerinden bakıyor.
"""

import json
import re
from unittest.mock import Mock, patch

from gozcu.agents.reporter import RootCauseReport
from gozcu.agents.supervisor import (ALL_TOOL_SCHEMAS, AUDIT_PREFIX,
                                     CORRECT_OBSERVATION, DEGRADED_REPLY,
                                     EMPTY_REPLY, MAX_TURNS, SYSTEM_PROMPT,
                                     UNFINISHED_REPLY, Supervisor,
                                     uncertainty_note)
from gozcu.gateway import Response
from gozcu.guard import (CLEAN_NOTE, FLAGGED_NOTE, NEUTRAL_NOTICE,
                         UNREADABLE_NOTE, Screening)
from gozcu.models import (Episode, Observation, RiskAssessment,
                          Signals)
from gozcu.store import Store

EPISODE_TS = 192.0


def _tool(name, params):
    return Response(tool_calls=[{"id": "c1", "type": "function",
                                 "function": {"name": name,
                                              "arguments": json.dumps(params)}}])


def _setup(responses):
    """Sahte gateway + tek açık epizot taşıyan depo.

    `gw.prompts` her çağrıdaki mesaj listesinin **dondurulmuş** kopyası:
    `call_args_list` canlı `history` listesine referans tuttuğu için doğrudan
    ondan okumak turun sonundaki hâli gösterir, o anki hâli değil.
    """
    gw = Mock()
    prompts: list[list[dict]] = []
    stream = iter(responses)

    def _ask(_tier, messages, **_kwargs):
        prompts.append([dict(m) for m in messages])
        return next(stream)

    gw.ask.side_effect = _ask
    gw.prompts = prompts

    store = Store(":memory:")
    e = Episode(start_ts=EPISODE_TS, phase="development",
                summary_tr="istif aracı devrildi, yerde hareketsiz kişi",
                preliminary_risk="Kritik")
    e.id = store.create_episode(e)
    return gw, store, e


def _risk(e):
    return RiskAssessment(episode_id=e.id, level="Kritik",
                          rationale_tr="g", preventable=True)


def _halt(reason="devrilme"):
    return _tool("halt_production_line", {"line_id": "B", "rationale": reason})


def _screening(text="metin"):
    """Yamalanmış `screen_text` için gerçek bir dönüş değeri.

    `MagicMock` `DialogueTurn(text=...)` doğrulamasından geçmez (`text: str`),
    yani `return_value` verilmeyen bir yama testi kodun kendisiyle ilgisi
    olmayan bir doğrulama hatasına düşürür.
    """
    return Screening(text, "safe", CLEAN_NOTE)


# -- belirsizlik notu -------------------------------------------------------

def test_uncertainty_note_names_what_the_camera_cannot_see():
    n = uncertainty_note(Signals(vanished_tracks=[3], person_count=1))
    assert n and "göremiyor" in n.lower()


def test_person_without_a_velocity_estimate_is_an_uncertainty():
    """`velocities` boşken 'hareket ediyor mu' sorusunun cevabı YOK.

    `compute_signals` hızları yalnız iki kare arasında eşleşen track'ler için
    üretiyor: pencerenin ilk karesinde ve track eşleşmediğinde sözlük boş
    kalıyor. Yani `person_count=1, velocities={}` tam olarak Beat 2'nin hâli —
    kadrajda bir kişi var, hareket edip etmediği bilinmiyor. Not bu yüzden
    doluyor; boş dönmesi belirsizliği sessizce yutmak olurdu.
    """
    assert uncertainty_note(Signals(person_count=1))


def test_uncertainty_note_is_silent_when_nothing_is_unknown():
    assert uncertainty_note(Signals()) == ""
    assert uncertainty_note(Signals(person_count=1,
                                    velocities={1: 0.4})) == ""


# -- prompt / şema tutarlılığı ----------------------------------------------

#: Promptta geçen kimlik biçimli sözcükler (en az bir alt çizgi). Türkçe
#: düzyazı bu desene uymaz, araç ve parametre adları uyar.
_IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def _schema_names():
    return {s["function"]["name"] for s in ALL_TOOL_SCHEMAS}


def _schema_params():
    return {p for s in ALL_TOOL_SCHEMAS
            for p in s["function"]["parameters"]["properties"]}


def test_prompt_never_names_a_tool_that_the_schemas_do_not_define():
    """Promptun `gozlem_duzelt` demesi sistemi sessizce öldürüyordu.

    Şema `correct_observation` tanımlıyordu; model promptun dediğini
    gönderiyor, o ad hiçbir yere düşmüyor ve düzeltme kaskadı hiç
    tetiklenmiyordu. Testler yeşil, KPI sıfır.
    """
    known = _schema_names() | _schema_params()
    unknown = [t for t in _IDENTIFIER.findall(SYSTEM_PROMPT) if t not in known]
    assert unknown == []


def test_prompt_catalogue_is_generated_from_every_offered_schema():
    """Yukarıdaki test boş bir promptla da geçerdi; bu onu boş bırakmıyor."""
    for name in _schema_names():
        assert name in SYSTEM_PROMPT


def test_prompt_teaches_the_correction_tool_by_its_schema_name():
    assert CORRECT_OBSERVATION in _schema_names()
    assert CORRECT_OBSERVATION in SYSTEM_PROMPT


# -- yükseltme --------------------------------------------------------------

def test_escalation_queries_the_shift_before_speaking():
    gw, store, e = _setup([
        _tool("query_shift_personnel", {"zone": "B-Hattı",
                                        "at_time": "03:12"}),
        Response(content="03:12 — B-Hattı'nda istif aracı devrildi. "
                         "Risk: Kritik."),
        Response(content="uygun"),
    ])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)):
        message = Supervisor(gw, store).escalate(e)
    assert "query_shift_personnel" in [a.tool_name for a in store.actions()]
    assert "03:12" in message


def test_critical_escalation_is_not_filtered_by_the_guard():
    gw, store, e = _setup([Response(content="KRİTİK: yerde hareketsiz kişi.")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.screen_text",
               return_value=_screening()) as g:
        Supervisor(gw, store).escalate(e)
    assert g.call_args.kwargs["critical"] is True


def test_escalation_carries_the_uncertainty_note_into_the_prompt():
    gw, store, e = _setup([Response(content="haber"), Response(content="uygun")])
    store.save_observation(Observation(ts=EPISODE_TS,
                                       signals=Signals(person_count=1)))
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)):
        Supervisor(gw, store).escalate(e)
    assert "BELİRSİZLİK" in gw.prompts[0][-1]["content"]


# -- guard kaydı ------------------------------------------------------------

def test_flagged_reply_is_replaced_and_the_verdict_is_recorded():
    gw, store, _ = _setup([Response(content="uygunsuz bir ifade"),
                           Response(content="uygunsuz")])
    n = Supervisor(gw, store)
    reply = n.talk("özet")
    assert reply == NEUTRAL_NOTICE
    assert n.last_screening.verdict == "unsafe"
    audit = [t for t in store.dialogue() if t.text.startswith(AUDIT_PREFIX)]
    assert audit and FLAGGED_NOTE in audit[-1].text


def test_unreadable_verdict_is_recorded_as_not_screened():
    gw, store, _ = _setup([Response(content="normal cevap"),
                           Response(content="???")])
    n = Supervisor(gw, store)
    n.talk("özet")
    assert n.last_screening.screened is False
    assert any(UNREADABLE_NOTE in t.text for t in store.dialogue())


def test_clean_verdict_does_not_pollute_the_dialogue():
    gw, store, _ = _setup([Response(content="temiz cevap"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("özet")
    assert [t.role for t in store.dialogue()] == ["operator", "supervisor"]


# -- bozulmuş yanıt ---------------------------------------------------------

def test_degraded_response_does_not_reach_the_operator_as_an_empty_message():
    gw, store, _ = _setup([Response(degraded=True)])
    reply = Supervisor(gw, store).talk("durum?")
    assert reply == DEGRADED_REPLY
    assert store.dialogue()[-1].text == DEGRADED_REPLY
    assert store.dialogue()[-1].role == "system"


def test_empty_response_falls_back_with_its_own_reason():
    gw, store, _ = _setup([Response(content="   ")])
    assert Supervisor(gw, store).talk("durum?") == EMPTY_REPLY


def test_the_three_fault_texts_are_distinct():
    assert len({DEGRADED_REPLY, EMPTY_REPLY, UNFINISHED_REPLY}) == 3


# -- onay kapısı ------------------------------------------------------------

def test_line_stop_is_held_for_approval_and_not_executed():
    gw, store, _ = _setup([_halt(), Response(content="B-Hattı'nı durdurayım mı?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("durumu özetle")
    pending = n.pending_approval()
    assert pending is not None and pending.tool_name == "halt_production_line"
    assert pending.result["awaiting_approval"] is True


def test_a_second_gated_action_is_refused_while_one_is_pending():
    """İkinci bekleyen satır birincisini kalıcı olarak görünmez kılıyordu."""
    gw, store, _ = _setup([_halt("ilk"), Response(content="onay?"),
                           Response(content="uygun"),
                           _halt("ikinci"), Response(content="ikinci cevap"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("hattı durdur")
    reply = n.talk("yine durdur")

    pending_rows = [a for a in store.actions() if a.approval == "pending"]
    assert len(pending_rows) == 1
    assert pending_rows[0].params["rationale"] == "ilk"
    assert n.pending_approval().id == pending_rows[0].id
    # operatör neyin beklediğini öğreniyor
    assert "halt_production_line" in reply and "onay" in reply.lower()


def test_the_refusal_reaches_the_model_as_a_tool_result():
    gw, store, _ = _setup([_halt("ilk"), Response(content="onay?"),
                           Response(content="uygun"),
                           _halt("ikinci"), Response(content="ikinci cevap"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("hattı durdur")
    n.talk("yine durdur")
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("refused") for m in tool_messages)


def test_ungated_actions_still_run_immediately():
    """Yalnız hat durdurma kapıda bekler; geri kalanı anında koşar."""
    gw, store, _ = _setup([_tool("dispatch_medical",
                                 {"location": "B-Hattı", "urgency": "critical",
                                  "description": "yerde kişi"}),
                           Response(content="ekip yolda"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("sağlık ekibi çağır")
    row = store.actions()[-1]
    assert row.tool_name == "dispatch_medical"
    assert row.approval == "not_required"
    assert row.result["state"] == "dispatched"


def test_approving_does_not_create_a_second_pending_approval():
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    n.approve(n.pending_approval().id, True)
    assert n.pending_approval() is None
    assert [a.approval for a in store.actions()].count("pending") == 0


def test_approving_actually_halts_the_line():
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    result = n.approve(n.pending_approval().id, True)
    # Onayın durumu ile aracın durumu ayrı anahtarlarda: düz birleştirmede
    # aracın `"halted"` değeri onayın `"approved"`ünü eziyordu.
    assert result["state"] == "approved"
    assert result["result"]["state"] == "halted"
    assert store.actions()[-1].result["state"] == "halted"


def test_refusing_marks_the_action_rejected_and_does_not_run_it():
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    before = len(store.actions())
    n.approve(n.pending_approval().id, False)
    assert len(store.actions()) == before
    assert store.actions()[-1].approval == "rejected"


def test_a_rejected_gate_frees_the_slot_for_a_new_action():
    gw, store, _ = _setup([_halt("ilk"), Response(content="onay?"),
                           Response(content="uygun"),
                           _halt("ikinci"), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    n.approve(n.pending_approval().id, False)
    n.talk("yeniden dur")
    assert n.pending_approval().params["rationale"] == "ikinci"


def test_approving_an_unknown_action_returns_a_result_instead_of_raising():
    gw, store, _ = _setup([Response(content="cevap"), Response(content="uygun")])
    result = Supervisor(gw, store).approve(9999, True)
    assert result["state"] == "unknown_action"
    assert result["error"]


def test_a_settled_action_is_never_executed_twice():
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    action_id = n.pending_approval().id
    n.approve(action_id, True)
    before = len(store.actions())
    result = n.approve(action_id, True)
    assert result["state"] == "not_pending"
    assert len(store.actions()) == before


# -- düzeltme kaskadı -------------------------------------------------------

def _correction(**overrides):
    params = {"episode_id": 1, "field": "event_type", "old": "araç devrildi",
              "new": "yük düştü", "rationale": "operatör gözlemi"}
    return _tool(CORRECT_OBSERVATION, {**params, **overrides})


def test_correction_is_recorded_and_cascades_to_the_episode_summary():
    gw, store, e = _setup([_correction(),
                           Response(content="Anlaşıldı, kaydı güncelledim."),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)):
        Supervisor(gw, store).talk("araç devrilmedi, yük düştü")
    assert store.corrections(1)[0].new == "yük düştü"
    assert "yük düştü" in store.episodes()[0].summary_tr


def test_correction_re_runs_the_risk_assessment():
    gw, store, e = _setup([_correction(old="a", new="b", rationale="g"),
                           Response(content="tamam"), Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk",
               return_value=_risk(e)) as r:
        Supervisor(gw, store).talk("düzeltme")
    r.assert_called_once()


def test_correction_is_stamped_with_the_video_time():
    gw, store, e = _setup([_correction(), Response(content="tamam"),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)):
        Supervisor(gw, store).talk("düzeltme")
    assert store.corrections(1)[0].ts == EPISODE_TS


def test_a_correction_with_stray_keys_returns_an_error_not_a_crash():
    """`Correction` `extra="forbid"` — tek fazla anahtar bütün turu düşürürdü."""
    gw, store, _ = _setup([_correction(confidence=0.9),
                           Response(content="olmadı"), Response(content="uygun")])
    Supervisor(gw, store).talk("düzeltme")
    assert store.corrections(1) == []
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("error") for m in tool_messages)


def test_correction_for_an_unknown_episode_is_reported():
    gw, store, _ = _setup([_correction(episode_id=77),
                           Response(content="olmadı"), Response(content="uygun")])
    Supervisor(gw, store).talk("düzeltme")
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    payloads = [json.loads(m["content"]) for m in tool_messages]
    assert any(p.get("warning") for p in payloads)


# -- süpervizörün kendi araçları --------------------------------------------

def test_search_timeline_is_reachable_as_a_tool():
    gw, store, _ = _setup([_tool("search_timeline", {"query": "devrilme"}),
                           Response(content="bulundu"),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.search_timeline",
               return_value=[]) as s:
        Supervisor(gw, store).talk("geçmişte oldu mu?")
    s.assert_called_once()


def test_root_cause_report_is_reachable_as_a_tool():
    """Geç import yamalanamıyordu; artık modül seviyesinde."""
    report = RootCauseReport(what_happened="oldu", probable_root_cause="fren",
                             confidence_limits="kamera")
    gw, store, _ = _setup([_tool("generate_root_cause_report", {}),
                           Response(content="rapor hazır"),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.generate_root_cause_report",
               return_value=report) as r:
        Supervisor(gw, store).talk("raporu ver")
    r.assert_called_once()


def test_request_risk_assessment_reports_an_unknown_episode():
    gw, store, _ = _setup([_tool("request_risk_assessment", {"episode_id": 77}),
                           Response(content="yok"), Response(content="uygun")])
    Supervisor(gw, store).talk("riski sor")
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("error") for m in tool_messages)


def test_an_invented_tool_name_is_reported_to_the_model():
    gw, store, _ = _setup([_tool("make_coffee", {}), Response(content="olmadı"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("kahve")
    assert store.actions() == []
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("error") for m in tool_messages)


# -- diyalog akışı ----------------------------------------------------------

def test_open_incident_is_appended_to_every_operator_turn():
    gw, store, _ = _setup([Response(content="cevap"), Response(content="uygun")])
    Supervisor(gw, store).talk("dur, başka bir şey soracağım")
    prompt_text = gw.prompts[0][-1]["content"]
    assert "Açık olay" in prompt_text


def test_dialogue_turns_are_recorded_both_sides():
    gw, store, _ = _setup([Response(content="Anlaşıldı."),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("durum nedir?")
    assert [s.role for s in store.dialogue()] == ["operator", "supervisor"]


def test_dialogue_turns_carry_the_video_time_not_zero():
    """Her satır `00:00` damgalıysa kök neden raporunun diyalog bölümü yalan."""
    gw, store, _ = _setup([Response(content="Anlaşıldı."),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("durum nedir?")
    assert [t.ts for t in store.dialogue()] == [EPISODE_TS, EPISODE_TS]


def test_tool_calls_are_stamped_with_the_video_time():
    gw, store, _ = _setup([_tool("query_equipment_history",
                                 {"equipment_id": "IST-04"}),
                           Response(content="bakım gecikmiş"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("ekipman geçmişi?")
    assert store.actions()[-1].ts == EPISODE_TS


def test_tool_loop_terminates_instead_of_spinning_forever():
    gw, store, _ = _setup([_tool("site_alarm", {"zone": "B",
                                                "level": "yuksek"})] * 12)
    reply = Supervisor(gw, store).talk("alarm çal")
    assert reply == UNFINISHED_REPLY
    assert gw.ask.call_count == MAX_TURNS <= 6
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_supervisor.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/supervisor.py` yaz

```python
"""Nöbetçi — operatörün konuştuğu ajan ve topolojinin ortası.

Şartnamenin "Otonomi ve Zeka" kalemi (%20) dört şey istiyor ve dördü de burada
karşılanıyor: kimse sormadan haber vermek (`escalate`), göremediğini sormak
(`uncertainty_note`), konu değişse de açık olaya dönmek (`talk`) ve doğal bir
Türkçe akış (sistem promptu).

Süpervizörün kendi araçları yedi saha aracının **yanına** ekleniyor; iki tür
arasında seçim yapmak model için tek bir karar oluyor ve şartnamenin puanladığı
*dinamik araç seçimi* defterden okunabiliyor.

## Onay kapısında yalnız `halt_production_line` var — ve bu bir karar

`NEEDS_APPROVAL` tek bir araç sayıyor. Bu bir eksik değil, bilerek verilmiş bir
iş güvenliği hükmü:

- `dispatch_medical`, `radio_call`, `site_alarm` ve `open_safety_incident`
  **geri alınabilir ve ucuz.** Yanlış çağrılan bir sağlık ekibi geri döner,
  boşuna çalan bir siren susturulur, fazladan açılan bir İSG kaydı kapatılır.
  Buna karşılık gecikmenin bedeli **can**: yerde hareketsiz bir kişi varken
  ekibi operatörün onayını bekletmek, kaybedilen her saniyeyi bir onay
  ekranına ödemek olurdu. Bu yüzden dördü de anında yürüyor.
- `halt_production_line` **geri alması zor ve pahalı.** Duran bir hattın
  yeniden devreye alınması vardiya planını, üretim çizelgesini ve teslimat
  taahhüdünü etkiler; ajanın tek başına vereceği bir karar değil. Bu yüzden
  kapıda bekliyor.

Kısacası: **geri alınabilir olan hemen koşar, geri alınamayan insana sorar.**
Ajan kendi hat durdurmasını onaylayamaz — onayın tek kaynağı aksiyon defteri
(`registry.call_tool`).

## Aynı anda tek bir onay bekleyebilir

`pending_approval()` tek bir kayıt döndürüyor. İkinci bir bekleyen satır
doğduğu anda birincisi kalıcı olarak görünmez olurdu: defterde sonsuza dek
`"pending"` kalır, konsolun onay çubuğu ise bayat satırın üzerine yeniden
açılırdı. Bu yüzden kapı **girişte** kapanıyor: onay bekleyen bir aksiyon
varken yeni bir kapılı aksiyon yürütülmüyor, modele reddedildiği söyleniyor ve
operatöre neyin beklediği Türkçe olarak bildiriliyor. Böylece "tek kayıt"
varsayımı bir umut değil, yapısal bir değişmez.

## Prompt ile şema ayrışamaz

Promptun araç kataloğu `ALL_TOOL_SCHEMAS`'tan **türetiliyor**; düzeltme
aracının adı da prompta elle yazılmıyor, `CORRECT_OBSERVATION` sabitinden
geliyor. Elle yazılmış bir ad ayrışır — ve ayrıştığında model var olmayan bir
aracı çağırır, düzeltme kaskadı hiç tetiklenmez, `correction_propagation` KPI'ı
sessizce sıfır okur. CLAUDE.md bu arızayı adıyla yazıyor; buradaki karşılığı
hatırlanması gereken bir kural değil, unutulması imkânsız bir yapı.
"""

import json

from gozcu.agents.reporter import generate_root_cause_report
from gozcu.agents.risk import _describe_tool, assess_risk
from gozcu.agents.router import mmss
from gozcu.guard import screen_text
from gozcu.memory import search_timeline
from gozcu.models import Correction, DialogueTurn, Episode, Signals
from gozcu.tools.registry import NEEDS_APPROVAL, TOOL_SCHEMAS, call_tool

#: Bir diyalog turunda izin verilen model çağrısı sayısı. Araç turu bitmezse
#: tur `UNFINISHED_REPLY` ile kapanır; sonsuz döngü operatörü bekletirdi.
MAX_TURNS = 4

#: Süpervizörün kendi araçlarının adları. Tek kopya burada: prompt da şema da
#: dağıtım da bu sabitleri okuyor, dolayısıyla üçü ayrışamaz.
SEARCH_TIMELINE = "search_timeline"
CORRECT_OBSERVATION = "correct_observation"
REQUEST_RISK_ASSESSMENT = "request_risk_assessment"
GENERATE_ROOT_CAUSE_REPORT = "generate_root_cause_report"

SUPERVISOR_TOOLS = [
    {"type": "function", "function": {
        "name": SEARCH_TIMELINE,
        "description": "Geçmiş olay arşivinde anlamsal arama yapar.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": CORRECT_OBSERVATION,
        "description": "Operatörün düzeltmesini kalıcı olarak kaydeder ve "
                       "olay özetiyle risk analizine yayar.",
        "parameters": {"type": "object", "properties": {
            "episode_id": {"type": "integer"}, "field": {"type": "string"},
            "old": {"type": "string"}, "new": {"type": "string"},
            "rationale": {"type": "string"}},
            "required": ["episode_id", "field", "old", "new", "rationale"]}}},
    {"type": "function", "function": {
        "name": REQUEST_RISK_ASSESSMENT,
        "description": "Bir olay için iş güvenliği risk analizi ister.",
        "parameters": {"type": "object",
                       "properties": {"episode_id": {"type": "integer"}},
                       "required": ["episode_id"]}}},
    {"type": "function", "function": {
        "name": GENERATE_ROOT_CAUSE_REPORT,
        "description": "Kapanan olay için kök neden raporu üretir.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

#: Modele sunulan şemaların tamamı — yedi saha aracı ve süpervizörün dördü.
ALL_TOOL_SCHEMAS = [*TOOL_SCHEMAS, *SUPERVISOR_TOOLS]

#: Promptun araç kataloğu, **şemalardan** üretiliyor. `gozcu.agents.risk`'in
#: aynı yardımcısı kullanılıyor: ikinci bir kopya iki ayrı yöne kayabilirdi.
TOOL_CATALOGUE = "\n".join(_describe_tool(s) for s in ALL_TOOL_SCHEMAS)

_SYSTEM_TEMPLATE = """Sen bir savunma sanayi üretim tesisinin kontrol odasında görevli
vardiya amirisin. Operatörle Türkçe konuşuyorsun.

Nasıl davranırsın:
- Kritik bir olay gördüğünde SORULMADAN önce sen haber verirsin
- Konuşmadan önce gerekli sorguları yaparsın (vardiya, ekipman geçmişi)
- Kameradan göremediğin bir şeyi UYDURMAZSIN, operatöre sorarsın
- Operatör seni düzeltirse {correction_tool} aracını çağırırsın
- Operatör konuyu değiştirirse cevaplarsın ama AÇIK OLAYI HATIRLATIRSIN
- Geri dönüşü zor aksiyonlarda ({gated_tools}) İZİN İSTERSİN; geri alınabilir
  aksiyonları (sağlık ekibi, telsiz, alarm, İSG kaydı) beklemeden çağırırsın
- Aynı anda YALNIZ BİR aksiyon onay bekleyebilir. Bekleyen bir onay varken
  yenisini isteme; önce operatörün kararını al
- Kısa cümleler kurarsın. Saha terminolojisi kullanırsın.

Çağırabileceğin araçlar — araç adını ve parametre değerlerini burada yazdığı
gibi, birebir kullan:
{tools}

Var olmayan bir araç adı UYDURMA.

Zaman damgalarını MM:SS biçiminde yazarsın."""

SYSTEM_PROMPT = _SYSTEM_TEMPLATE.format(
    correction_tool=CORRECT_OBSERVATION,
    gated_tools=", ".join(sorted(NEEDS_APPROVAL)),
    tools=TOOL_CATALOGUE)

# Arıza metinleri. Üçü bilerek farklı: operatör de kök neden raporunu okuyan
# kişi de "kademe sustu", "kademe boş yanıt döndü" ve "araç turu sonuçlanmadı"
# ayrımını görebilmeli — üçü farklı arızalar ve farklı müdahale gerektiriyor.
# Aynı metni paylaşsalardı `degraded` dalı sessizce ölü koda dönerdi.
DEGRADED_REPLY = ("Diyalog katmanı yanıt vermiyor. Olay kaydı ve aksiyon "
                  "defteri korunuyor; ekranınızdaki son duruma göre "
                  "ilerleyin.")
EMPTY_REPLY = ("Diyalog katmanı boş yanıt döndürdü. Olay kaydı ve aksiyon "
               "defteri korunuyor; sorunuzu tekrar iletin.")
UNFINISHED_REPLY = ("Yanıt üretilemedi: araç turu sonuçlanmadı. Olay kaydı ve "
                    "aksiyon defteri korunuyor.")

#: Denetim hükmünün diyalog dökümüne düştüğü satırın başı. Kök neden raporunun
#: DİYALOG bölümünde bu satırlar operatör konuşmasından ayırt edilebilmeli.
AUDIT_PREFIX = "[denetim]"

#: Modele söylenen ret gerekçesi — ikinci kapılı aksiyon denemesi.
SECOND_GATE_REFUSAL = ("Onay bekleyen bir aksiyon varken yeni bir onaylı "
                       "aksiyon başlatılamaz. Operatörden bekleyen aksiyon "
                       "için karar iste.")

#: Operatöre giden bildirim: neyin beklediğini adıyla söyler. Model
#: cevabından bağımsız olarak eklenir — bekleyen onayın duyurulması bir
#: prompt umuduna bırakılamaz.
PENDING_GATE_NOTICE = (
    "[SİSTEM] Onayınızı bekleyen bir aksiyon zaten var: {tool} — {params}. "
    "Aynı anda yalnız bir aksiyon onay bekleyebilir, bu yüzden yeni bir "
    "aksiyon başlatmadım. Önce bekleyen aksiyonu onaylayın ya da reddedin.")


def uncertainty_note(signals: Signals) -> str:
    """Kameranın göremediğini açıkça adlandırır.

    Beat 2 buna dayanıyor: 'yerdeki kişi hareket ediyor mu, göremiyorum'
    sorusunu prompt umuduna bırakmak yerine, sinyallerden türetilmiş gerçek
    bir belirsizlik notuyla güvenilir şekilde tetikliyoruz.

    Boş `velocities` bir eksiklik değil, bir **bilgi**: `compute_signals` hızı
    yalnız iki kare arasında eşleşen track'ler için üretiyor, yani sözlük
    boşken kadrajdaki kişinin hareket edip etmediği ölçülmemiştir. O hâlde
    not doludur; sessiz kalmak belirsizliği yutmak olurdu.
    """
    notes = []
    if signals.vanished_tracks:
        notes.append("bazı nesneler kadraj dışına çıktı, durumlarını "
                     "göremiyorum")
    if signals.person_count and not signals.velocities:
        notes.append("yerdeki kişinin hareket edip etmediğini bu açıdan "
                     "göremiyorum")
    return ("BELİRSİZLİK: " + "; ".join(notes)) if notes else ""


class Supervisor:
    """Operatörle konuşan ajan; araçları defter üzerinden çağırır."""

    def __init__(self, gw, store) -> None:
        self.gw, self.store = gw, store
        # Araç çağrılarının ve diyalog satırlarının deftere yazılacağı VİDEO
        # zamanı; `escalate()` onu açık epizottan alıyor. Duvar saati değil:
        # `00:00` damgalı bir defter kök neden raporunda yalan söyler.
        self.ts: float = 0.0
        self.history: list[dict] = [{"role": "system",
                                     "content": SYSTEM_PROMPT}]
        #: Son denetim hükmü — konsol ve KPI okuyabilsin diye tutuluyor.
        self.last_screening = None
        #: Bu turda operatöre eklenecek sistem bildirimi (bekleyen onay).
        self._notice: str | None = None

    # -- iç araçlar ---------------------------------------------------------

    def _apply_correction(self, params: dict) -> dict:
        """Düzeltmeyi kaydeder VE yayar: epizot özeti güncellenir, risk
        yeniden koşar. Sadece tabloya yazmak, hiçbir şey yapmamaktır.

        `Correction` `extra="forbid"` ilan ediyor; modelin eklediği tek bir
        fazla anahtar doğrulama hatasıyla bütün turu düşürürdü. Hata modele
        okunur biçimde geri veriliyor ki ikinci denemede düzeltebilsin.
        """
        try:
            correction = Correction(ts=self.ts, **params)
        except Exception as error:  # noqa: BLE001 — bozuk çağrı turu düşürmemeli
            return {"tool_name": CORRECT_OBSERVATION,
                    "error": f"düzeltme kaydı doğrulanamadı: {error}"}

        self.store.save_correction(correction)
        episode = self._episode(correction.episode_id)
        if episode is None:
            return {"state": "recorded",
                    "warning": f"epizot bulunamadı: {correction.episode_id}"}

        new_summary = episode.summary_tr.replace(correction.old,
                                                 correction.new)
        if new_summary == episode.summary_tr:
            new_summary = (f"{episode.summary_tr} "
                           f"(operatör düzeltmesi: {correction.new})")
        self.store.update_episode(episode.id, summary_tr=new_summary[:600])

        refreshed = self._episode(episode.id)
        risk = assess_risk(self.gw, self.store, refreshed)
        return {"state": "recorded", "new_summary": refreshed.summary_tr,
                "new_risk": risk.level}

    def _episode(self, episode_id) -> Episode | None:
        return next((e for e in self.store.episodes() if e.id == episode_id),
                    None)

    def _internal_tool(self, name: str, params: dict):
        """Süpervizörün kendi araçları; saha aracıysa `None` döner."""
        if name == SEARCH_TIMELINE:
            found = search_timeline(self.gw, self.store, params["query"])
            return {"results": [e.model_dump() for e in found]}
        if name == CORRECT_OBSERVATION:
            return self._apply_correction(params)
        if name == REQUEST_RISK_ASSESSMENT:
            episode = self._episode(params.get("episode_id"))
            if episode is None:
                return {"tool_name": REQUEST_RISK_ASSESSMENT,
                        "error": f"epizot bulunamadı: "
                                 f"{params.get('episode_id')}"}
            return assess_risk(self.gw, self.store, episode).model_dump()
        if name == GENERATE_ROOT_CAUSE_REPORT:
            return generate_root_cause_report(self.gw, self.store).model_dump()
        return None

    def _refuse_second_gate(self, name: str) -> dict | None:
        """Onay bekleyen bir aksiyon varken ikinci kapılı aksiyonu reddeder.

        Ret **yürütmeden önce** veriliyor: `call_tool`'a girseydi defterde
        ikinci bir `"pending"` satır doğar ve birincisi kalıcı olarak
        görünmez olurdu. Reddedilen çağrı deftere hiç düşmüyor — olmamış bir
        aksiyon defterde görünmemeli.
        """
        pending = self.pending_approval()
        if pending is None:
            return None
        params = json.dumps(pending.params, ensure_ascii=False, default=str)
        self._notice = self._notice or PENDING_GATE_NOTICE.format(
            tool=pending.tool_name, params=params)
        return {"tool_name": name, "refused": True,
                "reason": SECOND_GATE_REFUSAL,
                "pending_action_id": pending.id,
                "pending_tool": pending.tool_name}

    def _run_tool(self, call: dict) -> dict:
        """Tek bir araç çağrısını çalıştırır; her arıza okunur bir sonuç."""
        function = call.get("function") or {}
        name = function.get("name")
        try:
            params = json.loads(function.get("arguments") or "{}")
        except (ValueError, TypeError):
            return {"tool_name": name, "error": "araç parametreleri okunamadı"}
        if not isinstance(params, dict):
            return {"tool_name": name, "error": "araç parametreleri okunamadı"}

        try:
            internal = self._internal_tool(name, params)
        except Exception as error:  # noqa: BLE001 — bozuk çağrı turu düşürmemeli
            return {"tool_name": name,
                    "error": f"araç çalıştırılamadı: {error}"}
        if internal is not None:
            return internal

        if name in NEEDS_APPROVAL:
            refused = self._refuse_second_gate(name)
            if refused is not None:
                return refused

        try:
            return call_tool(self.store, name, params, actor="agent",
                             ts=self.ts)
        except KeyError:
            return {"tool_name": name, "error": f"bilinmeyen araç: {name}"}
        except Exception as error:  # noqa: BLE001 — bozuk argüman turu düşürmemeli
            return {"tool_name": name,
                    "error": f"araç çalıştırılamadı: {error}"}

    # -- diyalog ------------------------------------------------------------

    def _take_notice(self, text: str) -> str:
        """Bekleyen onay bildirimini cevabın altına ekler ve sıfırlar.

        Bildirim denetimden GEÇMİYOR: bizim yazdığımız sabit bir sistem metni,
        model üretimi değil — denetim katmanı model metnini süzmek için var.
        """
        notice, self._notice = self._notice, None
        return f"{text}\n\n{notice}".strip() if notice else text

    def _reply(self, content: str, critical: bool) -> str:
        """Modelin cevabını denetler, kaydeder ve operatöre döndürür."""
        screening = screen_text(self.gw, content, critical=critical)
        self.last_screening = screening
        text = self._take_notice(screening.text)

        self.history.append({"role": "assistant", "content": text})
        self.store.save_dialogue(DialogueTurn(ts=self.ts, role="supervisor",
                                              text=text))
        # Hüküm denetim kaydına düşüyor — ama yalnız söylenecek bir şey
        # varsa. "Temiz" her tura bir satır eklerdi; engellenen, okunamayan ya
        # da hiç uygulanmayan denetimin kaydı ise kanıttır.
        if screening.verdict != "safe":
            self.store.save_dialogue(DialogueTurn(
                ts=self.ts, role="system",
                text=f"{AUDIT_PREFIX} {screening.note}"))
        return text

    def _fault(self, message: str) -> str:
        """Arıza metnini operatöre verir ve deftere yazar.

        Bozulmuş yanıt `content=""` taşıyor; denetime sokup boş metni
        operatöre göndermek yerine tur burada kapanıyor. Metin `system`
        rolüyle kaydediliyor: bunu söyleyen süpervizör değil, sistemdir.
        """
        text = self._take_notice(message)
        self.history.append({"role": "assistant", "content": text})
        self.store.save_dialogue(DialogueTurn(ts=self.ts, role="system",
                                              text=text))
        return text

    def _turn_loop(self, critical: bool) -> str:
        for _ in range(MAX_TURNS):
            response = self.gw.ask("main", self.history,
                                   tools=ALL_TOOL_SCHEMAS)
            if response.degraded:
                return self._fault(DEGRADED_REPLY)

            if not response.tool_calls:
                content = (response.content or "").strip()
                if not content:
                    return self._fault(EMPTY_REPLY)
                return self._reply(content, critical)

            self.history.append({"role": "assistant",
                                 "content": response.content or None,
                                 "tool_calls": response.tool_calls})
            for call in response.tool_calls:
                result = self._run_tool(call)
                self.history.append({
                    "role": "tool", "tool_call_id": call.get("id", "c"),
                    "content": json.dumps(result, ensure_ascii=False,
                                          default=str)})

        return self._fault(UNFINISHED_REPLY)

    def escalate(self, episode: Episode) -> str:
        """Proaktif açılış: kimse sormadan operatöre seslenir."""
        self.ts = episode.start_ts
        risk = assess_risk(self.gw, self.store, episode)
        observations = [o for o in self.store.observations()
                        if episode.start_ts <= o.ts <= (episode.end_ts
                                                        or episode.start_ts)]
        signals = observations[-1].signals if observations else Signals()
        note = uncertainty_note(signals)

        self.history.append({
            "role": "user",
            "content": f"[SİSTEM] {mmss(episode.start_ts)} — kritik olay: "
                       f"{episode.summary_tr}. Risk: {risk.level}. "
                       f"Gerekçe: {risk.rationale_tr}\n{note}\n"
                       f"Operatöre kendin haber ver. Belirsizlik varsa sor."})
        return self._turn_loop(critical=risk.level in ("Yüksek", "Kritik"))

    def talk(self, operator_text: str) -> str:
        """Bir diyalog turu. Açık olay her turda hatırlatılıyor."""
        open_episode = self.store.open_episode()
        if open_episode:
            self.ts = open_episode.start_ts   # diyalogdaki çağrılar da videoda
        self.store.save_dialogue(DialogueTurn(ts=self.ts, role="operator",
                                              text=operator_text))
        reminder = (f"\n[SİSTEM] Açık olay: episode {open_episode.id} — "
                    f"{open_episode.summary_tr}" if open_episode else "")
        self.history.append({"role": "user",
                             "content": operator_text + reminder})
        return self._turn_loop(critical=False)

    # -- onaylar ------------------------------------------------------------

    def pending_approval(self):
        """Onay bekleyen tek aksiyon; yoksa `None`.

        `_refuse_second_gate` sayesinde defterde aynı anda en fazla bir
        bekleyen satır olabiliyor. Yine de **en eskisi** döndürülüyor: bir gün
        başka bir yazar ikinci satırı doğurursa, konsolun onay çubuğunun
        üzerine açıldığı satır kaybolmasın.
        """
        pending_rows = [a for a in self.store.actions()
                        if a.approval == "pending"]
        return pending_rows[0] if pending_rows else None

    def approve(self, action_id: int, approved: bool) -> dict:
        """Operatörün kararını uygular.

        Bilinmeyen kimlik çıplak bir `StopIteration` atmıyor, okunur bir sonuç
        dönüyor: bu çağrının kaynağı konsol, yani bir kullanıcı hatası
        yığın izine dönüşmemeli. Kararı verilmiş bir satır da yeniden
        yürütülmüyor — ikinci bir `call_tool` deftere ikinci bir hat durdurma
        yazardı.
        """
        record = next((a for a in self.store.actions() if a.id == action_id),
                      None)
        if record is None:
            return {"state": "unknown_action",
                    "error": f"aksiyon bulunamadı: {action_id}"}
        if record.approval != "pending":
            return {"state": "not_pending", "approval": record.approval,
                    "error": f"aksiyon zaten karara bağlanmış: "
                             f"{record.approval}"}

        if not approved:
            self.store.set_action_approval(action_id, "rejected")
            return {"state": "rejected", "action_id": action_id}

        # `approval` geçilmezse `call_tool` yeni bir "pending" satır doğurur ve
        # onay çubuğu hiç kapanmaz. `ts` orijinal satırdan: onay duvar
        # saatinde geliyor ama aksiyon videonun o anına ait.
        result = call_tool(self.store, record.tool_name, record.params,
                           actor="operator", approval="approved",
                           ts=record.ts)
        self.store.set_action_approval(action_id, "approved")
        # Araç sonucu İÇ İÇE duruyor, düzleştirilmiyor: `halt_production_line`
        # da bir `state` döndürüyor ve düz birleştirmede onun `"halted"`
        # değeri onayın `"approved"`ünü eziyordu — çağıran onayın gerçekten
        # işlendiğini hiçbir zaman göremezdi.
        return {"state": "approved", "action_id": action_id, "result": result}
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_supervisor.py -v
```
Beklenen: 39 passed

### 5. Commit

```bash
git add gozcu/agents/supervisor.py tests/test_supervisor.py
git commit -m "feat: Nöbetçi supervisor with tool loop, correction cascade and approvals"
```

## Doğrulama

```bash
uv run pytest tests/test_supervisor.py -v
```
Beklenen: **39 passed**

## 25 Ağustos akşamı: canlı prova — 2 saat, atlanamaz

Yukarıdaki testlerin hepsi mock. **Puanın %20'sini taşıyan katmanın gerçek
modelle hiç konuşmamış olması kabul edilemez.** Testler yeşile döndükten sonra
gerçek gateway ile en az iki tur prova yap ve promptu düzelt:

1. Yükseltme mesajı gerçekten kısa ve Türkçe mi, yoksa çeviri mi kokuyor?
2. Belirsizlik notu varken ajan **gerçekten soruyor mu**, yoksa uyduruyor mu?
3. Operatör konuyu değiştirdiğinde açık olaya **kendiliğinden dönüyor mu**?
4. Hat durdurma için **izin istiyor mu**, yoksa doğrudan çağırıyor mu?

Bunların dördü de demo videosunda görünecek. Prompt iterasyonu için bu iki saat
plandaki en yüksek getirili zaman.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Promptun araç kataloğu ŞEMALARDAN ÜRETİLİYOR** (`TOOL_CATALOGUE`,
  `ALL_TOOL_SCHEMAS`); düzeltme aracının adı da prompta elle yazılmıyor,
  `CORRECT_OBSERVATION` sabitinden geliyor. Bu dosya bir zamanlar promptta
  `gozlem_duzelt` derken şema `correct_observation` tanımlıyordu: model promptun
  dediğini gönderiyor, o ad hiçbir yere düşmüyor, düzeltme kaskadı hiç
  tetiklenmiyor ve `correction_propagation` KPI'ı **sessizce sıfır** okuyordu —
  üstelik bütün testler yeşilken. **Araç adını elle yazma.**
- **Aynı anda YALNIZ BİR onay yuvası var.** Bekleyen bir onay dururken ikinci bir
  kapılı aksiyon **yürütülmeden reddediliyor**: deftere hiçbir satır yazılmıyor,
  modele `refused` bir araç sonucu dönüyor ve operatörün cevabının altına Türkçe
  bir `[SİSTEM]` bildirimi ekleniyor (`PENDING_GATE_NOTICE`). Öncesinde
  `pending_approval()` bekleyenlerin **sonuncusunu** döndürüyordu: ikinci satır
  doğduğu anda birincisi kalıcı olarak görünmez oluyor, defterde sonsuza dek
  `"pending"` kalıyordu. Şimdi hem giriş kapalı hem de `pending_approval()`
  **en eskiyi** döndürüyor.
- **Kapıda YALNIZ `halt_production_line` var — ve bu bilerek verilmiş bir
  hüküm, eksik bir kapı değil.** `dispatch_medical`, `radio_call`, `site_alarm`
  ve `open_safety_incident` beklemeden yürüyor: geri alınabilirler ve zamana
  duyarlılar — yanlış çağrılan ekip geri döner, boşuna çalan siren susturulur,
  fazladan açılan İSG kaydı kapatılır, ama gecikmenin bedeli **can**.
  `halt_production_line` ise geri alması zor ve pahalı (vardiya planı, üretim
  çizelgesi, teslimat taahhüdü), o yüzden insana soruluyor. Kısacası: geri
  alınabilir olan hemen koşar, geri alınamayan insana sorar.
- **`approve()` İÇ İÇE bir sonuç döndürüyor:**
  `{"state": "approved" | "rejected" | "unknown_action" | "not_pending",
  "action_id": int, "result": {...}}`. Önceden araç sonucu üst seviyeye
  düzleştiriliyordu ve `halt_production_line`'ın kendi `state: "halted"` değeri
  onayın `"approved"`ünü eziyordu — hiçbir çağıran onayın gerçekten işlendiğini
  göremezdi. `not_pending` ikinci bir yürütmeyi engelliyor (karara bağlanmış bir
  satır bir daha `call_tool`'a girmiyor); bilinmeyen kimlik de okunur bir sonuç
  dönüyor. **Bu fonksiyon istisna atmıyor.**
- **Denetim hükümleri `role="system"` diyalog satırı olarak, `[denetim]`
  önekiyle kaydediliyor** (`AUDIT_PREFIX`) — ve yalnız hüküm `safe` değilken.
  [Görev 16](16-konsol.md) bu satırları sohbet panelinden **süzmeli**;
  [Görev 17](17-cikti-sozlesmesi.md)'nin kök neden raporu ise onları gösterecek,
  çünkü denetim kaydı kanıttır.
- **`DialogueTurn` ve `Correction` VİDEO zamanını taşıyor**, `0.0` değil:
  `escalate()` epizodun `start_ts`'ini tutuyor, `talk()` açık epizottan
  tazeliyor. Her satır `00:00` damgalı olsaydı kök neden raporunun DİYALOG
  bölümü yalan söylerdi.
- **`screen` / `screen_text` ve raportörün giriş noktası MODÜL SEVİYESİNDE
  import ediliyor.** Geç import `patch("gozcu.agents.supervisor.screen")`'i
  `AttributeError` ile düşürüyordu: var olmayan bir öznitelik yamalanamaz.
  Yeni bir bağımlılık eklerken de aynı kural — geç import testi imkânsız kılar.
- **`uncertainty_note`, kadrajda kişi varken ölçülmüş hız yokken DOLU döner.**
  Bu bir hata değil, özelliğin var olma sebebi: `compute_signals` hızı yalnız
  iki kare arasında eşleşen track'ler için üretiyor, yani `velocities` boşken
  kişinin hareket edip etmediği **hiç ölçülmemiştir**. Sessiz kalmak
  belirsizliği yutmak olurdu.
- **Dışa açık yüzey:** `Supervisor(gw, store)` — `.ts`, `.history`,
  `.last_screening` alanları; `.escalate(episode) -> str`;
  `.talk(operator_text) -> str`; `.pending_approval() -> ActionRecord | None`;
  `.approve(action_id, approved) -> dict`. Sınıfın yanında modül seviyesinde
  `uncertainty_note(signals) -> str`.
