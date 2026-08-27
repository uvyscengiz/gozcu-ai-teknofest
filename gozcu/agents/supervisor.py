"""Nöbetçi — operatörün konuştuğu ajan ve topolojinin ortası.

Şartnamenin "Otonomi ve Zeka" kalemi (%20) dört şey istiyor ve dördü de burada
karşılanıyor: kimse sormadan haber vermek (`escalate`), göremediğini sormak
(`uncertainty_note`), konu değişse de açık olaya dönmek (`talk`) ve doğal bir
Türkçe akış (sistem promptu).

Süpervizörün kendi araçları yedi saha aracının **yanına** ekleniyor; iki tür
arasında seçim yapmak model için tek bir karar oluyor ve şartnamenin puanladığı
*dinamik araç seçimi* defterden okunabiliyor.

## Onay kapısında yalnız `halt_production_line` var — ve bu bir karar

`NEEDS_APPROVAL` tek bir araç sayıyor. Bu bir eksik değil, bilerek verilmiş bir
iş güvenliği hükmü:

- `dispatch_medical`, `radio_call`, `site_alarm` ve `open_safety_incident`
  **geri alınabilir ve ucuz.** Yanlış çağrılan bir sağlık ekibi geri döner,
  boşuna çalan bir siren susturulur, fazladan açılan bir İSG kaydı kapatılır.
  Buna karşılık gecikmenin bedeli **can**: yerde hareketsiz bir kişi varken
  ekibi operatörün onayını bekletmek, kaybedilen her saniyeyi bir onay
  ekranına ödemek olurdu. Bu yüzden dördü de anında yürüyor.
- `halt_production_line` **geri alması zor ve pahalı.** Duran bir hattın
  yeniden devreye alınması vardiya planını, üretim çizelgesini ve teslimat
  taahhüdünü etkiler; ajanın tek başına vereceği bir karar değil. Bu yüzden
  kapıda bekliyor.

Kısacası: **geri alınabilir olan hemen koşar, geri alınamayan insana sorar.**
Ajan kendi hat durdurmasını onaylayamaz — onayın tek kaynağı aksiyon defteri
(`registry.call_tool`).

## Aynı anda tek bir onay bekleyebilir

`pending_approval()` tek bir kayıt döndürüyor. İkinci bir bekleyen satır
doğduğu anda birincisi kalıcı olarak görünmez olurdu: defterde sonsuza dek
`"pending"` kalır, konsolun onay çubuğu ise bayat satırın üzerine yeniden
açılırdı. Bu yüzden kapı **girişte** kapanıyor: onay bekleyen bir aksiyon
varken yeni bir kapılı aksiyon yürütülmüyor, modele reddedildiği söyleniyor ve
operatöre neyin beklediği Türkçe olarak bildiriliyor. Böylece "tek kayıt"
varsayımı bir umut değil, yapısal bir değişmez.

## Prompt ile şema ayrışamaz

Promptun araç kataloğu `ALL_TOOL_SCHEMAS`'tan **türetiliyor**; düzeltme
aracının adı da prompta elle yazılmıyor, `CORRECT_OBSERVATION` sabitinden
geliyor. Elle yazılmış bir ad ayrışır — ve ayrıştığında model var olmayan bir
aracı çağırır, düzeltme kaskadı hiç tetiklenmez, `correction_propagation` KPI'ı
sessizce sıfır okur. CLAUDE.md bu arızayı adıyla yazıyor; buradaki karşılığı
hatırlanması gereken bir kural değil, unutulması imkânsız bir yapı.
"""

import json

from gozcu.agents.action_planner import plan_actions
from gozcu.agents.reporter import generate_root_cause_report
from gozcu.agents.risk import _describe_tool, assess_risk
from gozcu.agents.orchestrator import mmss
from gozcu.guard import screen_text
from gozcu.memory import search_timeline
from gozcu.models import ActionPlan, Correction, DialogueTurn, Episode, Signals
from gozcu.tools.registry import NEEDS_APPROVAL, TOOL_SCHEMAS, call_tool

#: Bir diyalog turunda izin verilen model çağrısı sayısı. Araç turu bitmezse
#: tur `UNFINISHED_REPLY` ile kapanır; sonsuz döngü operatörü bekletirdi.
MAX_TURNS = 4

#: Süpervizörün kendi araçlarının adları. Tek kopya burada: prompt da şema da
#: dağıtım da bu sabitleri okuyor, dolayısıyla üçü ayrışamaz.
SEARCH_TIMELINE = "search_timeline"
CORRECT_OBSERVATION = "correct_observation"
REQUEST_RISK_ASSESSMENT = "request_risk_assessment"
GENERATE_ROOT_CAUSE_REPORT = "generate_root_cause_report"

