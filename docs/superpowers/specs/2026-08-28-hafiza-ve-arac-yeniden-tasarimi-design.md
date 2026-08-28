# Hafıza ve araç yeniden tasarımı (tasarım)

**Tarih:** 28 Ağustos 2026 · **Durum:** taslak → kör inceleme
**Üzerine yazdığı belgeler:**
- [2026-08-27-capraz-video-hafiza-design.md](2026-08-27-capraz-video-hafiza-design.md)
  — epizodik hafıza ve koşu içi kısa süreli hafıza. **Bu belge onun üzerine
  yazar**; çelişki halinde burası geçerli.
- [2026-08-27-mikro-ajan-yeniden-tasarimi-design.md](2026-08-27-mikro-ajan-yeniden-tasarimi-design.md)
  §2e — action_planner'ın araç seti. **Bu belge o bölümü ezer.**

---

## §0. Sorunun özeti

Hafıza sistemi üç katmandan oluşuyor; üçü de yarı çalışıyor:

| Katman | Yazan | Okuyan | Sorun |
|---|---|---|---|
| Koşu içi (`RunMemory`) | pipeline | orchestrator, interpreter | **Supervisor erişemiyor** — operatör "10. saniyede ne oldu?" deyince model uyduruyor (PR #5'in kanıtladığı) |
| Epizodik arşiv (Qdrant `episodes`) | pipeline | risk_analyst (hardcode), supervisor (araç) | Risk analisti **aracı çağırmıyor**, sonuç prompt'a enjekte ediliyor — jüri "dinamik araç seçimi" görmüyor |
| Belge deposu (Qdrant `documents`) | UI yükleme | **HİÇBİR AJAN** | Yalnız yazma var, okuma yok; PDF sessizce başarısız; silmede vektör temizlenmiyor |

Ek olarak: `query_shift_personnel` ve `query_equipment_history` senaryo
başına sabitlenmiş JSON fixture'lardan okuyor. Operatör bunları değiştiremiyor,
farklı bir tesis/senaryo için yeniden yazılmaları gerekiyor. Ajanın kendi
yüklediği belgelerden (vardiya listesi, ekipman kartı, prosedür) dinamik
olarak bilgi çekmesi daha güçlü bir demo — jüri hem belge yüklemeyi hem
`search_documents` araç çağrısını görüyor.

### Puan cetvelinde dokunduğu yerler

| Kriter | Ağırlık | Dokunuş |
|---|---|---|
| Fonksiyonellik | %35 | Mock araçların başarılı kullanımı, sistemin kararlı çalışması |
| Teknik İmplementasyon | %35 | **Dinamik araç seçimi**, bağlam yönetimi, **çok adımlı karar zincirleri**, **memory** |
| Otonomi ve Zekâ | %20 | İnisiyatif alma, doğru soruları sorma, bağlam değişimine tepki |
| Yenilikçilik | %10 | Beklentinin ötesinde ek özellikler — **belge yükleme + RAG** |

---

## §1. Araç yeniden düzeni

### 1a. Kaldırılan araçlar

| Araç | Neden |
|---|---|
| `query_shift_personnel` | Fixture'a bağlı; `search_documents` ile operatörün yüklediği vardiya listesinden okunacak |
| `query_equipment_history` | Fixture'a bağlı; `search_documents` ile operatörün yüklediği ekipman kartından okunacak |

**Üzerine yazdığı spec:** Mikro-ajan spec §2e, action_planner'a bu iki aracı
veriyor. Bu belge o kararı eziyor: ajanlar artık fixture yerine operatörün
yüklediği belgelerden bilgi çeker.

**Fixture dünyası kaldırılmıyor.** `gozcu/fixtures/` altındaki JSON dosyaları
silinmez — bu araçlar `field_systems.py`'den kaldırılır, fixture'lar
`protocols.json` ve zone çözümleme tarafından hâlâ kullanılabilir.

### 1b. Korunan araçlar

Beş saha aracı **aynen kalıyor**, onay kapısı **boş kalıyor** (26 Ağustos
kararı):

| Araç | Tip | Değişiklik |
|---|---|---|
| `radio_call` | Aksiyon | Yok |
| `dispatch_medical` | Aksiyon | Yok |
| `site_alarm` | Aksiyon | Yok |
| `halt_production_line` | Aksiyon | Yok |
| `open_safety_incident` | Aksiyon | Yok |

`NEEDS_APPROVAL` **boş kalır.** 26 Ağustos ölçümü (kapılı: 0 araç çağrısı,
kapısız: 4 çağrı) bunu kesinleştirdi. Karar günlüğündeki gerekçe aynen
geçerli.

### 1c. Eklenen araçlar

| Araç | Tip | Açıklama |
|---|---|---|
| `search_timeline` | Okuma | **Yeni değil, yeni erişim.** Bugün supervisor'da araç, risk_analyst'ta hardcode. Risk analisti artık bunu araç olarak çağırır — model karar verir |
| `search_documents` | Okuma | **YENİ.** Qdrant `documents` koleksiyonunda anlamsal arama. Yüklenen belgelerden (vardiya listesi, ekipman kartı, prosedür, güvenlik talimatı) bilgi döndürür |
| `query_current_run` | Okuma | **YENİ.** `RunMemory`'nin pencere notlarını döndürür. Opsiyonel `from_s`/`to_s` zaman aralığı filtresi |

### 1d. Ajan başına araç dağılımı

| Ajan | Model | Araçlar | Maks tur | Değişiklik |
|---|---|---|---|---|
| Orchestrator | `router` | — | 1 | Yok |
| Interpreter | `vlm` | — | 1 | Yok |
| Anomaly Analyst | `fast` | — | 1 | Yok |
| **Risk Analyst** | `main` | `search_timeline`, `search_documents` | **6** (son tur araçsız) | **Kırılma:** fixture araçları gitti, arşiv araç oldu, belge araması eklendi, tur limiti 2→6 |
| **Action Planner** | `main` | `search_documents` | 2 | **Kırılma:** fixture araçları gitti, belge araması eklendi |
| **Supervisor** | `main` | 5 aksiyon + `search_timeline`, `search_documents`, `query_current_run`, `correct_observation`, `request_risk_assessment`, `generate_root_cause_report` | 4 | **Ekleme:** `search_documents`, `query_current_run` |
| Reporter | `main` | — | 1 | Yok |
| Guard | `guard` | — | 1 | Yok |

**Toplam araç sayısı:** 5 (aksiyon) + 3 (okuma) + 3 (supervisor dahili) = **11**.
Önceki: 7 + 4 = 11. Net sayı aynı; karakter değişti — fixture'a bağlı statik
araçlar yerine dinamik RAG araçları.

### 1e. Risk analisti tur mekanizması

**Bugün:**
1. Tur 1: `ask(messages, tools=READ_TOOL_SCHEMAS)` — model araç çağırabilir
2. Tur 2: `ask(messages)` — araçlar **yok**, model zorla değerlendirme üretir

**Bundan sonra:**
1. Tur 1–5: `ask(messages, tools=RISK_TOOL_SCHEMAS)` — model istediği
   kadar araç çağırır
2. Model araç çağrısı yapmazsa → döngü biter, değerlendirme alınır
3. Tur 6 (güvenlik ağı): `ask(messages)` — araçlar **yok**, zorla
   değerlendirme

**Neden 6:** Gateway'in ana kademe yanıt süresi 0.9–4.6s (ölçülmüş). 5 araç
turu × ~3s = ~15s ek gecikme — kabul edilebilir. 6. tur yalnız güvenlik ağı;
pratikte modelin 2–3 turda yeterli bağlam toplaması bekleniyor.

**Yapısal garanti:** Son tur her zaman araçsız. Bu, `RiskAssessment`
üretimini garanti eden yük taşıyan desen — kaldırılmaz.

---

## §2. Belge gömme — MarkItDown

### 2a. Sorun

`embed_document()` bugün `data.decode("utf-8")` yapıyor. PDF, DOCX, PPTX,
XLSX gibi ikili dosyalar `UnicodeDecodeError` ile sessizce başarısız —
`embedded: false` olarak kaydediliyor. OCR yok, metin çıkarma yok.

### 2b. Çözüm

`markitdown` kütüphanesini bağımlılık olarak ekle. `embed_document()`
akışını değiştir:

```
dosya yükle → MarkItDown.convert(dosya_yolu) → Markdown çıktısı
  → 8000 karakter kes → embed(f"{dosya_adı} | {metin}")
  → Qdrant upsert
```

**Geri dönüş:** MarkItDown başarısız olursa (desteklenmeyen format) →
bugünkü `data.decode("utf-8")` denensin → o da başarısız olursa →
`embedded: false`.

### 2c. Desteklenen formatlar

MarkItDown'ın desteklediği: PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML,
ZIP, resim (EXIF + alt metin), ses (transkript). Çıktı her zaman Markdown.

### 2d. UI güncelleme

Yükleme bölgesindeki `md · txt · json · csv · pdf` listesi
güncellenir: `pdf · docx · pptx · xlsx · md · txt · json · csv`.

### 2e. `embed_document()` imza değişikliği

Bugün:
```python
def embed_document(gw, document, data: bytes, client=None) -> bool
```

MarkItDown dosya yolu bekliyor; `data: bytes` yerine diske kaydedilmiş
dosyanın yolunu almak gerekecek. `library.save_document()` zaten dosyayı
`documents/{uuid}/content` yoluna yazıyor — bu yol geçirilir.

Bundan sonra:
```python
def embed_document(gw, document, file_path: Path, client=None) -> bool
```

---

## §3. `search_documents` — yeni retrieval fonksiyonu

### 3a. Fonksiyon

`gozcu/memory/episodic.py`'ye eklenir:

```python
def search_documents(gw, query: str, top_k: int = 3,
                     threshold: float | None = None,
                     client=None) -> list[DocumentResult]:
```

### 3b. `DocumentResult` modeli

`gozcu/core/models.py`'ye eklenir:

```python
class DocumentResult(Base):
    document_id: str
    name: str
    text_excerpt: str        # gömme sırasında kaydedilen metin, 500 karakter
    score: float
```

### 3c. Akış

1. `gw.embed(query)` ile sorgu vektörü oluştur
2. `QDRANT_DOCUMENT_COLLECTION` üzerinde `query_points()` çağır
3. Sonuçları `threshold` ile süz (varsayılan: `QDRANT_SCORE_THRESHOLD_DIALOGUE`)
4. `DocumentResult` listesi döndür

### 3d. Araç şeması

```python
SEARCH_DOCUMENTS = "search_documents"

{"type": "function", "function": {
    "name": "search_documents",
    "description": "Operatörün yüklediği referans belgelerinde anlamsal arama "
                   "yapar. Vardiya listesi, ekipman kartı, prosedür, güvenlik "
                   "talimatı gibi belgelerde bilgi arar.",
    "parameters": {"type": "object",
                   "properties": {"query": {"type": "string",
                                            "description": "Aranacak konu"}},
                   "required": ["query"]}}}
```

### 3e. Belge ön bilgisi — ajan prompt'una enjekte

Gömülü belge sayısı ve başlıkları, araç açıklamasının bir parçası olarak
veya sistem prompt'una enjekte edilerek ajana iletilir. Böylece ajan hangi
belgelerin mevcut olduğunu bilir ve ona göre arama yapar.

Format:

```
YÜKLÜ BELGELER (search_documents aracıyla erişilebilir):
1. "Vardiya_Listesi_Agustos.xlsx" — vardiya personeli ve sertifikaları
2. "Forklift_B12_Bakim_Karti.pdf" — ekipman bakım ve arıza geçmişi
3. "ISG_Prosedur_Genel.docx" — iş güvenliği prosedürleri
(Belge yoksa bu bölüm boş bırakılır.)
```

Bu bilgi `library.list_documents()` çağrısıyla dinamik olarak üretilir.
Yalnız `embedded: true` olan belgeler listelenir.

---

## §4. Qdrant vektör temizliği

### 4a. Sorun

`DELETE /api/library/documents/{doc_id}` dosyayı diskten siliyor ama
Qdrant'taki vektörü bırakıyor. Yorum: "bir sonraki koleksiyon temizliğine
kadar kalır."

### 4b. Çözüm

Silme endpoint'ine Qdrant cleanup ekle:

```python
point_id = uuid5(_NAMESPACE, f"belge:{doc_id}")
target.delete(
    collection_name=QDRANT_DOCUMENT_COLLECTION,
    points_selector=PointIdsList(points=[str(point_id)])
)
```

**Hata yönetimi:** Qdrant erişilemezse (ağ hatası, anahtarsız çalışma) →
dosya diskten yine silinir, uyarı loglanır. Disk tutarlılığı Qdrant
tutarlılığından önce gelir.

---

## §5. `query_current_run` — RunMemory aracı

### 5a. Sorun

`RunMemory` yalnız orchestrator ve interpreter'a akıyor. Supervisor mevcut
koşunun gözlemlerine erişemiyor — operatör "10. saniyede ne oldu?" deyince
model uyduruyor. PR #5 (`fix/supervisor-kosu-zaman-cizelgesi`) bu sorunu ham
gözlem okumasıyla çözmüş ama RunMemory'yi atlıyor.

### 5b. Çözüm

RunMemory'yi supervisor'a bir araç olarak aç. PR #5'i kapat.

### 5c. Araç şeması

```python
QUERY_CURRENT_RUN = "query_current_run"

{"type": "function", "function": {
    "name": "query_current_run",
    "description": "Bu koşudaki pencere gözlemlerini döndürür. "
                   "Mevcut videoda ne olduğunu, kimlerin/nelerin görüldüğünü "
                   "ve hangi kararların verildiğini sorgular.",
    "parameters": {"type": "object",
                   "properties": {
                       "from_s": {"type": "number",
                                  "description": "Başlangıç saniyesi (opsiyonel)"},
                       "to_s": {"type": "number",
                                "description": "Bitiş saniyesi (opsiyonel)"}},
                   "required": []}}}
```

### 5d. Uygulama

Supervisor'ın `__init__`'ine `run_memory: RunMemory | None` parametresi
eklenir. `_internal_tool` dispatch'ine `QUERY_CURRENT_RUN` dalı eklenir.

Davranış:
1. `run_memory` yoksa (None) → `"Bu koşuda henüz gözlem kaydı yok."` döndür
2. `from_s`/`to_s` verilmişse → `run_memory.recent()` sonuçlarını zaman
   aralığına göre filtrele
3. `from_s`/`to_s` verilmemişse → `run_memory.recent()` tam döndür
4. Sonuç formatı: `MM:SS [katılımcılar] — açıklama` satırları (render()
   formatına benzer)

### 5e. `RunMemory.recent()` filtre uzantısı

`recent()` bugün `n` parametresi alıyor (son N pencere). Zaman aralığı
filtresi eklenir:

```python
def recent(self, n: int = 3, *,
           from_ts: float | None = None,
           to_ts: float | None = None) -> list[WindowNote]:
```

Eklenen mantık: `from_ts`/`to_ts` verilmişse, zamana göre süz; sonra
mevcut `n` + pin mantığını uygula.

---

## §6. Risk analisti — `search_timeline` araç olarak

### 6a. Bugün

`assess_risk()` ([risk.py:300](../../../gozcu/agents/risk.py)) `search_timeline()`'ı
Python fonksiyonu olarak çağırıyor, sonucu `ARSIV:` başlığı altında
prompt'a enjekte ediyor. Model bu aramayı hiç görmüyor.

### 6b. Bundan sonra

`search_timeline` risk analisti'nin araç setine eklenir. Model kendi
karar verir: arşivi aramak mı, belge aramak mı, ikisini birden mi,
hiçbirini mi.

**`ARSIV:` enjeksiyonu kaldırılır.** Prompt'taki `{history_text}` bölümü
çıkar. Yerine araç açıklaması modeli yönlendirir.

### 6c. `exclude` mantığı

Bugün `search_timeline()` çağrısında `exclude=(episode.source, episode.id)`
geçiriliyor — mevcut epizotun kendisini emsal olarak döndürmemesi için.

Araç olarak çağrıldığında bu bilgi modelden gelmez — sunucu tarafında
uygulanır. `_internal_tool` dispatch'i mevcut açık epizotun `source` ve
`id`'sini otomatik olarak `exclude` parametresine geçirir (supervisor'daki
mevcut desene benzer şekilde).

