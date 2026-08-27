"""Görev 2 — `gozcu/ui/view.py`: depodan veri derleyicileri.

`console.py`'nin saf katmanının ikizi: aynı kural, dönüş tipi Markdown/satır
listesi yerine sözlük/liste. Bu dosya `test_console.py`'den GÖÇ EDEN 32 testi
(kural aynı, artık veriye bakıyor) ve 7 yeni testi taşıyor — iki test adı
(`test_kpi_numbers_use_turkish_decimal_commas`,
`test_a_crashed_run_does_not_fabricate_an_empty_root_cause_report`) her iki
kümede de birebir aynı senaryoyu sınadığı için tek fonksiyonda birleşti.

Ağ yok: sahte süpervizör, sahte ağ geçidi, bellek içi depo.
"""

import typing

from benchmark.kpi import DEGRADED, MEASURED, UNMEASURED
from gozcu.models import (ActionRecord, Detail, EventSummary, Handoff,
                          PipelineOutput, RiskLevel)
from gozcu.store import Store
from gozcu.ui import view
from tests.doubles import FakeSupervisor as _FakeSupervisor


# -- ikizler ------------------------------------------------------------------

class _FakeGateway:
    """Yalnız `is_degraded` taşıyan ağ geçidi ikizi.

    `tier` **kaydediliyor**: durum rozetinin doğru çağrısı çıplak
    `is_degraded()` ve tek bir kademe sorulursa rozet yanlış cevap verir.
    """

    def __init__(self, broken_any=False, broken_vlm=False):
        self.broken_any, self.broken_vlm = broken_any, broken_vlm
        self.asked: list = []

    def is_degraded(self, tier=None) -> bool:
        self.asked.append(tier)
        return self.broken_any if tier is None else self.broken_vlm


def _pending(tool_name="halt_production_line", action_id=7):
    return ActionRecord(id=action_id, ts=192.0, tool_name=tool_name,
                        params={"line_id": "B-Hattı"},
                        result={"state": "awaiting_approval"},
                        actor="agent", approval="pending")


def _action(ts=30.0, tool="radio_call", params=None, result=None,
            actor="agent", approval="not_required", caller="supervisor"):
    return ActionRecord(ts=ts, tool_name=tool, params=params or {},
                        result=result or {}, actor=actor, approval=approval,
                        caller=caller)


def _output(root_cause=None, detail=True):
    return PipelineOutput(
        summary="B-Hattında istif aracı devrildi.", risk="Kritik",
        events=[EventSummary(time="03:12", event="devrildi")],
        actions=["Sağlık ekibini çağır"],
        detail=Detail(root_cause_report=root_cause) if detail else None)


# =============================================================================
# Adım 1 — yeni testler (kırmızıdan yeşile)
# =============================================================================

def test_unmeasured_is_written_not_hidden():
    """Deponun kuralı: 0 'ölçtük, sıfır çıktı' demek. Ölçülemeyeni
    gizlemek okuyanına o metriğin var olmadığını düşündürür."""
    assert view.pct(None) == view.KPI_UNMEASURED
    assert view.pct(0.0) == "%0,0"


def test_kpi_numbers_use_turkish_decimal_commas():
    """Biçimleme SUNUCUDA — tarayıcıda olsaydı test kapsamı dışına
    düşerdi ve panel iki belgeyi ayrı dillere bölerdi.

    `console.py:907`'deki `kpi_numbers_use_turkish_decimal_commas` ile
    birebir aynı senaryo — göç eden test burada birleşti.
    """
    assert view.pct(0.724) == "%72,4"
    assert "." not in view.pct(0.724)
    assert view.pct(0.991) == "%99,1"


def test_the_run_badge_uses_only_the_kpi_modules_values():
    assert view.RUN_BADGE_VALUES == (MEASURED, DEGRADED, UNMEASURED)


def test_perception_kpis_are_available_before_any_run():
    """Algı ölçümü koşudan bağımsız — çevrimdışı ölçüldü (şartname §4)."""
    payload = view.perception_payload()
    assert payload is not None
    assert "blocks" in payload


