# Çapraz video epizodik hafıza + koşu içi kısa süreli hafıza (tasarım)

**Tarih:** 27 Ağustos 2026 · **Durum:** taslak → kör inceleme
**Kaynak belge:** `bunu-implament-etmek-icin-vast-starlight.md` (kullanıcı
tarafından verildi; içindeki B1–B9 arızaları koşturularak ölçülmüş).
**Bu belgedeki ek ölçümler:** 27 Ağustos, depo üzerinde — canlı `team37`
koleksiyonu, `.env`, `pytest --collect-only`, `git log`.

---

## §0. Sorun — sistemin iki türlü hatırlaması gerekiyor, ikisi de çalışmıyor

1. **Koşu içi (kısa süreli).** Video 10 saniyelik pencerelere bölünüyor ve görü
   katmanı her pencereye **sıfırdan** bakıyor. 2. dakikadaki dengesizlik, 5.
   dakikadaki devrilmenin bağlamı olamıyor.
2. **Videolar arası (uzun süreli).** Operatörün *"bu araçla daha önce sorun oldu
   mu?"* sorusu — plan-of-record demo senaryosunun 5. beat'i ve şartnamenin adıyla
   saydığı "bağlam değişimi" koşulu — her seferinde "kayıt bulunamadı" alıyor.

Kod yazılmış ve testleri geçiyor (`gozcu/memory.py`). Sorun **canlı hiçbir
koşuda devreye girmemesi**. Bu bir özellik geliştirme değil, bir **onarım**.

Puan cetvelinde dokunduğu yer: %35 teknik implementasyon (dört anahtar
kelimesinden biri doğrudan *memory*), %20 otonomi ve zekâ (bağlam değişimi),
%35 fonksiyonellik ve senaryo kapsamı (senaryoda yazılı bir beat sahnede
başarısız oluyor).

### Ölçülmüş arızalar

| # | Arıza | Kanıt |
|---|---|---|
| **B1** | `load_history()` hiçbir yerden çağrılmıyor — yalnız testlerden | `app.py` → `ui/server.baslat()`; grep'te üretim çağrısı yok |
| **B2** | **Kapanmayan epizot arşive HİÇ girmiyor** | Gömmenin tek yolu `_on_close` ([run.py:205](../../../gozcu/run.py)), o da yalnız `close_episode` dalında. Gerçek demo klibinde epizot videonun sonuna kadar açık kalıyor. `_sweep_stale_risk` risk biçiyor, **gömmüyor** |
| **B3** | Koşular birbirini eziyor | Nokta kimliği `episode.id` = koşu içi SQLite rowid; `Store()` her koşuda `":memory:"`. İki videodan iki epizot → **1 nokta** |
| **B4** | Alaka eşiği yok | `query_points(..., limit=top_k)`, `score_threshold` geçilmiyor. Alakasız sorgu ("kantinde yemek kuyruğu uzadı") 3 kaydın **üçünü de** döndürdü — 0,743 / 0,557 / 0,371 |
| **B5** | Emsalin kökeni yok | `Episode` hangi videodan/tarihten geldiğini taşımıyor |
| **B6** | Hafıza hiçbir ekranda görünmüyor | Emsal yalnız prompt'a giriyor; jüri prompt görmez |
| **B7** | **Yerel Qdrant eş zamanlı erişimde güvenli değil** | `ValueError: operands could not be broadcast together with shapes (32,) (31,)`; `search_timeline`'ın geniş `except`'i yutuyor → 400 sorgunun 6'sı sessizce `[]` |
| **B8** | Aynı videonun ikinci koşusu emsal listesini ikizliyor | Aynı `source`'tan 2 nokta |
| **B9** | `.env` var ama iki anahtar da boş | **ARTIK GEÇERSİZ — bkz. §0b** |

### Ve saf onarım çıktı sözleşmesini bozuyor

`load_history`'yi olduğu gibi çağırmak **yasak**:

- `build_output` ([report.py:172](../../../gozcu/report.py)) **bütün**
  `store.episodes()`'i geziyor → fikstürler `00:00` damgasıyla şartnamenin
  puanlanan `events[]` dizisine girer.
- **`risk` yedeği kayar:** `levels = [r.level for r in risks] or [e.preliminary_risk …]`.
  Değerlendirmesiz bir koşuda bu videonun gerçeği **Düşük**, teslim edilen
  **Yüksek** olur.
- **Körlük itirafı ölür:** `if not episodes and perception.blind` üç fikstürle
  asla tetiklenmez.
- **Kök neden raporu kirlenir:** `agents/reporter.py` de `store.episodes()` okuyor.

---

## §0b. Kaynak belgeden ölçülmüş sapmalar — 27 Ağustos

Kaynak belge 26 Ağustos'un deposuna karşı yazıldı. O günden bu yana üç şey
değişti; **belgenin satır referansları bu üç noktada geçersiz** ve plan onları
düzeltilmiş hâliyle uygular.

| Kaynak belge | 27 Ağustos'ta ölçülen |
|---|---|
| B9: iki anahtar da sıfır karakter | **İkisi de dolu ve gerçek** — `GOZCU_GATEWAY_API_KEY` (`sk-evren-t…`, 48 hane), `GOZCU_QDRANT_API_KEY` (`qdr-team37…`, 43 hane) |
| Bağlanma noktaları `gozcu/ui/console.py:{91,535,537,552,681,708}` | **`console.py` 27 Ağustos'ta emekliye ayrıldı** (`d651abd`, Görev 21). Yerine `gozcu/ui/server.py` (`post_run`, `_work`, `/api/meta`) ve `gozcu/ui/session.py` (`Session.__init__`, `archived`) |
| "948 test tabanı" | **1026 test** (`pytest --collect-only`) |
| Aşama 0.3: koleksiyonu silmek takım arkadaşlarının koşularını da siler | Canlı `team37/episodes` koleksiyonunda **tam 3 nokta** var: kimlikler `1`/`2`/`3`, payload anahtarları `[end_ts, id, participants, phase, preliminary_risk, start_ts, state, summary_tr]` — üçü de `prior_incidents.json`'ın fikstürleri. **`source` yok, `summary_source` yok, `beats` yok.** Takım koşusundan gelen tek bir nokta bile yok. |

