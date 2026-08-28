"""Canlı besleme — oluş sırasında, ajan atıflı tek akış.

Beş sekmelik konsol sistemin yaptığı işi KAYNAĞINA göre bölüyordu: devirler
bir sekmede, araç çağrıları başkasında, süpervizörün konuşması üçüncüde,
epizotlar dördüncüde. Hepsi aynı on saniyede olup bitmiş şeylerdi ve hiçbir
ekran onları BİRLİKTE göstermiyordu — jüri, ajanların birbirine ne
devrettiğini görmek için sekme değiştirmek ve iki tabloyu zaman damgasından
elle eşleştirmek zorundaydı. Şartname §7 "çok adımlı karar zincirleri"ni
doğrudan puanlıyor ve o zincir tam olarak burada görünüyor.

Bu modül SAF: Gradio bilmiyor, depoyu yalnız okuyor, `tests/test_feed.py`
bütünüyle sınıyor.

## Sıra `seq`, `ts` DEĞİL

Besleme `Store.journal()`'ın küresel yazma sırasında çiziliyor. Telafi
(`DecisionLoop.catch_up`) sonradan yazılan bir kaydı ÖNCEKİ bir video
saniyesine koyabiliyor; `ts`'e göre dizmek onu yaşanmadığı bir geçmişe
taşırdı. Damga ekranda duruyor ve hangi saniyeye ait olduğunu zaten söylüyor.

## Susmak, uydurmaktan iyidir

Tanınmayan bir defter kaynağı, silinmiş bir satıra işaret eden bir satır ya
da bilinmeyen bir risk seviyesi — üçü de sessizce atlanıyor ya da kendi
rengine düşüyor. Bir tanı yüzeyi ölçtüğü koşuyu öldürmemeli (`trace.py` ile
aynı sözleşme) ve olmayan bir şeyi varmış gibi göstermemeli.
"""

import html

from gozcu.agents.orchestrator import mmss
from gozcu.agents.supervisor import AUDIT_PREFIX
from gozcu.core.models import Base

__all__ = ["FEED_EMPTY", "NO_INTERVENTION", "REALTIME_FRAMING", "FeedEntry",
           "build_feed", "format_confidence", "intervention_card",
           "visible_dialogue"]

FEED_EMPTY = "Henüz kayda değer olay yok."

GREEN = "#2e7d32"
YELLOW = "#f9a825"
ORANGE = "#ef6c00"
RED = "#c62828"
UNKNOWN_COLOR = "#546e7a"
NEUTRAL = "#78909c"

#: `RiskLevel` ile birebir aynı (CLAUDE.md). Şema ile bu tablo ayrışırsa
#: besleme sessizce gri basar — bu yüzden bilinmeyen seviye gerçek bir rengi
#: ÖDÜNÇ ALMIYOR, kendi rengine düşüyor.
RISK_COLORS = {"Düşük": GREEN, "Orta": YELLOW, "Yüksek": ORANGE,
               "Kritik": RED}

#: Ajanların ekran rozeti. Adlar İngilizce KALIYOR — sistem kimlikleri ve
#: RAPOR'daki devir defteri de aynı adları basıyor; iki ekran birbirini
#: tutmak zorunda.
AGENT_MARKS = {"perception": "👁", "orchestrator": "🧭", "interpreter": "🔎",
               "anomaly_analyst": "🧩", "risk_analyst": "⚖️",
               "action_planner": "📋", "supervisor": "🎙",
               "reporter": "📄", "operator": "👤", "system": "⚙️"}