def test_a_crashed_run_does_not_fabricate_an_empty_root_cause_report():
    """`detail=None` "o katman hiç koşmadı" demek; boş bir rapor UYDURULMUYOR
    — fonksiyon `None` döner, sahte bir "kayda değer olay yok" raporu değil.

    `console.py:269`'daki aynı adlı test ile aynı senaryo — göç eden test
    burada birleşti.
    """
    class _Output:
        detail = None
    assert view.root_cause_payload(_Output()) is None


def test_tool_rows_put_the_outcome_first():
    """Bir aracın çalışmadığını gizleyen şerit, çalıştığını iddia eder."""
    action = ActionRecord(id=1, ts=12.0, tool_name="site_alarm",
                          params={"zone": "A"},
                          result={"alarm_id": "x",
                                  "siren_state": "zone_unresolved"},
                          actor="agent", approval="not_required")
    row = view.tool_rows([action])[0]
    assert list(row["result"])[0] == "siren_state"


def test_the_wire_risk_levels_match_the_schema_exactly():
    """Prompt/şema ayrışması bu depoyu bir kez sessizce öldürdü."""
    assert set(view.RISK_LEVELS) == set(typing.get_args(RiskLevel))


# =============================================================================
# Kural 7: rozetler — `console.status_badges`'tan göç
# =============================================================================

def test_the_status_badge_asks_the_bare_degradation_flag(monkeypatch):
    """Rozet "herhangi bir kademe bozuk mu" demek — kademe adı geçilmemeli."""
    monkeypatch.setattr(view, "memory_backend", lambda: "qdrant")
    monkeypatch.setattr(view, "run_status", lambda store: "measured")
    gw = _FakeGateway(broken_any=True, broken_vlm=False)
    result = view.badges(gw, Store(":memory:"))
    assert gw.asked == [None]
    assert result["gateway"] == "degraded"


def test_a_healthy_run_shows_all_three_badges(monkeypatch):
    monkeypatch.setattr(view, "memory_backend", lambda: "local")
    monkeypatch.setattr(view, "run_status", lambda store: "unmeasured")
    result = view.badges(_FakeGateway(), Store(":memory:"))
    assert result == {"gateway": "healthy", "memory": "local",
                      "run": "unmeasured"}


def test_the_memory_badge_reports_the_real_backend(monkeypatch):
    """Sessiz düşüşün kendisi kabul edilebilir, görünmezliği değil."""
    monkeypatch.setattr(view, "run_status", lambda store: "measured")
    monkeypatch.setattr(view, "memory_backend", lambda: "qdrant")
    assert view.badges(_FakeGateway(), Store(":memory:"))["memory"] == "qdrant"
    monkeypatch.setattr(view, "memory_backend", lambda: "local")
    assert view.badges(_FakeGateway(), Store(":memory:"))["memory"] == "local"


def test_the_run_status_badge_comes_from_the_kpi_module():
    """Boş depo ölçülemez bir koşudur; rozet bunu söylemeli."""
    assert view.badges(_FakeGateway(), Store(":memory:"))["run"] == "unmeasured"


def test_the_badges_omit_the_archive_count_until_seeding_has_run():
    """`None` "sıfır" DEĞİL, "henüz tohumlanmadı"."""
    assert "archive" not in view.badges(_FakeGateway(), Store(":memory:"))


def test_the_badges_report_a_zero_archive_as_zero():
    """Tohumlama sessizce başarısız olduysa tek uyarı bu."""
    result = view.badges(_FakeGateway(), Store(":memory:"), archive=0)
    assert result["archive"] == 0


# =============================================================================
# Kural 7: onay çubuğu — `console.approval_text`'ten göç
# =============================================================================
#
# `apply_approval`ın 7 testi Görev 11'de `test_console.py`'den BURAYA taşındı
# (triyajda `taşı`): iddia birebir aynı, yalnız çağrı yolu
# `console.apply_approval` yerine `view.apply_approval`. Veri sözleşmesi
# (`tuple[str, object]`) hiç değişmedi.

