# Görev 10 — Yedi saha sistemi aracı (`gozcu/tools/`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `198801e`
>
> **Yedi saha aracı indi.** `gozcu/tools/field_systems.py` ve
> `gozcu/tools/registry.py` var; `tests/test_tools.py` 23 test ile yeşil. Bu
> dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **`halt_production_line` artık gerçekten iki fazlı** — onaysız çağrı hattı
> durdurmuyor, onaylı çağrı gerçekten durduruyor ve onayı **defter** veriyor,
> model değil; **`urgency` enum'u şemada tanımlı** (`("normal", "critical")`)
> ve Görev 11'in promptu birebir bu iki değeri yazmak zorunda; ve **`call_tool`
> deftere videonun zamanını yazıyor** (`ts`), duvar saatini değil.

**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [09](09-tesis-dunyasi.md)

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Sistemin ajanı "sağlık ekibini çağırın" diye bir **cümle yazmıyor** — sağlık
ekibini gerçekten **arıyor.** Bu araçlar o çağrıların gittiği sahte saha
sistemleri: telsiz, alarm, İSG kaydı, vardiya listesi, ekipman geçmişi.

Şartname bunları iki ayrı yerde puanlıyor (*"mock fonksiyonların ajanın araçları
olarak başarıyla kullanılması"* ve *"mock sistem entegrasyonunun başarısı"*) ve
ayrıca teslim kalemi olarak sayıyor. Puanın %70'inin bulunduğu iki kalemden
ikisine birden dokunuyorsun.

**İyi haber:** bu görev hiçbir yapay zekâ modeli çağırmıyor. Saf Python
fonksiyonları, sözlük döndürüyor. Gateway erişimin olmasa da tamamen çalışır.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v          # mevcut testler geçmeli
```

## Bağımlı olduğun imzalar

Bunların hepsi zaten yazılmış durumda, sen sadece kullanacaksın:

```python
# gozcu/models.py
ActionRecord(id: int | None, ts: float, tool_name: str, params: dict,
             result: dict, actor: "agent" | "operator",
             approval: "not_required" | "pending" | "approved" | "rejected")

# gozcu/store.py
Store(db_path=":memory:")
Store.save_action(a: ActionRecord) -> int
Store.actions() -> list[ActionRecord]
```

Fikstürler **diskte hazır:** [Görev 09](09-tesis-dunyasi.md) indi (`c6d82ec`) ve
dört JSON ile yükleyici `gozcu/fixtures/` altında duruyor. Bu görev onları
kurmuyor, sadece okuyor; yükleyicinin dört fonksiyonu burada bağlayıcı:

```python
# gozcu/fixtures/loader.py  (Görev 09)
load_fixture(name) -> dict
resolve_zone(name) -> dict | None    # "B-Hattı" / "B" / "B-Hattı sevkiyat alanı"
resolve_shift(at_time) -> str | None # "03:12" -> "night"
overdue_maintenance_months(equipment_id) -> int
```

- **`overdue_maintenance_months` bir JSON anahtarı DEĞİL**, fonksiyon.
  `equipment.json`'dan o anahtar kalktı; sözlükten okuyan kod `KeyError` alır.
  Sayı bakım vadeleriyle senaryo tarihinden türetiliyor (`IST-04` → `4`).
- **Bölgeler ve hatlar gerçekten tanımlı.** Bölge kimlikleri `line_b`,
  `line_b_shipping`, `line_c`, `line_c_assembly`, `warehouse`; her biri
  `medical_team` ve `medical_eta_minutes` taşıyor. Hat kimlikleri `"B"` ve
  `"C"`. `dispatch_medical` ile `halt_production_line` serbest metne konuşmak
  zorunda değil.
- **`at_time`'ın karşılığı var:** vardiyalar `night` / `day` / `evening`.
  Personel kayıtları kararlı `PRS-00N` kimlikleri ve `shift_id` taşıyor;
  `zone` alanı ise insana görünen Türkçe adı (`"B-Hattı"`) tutmaya devam
  ediyor, yani aşağıdaki `k["zone"] == zone_name` filtresi çalışıyor.

## Ne yapacaksın

İki modül:

**`gozcu/tools/field_systems.py`** — yedi fonksiyon. İkisi **okuma** (ajanın muhakemesini
besliyor), beşi **aksiyon**.

Dönen anahtarlar **İngilizce** (CLAUDE.md: JSON anahtarı koddur); Türkçe kalan
tek şey insana görünen metin ve risk seviyeleridir.

| Araç | Tür | Döner |
|---|---|---|
| `query_shift_personnel(zone, at_time)` | okuma | `zone, zone_id, at_time, shift_id, personnel` — **o saatteki** vardiyada olan personel, roller, yetki belgeleri |
| `query_equipment_history(equipment_id)` | okuma | `equipment_id` + fikstür alanları + türetilmiş `overdue_maintenance_months`; bilinmeyen ekipmanda `equipment_id, not_found` |
| `radio_call(unit, message)` | aksiyon | `call_id, unit, message, state, awaiting_reply` |
| `dispatch_medical(location, urgency, description)` | aksiyon | `request_id, location, urgency, description, zone_id, team, eta_minutes, state` (`dispatched` \| `zone_unresolved`); enum dışı aciliyette ayrıca `unrecognised_urgency` |
| `site_alarm(zone, level)` | aksiyon | `alarm_id, affected_zone, zone_id, level, siren_state` (`active` \| `zone_unresolved`) |
| `open_safety_incident(episode_id, classification, description)` | aksiyon | `record_no, classification, state, episode_id, description` |
| `halt_production_line(line_id, rationale, approved=False)` | aksiyon | `line_id, zone_id, rationale, state` (`awaiting_approval` \| `halted` \| `line_unresolved` \| `zone_has_no_line`); yalnızca onaysız çağrıda ayrıca `awaiting_approval: True` |

Okuma/aksiyon karışımı kasıtlı: ajan önce sorgulayıp sonra mı harekete geçecek,
yoksa doğrudan mı — bu gerçek bir karar ve şartnamenin *"dinamik araç seçimi"*
kalemi tam olarak burada görünür hale geliyor.

`halt_production_line` **operatör onayı istiyor ve onay gerçekten bir şey
yapıyor:** onaysız çağrı hattı durdurmuyor, onaylı çağrı durduruyor. Onay
çubuğunun kapanıp hiçbir şeyin olmaması tiyatro olurdu.

**`gozcu/tools/registry.py`** — araç şemaları, dağıtım, aksiyon defteri.

```python
TOOLS: dict[str, Callable]
TOOL_SCHEMAS: list[dict]          # OpenAI tool-schema formatı
NEEDS_APPROVAL: set[str] = {"halt_production_line"}
call_tool(store, tool_name, params, actor="agent", approval=None, ts=0.0) -> dict
```

`approval` parametresi Görev 14'ün onay akışı için: operatör onayladığında
aynı araç `approval="approved"` ile çağrılıyor, yoksa her onay yeni bir
bekleyen kayıt doğurur. `ts` ise **videonun zamanı** — kararlar olay anında
veriliyor, defterdeki "ne zaman" sorusunun anlamlı cevabı videonun kaçıncı
saniyesi olduğu.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_tools.py`

> Aşağıdaki liste sevk edilen dosyanın kendisi; **tek fark** enum dışı aciliyet
> testinin ham değeri. Sevk edilen dosyada satır içinde `"kritik"` yazıyor,

```python
"""Görev 10 — yedi saha sistemi aracı ve aksiyon defteri.

Testler `call_tool` üzerinden geçiyor: araçların tek meşru giriş noktası o,
çünkü deftere yazan da o.
"""

import pytest

from gozcu.fixtures.loader import load_fixture
from gozcu.store import Store
from gozcu.tools import field_systems
from gozcu.tools.registry import (NEEDS_APPROVAL, TOOL_SCHEMAS, TOOLS,
                                  call_tool)


def _schema(name: str) -> dict:
    return next(s["function"] for s in TOOL_SCHEMAS
                if s["function"]["name"] == name)


# -- defter -----------------------------------------------------------------

def test_every_call_lands_in_the_action_ledger():
    store = Store(":memory:")
    call_tool(store, "radio_call",
              {"unit": "vardiya amiri", "message": "B-Hattı'na gel"})
    record = store.actions()[0]
    assert record.tool_name == "radio_call" and record.actor == "agent"
    assert record.approval == "not_required"


def test_action_records_carry_the_video_time_of_the_call():
    """Defterdeki saat videonun saati; `ts=0.0` sabiti her kaydı zamansız
    bırakıyordu ve jürinin okuduğu şey tam olarak bu defter."""
    store = Store(":memory:")
    call_tool(store, "radio_call", {"unit": "revir", "message": "gel"},
              ts=192.5)
    assert store.actions()[0].ts == 192.5


def test_unknown_tool_raises_rather_than_silently_succeeding():
    with pytest.raises(KeyError):
        call_tool(Store(":memory:"), "nukleer_firlat", {})


# -- hat durdurma: iki faz --------------------------------------------------

def test_line_stop_waits_for_operator_approval():
    store = Store(":memory:")
    result = call_tool(store, "halt_production_line",
                       {"line_id": "B-Hattı sevkiyat alanı",
                        "rationale": "devrilme"})
    assert result["awaiting_approval"] is True
    assert result["state"] == "awaiting_approval"
    # Bölge çözülmeli: serbest metin geri yankılanırsa bu satır kırılır.
    assert result["line_id"] == "B" and result["zone_id"] == "line_b_shipping"
    assert store.actions()[0].approval == "pending"
    assert "halt_production_line" in NEEDS_APPROVAL


def test_approved_line_stop_actually_halts_and_drops_the_pending_flag():
    """Onaydan sonra hat gerçekten duruyor; onay çubuğu kapanıp hiçbir şey
    olmaması tiyatro olurdu."""
    store = Store(":memory:")
    params = {"line_id": "B", "rationale": "devrilme"}
    first = call_tool(store, "halt_production_line", params)
    second = call_tool(store, "halt_production_line", params,
                       actor="operator", approval="approved")
    assert first["awaiting_approval"] is True and first["state"] != "halted"
    assert second["state"] == "halted"
    assert "awaiting_approval" not in second
    assert [(a.tool_name, a.approval) for a in store.actions()] == [
        ("halt_production_line", "pending"),
        ("halt_production_line", "approved")]


def test_explicit_approval_state_overrides_the_default():
    store = Store(":memory:")
    call_tool(store, "halt_production_line", {"line_id": "B", "rationale": "x"},
              actor="operator", approval="approved")
    assert store.actions()[0].approval == "approved"


def test_the_agent_cannot_approve_its_own_line_stop():
    """Onayı defter verir, model değil: `approved=True` uydursa da beklemede."""
    store = Store(":memory:")
    result = call_tool(store, "halt_production_line",
                       {"line_id": "B", "rationale": "x", "approved": True})
    assert result["awaiting_approval"] is True
    assert store.actions()[0].approval == "pending"
    assert store.actions()[0].params["approved"] is False


def test_halting_a_zone_that_belongs_to_no_line_is_explicit():
    """Ambarın `line_id`'si yok — deftere `None` düşürmek yerine söylüyoruz."""
    result = call_tool(Store(":memory:"), "halt_production_line",
                       {"line_id": "Ambar", "rationale": "x"})
    assert result["state"] == "zone_has_no_line"
    assert result["zone_id"] == "warehouse" and result["line_id"] == "Ambar"
    assert "awaiting_approval" not in result


def test_halting_an_unknown_line_is_explicit():
    result = call_tool(Store(":memory:"), "halt_production_line",
                       {"line_id": "Z-Hattı", "rationale": "x"})
    assert result["state"] == "line_unresolved"
    assert result["line_id"] == "Z-Hattı"


# -- sağlık ekibi -----------------------------------------------------------

def test_dispatch_medical_resolves_the_zone_to_a_team_and_an_eta():
    """Bölge fikstürlerinin bütün varlık sebebi bu çağrı."""
    result = call_tool(Store(":memory:"), "dispatch_medical",
                       {"location": "B-Hattı sevkiyat alanı",
                        "urgency": "critical", "description": "yerde kişi"})
    assert result["zone_id"] == "line_b_shipping"
    assert result["team"] == "Revir-2" and result["eta_minutes"] == 2
    assert result["state"] == "dispatched"


def test_normal_urgency_is_slower_than_critical():
    normal = field_systems.dispatch_medical("Ambar", "normal")
    critical = field_systems.dispatch_medical("Ambar", "critical")
    assert critical["eta_minutes"] == 7 and normal["eta_minutes"] == 12


def test_an_unrecognised_urgency_is_flagged_not_treated_as_normal():
    """Model 'kritik' ya da 'high' derse sessizce yavaş dalda kalmamalı."""
    result = call_tool(Store(":memory:"), "dispatch_medical",
                       {"location": "B-Hattı", "urgency": "kritik"})  # check-tasks: allow-tr
    assert result["unrecognised_urgency"] == "kritik"  # check-tasks: allow-tr
    assert result["urgency"] == "critical"
    assert result["eta_minutes"] == 2


def test_the_urgency_vocabulary_is_declared_in_the_tool_schema():
    urgency = _schema("dispatch_medical")["parameters"]["properties"]["urgency"]
    assert urgency["enum"] == list(field_systems.URGENCY_LEVELS)


def test_an_unresolved_location_does_not_invent_an_eta():
    result = call_tool(Store(":memory:"), "dispatch_medical",
                       {"location": "kantin arkası", "urgency": "critical"})
    assert result["state"] == "zone_unresolved"
    assert result["eta_minutes"] is None and result["team"] is None


# -- alarm ve İSG kaydı -----------------------------------------------------

def test_site_alarm_resolves_the_zone_instead_of_echoing_free_text():
    result = call_tool(Store(":memory:"), "site_alarm",
                       {"zone": "sevkiyat", "level": "yüksek"})
    assert result["zone_id"] == "line_b_shipping"
    assert result["affected_zone"] == "B-Hattı sevkiyat alanı"
    assert result["siren_state"] == "active" and result["level"] == "yüksek"


def test_site_alarm_does_not_claim_a_siren_in_an_unknown_zone():
    result = call_tool(Store(":memory:"), "site_alarm",
                       {"zone": "kantin arkası", "level": "yüksek"})
    assert result["siren_state"] == "zone_unresolved"
    assert result["zone_id"] is None


def test_open_safety_incident_records_an_open_case_for_the_episode():
    store = Store(":memory:")
    result = call_tool(store, "open_safety_incident",
                       {"episode_id": 7, "classification": "devrilme",
                        "description": "istif aracı devrildi"})
    assert result["state"] == "open" and result["episode_id"] == 7
    assert result["classification"] == "devrilme"
    assert result["record_no"] and store.actions()[0].approval == "not_required"


# -- okuma araçları ---------------------------------------------------------

def test_the_roster_is_scoped_to_the_shift_that_owns_the_query_time():
    """03:12 gece vardiyası: gündüz personeli listede görünmemeli."""
    result = call_tool(Store(":memory:"), "query_shift_personnel",
                       {"zone": "B", "at_time": "03:12"})
    assert result["shift_id"] == "night" and result["zone_id"] == "line_b"
    people = result["personnel"]
    assert {k["personnel_id"] for k in people} == {"PRS-001", "PRS-002",
                                                   "PRS-003"}
    assert all("certifications" in k for k in people)


def test_equipment_history_derives_the_overdue_months_instead_of_reading_a_key():
    """Gecikme fikstürde YAZMIYOR; araç onu Görev 09'un fonksiyonundan alır."""
    assert "overdue_maintenance_months" not in (
        load_fixture("equipment")["equipment"]["IST-04"])
    history = call_tool(Store(":memory:"), "query_equipment_history",
                        {"equipment_id": "IST-04"})
    assert history["overdue_maintenance_months"] == 4
    assert any(m["operation_type"] == "brake_service"
               for m in history["maintenance_history"])


def test_unknown_equipment_returns_a_flag_not_an_exception():
    g = call_tool(Store(":memory:"), "query_equipment_history",
                  {"equipment_id": "YOK-99"})
    assert g["not_found"] is True


# -- şemalar ----------------------------------------------------------------

def test_schemas_cover_every_registered_tool():
    assert {s["function"]["name"] for s in TOOL_SCHEMAS} == set(TOOLS)


def test_every_schema_declares_its_required_parameters():
    for s in TOOL_SCHEMAS:
        p = s["function"]["parameters"]
        assert p["required"] and set(p["required"]) <= set(p["properties"])


def test_the_approval_flag_is_declared_but_never_demanded_from_the_model():
    p = _schema("halt_production_line")["parameters"]
    assert "approved" in p["properties"] and "approved" not in p["required"]
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.tools'`

### 3. `gozcu/tools/field_systems.py` yaz

`gozcu/tools/__init__.py` (boş) de gerekiyor.

```python
"""Sahte saha sistemleri — telsiz, revir, alarm, İSG kaydı, vardiya, ekipman.

Ajan "sağlık ekibini çağırın" diye bir cümle yazmıyor; buradaki fonksiyonu
çağırıyor. Beşi aksiyon, ikisi okuma.

**Tek meşru giriş noktası `registry.call_tool`.** Buradaki fonksiyonlar sade
public fonksiyonlar, yani doğrudan çağrılabilirler — ama doğrudan çağrılan bir
araç **aksiyon defterine hiç düşmez** ve `halt_production_line` için onay
kapısını da atlar. Defter jürinin okuduğu şey ve Görev 17'nin `detail`
altında teslim ettiği kalem; deftere düşmeyen bir aksiyon olmamış sayılır.
Testler ve dışarıdan kullanım `call_tool` üzerinden geçmeli.

Fikstür yolunu burada KURMUYORUZ: `gozcu.fixtures` onu tek yerden veriyor.
"""

from gozcu.fixtures.loader import (load_fixture, overdue_maintenance_months,
                                   resolve_shift, resolve_zone)

#: `dispatch_medical`'in tanıdığı aciliyet değerleri. Tool şeması bunu `enum`
#: olarak bildiriyor — prompt ile şemanın ayrı sözlük konuşması bu projede bir
#: kez sistemi sessizce öldürdü.
URGENCY_LEVELS = ("normal", "critical")

#: Aciliyeti düşük olan çağrının varış süresine eklenen dakika.
NON_CRITICAL_DELAY_MINUTES = 5

_counter = {"call": 1000, "request": 2000, "alarm": 3000, "record": 4000,
            "halt": 5000}


def _ref(kind: str) -> str:
    _counter[kind] += 1
    return f"2026-{_counter[kind]}"


def radio_call(unit: str, message: str) -> dict:
    """Bir saha birimini telsizle arar."""
    return {"call_id": _ref("call"), "unit": unit, "message": message,
            "state": "delivered", "awaiting_reply": True}


def dispatch_medical(location: str, urgency: str = "normal",
                     description: str = "") -> dict:
    """Revir ekibini çağırır; ekip ve varış süresi bölgeden çözülür.

    Varış süresi fikstürden gelir, uydurulmaz: bölge çözülemiyorsa veri gibi
    duran bir sayı döndürmek yerine durum açıkça `zone_unresolved` olur.

    Tanınmayan bir aciliyet değeri sessizce `normal` sayılmaz — sessiz düşüş
    burada ekibin geç gelmesi demek. Bilinmeyen değer en kötü hâl (`critical`)
    kabul edilir ve ham değer `unrecognised_urgency` ile deftere yazılır.
    """
    recognised = urgency in URGENCY_LEVELS
    effective = urgency if recognised else "critical"
    zone = resolve_zone(location)

    result = {"request_id": _ref("request"), "location": location,
              "urgency": effective, "description": description}
    if zone is None:
        result |= {"zone_id": None, "team": None, "eta_minutes": None,
                   "state": "zone_unresolved"}
    else:
        eta = zone["medical_eta_minutes"]
        if effective != "critical":
            eta += NON_CRITICAL_DELAY_MINUTES
        result |= {"zone_id": zone["zone_id"], "team": zone["medical_team"],
                   "eta_minutes": eta, "state": "dispatched"}
    if not recognised:
        result["unrecognised_urgency"] = urgency
    return result


def site_alarm(zone: str, level: str) -> dict:
    """Bölgesel sesli alarmı çalıştırır.

    Bölge adı çözülür; serbest metni geri yankılamak "kantin arkasında siren
    çalıyor" gibi olmayan bir bölge uydurmak olurdu.
    """
    found = resolve_zone(zone)
    if found is None:
        return {"alarm_id": _ref("alarm"), "affected_zone": zone,
                "zone_id": None, "level": level,
                "siren_state": "zone_unresolved"}
    return {"alarm_id": _ref("alarm"), "affected_zone": found["name"],
            "zone_id": found["zone_id"], "level": level,
            "siren_state": "active"}


def open_safety_incident(episode_id: int, classification: str,
                         description: str = "") -> dict:
    """İş güvenliği olay kaydı açar."""
    return {"record_no": _ref("record"), "classification": classification,
            "state": "open", "episode_id": episode_id,
            "description": description}


def halt_production_line(line_id: str, rationale: str,
                         approved: bool = False) -> dict:
    """Üretim hattını durdurur. İki fazlı: önce onay istenir, sonra durur.

    `approved` bayrağını **defter** verir (`call_tool`), model değil — ajan
    kendi geri dönüşü zor aksiyonunu onaylayamaz. Onaysız çağrı hattı
    durdurmaz, `awaiting_approval` ile döner; onaylı çağrı gerçekten durdurur
    ve o anahtarı hiç taşımaz, yoksa onay çubuğu kapanır ama hat asla
    durmuş görünmez.

    "B-Hattı" da "B" de "B-Hattı sevkiyat alanı" da aynı hatta çözülmeli.
    Ambar gibi hiçbir hatta bağlı olmayan bir bölge için durdurulacak hat
    yoktur; deftere `None` düşürmek yerine durum açıkça söylenir.
    """
    zone = resolve_zone(line_id)
    if zone is None:
        return {"line_id": line_id, "zone_id": None, "rationale": rationale,
                "state": "line_unresolved"}
    if zone["line_id"] is None:
        return {"line_id": line_id, "zone_id": zone["zone_id"],
                "rationale": rationale, "state": "zone_has_no_line"}

    resolved = {"line_id": zone["line_id"], "zone_id": zone["zone_id"],
                "rationale": rationale}
    if not approved:
        return resolved | {"state": "awaiting_approval",
                           "awaiting_approval": True}
    return resolved | {"state": "halted"}


def query_shift_personnel(zone: str, at_time: str) -> dict:
    """O bölgede, o saatteki vardiyada olan personel.

    `at_time` yok sayılmıyor: saat bir vardiyaya çözülüyor ve liste ona göre
    daralıyor. Personel kaydının `zone` alanı insana görünen adı tuttuğu için
    filtre çözülmüş bölge ADI üzerinden kuruluyor — böylece ajan "B" dese de
    "B-Hattı" dese de aynı listeyi alıyor.
    """
    found = resolve_zone(zone)
    zone_name = found["name"] if found else zone
    shift_id = resolve_shift(at_time)
    people = [k for k in load_fixture("personnel")["personnel"]
              if k["zone"] == zone_name
              and (shift_id is None or k["shift_id"] == shift_id)]
    return {"zone": zone_name, "zone_id": found["zone_id"] if found else None,
            "at_time": at_time, "shift_id": shift_id, "personnel": people}


def query_equipment_history(equipment_id: str) -> dict:
    """Bakım ve arıza geçmişi + TÜRETİLMİŞ gecikme.

    `overdue_maintenance_months` fikstürde bir anahtar değil; Görev 09'un
    fonksiyonu onu bakım vadeleriyle senaryo tarihinden hesaplıyor.
    """
    record = load_fixture("equipment")["equipment"].get(equipment_id)
    if record is None:
        return {"equipment_id": equipment_id, "not_found": True}
    return {"equipment_id": equipment_id, **record,
            "overdue_maintenance_months": overdue_maintenance_months(
                equipment_id)}
```

### 4. `gozcu/tools/registry.py` yaz

```python
"""Araç şemaları, dağıtım ve aksiyon defteri.

`call_tool` araçların tek meşru giriş noktası: şemayı, onay kapısını ve
deftere yazmayı bir arada tutan yer burası.
"""

from gozcu.models import ActionRecord
from gozcu.tools import field_systems

TOOLS = {
    "radio_call": field_systems.radio_call,
    "dispatch_medical": field_systems.dispatch_medical,
    "site_alarm": field_systems.site_alarm,
    "open_safety_incident": field_systems.open_safety_incident,
    "halt_production_line": field_systems.halt_production_line,
    "query_shift_personnel": field_systems.query_shift_personnel,
    "query_equipment_history": field_systems.query_equipment_history,
}

NEEDS_APPROVAL = {"halt_production_line"}

#: Araç adı -> (açıklama, JSON-şema özellikleri, zorunlu parametreler).
#: Zorunlular ayrı duruyor çünkü `halt_production_line`'ın `approved` bayrağı
#: modelden istenen bir şey değil — defterden geliyor (bkz. `call_tool`).
_TOOL_SPECS = {
    "radio_call": ("Bir saha birimini telsizle arar.",
                   {"unit": {"type": "string"},
                    "message": {"type": "string"}},
                   ("unit", "message")),
    "dispatch_medical": ("Revir sağlık ekibini olay yerine çağırır.",
                         {"location": {"type": "string"},
                          "urgency": {"type": "string",
                                      "enum": list(
                                          field_systems.URGENCY_LEVELS)},
                          "description": {"type": "string"}},
                         ("location", "urgency", "description")),
    "site_alarm": ("Bölgesel sesli alarmı çalıştırır.",
                   {"zone": {"type": "string"},
                    "level": {"type": "string"}},
                   ("zone", "level")),
    "open_safety_incident": ("İş güvenliği olay kaydı açar.",
                             {"episode_id": {"type": "integer"},
                              "classification": {"type": "string"},
                              "description": {"type": "string"}},
                             ("episode_id", "classification", "description")),
    "halt_production_line": ("Üretim hattını durdurur. Operatör onayı gerekir.",
                             {"line_id": {"type": "string"},
                              "rationale": {"type": "string"},
                              "approved": {
                                  "type": "boolean",
                                  "description": "Operatör onayı. Bu bayrağı "
                                                 "aksiyon defteri verir, ajan "
                                                 "kendisi onaylayamaz."}},
                             ("line_id", "rationale")),
    "query_shift_personnel": ("Bir bölgede vardiyadaki personeli ve yetki "
                              "belgelerini getirir.",
                              {"zone": {"type": "string"},
                               "at_time": {"type": "string"}},
                              ("zone", "at_time")),
    "query_equipment_history": ("Bir ekipmanın bakım ve arıza geçmişini "
                                "getirir.",
                                {"equipment_id": {"type": "string"}},
                                ("equipment_id",)),
}

TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(required),
        },
    },
} for name, (description, properties, required) in _TOOL_SPECS.items()]


def call_tool(store, tool_name: str, params: dict, actor: str = "agent",
              approval: str | None = None, ts: float = 0.0) -> dict:
    """Bir aracı çalıştırır ve çağrıyı aksiyon defterine yazar.

    `approval` Görev 14'ün onay akışı için: operatör onayladığında aynı araç
    `approval="approved"` ile çağrılıyor, yoksa her onay yeni bir bekleyen
    kayıt doğurur.

    `ts` **videonun zamanı**, duvar saati değil. Kararlar olay anında
    veriliyor; defterdeki "ne zaman" sorusunun anlamlı cevabı videonun kaçıncı
    saniyesinde olduğu. Çağıran o anı biliyor, varsayılan videonun başı.
    """
    fn = TOOLS[tool_name]          # bilinmeyen araçta KeyError — kasıtlı
    if approval is None:
        approval = ("pending" if tool_name in NEEDS_APPROVAL
                    else "not_required")
    if tool_name in NEEDS_APPROVAL:
        # Onayın tek kaynağı defter: modelin gönderdiği `approved` ezilir,
        # yoksa ajan kendi hat durdurmasını onaylayabilirdi.
        params = {**params, "approved": approval == "approved"}
    result = fn(**params)
    store.save_action(ActionRecord(
        ts=ts, tool_name=tool_name, params=params, result=result,
        actor=actor, approval=approval))
    return result
```

### 5. Yeşil olduğunu gör

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: 23 passed

Okuma araçlarının testleri [Görev 09](09-tesis-dunyasi.md)'un fikstürlerine
dayanıyor; fikstürler diskte olduğu için ek bir hazırlık gerekmiyor. İkisi
zaten (yanlışlıkla) Görev 09'un dosyasında duruyordu, buraya taşındılar.

### 6. Commit

```bash
git add gozcu/tools tests/test_tools.py
git commit -m "feat: seven field-system tools with a two-phase halt"
```

## Doğrulama

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: **23 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`call_tool(store, name, params, actor="agent", approval=None, ts=0.0)`'ın
  `ts`'i VİDEONUN ZAMANI**, duvar saati değil. Çağıran o anı biliyor; geçmezse
  kayıt `0.0` ile düşer. [Görev 14](14-nobetci.md) ve
  [Görev 17](17-cikti-sozlesmesi.md) için bağlayıcı: olay zamanı geçilmezse
  `detail.action_ledger` sıfırlarla dolu teslim edilir ve defterdeki "ne zaman"
  sorusunun cevabı kalmaz.
- **Ajan kendi hat durdurmasını ONAYLAYAMAZ.** `halt_production_line` şemada
  bir `approved` alanı bildiriyor ama `call_tool` modelin gönderdiği değeri
  **eziyor**: bayrağı defterdeki onay durumunun `"approved"` olup olmadığı
  belirliyor. Tek doğruluk kaynağı defter. [Görev 14](14-nobetci.md)'ün mevcut
  `call_tool(..., actor="operator", approval="approved")` çağrısı artık hattı
  gerçekten durduruyor.
- **İki faz, iki farklı şekil.** Onaysız çağrı `state: "awaiting_approval"` ve
  `awaiting_approval: True` döner; onaylı çağrı `state: "halted"` döner ve
  `awaiting_approval` anahtarını **hiç taşımaz**. Konsol/rapor tarafı bekleyen
  satırı bu anahtarla ayırt edebilir.
- **`urgency` sözlüğü tam olarak `("normal", "critical")`** ve tek kaynağı
  `field_systems.URGENCY_LEVELS`; şema onu JSON-şema `enum`'u olarak bildiriyor.
  [Görev 11](11-risk-analisti.md)'in promptu bu iki değeri **birebir** yazmak
  zorunda. Enum dışı bir değer sessizce `normal` sayılmaz: **güvenli tarafa,
  `critical`'a düşer** ve ham değer `unrecognised_urgency` ile deftere yazılır —
  bir güvenlik sisteminde güvenli başarısızlık yükseltmektir, düşürmek değil.
- **`field_systems.*` sade fonksiyonlar; doğrudan çağrılan araç deftere hiç
  düşmez** ve onay kapısını da atlar. Tek meşru giriş noktası `call_tool`;
  deftere düşmeyen bir aksiyon olmamış sayılır.
- **`_TOOL_SPECS` girdileri üçlüdür:** `(açıklama, özellikler, zorunlular)`.
  Zorunlular ayrı duruyor çünkü `approved` modelden istenen bir parametre değil
  — şemada bildirilir ama `required` listesine girmez.
- **Çözülemeyen bölge/hat açıkça söylenir.** `zone_unresolved`,
  `line_unresolved`, `zone_has_no_line` — varış süresi uydurmak ya da deftere
  `None` düşürüp sessiz kalmak yerine durum bir değer olarak dönüyor.
