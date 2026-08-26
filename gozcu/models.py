"""Ajan katmanının paylaşılan sözleşmesi.

Modül sınırını geçen her kayıt burada tanımlı. Hiçbir görev kendi tipini
uydurmaz — eksik bir tip varsa buraya eklenir.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["Düşük", "Orta", "Yüksek", "Kritik"]

#: Bir anın Türkçe metninin üst sınırı. `EventSummary.event` (200) altında
#: bilerek: her an teslim edilen olay listesine olduğu gibi giriyor, kesilmesi
#: gereken bir metin oraya hiç ulaşmamalı.
MAX_BEAT_TEXT = 160
#: Bir klipten okunacak an sayısı. Şemaya `maxItems` olarak da geçiyor
#: (`strict_schema` onu bilerek telde bırakıyor) — kaçak tekrara karşı tek
#: koruma o. 10 saniyelik bir pencerede 4–6 an zaten bol.
MAX_BEATS = 6
#: Bir epizodun biriktirebileceği an sayısı. Kaynaşma anları EKLİYOR (yoksa
#: olayın başladığı an bir sonraki pencerede kaybolur), dolayısıyla uzun bir
#: olayda liste pencere sayısıyla büyür; teslim edilen `events[]` bir zaman
#: çizelgesi olmalı, bir kayıt dökümü değil.
MAX_EPISODE_BEATS = 12
AgentName = Literal["perception", "router", "interpreter", "synthesizer",
                    "risk_analyst", "supervisor", "reporter"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClipBeat(Base):
    """Görü kademesinin okuduğu klip içi bir an.

    `offset_s` **klibin başlangıcından** itibaren saniye — mutlak video
    zamanı DEĞİL. Çeviriyi tek bir yer yapıyor (`gozcu.agents.synthesizer`):
    `window[0].ts + offset_s`.
    """

    offset_s: float = Field(ge=0.0)
    text: str = Field(max_length=MAX_BEAT_TEXT)


class EventBeat(Base):
    """Epizoda taşınmış an — `ts` **mutlak video saniyesi**.

    `ClipBeat` ile aynı şey değil ve bilerek ayrı tipler: ikisi tek tipte
    birleştirilirse göreli bir damga hiç fark edilmeden mutlak damga
    yerine geçer ve olay yanlış saniyeye yazılır.
    """

    ts: float
    text: str = Field(max_length=MAX_BEAT_TEXT)


class Detection(Base):
    label: str
    confidence: float
    box: tuple[float, float, float, float]
    track_id: int | None = None


class Signals(Base):
    velocities: dict[int, float] = Field(default_factory=dict)
    vanished_tracks: list[int] = Field(default_factory=list)
    #: Kadraj kenarına DEĞMEDEN kaybolan izler — `vanished_tracks`'in alt
    #: kümesi. Kadrajı terk eden bir insan gitmiştir; kadrajın ortasında
    #: kaybolan bir insan bir şeyin İÇİNE girmiştir ve bu ikisini aynı
    #: kelimeyle anlatmak "makineye kapıldı"yı "çıkıp gitti" diye okur.
    interior_vanished_tracks: list[int] = Field(default_factory=list)
    person_count: int = 0
    person_count_delta: int = 0
    gathering: bool = False


class Observation(Base):
    id: int | None = None
    ts: float
    detections: list[Detection] = Field(default_factory=list)
    signals: Signals = Field(default_factory=Signals)


class RouterDecision(Base):
    decision: Literal["ignore", "inspect", "open_episode",
                      "update_episode", "close_episode", "escalate"]
    rationale: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)


class Interpretation(Base):
    id: int | None = None
    observation_ts: float
    description: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)
    #: Klip içindeki anlar, klibin başlangıcına göre (bkz. `ClipBeat`).
    beats: list[ClipBeat] = Field(default_factory=list, max_length=MAX_BEATS)
    model: str
    latency_ms: int = 0
    tokens: int = 0


class Episode(Base):
    id: int | None = None
    start_ts: float
    end_ts: float | None = None
    phase: Literal["onset", "development", "outcome"]
    summary_tr: str = Field(max_length=600)
    participants: list[str] = Field(default_factory=list)
    preliminary_risk: RiskLevel
    state: Literal["open", "closed"] = "open"
    #: Olayın içindeki anlar, MUTLAK video saniyesiyle (bkz. `EventBeat`).
    beats: list[EventBeat] = Field(default_factory=list)
    #: `summary_tr` modelden mi geldi, yoksa bir ARIZA metni mi.
    #:
    #: Metne bakarak ayırt edilemiyor ve ayırt edilmediği için bir kez ağır
    #: bir şey oldu: sentezleyici boş döndü, özet "Sentez katmanı boş yanıt
    #: döndürdü" oldu, süpervizör onu fabrikada olmuş bir olay sanıp var
    #: olmayan bir bölgeye alarm çaldırdı ve sağlık ekibi çağırdı. Arıza
    #: metni bir olay tarifi DEĞİLDİR ve onu tüketen her katman bunu
    #: bilmek zorunda.
    summary_source: Literal["model", "fallback"] = "model"

    @property
    def event_ts(self) -> float:
        """Olayın gerçekten başladığı an.

        `start_ts` PENCERENİN sınırı olarak kalıyor ve öyle kalmak zorunda:
        devir defteri, süpervizörün gözlem penceresi (`start_ts <= o.ts <=
        end_ts`) ve aksiyon defteri onu aralık başlangıcı olarak okuyor —
        ileri kaydırılırsa olaydan önceki gözlemler sessizce kadraj dışında
        kalır. Olayın anı bu yüzden AYRI taşınıyor: ilk an, yoksa pencere
        başlangıcı.
        """
        return min((beat.ts for beat in self.beats), default=self.start_ts)


class LoopEvent(Base):
    """`DecisionLoop.run()`'ın yield ettiği şey.

    Tek kanaldan iki farklı anlam akıyordu: canlı bir yükseltme ile kesinti
    sonrası geri doldurulan bir epizot ayırt edilemiyordu, çağıran taraf da
    bayat olanı taze kriz gibi duyuruyordu. `late` bu ikisini ayırır.
    """

    episode: Episode
    late: bool = False      # kesinti sonrası geri doldurulduysa True


class ProposedAction(Base):
    description_tr: str = Field(max_length=200)
    tool_name: str
    params: dict = Field(default_factory=dict)


class RiskAssessment(Base):
    id: int | None = None
    episode_id: int
    level: RiskLevel
    rationale_tr: str = Field(max_length=800)
    preventable: bool
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


class Handoff(Base):
    id: int | None = None
    ts: float
    source_agent: AgentName
    target_agent: AgentName
    reason: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    payload_ref: str


class ActionRecord(Base):
    """Deftere yazılmış bir araç çağrısı.

    `actor` "insan mı makine mi", `caller` ise **hangi ajan**. İkisi ayrı
    sorular: risk analisti kendi soruşturma araçlarını `assess_risk` içinde
    çağırıyor (`risk.py`) ve o çağrılar süpervizör daha ağzını açmadan
    deftere düşüyor. Tek bir "ajan" etiketi onları süpervizöre yazardı ve
    besleme zincirin kendisi hakkında yalan söylerdi.
    """

    id: int | None = None
    ts: float
    tool_name: str
    params: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    actor: Literal["agent", "operator"]
    approval: Literal["not_required", "pending", "approved", "rejected"]
    #: Varsayılan süpervizör: araçların çoğunu o çağırıyor ve varsayılan,
    #: alan eklenmeden önce yazılmış satırları da geçerli tutuyor.
    caller: AgentName = "supervisor"


class Correction(Base):
    id: int | None = None
    ts: float
    episode_id: int
    field: str
    old: str
    new: str
    rationale: str = Field(max_length=300)


class WindowRecord(Base):
    """Bir pencerenin algı + triyaj özeti.

    Aynı sayılar `DecisionLoop.run()` içinde hesaplanıp yalnız `trace`e
    gidiyordu — yani ekranda "sistem bu on saniyede ne gördü" sorusunun
    cevabı hiç yoktu. Besleme buradan okuyor; ham gözlem 3 fps ile akıyor
    (on saniyede ~30 satır) ve ekrana basılamaz.

    `outcome` dört dalı ayırıyor: `routed` tabandan geçti ve yönlendiriciye
    gitti, `forced` geçemedi ama görü bütçesine seçildi, `skipped` hiçbir
    katman bakmadı, `deferred` görü kademesi kesikti ve pencere telafi
    kuyruğuna alındı. "Bakılmadı" ile "bakıldı, bir şey yoktu" aynı kelimeye
    düşemez — biri kör noktadır, öbürü ölçümdür; "kesinti yüzünden
    bakılamadı" ise üçüncü bir şey ve demo beat 6'nın kendisi.
    """

    id: int | None = None
    ts: float
    end_ts: float
    index: int
    total: int
    frames: int
    person_peak: int = 0
    detections: int = 0
    labels: list[str] = Field(default_factory=list)
    floor_passed: bool
    vision_budgeted: bool = False
    outcome: Literal["routed", "forced", "skipped", "deferred"]


class JournalEntry(Base):
    """Bir yazmanın küresel sıradaki yeri.

    Tipli tablolar tek gerçek kaynak olarak KALIYOR; defter yalnız "hangi
    satır ne zaman yazıldı"yı söylüyor. `seq` süreç boyunca artan tek sayaç —
    aynı `ts`'e düşen yazmaları ayıran tek şey o, çünkü satır kimlikleri
    TABLO BAŞINA artıyor ve bir pencerenin bütün üretimi aynı saniyeye
    düşüyor.

    `snapshot` yalnız DEĞİŞEN kayıtlarda dolu (epizot, aksiyon onayı): defter
    satırı canlı satıra çözülürse o an geçerli olmayan bir metin basılır ve
    ekran söylenmemiş bir şeyi söylemiş gibi görünür.
    """

    seq: int
    source: str
    row_id: int
    kind: Literal["create", "update", "approval"]
    snapshot: dict | None = None


class DialogueTurn(Base):
    """Bir diyalog turu.

    `proactive` **yazma anında** kaydediliyor, sonradan komşuluktan
    türetilmiyor. Türetme iş parçacıkları arasında kırılıyor: `talk()` önce
    operatör satırını yazıyor, sonra saniyelerce modelde kalıyor; o boşlukta
    düşen bir yükseltme sırayı operatör → yükseltme → cevap yapıyor ve
    komşuluk kuralı rozeti YANLIŞ satıra takıyor. `escalate()` kendisinin
    kimse sormadan konuştuğunu zaten biliyor.
    """

    id: int | None = None
    ts: float
    role: Literal["operator", "supervisor", "system"]
    text: str
    proactive: bool = False


class EventSummary(Base):
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    event: str = Field(max_length=200)


class Detail(Base):
    episodes: list[Episode] = Field(default_factory=list)
    risk_assessments: list[RiskAssessment] = Field(default_factory=list)
    handoff_chain: list[Handoff] = Field(default_factory=list)
    action_ledger: list[ActionRecord] = Field(default_factory=list)
    root_cause_report: dict | None = None


class PipelineOutput(Base):
    summary: str
    events: list[EventSummary] = Field(default_factory=list)
    risk: RiskLevel
    actions: list[str] = Field(default_factory=list)
    detail: Detail | None = None