def test_an_approved_halt_says_the_line_actually_stopped():
    """`state="approved"` onayın işlendiğini söyler, hattın durduğunu değil.

    Hattın gerçekten durduğu İÇ İÇE duran araç sonucunda yazıyor.
    """
    nobetci = _FakeSupervisor({"state": "approved", "action_id": 7,
                               "result": {"state": "halted",
                                          "line": "B-Hattı"}})
    text, pending = view.apply_approval(nobetci, 7, True)
    assert view.HALTED_NOTE in text
    assert pending is None
    assert nobetci.calls == [(7, True)]


def test_an_approved_action_that_did_not_halt_is_not_reported_as_halted():
    """Onay işlendi ama araç hattı durdurmadı — bu iki farklı şey."""
    nobetci = _FakeSupervisor({"state": "approved", "action_id": 7,
                               "result": {"state": "awaiting_approval"}})
    text, _ = view.apply_approval(nobetci, 7, True)
    assert view.HALTED_NOTE not in text
    assert view.NOT_HALTED_NOTE.split("{")[0] in text


def test_a_rejected_action_says_nothing_was_called():
    nobetci = _FakeSupervisor({"state": "rejected", "action_id": 7})
    text, _ = view.apply_approval(nobetci, 7, False)
    assert view.REJECTED_NOTE in text
    assert nobetci.calls == [(7, False)]


def test_an_unknown_action_is_reported_not_raised():
    nobetci = _FakeSupervisor({"state": "unknown_action",
                               "error": "aksiyon bulunamadı: 99"})
    text, _ = view.apply_approval(nobetci, 99, True)
    assert view.UNKNOWN_ACTION_NOTE in text


def test_an_already_decided_action_is_reported_not_raised():
    nobetci = _FakeSupervisor({"state": "not_pending", "approval": "approved"})
    text, _ = view.apply_approval(nobetci, 7, True)
    assert view.NOT_PENDING_NOTE.split("{")[0] in text
    assert "approved" in text


def test_an_unexpected_state_is_still_shown_to_the_operator():
    """Sözleşme büyürse çubuk sessiz kalmamalı."""
    nobetci = _FakeSupervisor({"state": "brand_new"})
    text, _ = view.apply_approval(nobetci, 7, True)
    assert "brand_new" in text


def test_the_bar_is_refreshed_from_the_supervisor_after_every_decision():
    """Karar sonrası çubuk yeniden okunmazsa bayat satırın üzerinde açık kalır."""
    still = _pending()
    nobetci = _FakeSupervisor({"state": "rejected", "action_id": 7},
                              pending_after=still)
    _, pending = view.apply_approval(nobetci, 7, False)
    assert nobetci.pending_reads == 1
    assert pending is still


def test_the_pending_payload_names_the_tool_and_is_none_when_empty():
    assert view.pending_payload(None) is None
    payload = view.pending_payload(_pending())
    assert payload == {"action_id": 7, "tool": "halt_production_line",
                       "params": {"line_id": "B-Hattı"}}


# =============================================================================
# Teslim edilen yük — `console.payload_json`/`root_cause_markdown`'dan göç
# =============================================================================

def test_the_four_keys_are_present_in_the_payload():
    payload = view.payload_dict(_output())
    for key in ("summary", "events", "risk", "actions"):
        assert key in payload


def test_no_run_yet_returns_none_not_an_empty_payload():
    assert view.payload_dict(None) is None
    assert view.root_cause_payload(None) is None


def test_a_run_without_a_report_returns_none_not_an_empty_dict():
    """Boş bir rapor UYDURULMUYOR: koşu tamam ama kayda değer olay yoksa da
    `None` döner — çöken katmanla (`test_a_crashed_run_...`) aynı `None`,
    ama HANGİ Türkçe mesajın gösterileceği kaybolmuyor: `root_cause_state`
    bu ikisini ayrı tutuyor (bkz. `TestRootCauseState`)."""
    assert view.root_cause_payload(_output(root_cause=None)) is None