SUPERVISOR_TOOLS = [
    {"type": "function", "function": {
        "name": SEARCH_TIMELINE,
        "description": "Geçmiş olay arşivinde anlamsal arama yapar.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": CORRECT_OBSERVATION,
        "description": "Operatörün düzeltmesini kalıcı olarak kaydeder ve "
                       "olay özetiyle risk analizine yayar.",
        "parameters": {"type": "object", "properties": {
            "episode_id": {"type": "integer"}, "field": {"type": "string"},
            "old": {"type": "string"}, "new": {"type": "string"},
            "rationale": {"type": "string"}},
            "required": ["episode_id", "field", "old", "new", "rationale"]}}},
    {"type": "function", "function": {
        "name": REQUEST_RISK_ASSESSMENT,
        "description": "Bir olay için iş güvenliği risk analizi ister.",
        "parameters": {"type": "object",
                       "properties": {"episode_id": {"type": "integer"}},
                       "required": ["episode_id"]}}},
    {"type": "function", "function": {
        "name": GENERATE_ROOT_CAUSE_REPORT,
        "description": "Kapanan olay için kök neden raporu üretir.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

#: Modele sunulan şemaların tamamı — yedi saha aracı ve süpervizörün dördü.
ALL_TOOL_SCHEMAS = [*TOOL_SCHEMAS, *SUPERVISOR_TOOLS]

#: Promptun araç kataloğu, **şemalardan** üretiliyor. `gozcu.agents.risk`'in
#: aynı yardımcısı kullanılıyor: ikinci bir kopya iki ayrı yöne kayabilirdi.
TOOL_CATALOGUE = "\n".join(_describe_tool(s) for s in ALL_TOOL_SCHEMAS)

_SYSTEM_TEMPLATE = """Sen bir savunma sanayi üretim tesisinin kontrol odasında görevli
vardiya amirisin. Operatörle Türkçe konuşuyorsun.

Nasıl davranırsın:
- Kritik bir olay gördüğünde SORULMADAN önce sen haber verirsin
- **ÖNCE ARAÇLARI ÇAĞIRIRSIN, SONRA konuşursun.** Kritik bir olayda ilk
  turda en az bir saha aracı çağırman gerekir — `dispatch_medical`,
  `radio_call`, `site_alarm`, `open_safety_incident`. Bunlar mock saha
  sistemleri; çağırmak kimseyi riske atmaz, çağırMAmak müdahaleyi geciktirir
- Belirsizlik aracı çağırmana ENGEL DEĞİL: önce çağırır, sonra sorarsın.
  "Emin olmadığım için beklemedim" yanlış; hayat kurtaran aksiyon önce gider
- Konuşmadan önce gerekli sorguları yaparsın (vardiya, ekipman geçmişi)
- Kameradan göremediğin bir şeyi UYDURMAZSIN — ama bu, aracı çağırmayı
  değil, GÖRMEDİĞİNİ ANLATMAYI yasaklar
- Operatör seni düzeltirse {correction_tool} aracını çağırırsın
- Operatör konuyu değiştirirse cevaplarsın ama AÇIK OLAYI **BİR KEZ**
  hatırlatırsın — her turda değil
- **Operatör bir olayı açıkça geçiştirdiyse ("sorun yok", "kontrol ettim",
  "devam et") KABUL EDERSİN:** {correction_tool} ile kaydeder, kararı
  operatöre yazar ve KONUYU BIRAKIRSIN. Kaydı silmezsin ama tartışmayı
  sürdürmezsin
- **Aynı onayı iki defadan fazla isteme.** İkinci reddin ardından kararı
  deftere yazıp susarsın; üçüncü kez sormak operatörü kilitler
- Kısa cümleler kurarsın. Saha terminolojisi kullanırsın.

Çağırabileceğin araçlar — araç adını ve parametre değerlerini burada yazdığı
gibi, birebir kullan:
{tools}

Var olmayan bir araç adı UYDURMA.

Zaman damgalarını MM:SS biçiminde yazarsın."""

SYSTEM_PROMPT = _SYSTEM_TEMPLATE.format(
    correction_tool=CORRECT_OBSERVATION,
    tools=TOOL_CATALOGUE)

#: `escalate()`'in modele verdiği talimat. Eskiden "Operatöre kendin haber
#: ver. Belirsizlik varsa sor." diyordu ve sistem promptundaki eylem kuralını
#: EZİYORDU: yükseltme mesajı son sözü söylüyor ve son söz "sor"du. Ölçülen
#: sonuç 7 yükseltme / 0 araç çağrısıydı.
#:
#: 26 Ağustos kararı (spec §2) sonrası saha araçları artık her çağrıda
#: başarıyor, yani `zone_unresolved` paragrafı ölü koda döndü ve silindi —
#: geriye kalan tek okuma kuralı `refused`/`duplicate` (yineleme kısa devresi,
#: bkz. `registry._incident_guard`) için.
ESCALATION_INSTRUCTION = (
    "ÖNCE gerekli saha araçlarını çağır (sağlık, telsiz, alarm, İSG kaydı), "
    "SONRA operatöre ne yaptığını tek paragrafta anlat ve eksik bilgi varsa "
    "en fazla iki soru sor. "
    "ARAÇ SONUCUNU OKU: yalnızca gerçekten başarılı olan çağrıları rapor "
    "et; `refused` ya da `duplicate` dönen bir çağrıyı yapılmış gibi "
    "anlatma.")

#: Aynı açık olayın SONRAKİ yükseltmelerinin talimatı. İlk yükseltme tam
#: müdahaledir; 26 Ağustos koşusunda aynı olay 6 kez yükseltilip 18 saha
#: çağrısı üretti — ESCALATION_INSTRUCTION her seferinde "önce araçları
#: çağır" diye emrettiği için. Gelişme kipi operatörü bilgilendirir,
#: ambulansı yeniden çağırmaz (spec §3).
UPDATE_INSTRUCTION = (
    "Bu olay için saha araçları ZATEN çağrıldı ve aksiyon defterinde "
    "duruyor; aynı aracı aynı gerekçeyle TEKRAR ÇAĞIRMA. Gelişmeyi 1-2 "
    "cümleyle operatöre bildir. Yalnız YENİ doğan bir ihtiyaç için yeni "
    "araç çağırabilirsin. ARAÇ SONUCUNU OKU: yalnızca gerçekten başarılı "
    "olan çağrıları rapor et.")

#: Planın yükseltme mesajındaki satırı — yalnız İLK yükseltmede. Nöbetçi
#: araç kataloğunu zaten görüyor; bu satır ona hangi prosedürün geçerli
#: olduğunu söylüyor ki seçimi kendi sezgisi değil tesisin kuralı belirlesin.
PLAN_LINE = ("Geçerli prosedür: {protocol}. Önerilen müdahale: {actions}. "
             "Bu öneriyi operatöre sun ve onay iste.")
NO_PLAN_LINE = ("Bu olay için tanımlı bir prosedür yok; müdahaleyi kendi "
                "değerlendirmenle öner.")

#: `PLAN_LINE`'ın GÜNCELLEME kipindeki karşılığı — İKİZİ değil, kasıtlı
#: biçimde imperatifsiz. `PLAN_LINE`'ın "bu öneriyi sun ve onay iste" emri
#: güncellemede `UPDATE_INSTRUCTION`'ın hemen üstünde duruyordu ve o
#: talimatın "aynı aracı aynı gerekçeyle TEKRAR ÇAĞIRMA" cümlesiyle doğrudan
#: çelişiyordu — modele aynı anda hem "öner" hem "çağırma" deniyordu. Bu tam
#: olarak 26 Ağustos'un "yükseltme fırtınası" arızasının sınıfı: aynı olay 6
#: kez yükseltilip 18 saha çağrısı üretmişti. Güncelleme satırı bu yüzden
#: yalnız OLGUSAL bir hatırlatma — hangi prosedür zaten uygulandı — hiçbir
#: fiil operatöre sunmayı ya da onay istemeyi emretmiyor (controller ruling 8).
UPDATE_PLAN_LINE = "Daha önce önerilen prosedür: {protocol}. Önerilen müdahale: {actions}."


def plan_line(plan: ActionPlan | None, update: bool = False) -> str:
    """Planı tek satırlık talimata (ilk yükseltme) ya da olgusal bir
    hatırlatmaya (güncelleme) çevirir.

    Güncelleme kipinde uygulanacak/hatırlatılacak somut bir şey yoksa
    (`plan` yok ya da öneri listesi boş) satır tamamen düşer — boş bir
    "prosedür yok" imperatifi güncelleme kipinde de aynı çelişkiyi üretirdi.
    """
    if plan is None or not plan.proposed_actions:
        return "" if update else NO_PLAN_LINE
    action_parts = []
    for a in plan.proposed_actions:
        params_str = ", ".join(f"{k}={v!r}" for k, v in a.params.items())
        call = f"{a.tool_name}({params_str})" if params_str else a.tool_name
        action_parts.append(f"{a.description_tr} [{call}]")
    actions = " · ".join(action_parts)
    template = UPDATE_PLAN_LINE if update else PLAN_LINE
    return template.format(protocol=plan.protocol_id or "(kayıtsız)",
                           actions=actions)


# Arıza metinleri. Üçü bilerek farklı: operatör de kök neden raporunu okuyan
# kişi de "kademe sustu", "kademe boş yanıt döndü" ve "araç turu sonuçlanmadı"
# ayrımını görebilmeli — üçü farklı arızalar ve farklı müdahale gerektiriyor.
# Aynı metni paylaşsalardı `degraded` dalı sessizce ölü koda dönerdi.
DEGRADED_REPLY = ("Diyalog katmanı yanıt vermiyor. Olay kaydı ve aksiyon "
                  "defteri korunuyor; ekranınızdaki son duruma göre "
                  "ilerleyin.")
#: Sentez kademesi arıza metni döndürdüğünde olay tarifinin YERİNE geçen not.
#:
#: Arıza metni ("Sentez katmanı boş yanıt döndürdü") prompt'a olay tarifi
#: olarak girdiğinde model onu fabrikada olmuş bir şey sandı, var olmayan bir
#: bölge adı uydurdu ("Sentez Hattı"), oraya alarm çaldırdı, telsizle operatör
#: aradı ve sağlık ekibi çağırdı — hiçbiri yaşanmamıştı (26 Ağu canlı koşu).
#:
#: Bu ilk düzeltme yetmedi: yerine konan "Sentez kademesi bu pencere için bir
#: olay tarifi ÜRETEMEDİ" notu da aynı gün, aynı koşuda ikinci kez patladı —
#: model "Sentez kademesi"ni bir bölge sandı ve `dispatch_medical`,
#: `site_alarm`, `radio_call` çağrılarına konum/bölge parametresi olarak
#: geçirdi; teslim edilen `summary` de aynı uydurma adı taşıdı (14 tekrar,
#: var olmayan bir bölge). Not artık hiçbir iç katman adı taşımıyor ve
#: kendi içindeki hiçbir kelimenin bölge/hat/ekipman adı OLMADIĞINI açıkça
#: söylüyor.
#:
#: Yükseltme İPTAL EDİLMİYOR: yönlendiricinin sinyallere dayanan kararı hâlâ
#: gerçek bir bilgi. Değişen tek şey, modele elinde ne OLMADIĞININ
#: söylenmesi — ve olmayan bir şeyi uydurmasının yasaklanması.
NO_DESCRIPTION_NOTE = (
    "Bu pencere için bir olay tarifi ÜRETİLEMEDİ. Ne olduğunu BİLMİYORSUN. "
    "Aşağıdaki sinyaller dışında hiçbir şey varsayma: bölge adı, ekipman "
    "adı, olay türü ya da hasar UYDURMA. Bu notun kendisinde geçen hiçbir "
    "kelime bir bölge, hat ya da ekipman adı DEĞİLDİR — hiçbirini bir araç "
    "çağrısında parametre değeri olarak KULLANMA. Bölge adı gerektiren bir "
    "aracı, bölgeyi gerçekten bilmiyorsan ÇAĞIRMA. Operatöre ne gördüğünü "
    "değil, görüntüyü okuyamadığını söyle ve ne yapmasını istediğini sor.")

#: Açık olay yedek özetliyse `talk()`'un her turda tekrarladığı hatırlatmada
#: özetin YERİNE geçen metin. Arıza metni olay tarifi değildir; hatırlatma
#: yine de olayın kimliğini (`episode {id}`) taşır — kaybolan yalnız uydurma
#: tarif olmalı (spec §1, bkz. `NO_DESCRIPTION_NOTE`).
#:
#: "sentez" sözcüğü kasıtlı olarak burada da yok: `NO_DESCRIPTION_NOTE`'un
#: yaşadığı aynı sızıntı sınıfı (bkz. yukarısı).
FALLBACK_REMINDER = "(tarif üretilemedi — iç arıza)"

EMPTY_REPLY = ("Diyalog katmanı boş yanıt döndürdü. Olay kaydı ve aksiyon "
               "defteri korunuyor; sorunuzu tekrar iletin.")
UNFINISHED_REPLY = ("Yanıt üretilemedi: araç turu sonuçlanmadı. Olay kaydı ve "
                    "aksiyon defteri korunuyor.")

#: Denetim hükmünün diyalog dökümüne düştüğü satırın başı. Kök neden raporunun
#: DİYALOG bölümünde bu satırlar operatör konuşmasından ayırt edilebilmeli.
AUDIT_PREFIX = "[denetim]"

#: Modele söylenen ret gerekçesi — ikinci kapılı aksiyon denemesi.
SECOND_GATE_REFUSAL = ("Onay bekleyen bir aksiyon varken yeni bir onaylı "
                       "aksiyon başlatılamaz. Operatörden bekleyen aksiyon "
                       "için karar iste.")

#: Operatöre giden bildirim: neyin beklediğini adıyla söyler. Model
#: cevabından bağımsız olarak eklenir — bekleyen onayın duyurulması bir
#: prompt umuduna bırakılamaz.
PENDING_GATE_NOTICE = (
    "[SİSTEM] Onayınızı bekleyen bir aksiyon zaten var: {tool} — {params}. "
    "Aynı anda yalnız bir aksiyon onay bekleyebilir, bu yüzden yeni bir "
    "aksiyon başlatmadım. Önce bekleyen aksiyonu onaylayın ya da reddedin.")


def uncertainty_note(signals: Signals) -> str:
    """Kameranın göremediğini açıkça adlandırır.

    Beat 2 buna dayanıyor: 'yerdeki kişi hareket ediyor mu, göremiyorum'
    sorusunu prompt umuduna bırakmak yerine, sinyallerden türetilmiş gerçek
    bir belirsizlik notuyla güvenilir şekilde tetikliyoruz.

    Boş `velocities` bir eksiklik değil, bir **bilgi**: `compute_signals` hızı
    yalnız iki kare arasında eşleşen track'ler için üretiyor, yani sözlük
    boşken kadrajdaki kişinin hareket edip etmediği ölçülmemiştir. O hâlde
    not doludur; sessiz kalmak belirsizliği yutmak olurdu.
    """
    notes = []
    if signals.vanished_tracks:
        notes.append("bazı nesneler kadraj dışına çıktı, durumlarını "
                     "göremiyorum")
    if signals.person_count and not signals.velocities:
        notes.append("yerdeki kişinin hareket edip etmediğini bu açıdan "
                     "göremiyorum")
    return ("BELİRSİZLİK: " + "; ".join(notes)) if notes else ""


class Supervisor:
    """Operatörle konuşan ajan; araçları defter üzerinden çağırır."""

    def __init__(self, gw, store, source: str | None = None) -> None:
        self.gw, self.store = gw, store
        #: Bu koşunun videosunun kimliği — precedent_line aramasında kendi
        #: epizotlarını dışlayabilmek için. `None` doğrudan çağıranlar için.
        self.source = source
        # Araç çağrılarının ve diyalog satırlarının deftere yazılacağı VİDEO
        # zamanı; `escalate()` onu açık epizottan alıyor. Duvar saati değil:
        # `00:00` damgalı bir defter kök neden raporunda yalan söyler.
        self.ts: float = 0.0
        #: Sıradaki cevabın kimse sormadan söylenip söylenmediği.
        #: `escalate()` açıyor, `talk()` kapatıyor ve `_reply` deftere
        #: yazıyor. Komşuluktan TÜRETİLMİYOR: `talk()` operatör satırını
        #: yazdıktan sonra saniyelerce modelde kalıyor ve o boşlukta düşen
        #: bir yükseltme türetmeyi yanlış satıra takıyor.
        self._proactive: bool = False
        self.history: list[dict] = [{"role": "system",
                                     "content": SYSTEM_PROMPT}]
        #: Son denetim hükmü — konsol ve KPI okuyabilsin diye tutuluyor.
        self.last_screening = None
        #: Bu turda operatöre eklenecek sistem bildirimi (bekleyen onay).
        self._notice: str | None = None
        #: Tam müdahalesi yapılmış epizot kimlikleri — spec §3'ün iki kipli
        #: yükseltmesi.
        self._escalated: set[int] = set()

    # -- iç araçlar ---------------------------------------------------------

    def _apply_correction(self, params: dict) -> dict:
        """Düzeltmeyi kaydeder VE yayar: epizot özeti güncellenir, risk
        yeniden koşar. Sadece tabloya yazmak, hiçbir şey yapmamaktır.

        `Correction` `extra="forbid"` ilan ediyor; modelin eklediği tek bir
        fazla anahtar doğrulama hatasıyla bütün turu düşürürdü. Hata modele
        okunur biçimde geri veriliyor ki ikinci denemede düzeltebilsin.
        """
        try:
            correction = Correction(ts=self.ts, **params)
        except Exception as error:  # noqa: BLE001 — bozuk çağrı turu düşürmemeli
            return {"tool_name": CORRECT_OBSERVATION,
                    "error": f"düzeltme kaydı doğrulanamadı: {error}"}

        self.store.save_correction(correction)
        episode = self._episode(correction.episode_id)
        if episode is None:
            return {"state": "recorded",
                    "warning": f"epizot bulunamadı: {correction.episode_id}"}

        new_summary = episode.summary_tr.replace(correction.old,
                                                 correction.new)
        if new_summary == episode.summary_tr:
            new_summary = (f"{episode.summary_tr} "
                           f"(operatör düzeltmesi: {correction.new})")
        # `origin="supervisor"`: bu satırı operatörün sözü değiştirdi, model
        # değil. Defter ikisini ayırmazsa besleme insan müdahalesini model
        # çıktısı gibi gösterir — %20'lik otonomi kriteri tam olarak bunu
        # soruyor.
        self.store.update_episode(episode.id, summary_tr=new_summary[:600],
                                  origin="supervisor")

        refreshed = self._episode(episode.id)
        risk = assess_risk(self.gw, self.store, refreshed)
        plan_actions(self.gw, self.store, refreshed, risk)
        return {"state": "recorded", "new_summary": refreshed.summary_tr,
                "new_risk": risk.level}

    def _episode(self, episode_id) -> Episode | None:
        return next((e for e in self.store.episodes() if e.id == episode_id),
                    None)

    def _latest_risk(self, episode: Episode):
        """Epizodun depodaki SON değerlendirmesi; yoksa None."""
        rows = [r for r in self.store.risks() if r.episode_id == episode.id]
        return rows[-1] if rows else None

    def _latest_plan(self, episode: Episode):
        """Epizodun depodaki SON planı; yoksa None."""
        rows = [p for p in self.store.action_plans()
                if p.episode_id == episode.id]
        return rows[-1] if rows else None

    def _internal_tool(self, name: str, params: dict):
        """Süpervizörün kendi araçları; saha aracıysa `None` döner."""
        if name == SEARCH_TIMELINE:
            # Kendi koşusunun AÇIK epizodu emsal değil: operatör "bu araçla
            # daha önce sorun oldu mu?" diye sorduğunda ŞU ANKİ olayın
            # kendisini geri almamalı. `self.source` tam olarak bunun için
            # taşınıyor — dışlanmazsa alan ölü kalırdı.
            open_ep = self.store.open_episode()
            exclude = ((self.source, open_ep.id)
                       if open_ep is not None and open_ep.id is not None
                       else None)
            found = search_timeline(self.gw, self.store, params["query"],
                                    exclude=exclude)
            # Tam `model_dump()` DEĞİL: `Episode` artık `beats` ve
            # `actions_taken` da taşıyor ve o yük doğrudan `self.history`'ye
            # girip her turda yeniden gönderilirdi — geçmiş budamasıyla ters
            # yönde. `participants` projeksiyonda KALIYOR: arşiv kayıtlarında
            # ekipman kimliğini bugün gerçekten taşıyan alan o
            # (`["IST-04", "PRS-001"]`).
            return {"results": [{"summary_tr": p.episode.summary_tr,
                                 "occurred_at": p.episode.occurred_at,
                                 "source": p.episode.source,
                                 "equipment_ids": p.episode.equipment_ids,
                                 "participants": p.episode.participants,
                                 "actions_taken": p.episode.actions_taken,
                                 "score": round(p.score, 3)}
                                for p in found]}
        if name == CORRECT_OBSERVATION:
            return self._apply_correction(params)
        if name == REQUEST_RISK_ASSESSMENT:
            episode = self._episode(params.get("episode_id"))
            if episode is None:
                return {"tool_name": REQUEST_RISK_ASSESSMENT,
                        "error": f"epizot bulunamadı: "
                                 f"{params.get('episode_id')}"}
            assessment = assess_risk(self.gw, self.store, episode)
            plan = plan_actions(self.gw, self.store, episode, assessment)
            return {**assessment.model_dump(),
                    "plan": plan.model_dump()}
        if name == GENERATE_ROOT_CAUSE_REPORT:
            return generate_root_cause_report(self.gw, self.store).model_dump()
        return None

    def _refuse_second_gate(self, name: str) -> dict | None:
        """Onay bekleyen bir aksiyon varken ikinci kapılı aksiyonu reddeder.

        Ret **yürütmeden önce** veriliyor: `call_tool`'a girseydi defterde
        ikinci bir `"pending"` satır doğar ve birincisi kalıcı olarak
        görünmez olurdu. Reddedilen çağrı deftere hiç düşmüyor — olmamış bir
        aksiyon defterde görünmemeli.
        """
        pending = self.pending_approval()
        if pending is None:
            return None
        params = json.dumps(pending.params, ensure_ascii=False, default=str)
        self._notice = self._notice or PENDING_GATE_NOTICE.format(
            tool=pending.tool_name, params=params)
        return {"tool_name": name, "refused": True,
                "reason": SECOND_GATE_REFUSAL,
                "pending_action_id": pending.id,
                "pending_tool": pending.tool_name}

    def _run_tool(self, call: dict) -> dict:
        """Tek bir araç çağrısını çalıştırır; her arıza okunur bir sonuç."""
        function = call.get("function") or {}
        name = function.get("name")
        try:
            params = json.loads(function.get("arguments") or "{}")
        except (ValueError, TypeError):
            return {"tool_name": name, "error": "araç parametreleri okunamadı"}
        if not isinstance(params, dict):
            return {"tool_name": name, "error": "araç parametreleri okunamadı"}

        try:
            internal = self._internal_tool(name, params)
        except Exception as error:  # noqa: BLE001 — bozuk çağrı turu düşürmemeli
            return {"tool_name": name,
                    "error": f"araç çalıştırılamadı: {error}"}
        if internal is not None:
            return internal

        if name in NEEDS_APPROVAL:
            refused = self._refuse_second_gate(name)
            if refused is not None:
                return refused

        try:
            return call_tool(self.store, name, params, actor="agent",
                             ts=self.ts)
        except KeyError:
            return {"tool_name": name, "error": f"bilinmeyen araç: {name}"}
        except Exception as error:  # noqa: BLE001 — bozuk argüman turu düşürmemeli
            return {"tool_name": name,
                    "error": f"araç çalıştırılamadı: {error}"}

    # -- diyalog ------------------------------------------------------------

    def _take_notice(self, text: str) -> str:
        """Bekleyen onay bildirimini cevabın altına ekler ve sıfırlar.

        Bildirim denetimden GEÇMİYOR: bizim yazdığımız sabit bir sistem metni,
        model üretimi değil — denetim katmanı model metnini süzmek için var.
        """
        notice, self._notice = self._notice, None
        return f"{text}\n\n{notice}".strip() if notice else text

    def _reply(self, content: str, critical: bool) -> str:
        """Modelin cevabını denetler, kaydeder ve operatöre döndürür."""
        screening = screen_text(self.gw, content, critical=critical)
        self.last_screening = screening
        text = self._take_notice(screening.text)

        self.history.append({"role": "assistant", "content": text})
        self.store.save_dialogue(DialogueTurn(ts=self.ts, role="supervisor",
                                              text=text,
                                              proactive=self._proactive))
        # Hüküm denetim kaydına düşüyor — ama yalnız söylenecek bir şey
        # varsa. "Temiz" her tura bir satır eklerdi; engellenen, okunamayan ya
        # da hiç uygulanmayan denetimin kaydı ise kanıttır.
        if screening.verdict != "safe":
            self.store.save_dialogue(DialogueTurn(
                ts=self.ts, role="system",
                text=f"{AUDIT_PREFIX} {screening.note}"))
        return text

    def _fault(self, message: str) -> str:
        """Arıza metnini operatöre verir ve deftere yazar.

        Bozulmuş yanıt `content=""` taşıyor; denetime sokup boş metni
        operatöre göndermek yerine tur burada kapanıyor. Metin `system`
        rolüyle kaydediliyor: bunu söyleyen süpervizör değil, sistemdir.
        """
        text = self._take_notice(message)
        self.history.append({"role": "assistant", "content": text})
        self.store.save_dialogue(DialogueTurn(ts=self.ts, role="system",
                                              text=text))
        return text

    def _turn_loop(self, critical: bool) -> str:
        for _ in range(MAX_TURNS):
            response = self.gw.ask("main", self.history,
                                   tools=ALL_TOOL_SCHEMAS)
            if response.degraded:
                return self._fault(DEGRADED_REPLY)

            if not response.tool_calls:
                content = (response.content or "").strip()
                if not content:
                    return self._fault(EMPTY_REPLY)
                return self._reply(content, critical)

            self.history.append({"role": "assistant",
                                 "content": response.content or None,
                                 "tool_calls": response.tool_calls})
            for call in response.tool_calls:
                result = self._run_tool(call)
                self.history.append({
                    "role": "tool", "tool_call_id": call.get("id", "c"),
                    "content": json.dumps(result, ensure_ascii=False,
                                          default=str)})

        return self._fault(UNFINISHED_REPLY)

    def escalate(self, episode: Episode) -> str:
        """Proaktif açılış: kimse sormadan operatöre seslenir.

        Saat olayın BAŞINA değil ŞU ANA kuruluyor. `start_ts` pencerenin
        sınırı ve olay dakikalarca sürebiliyor; ajan olayın başında değil,
        yükseltmenin olduğu anda davranıyor. Eskiden bütün konuşma ve araç
        çağrıları olayın ilk saniyesine damgalanıyordu: 26 Ağustos koşusunda
        01:16'ya kadar süren bir olayın 18 çağrısının hepsi 00:40 yazıyordu
        ve besleme geriye doğru sayıyordu.
        """
        self.ts = episode.end_ts or episode.start_ts
        self._proactive = True
        update = episode.id in self._escalated
        risk = self._latest_risk(episode) if update else None
        if risk is None:
            # İlk yükseltme — ya da (teorik dal) güncellemede depoda hiç
            # değerlendirme yok: tam müdahaleye düşülür.
            update = False
            risk = assess_risk(self.gw, self.store, episode)
            plan = plan_actions(self.gw, self.store, episode, risk)
        else:
            plan = self._latest_plan(episode)
        self._escalated.add(episode.id)
        observations = [o for o in self.store.observations()
                        if episode.start_ts <= o.ts <= (episode.end_ts
                                                        or episode.start_ts)]
        signals = observations[-1].signals if observations else Signals()
        note = uncertainty_note(signals)

        # Arıza metni olay tarifi DEĞİLDİR. `summary_source` bunu yapısal
        # olarak söylüyor; metne bakarak ayırt etmek imkânsız ve bir kez
        # ağır bir uydurmaya yol açtı (bkz. `NO_DESCRIPTION_NOTE`).
        if episode.summary_source == "fallback":
            headline = NO_DESCRIPTION_NOTE
        else:
            headline = f"kritik olay: {episode.summary_tr}."
        # Başlığın saati `self.ts` — yani videonun ŞİMDİ'si — olmalı,
        # `episode.start_ts` değil: sistem promptu modele MM:SS damgalarını
        # YAZMASINI söylüyor ve model burada gördüğü yanlış saati örnek alıp
        # operatöre olayın başlangıcını "şimdi" diye bildirebilirdi. Bu satır
        # eskiden `episode.start_ts` kullanıyordu; uzun süren bir olayda
        # (00:00 açılış, 00:19+ yükseltme) başlık "00:00" derken defterdeki
        # her aksiyon ve diyalog satırı zaten `self.ts` ile 00:19 taşıyordu —
        # aynı yalanın besleme tarafındaki ikizi (bkz. yukarısı: `self.ts`).
        self.history.append({
            "role": "user",
            "content": f"[SİSTEM] {mmss(self.ts)} — {headline} "
                       f"Olay kimliği (episode_id): {episode.id}. "
                       f"Risk: {risk.level}. "
                       f"Gerekçe: {risk.rationale_tr}\n"
                       f"{plan_line(plan, update=update)}\n{note}\n"
                       f"{UPDATE_INSTRUCTION if update else ESCALATION_INSTRUCTION}"})
        return self._turn_loop(critical=risk.level in ("Yüksek", "Kritik"))

    def talk(self, operator_text: str) -> str:
        """Bir diyalog turu. Açık olay her turda hatırlatılıyor."""
        # Operatör sordu: bundan sonraki cevap kendiliğinden DEĞİL.
        self._proactive = False
        open_episode = self.store.open_episode()
        if open_episode:
            # Diyalogdaki çağrılar da videoda — ama olayın BAŞINDA değil,
            # konuşmanın olduğu anda. Açık bir olayın `end_ts`'i son
            # kaynaşan pencerenin sonu, yani videonun "şimdi"si.
            self.ts = open_episode.end_ts or open_episode.start_ts
        self.store.save_dialogue(DialogueTurn(ts=self.ts, role="operator",
                                              text=operator_text))
        summary = (FALLBACK_REMINDER
                   if open_episode and open_episode.summary_source == "fallback"
                   else open_episode.summary_tr if open_episode else "")
        reminder = (f"\n[SİSTEM] Açık olay: episode {open_episode.id} — "
                    f"{summary}" if open_episode else "")
        self.history.append({"role": "user",
                             "content": operator_text + reminder})
        return self._turn_loop(critical=False)

    # -- onaylar ------------------------------------------------------------

    def pending_approval(self):
        """Onay bekleyen tek aksiyon; yoksa `None`.

        `_refuse_second_gate` sayesinde defterde aynı anda en fazla bir
        bekleyen satır olabiliyor. Yine de **en eskisi** döndürülüyor: bir gün
        başka bir yazar ikinci satırı doğurursa, konsolun onay çubuğunun
        üzerine açıldığı satır kaybolmasın.
        """
        pending_rows = [a for a in self.store.actions()
                        if a.approval == "pending"]
        return pending_rows[0] if pending_rows else None

    def approve(self, action_id: int, approved: bool) -> dict:
        """Operatörün kararını uygular.

        Bilinmeyen kimlik çıplak bir `StopIteration` atmıyor, okunur bir sonuç
        dönüyor: bu çağrının kaynağı konsol, yani bir kullanıcı hatası
        yığın izine dönüşmemeli. Kararı verilmiş bir satır da yeniden
        yürütülmüyor — ikinci bir `call_tool` deftere ikinci bir hat durdurma
        yazardı.
        """
        record = next((a for a in self.store.actions() if a.id == action_id),
                      None)
        if record is None:
            return {"state": "unknown_action",
                    "error": f"aksiyon bulunamadı: {action_id}"}
        if record.approval != "pending":
            return {"state": "not_pending", "approval": record.approval,
                    "error": f"aksiyon zaten karara bağlanmış: "
                             f"{record.approval}"}

        if not approved:
            self.store.set_action_approval(action_id, "rejected")
            return {"state": "rejected", "action_id": action_id}

        # `approval` geçilmezse `call_tool` yeni bir "pending" satır doğurur ve
        # onay çubuğu hiç kapanmaz. `ts` orijinal satırdan: onay duvar
        # saatinde geliyor ama aksiyon videonun o anına ait.
        result = call_tool(self.store, record.tool_name, record.params,
                           actor="operator", approval="approved",
                           ts=record.ts)
        self.store.set_action_approval(action_id, "approved")
        # Araç sonucu İÇ İÇE duruyor, düzleştirilmiyor: `halt_production_line`
        # da bir `state` döndürüyor ve düz birleştirmede onun `"halted"`
        # değeri onayın `"approved"`ünü eziyordu — çağıran onayın gerçekten
        # işlendiğini hiçbir zaman göremezdi.
        return {"state": "approved", "action_id": action_id, "result": result}
