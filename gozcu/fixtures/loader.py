"""Fikstür okuyucu ve olay arşivi tohumlayıcısı.

Burada iki iş var:

1. **Okuma yardımcıları.** `load_fixture()` dosyaları, `resolve_zone()` /
   `resolve_shift()` / `overdue_maintenance_months()` ise araçların ve
   raporun sorduğu türetilmiş bilgiyi verir. Bakımın kaç ay geciktiği
   hiçbir dosyada **yazmıyor** — tarihlerden hesaplanıyor. Elle yazılan bir
   sayı kendi tarihleriyle çelişebilir; hesaplanan sayı çelişemez.

2. **Arşiv tohumlama.** `load_history()` önceki olayları epizot olarak
   kaydeder ve gömer; operatör *"bu araçla ilgili daha önce bir olay olmuş
   muydu?"* diye sorduğunda cevabın geldiği yer burasıdır.

Bütün tarihler dosyalarda **sabit**: senaryo 15 Ağustos 2026'da geçiyor ve
hiçbir değer "bugün"den hesaplanmıyor. Aksi hâlde demo gerçek zaman
ilerledikçe kayar — dört ay gecikmiş bakım bir ay sonra beş ay gecikmiş olur.
"""

import json
from datetime import date

from gozcu.fixtures import FIXTURE_DIR
from gozcu.memory import embed_episode
from gozcu.models import Episode, EventClass, Protocol, RiskLevel


def load_fixture(name: str) -> dict:
    """Adı verilen fixture dosyasını `gozcu/fixtures/` altından okur."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


#: Senaryonun geçtiği gün. Tek kaynağı fikstür dosyası — kod kendi tarihini
#: uydurmaz ve `date.today()` çağrılmaz.
SCENARIO_DATE = date.fromisoformat(
    load_fixture("facility")["facility"]["scenario_date"])


def resolve_zone(name: str) -> dict | None:
    """Bir bölge adını, hat kodunu veya takma adı bölge kaydına çözer.

    Ajan bir yeri üç ayrı biçimde söyleyebiliyor — `"B-Hattı"`, `"B"`,
    `"B-Hattı sevkiyat alanı"` — ve üçü de gerçek bir bölgeye oturmalı;
    yoksa `dispatch_medical` ile `halt_production_line` serbest metne
    konuşur. Tanınmayan ad için `None` döner, istisna atmaz.
    """
    wanted = str(name).casefold().strip()
    for zone in load_fixture("facility")["zones"]:
        candidates = [zone["zone_id"], zone["name"], *zone["aliases"]]
        if any(wanted == c.casefold() for c in candidates):
            return zone
    return None


def resolve_shift(at_time: str, facility: dict | None = None) -> str | None:
    """`"03:12"` gibi bir saati vardiya kimliğine çözer; bilinmiyorsa `None`."""
    facility = facility or load_fixture("facility")
    for shift in facility["shifts"]:
        if shift["start"] <= at_time < shift["end"]:
            return shift["shift_id"]
    return None


def _months_between(earlier: date, later: date) -> int:
    """İki tarih arasındaki **tam** ay sayısı; geçmemişse negatif."""
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    return months - 1 if later.day < earlier.day else months


def overdue_maintenance_months(equipment_id: str,
                               as_of: date | None = None) -> int:
    """Bir ekipmanın bakımının kaç **tam ay** geciktiği.

    Her bakım türünün (`operation_type`) en son kaydı alınır, o kaydın
    `next_due` vadesi senaryo tarihiyle karşılaştırılır ve en kötü gecikme
    döner. Vadesi geçmemiş ekipman için `0`. Bilinmeyen ekipman da `0` —
    "gecikme yok" demek değil, "kaydı yok" demek; onu `not_found` ile
    ayırmak çağıranın işi.
    """
    record = load_fixture("equipment")["equipment"].get(equipment_id)
    if record is None:
        return 0
    as_of = as_of or SCENARIO_DATE
    latest: dict[str, dict] = {}
    for entry in record["maintenance_history"]:
        kind = entry["operation_type"]
        if kind not in latest or entry["date"] > latest[kind]["date"]:
            latest[kind] = entry
    overdue = [_months_between(date.fromisoformat(e["next_due"]), as_of)
               for e in latest.values()]
    return max([*overdue, 0])


def load_history(gw, store) -> int:
    """Önceki olayları arşive yükler ve gömer; **gerçekten gömülen** sayısı döner.

    Dönen sayı `store.embeddings()` ile birebir aynıdır. Epizot kaydedilmiş
    ama gömülememişse sayılmaz: gömme kademesi bozukken "3 olay yüklendi"
    demek, arama hiçbir şey bulamazken sistemin çalıştığını sanmak demektir.

    `embed_episode()` bir fikstür için `False` döndürdüğünde o olay
    **arşivde durur ama hafıza aramasında bulunamaz** — kademe düzelip
    yeniden gömülene kadar. Bu yüzden ikinci çağrı zararsız ve onarıcıdır:
    epizodu çoğaltmaz, yalnızca vektörü eksik olanları yeniden gömer.
    """
    payload = load_fixture("prior_incidents")
    archived = {e.summary_tr: e for e in store.episodes()}
    embedded = {episode_id for episode_id, _ in store.embeddings()}
    stored = 0
    for record in payload["incidents"]:
        fields = record["episode"]
        episode = archived.get(fields["summary_tr"])
        if episode is None:
            episode = Episode(**fields, state="closed")
            episode.id = store.create_episode(episode)
        elif episode.id in embedded:
            continue
        if embed_episode(gw, store, episode):
            stored += 1
        else:
            print(f"UYARI: fikstür gömülemedi — {episode.summary_tr}")
    return stored


#: Risk seviyesinin sıralaması — `min_risk` eşiği bununla karşılaştırılıyor.
#: `report.ORDER`'ın ikizi değil: orası çıktı sözleşmesinin en yüksek riskini
#: seçiyor, burası bir eşik testi yapıyor ve ikisi ayrı sebeplerle değişebilir.
_RISK_ORDER: tuple[RiskLevel, ...] = ("Düşük", "Orta", "Yüksek", "Kritik")


def load_protocols() -> list[Protocol]:
    """`protocols.json`'ı doğrulanmış `Protocol` listesine çevirir."""
    raw = load_fixture("protocols")["protocols"]
    return [Protocol(**item) for item in raw]