#: Ajanların İNSANA görünen Türkçe adı — Agents ekranının (Görev raporu §3)
#: düğüm başlıkları. `AGENT_MARKS`'ın anahtarları sistem kimliği olarak
#: İngilizce kalıyor (yukarıdaki not), ama ekranda okunan metin Türkçe
#: (CLAUDE.md). İkisi AYNI sözlükte birleştirilemezdi: biri kimlik, diğeri
#: çeviri.
#:
#: Sözcükler uydurulmadı, konsolun kendi söz dağarcığından alındı — trace
#: satırları zaten `nöbetçi.duyur` ve `raportör.kök-neden` yazıyor,
#: yönlendirici de kod boyunca "yönlendirici". Görev raporu orchestrator
#: için "Yönetici AI" demişti; depo genelinde tutarlılık kazandı, çünkü
#: aynı ajanı iki ekranda iki adla anmak operatörü ikiye böler.
AGENT_LABELS = {"perception": "Algı", "orchestrator": "Yönlendirici",
                "interpreter": "Yorumlayıcı",
                "anomaly_analyst": "Anomali Analisti",
                "risk_analyst": "Risk Analisti",
                "action_planner": "Aksiyon Planlayıcı",
                "supervisor": "Nöbetçi", "reporter": "Raportör",
                "operator": "Operatör", "system": "Sistem"}

FLOOR_LABELS = {True: "taban geçti", False: "taban geçemedi"}
OUTCOME_LABELS = {"routed": "yönlendiriciye gitti",
                  "forced": "görü bütçesinden bakıldı",
                  "skipped": "hiçbir katman bakmadı",
                  "deferred": "⚠ görü kesik — telafi kuyruğuna alındı"}

PROACTIVE_MARK = "🔔 [KENDİLİĞİNDEN]"
APPROVAL_LABELS = {"not_required": "otomatik", "pending": "⏸ onay bekliyor",
                   "approved": "✓ onaylandı", "rejected": "✗ reddedildi"}

EPISODE_OPENED = "Olay açıldı"
EPISODE_MERGED = "Olaya eklendi"
EPISODE_CORRECTED = "Özet düzeltildi"


def visible_dialogue(turns: list) -> list:
    """Ekranda gösterilecek diyalog satırları. **`console.py`'dan taşındı.**

    Yalnız `[denetim]` ile BAŞLAYAN `role="system"` satırları süzülüyor —
    onlar denetim hükmünün kaydı, operatöre söylenmiş bir söz değil.

    Düz bir `role != "system"` süzgeci ise bozulmuş modu ekrandan siler:
    `Supervisor._fault`'un DEGRADED/EMPTY/UNFINISHED cevapları, `run.py`'nin
    `LATE_NOTICE` damgası ve bekleyen onay bildirimi hep `system` satırı — ve
    demo beat 6'da jürinin görmesi gereken şey tam olarak bunlar.

    Ev değişti çünkü `feed` onu `console`dan alsaydı import dairesi kapanırdı:
    `console` modül başında `feed`i çağırıyor, `feed` de yarı kurulmuş
    `console`dan bu adı isterdi ve konsol her açılışta `ImportError` ile
    ölürdü. Kural yine tek yerde duruyor, yalnız evi değişti.
    """
    return [turn for turn in turns
            if not (turn.role == "system"
                    and turn.text.startswith(AUDIT_PREFIX))]


def risk_color(level) -> str:
    """Tanınmayan seviye gerçek bir rengi ÖDÜNÇ ALMIYOR, kendi rengine düşer."""
    if level is None:
        return NEUTRAL
    return RISK_COLORS.get(level, UNKNOWN_COLOR)


def format_confidence(value: float) -> str:
    """Güveni Türkçe ondalık virgülle yazar — TEK biçimlendirme yeri.

    Devir defteri (`view.py::handoff_rows`) ve tel (`server.py::
    _dump_feed_entry`, tarayıcı karar veren hiçbir şey yapmasın diye) AYNI
    dizeyi bu fonksiyondan alıyor. İkinci bir kopya (`js/feed.js`'in eski
    `toFixed(2)` + virgül değişimi gibi) bir gün ayrışır ve iki ekran aynı
    güveni iki biçimde gösterir — tıpkı `RISK_COLORS`'ın ikinci bir renk
    tablosuna karşı uyardığı gibi.
    """
    return f"güven {value:.2f}".replace(".", ",")


