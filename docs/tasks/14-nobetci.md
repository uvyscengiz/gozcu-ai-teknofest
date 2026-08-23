# Görev 14 — Nöbetçi süpervizör (`gozcu/agents/supervisor.py`)

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
güncellemek zorunlu.

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
call_tool(store, tool_name, params, actor="agent", approval=None) -> dict

# gozcu/memory.py
search_timeline(gw, store, query, top_k=5) -> list[Episode]

# gozcu/agents/risk.py
assess_risk(gw, store, episode: Episode) -> RiskAssessment

# gozcu/agents/raportor.py
generate_root_cause_report(gw, store) -> RootCauseReport

# gozcu/guard.py
screen(gw, text: str, critical: bool = False) -> str

# gozcu/store.py
Store.save_dialogue, Store.save_correction, Store.update_episode,
Store.open_episode, Store.episodes, Store.actions, Store.set_action_approval

# gozcu/agents/router.py
mmss(ts: float) -> str
```

**Bozulmuş yanıt guard'ı (Görev 03).** `gw.ask()` kesintide istisna atmıyor;
`content=""`, `tool_calls=[]` olan `degraded=True` bir `Response` dönüyor.
Bozulmuş yanıt hiçbir şeye ayrışmaz — `tool_calls[0]` erişimi ve JSON
ayrıştırma boş yanıta karşı korunmalı, yoksa operatöre boş mesaj gider ya da
`IndexError` alırsın. `except GatewayError` bunu yakalamaz.

## Ne yapacaksın

```python
Supervisor(gw, store)
  .escalate(episode: Episode) -> str        # proaktif açılış — beat 1
  .talk(operator_text: str) -> str     # bir diyalog turu
  .pending_approval() -> ActionRecord | None
  .approve(action_id: int, approved: bool) -> dict
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_supervisor.py`

```python
import json
from unittest.mock import Mock, patch

from gozcu.agents.supervisor import Supervisor, uncertainty_note
from gozcu.gateway import Response
from gozcu.models import (ActionRecord, Episode, RiskAssessment, Signals)
from gozcu.store import Store


def _tool(name, params):
    return Response(tool_calls=[{"id": "c1", "type": "function",
                                  "function": {"name": name,
                                               "arguments": json.dumps(params)}}])


def _setup(yanitlar):
    gw = Mock(); gw.ask.side_effect = yanitlar
    store = Store(":memory:")
    e = Episode(start_ts=192.0, phase="development",
               summary_tr="istif aracı devrildi, yerde hareketsiz kişi",
               preliminary_risk="Kritik")
    e.id = store.create_episode(e)
    return gw, store, e


def _risk(e):
    return RiskAssessment(episode_id=e.id, level="Kritik",
                             rationale_tr="g", preventable=True)


def test_uncertainty_note_names_what_the_camera_cannot_see():
    n = uncertainty_note(Signals(vanished_tracks=[3], person_count=1))
    assert n and "göremiyor" in n.lower()
    assert uncertainty_note(Signals(person_count=1)) == ""


def test_escalation_queries_the_shift_before_speaking():
    gw, store, e = _setup([
        _tool("query_shift_personnel",
              {"zone": "B-Hattı", "at_time": "03:12"}),
        Response(content="03:12 — B-Hattı'nda istif aracı devrildi. Risk: Kritik."),
        Response(content="uygun"),
    ])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)):
        message = Supervisor(gw, store).escalate(e)
    assert "query_shift_personnel" in [a.tool_name for a in store.actions()]
    assert "03:12" in message


def test_critical_escalation_is_not_filtered_by_the_guard():
    gw, store, e = _setup([
        Response(content="KRİTİK: yerde hareketsiz kişi var."),
    ])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.screen") as g:
        Supervisor(gw, store).escalate(e)
    assert g.call_args.kwargs["critical"] is True