def match_protocols(event_class: EventClass, zone_id: str | None,
                    risk_level: RiskLevel) -> list[Protocol]:
    """Olaya uyan protokoller — **deterministik**, model karışmıyor.

    Üç süzgeç birlikte uygulanıyor:

    1. `event_class` birebir eşleşmeli. Uydurulmuş bir sınıf (`"diğer"`e
       düşürülmüş olan) hiçbir prosedürle eşleşmez ve bu doğru: yanlış
       prosedürü uygulamak, prosedürsüz kalmaktan kötüdür.
    2. `zone_ids` boşsa protokol bütün tesiste geçerli; doluysa olayın
       bölgesi listede olmalı. Bölge bilinmiyorsa (`zone_id is None`)
       yalnız tesis geneli protokoller eşleşir — bölgeye özgü bir prosedürü
       bilinmeyen bir bölgeye uygulamak varsayım üretmek olurdu.
    3. Olayın riski `min_risk`'in ALTINDAysa protokol tetiklenmez.

    Boş liste geçerli bir sonuç: çağıran (`action_planner`) onu
    `plan_source="empty"` ile kaydediyor, uydurulmuş bir plana düşmüyor.
    """
    threshold = _RISK_ORDER.index(risk_level)
    return [p for p in load_protocols()
            if p.event_class == event_class
            and (not p.zone_ids or (zone_id is not None
                                    and zone_id in p.zone_ids))
            and threshold >= _RISK_ORDER.index(p.min_risk)]
