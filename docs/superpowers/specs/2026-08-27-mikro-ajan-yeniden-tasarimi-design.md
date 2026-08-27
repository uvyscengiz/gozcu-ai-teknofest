# Mikro-ajan mimarisi — yeniden tasarım (tasarım)

**Kaynak:** `Feraset_Guncel_Ajan_Mimarisi.pdf` (takım içi öneri, 27 Ağustos).
**Plan-of-record:** [2026-08-22-agentic-gozcu-design.md](2026-08-22-agentic-gozcu-design.md).
Bu doküman onu **değiştirmiyor, üzerine yazıyor**: çelişki halinde burası geçerli.

---

## 0. Sorunun özeti

PDF sekiz mikro-ajan sayıyor. Sekizin altısı **zaten kodda var** — farklı
adlarla, ama aynı işi yaparak. Gerçek fark üç yerde:

1. **Karar & Aksiyon ajanı yok.** Bugün risk analisti hem ciddiyeti biçiyor
   hem müdahale öneriyor — tek model çağrısında iki iş.
2. **Adlar tutmuyor.** PDF'in "Orkestratör"ü kodda `router`, "Anomali
   Analiz"i `synthesizer`. Mimari dokümanla trace panelinde aynı olay iki ayrı
   isimle görünüyor.
3. **PDF üç bileşeni saymıyor:** Yorumlayıcı (VLM — piksele bakan tek
   bileşen), Raportör (kök neden raporu, şartname çıktısı) ve Guard. Bunlar
   **eksik sayım, silme talebi değil**; üçü de yerinde kalıyor.