def test_a_real_report_renders_all_five_sections():
    report = {"what_happened": "B-Hattında istif aracı devrildi.",
              "probable_root_cause": "Olası fren arızası.",
              "actions_taken": ["Sağlık ekibi çağrıldı."],
              "prevention_recommendations": ["Fren bakımı öne alınmalı."],
              "confidence_limits": "Kamera sesi duymuyor."}
    payload = view.root_cause_payload(_output(root_cause=report))
    assert payload == report


# =============================================================================
# Kök nedenin YOKLUĞUNUN nedeni — `root_cause_payload`'ın `None`'da
# birleştirdiği üç durumu `root_cause_state` ayrı tutuyor mu?
# =============================================================================

class TestRootCauseState:
    """`console.root_cause_markdown`'ın üç ayrı yokluk kuralı
    (`console.py:442-448`) veri katmanında da kaybolmamalı — dört dal da
    tek tek sabitleniyor, artı eşlemenin dördünü de kapsadığı."""

    def test_no_run_state(self):
        assert view.root_cause_state(None) == "no_run"

    def test_crashed_state(self):
        assert view.root_cause_state(_output(detail=False)) == "crashed"

    def test_no_notable_event_state(self):
        assert view.root_cause_state(_output(root_cause=None)) == "no_notable_event"

    def test_ok_state(self):
        report = {"what_happened": "B-Hattında istif aracı devrildi."}
        assert view.root_cause_state(_output(root_cause=report)) == "ok"

    def test_the_message_mapping_covers_every_state_the_function_can_return(self):
        """Liste elle tekrar yazılmıyor — `ROOT_CAUSE_STATES`'ten okunuyor,
        `RUN_STATES` ile aynı kural."""
        assert set(view.ROOT_CAUSE_MESSAGES) == set(view.ROOT_CAUSE_STATES)

    def test_each_state_maps_to_its_own_turkish_constant(self):
        assert view.ROOT_CAUSE_MESSAGES["no_run"] == view.NO_RUN_YET
        assert view.ROOT_CAUSE_MESSAGES["crashed"] == view.CRASHED_RUN
        assert view.ROOT_CAUSE_MESSAGES["no_notable_event"] == view.NO_ROOT_CAUSE
        assert view.ROOT_CAUSE_MESSAGES["ok"] is None


class TestPayloadAbsenceMessage:
    """Çıktının YOKLUĞU koşunun DURUMUNA göre farklı bir cümle.

    Son inceleme turunun bulgusu: koşu çöktüğünde ekran ÜÇ ayrı şey
    söylüyordu — afiş "koşu hata ile sonuçlandı", karar paneli son
    değerinde donmuş "sürüyor", JSON modalı da `{"detail": "Analiz henüz
    koşmadı."}`. Üçüncüsü açıkça yanlış: analiz KOŞTU, yalnız bitiremedi.
    """

    def test_a_failed_run_does_not_claim_it_never_ran(self):
        message = view.payload_absence_message("failed")
        assert message == view.FAILED_RUN_PAYLOAD
        assert message != view.NO_RUN_YET

    def test_an_abandoned_run_says_its_output_was_discarded(self):
        message = view.payload_absence_message("abandoned")
        assert message == view.ABANDONED_RUN_PAYLOAD
        assert message != view.NO_RUN_YET

    def test_a_run_that_really_has_not_run_still_says_so(self):
        for state in ("idle", "running", "paused", "intervened"):
            assert view.payload_absence_message(state) == view.NO_RUN_YET

    def test_every_message_answers_a_real_run_state(self):
        """Tablo `RUN_STATES`'ten sapamaz — var olmayan bir duruma cevap
        veren bir cümle sonsuza dek ölü kalırdı."""
        from gozcu.ui.session import RUN_STATES

        assert set(view.PAYLOAD_ABSENCE_MESSAGES) <= set(RUN_STATES)

    def test_the_three_sentences_are_distinct(self):
        assert len({view.NO_RUN_YET, view.FAILED_RUN_PAYLOAD,
                    view.ABANDONED_RUN_PAYLOAD}) == 3


