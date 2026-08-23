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

Fixture dosyaları [Görev 09](09-tesis-dunyasi.md)'dan geliyor ve o da sende.
İkisini birlikte yap: önce 09 (fixture'lar), sonra 10 (araçlar).

## Ne yapacaksın

İki modül:

**`gozcu/tools/field_systems.py`** — yedi fonksiyon. İkisi **okuma** (ajanın muhakemesini
besliyor), beşi **aksiyon**.

| Araç | Tür | Döner |
|---|---|---|
| `query_shift_personnel(zone, at_time)` | okuma | vardiyadaki personel, roller, **yetki belgeleri** |
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

from gozcu.store import Store
from gozcu.tools.registry import TOOL_SCHEMAS, TOOLS, NEEDS_APPROVAL, call_tool


def test_every_call_lands_in_the_action_ledger():
    store = Store(":memory:")
    call_tool(store, "radio_call",
          {"unit": "shift amiri", "message": "B-Hattı'na gel"})
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
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
_sayac = {"cagri": 1000, "talep": 2000, "alarm": 3000, "record": 4000}


def _ref(kind: str) -> str:
    _sayac[kind] += 1
    return f"2026-{_sayac[kind]}"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def radio_call(unit: str, message: str) -> dict:
    return {"call_id": _ref("cagri"), "unit": unit, "message": message,
            "state": "delivered", "awaiting_reply": True}


def dispatch_medical(location: str, urgency: str, description: str = "") -> dict:
    return {"request_id": _ref("talep"), "location": location, "team": "Revir-2",
            "eta_minutes": 2 if urgency == "critical" else 8}


def site_alarm(zone: str, level: str) -> dict:
    return {"alarm_id": _ref("alarm"), "affected_zone": zone,
            "siren_state": "active", "level": level}


def open_safety_incident(episode_id: int, classification: str,
                      description: str = "") -> dict:
    return {"record_no": _ref("record"), "classification": classification,
            "state": "open", "episode_id": episode_id}


def halt_production_line(line_id: str, rationale: str) -> dict:
    return {"line_id": line_id, "rationale": rationale, "awaiting_approval": True}


def query_shift_personnel(zone: str, at_time: str) -> dict:
    payload = _load("personnel")
    return {"zone": zone, "at_time": at_time,
            "personnel": [k for k in payload["personnel"] if k["zone"] == zone]}


def query_equipment_history(equipment_id: str) -> dict:
    record = _load("equipment")["equipment"].get(equipment_id)
    if record is None:
        return {"equipment_id": equipment_id, "not_found": True}
    return {"equipment_id": equipment_id, **record}
```

### 4. `gozcu/tools/registry.py` yaz

```python
from gozcu.models import ActionRecord
from gozcu.tools import saha

TOOLS = {
    "radio_call": saha.radio_call,
    "dispatch_medical": saha.dispatch_medical,
    "site_alarm": saha.site_alarm,
    "open_safety_incident": saha.open_safety_incident,
    "halt_production_line": saha.halt_production_line,
    "query_shift_personnel": saha.query_shift_personnel,
    "query_equipment_history": saha.query_equipment_history,
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
Beklenen: 9 passed

3. ve 5. testler [Görev 09](09-tesis-dunyasi.md)'un fixture dosyalarına ihtiyaç
duyuyor. Görev 09'u önce yaptıysan geçerler.

### 6. Commit

```bash
git add gozcu/tools tests/test_tools.py
git commit -m "feat: seven mock field-system tools with an action ledger"
```

## Doğrulama

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: **9 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
