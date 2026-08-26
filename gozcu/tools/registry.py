"""Araç şemaları, dağıtım ve aksiyon defteri.

`call_tool` araçların tek meşru giriş noktası: şemayı, onay kapısını ve
deftere yazmayı bir arada tutan yer burası.
"""

import inspect
import os

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

#: Operatör onayı isteyen araçlar. **Boş** — ve bu bilinçli bir karar.
#:
#: Buradaki yedi fonksiyon `field_systems`'te birer sözlük döndüren MOCK:
#: ne gerçek bir hat duruyor, ne gerçek bir sağlık ekibi çıkıyor. Olmayan
#: bir eylemi kapılamanın maliyeti ölçüldü — ajan yedi kez yükseltti ve
#: HİÇBİR araç çağırmadı, çünkü kapı promptta üçüncü bir "önce sor" baskısı
#: yaratıyordu. Yarışmanın %35'lik kriteri araçların KULLANILMASINI
#: puanlıyor; kapı tam onu engelliyordu.
#:
#: Silinmedi, boşaltıldı: gerçek saha sistemlerine bağlanan bir kurulumda
#: `halt_production_line` yeniden kapılanmalı ve makine (`call_tool`,
#: `Supervisor._refuse_second_gate`, konsolun onay çubuğu) yerinde duruyor.
#: `GOZCU_NEEDS_APPROVAL="halt_production_line"` ile geri gelir.
NEEDS_APPROVAL = frozenset(
    name for name in os.environ.get("GOZCU_NEEDS_APPROVAL", "").split(",")
    if name.strip())

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


#: Olay kaydı bir kere açılır. Aynı epizot için ikinci çağrı, bir kez olan
#: şeyi iki kez olmuş gibi gösterir.
INCIDENT_TOOL = "open_safety_incident"
NO_SUCH_EPISODE = "Böyle bir olay yok; kayıt açılmadı."


def _incident_guard(store, tool_name: str, params: dict) -> dict | None:
    """Olay kaydı disiplini; kapsamadığı çağrılarda `None`.

    26 Ağustos canlı koşusunda depoda **tek** epizot vardı ve süpervizör
    `episode_id` 1, 2, 3, 4 ile **dört** kayıt açtı: üçü hiç var olmayan
    olaylardı, sayıyı model kendi artırdı. Saha sistemi bir mock ve ne
    verilirse kabul eder; disiplin ajanın tarafında olmak zorunda.

    İki kural:
    - Olmayan bir epizot için kayıt açılmaz — uydurulmuş bir kimlik, defterde
      gerçek bir kaydın yanında ayırt edilemez duruyor.
    - Aynı epizot için ikinci kayıt açılmaz; ilk kaydın numarası döner.
    """
    if tool_name != INCIDENT_TOOL:
        return None

    episode_id = params.get("episode_id")
    if episode_id not in {episode.id for episode in store.episodes()}:
        return {"refused": True, "reason": NO_SUCH_EPISODE,
                "episode_id": episode_id}

    for action in store.actions():
        if (action.tool_name == INCIDENT_TOOL
                and action.params.get("episode_id") == episode_id
                and action.result.get("record_no")):
            return {**action.result, "duplicate": True}
    return None


def call_tool(store, tool_name: str, params: dict, actor: str = "agent",
              approval: str | None = None, ts: float = 0.0,
              caller: str = "supervisor") -> dict:
    """Bir aracı çalıştırır ve çağrıyı aksiyon defterine yazar.

    `approval` Görev 14'ün onay akışı için: operatör onayladığında aynı araç
    `approval="approved"` ile çağrılıyor, yoksa her onay yeni bir bekleyen
    kayıt doğurur.

    `caller` **hangi ajanın** çağırdığı — `actor`'dan ayrı bir soru. `actor`
    "insan mı makine mi" diye soruyor; `caller` makinenin hangisi olduğunu
    söylüyor. Risk analisti soruşturma araçlarını kendisi çağırıyor
    (`risk.py`) ve varsayılan süpervizör onları yanlış ajana yazardı.

    `ts` **videonun zamanı**, duvar saati değil. Kararlar olay anında
    veriliyor; defterdeki "ne zaman" sorusunun anlamlı cevabı videonun kaçıncı
    saniyesinde olduğu. Çağıran o anı biliyor, varsayılan videonun başı.
    """
    guarded = _incident_guard(store, tool_name, params)
    if guarded is not None:
        # Deftere YAZILMIYOR: reddedilen ya da yinelenen bir çağrı olmamış
        # bir aksiyondur ve defterdeki kayıt sayısı jürinin saydığı şey.
        return guarded

    fn = TOOLS[tool_name]          # bilinmeyen araçta KeyError — kasıtlı
    if approval is None:
        approval = ("pending" if tool_name in NEEDS_APPROVAL
                    else "not_required")
    if tool_name in NEEDS_APPROVAL:
        # Onayın tek kaynağı defter: modelin gönderdiği `approved` ezilir,
        # yoksa ajan kendi hat durdurmasını onaylayabilirdi.
        params = {**params, "approved": approval == "approved"}
    elif "approved" in inspect.signature(fn).parameters:
        # Kapı YOKKEN iki fazlı aracın ikinci fazı hiç gelmez ve mock
        # sonsuza dek `awaiting_approval` döndürür — ajan aracı çağırsa bile
        # HİÇBİR ŞEY olmaz. Kapısız kurulumda tek faz var: eylem.
        params = {**params, "approved": True}
    result = fn(**params)
    store.save_action(ActionRecord(
        ts=ts, tool_name=tool_name, params=params, result=result,
        actor=actor, approval=approval, caller=caller))
    return result