class FeedEntry(Base):
    """Beslemedeki tek girdi. Saf veri; çizim tarayıcının işi.

    Görev 11'e kadar bu modülde bir `feed_html` de vardı ve beslemeyi
    Gradio için tek bir HTML dizesine çiziyordu. Web konsolu girdileri
    telde JSON olarak alıp `js/feed.js`'te artımlı çiziyor — sunucuda
    ikinci bir çizici tutmak iki ekranın aynı veriyi iki biçimde
    göstermesi demekti.
    """

    seq: int
    ts: float
    agent: str
    kind: str
    title: str
    detail: str = ""
    target: str | None = None
    risk: str | None = None
    confidence: float | None = None
    #: Kimse sormadan söylenmiş bir süpervizör satırı mı. AYRI bir alan,
    #: `title`'a gömülü bir önek değil: `title` saf metin kalmalı, yoksa
    #: rozeti metinden ayırmak isteyen her okuyucu dizeyi kesmek zorunda
    #: kalır ve kaçırma (`html.escape`) sunumu da kapsar.
    proactive: bool = False
    #: Yükseltme kartının HTML'i — yalnız `kind == "escalation"` girdilerde.
    #: Kart burada duruyor çünkü beslemenin İÇİNDE, olduğu anda basılıyor;
    #: ayrı bir sekme onu olaydan koparıyordu.
    card: str | None = None


#: Bir araç sonucunda "işe yaradı mı" sorusunu cevaplayan alanlar. Sonuç
#: sözlüğü kesilirken bunlar ÖNE alınıyor: 26 Ağustos koşusunda ekranda
#: `alarm_id=…, affected_zone=…, zone_id=None …` yazıyordu ve gerçek cevap —
#: `siren_state=zone_unresolved`, yani siren hiç çalmadı — üç noktanın
#: arkasında kalmıştı. Bir aracın çalışmadığını gizleyen şerit, o aracın
#: çalıştığını iddia eder.
OUTCOME_KEYS = ("state", "siren_state", "refused", "duplicate", "failed",
                "not_found", "error")


def _outcome_first(result: dict) -> dict:
    """Sonuç sözlüğünü, akıbeti söyleyen alanlar başa gelecek şekilde dizer."""
    if not result:
        return result
    lead = {key: result[key] for key in OUTCOME_KEYS if key in result}
    return {**lead, **{k: v for k, v in result.items() if k not in lead}}


def _pairs(mapping: dict, limit: int = 3) -> str:
    """Sözlüğü `anahtar=değer` olarak yazar; boşsa tire.

    Boş bırakmak yerine tire: boş bir hücre "parametresiz çağrıldı" ile
    "gösterilmedi" arasındaki farkı yutar.
    """
    if not mapping:
        return "—"
    items = list(mapping.items())[:limit]
    text = ", ".join(f"{key}={value}" for key, value in items)
    return text + (" …" if len(mapping) > limit else "")


# --- müdahale kartı ---------------------------------------------------------
#
# Kart `console.py`'dan TAŞINDI ve artık kendi sekmesinde değil, beslemenin
# İÇİNDE, yükseltmenin olduğu anda basılıyor. Ayrı bir sekme onu olaydan
# koparıyordu: jüri kartı görmek için ekran değiştirmek zorundaydı ve kartın
# hangi saniyeye ait olduğu ancak damgadan çıkarılabiliyordu.

REALTIME_FRAMING = "Gerçek zamanlı kurulumda ajan bu anda müdahale ederdi"

CARD_TITLE = "MÜDAHALE ANI"
CARD_SEEN = "GÖRDÜĞÜ"
CARD_SAID = "DEDİĞİ"
CARD_CALLED = "ÇAĞIRDIĞI"
CARD_GATED = "ONAY İSTEDİĞİ"
CARD_WHY = "GEREKÇE"
CARD_PRECEDENT = "EMSAL"

