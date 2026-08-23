# Görev 10 — Yedi saha sistemi aracı (`gozcu/tools/`)

**Sahip:** `Xana-bit` · **Gün:** 25 Ağustos · **Süre:** ~3 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [09](09-tesis-dunyasi.md)
**Etiket:** `cold-start` — bu kod tabanını ilk kez görüyorsan bu görev sana göre

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

Fikstür dosyaları [Görev 09](09-tesis-dunyasi.md)'dan geliyor ve o da sende.
İkisini birlikte yap: **önce 09 (fikstürler), sonra 10 (araçlar).**

Görev 09 indi (`c6d82ec`) ve okuma araçlarının dayanacağı sözleşme netleşti —
üçü de burada bağlayıcı:

```python
# gozcu/fixtures/loader.py  (Görev 09)
load_fixture(name) -> dict
resolve_zone(name) -> dict | None    # "B-Hattı" / "B" / "B-Hattı sevkiyat alanı"
resolve_shift(at_time) -> str | None # "03:12" -> "night"
overdue_maintenance_months(equipment_id) -> int
```

- **`overdue_maintenance_months` artık bir JSON anahtarı DEĞİL**, fonksiyon.
  `equipment.json`'dan o anahtar kalktı; sözlükten okuyan kod `KeyError` alır.
  Sayı bakım vadeleriyle senaryo tarihinden türetiliyor (`IST-04` → `4`).
- **Bölgeler ve hatlar artık gerçekten tanımlı.** Bölge kimlikleri `line_b`,
  `line_b_shipping`, `line_c`, `line_c_assembly`, `warehouse`; her biri
  `medical_team` ve `medical_eta_minutes` taşıyor. Hat kimlikleri `"B"` ve
  `"C"`. `dispatch_medical` ile `halt_production_line` serbest metne konuşmak
  zorunda değil.
- **`at_time`'ın karşılığı var:** vardiyalar `night` / `day` / `evening`.
  Personel kayıtları kararlı `PRS-00N` kimlikleri ve `shift_id` taşıyor;
  `zone` alanı ise insana görünen Türkçe adı (`"B-Hattı"`) tutmaya devam
  ediyor, yani aşağıdaki `k["zone"] == zone` filtresi çalışmayı sürdürüyor.

## Ne yapacaksın

İki modül:

**`gozcu/tools/field_systems.py`** — yedi fonksiyon. İkisi **okuma** (ajanın muhakemesini
besliyor), beşi **aksiyon**.

| Araç | Tür | Döner |
|---|---|---|
| `query_shift_personnel(zone, at_time)` | okuma | **o saatteki** vardiyada olan personel, roller, yetki belgeleri |
| `query_equipment_history(equipment_id)` | okuma | bakım geçmişi, arıza kayıtları |
| `radio_call(unit, message)` | aksiyon | `{cagri_id, durum, yanit_bekleniyor}` |
| `dispatch_medical(location, urgency, description)` | aksiyon | `{talep_id, ekip, tahmini_varis_dk}` |
| `site_alarm(zone, level)` | aksiyon | `{alarm_id, etkilenen_bolge, siren_durumu}` |
| `open_safety_incident(episode_id, classification, description)` | aksiyon | `{kayit_no, durum}` |
| `halt_production_line(line_id, rationale)` | aksiyon | `{onay_bekliyor: True}` |

Okuma/aksiyon karışımı kasıtlı: ajan önce sorgulayıp sonra mı harekete geçecek,
yoksa doğrudan mı — bu gerçek bir karar ve şartnamenin *"dinamik araç seçimi"*
kalemi tam olarak burada görünür hale geliyor.

`halt_production_line` **operatör onayı istiyor.** Ajan geri dönüşü zor bir
aksiyonu tek başına almıyor.

**`gozcu/tools/registry.py`** — araç şemaları, dağıtım, aksiyon defteri.

```python
TOOLS: dict[str, Callable]
TOOL_SCHEMAS: list[dict]          # OpenAI tool-schema formatı
NEEDS_APPROVAL: set[str] = {"halt_production_line"}
call_tool(store, tool_name, params, actor="agent", approval=None) -> dict
```