**Doğrulanan ve DEĞİŞMEYEN her şey.** `_on_close` gömmenin tek yolu;
`_sweep_stale_risk` gömmüyor; `search_timeline` `score_threshold` geçmiyor;
`load_history`'nin üretim çağrısı yok; `_write_ledger` / `Store.save_embedding`
/ `episode_embedding` tablosu canlı; `_route_accepts_energy` iki **veya daha
çok** konumsal parametre sayıyor (yani üçüncü parametre tespiti bozmuyor);
`build_output` bütün epizotları geziyor.

### Bunun tasarıma etkisi

1. **Aşama 0.1 (anahtar iste) düştü.** Anahtarlar var; her doğrulama adımı
   gerçek kalıcılığa karşı koşulabilir.
2. **`GOZCU_QDRANT_PATH` KALIYOR ama gerekçesi değişti.** Kaynak belgedeki
   gerekçe ("anahtar yok, gerçek çalışma modu yerel mod") artık yanlış. Yeni
   gerekçe iki tane ve ikisi de ölçülebilir: (a) prova koşuları paylaşılan
   `team37`'yi kirletmeden **kalıcı** bir arşive yazabilmeli — çapraz video
   davranışı ancak süreçler arası yaşayan bir depoda kanıtlanabilir;
   (b) `memory_backend()`'in üç değeri, sessiz düşüşün rozette görünmesini
   sağlıyor ve bu proje sessiz düşüşü bir kez ağır ödedi.
3. **B7 kilidi KALIYOR.** Uzak istemcide eşzamanlılığı sunucu hallediyor, ama
   1026 testin tamamı ve anahtarsız her koşu yerel istemcide koşuyor; Aşama 1
   ayrıca tohumlamayı bilerek boru hattıyla örtüştürüyor.

---

## §0c. Ürün sahibi kararı — 27 Ağustos

**Koleksiyon tamamen düşürülecek** (`delete_collection`), cerrahi silme değil.
Uveys'e üç seçenek ölçümle birlikte sunuldu; seçilen bu. Sonuç: `_ensure_collection`
koleksiyonu sıfırdan kurar, fikstürler yeni UUID kimlikleriyle yeniden
tohumlanır. Kayıp, `prior_incidents.json`'dan bire bir yeniden üretilebilen üç
noktadır.

**Silme elle ve bilerek çalıştırılan bir script'te.** `scripts/reset_memory.py`
çıplak çağrıldığında **hiçbir şey silmez** — ne yapacağını yazar ve çıkar;
silmesi için `GOZCU_MEMORY_RESET=1` gerekir. Gerekçe: paylaşılan bir takım
kaynağını düşüren bir dosya `scripts/` altında durup yanlışlıkla
çalıştırılabilecek durumda bırakılmaz.

---

## §1. Mimari karar — tek cümle

> **SQLite (`Store`) koşu kapsamlı KALIR. Qdrant, uzun süreli hafızanın TEK
> adresidir.** Arşiv, koşunun deposuna hiç girmez.

Kalıcı SQLite denendi ve **reddedildi**: videolar arası `open_episode` sızması
(koşu 2, koşu 1'in epizodunu açık görüyor → `_resolve('open_episode')` →
`'update_episode'`, yani video B video A'nın olayına kaynaşıyor), defter
birikmesi ve §0'daki dört çıktı arızası. Üstelik amacı da karşılamıyordu:
anahtarsız modda `build_client()` zaten süreç içi bir Qdrant döndürüyor.

Bu tek karar B1'in yan hasarını, çıktı sözleşmesi arızalarını ve `open_episode`
sızmasını **birlikte** çözüyor.

### Sıra — bağımlılık gerekçesiyle

| Aşama | İş | Neden bu sırada |
|---|---|---|
| **0** | `GOZCU_QDRANT_PATH` · üç değerli `memory_backend()` · koleksiyon sıfırlama script'i | Kalıcılığı kanıtlayabilen zemin |
| **1** | Arşiv yalnız Qdrant'ta (`load_history` depoya yazmayı bırakır) + tohumlamanın çağrılması | Çıktı sözleşmesi arızalarını (B1'in yan hasarı) açılmadan kapatır |
| **2** | Kimlik `uuid5(source:id)` + köken alanları + `source` zinciri | Aşama 3 ve 4 buna dayanıyor; yarısı bağlanırsa filtre sessizce boş döner |
| **3** | Koşu sonu gömme süpürmesi | **B2'nin onarımı.** Aşama 2'den sonra olmalı, yoksa çakışan kimlikle yazar |
| **4** | Dışlama filtresi · eşik iskeleti (`None`) · kaynak dedup · yerel kilit | Aşama 2'nin payload'ına muhtaç |
| **5** | Skorlu dönüş · `precedents` · EMSAL kartı · rozet | Aşama 4'ün skoruna muhtaç |
| **6** | Kısa süreli hafıza (`recall.py` + dört bağlanma noktası) | Bağımsız; ama Aşama 7'den **önce** olmalı |
| **7** | Eşik kalibrasyonu + arşiv kapsamı | **En son:** Aşama 6.1 özet metinlerini değiştiriyor, skorlar kayıyor |

**Sırayı bozarsan sessizce kırılanlar:** 3'ü 2'den önce yaparsan çakışan
kimlikle yazarsın; 7'yi 6'dan önce yaparsan eşiği iki kez kalibre edersin; 1'i
atlayıp 3'ü yaparsan canlı olay gömülür ama arşiv boş kalır — yarım çözüm,
demo yine boş.

---

## §2. Aşama 0 — zemin

### 2.1 `GOZCU_QDRANT_PATH`

`config.py`'a `QDRANT_PATH` (varsayılan boş dize). `build_client()` üç dallı:

```
anahtar varsa          → uzak istemci (bugünkü dal: port=443, prefix, REST-only)
anahtar yok + path     → QdrantClient(path=QDRANT_PATH)      # süreçler arası yaşar
anahtar yok + path yok → QdrantClient(":memory:")            # bugünkü davranış
```

`memory_backend()` artık **üç** değer döndürür: `"qdrant" | "local-disk" |
"local-memory"`. Sessiz düşüş bu projede yasak; rozet hangi modda olduğunu
söylemeli.

> **Kısıt, gizlenmeden yazılacak:** yerel disk Qdrant **tek süreç**. Aynı dizine
> ikinci istemci `RuntimeError: already accessed by another instance` alıyor —
> konsol ile `benchmark` aynı anda koşamaz. `build_client()` docstring'ine ve
> README'ye yazılır.

`ui/view.BADGE_LABELS`'in `"local"` anahtarı iki yeni anahtarla değişir:
`"local-disk" → "yerel disk"`, `"local-memory" → "yerel bellek"`. `BADGE_LABELS`
telin Türkçesinin **tek** kaynağı; ham değer değişmez, sunum ondan türer.

### 2.2 Koleksiyon sıfırlama

`scripts/reset_memory.py` — mevcut script geleneği (env değişkeni, argparse yok,
`REPO_ROOT = Path(__file__).resolve().parent.parent`, sonunda tek satır özet).
Yaptığı: koleksiyonun nokta sayısını yazar; `GOZCU_MEMORY_RESET=1` yoksa çıkar;
varsa `delete_collection` çağırır ve `load_history` ile yeniden tohumlar.

---

## §3. Aşama 1 — arşiv yalnız Qdrant'ta yaşar

**Dosya:** `gozcu/fixtures/loader.py`

`load_history(gw, store)` içindeki `store.create_episode(episode)` çağrısı
**kaldırılır**; fikstür doğrudan `embed_episode` ile gömülür. Fikstür `Episode`'u
bellekte kurulur, `id` alanı yükleyicide **açıkça** verilir (`episode.id = 0, 1,
2, …` sıra numarası) — `embed_episode`'un `episode.id is None` guard'ı **yerinde
kalır**, kaldırmak sessiz bir çakışma açar.

> **Tutamak kuralı — atlanırsa sessizce bozulur.** İmza `(gw, store)` olarak
> **değişmez** ve `store` hâlâ geçilir, ama artık bir depo değil
> **`memory._client()`'ın indeks anahtarı** olarak. Anahtarsız modda yerel
> istemciler tutamak başına bir `WeakKeyDictionary`'de tutuluyor. Ölçüldü:
> `store_A` ile tohumlayıp `store_B` ile aramak → **0 sonuç**. Docstring'e
> yazılır, yoksa biri "kullanılmayan parametre" diye siler.

**Ölen kod:** `memory._write_ledger`, `Store.save_embedding`, `Store.embeddings()`,
`episode_embedding` tablosu ve yükleyicinin tekrarsızlık kontrolü — kararlı
kimlik `upsert`'ü zaten idempotent yapıyor (Aşama 2). Görev 08'in tamamlanma
notları bunu zaten "Görev 17/18 borcu" diye işaretlemişti.

### Tohumlamanın çağrıldığı yer

`gozcu/ui/server.py::post_run` — `Session()` kurulduktan **sonra**,
`thread.start()`'tan **önce**.

- Senkron çağırma **yasak**: `QDRANT_TIMEOUT_S = 600`, uç dakikalarca asılı kalır.
- Ayrı thread + **sınırlı `join(timeout)`**. Süre dolarsa boru hattı yine başlar;
  B7 kilidi (§6.3) o örtüşmeyi güvenli kılar.
- `try/except` içinde: bozuk fikstür JSON'u bir koşuyu öldürmemeli.
- Dönen sayı `session.archive_count`'a yazılır — rozet onu okur (§7).

### Benchmark

`benchmark/run.py`'deki `seeded = {episode.id for episode in store.episodes()}`
artık **daima boş küme** döner. Zararsız — depoda zaten yalnız canlı epizotlar
var — ama `kpi.detections(store, seeded_episode_ids)` parametresi ölü hâle gelir.
**Silinmez, belgelenir.**

`run_pipeline`'a `archive: bool = True` bayrağı eklenir; benchmark `archive=False`
geçer. Bayrak **İKİ yola birden** ulaşmalı: koşu sonu süpürmesine (§5) ve
`_on_close`'un koşu ortasındaki gömmesine. Yalnız süpürmeyi kapatmak, kapanan her
epizodun yine `team37`'ye yazılması demektir.

> Parametre `run_pipeline` imzasının **sonuna** eklenir — bu dosyanın yerleşik
> geleneği (`motion_for` aynı gerekçeyle sona konmuş): araya sokulan bir parametre
> konumsal çağrıları sessizce kaydırır.

---

## §4. Aşama 2 — kimlik ve köken

**Dosyalar:** `gozcu/memory.py`, `gozcu/models.py`, `gozcu/run.py`,
`gozcu/agents/synthesizer.py`, `gozcu/ui/session.py`, `gozcu/ui/server.py`

### 4.1 Kaynak parmak izi

```python
def video_key(path) -> str:
    """Videonun kimliği: ilk 1 MB + dosya boyutu üzerinden sha256 (16 hane)."""

def point_id(episode: Episode) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{episode.source}:{episode.id}"))
```

- **Dosya adı değil içerik hash'i.** Yükleme ya da kopyalanmış bir `video.mp4`
  iki farklı videoyu aynı isimle getirir; çakışma iki alakasız olayı **tek
  noktada birleştirir** — çoğaltmadan kötü.
- **İkinci parça `episode.id`, `start_ts` DEĞİL.** `DecisionLoop.catch_up`
  ertelenmiş pencereleri sonradan işliyor ve **daha erken** `start_ts`'li
  epizotlar doğurabiliyor; zamana dayalı kimlik tam o anda kimlikleri birbirine
  kaydırırdı.