#: Hiç yükseltme olmadığında yazılan şey. "Henüz olay yok" DEĞİL: olay
#: olabilir ve yine de hiçbiri yükseltmeye değmemiş olabilir — ikisi farklı
#: şeyler ve besleme zaten olayları gösteriyor.
NO_INTERVENTION = ("Bu koşuda ajan hiçbir ana müdahale etmedi. "
                   "Açılan olaylar zaman çizelgesinde.")


def _card_row(label: str, value: str) -> str:
    """Kartın tek satırı. Boş değer yerine tire — boş hücre "yoktu" ile
    "gösterilmedi"yi aynı şeye çevirir."""
    return (f"<tr><td style='padding:.15rem .6rem .15rem 0;"
            f"vertical-align:top;opacity:.65;white-space:nowrap'>{label}</td>"
            f"<td style='padding:.15rem 0'>{value or '—'}</td></tr>")


def _tool_line(action) -> str:
    return (f"<code>{html.escape(action.tool_name)}</code> "
            f"<span style='opacity:.7'>({html.escape(_pairs(action.params))})</span>")


def intervention_card(episode, risk, actions: list, said: str,
                      ts: float | None = None) -> str:
    """Tek bir yükseltme anının kartı — "gerçek zamanlı olsaydı ne olurdu".

    Damga YÜKSELTME ANI — canlı yolda ilk risk değerlendirmesinin `ts`'i
    (ilk değerlendirme ilk yükseltmenin içinde koşar, ikisi aynı an;
    kapanışta değerlendirilip geç yükseltilen telafi epizodunda kapanış anı
    basılır — kabul edilen sapma). `ts=None` `event_ts`'e düşer: doğrudan
    çağıranlar ve damgasız eski kayıtlar için.

    Onay kapısı **yalnız** `halt_production_line`'da (`tools/registry.py`).
    Bu yüzden çağrılar ikiye ayrılıyor: kendiliğinden geçenler ve onay
    isteyenler. Altı aracı "onay bekliyor" diye çizmek tasarımı yanlış
    anlatırdı.

    Model metni HTML olarak kaçırılıyor — ham basılırsa sayfayı bozar.
    """
    stamp = ts if ts is not None else episode.event_ts
    color = risk_color(risk.level if risk else episode.preliminary_risk)
    level = risk.level if risk else episode.preliminary_risk
    gated = [a for a in actions
             if a.approval in ("pending", "approved", "rejected")]
    automatic = [a for a in actions if a.approval == "not_required"]

    rows = [
        _card_row(CARD_SEEN,
                  html.escape(episode.summary_tr)
                  + (f" <span style='opacity:.7'>· "
                     f"{html.escape(', '.join(episode.participants))}</span>"
                     if episode.participants else "")),
        _card_row(CARD_SAID, html.escape(said)),
        _card_row(CARD_CALLED,
                  "<br>".join(f"✓ {_tool_line(a)}" for a in automatic)),
    ]
    if gated:
        rows.append(_card_row(
            CARD_GATED,
            "<br>".join(
                f"{APPROVAL_LABELS.get(a.approval, a.approval)} "
                f"{_tool_line(a)}" for a in gated)))
    rows.append(_card_row(CARD_WHY,
                          html.escape(risk.rationale_tr) if risk else ""))

    # Emsal satırı DETERMİNİSTİK — model prozasından değil, arşivin
    # kendisinden geliyor. Emsal yoksa satır HİÇ basılmıyor: boş bir
    # "EMSAL —" satırı "arşivde kayıt yok" ile "arşive bakılmadı"yı aynı
    # şeye çevirirdi.
    # `getattr` fallback'i YOK: `RiskAssessment.precedents` varsayılanlı bir
    # alan ve her zaman var. Ölü bir dal, çalıştığı sanılan bir daldır.
    precedents = risk.precedents if risk else []
    if precedents:
        lines = []
        for precedent in precedents:
            past = precedent.episode
            when = (past.occurred_at or "")[:10] or "—"
            origin = past.source or "—"
            lines.append(
                f"{html.escape(past.summary_tr)} "
                f"<span style='opacity:.7'>· {html.escape(when)} "
                f"· {html.escape(origin)} · benzerlik "
                # Türkçe ondalık VİRGÜL — `format_confidence` (bu dosyada)
                # aynı kuralı "TEK biçimlendirme yeri" diye ilan ediyor ve
                # ikinci bir biçim bir gün ondan ayrışır.
                + f"{precedent.score:.2f}".replace(".", ",") + "</span>")
        rows.append(_card_row(CARD_PRECEDENT, "<br>".join(lines)))

    return (
        f"<div style='border:1px solid {color};border-left:6px solid {color};"
        f"border-radius:6px;padding:.6rem .8rem;margin:.5rem 0'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:baseline;gap:1rem'>"
        f"<b>⚠ {html.escape(mmss(stamp))} — {CARD_TITLE}</b>"
        f"<span style='color:{color};font-weight:600'>{html.escape(level)}</span>"
        f"</div>"
        f"<div style='opacity:.75;font-style:italic;margin:.25rem 0 .5rem'>"
        f"{REALTIME_FRAMING}</div>"
        f"<table style='border-collapse:collapse;font-size:.92em'>"
        f"{''.join(rows)}</table></div>")