def test_line_stop_is_held_for_approval_and_not_executed():
    gw, store, _ = _setup([
        _tool("halt_production_line", {"line_id": "B", "rationale": "devrilme"}),
        Response(content="B-Hattı'nı durdurmamı ister misiniz?"),
        Response(content="uygun"),
    ])
    n = Supervisor(gw, store)
    n.talk("durumu özetle")
    pending_rows = n.pending_approval()
    assert pending_rows is not None and pending_rows.tool_name == "halt_production_line"


def test_approving_does_not_create_a_second_pending_approval():
    gw, store, _ = _setup([
        _tool("halt_production_line", {"line_id": "B", "rationale": "x"}),
        Response(content="onay?"), Response(content="uygun"),
    ])
    n = Supervisor(gw, store)
    n.talk("dur")
    n.approve(n.pending_approval().id, True)
    assert n.pending_approval() is None
    assert [a.approval for a in store.actions()].count("pending") == 0


def test_refusing_marks_the_action_rejected_and_does_not_run_it():
    gw, store, _ = _setup([
        _tool("halt_production_line", {"line_id": "B", "rationale": "x"}),
        Response(content="onay?"), Response(content="uygun"),
    ])
    n = Supervisor(gw, store)
    n.talk("dur")
    onceki = len(store.actions())
    n.approve(n.pending_approval().id, False)
    assert len(store.actions()) == onceki
    assert store.actions()[-1].approval == "rejected"


def test_correction_is_recorded_and_cascades_to_the_episode_summary():
    gw, store, e = _setup([
        _tool("correct_observation",
              {"episode_id": 1, "field": "event_type", "old": "araç devrildi",
               "new": "yük düştü", "rationale": "operatör gözlemi"}),
        Response(content="Anlaşıldı, kaydı güncelledim."),
        Response(content="uygun"),
    ])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)):
        Supervisor(gw, store).talk("araç devrilmedi, yük düştü")
    assert store.corrections(1)[0].new == "yük düştü"
    assert "yük düştü" in store.episodes()[0].summary_tr


def test_correction_re_runs_the_risk_assessment():
    gw, store, e = _setup([
        _tool("correct_observation",
              {"episode_id": 1, "field": "event_type", "old": "a", "new": "b",
               "rationale": "g"}),
        Response(content="tamam"), Response(content="uygun"),
    ])
    with patch("gozcu.agents.supervisor.assess_risk",
               return_value=_risk(e)) as r:
        Supervisor(gw, store).talk("düzeltme")
    r.assert_called_once()


def test_open_incident_is_appended_to_every_operator_turn():
    gw, store, _ = _setup([Response(content="cevap"), Response(content="uygun")])
    Supervisor(gw, store).talk("dur, başka bir şey soracağım")
    prompt_text = gw.ask.call_args_list[0].args[1][-1]["content"]
    assert "Açık olay" in prompt_text


def test_dialogue_turns_are_recorded_both_sides():
    gw, store, _ = _setup([Response(content="Anlaşıldı."), Response(content="uygun")])
    Supervisor(gw, store).talk("state nedir?")
    assert [s.role for s in store.dialogue()] == ["operator", "supervisor"]


def test_tool_loop_terminates_instead_of_spinning_forever():
    gw, store, _ = _setup([_tool("site_alarm", {"zone": "B",
                                                   "level": "yuksek"})] * 12)
    cevap = Supervisor(gw, store).talk("alarm çal")
    assert cevap and gw.ask.call_count <= 6
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_supervisor.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/supervisor.py` yaz

```python
import json

from gozcu.agents.router import mmss
from gozcu.agents.risk import assess_risk
from gozcu.memory import search_timeline
from gozcu.models import DialogueTurn, Correction, Episode, Signals
from gozcu.tools.registry import TOOL_SCHEMAS, call_tool

MAX_TURNS = 4