`approval` parametresi Görev 14'ün onay akışı için: operatör onayladığında
aynı araç `approval="approved"` ile çağrılıyor, yoksa her onay yeni bir
bekleyen kayıt doğurur.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_tools.py`

```python
import pytest

from gozcu.fixtures.loader import load_fixture
from gozcu.store import Store
from gozcu.tools.registry import TOOL_SCHEMAS, TOOLS, NEEDS_APPROVAL, call_tool


def test_every_call_lands_in_the_action_ledger():
    store = Store(":memory:")
    call_tool(store, "radio_call",
          {"unit": "vardiya amiri", "message": "B-Hattı'na gel"})
    record = store.actions()[0]
    assert record.tool_name == "radio_call" and record.actor == "agent"
    assert record.approval == "not_required"


def test_line_stop_waits_for_operator_approval():
    store = Store(":memory:")
    result = call_tool(store, "halt_production_line",
                  {"line_id": "B", "rationale": "devrilme"})
    assert result["awaiting_approval"] is True
    assert store.actions()[0].approval == "pending"
    assert "halt_production_line" in NEEDS_APPROVAL


def test_explicit_approval_state_overrides_the_default():
    store = Store(":memory:")
    call_tool(store, "halt_production_line", {"line_id": "B", "rationale": "x"},
          actor="operator", approval="approved")
    assert store.actions()[0].approval == "approved"


def test_shift_query_returns_certifications_so_the_agent_can_reason():
    people = call_tool(Store(":memory:"), "query_shift_personnel",
                    {"zone": "B-Hattı", "at_time": "03:12"})["personnel"]
    assert people and all("certifications" in k for k in people)


def test_equipment_history_exposes_overdue_maintenance():
    history = call_tool(Store(":memory:"), "query_equipment_history",
                   {"equipment_id": "IST-04"})
    assert history["overdue_maintenance_months"] >= 4


def test_equipment_history_derives_the_overdue_months_instead_of_reading_a_key():
    """Gecikme fikstürde YAZMIYOR; araç onu Görev 09'un fonksiyonundan alır."""
    assert "overdue_maintenance_months" not in (
        load_fixture("equipment")["equipment"]["IST-04"])
    history = call_tool(Store(":memory:"), "query_equipment_history",
                   {"equipment_id": "IST-04"})
    assert history["overdue_maintenance_months"] == 4
    assert any(m["operation_type"] == "brake_service"
               for m in history["maintenance_history"])


def test_the_roster_is_scoped_to_the_shift_that_owns_the_query_time():
    """03:12 gece vardiyası: gündüz personeli listede görünmemeli."""
    result = call_tool(Store(":memory:"), "query_shift_personnel",
                  {"zone": "B", "at_time": "03:12"})
    assert result["shift_id"] == "night" and result["zone_id"] == "line_b"
    people = result["personnel"]
    assert {k["personnel_id"] for k in people} == {"PRS-001", "PRS-002",
                                                   "PRS-003"}
    assert all("certifications" in k for k in people)


def test_unknown_equipment_returns_a_flag_not_an_exception():
    g = call_tool(Store(":memory:"), "query_equipment_history",
              {"equipment_id": "YOK-99"})
    assert g["not_found"] is True


def test_unknown_tool_raises_rather_than_silently_succeeding():
    with pytest.raises(KeyError):
        call_tool(Store(":memory:"), "nukleer_firlat", {})


def test_schemas_cover_every_registered_tool():
    assert {s["function"]["name"] for s in TOOL_SCHEMAS} == set(TOOLS)


def test_every_schema_declares_its_required_parameters():
    for s in TOOL_SCHEMAS:
        p = s["function"]["parameters"]
        assert p["required"] and set(p["required"]) <= set(p["properties"])
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.tools'`

### 3. `gozcu/tools/field_systems.py` yaz

`gozcu/tools/__init__.py` (boş) de gerekiyor.