def _proactive_ids(turns: list) -> set:
    """Kimse sormadan söylenmiş süpervizör satırlarının kimlikleri.

    Kaynak **`DialogueTurn.proactive`** — `escalate()` yazma anında
    işaretliyor. Eskiden komşuluktan türetiliyordu ("kendinden önce operatör
    satırı yoksa kimse sormamıştır") ve o kural iş parçacıkları arasında
    kırılıyor: `talk()` operatör satırını yazıp saniyelerce modelde kalıyor,
    o boşlukta düşen bir yükseltme sırayı operatör → yükseltme → cevap
    yapıyor ve rozet YANLIŞ satıra takılıyor. Adım adım kapalıyken (demo
    varsayılanı) boru hattı koşmaya devam ettiği için bu gerçek bir ihtimal.

    Türetilmiş yedek YOK. Bir yedek yazıldı ve ölü çıktı: `proactive` bir
    `bool` ve hiçbir zaman `None` olmuyor, yani "alan yok" diye bir durum
    kurulamıyor. Ölü bir dal, çalıştığı sanılan bir daldır.
    """
    return {turn.id for turn in visible_dialogue(turns)
            if turn.role == "supervisor" and turn.proactive}


def _window_entry(seq: int, record, outcome: str | None = None) -> FeedEntry:
    """Algı satırı.

    `outcome` anlık görüntüden geliyor: kayıt sonradan düzeltilebiliyor
    (kesinti telafi kuyruğu) ve canlı okumak ilk satıra o düzeltmeyi
    bastırırdı.
    """
    outcome = outcome or record.outcome
    return FeedEntry(
        seq=seq, ts=record.ts, agent="perception", kind="window",
        title=(f"Pencere {record.index}/{record.total} "
               f"({mmss(record.ts)}–{mmss(record.end_ts)}) — "
               f"{FLOOR_LABELS[record.floor_passed]}"),
        detail=(f"{record.frames} kare · kişi≤{record.person_peak} · "
                f"kutu={record.detections} · "
                f"{', '.join(record.labels) or 'tespit yok'} · "
                f"{OUTCOME_LABELS.get(outcome, outcome)}"))