### 6d. `threshold` yapılandırması

İki farklı eşik kalıyor:
- `QDRANT_SCORE_THRESHOLD_RISK = 0.54` — risk analisti tarafından yapılan
  aramalar için (cümle tabanlı sorgu)
- `QDRANT_SCORE_THRESHOLD_DIALOGUE = 0.47` — supervisor tarafından yapılan
  aramalar için (soru tabanlı sorgu)

Hangi eşiğin uygulanacağı `caller` parametresinden belirlenir.

---

## §7. Prompt değişiklikleri

### 7a. Risk analisti sistem prompt'u

**Çıkan:**
- `ARSIV:` bölümü (statik enjeksiyon)
- `query_shift_personnel`, `query_equipment_history` araç referansları

**Eklenen:**
- `search_timeline` ve `search_documents` araç kullanım talimatları
- Yüklü belge listesi (§3e)
- "Arşivi ve belgeleri araştır, sonra değerlendir" yönlendirmesi

### 7b. Action planner prompt'u

**Çıkan:**
- `query_shift_personnel`, `query_equipment_history` araç referansları

**Eklenen:**
- `search_documents` araç kullanım talimatı
- Yüklü belge listesi (§3e)

### 7c. Supervisor sistem prompt'u

**Eklenen:**
- `search_documents` araç açıklaması
- `query_current_run` araç açıklaması
- Yüklü belge listesi (§3e)

