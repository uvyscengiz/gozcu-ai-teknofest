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