def _episode_entry(entry, episode, card: str | None = None) -> FeedEntry:
    snapshot = entry.snapshot or {}
    # `update_episode`'un İKİ çağıranı var ve ikisi ayrı şeyler yapıyor:
    # sentezleyici kaynaştırıyor, süpervizör operatörün sözüyle özeti
    # DÜZELTİYOR. Tek satıra düşerlerse insan müdahalesi model çıktısı gibi
    # görünür — %20'lik otonomi kriteri tam olarak bunu soruyor.
    origin = snapshot.get("origin", "anomaly_analyst")
    if entry.kind == "create":
        kind, note = "episode", EPISODE_OPENED
    elif origin == "supervisor":
        kind, note = "episode_update", EPISODE_CORRECTED
    else:
        kind, note = "episode_update", EPISODE_MERGED
    # Yükseltme çapası `create` ile SINIRLI DEĞİL: açık bir epizotta
    # `escalate` `_resolve` ile kaynaşmaya iniyor ve o an bir `update` satırı
    # doğuruyor.
    if card is not None:
        kind = "escalation"
    # Epizot kendi içinde bir zaman çizelgesi taşıyor. Tek satıra
    # düşürülürse operatör olayın SEYRİNİ değil yalnız pencerenin sınırını
    # görür — anlar bu yüzden damgalarıyla birlikte satırın altında duruyor
    # (teslim edilen `events[]` ile aynı kural, bkz. `gozcu.report._events`).
    beats = snapshot.get("beats")
    if beats is None:
        beats = [[beat.ts, beat.text] for beat in episode.beats]
    if beats:
        note = " · ".join([note] + [f"{mmss(ts)} {text}"
                                    for ts, text in sorted(beats)])
    # Damga: AÇILIŞTA olayın gerçekten başladığı an (`start_ts` pencerenin
    # sınırı ve öyle kalmak zorunda — bkz. `models.Episode.event_ts`), ama
    # KAYNAŞMADA kaynaşmanın olduğu an.
    #
    # İkisi ayrılmazsa besleme geriye doğru sayar: 26 Ağustos koşusunda
    # 01:13'ten sonra 00:40 yazıyordu, çünkü her kaynaşma epizodun ilk anını
    # basıyordu. Sıra doğruydu (yazma sırası), saat yalan söylüyordu.
    start = snapshot.get("start_ts", episode.start_ts)
    if entry.kind == "create":
        ts = min((beat_ts for beat_ts, _ in beats), default=start)
    else:
        ts = snapshot.get("end_ts") or episode.end_ts or start
    return FeedEntry(
        seq=entry.seq, ts=ts, agent=origin, kind=kind,
        title=snapshot.get("summary_tr", episode.summary_tr), detail=note,
        risk=snapshot.get("preliminary_risk", episode.preliminary_risk),
        card=card)