SYSTEM_PROMPT = """Sen bir savunma sanayi üretim tesisinin kontrol odasında görevli
vardiya amirisin. Operatörle Türkçe konuşuyorsun.

Nasıl davranırsın:
- Kritik bir olay gördüğünde SORULMADAN önce sen haber verirsin
- Konuşmadan önce gerekli sorguları yaparsın (vardiya, ekipman geçmişi)
- Kameradan göremediğin bir şeyi UYDURMAZSIN, operatöre sorarsın
- Operatör seni düzeltirse gozlem_duzelt aracını çağırırsın
- Operatör konuyu değiştirirse cevaplarsın ama AÇIK OLAYI HATIRLATIRSIN
- Geri dönüşü zor aksiyonlarda (hat durdurma) İZİN İSTERSİN
- Kısa cümleler kurarsın. Saha terminolojisi kullanırsın.

Zaman damgalarını MM:SS biçiminde yazarsın."""

SUPERVISOR_TOOLS = [
    {"type": "function", "function": {
        "name": "search_timeline",
        "description": "Geçmiş olay arşivinde anlamsal arama yapar.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "correct_observation",
        "description": "Operatörün düzeltmesini kalıcı olarak kaydeder.",
        "parameters": {"type": "object", "properties": {
            "episode_id": {"type": "integer"}, "field": {"type": "string"},
            "old": {"type": "string"}, "new": {"type": "string"},
            "rationale": {"type": "string"}},
            "required": ["episode_id", "field", "old", "new", "rationale"]}}},
    {"type": "function", "function": {
        "name": "request_risk_assessment",
        "description": "Bir olay için iş güvenliği risk analizi ister.",
        "parameters": {"type": "object",
                       "properties": {"episode_id": {"type": "integer"}},
                       "required": ["episode_id"]}}},
    {"type": "function", "function": {
        "name": "generate_root_cause_report",
        "description": "Kapanan olay için kök reason raporu üretir.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def uncertainty_note(signals: Signals) -> str:
    """Kameranın göremediğini açıkça adlandırır.

    Beat 2 buna dayanıyor: 'yerdeki kişi hareket ediyor mu, göremiyorum'
    sorusunu prompt umuduna bırakmak yerine, sinyallerden türetilmiş gerçek
    bir belirsizlik notuyla güvenilir şekilde tetikliyoruz.
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
    def __init__(self, gw, store) -> None:
        self.gw, self.store = gw, store
        self.history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # -- iç araçlar ---------------------------------------------------------

    def _apply_correction(self, p: dict) -> dict:
        """Düzeltmeyi kaydeder VE yayar: epizot özeti güncellenir, risk
        yeniden koşar. Sadece tabloya yazmak, hiçbir şey yapmamaktır."""
        self.store.save_correction(Correction(ts=0.0, **p))
        episode = next((e for e in self.store.episodes()
                       if e.id == p["episode_id"]), None)
        if episode is None:
            return {"state": "kaydedildi", "uyari": "episode bulunamadı"}

        new_summary = episode.summary_tr.replace(p["old"], p["new"])
        if new_summary == episode.summary_tr:
            new_summary = f"{episode.summary_tr} (operatör düzeltmesi: {p['new']})"
        self.store.update_episode(episode.id, summary_tr=new_summary[:600])

        refreshed = next(e for e in self.store.episodes() if e.id == episode.id)
        risk = assess_risk(self.gw, self.store, refreshed)
        return {"state": "kaydedildi", "new_summary": new_summary,
                "yeni_risk": risk.level}

    def _internal_tool(self, name: str, p: dict):
        if name == "search_timeline":
            return {"sonuclar": [e.model_dump() for e in
                                 search_timeline(self.gw, self.store,
                                                     p["query"])]}
        if name == "correct_observation":
            return self._apply_correction(p)
        if name == "request_risk_assessment":
            episode = next((e for e in self.store.episodes()
                           if e.id == p["episode_id"]), None)
            if episode is None:
                return {"hata": "episode bulunamadı"}
            return assess_risk(self.gw, self.store, episode).model_dump()
        if name == "generate_root_cause_report":
            # Geç import: Görev 12 aynı gün başka biri tarafından yazılıyor,
            # modül seviyesinde import etmek bu görevi ona bağlardı.
            from gozcu.agents.reporter import generate_root_cause_report
            return generate_root_cause_report(self.gw, self.store).model_dump()
        return None

    def _run_tool(self, cagri: dict) -> dict:
        name = cagri["function"]["name"]
        try:
            p = json.loads(cagri["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {"hata": "params okunamadı"}
        ic = self._internal_tool(name, p)
        if ic is not None:
            return ic
        try:
            return call_tool(self.store, name, p, actor="agent")
        except KeyError:
            return {"hata": f"bilinmeyen araç: {name}"}

    # -- diyalog ------------------------------------------------------------

    def _turn_loop(self, critical: bool) -> str:
        from gozcu.guard import screen  # geç import — Görev 13 aynı gün

        tools = TOOL_SCHEMAS + SUPERVISOR_TOOLS
        for _ in range(MAX_TURNS):
            response = self.gw.ask("main", self.history, tools=tools)
            if not response.tool_calls:
                text = screen(self.gw, response.content, critical=critical)
                self.history.append({"role": "assistant", "content": text})
                self.store.save_dialogue(
                    DialogueTurn(ts=0.0, role="supervisor", text=text))
                return text

            self.history.append({"role": "assistant",
                                "tool_calls": response.tool_calls})
            for cagri in response.tool_calls:
                result = self._run_tool(cagri)
                self.history.append({
                    "role": "tool", "tool_call_id": cagri.get("id", "c"),
                    "content": json.dumps(result, ensure_ascii=False,
                                          default=str)})

        message = "Yanıt üretilemedi; olay kaydı korunuyor."
        self.store.save_dialogue(
            DialogueTurn(ts=0.0, role="system", text=message))
        return message

    def escalate(self, episode: Episode) -> str:
        risk = assess_risk(self.gw, self.store, episode)
        observations = [g for g in self.store.observations()
                     if episode.start_ts <= g.ts <= (episode.end_ts
                                                        or episode.start_ts)]
        signals = observations[-1].signals if observations else Signals()
        not_ = uncertainty_note(signals)

        self.history.append({
            "role": "user",
            "content": f"[SİSTEM] {mmss(episode.start_ts)} — critical olay: "
                       f"{episode.summary_tr}. Risk: {risk.level}. "
                       f"Gerekçe: {risk.rationale_tr}\n{not_}\n"
                       f"Operatöre kendin haber ver. Belirsizlik varsa ask."})
        return self._turn_loop(critical=risk.level in ("Yüksek", "Kritik"))

    def talk(self, operator_text: str) -> str:
        self.store.save_dialogue(
            DialogueTurn(ts=0.0, role="operator", text=operator_text))
        open_ep = self.store.open_episode()
        ek = (f"\n[SİSTEM] Açık olay: episode {open_ep.id} — {open_ep.summary_tr}"
              if open_ep else "")
        self.history.append({"role": "user", "content": operator_text + ek})
        return self._turn_loop(critical=False)

    # -- onaylar ------------------------------------------------------------

    def pending_approval(self):
        pending_rows = [a for a in self.store.actions()
                    if a.approval == "pending"]
        return pending_rows[-1] if pending_rows else None

    def approve(self, action_id: int, approved: bool) -> dict:
        record = next(a for a in self.store.actions() if a.id == action_id)
        if not approved:
            self.store.set_action_approval(action_id, "rejected")
            return {"state": "rejected"}
        # onay_durumu geçilmezse cagir yeni bir "bekliyor" satırı doğurur ve
        # onay çubuğu hiç kapanmaz.
        result = call_tool(self.store, record.tool_name, record.params,
                      actor="operator", approval="approved")
        self.store.set_action_approval(action_id, "approved")
        return {"state": "approved", **result}
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_supervisor.py -v
```
Beklenen: 11 passed

### 5. Commit

```bash
git add gozcu/agents/supervisor.py tests/test_supervisor.py
git commit -m "feat: Nöbetçi supervisor with tool loop, correction cascade and approvals"
```

## Doğrulama

```bash
uv run pytest tests/test_supervisor.py -v
```
Beklenen: **11 passed**

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