- Ölçüldü: eski kimlikle 2 epizot → **1 nokta**; `uuid5` ile → **2 nokta**.

### 4.2 Yeni `Episode` alanları

```python
source: str | None = None            # "9f2a…" | "arşiv:OLY-2026-0812"
occurred_at: str | None = None       # ISO 8601 METİN
equipment_ids: list[str] = []
actions_taken: list[dict] = []       # [{"tool": …, "eta_minutes": …, …}]
```

- `Base` `extra="forbid"` ama **alan eklemek güvenli**: `memory._episode()`
  bilinmeyen anahtarları süzüyor ve eksikler varsayılana düşüyor. Ölçüldü,
  **çift yönlü uyumlu**.
- **`occurred_at` ayrı ISO metin alanı; `start_ts`'e epoch damgası YAZILMAZ.**
  `start_ts` video saniyesi; oraya epoch yazılırsa `mmss()` onu `99:59`'a
  yapıştırır ve `kpi.epoch_scale_episodes` koşuyu düşürür.
- **Alanlar payload'a değil MODELE ekleniyor.** Modelde olmayan bir alan yazılır
  ama hiçbir zaman okunmaz — `_episode()` süzer, `supervisor`'ın `model_dump()`'ı
  da taşımaz.

### 4.3 `source` zincirinin bağlanması

`source` **yaratılışta** damgalanır, kapanışta değil: `Supervisor.escalate` →
`assess_risk` **açık** epizot üzerinde koşuyor; kapanışta damgalansaydı `exclude`
için elde `"None:0"` olurdu ve epizot kendi emsali olarak listenin başına otururdu.

Zincir: `run_pipeline(video_path)` → `video_key()` → `synthesize(..., source=…)`
→ `Episode(source=…)` (`synthesizer.py:298`, açılış dalı). Güncelleme dalı
`source`'a dokunmaz — epizot onu doğuşundan taşıyor.