def build_feed(store, escalated_ids=None, archived=None) -> list:
    """Defteri `seq` sırasında gezip besleme girdilerine çevirir.

    `archived` — koşudan ÖNCE depoda duran epizot kimlikleri.
    `fixtures.loader.load_history` arşiv fikstürlerini epizot olarak yazıyor
    ve onlar bu videonun olayı değil; beslemede "sentezleyici olay açtı" diye
    görünürlerse ekran olmamış bir şey iddia eder. `run.py` aynı korumayı
    risk biçmesi için zaten yapıyor.

    `escalated_ids` ajanın gerçekten yükselttiği epizotlar — o girdi kart
    olarak vurgulanıyor. `None` geçilirse hiçbir şey vurgulanmıyor:
    "bilmiyorum"un güvenli yorumu abartmak değil susmaktır.
    """
    skip = set(archived or ())
    escalated = set(escalated_ids or ())

    windows = {r.id: r for r in store.window_records()}
    handoffs = {h.id: h for h in store.handoffs()}
    interpretations = {i.id: i for i in store.interpretations()}
    episodes = {e.id: e for e in store.episodes()}
    risks = {r.id: r for r in store.risks()}
    plans = {p.id: p for p in store.action_plans()}
    actions = {a.id: a for a in store.actions()}

    dialogue = store.dialogue()
    visible = {turn.id: turn for turn in visible_dialogue(dialogue)}
    proactive = _proactive_ids(dialogue)

    # Kart malzemesi. Araçlar epizodun KENDİ zaman aralığına göre eşleniyor:
    # bir çağrının hangi olaya ait olduğunu söyleyen başka bir alan yok
    # (`ActionRecord` yalnız `ts` taşıyor). Açık epizotta `end_ts` `None`
    # olabiliyor, o zaman üst sınır yok.
    risk_by_episode = {risk.episode_id: risk for risk in risks.values()}

    # Yükseltilen bir epizot birden çok defter satırı taşıyor (açılış, sonra
    # her kaynaşma). Hepsini işaretlemek AYNI kartı iki üç kez bastırırdı —
    # beslemenin ortadan kaldırmak için var olduğu tekrarın ta kendisi. Kart
    # epizodun SON satırına iliştiriliyor: yükseltme o an yaşandı.
    journal = store.journal()          # TEK okuma: iki ayrı okuma arasında
                                       # düşen bir yazma kartı bayat satıra
                                       # iliştirirdi.
    last_row_of = {}
    for entry in journal:
        if entry.source == "episode" and entry.row_id in escalated:
            last_row_of[entry.row_id] = entry.seq

    # #3 — kartın DEDİĞİ'si defter sırasından: `talk()` sohbet cevabını açık
    # epizodun `start_ts`'ine sabitliyor, yani ts anahtarlı bir arama
    # yükseltmeden ÖNCEKİ bir sohbet cevabını karta yazabiliyordu.
    supervisor_says = [(row.seq, visible[row.row_id].text)
                       for row in journal
                       if row.source == "dialogue" and row.row_id in visible
                       and visible[row.row_id].role == "supervisor"]

    entries = []
    for entry in journal:
        made = None

        if entry.source == "window_record":
            record = windows.get(entry.row_id)
            if record and entry.kind == "create":
                made = _window_entry(entry.seq, record,
                                     (entry.snapshot or {}).get("outcome"))
            elif record:
                # Akıbet düzeltmesi: pencere işlendi, SONRA kesinti yüzünden
                # telafi kuyruğuna alındı. İkisi de olmuş şeyler ve ayrı
                # satırlar — düzeltmeyi ilk satıra yazmak kesintiyi olayın
                # başında olmuş gibi gösterirdi.
                outcome = (entry.snapshot or {}).get("outcome", record.outcome)
                made = FeedEntry(
                    seq=entry.seq, ts=record.ts, agent="perception",
                    kind="window_update",
                    title=f"Pencere {record.index}/{record.total} — "
                          f"{OUTCOME_LABELS.get(outcome, outcome)}")

        elif entry.source == "handoff":
            handoff = handoffs.get(entry.row_id)
            if handoff:
                made = FeedEntry(
                    seq=entry.seq, ts=handoff.ts, agent=handoff.source_agent,
                    kind="handoff",
                    title=f"{handoff.source_agent} → {handoff.target_agent}",
                    detail=handoff.reason, target=handoff.target_agent,
                    confidence=handoff.confidence)

        elif entry.source == "interpretation":
            reading = interpretations.get(entry.row_id)
            if reading:
                made = FeedEntry(
                    seq=entry.seq, ts=reading.observation_ts,
                    agent="interpreter", kind="interpretation",
                    title=reading.description,
                    detail=" · ".join(beat.text for beat in reading.beats))

        elif entry.source == "episode":
            episode = episodes.get(entry.row_id)
            if episode is not None and entry.row_id not in skip:
                card = None
                if last_row_of.get(entry.row_id) == entry.seq:
                    window = [
                        action for action in actions.values()
                        if action.ts >= episode.start_ts
                        and (episode.end_ts is None
                             or action.ts <= episode.end_ts)]
                    spoken = next((text for seq, text in supervisor_says
                                   if seq > entry.seq), "")
                    first_risk = next(
                        (r for r in risks.values()
                         if r.episode_id == episode.id and r.ts), None)
                    card = intervention_card(
                        episode, risk_by_episode.get(episode.id), window,
                        spoken,
                        ts=first_risk.ts if first_risk else episode.event_ts)
                made = _episode_entry(entry, episode, card)

        elif entry.source == "risk":
            risk = risks.get(entry.row_id)
            if risk:
                episode = episodes.get(risk.episode_id)
                # Değerlendirmenin KENDİ anı (spec §6). 0.0 damgasız eski
                # kayıt demek; o durumda epizot damgasına düşülür.
                # Öneri artık bu satırda değil — analist yalnız derecelendirir
                # (Görev 6, spec §2d); öneriler kendi "action_plan" satırında.
                made = FeedEntry(
                    seq=entry.seq,
                    ts=risk.ts or (episode.event_ts if episode else 0.0),
                    agent="risk_analyst", kind="risk",
                    title=risk.rationale_tr, detail="", risk=risk.level)

        elif entry.source == "action_plan":
            plan = plans.get(entry.row_id)
            if plan:
                proposed = " · ".join(a.description_tr
                                      for a in plan.proposed_actions)
                made = FeedEntry(
                    seq=entry.seq, ts=plan.ts,
                    agent="action_planner", kind="plan",
                    title=(f"prosedür: {plan.protocol_id}"
                           if plan.protocol_id else "tanımlı prosedür yok"),
                    detail=f"öneri: {proposed}" if proposed else "")

        elif entry.source == "dialogue":
            turn = visible.get(entry.row_id)
            if turn and turn.role == "operator":
                made = FeedEntry(seq=entry.seq, ts=turn.ts, agent="operator",
                                 kind="dialogue", title=turn.text)
            elif turn and turn.role == "system":
                made = FeedEntry(seq=entry.seq, ts=turn.ts, agent="system",
                                 kind="dialogue", title=turn.text)
            elif turn:
                made = FeedEntry(seq=entry.seq, ts=turn.ts, agent="supervisor",
                                 kind="dialogue", title=turn.text,
                                 proactive=turn.id in proactive)

        elif entry.source == "action":
            made = _action_entry(entry, actions)

        # `correction` bilerek atlanıyor: `Supervisor._apply_correction` hem
        # düzeltmeyi hem epizot güncellemesini yazıyor ve ikisini de basmak
        # tek bir düzeltmeyi iki kez göstermek olurdu. Güncelleme satırı
        # `origin="supervisor"` ile zaten "Özet düzeltildi" diyor.
        #
        # Tanınmayan `source` SUSARAK atlanıyor: yeni bir tablo eklenip
        # eşleme unutulursa besleme uydurmak yerine susar.
        if made is not None:
            entries.append(made)
    return entries