---

## §8. `field_systems.py` ve `registry.py` değişiklikleri

### 8a. `field_systems.py`

`query_shift_personnel()` ve `query_equipment_history()` fonksiyonları
**silinir**. Fixture import'ları bu fonksiyonlara özgüyse onlar da
temizlenir. `protocols.json` kullanan fixture fonksiyonları (zone
çözümleme vb.) kalır.

### 8b. `registry.py`

`TOOLS` dict'inden iki araç çıkar. `TOOL_SCHEMAS` ve `_TOOL_SPECS`
güncellenir. `call_tool()` bu iki adı artık tanımaz.

### 8c. `risk.py`

`READ_TOOLS` ve `READ_TOOL_SCHEMAS` kaldırılır. Yerine:

```python
RISK_TOOLS = ("search_timeline", "search_documents")
RISK_TOOL_SCHEMAS = [SEARCH_TIMELINE_SCHEMA, SEARCH_DOCUMENTS_SCHEMA]
```

`assess_risk()` akışı: §1e'deki tur mekanizmasına dönüşür.

### 8d. `action_planner.py`

`PLANNER_READ_TOOLS` ve `PLANNER_TOOL_SCHEMAS` güncellenir:

```python
PLANNER_READ_TOOLS = ("search_documents",)
PLANNER_TOOL_SCHEMAS = [SEARCH_DOCUMENTS_SCHEMA]
```