> **`video_key` iki yerde çağrılır ve bu bilerek böyle:** bir kez
> `run_pipeline` içinde (epizotları damgalamak için), bir kez `post_run` içinde
> (`Supervisor`'ı kurmak için). `run_pipeline`'a `source` parametresi
> **EKLENMEZ**: ikisi de `session.video_path`'in aynı dosyasını okuyor ve hash
> saf, yani değerler eşit olmak zorunda. Parametre eklemek o eşitliği çağıranın
> disiplinine bırakırdı — ve bir çağıran onu geçmeyi unuttuğunda filtre sessizce
> boş küme döndürürdü (§4.3'ün baş tehdidi). Maliyet dosyanın ilk 1 MB'ının
> ikinci kez okunması; ölçülebilir değil.

`Supervisor` de kurulumda `source` alır (aynı filtreyi uygulayabilmek için).
**Tek üretim kurulum noktası `ui/session.py::Session.__init__`.** `post_run`
`Session()`'ı bugün yüklemeden ÖNCE kuruyor; `video_key` dosyanın diske tam
yazılmasını gerektirdiği için **`Session()` kurulumu yükleme döngüsünden SONRAYA
alınır** (aradaki tek kullanım `session.output_dir` ataması ve o da sonrasında).
`_run_lock` bütün blok boyunca tutulduğu için yarış penceresi açılmaz.

> **Yarısı bağlanırsa filtre sessizce boş küme döndürür.** Bu adım bitmeden
> Aşama 4'e geçilmez.

### 4.4 `actions_taken` doldurma

`ActionRecord`'da `episode_id` **yok**; eşleme video zamanıyla yapılır: gömme
anında `store.actions()` içinden `episode.start_ts <= a.ts <= episode.end_ts`
penceresine düşenler alınır, `tool_name` ve `result`'ın anahtar alanları
(`eta_minutes`, `team`, `zone_id`, `record_no`) yazılır.

Ölçüldü: `dispatch_medical` gerçekten `{'team': 'revir-1', 'eta_minutes': 4}`
döndürüyor, ama bu satır koşu kapsamlı SQLite'ta yaşıyor ve video bitince yok
oluyor. Bu alan olmadan *"geçen sefer ambulans kaç dakikada geldi"* **yapısal
olarak** cevaplanamaz.

---

## §5. Aşama 3 — koşu sonu gömme süpürmesi (B2'nin onarımı)

**Dosya:** `gozcu/run.py`

`_sweep_stale_risk`'in yanına `_sweep_unembedded(gw, store, fresh, source)`
eklenir ve `run_pipeline` içinde risk süpürmesinden **SONRA** çağrılır.

- **Neden sonra:** `_sweep_stale_risk` açık epizotların özetini ve riskini son
  hâline getiriyor. Gömme önce koşarsa arşive olayın **erken** hâli girer.
- **Neden `fresh`'in tamamı:** kapanmış/açık ayrımı yapılmaz. `embed_episode`
  idempotent ve istisna atmıyor; zaten gömülmüş epizot noktanın üstüne yazar.
- **Sessiz dal — bozulma tablosunda satır:** `embed_episode`,
  `summary_source == "fallback"` olan epizodu reddediyor — doğru karar, arıza
  metni emsal aramasını zehirler. Ama sentezin bozulduğu bir koşuda süpürme
  **hiçbir şey** arşivlemez ve bu bugün hiçbir yerde görünmüyor.
- **İkinci sessiz dal:** süpürme genişletilmiş yolun `try` bloğunun içinde. O yol
  çökerse koşu geçerli çıktı verir ama **arşive hiçbir şey yazılmaz**.
- **`source` parametresi bir yedek, ana yol değil.** Epizot `source`'unu §4.3'te
  doğuşunda alıyor; süpürme yalnız `episode.source is None` olan epizotlara onu
  geri yazar (sentez dalının atlandığı ya da eski bir satırın okunduğu durum).
  Zaten damgalı bir epizodun `source`'u **ezilmez** — ezilirse `catch_up` ile
  gelen bir epizot yanlış videoya bağlanabilirdi.
- **`archive=False` iken süpürme hiç koşmaz** ve `_on_close` de gömmez; ikisi
  aynı bayrağı okur (§3, benchmark).

---

## §6. Aşama 4 — arama kalitesi

**Dosya:** `gozcu/memory.py`

### 6.1 Dışlamanın filtreye taşınması

Bugünkü `Filter(must_not=[HasIdCondition(has_id=[exclude_id])])` UUID
kimliklerle eşleşmez. Yerine **iç içe** filtre:

```python
must_not=[Filter(must=[FieldCondition(key="episode_id", match=MatchValue(value=X)),
                       FieldCondition(key="source",     match=MatchValue(value=Y))])]
```

> **Ölçülmüş tuzak:** düz `must_not=[episode_id == X]` **iki noktanın ikisini
> birden** eledi — farklı videoların epizotları da 1 numarayı taşıyor. İç içe
> hâlde `videoB` doğru şekilde hayatta kaldı.

Payload'a `episode_id` ve `source` **ayrı anahtar olarak** yazılır (nokta kimliği
artık UUID, içinden okunamaz). `source` zaten `model_dump()`'ta; `episode_id`
`model_dump()`'ın yanına elle eklenir ve `_episode()` onu okurken süzer.

`search_timeline`'ın imzası `exclude_id: int | None` yerine
`exclude: tuple[str | None, int] | None` alır — çift, tek sayı değil.

### 6.2 Alaka eşiği ve kaynak tekilleştirmesi

- `config.py`'a **iki** eşik: `QDRANT_SCORE_THRESHOLD_RISK` ve
  `QDRANT_SCORE_THRESHOLD_DIALOGUE`. **Varsayılan `None`.**
  > `0.0` bir "koruma yok" değeri **DEĞİL**: kosinüs negatif skor üretebilir,
  > `0.0` negatifleri süzer — yani ölçülmemiş bir eşiktir. Korumasız hâl `None`'dır.
- **Neden iki:** `risk.py` arşivi bir **cümleyle** sorguluyor
  (`f"{summary_tr} {participants}"`), `supervisor.py` ise modelin yazdığı bir
  **soruyla**. Soru–cümle kosinüsü sistematik olarak cümle–cümle kosinüsünden
  düşük; tek eşik ya analisti kör eder ya beat 5'i keser.
- **Kaynak tekilleştirmesi:** `source` başına en iyi skor tutulur ve bu **`top_k`
  kesilmeden ÖNCE** uygulanır — sonra yapılırsa ikizler gerçek emsallerin yerini
  çalar. Uygulama: Qdrant'a `limit=top_k * _DEDUP_OVERSAMPLE` (4) ile sorulur,
  dedup Python'da yapılır, sonra `top_k`'ya kırpılır. (Dışlamanın Qdrant'ta
  yapılmasıyla aynı gerekçe: kırpma her zaman en son.)
- Payload indeksi: `equipment_ids`, `zone_id` (keyword), `occurred_at` (range).

### 6.3 Yerel istemci kilidi (B7)

`memory.py` modül düzeyinde bir `threading.Lock`; **yalnız yerel** istemci
işlemlerini sarar (uzak istemcide sunucu hallediyor). `_ensure_collection`,
`embed_episode`'un `upsert`'ü ve `search_timeline`'ın `query_points`'i kapsanır.

---

## §7. Aşama 5 — görünürlük (B6)

**Dosyalar:** `gozcu/memory.py`, `gozcu/models.py`, `gozcu/agents/risk.py`,
`gozcu/agents/supervisor.py`, `gozcu/ui/feed.py`, `gozcu/ui/view.py`,
`gozcu/ui/server.py`, `gozcu/ui/session.py`, `gozcu/ui/web/js/sse.js`

- `search_timeline` **skorlu** döner: `list[Precedent]`, yeni model
  (`episode: Episode`, `score: float`). İki tüketici güncellenir: `risk.py` ve
  `supervisor.py`.
- `RiskAssessment`'a `precedents: list[Precedent]` alanı. **Yeni tablo ya da
  `build_output` değişikliği GEREKMİYOR** — `Detail` teslim anında depodan
  yeniden kuruluyor, alan `detail.risk_assessments` içinde kendiliğinden teslim
  edilir.
- **Konsol EMSAL kartı:** `feed.intervention_card` içine, `CARD_WHY` satırından
  sonra yeni bir `_card_row` — köken, tarih, özet, **skor**. Model prozasına
  bağlı değil, deterministik. Emsal yoksa **satır hiç basılmaz** (uydurma emsal
  yok).
- **Yükseltme açılışı:** `Supervisor.escalate`'in `[SİSTEM]` satırına, emsal
  varsa deterministik bir cümle eklenir — jürinin izlediği ilk an orası.
- **Rozet:** `view.badges()`'ın `memory` değeri artık üç değerden biri ve yanına
  **arşiv kayıt sayısı** gelir (`badges(gw, store, archive=None)`;
  `/api/meta` ve `_snapshot` `session.archive_count` geçer). Sıfırsa sıfır
  yazılır — tohumlama sessizce başarısız olduysa tek uyarı budur. Sayı
  tohumlamanın dönüşünden okunur, ayrı bir Qdrant çağrısıyla değil.
  **`archive=None` "sıfır" DEĞİL, "henüz tohumlanmadı"dır** (koşu başlamadan
  `/api/meta`): rozet o durumda sayıyı hiç basmaz. Sıfır ile bilinmeyeni aynı
  şeye çevirmek, bu depoda `blind` itirafının onarmak için var olduğu hatanın
  aynısı olurdu.

### Emsalden karara — prompt kuralları

Emsal bir **gerekçe değil, gerekçenin başlangıcı**. `risk.py` zaten gerçek bir
araç turu koşturuyor (`query_equipment_history`) ve
`fixtures.overdue_maintenance_months` gecikmiş bakımı tarihlerden hesaplıyor.

```
raf çarpması
  → search_timeline         → arşivde IST-04'ün fren kaydı
  → query_equipment_history → "fren bakımı 4 ay gecikmiş"
  → risk yükselir, halt_production_line önerilir
```

- *Arşiv kaydı bir ekipman kimliği taşıyorsa `query_equipment_history` ile o
  ekipmanın geçmişini sorgula.*
- *Aynı ekipman ya da bölge tekrar ediyorsa bu bir **örüntüdür**; hangi kaydı
  gördüğünü yaz.*
- *Arşiv kaydı bu olayla ilgisizse KULLANMA ve ondan söz etme.* ← eşik kalibre
  edilene kadar B4'e karşı **tek** koruma budur.
- *Kamera ekipman kimliği okumaz. Arşivdeki kaydın sahnedeki araca ait olduğunu
  VARSAYMA; "saha doğrulaması gerekir" biçiminde yaz.*

> **Reddedilen tasarım — tekrar önerilmesin.** İlk taslak, canlı epizodun
> `participants` listesiyle arşivi kesiştirip "TEKRAR:" satırı basmayı
> öneriyordu. **Çalışmaz:** canlı `participants` sentezleyici modelinin serbest
> metni ve algı katmanında OCR yok — model videodan "IST-04" okumaz. Canlı liste
> "forklift", "operatör" taşır; arşiv listesi `["IST-04"]`. Kesişim **her zaman
> boş**.

> **Fikstür tutarlılığı — anlatılan örüntü GERÇEK olmalı.** Bugün
> `prior_incidents.json`'da IST-04 **tek** kayıtta geçiyor (OLY-2026-0812).
> "IST-04 iki kez" diyen bir anlatı **uydurma olurdu** — şartname §16, jüriyi
> yanıltıcı bilgi. Doğru hamle üçüncü bir olay uydurmak değil:
> `gozcu/fixtures/equipment.json`'da IST-04 için `incident_id: null` taşıyan
> bağlanmamış bir arıza kaydı duruyor (2026-04-19, *"Fren pedalı sertleşti;
> bakım talebi açıldı, iş emri kapanmadı"*, `status: open`, `severity: medium`,
> `reported_by: PRS-005`). **O kayıt `prior_incidents.json`'a gerçek bir olay
> olarak terfi ettirilir** ve `equipment.json`'daki `incident_id` ona bağlanır —
> iki fikstür dosyası birbirinden ayrışmasın.

---

## §8. Aşama 6 — kısa süreli hafıza

**Yeni dosya:** `gozcu/recall.py`

`RunMemory`: pencere başına bir satır — `ts`, tek cümlelik an, katılımcılar,
yönlendirici kararı, `severity`. Sınır **hiyerarşik**: son N pencere tam detay +
`severity == "olay"` olan **her** pencere kalıcı. Olay asla düşmez, rutin
pencereler kayar. (Uzun-video literatüründeki "hafıza bankası" deseninin metin
karşılığı; özellik seviyesinde yapılamaz çünkü ağ geçidine base64 mp4 gidip
metin dönüyor.)

`DecisionLoop`'a enjekte edilir — mevcut geri çağrı desenine uyar, modül ajansız
test edilebilir kalır.

### Bağlanma noktaları

**8.1 — Yorumlayıcı.** `interpreter._message()` içine `ÖNCEKİ PENCERELER` bloğu.
Asıl kazanç bu: bugün `_context(window)` yalnız o pencerenin sinyallerini yazıyor.

> **Blokta `severity` etiketi YAZILMAZ.** `severity`, epizot açılışının tek kapısı
> (`DecisionLoop._may_open`). Geçmiş derecelendirmeleri görürse model kendini
> doğrulayan bir döngüye girer ("olay, olay → olay"). Blok **ne görüldüğünü**
> taşır, **nasıl derecelendirildiğini** değil. Değerler (`rutin`/`dikkat`/`olay`)
> `RunMemory`'de tutulur ama render edilmez. Başlık: *"bağlam — bu klibin kanıtı
> DEĞİL"*.

Maliyet ölçüldü: dört satırlık blok 301 karakter ≈ 120 token; görü çağrısı bugün
~8.285 token → **+%1,5**. `SCHEMA_MAX_TOKENS` **çıktı** tavanı değişmez.

`config.py`'a iki anahtar: `RECALL_WINDOW_N` (`GOZCU_RECALL_WINDOW_N`,
varsayılan 4 — ölçülen 301 karakterlik blok bu sayıdan geliyor) ve
`RECALL_VISION` (`GOZCU_RECALL_VISION`, `"0"` ise kapalı). Kapalıyken
`_message()` bloğu hiç basmaz; `RunMemory` yine dolar ve 8.2–8.4 çalışmaya
devam eder — anahtar yalnız görü çağrısını kapsar, çünkü ölçülen tek bedel
orada.