class TestRootCauseFieldLabels:
    """Rapor bölümlerinin başlıkları da tek kaynaktan — `js/trace.js`
    kendi çeviri tablosunu TUTMUYOR (`window_outcome_labels` ile aynı
    ilke)."""

    def test_the_labels_cover_exactly_the_report_fields(self):
        report = {"what_happened": "devrildi", "probable_root_cause": "fren",
                  "actions_taken": ["sağlık ekibi"],
                  "prevention_recommendations": ["bakım"],
                  "confidence_limits": "kamera sesi duymuyor"}
        payload = view.root_cause_payload(_output(root_cause=report))
        assert set(view.ROOT_CAUSE_FIELD_LABELS) == set(payload)

    def test_the_order_is_the_retired_consoles_order(self):
        """Emekliye ayrılan `console.root_cause_markdown` bölümleri bu
        sırayla basıyordu; ekran sırası bir sözleşme, sözlük ekleme
        sırasını koruyor ve `trace.js` onu OKUYOR."""
        assert list(view.ROOT_CAUSE_FIELD_LABELS) == [
            "what_happened", "probable_root_cause", "actions_taken",
            "prevention_recommendations", "confidence_limits"]

    def test_every_label_is_turkish_text_not_a_bare_key(self):
        for key, label in view.ROOT_CAUSE_FIELD_LABELS.items():
            assert label.strip() and label != key


class TestTheRunInProgressIsNotOneOfTheFourAbsences:
    """"Koşu ŞU ANDA sürüyor" dört durumdan hiçbiri değil.

    `root_cause_state`'in dördü de BİTMİŞ bir koşuya bakıyor. Koşu
    sürerken `output` daha `None`, yani fonksiyon `"no_run"` diyor ve
    panel koşunun ortasında "Analiz henüz koşmadı." basıyordu — üç
    yokluğun birbirine karışmasını önlemek için var olan panelde, ekranın
    yalanı. Çözüm sözleşmeyi genişletmek DEĞİL: ekran koşu canlıyken
    soruyu hiç sormuyor (`js/trace.js`) ve bu cümleyi basıyor.
    """

    def test_the_four_states_are_untouched(self):
        """Görev 2'nin kararı ve testleri bu dördü sabitliyor — beşinci
        bir durum EKLENMEDİ."""
        assert view.ROOT_CAUSE_STATES == ("no_run", "crashed",
                                          "no_notable_event", "ok")
        assert set(view.ROOT_CAUSE_MESSAGES) == set(view.ROOT_CAUSE_STATES)

    def test_the_pending_sentence_is_not_any_of_the_absence_sentences(self):
        assert view.ROOT_CAUSE_PENDING not in set(view.ROOT_CAUSE_MESSAGES.values())
        assert view.ROOT_CAUSE_PENDING != view.NO_RUN_YET

    def test_the_pending_sentence_says_the_run_is_still_going(self):
        """"Henüz koşmadı" ile "hâlâ koşuyor" aynı cümleye düşerse ekran
        yine yanlış bir şey söyler."""
        assert "sürüyor" in view.ROOT_CAUSE_PENDING


# =============================================================================
# Devir defteri — `console.handoff_rows`'tan göç
# =============================================================================

def test_the_handoff_ledger_stamps_video_time():
    rows = view.handoff_rows([Handoff(ts=192.0, source_agent="orchestrator",
                                      target_agent="supervisor",
                                      reason="hız eşiği aşıldı",
                                      confidence=0.9,
                                      payload_ref="window@192.0")])
    assert rows == [{"ts": "03:12", "source": "orchestrator", "target": "supervisor",
                     "reason": "hız eşiği aşıldı", "confidence": "güven 0,90"}]


