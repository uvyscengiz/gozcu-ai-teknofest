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