def _action_entry(entry, actions: dict):
    """Araç çağrısı ya da onay kararı.

    Onaylı bir araç ÜÇ defter satırı doğuruyor: ajanın `pending` çağrısı,
    operatörün ikinci `call_tool`u ve onay güncellemesi. Üçünü de basmak, bir
    kez çağrılan aracı üç kez çağrılmış gibi gösterir — operatörün ikiz
    `create`i atlanıyor, karar zaten onay satırında görünüyor.
    """
    action = actions.get(entry.row_id)
    if action is None:
        return None

    if entry.kind != "create":
        state = (entry.snapshot or {}).get("approval", action.approval)
        return FeedEntry(
            seq=entry.seq, ts=action.ts, agent="operator", kind="approval",
            title=f"{action.tool_name} — "
                  f"{APPROVAL_LABELS.get(state, state)}")

    if action.actor == "operator" and any(
            other.tool_name == action.tool_name and other.ts == action.ts
            and other.actor == "agent" and (other.id or 0) < (action.id or 0)
            for other in actions.values()):
        return None

    state = (entry.snapshot or {}).get("approval", action.approval)
    # `actor` "insan mı makine mi", `caller` **hangi ajan**. Risk analisti
    # soruşturma araçlarını `assess_risk` içinde, süpervizör daha ağzını
    # açmadan çağırıyor; hepsini süpervizöre yazmak zincir hakkında yalan
    # söylemek olurdu — ve §7'nin puanladığı şey tam olarak o zincir.
    return FeedEntry(
        seq=entry.seq, ts=action.ts,
        agent=action.caller if action.actor == "agent" else "operator",
        kind="action", title=action.tool_name,
        detail=(f"parametre: {_pairs(action.params)} · "
                f"sonuç: {_pairs(_outcome_first(action.result))} · "
                f"{APPROVAL_LABELS.get(state, state)}"))