def test_the_handoff_ledger_formats_confidence_the_same_way_as_the_feed():
    """`format_confidence` TEK biçimlendirme yeri (`gozcu/ui/feed.py`) —
    `/handoffs` kendi virgülsüz float'ını basmıyor, SSE besleme yoluyla
    (`server.py::_dump_feed_entry`) AYNI fonksiyondan geçiyor. İki panel
    aynı güveni iki farklı biçimde göstermesin diye."""
    from gozcu.ui.feed import format_confidence

    row = view.handoff_rows([Handoff(ts=0.0, source_agent="orchestrator",
                                     target_agent="interpreter", reason="x",
                                     confidence=0.8375,
                                     payload_ref="window@0.0")])[0]
    assert row["confidence"] == format_confidence(0.8375)


# =============================================================================
# Araç şeridi — `console.tool_rows`'tan göç
# =============================================================================

class TestToolRows:
    def test_empty_ledger_says_so(self):
        assert view.tool_rows([]) == []

    def test_timestamp_is_video_time(self):
        row = view.tool_rows([_action(ts=90.0)])[0]
        assert row["ts"] == "01:30"

    def test_tool_name_is_shown_verbatim(self):
        """Araç adı jürinin aradığı şey; süslenmiyor."""
        row = view.tool_rows([_action(tool="dispatch_medical")])[0]
        assert row["tool"] == "dispatch_medical"

    def test_params_are_available_as_a_dict(self):
        row = view.tool_rows([_action(params={"unit": "vardiya",
                                              "message": "acil"})])[0]
        assert row["params"] == {"unit": "vardiya", "message": "acil"}

    def test_empty_params_are_an_empty_dict_not_none(self):
        assert view.tool_rows([_action(params={})])[0]["params"] == {}

    def test_result_is_rendered(self):
        row = view.tool_rows([_action(result={"ref": "ISG-0007"})])[0]
        assert row["result"]["ref"] == "ISG-0007"

    def test_approval_states_are_turkish_and_distinct(self):
        states = [view.tool_rows([_action(approval=a)])[0]["approval"]
                  for a in ("not_required", "pending", "approved", "rejected")]
        assert len(set(states)) == 4
        assert all(s for s in states)

    def test_operator_actor_is_distinguishable_from_agent(self):
        """Operatörün tetiklediği çağrı, ajanın kendi kararıyla aynı
        görünmemeli — %20'lik otonomi kriteri tam olarak bu farkı soruyor."""
        agent = view.tool_rows([_action(actor="agent")])[0]
        operator = view.tool_rows([_action(actor="operator")])[0]
        assert agent["actor"] != operator["actor"]

    def test_rows_are_sorted_by_time(self):
        rows = view.tool_rows([_action(ts=90.0), _action(ts=30.0)])
        assert [r["ts"] for r in rows] == ["00:30", "01:30"]

    def test_row_has_exactly_the_declared_fields(self):
        row = view.tool_rows([_action()])[0]
        assert set(row) == {"ts", "tool", "params", "result", "approval",
                            "actor", "actor_raw", "caller"}

    def test_caller_is_the_agent_that_actually_called_the_tool(self):
        """`caller` (hangi ajan) `actor`'dan (insan mı makine mi) AYRI bir
        soru — risk analisti kendi soruşturma araçlarını `assess_risk`
        içinde çağırıyor, süpervizör daha ağzını açmadan. Tek bir "ajan"
        etiketi bu çağrıyı süpervizöre yazardı ve zincir hakkında yalan
        söylerdi (bkz. `gozcu/models.py::ActionRecord` docstring)."""
        row = view.tool_rows([_action(caller="risk_analyst")])[0]
        assert row["caller"] == "risk_analyst"
        assert row["caller"] != "supervisor"

    def test_operator_action_is_attributed_to_operator_not_supervisor(self):
        """Operatörün araç çağrısı `caller="supervisor"` (varsayılan) içeriyorsa
        bile, Şeffaflık paneli onu operatöre yazmalı. JS'deki `callerFor`
        logiki `actor_raw` ham enum'ını çekmeli — Türkçe rozet değişirse
        sessizce kırılmayacak (bkz. `trace.js::callerFor` ve `sse.js::setBadge`
        desenini — raw değer logik, label ekran)."""
        operator_row = view.tool_rows([_action(actor="operator",
                                               caller="supervisor")])[0]
        assert operator_row["actor_raw"] == "operator"  # Ham enum JS tarafından
        assert operator_row["actor"] == "👤 operatör"  # Ekran etiketi
        assert operator_row["caller"] == "supervisor"  # Sunucu alanı (JS bunu görmez)