PDF ayrıca Mock (#7), Benchmark (#8) ve Orkestratör'ü (#1) "ajan" diye
adlandırıyor. İlk ikisi bugün deterministik Python — araç kaydı ve KPI modülü.
Bkz. §0b, karar 1.

### PDF'in sekizi ↔ bugünkü kod

| PDF | Bugün | Sonuç |
|---|---|---|
| 1. Yönetici / Orkestratör | [router.py](../../../gozcu/agents/router.py) + [loop.py](../../../gozcu/loop.py) `DecisionLoop` | Var — `orchestrator` diye yeniden adlandırılıyor |
| 2. Uzun Süreli Hafıza | [memory.py](../../../gozcu/memory.py) — Qdrant `team37/episodes` | **Ertelendi** (§6) |
| 3. Anomali Analiz | [synthesizer.py](../../../gozcu/agents/synthesizer.py) | Var — `anomaly_analyst` diye yeniden adlandırılıyor |
| 4. Risk Değerlendirme | [risk.py](../../../gozcu/agents/risk.py) | Var — **daralıyor** (§3) |
| 5. Karar & Aksiyon | — | **YENİ** (§2) |
| 6. Operatör Diyalog | [supervisor.py](../../../gozcu/agents/supervisor.py) — Nöbetçi | Var, adı değişmiyor (§4) |
| 7. Mock / Simülasyon | [tools/](../../../gozcu/tools/) — yedi saha aracı | Ajan değil, **alt sistem** |
| 8. Performans / Benchmark | [benchmark/kpi.py](../../../benchmark/kpi.py) | Ajan değil, **alt sistem** |
| *(PDF'de yok)* | [interpreter.py](../../../gozcu/agents/interpreter.py) | Ajan, kalıyor |
| *(PDF'de yok)* | [reporter.py](../../../gozcu/agents/reporter.py) | Ajan, kalıyor |
| *(PDF'de yok)* | [guard.py](../../../gozcu/guard.py) | Süzgeç, kalıyor |

---

## 0b. Ürün sahibi kararları (27 Ağustos)

1. **"Ajan" = model çalıştıran aktör.** Mock ve Benchmark ajan *değil*; mimari
   şemada alt sistem olarak çizilirler. Sekiz ajan yerine altı ajan + iki alt
   sistem — jüri "araç kaydını neden ajan sayıyorsunuz?" diye sorduğunda
   savunulabilir olan bu.
2. **"Tamamen yerel (offline)" ifadesi düzeltiliyor.** Kastedilen: modeller
   **kendi kendine servis edilebilir açık ağırlıklı** modeller, EVREN de bunu
   yarışma adına barındırıyor. Sistem çevrimdışı değil — ağ giderse durur.
   Doküman bu cümleyi böyle yazacak; kodda karşılığı yok.
3. **Karar & Aksiyon ajanı A2 kapsamında:** protokol seçici (§2).
4. **Yeniden adlandırma kodda yapılıyor**, görüntü katmanında değil:
   `router → orchestrator`, `synthesizer → anomaly_analyst`.
5. **Hız sonra.** Yeni ajan kritik anın tam ortasına bir model çağrısı daha
   koyuyor; bu bilinerek kabul edildi (§8, R1).

---

## 1. Ajan kadrosu

**Ajanlar (model çalıştırır):**

```
perception ─▶ orchestrator ─▶ interpreter ─▶ anomaly_analyst ─▶ risk_analyst
   (alt sistem)                                                      │
                                                                     ▼
        operatör ◀── supervisor (Nöbetçi) ◀────────────── action_planner
                          │
                          ▼
                  saha araçları (alt sistem)   ·   reporter   ·   memory (ertelendi)
```

`guard` zincirin bir durağı değil, operatöre giden metni saran süzgeç.

**Alt sistemler (deterministik):** algı hattı, saha araçları (yedi mock
sistem), benchmark/KPI. Şemada ajan kutusu değil, silindir çizilir.

`AgentName` yeni hâli:

```python
AgentName = Literal["perception", "orchestrator", "interpreter",
                    "anomaly_analyst", "risk_analyst", "action_planner",
                    "supervisor", "reporter"]
```

---

## 2. Karar & Aksiyon ajanı (`action_planner`) — YENİ

**İşlev:** Riski biçilmiş bir epizoda karşı **tesisin yazılı prosedürüne
dayanan** müdahale planı üretir. Kendisi saha sistemini tetiklemez; planı
Nöbetçi'ye verir, operatör onayı hâlâ tek kapıdır.

### 2a. Neden protokol seçici (A2), saf öneri (A1) değil

Saf öneri, ekstra bir model çağrısını yalnızca bir JSON alanını bir
nesneden diğerine taşımak için harcar. Protokole bağlamak iki şey kazandırır:

- **`preventable` gerçek bir iddiaya dönüşür.** "Önlenebilirdi" bugün modelin
  kanaati; protokolle "PRT-B-SIKISMA prosedürü vardı ve uygulanmadı" olur.
  Kök neden raporunun asıl cümlesi budur.
- **Deterministik yedek doğar.** Model susarsa eşleşen protokolün adımları
  **birebir** plana yazılır. Bugün risk analisti düşerse `actions` boş kalır;
  bundan sonra kalmaz.

### 2b. Önkoşul: epizot olay sınıfı ve bölge taşımalı

Protokolü deterministik süzmek için epizotta süzülecek bir alan gerekiyor —
bugün **yok**. `Episode`'da `summary_tr` var, `participants` var, ama olayın
*ne olduğu* yalnız serbest metinde; bölge ise hiç yok. Bugün
`dispatch_medical(location=...)` çağrısındaki bölge adını model serbest metin
olarak uyduruyor ve `resolve_zone` onu aracın içinde çözmeye çalışıyor.

`anomaly_analyst` iki tipli alan daha üretir:

```python
EventClass = Literal["sıkışma", "düşme", "çarpma", "yangın",
                     "kimyasal sızıntı", "ekipman arızası",
                     "yetkisiz giriş", "rutin", "diğer"]

class Episode(Base):
    ...
    event_class: EventClass = "diğer"
    zone_id: str | None = None          # facility.json'daki zone_id, birebir
```

Bu, yeniden adlandırmanın kozmetik olmadığı yer: PDF #3'ün *"rutin akış ile
kaza/tehlike anlarını birbirinden ayırır"* cümlesi, `event_class` ile serbest
metinden çıkıp tipli bir alana dönüşüyor — `"rutin"` de geçerli bir değer,
yani ajan "burada bir şey yok" diyebiliyor.

İki yan kazanç: saha aracı parametreleri artık uydurulmuş bölge adı yerine
gerçek `zone_id`'ye dayanıyor, ve `bench/` ölçümü olay sınıfına göre
kırılabiliyor.

**Prompt/şema kuralı burada da geçerli** (CLAUDE.md): `EventClass` değerleri
sentez prompt'unda birebir sayılır. Model listede olmayan bir sınıf
döndürürse `"diğer"`e düşürülür — uydurma sınıf hiçbir protokolle eşleşmez ve
sessizce boş plana yol açardı.

### 2c. Yeni fixture: `gozcu/fixtures/protocols.json`

Mevcut fixture dünyası zengin — bölgede `medical_team` ve
`medical_eta_minutes`, ekipmanda bakım gecikmesi ve açık arıza kaydı,
personelde sertifika, üç geçmiş olay — ama **prosedür yok**. Eklenen:

```python
class ProtocolStep(Base):
    order: int
    description_tr: str
    tool_name: str                      # TOOLS içinden, birebir
    params: dict = Field(default_factory=dict)

class Protocol(Base):
    protocol_id: str                    # "PRT-B-SIKISMA"
    title_tr: str
    event_class: EventClass             # §2b'deki enum, birebir
    zone_ids: list[str] = []            # boş = tüm tesis
    min_risk: RiskLevel                 # bu seviyeden itibaren geçerli
    steps: list[ProtocolStep]
```

Kapsam: senaryonun geçtiği olay sınıflarını örten **dört ila altı protokol**.
Eksiksiz bir İSG el kitabı yazılmıyor; demo anlarını ve kök neden raporunu
besleyecek kadarı yazılıyor.

### 2d. Sözleşme

```python
class ActionPlan(Base):
    id: int | None = None
    ts: float                           # videonun saati, duvarın değil
    episode_id: int
    risk_assessment_id: int
    protocol_id: str | None             # None = eşleşen protokol yok
    rationale_tr: str = Field(max_length=800)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    plan_source: Literal["model", "protocol_fallback", "empty"] = "model"
```

Yeni tablo: `action_plan`. Defterleniyor (journal), çünkü bir ajan sınırını
geçiyor.

**Neden `RiskAssessment.proposed_actions` içinde kalmıyor:** spec'in kendi
kuralı — *"hiçbir şey bir ajan sınırını serbest metin olarak geçmez; her
devir tipli bir kayıttır."* Bir ajanın başka bir ajanın kaydına yazması,
tipler tutsa bile bu kuralı ruhen bozar ve trace panelinde iki ajanın işi tek
satırda görünür.

### 2e. Giriş — ajan ne görür

- Epizot (özet, katılımcılar, `beats`, faz)
- Risk değerlendirmesi (seviye, gerekçe, `preventable`)
- **Aday protokoller:** `event_class` + `zone_id` + `min_risk` ile deterministik
  olarak süzülüp prompt'a yazılır. Model protokol *uydurmaz*, verilenler
  arasından seçer — ya da hiçbiri uymuyorsa `protocol_id: null` der.
- İki salt-okunur araç: `query_shift_personnel`, `query_equipment_history`.
  Parametreleri (kim nöbette, ekipman kimliği) plandan önce doldurmak için.

**Yazma araçları bu ajana kapalı.** `dispatch_medical`,
`halt_production_line`, `site_alarm`, `radio_call`, `open_safety_incident`
yalnızca Nöbetçi'nin onay kapısından geçer. A3 (düşük riskte özerk yürütme)
bilerek reddedildi — bkz. §6.

### 2f. Yedekler

| Durum | Sonuç |
|---|---|
| Model geçerli JSON döndürmedi | Eşleşen protokolün `steps`'i birebir plana yazılır, `plan_source="protocol_fallback"` |
| Eşleşen protokol de yok | Boş plan, `plan_source="empty"`, `rationale_tr` sebebi söyler |
| Model var olmayan `tool_name` uydurdu | O aksiyon düşürülür (bugünkü `risk.py:360` deseni) |

Çıktı sözleşmesinin `actions` anahtarı bundan sonra `ActionPlan` satırlarından
türüyor. **Dört anahtar her hâlükârda üretilir** — `plan_source="empty"` bile
`actions: []` demektir, eksik anahtar değil.

---

## 3. Risk analisti daralıyor

`assess_risk` artık **yalnız derecelendirir**:

```python
class RiskAssessment(Base):
    id: int | None = None
    episode_id: int
    ts: float = 0.0
    level: RiskLevel                    # "Düşük" | "Orta" | "Yüksek" | "Kritik"
    rationale_tr: str = Field(max_length=800)
    preventable: bool
    # proposed_actions KALDIRILDI → ActionPlan
```

Soruşturma araçlarını (`query_*`) çağırma yetkisi **kalıyor** — ciddiyeti
biçmek için bakım gecikmesini bilmek gerekiyor.

`risk.py`'nin prompt'undan araç listesi ve "her aksiyonu bir araca bağla"
bölümü çıkar. Şema küçüldüğü için çıktı da kısalır; bu, §8/R1'deki gecikme
artışının bir kısmını geri verir.

**Prompt/şema eşleşmesi:** `RiskLevel` enum değerleri prompt'ta birebir
tekrarlanıyor. Bunlar bir kez ayrıştı ve sistem sessizce öldü (CLAUDE.md).
Daraltma sırasında dokunulmayacak tek yer burası.

---

## 4. Yeniden adlandırma

| Eski | Yeni | Gerekçe |
|---|---|---|
| `router` | `orchestrator` | PDF #1. Rol zaten "hangi ajan ne zaman koşar" |
| `synthesizer` | `anomaly_analyst` | PDF #3. Yalnız ad değil: §2b ile `event_class` + `zone_id` üretmeye başlıyor, yani "rutin akış ile kaza anını ayırma" tipli bir çıktıya dönüşüyor |
| `supervisor` | *(değişmiyor)* | PDF #6 "Diyalog" diyor, ama Nöbetçi diyalogdan fazlasını yapıyor: araç çağırır, yükseltir, düzeltme uygular. `dialogue_agent` adı işi küçültürdü. **Ürün sahibi burayı ezerse ~100 test referansı ile birlikte döner.** |
| `risk_analyst`, `interpreter`, `reporter`, `perception` | *(değişmiyor)* | Ad zaten işi anlatıyor |

### Dokunulan yerler

Ajan adları üç yerde daha elle yazılı:

- [ui/web/js/trace.js:48](../../../gozcu/ui/web/js/trace.js) — `CHAIN_STAGES`
  (yeni durak `action_planner` da buraya)
- [ui/feed.py:58](../../../gozcu/ui/feed.py) — emoji eşlemesi
- [ui/view.py:345](../../../gozcu/ui/view.py) — kova etiketleri
- `ui/web/css/styles.css` — `[data-bucket="to_synthesizer"]` seçicileri

### Göç gerekmiyor

`Store()` varsayılanı `:memory:` ve üç kurucu yerin (
[run.py:352](../../../gozcu/run.py), [ui/session.py:58](../../../gozcu/ui/session.py),
[ui/server.py:479](../../../gozcu/ui/server.py)) üçü de varsayılanı kullanıyor.
Diskte ajan adı taşıyan bir SQLite dosyası **yok**.

### KPI temeli korunuyor

[benchmark/kpi.py:60](../../../benchmark/kpi.py) `_BUCKET_BY_TARGET` sözlüğü
ajan adını kova adından zaten ayırıyor. Yalnız sözlüğün **anahtarları**
değişir; `closed_at_router` ve `to_synthesizer` kova adları **aynı kalır**, ki
`bench/kpi.json` içindeki ölçüm temeli karşılaştırılabilir kalsın. Kova adı
ile ajan adının ayrışması `benchmark/kpi.py` başına bir yorumla kayda geçer.

---

## 5. Devir zinciri ve arayüz

Yeni devir: `risk_analyst → action_planner → supervisor`.

`Handoff` kaydı değişmiyor (`source_agent`, `target_agent`, `reason`,
`confidence`, `payload_ref`) — yalnız iki yeni ad geçerli değer oluyor.

`Detail` genişliyor:

```python
class Detail(Base):
    episodes: list[Episode] = []
    risk_assessments: list[RiskAssessment] = []
    action_plans: list[ActionPlan] = []          # YENİ
    handoff_chain: list[Handoff] = []
    action_ledger: list[ActionRecord] = []
    root_cause_report: dict | None = None
```

Trace paneli yeni durağı gösterir; müdahale kartı planın `protocol_id`'sini ve
başlığını yazar — *"PRT-B-SIKISMA · B-Hattı sıkışma prosedürü"*. Operatörün
ekranda gördüğü şey artık modelin fikri değil, tesisin kuralı.

---

## 6. Kapsam dışı (bilinçli)

- **Uzun Süreli Hafıza ajanı (PDF #2).** `memory.py` başka bir oturumda
  yeniden yazılıyor. O iş indikten sonra ayrı bir turda ele alınacak. PDF'in
  örneği (*"askerlerin eve girmesinden 15 dk sonra patlama"*) hem alan dışı —
  3. senaryo fabrika — hem de bugünkü `search_timeline`'ın yapmadığı bir
  **nedensel çıkarım** adımı istiyor. İkisi de o turun konusu.
- **Mock ve Benchmark'ın ajanlaştırılması.** §0b/1.
- **A3 — düşük riskte özerk yürütme.** Onay kapısı sistemin en okunur
  parçası; kolay vakalar için atlatmak, jürinin göremeyeceği bir özerklik
  iddiası karşılığında demoyu kontrolsüzleştirir.
- **`supervisor` yeniden adlandırması.** §4.
- **vLLM'e geçiş.** §0b/2 — sorun ifadedeydi, servis katmanında değil.
- **Gecikme optimizasyonu.** §8/R1 ölçülür, bu turda çözülmez.

---

## 7. Test stratejisi (TDD — önce kırmızı)

| # | Test | Kırmızı olmalı çünkü |
|---|---|---|
| 1 | `RiskAssessment` artık `proposed_actions` kabul etmiyor | Alan hâlâ var |
| 2 | `assess_risk` prompt'unda araç listesi geçmiyor | Geçiyor |
| 2b | `synthesize` epizoda `event_class` ve `zone_id` yazıyor | Alanlar yok |
| 2c | Model listede olmayan olay sınıfı döndürünce `"diğer"`e düşüyor | Alan yok |
| 2d | Sentez prompt'unda `EventClass` değerleri şemadakiyle birebir aynı | Enum yok |
| 3 | `plan_actions` eşleşen protokolü seçip adımlarını araca bağlıyor | Fonksiyon yok |
| 3b | Protokol süzgeci `event_class` + `zone_id` + `min_risk` üçünü birden uyguluyor | Süzgeç yok |
| 4 | Model bozuk JSON döndürdüğünde plan protokol adımlarına düşüyor, `plan_source="protocol_fallback"` | Fonksiyon yok |
| 5 | Eşleşen protokol yokken plan boş ve `plan_source="empty"`, ama `actions` anahtarı yine üretiliyor | Fonksiyon yok |
| 6 | `plan_actions` yazma aracı çağırmaya kalkarsa reddediliyor | Fonksiyon yok |
| 7 | Uydurma `tool_name` plandan düşüyor | Fonksiyon yok |
| 8 | `risk_analyst → action_planner → supervisor` deviri deftere yazılıyor | Yeni ad geçersiz |
| 9 | `AgentName` `"router"`/`"synthesizer"` kabul etmiyor, `"orchestrator"`/`"anomaly_analyst"` kabul ediyor | Tersi doğru |
| 10 | KPI kova adları yeniden adlandırma sonrası değişmiyor (`closed_at_router` hâlâ üretiliyor) | — regresyon kilidi |
| 11 | Kök neden raporu protokol kimliğini ve "uygulanmadı" tespitini içeriyor | Rapor protokolü bilmiyor |
| 12 | Uçtan uca: dört anahtarlı çıktı sözleşmesi planlayıcı düştüğünde de üretiliyor | — regresyon kilidi |

Mevcut `tests/test_risk.py` içinde `proposed_actions`'a bakan sekiz iddia
`tests/test_action_planner.py`'ye taşınır; taşınırken **daraltılmaz** —
kaybolan iddia, kaybolan davranıştır.

---

## 8. Riskler

**R1 — Kritik anda bir model çağrısı daha.** Yeni durak tam olarak operatörün
donmuş kareye bakıp beklediği yere düşüyor. Hafifletme: risk şeması küçüldü
(§3), aday protokoller deterministik süzülüyor (model bütün tabloyu okumuyor),
planlayıcı `llm-fast` kademesinde denenecek. Ölçüm §7/#10 ile aynı koşuda
alınır. Kabul edilen bir takas, sürpriz değil.

**R2 — Başka oturumla çakışma.** `memory.py` başka bir oturumda yeniden
yazılıyor; bu tur `models.py`, `store.py` ve `loop.py`'ye dokunuyor. İkisi de
`AgentName`'e bakıyor. Birleştirme sırası önceden konuşulmalı.

**R3 — Protokol fixture'ı senaryoya fazla oturursa.** Dört-altı protokol
demo anlarını birebir örterse sistem "prosedürü uygula" makinesine benzer.
Hafifletme: en az bir demo anı **eşleşen protokolü olmayan** bir olay olsun ki
`plan_source="empty"` yolu sahnede de görünsün.

**R4 — Bu tur bitmiş bir sistemi açıyor.** Görev tablosunda 18 dışında her şey
kapalı. Yeniden adlandırma geniş ama sığ; asıl derinlik yeni ajanda. Her adım
kendi testiyle iniyor, tur ortasında yarım bir zincir bırakılmıyor.

---

## 9. Belgeleme

Bu tur indiğinde güncellenir:

- `docs/05-decisions/decision-log.md` — 0b'deki beş karar, gerekçeleriyle
- `docs/tasks/README.md` — yeni görev satırı ve durum
- `docs/superpowers/specs/2026-08-22-agentic-gozcu-design.md` — §3
  "Components" listesine üstyazı bandı: kadro ve adlar bu dokümanda
- PDF'in kendisi — §0b/2'deki "offline" düzeltmesi, askerler örneğinin
  fabrika örneğiyle değişmesi, sekiz-ajan çerçevesinin altı ajan + iki alt
  sistem olarak yeniden çizilmesi