`_describe_tool()` hâlâ tüm 5 aksiyon aracının şemasını prompt'a yazıyor
(öneri kelime dağarcığı olarak). Bu değişmiyor.

---

## §9. Değişmeyen şeyler

- Orchestrator, interpreter, anomaly_analyst, reporter, guard — dokunulmaz
- Epizot gömme akışı (`embed_episode`) — dokunulmaz
- Dört çıktı anahtarı (`summary`, `events`, `risk`, `actions`) — dokunulmaz
- `protocols.json` fixture'ı ve deterministik protokol eşleşme — dokunulmaz
- Supervisor'ın `correct_observation`, `request_risk_assessment`,
  `generate_root_cause_report` araçları — dokunulmaz
- `NEEDS_APPROVAL` boş — dokunulmaz
- `RunMemory`'nin orchestrator ve interpreter'a akışı — dokunulmaz (ek olarak
  supervisor'a da açılıyor)

---

## §10. Riskler ve azaltma

| Risk | Olasılık | Azaltma |
|---|---|---|
| Risk analisti 6 turda hiç değerlendirme üretmez | Düşük | Son tur araçsız — yapısal garanti |
| Risk analisti gereksiz yere döngüye girer (aynı sorguyu farklı kelimelerle) | Orta | Prompt'ta "yeterli bilgi topladığında değerlendir" yönlendirmesi; 6-tur üst sınırı |
| MarkItDown büyük PDF'lerde yavaş | Düşük | Yükleme sırasında yapılıyor (arka plan), koşu sırasında değil |
| Belge aramasının kalitesi fixture araçlarından düşük | Orta | Fixture dünyası deterministik, RAG yaklaşık. Ama jüri **dinamik araç seçimini** puanlıyor, deterministik fixture okumasını değil |
| `query_current_run` RunMemory boşken çağrılır | Düşük | Boş yanıt döndürür, hata değil |
| Qdrant cleanup ağ hatasında başarısız | Düşük | Dosya diskten yine silinir; yetim vektör zararsız |

---

## §11. Test stratejisi

### Yeni testler

1. **`test_search_documents`** — `search_documents()` fonksiyonu: gömme, arama,
   eşik filtreleme, boş koleksiyon
2. **`test_embed_document_markitdown`** — MarkItDown ile PDF/DOCX/XLSX gömme,
   geri dönüş (desteklenmeyen format), boş dosya
3. **`test_query_current_run`** — araç çağrısı: boş RunMemory, zaman filtresi,
   tam döndürme
4. **`test_qdrant_cleanup_on_delete`** — belge silmede vektör temizliği, Qdrant
   erişilemezken graceful degradation
5. **`test_risk_analyst_tool_loop`** — risk analisti 6-tur mekanizması: erken
   çıkış (2 turda), tam 6 tur, son tur araçsız garantisi
6. **`test_risk_analyst_search_timeline_tool`** — `search_timeline` araç olarak
   çağrıldığında `exclude` mantığının çalışması

### Değişen testler

- `test_risk.py` — `READ_TOOLS` referansları güncellenir
- `test_action_planner.py` — `PLANNER_READ_TOOLS` referansları güncellenir
- `test_supervisor.py` — yeni araç sayısı (11→11, ama farklı araçlar)
- `test_registry.py` — araç sayısı 7→5
- `test_episodic.py` — `embed_document` imza değişikliği

---

## §12. Bağımlılık

```toml
[project.dependencies]
markitdown = ">=0.1.0"
```

`pyproject.toml`'a eklenir. MarkItDown'ın kendi bağımlılıkları (pdfminer,
python-pptx, openpyxl vb.) transitif olarak gelir.

---

## §13. PR #5 (`fix/supervisor-kosu-zaman-cizelgesi`)

Bu PR `query_run_timeline` adında ham gözlem okuyan bir araç ekliyordu.
`query_current_run` (RunMemory tabanlı) aynı sorunu daha temiz çözüyor.

**Karar:** PR #5 kapatılır, branch silinir. Bu spec'in implementasyonu
onun yerine geçer.