class TestToolSummary:
    def test_no_calls_is_not_an_empty_string(self):
        """Boş bir sayaç 'araçlar çalışmıyor' gibi okunur."""
        assert view.NO_TOOLS_YET in view.tool_summary([])["text"]

    def test_counts_distinct_tools_against_the_catalogue(self):
        summary = view.tool_summary([_action(tool="radio_call"),
                                     _action(tool="radio_call"),
                                     _action(tool="site_alarm")])
        assert summary["used_tools"] == 2
        assert "7 araçtan 2" in summary["text"]

    def test_counts_total_calls(self):
        summary = view.tool_summary([_action(), _action(), _action()])
        assert summary["total_calls"] == 3

    def test_counts_approval_gated_calls(self):
        summary = view.tool_summary([
            _action(tool="halt_production_line", approval="approved"),
            _action(tool="radio_call")])
        assert summary["gated_calls"] == 1

    def test_catalogue_size_comes_from_the_registry(self):
        """Sayı elle yazılırsa yeni bir araç eklendiğinde sessizce yalan olur."""
        from gozcu.tools.registry import TOOLS
        assert view.tool_summary([_action()])["catalogue_size"] == len(TOOLS)


# =============================================================================
# KPI paneli — `console.kpi_markdown`/`perception_markdown`'dan göç
# =============================================================================