**8.2 — Yönlendirici.** Son 3 pencerenin kararı `route`'a geçer. Ölçüldü:
`_route_accepts_energy` iki **veya daha çok** konumsal parametre sayıyor;
**üçüncü parametre bu tespiti bozmuyor** — eski tek argümanlı sahte
yönlendiriciler yeşil kalıyor.

**8.3 — Sentezleyici.** `_digest()` bugün yalnız **açık** epizodun özetini başa
koyuyor (`DEVAM EDEN OLAY:`). Aynı koşuda daha önce **kapanmış** epizotlar da
eklenir — bugün epizot kapanınca öncesi tamamen unutuluyor.

**8.4 — Süpervizör geçmişi.** `Supervisor.history` sistem promptu + her tur + her
araç sonucu JSON'u ile **sınırsız** büyüyor. Sistem promptu + son N tur + açık
epizodun sabitlenmiş özeti ile budanır.

> **`_may_open` kapısına DOKUNULMAZ.** Kapanmış epizotlar yalnız digest'i ve risk
> analizini zenginleştirir; açılış kararına girmez.

---

## §9. Aşama 7 — kalibrasyon (EN SON)

**Yeni:** `scripts/calibrate_memory.py` — mevcut script geleneğine uyar.
Fikstürleri gömer ve **üç sorgu ailesi** koşturur:

(a) fikstür konusuna yakın · (b) kasten alakasız ("kantinde yemek kuyruğu
uzadı") · (c) **beat 5'in gerçek diyalog biçimi** ("bu araçla daha önce sorun
oldu mu?").

(c) şart: canlı sorgu, süpervizör modelinin yazdığı `params["query"]` — fikstür
metnine benzeyen bir cümle değil. (c)'yi ölçmeyen bir eşik, onarmak için var
olduğumuz beat'i keser.

> **Neden en son:** eşik epizot **özet metinleri** üzerinden kalibre ediliyor.
> §8.1 yorumlayıcının `description`'ını değiştiriyor → sentezleyicinin
> `summary_tr`'si değişiyor → **aynı arşive karşı kosinüs skorları kayıyor.**

**Arşiv kapsamı.** Arşivdeki kayıtlar fren, hatalı istifleme ve kask; demo
klipleri **forklift devrilmesi**. Kalibre edilmiş bir eşik büyük ihtimalle
**sıfır emsal** döndürür ve beat 5 dürüstçe ama işe yaramaz şekilde "kayıt
bulunamadı" der. §7'deki terfi doğru yön ama tek kayıt yetmeyebilir. **Üçüncü
bir olay UYDURULMAZ** (şartname §16); kalibrasyondan çıkan skorlar düşükse bu
bir bulgu olarak karar günlüğüne yazılır ve kapsam genişletmesi ayrı bir ürün
sahibi kararıdır.

Çıkan sayılar `config.py`'a ve `docs/05-decisions/decision-log.md`'ye yazılır.

---

## §10. Bozulma davranışı — değişmeyen sözleşme

Kural aynı: **hiçbir kesinti bir koşuyu düşürmez.**

| Arıza | Davranış |
|---|---|
| Gömme kademesi bozuk | `load_history` 0 döner, rozet "arşiv: 0", analist "(kayıt yok)" okur, koşu sürer |
| Qdrant erişilemez | `search_timeline` `[]`, `embed_episode` `False`; istisna yok |
| Eşik altında tek emsal | Emsal listesi boş, EMSAL kartı çizilmez — uydurma emsal yok |
| `source` üretilemiyor | Süreç başına önek; çakışma yok, yalnız tekrar koşuda çoğalma |
| Eski şemalı Qdrant noktası | Sıfırlamayla kalkar; kalırsa alanlar varsayılana düşer |
| **Sentez yedeğe düştü** | Süpürme o epizodu **gömmez** (`summary_source == "fallback"`) — arşiv o koşudan boş çıkar |
| **Genişletilmiş yol çöktü** | Süpürme hiç koşmaz; koşu geçerli çıktı verir ama arşive hiçbir şey yazılmaz |
| Tohumlama `join(timeout)`'u aştı | Boru hattı yine başlar; arşiv o koşuda eksik olabilir, rozet sayıyı gösterir |
| Anahtarsız + path yok | Süreç içi Qdrant; rozet `yerel bellek` yazar — kalıcılık **yok** ve bunu söyler |

---

## §11. Test planı — 1026 testin içinden

**Güncellenecek** (davranış bilerek değişiyor; iddia hâlâ anlamlı):

| Test | Neden |
|---|---|
| `test_memory.py` `…reports_true_when_a_vector_is_stored` | `[p.id for p in stored] == [7]` → UUID beklemeli; `payload["episode_id"] == 7` eklenmeli |
| `test_memory.py` `…same_episode_twice_replaces_the_point` | Aynı gerekçe; tekilliği UUID üzerinden iddia et |
| `test_memory.py` `…excludes_the_originating_episode` | `exclude` artık `(source, episode.id)` çifti |
| `test_memory.py` `…keeps_every_episode_when_no_exclusion` | Aynı |
| `test_memory.py` `memory_backend…` (2 test) | Artık üç değer |
| `test_risk.py` `…consults_the_archive_and_excludes…` | `search.call_args.kwargs["exclude_id"]` → yeni imza |
| `test_supervisor.py` `…reachable_as_a_tool` | Dönüş tipi `list[Precedent]` |
| `test_kpi.py:305` `…no_episode_in_the_store_carries_an_epoch_timestamp` | `load_history` sonrası `store.episodes()` BOŞ; iddia **korunur ama taşınır** — yükleyicinin kurduğu `Episode`'lara karşı sınanır. Epoch kuralı gerçek bir alan kuralı, silinmez |
| `test_fixtures.py:53` `…fault_log_and_the_archive_tell_the_same_ist04_story` | Terfi (§7) sonrası **iddia aynen geçer** (yeni olay `2026-04-19 <= 2026-08-12`, özeti IST-04'ü adıyla anıyor); yalnız "bağlanmamış arıza kaydı" yorumu bayatlar ve güncellenir |

**Silinecek** (iddia ettikleri mekanizma ortadan kalkıyor):

| Test | Neden |
|---|---|
| `test_memory.py` `…store_handle_is_accepted_by_the_legacy_callers` | `store.embeddings()` defteri ölüyor |
| `test_fixtures.py` arşiv tohumlama testleri (4) | `load_history` artık depoya yazmıyor. **Yerine yeni testler 5-6** |
| `test_store.py` `save_embedding`/`embeddings` testleri | Tablo ölüyor |

### Yeni testler

1. `point_id` `(source, id)` için kararlı; farklı `source`, aynı `id` → farklı nokta
2. Aynı epizodu iki kez gömmek tek nokta bırakır
3. `video_key` dosya adından bağımsız; farklı içerik farklı anahtar
4. **Koşu sonunda AÇIK kalan epizot gömülür** ← B2'nin regresyonu
5. `load_history` sonrası `store.episodes()` **BOŞ** ve `events[]` hayalet satır taşımıyor
6. Kör koşuda fikstürler varken bile `perception.blind` itirafı üretiliyor
7. `catch_up` sonrası doğan epizot, önceki epizodun noktasını **ezmiyor**
8. `exclude` verilen epizot — **açık epizotta da** — sonuçta yok
9. Eşik altındaki aday süzülür; eşik `None` iken süzme yok
10. Aynı `source`'lu emsal listede bir kez görünür (dedup, `top_k`'dan önce)
11. `search_timeline` skor taşır; iki tüketici de yeni tipi okur
12. `RiskAssessment.precedents` teslim JSON'unun `detail`'inde görünür
13. `run_pipeline(archive=False)` hiçbir nokta yazmaz (süpürme **ve** `_on_close`)
14. Eski payload (`source` yok) okunabilir
15. Emsal yokken EMSAL bloğu **hiç** basılmaz
16. Kimliksiz epizot gömülmez (guard yerinde)
17. Anahtarsız modda tohumlama ve arama **aynı tutamağı** kullanıyor
18. Yerel istemciye eş zamanlı yazma+okuma sonuç kaybettirmiyor (B7 regresyonu)
19. `actions_taken` epizodun zaman penceresindeki aksiyonlardan doluyor
20. `RunMemory` sınırı: rutin pencereler kayar, `"olay"` pencereleri kalır
21. Yorumlayıcı bloğu derecelendirme SIZDIRMIYOR: `severity="olay"` taşıyan
    kayıtlardan kurulmuş bir `RunMemory`'nin render'ı, `SEVERITY_LEVELS`'in üç
    değerinden hiçbirini içermez. **İddia kayıt metinlerinden değil render
    fonksiyonundan okunur:** kayıtların `moment` metinleri o üç kelimeyi
    içermeyecek şekilde seçilir (yoksa test kendi verisini yakalar), ve blokta
    `severity` alanı için AYRI bir sütun/etiket olmadığı da iddia edilir
22. `memory_backend()` path verildiğinde `"local-disk"`; `BADGE_LABELS` üç değeri de biliyor
23. `Session` `source` taşır ve `Supervisor`'a geçirir
24. Rozet arşiv sayısını taşır; tohumlama 0 dönerse 0 yazılır

---

## §12. Doğrulama — bitti demeden önce

```bash
uv run pytest tests/ -q                       # 1026 taban; sapma açıklanmalı
GOZCU_MEMORY_RESET=1 uv run --env-file .env python scripts/reset_memory.py
uv run --env-file .env python scripts/calibrate_memory.py
uv run --env-file .env python app.py
```

1. **Sıfırlama + kalibrasyon.** Koleksiyon düşürülür, fikstürler yeniden
   tohumlanır, eşikler `config.py`'a yazılır.
2. **Beat 5, canlı.** Klip koşarken operatör *"bu araçla daha önce sorun oldu mu?"*
   yazar. Beklenen: `search_timeline` çağrılır, **gerçek kayıt** döner, süpervizör
   açık olaya kendiliğinden döner.
3. **Emsalli karar zinciri.** Beklenen: analist arşivdeki IST-04 kaydını görür,
   `query_equipment_history` çağırır, gecikmiş bakımı gerekçeye koyar, EMSAL kartı
   **skorla** çizilir, `detail.risk_assessments[].precedents` dolu.
4. **ETA sorusu.** *"Geçen sefer ekip kaç dakikada gelmişti?"* — cevap
   `actions_taken`'dan gelir, uydurma değil.
5. **Teslim JSON'u temiz.** `events[]` yalnız bu videonun anlarını taşır; hayalet
   `00:00` satırı yok; `risk` bu videonun gerçek riski.
6. **İkinci video.** Aynı Qdrant örneğine ikinci klip koşulur. Beklenen: ikinci
   koşunun emsalleri **birinci koşunun olayını** içerir, birincinin noktası hâlâ
   arşivdedir.
7. **Prova dayanıklılığı.** Aynı klip ikinci kez koşulur. Beklenen: aynı
   `source`'lu emsaller örüntü sayılmaz, listede bir kez görünür, hiçbir "tekrar
   eden olay" iddiası doğmaz.
8. **Kısa süreli hafıza, önce/sonra.** §8.1 **k04 VE k05** üzerinde canlı
   ölçülmeden birleştirilmez — k05 projenin aşırı-uyum kontrol klibi. Ölçülecek:
   epizot açılış anı, `events[]` an sayısı, koşu süresi, uydurma var mı.

Her aşama sonunda `docs/05-decisions/decision-log.md`'ye önce/sonra ölçümü;
`docs/tasks/` altındaki görev dosyası ve `docs/tasks/README.md` durum tablosu
güncellenir.

---

## §13. Kapsam dışı (bilerek)

- **Hafıza KPI'ı** (R@1, emsal isabet oranı) — ayrı görev.
- **`RootCauseReport`'a emsal alanı** — strict şema maliyeti.
- **Operatör düzeltmelerinin gömülmesi** — ayrı tasarım yüzeyi.
- **Video içi anların (beat) ayrı gömülmesi** — süpervizör bu soruları depodan
  cevaplıyor; ikinci arama yolu YAGNI.
- **`rerank`** — organizasyon ölçtü, zararlı buldu (R@1 0,95 → 0,55).
- **Niceleme / ColBERT / kelime bazlı hibrit** — sırasıyla: 1000 epizot = 4 MB
  (kazanç yok); ağ geçidi yalnız yoğun vektör veriyor; hibrit **mevcut isimsiz
  koleksiyona sonradan eklenemiyor** (`ValueError: Not existing vector name` —
  `_ensure_collection` koleksiyonu yalnız *yoksa* kurduğu için sessizce ölü
  kalır). Hibrit istenirse **açık bir migration script'i** ile yapılmalı.
- **Video OCR / gerçek ekipman kimliği okuma** — belirsizlik dürüstçe taşınıyor.
- **`archived` tesisatının sökülmesi** (`ui/session.py`, `run.py:399`) — arşiv
  depoya girmediği için artık imkânsız bir durumu koruyor; çalışıyor ve zarar
  vermiyor, sökülmesi ayrı bir temizlik görevi.
- **Dördüncü bir arşiv olayı uydurmak** — şartname §16 (jüriyi yanıltıcı bilgi).