```python
from gozcu.fixtures.loader import (load_fixture, overdue_maintenance_months,
                                   resolve_shift, resolve_zone)

# Fikstür yolunu burada KURMUYORUZ: `gozcu.fixtures` onu tek yerden veriyor.
_counter = {"call": 1000, "request": 2000, "alarm": 3000, "record": 4000}


def _ref(kind: str) -> str:
    _counter[kind] += 1
    return f"2026-{_counter[kind]}"


def radio_call(unit: str, message: str) -> dict:
    return {"call_id": _ref("call"), "unit": unit, "message": message,
            "state": "delivered", "awaiting_reply": True}


def dispatch_medical(location: str, urgency: str, description: str = "") -> dict:
    """Revir ekibini çağırır; ekip ve varış süresi bölgeden çözülür."""
    zone = resolve_zone(location)
    eta = zone["medical_eta_minutes"] if zone else 8
    return {"request_id": _ref("request"), "location": location,
            "zone_id": zone["zone_id"] if zone else None,
            "team": zone["medical_team"] if zone else "Revir-1",
            "eta_minutes": eta if urgency == "critical" else eta + 5,
            "description": description}


def site_alarm(zone: str, level: str) -> dict:
    return {"alarm_id": _ref("alarm"), "affected_zone": zone,
            "siren_state": "active", "level": level}


def open_safety_incident(episode_id: int, classification: str,
                      description: str = "") -> dict:
    return {"record_no": _ref("record"), "classification": classification,
            "state": "open", "episode_id": episode_id}


def halt_production_line(line_id: str, rationale: str) -> dict:
    """Hattı durdurur. "B-Hattı" da "B" de aynı hatta çözülmeli."""
    zone = resolve_zone(line_id)
    return {"line_id": zone["line_id"] if zone else line_id,
            "rationale": rationale, "awaiting_approval": True}


def query_shift_personnel(zone: str, at_time: str) -> dict:
    """O bölgede, o saatteki vardiyada olan personel.

    `at_time` artık yok sayılmıyor: saat bir vardiyaya çözülüyor ve liste
    ona göre daralıyor. Personel kaydının `zone` alanı insana görünen adı
    tuttuğu için filtre çözülmüş bölge ADI üzerinden kuruluyor — böylece
    ajan "B" dese de "B-Hattı" dese de aynı listeyi alıyor.
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

_TOOL_SPECS = {
    "radio_call": ("Bir saha birimini telsizle arar.",
                            {"unit": "string", "message": "string"}),
    "dispatch_medical": ("Revir sağlık ekibini olay yerine çağırır.",
                           {"location": "string", "urgency": "string",
                            "description": "string"}),
    "site_alarm": ("Bölgesel sesli alarmı çalıştırır.",
                    {"zone": "string", "level": "string"}),
    "open_safety_incident": ("İş güvenliği olay kaydı açar.",
                          {"episode_id": "integer", "classification": "string",
                           "description": "string"}),
    "halt_production_line": ("Üretim hattını durdurur. Operatör onayı gerekir.",
                            {"line_id": "string", "rationale": "string"}),
    "query_shift_personnel": ("Bir bölgede vardiyadaki personeli ve yetki "
                                 "belgelerini getirir.",
                                 {"zone": "string", "at_time": "string"}),
    "query_equipment_history": ("Bir ekipmanın bakım ve arıza geçmişini "
                                "getirir.", {"equipment_id": "string"}),
}

TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {p: {"type": t} for p, t in params.items()},
            "required": list(params),
        },
    },
} for name, (description, params) in _TOOL_SPECS.items()]


def call_tool(store, tool_name: str, params: dict, actor: str = "agent",
          approval: str | None = None) -> dict:
    fn = TOOLS[tool_name]          # bilinmeyen araçta KeyError — kasıtlı
    result = fn(**params)
    if approval is None:
        approval = ("pending" if tool_name in NEEDS_APPROVAL
                       else "not_required")
    store.save_action(ActionRecord(
        ts=0.0, tool_name=tool_name, params=params, result=result,
        actor=actor, approval=approval))
    return result
```

### 5. Yeşil olduğunu gör

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: 11 passed

Okuma araçlarının testleri [Görev 09](09-tesis-dunyasi.md)'un fikstürlerine
ihtiyaç duyuyor. Görev 09'u önce yaptıysan geçerler — ikisi zaten (yanlışlıkla)
Görev 09'un dosyasında duruyordu, buraya taşındılar.

### 6. Commit

```bash
git add gozcu/tools tests/test_tools.py
git commit -m "feat: seven mock field-system tools with an action ledger"
```

## Doğrulama

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: **11 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