class TestKpiPanel:
    def test_unmeasured_is_never_rendered_as_zero(self):
        """`benchmark/kpi.py` ile aynı sözleşme: 0 'ölçtük, sıfır çıktı'."""
        payload = view.kpi_payload(Store(":memory:"))
        assert payload["decision"]["vlm_trigger_rate"] == view.KPI_UNMEASURED
        assert payload["decision"]["turkish_output_rate"] == view.KPI_UNMEASURED
        assert payload["decision"]["correction_propagation"] == view.KPI_UNMEASURED
        assert payload["decision"]["vision_tokens"] == view.KPI_UNMEASURED
        assert payload["performance"]["elapsed_s"] == view.KPI_UNMEASURED
        assert payload["performance"]["timestamp_drift_s"] == view.KPI_UNMEASURED
        assert "%0" not in str(payload)

    def test_kpi_payload_carries_all_six_benchmark_kpis(self):
        """Görev 9: Performans görünümü `benchmark.kpi.collect`'in altı
        KPI'sının hepsini gösteriyor — `decision_distribution` ve
        `vlm_trigger_rate`/`turkish_output_rate` Görev 2'den beri telde,
        ama `vision_tokens`/`correction_propagation`/`timestamp_drift_s`
        kpi_payload'da hiç YOKTU (sınandı: `test_view.py` bu üçünü daha
        önce hiç sınamıyordu). Üçünü gizlemek "altı KPI" iddiasını
        karşılamıyordu; bu test o boşluğu kilitliyor.
        """
        store = Store(":memory:")
        payload = view.kpi_payload(store)
        # Hiç veri yokken üçü de ölçülemedi — hiçbiri sessizce eksik değil,
        # anahtarların KENDİSİ payload'da var.
        assert "vision_tokens" in payload["decision"]
        assert "correction_propagation" in payload["decision"]
        assert "timestamp_drift_s" in payload["performance"]

    def test_vision_tokens_shows_real_token_counts_per_model(self):
        from gozcu.models import Interpretation
        from gozcu.config import MODELS

        store = Store(":memory:")
        store.save_interpretation(Interpretation(
            observation_ts=0.0, description="x", model=MODELS["vlm"],
            tokens=120, latency_ms=500, severity="olay"))
        payload = view.kpi_payload(store)
        assert payload["decision"]["vision_tokens"] != view.KPI_UNMEASURED
        assert MODELS["vlm"] in payload["decision"]["vision_tokens"]

    def test_correction_propagation_reflects_a_landed_correction(self):
        from gozcu.models import Correction, Episode

        store = Store(":memory:")
        episode = Episode(start_ts=0.0, phase="outcome",
                          summary_tr="yeni özet", preliminary_risk="Orta")
        episode.id = store.create_episode(episode)
        store.save_correction(Correction(ts=1.0, episode_id=episode.id,
                                         field="summary_tr", old="eski özet",
                                         new="yeni özet", rationale="düzeltme"))
        payload = view.kpi_payload(store)
        assert payload["decision"]["correction_propagation"] == "%100,0"

    def test_timestamp_drift_stays_unmeasured_without_ground_truth(self):
        """Canlı koşuda etiketli gerçek (`truth`) veri YOK — yalnız
        `benchmark/` koşucusu bunu geçirebiliyor. `kpi_payload` bir
        `truth` parametresi almadığı sürece bu KPI web konsolunda HER
        ZAMAN 'ölçülemedi' — bu bir eksiklik değil, dürüst bir sınır.
        """
        payload = view.kpi_payload(Store(":memory:"))
        assert payload["performance"]["timestamp_drift_s"] == view.KPI_UNMEASURED

    def test_perception_block_reads_the_bench_file(self, tmp_path):
        import json
        path = tmp_path / "perception.json"
        path.write_text(json.dumps({"result": {
            "presence_recall": 0.991, "count_recall": 0.931,
            "incident_energy_percentile": 0.035, "frames": 347,
            "real_time_factor": 0.35}}), encoding="utf-8")
        values = [block["value"] for block in view.perception_payload(path)["blocks"]]
        assert any("%99" in v for v in values)
        assert any("%93" in v for v in values)

    def test_perception_block_says_so_when_the_file_is_missing(self, tmp_path):
        """Ölçüm dosyası yoksa uydurulmuyor."""
        payload = view.perception_payload(tmp_path / "yok.json")
        assert view.KPI_UNMEASURED in payload["message"]

    def test_perception_block_survives_a_corrupt_file(self, tmp_path):
        path = tmp_path / "bozuk.json"
        path.write_text("{ bu json değil", encoding="utf-8")
        assert view.KPI_UNMEASURED in view.perception_payload(path)["message"]

    def test_kpi_payload_names_its_three_blocks(self):
        payload = view.kpi_payload(Store(":memory:"))
        labels = {payload["perception"]["label"], payload["decision"]["label"],
                  payload["performance"]["label"]}
        assert labels == {view.KPI_PERCEPTION, view.KPI_DECISION,
                          view.KPI_PERFORMANCE}


# =============================================================================
# `Adım adım` varsayılanı ve zorlu koşul metinleri — Görev 11'de
# `test_console.py`'den taşındı (triyajda `taşı`). İkisi de `view.py`'nin
# sabitleri; iddia birebir aynı, yalnız import yolu değişti.
# =============================================================================

def test_step_mode_is_off_by_default():
    """Varsayılan akış: 4 dakikalık sunumda düğmeye basılmıyor."""
    assert view.STEP_MODE_DEFAULT is False


class TestStressPrompts:
    """Şartname §6 demo videosunda "zorlu koşulları (örn: bağlam değişimi
    denemesi) nasıl yönettiği" isteniyor. 4 dakikalık sunumda (§11) bunları
    elle yazmak zaman kaybı; hazır metinler tek tıkla gidiyor."""

    def test_every_prompt_has_text_and_a_label(self):
        for key, (label, text) in view.STRESS_PROMPTS.items():
            assert label.strip(), key
            assert text.strip(), key

    def test_context_change_prompt_is_off_topic(self):
        """Bağlam değişimi denemesi, olayla İLGİSİZ olmalı — yoksa ajanın
        konuyu koruduğunu göstermez."""
        _, text = view.STRESS_PROMPTS["baglam"]
        assert "hava" in text.lower() or "yemek" in text.lower()

    def test_false_information_prompt_contradicts_the_observation(self):
        _, text = view.STRESS_PROMPTS["yanlis_bilgi"]
        assert "kimse yok" in text.lower()
