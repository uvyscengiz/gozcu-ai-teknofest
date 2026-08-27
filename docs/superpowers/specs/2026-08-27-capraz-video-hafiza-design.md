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
- **Ekrandaki KPI sayısı şişer:** `ui/view.py:399` `"episodes": len(store.episodes())`
  basıyor — jüri üç fikstürü bu koşunun tespiti sanır.
- **`turkish_output_rate` yapay olarak yükselir:** `benchmark/kpi.py:296`
  epizot özetlerini korpusa katıyor ve fikstür özetleri her zaman Türkçe.

Altı yol da aynı kökten: **arşiv koşunun deposuna girmemeli.**

---

## §0b. Kaynak belgeden ölçülmüş sapmalar — 27 Ağustos

Kaynak belge 26 Ağustos'un deposuna karşı yazıldı. O günden bu yana üç şey
değişti; **belgenin satır referansları bu üç noktada geçersiz** ve plan onları
düzeltilmiş hâliyle uygular.

| Kaynak belge | 27 Ağustos'ta ölçülen |
|---|---|
| B9: iki anahtar da sıfır karakter | **İkisi de dolu ve gerçek** — `GOZCU_GATEWAY_API_KEY` (`sk-evren-t…`, 48 hane), `GOZCU_QDRANT_API_KEY` (`qdr-team37…`, 43 hane) |
| Bağlanma noktaları `gozcu/ui/console.py:{91,535,537,552,681,708}` | **`console.py` 27 Ağustos'ta emekliye ayrıldı** (`d651abd`, Görev 21). Yerine `gozcu/ui/server.py` (`post_run`, `_work`, `/api/status`) ve `gozcu/ui/session.py` (`Session.__init__`, `archived`) |
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
2. **`GOZCU_QDRANT_PATH` DÜŞTÜ ve `memory_backend()` iki değerli kalıyor.**
   Kaynak belgedeki gerekçe ("anahtar yok, gerçek çalışma modu yerel mod")
   artık yanlış, ve yerine konan gerekçe kör incelemede çürüdü — ayrıntı
   §0c'nin sonundaki turda. Kalıcılık artık gerçek `team37`'de kanıtlanıyor.
3. **B7 kilidi KALIYOR.** Uzak istemcide eşzamanlılığı sunucu hallediyor, ama
   1026 testin tamamı ve anahtarsız her koşu yerel istemcide koşuyor; Aşama **2**
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

### Kör inceleme turu — 27 Ağustos

Bu spec, yazan konuşmayı görmemiş bağımsız bir inceleyiciden geçti. Turun
değiştirdiği yedi şey aşağıda; hepsi kodda doğrulandı ve belgeye işlendi.

1. **`GOZCU_QDRANT_PATH` ÇIKARILDI.** Gerekçesi kendi kendini yiyordu: anahtar
   doluyken `build_client()` uzak dala giriyor ve path'e **hiç ulaşılmıyor** —
   yani "prova koşusu team37'yi kirletmesin" gerekçesi, prova prosedürü
   anahtarı elle boşaltmadıkça gerçekleşmiyor. Dahası sessiz bir düşüş yüzeyi
   açıyordu: yerel istemciler tutamak başına açılıyor
   ([memory.py:107](../../../gozcu/memory.py)), `Session` başına yeni bir
   `Store` var ([session.py:58](../../../gozcu/ui/session.py)), yani **ikinci
   koşu** aynı dizine ikinci istemci açar, `RuntimeError` alır, `memory.py`'nin
   geniş `except`'i onu yutar ve rozet yine "yerel disk" der. Tam olarak §12'nin
   6. doğrulama adımının koştuğu mod. `memory_backend()` **iki değerli kalıyor**
   ve bu daha dürüst: `"local"` artık istisnasız "kalıcılık yok" demek.
2. **Sıra düzeltildi (A1).** Eski sıra tohumlamayı kararlı kimlikten ÖNCE
   açıyordu: fikstür noktaları `id = 0,1,2`, canlı epizot rowid'leri `1,2,3`
   ([store.py:192](../../../gozcu/store.py)) → fikstürler koşunun kendi
   epizotları tarafından ezilir, hem de artık gerçekten paylaşılan `team37`'de.
   Kimlik işi tohumlamanın çağrılmasından ÖNCEYE alındı.
3. **Dışlama basitleşti (B3).** Nokta kimliği artık `uuid5(source:id)` —
   yani dışlanacak noktanın kimliği çağrı anında **hesaplanabiliyor**. İç içe
   `Filter(must_not=[Filter(must=[...])])` ve ayrı `episode_id` payload anahtarı
   gereksiz; `HasIdCondition([point_id(source, id)])` yetiyor.
4. **Kilit koşulsuzlaştı (B4).** "Yalnız yerel istemciyi sar" koşulu
   hesaplanamıyor: `_client()` doğrudan geçilen bir istemciyi olduğu gibi
   döndürüyor ([memory.py:105](../../../gozcu/memory.py)) ve o dalda yerel mi
   uzak mı olduğu bilinmiyor — testlerin çoğu ve `calibrate_memory.py` tam o
   dalı kullanıyor.
5. **`route`'a üçüncü parametre EKLENMİYOR (B7).** `DecisionLoop` `route`'u iki
   argümanla çağırıyor ([loop.py:479](../../../gozcu/loop.py)); üçüncü konumsal
   parametre hiçbir zaman geçilmez. `RunMemory` `run.py`'deki kapanışla
   yakalanır.
6. **Rozet ucu düzeltildi (B1).** `/api/meta` değil **`/api/status`**
   ([server.py:365](../../../gozcu/ui/server.py)); `get_meta` `view.badges`'i hiç
   çağırmıyor. `view.badges`'in **dört** çağıranı var: `:383`, `:889`, `:1031`,
   `:1053`.
7. **Payload indeksleri çıkarıldı (B2).** Önerilen üç indeksten `zone_id`
   `Episode`'a hiç eklenmiyor, `equipment_ids`/`occurred_at` üzerinde hiçbir
   sorgu filtre kurmuyor. Üç noktalık bir koleksiyonda ölçülebilir kazanç yok.

---

## §1. Mimari karar — tek cümle

> **SQLite (`Store`) koşu kapsamlı KALIR. Qdrant, uzun süreli hafızanın TEK
> adresidir.** Arşiv, koşunun deposuna hiç girmez.

Kalıcı SQLite denendi ve **reddedildi**: videolar arası `open_episode` sızması
(koşu 2, koşu 1'in epizodunu açık görüyor → `_resolve('open_episode')` →
`'update_episode'`, yani video B video A'nın olayına kaynaşıyor), defter
birikmesi ve §0'daki altı çıktı arızası. Üstelik amacı da karşılamıyordu:
anahtarsız modda `build_client()` zaten süreç içi bir Qdrant döndürüyor.

Bu tek karar B1'in yan hasarını, çıktı sözleşmesi arızalarını ve `open_episode`
sızmasını **birlikte** çözüyor.

### Sıra — bağımlılık gerekçesiyle

| Aşama | İş | Neden bu sırada |
|---|---|---|
| **0** | Koleksiyon sıfırlama script'i (`scripts/reset_memory.py`) — **yazılır, KOŞTURULMAZ** | Aracın hazır olması. Sıfırlamanın kendisi §12'nin 1. adımında, Aşama 1–5 indikten SONRA koşar: Aşama 1'den önce koşturulan bir sıfırlama koleksiyona taze **tamsayı** kimlikli noktalar koyar ve hiçbir işe yaramaz |
| **1** | **Kimlik ve köken:** `video_key` · `point_id` · yeni `Episode` alanları · `source` zinciri | Her şeyin altında. Yarısı bağlanırsa filtre sessizce boş küme döner |
| **2** | **Arşiv yalnız Qdrant'ta:** `load_history` depoya yazmayı bırakır, ölü defter silinir, tohumlama `post_run`'dan çağrılır | Çıktı sözleşmesi arızalarını (B1'in yan hasarı) açılmadan kapatır. **Aşama 1'den SONRA** — bkz. aşağıdaki tuzak |
| **3** | Koşu sonu gömme süpürmesi + `archive` bayrağı | **B2'nin onarımı.** Aşama 1'in kararlı kimliğine muhtaç |
| **4** | Dışlama · eşik iskeleti (`None`) · kaynak dedup · kilit | Aşama 1'in `source`'una muhtaç |
| **5** | Skorlu dönüş · `precedents` · EMSAL kartı · rozet | Aşama 4'ün skoruna muhtaç |
| **6** | Kısa süreli hafıza (`recall.py` + dört bağlanma noktası) | **Tamamen bağımsız** — 0–5 ile paralel koşabilir. Yalnız Aşama 7'den önce bitmeli |
| **7** | Eşik kalibrasyonu + arşiv kapsamı | **En son:** §8.1 (Aşama 6'nın yorumlayıcı bağlanması) özet metinlerini değiştiriyor, skorlar kayıyor |

**Sırayı bozarsan sessizce kırılanlar:**

- **2'yi 1'den önce yaparsan canlı arşivi bozarsın.** Tohumlama fikstürlere
  `id = 0,1,2` veriyor; nokta kimliği hâlâ ham `episode.id` ise
  ([memory.py:199](../../../gozcu/memory.py)) ve canlı epizotlar SQLite rowid
  `1,2,3` alıyorsa ([store.py:192](../../../gozcu/store.py)), o koşu fikstür
  noktalarının **üstüne yazar** — hem de artık gerçekten paylaşılan `team37`'de.
- **3'ü 1'den önce yaparsan** çakışan kimlikle yazarsın (aynı gerekçe).
- **7'yi 6'dan önce yaparsan** eşiği iki kez kalibre edersin.
- **2'yi atlayıp 3'ü yaparsan** canlı olay gömülür ama arşiv boş kalır — yarım
  çözüm, demo yine boş.

**Gerçekten paralel olanlar:** Aşama 6 (0–5'in hiçbirine dokunmuyor) ve Aşama 5'in
EMSAL kartı/rozet kalemleri (skor `query_points` yanıtında bugün de var —
[memory.py:250](../../../gozcu/memory.py); Aşama 4'ün getirdiği yalnız eşik ve
dedup).

---

## §2. Aşama 0 — koleksiyon sıfırlama

`scripts/reset_memory.py` — mevcut script geleneği (env değişkeni, argparse yok,
`REPO_ROOT = Path(__file__).resolve().parent.parent`, sonunda tek satır özet;
bkz. `scripts/gen-litellm-config.py`).

Yaptığı: koleksiyonun nokta sayısını yazar; `GOZCU_MEMORY_RESET=1` **yoksa
hiçbir şey silmeden çıkar**; varsa `delete_collection` çağırır ve `load_history`
ile yeniden tohumlar. Gerekçe §0c'de: paylaşılan bir takım kaynağını düşüren bir
dosya `scripts/` altında yanlışlıkla çalıştırılabilecek durumda bırakılmaz.

**`memory_backend()` DEĞİŞMİYOR** — iki değer (`"qdrant" | "local"`) ve
`view.BADGE_LABELS` olduğu gibi kalıyor. Kör inceleme turu üç değerli hâli
çıkardı (§0c/1).

## §3. Aşama 1 — kimlik ve köken

**Dosyalar:** `gozcu/memory.py`, `gozcu/models.py`, `gozcu/run.py`,
`gozcu/agents/synthesizer.py`, `gozcu/ui/session.py`, `gozcu/ui/server.py`

### 3.1 Kaynak parmak izi

```python
def video_key(path) -> str:
    """Videonun kimliği: ilk 1 MB + dosya boyutu üzerinden sha256 (16 hane).

    Dosya okunamazsa süreç başına sabit bir önek döner; istisna ATMAZ.
    """

def point_id(source: str | None, episode_id: int) -> str:
    """Noktanın kimliği. `Episode` DEĞİL iki alan alıyor: dışlama filtresi
    (§6.1) elinde epizot yokken de aynı kimliği hesaplayabilmeli."""
    return str(uuid.uuid5(_NAMESPACE, f"{source}:{episode_id}"))
```

**YAZMA TARAFI — bu satır olmadan aşağıdakilerin hiçbiri işe yaramaz.**
`embed_episode`'un bugünkü `PointStruct(id=episode.id, …)` satırı
([memory.py:199](../../../gozcu/memory.py))
`PointStruct(id=point_id(episode.source, episode.id), …)` olur.

> Bunu atlamak **istisna atmaz**: noktalar eski tamsayı kimliğiyle yazılmaya
> devam eder, §6.1'in `HasIdCondition`'ı hesapladığı UUID'yi hiçbir zaman
> bulamaz, dışlama sessizce hiçbir şey elemez ve epizot kendi emsali olarak
> listenin başına oturur — yani B3'ün ve §6.1'in onarmak için var olduğu
> davranışın ta kendisi. Kimliğin okuma ve yazma tarafı **tek fonksiyondan**
> gelmek zorunda.

Ad **tek biçim: `point_id`** (alt çizgisiz), `memory.py`'de modül düzeyinde ve
dışa açık — `search_timeline` ile `embed_episode` onu paylaşıyor, testler de
doğrudan çağırıyor (yeni test 1).

- **Dosya adı değil içerik hash'i.** Yükleme ya da kopyalanmış bir `video.mp4`
  iki farklı videoyu aynı isimle getirir; çakışma iki alakasız olayı **tek
  noktada birleştirir** — çoğaltmadan kötü.
- **İkinci parça `episode.id`, `start_ts` DEĞİL.** `DecisionLoop.catch_up`
  ertelenmiş pencereleri sonradan işliyor ve **daha erken** `start_ts`'li
  epizotlar doğurabiliyor; zamana dayalı kimlik tam o anda kimlikleri birbirine
  kaydırırdı.
- Ölçüldü: eski kimlikle 2 epizot → **1 nokta**; `uuid5` ile → **2 nokta**.
- **`video_key` OKUNAMAYAN dosyada istisna atmaz.** `tests/test_run.py` var
  olmayan bir `"video.mp4"` yolunu **29 kez** geçiyor (31 satırda); atan bir `video_key`
  o testlerin hepsini çökertir. Okunamazsa süreç başına sabit bir önek döner
  (`f"proc-{os.getpid()}"`) — §10'un "`source` üretilemiyor" satırının kod
  tarafındaki karşılığı. Bu dal imza bloğunda yazılı olmalı, yoksa uygulayan
  kişi §10'a bakmadan çıplak `sha256(open(path))` yazar.

### 3.2 Yeni `Episode` alanları

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

### 3.3 `source` zincirinin bağlanması

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
> boş küme döndürürdü (§3.3'ün baş tehdidi). Maliyet dosyanın ilk 1 MB'ının
> ikinci kez okunması; ölçülebilir değil.

`Supervisor` de kurulumda `source` alır (aynı filtreyi uygulayabilmek için).
**Tek üretim kurulum noktası `ui/session.py::Session.__init__`.** `post_run`
`Session()`'ı bugün yüklemeden ÖNCE kuruyor; `video_key` dosyanın diske tam
yazılmasını gerektirdiği için **`Session()` kurulumu yükleme döngüsünden SONRAYA
alınır** (aradaki tek kullanım `session.output_dir` ataması ve o da sonrasında).
`_run_lock` bütün blok boyunca tutulduğu için yarış penceresi açılmaz.

> **Yarısı bağlanırsa filtre sessizce boş küme döndürür.** Bu adım bitmeden
> Aşama 4'e geçilmez.

### 3.4 `actions_taken` doldurma

`ActionRecord`'da `episode_id` **yok**; eşleme video zamanıyla yapılır: gömme
anında `store.actions()` içinden `episode.start_ts <= a.ts <= episode.end_ts`
penceresine düşenler alınır, `tool_name` ve `result`'ın anahtar alanları
(`eta_minutes`, `team`, `zone_id`, `record_no`) yazılır.

Ölçüldü: `dispatch_medical` gerçekten `{'team': 'revir-1', 'eta_minutes': 4}`
döndürüyor, ama bu satır koşu kapsamlı SQLite'ta yaşıyor ve video bitince yok
oluyor. Bu alan olmadan *"geçen sefer ambulans kaç dakikada geldi"* **yapısal
olarak** cevaplanamaz.

---

## §4. Aşama 2 — arşiv yalnız Qdrant'ta yaşar

**Dosya:** `gozcu/fixtures/loader.py`

> **Bu aşama §3'ün kararlı kimliğine muhtaç.** §3 inmeden buradaki tohumlama
> çağrısı canlı arşivi bozar — bkz. §1'in tuzak listesi.

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

### Fikstür alan eşlemesi — atlanırsa üç kayıttan ikisi sessizce düşer

`prior_incidents.json`'ın `episode` alt sözlüğü **yalnız** `start_ts` · `end_ts`
· `phase` · `preliminary_risk` · `participants` · `summary_tr` taşıyor;
`occurred_at` · `equipment_id` · `zone_id` · `incident_id` bir üst düzeyde,
epizodun **dışında**. Bugünkü yükleyici `Episode(**fields, state="closed")`
yapıyor ([loader.py:114](../../../gozcu/fixtures/loader.py)) — yani yeni alanlar
eklendiğinde de boş kalırlar. Yükleyici bunları **açıkça** eşler:

```python
episode = Episode(**fields, state="closed",
                  source=f"arşiv:{record['incident_id']}",
                  occurred_at=record["occurred_at"],
                  equipment_ids=([record["equipment_id"]]
                                 if record.get("equipment_id") else []))
episode.id = index          # 0, 1, 2, … — sıra numarası
```

> **Neden bloklayıcı.** Eşleme yapılmazsa üç arşiv epizodu da `source=None` ile
> gömülür ve §6.2'nin kaynak tekilleştirmesi ("`source` başına en iyi skor")
> üçünü **tek kovaya** koyar — emsal listesine yalnız biri girer. §12.3'ün
> "analist arşivdeki IST-04 kaydını görür" adımı ve beat 5, hiçbir hata
> vermeden kesilir. Bu boşluk dedup'tan önce zararsızdı; dedup ile birlikte
> aktif bir sessiz arıza hâline geliyor.
>
> `source` öneki `"arşiv:"` bilerek: canlı `video_key` 16 haneli hex, arşiv
> kaydı okunur bir olay kimliği — EMSAL kartında (§7) köken sütunu ikisini
> ayırt edebilmeli. Ayrıca `exclude` çifti hiçbir zaman bir arşiv kaydına denk
> gelmiyor: canlı epizotların kimlik uzayı ayrı.

**Ölen kod:** `memory._write_ledger`, `Store.save_embedding`, `Store.embeddings()`,
`episode_embedding` tablosu ve yükleyicinin tekrarsızlık kontrolü — kararlı
kimlik `upsert`'ü zaten idempotent yapıyor (Aşama 1, §3). Görev 08'in tamamlanma
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

`benchmark/run.py:141`'deki `seeded = {episode.id for episode in store.episodes()}`
**zaten bugün de boş küme** dönüyor: benchmark `load_history`'yi hiç çağırmıyor ve
`_store_factory` her klipte dosyayı silip taze bir `Store` kuruyor
([benchmark/run.py:143](../../../benchmark/run.py)). Bu değişiklik onu ölü hâle
GETİRMİYOR, ölü olduğunu **kesinleştiriyor** — `kpi.detections`'ın
`seeded_episode_ids` parametresi bundan sonra hiçbir koşulda dolamaz.
**Silinmez, belgelenir.**

`run_pipeline`'a `archive: bool = True` bayrağı eklenir; benchmark `archive=False`
geçer. Bayrak **İKİ yola birden** ulaşmalı: koşu sonu süpürmesine (§5) ve
`_on_close`'un koşu ortasındaki gömmesine. Yalnız süpürmeyi kapatmak, kapanan her
epizodun yine `team37`'ye yazılması demektir.

> Parametre `run_pipeline` imzasının **sonuna** eklenir — bu dosyanın yerleşik
> geleneği (`motion_for` aynı gerekçeyle sona konmuş): araya sokulan bir parametre
> konumsal çağrıları sessizce kaydırır.

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
- **`source` parametresi bir yedek, ana yol değil.** Epizot `source`'unu §3.3'te
  doğuşunda alıyor; süpürme yalnız `episode.source is None` olan epizotlara onu
  geri yazar (sentez dalının atlandığı ya da eski bir satırın okunduğu durum).
  Zaten damgalı bir epizodun `source`'u **ezilmez** — ezilirse `catch_up` ile
  gelen bir epizot yanlış videoya bağlanabilirdi.
- **`archive=False` iken süpürme hiç koşmaz** ve `_on_close` de gömmez; ikisi
  aynı bayrağı okur (§4, benchmark).

---

## §6. Aşama 4 — arama kalitesi

**Dosya:** `gozcu/memory.py`

### 6.1 Dışlamanın filtreye taşınması

`search_timeline`'ın imzası `exclude_id: int | None` yerine
`exclude: tuple[str | None, int] | None` alır — çift, tek sayı değil. Filtre
bugünkü biçimini KORUR, yalnız kimlik hesaplanır:

```python
must_not=[HasIdCondition(has_id=[point_id(*exclude)])]
```

> **Neden iç içe `FieldCondition` filtresi DEĞİL.** İlk taslak payload'a ayrı bir
> `episode_id` anahtarı yazıp `must_not=[Filter(must=[episode_id==X, source==Y])]`
> öneriyordu. Gereksiz: nokta kimliği artık `uuid5(source:id)` ve dışlanacak
> noktanın kimliği **çağrı anında hesaplanabiliyor** — `point_id`'nin `Episode`
> değil iki alan alması (§3.1) tam olarak bunun için. Ayrı payload anahtarını,
> `_episode()`'te onu yeniden süzmeyi ve iç içe filtreyi birlikte ortadan
> kaldırıyor.
>
> Ölçülmüş tuzak yine kayıtta: düz `must_not=[episode_id == X]` **iki noktanın
> ikisini birden** eledi — farklı videoların epizotları da 1 numarayı taşıyor.
> Kimlik tabanlı dışlama o tuzağa hiç girmiyor, çünkü UUID zaten `source`'u
> içeriyor.

`source` payload'a `model_dump()` üzerinden kendiliğinden giriyor (§3.2); dedup
onu okuyor.

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
- **Payload indeksi KURULMUYOR.** İlk taslak `equipment_ids` · `zone_id` ·
  `occurred_at` öneriyordu; üçü de gereksiz çıktı: `zone_id` `Episode`'a hiç
  eklenmiyor (§3.2), diğer ikisi üzerinde hiçbir sorgu filtre kurmuyor (dedup ve
  eşik Python tarafında), ve tek gerçek filtre nokta kimliği üzerinden çalışıyor
  (§6.1) — o zaten indeksli. Üç noktalık bir koleksiyonda ölçülebilir kazanç yok.

### 6.3 Yerel istemci kilidi (B7)

`memory.py` modül düzeyinde bir `threading.Lock`; `_ensure_collection`,
`embed_episode`'un `upsert`'ü ve `search_timeline`'ın `query_points`'i **koşulsuz**
sarılır.

> **"Yalnız yerel istemciyi sar" DENENDİ ve uygulanamaz çıktı.** Koşul
> hesaplanamıyor: `_client()` doğrudan geçilen bir istemciyi olduğu gibi
> döndürüyor ([memory.py:105](../../../gozcu/memory.py)) ve o dalda istemcinin
> yerel mi uzak mı olduğuna dair hiçbir bilgi yok — testlerin çoğu ve §9'un
> `calibrate_memory.py`'si tam o dalı kullanıyor. `not QDRANT_API_KEY` predikatı
> da yanlış olurdu: anahtar doluyken doğrudan geçilen yerel bir istemci kilitsiz
> kalır, yani B7 regresyonu açık kalırdı. Koşulsuz kilidin ölçülebilir bir
> maliyeti yok — `upsert`/`query_points` zaten seri.

---

## §7. Aşama 5 — görünürlük (B6)

**Dosyalar:** `gozcu/memory.py`, `gozcu/models.py`, `gozcu/agents/risk.py`,
`gozcu/agents/supervisor.py`, `gozcu/ui/feed.py`, `gozcu/ui/view.py`,
`gozcu/ui/server.py`, `gozcu/ui/session.py`, `gozcu/ui/web/js/sse.js`

- `search_timeline` **skorlu** döner: `list[Precedent]`, yeni model
  (`episode: Episode`, `score: float`). İki tüketici güncellenir: `risk.py` ve
  `supervisor.py`.
- **Süpervizörün araç sonucu tam epizodu TAŞIMAZ.** Bugün
  `{"results": [e.model_dump() …]}` yazıyor ([supervisor.py:341](../../../gozcu/agents/supervisor.py));
  `Episode` artık `beats` + `actions_taken` da taşıdığı için bu yük doğrudan
  `Supervisor.history`'ye giriyor ve §8.4'ün budama hedefiyle **ters yönde**
  çalışırdı. Araç sonucu bir **projeksiyon** olur: `summary_tr` · `occurred_at`
  · `source` · `equipment_ids` · **`participants`** · `actions_taken` ·
  `score`. `beats` süpervizöre hiçbir şey söylemiyor ve düşüyor.
  > **`participants` projeksiyonda KALMAK zorunda.** İlk taslak onu düşürüyordu.
  > Arşiv kayıtlarında ekipman kimliğini bugün gerçekten taşıyan alan o:
  > `prior_incidents.json` → `participants: ["IST-04", "PRS-001"]`.
  > `equipment_ids` yeni eklenen bir alan ve yalnız yükleyicinin eşlemesi (§4)
  > onu dolduruyor; `participants` düşerse beat 5'te süpervizöre giden emsalde
  > ekipman kimliği **hiç** bulunmayabilir ve §7'nin bütün emsal→araç zinciri
  > kopar.
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
- **Rozet:** `view.badges()`'ın `memory` değerinin yanına **arşiv kayıt sayısı**
  gelir (`badges(gw, store, archive=None)`;
  **`/api/status`** ([server.py:365](../../../gozcu/ui/server.py)) ve `_snapshot`
  (`:889`) `session.archive_count` geçer — `/api/meta` DEĞİL: `get_meta`
  (`:279`) `view.badges`'i hiç çağırmıyor, yalnız `badge_labels` döndürüyor.
  `view.badges`'in dört çağıranı var (`:383`, `:889`, `:1031`, `:1053`) ve yeni
  parametre varsayılanlı olduğu için son ikisi değişmeden geçer.
  **`get_status`'un GÖVDESİ de değişir:** o uç `memory`'yi `badges()`'ten değil
  **doğrudan** `memory_backend()`'ten okuyor (`server.py:382`) ve `view.badges`'i
  yalnız `["gateway"]` için çağırıyor (`:383`) — yani `session.archive_count`
  oraya elle bir anahtar olarak konmadıkça tele hiç çıkmaz. Sıfırsa sıfır
  yazılır — tohumlama sessizce başarısız olduysa tek uyarı budur. Sayı
  tohumlamanın dönüşünden okunur, ayrı bir Qdrant çağrısıyla değil.
  **`archive=None` "sıfır" DEĞİL, "henüz tohumlanmadı"dır** (koşu başlamadan
  `/api/status`): rozet o durumda sayıyı hiç basmaz. Sıfır ile bilinmeyeni aynı
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

**8.2 — Yönlendirici.** Son 3 pencerenin kararı `route`'a geçer — **ama
`DecisionLoop`'a DOKUNULMADAN.**

> **Reddedilen tasarım.** İlk taslak `route`'a üçüncü bir konumsal parametre
> eklemeyi öneriyordu ve gerekçesi olarak `_route_accepts_energy`'nin `>= 2`
> saydığını gösteriyordu. Gerekçe doğru ama **ilgisiz**: o kontrol eski tek
> argümanlı sahte yönlendiricileri koruyor, üçüncü argümanı taşımıyor.
> `DecisionLoop` `route`'u iki argümanla çağırıyor
> ([loop.py:479](../../../gozcu/loop.py)) — eklenen üçüncü parametre hiçbir
> zaman geçilmez, varsayılansız olursa `TypeError` verir.

Doğru yol `run.py:419-421`'deki kapanışın `RunMemory`'yi **yakalaması**:
`route=lambda window, energy=None: route(gw, window, …, recall=run_memory)`.
`DecisionLoop`, `loop.py` ve `_route_accepts_energy` değişmez.

> **Sıralama kısıtı — atlanırsa blok bir pencere geriden gelir.** `RunMemory` o
> pencerenin satırını, `route` o pencere için çağrılmadan **önce** almış olmalı.
> Kayıt yorumlayıcının çıktısından doğduğu için akış zaten "önceki pencereler"
> anlamını taşıyor; kritik olan aynı pencereyi iki kez yazmamak.

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
| Eski şemalı Qdrant noktası | Sıfırlamayla kalkar (Aşama 1–5 indikten SONRA koşulur, bkz. §1); kalırsa alanlar varsayılana düşer |
| **Sentez yedeğe düştü** | Süpürme o epizodu **gömmez** (`summary_source == "fallback"`) — arşiv o koşudan boş çıkar |
| **Genişletilmiş yol çöktü** | Süpürme hiç koşmaz; koşu geçerli çıktı verir ama arşive hiçbir şey yazılmaz |
| Tohumlama `join(timeout)`'u aştı | Boru hattı yine başlar; arşiv o koşuda eksik olabilir, rozet sayıyı gösterir |
| Anahtarsız koşu | Süreç içi Qdrant; rozet `yerel` yazar — kalıcılık **yok** ve bunu söyler |
| **Aynı video ikinci kez, daha AZ epizotla** | `uuid5(source:id)` yalnız aynı `id`'yi ezer; birinci koşunun fazla noktaları arşivde kalır. Emsal listesi doğru kalır (dedup, §6.2) ama arşiv büyür ve §9'un kalibrasyonu kirlenmiş kümede yapılır — kalibrasyondan ÖNCE sıfırlama (§2) bu yüzden prosedürün parçası |

---

## §11. Test planı — 1026 testin içinden

> **§12'nin "1026 taban; sapma açıklanmalı" kapısı ancak bu liste TAM ise
> anlamlı.** Kör inceleme turu, ilk taslağın yedi kırılan testi saymadığını
> ölçtü; hepsi aşağıda.

**Güncellenecek** (davranış bilerek değişiyor; iddia hâlâ anlamlı):

| Test | Neden |
|---|---|
| `test_memory.py:114` `…reports_true_when_a_vector_is_stored` | `[p.id for p in stored] == [7]` → UUID beklemeli |
| `test_memory.py:143` `…same_episode_twice_replaces_the_point` | Tekilliği UUID üzerinden iddia et |
| `test_memory.py:247` `…excludes_the_originating_episode` | `exclude` artık `(source, id)` çifti |
| `test_memory.py:261` `…keeps_every_episode_when_no_exclusion` | Aynı |
| `test_memory.py:330,336` `memory_backend…` | **DEĞİŞMİYOR** — `memory_backend()` iki değerli kaldı (§0c/1) |
| `test_memory.py:64` `…ranks_the_semantically_closest_episode_first` | `result[0].summary_tr` → `result[0].episode.summary_tr` |
| `test_memory.py:271` `…returns_episodes_rebuilt_from_the_payload` | `isinstance(found, Episode)` → `Precedent`; docstring'i de ("çağıranlar değişmedi") artık yanlış |
| `test_memory.py:305` `…drops_fallback_sourced_episodes_from_earlier_runs` | `[e.id for e in result]` → `[p.episode.id …]` |
| `test_risk.py:75` `_archive_patch` | `return_value` `Episode` listesi; `risk.py` `p.episode.summary_tr` okumaya başlayınca **`AttributeError` ve `assess_risk` istisna atar** (etrafında `try` yok) — yardımcı `Precedent` döndürmeli |
| `test_risk.py:104-116` `…consults_the_archive_and_excludes…` | `search.call_args.kwargs["exclude_id"]` → yeni imza |
| `test_supervisor.py:505` `…reachable_as_a_tool` | Araç sonucu artık projeksiyon (§7, emsal projeksiyonu) |
| `test_view.py:139` `…healthy_run_shows_all_three_badges` | `assert result == {…}` **tam sözlük eşitliği**; `badges()`'e `archive` anahtarı eklemek kırar |
| ~~`test_server.py:345` `…turkish_badge_labels`~~ | **DEĞİŞMİYOR.** Yalnız `/api/meta` okuyor (`:354`) ve `BADGE_LABELS` değişmediği için geçer. `/api/status` gövdesini okuyan testler (`:243`, `:999`, `:1009`, `:1014`) tam küme değil tek tek anahtar iddia ediyor — `archive` eklemek hiçbirini kırmıyor |
| `test_kpi.py:305` `…no_episode_in_the_store_carries_an_epoch_timestamp` | `load_history` sonrası `store.episodes()` BOŞ; iddia **korunur ama taşınır** — yükleyicinin kurduğu `Episode`'lara karşı sınanır. Epoch kuralı gerçek bir alan kuralı, silinmez |
| `test_fixtures.py:53` `…fault_log_and_the_archive_tell_the_same_ist04_story` | Terfi (§7) sonrası **iddia aynen geçer**; yalnız "bağlanmamış arıza kaydı" yorumu bayatlar |
| `test_fixtures.py:173` `…loading_twice_does_not_duplicate_the_archive` | **Silinmiyor, iddiası dönüyor:** tekrarsızlık kontrolü kalkınca ikinci `load_history` `0` değil `3` döner. Sayı doğrudan `session.archive_count` üzerinden rozete gidiyor (§7) — çoğalmama iddiası artık Qdrant nokta sayısı üzerinden kurulur |

**Silinecek** (iddia ettikleri mekanizma ortadan kalkıyor):

| Test | Neden |
|---|---|
| `test_memory.py:290` `…store_handle_is_accepted_by_the_legacy_callers` | `store.embeddings()` defteri ölüyor |
| `test_store.py:54` `…embedding_roundtrips_and_replaces_by_episode_id` | `episode_embedding` tablosu ölüyor |
| `test_fixtures.py:156` `…loaded_closed_and_embedded` | `store.embeddings()` mekanizması; yerine yeni test 5 |
| `test_fixtures.py:191` `…second_call_embeds_what_the_degraded_tier_missed` | İki kademeli onarım deseni `store.embeddings()`'e dayanıyordu; `upsert` idempotent |

**Silinmeyecek — ALAN KURALI taşıyorlar** (deponun ölçütü: mekanizma → sil,
alan kuralı → yeniden kur). Kör inceleme turu ikisini silme listesinden geri aldı:

| Test | Taşıdığı kural |
|---|---|
| `test_fixtures.py:181` `…degraded_embedding_tier_is_reported_as_zero_not_as_success` | **"Sessiz düşüş yasak."** `assert n == 0` — kademe bozuksa yükleyici yalan söylemez. `store.embeddings()` yerine Qdrant nokta sayısı üzerinden yeniden kurulur |
| `test_fixtures.py:166` `…prior_incident_involves_the_same_vehicle_as_the_demo` | **"Demo aracının arşivde bir emsali olmak zorunda."** §7'nin bütün emsal zinciri (IST-04 → `query_equipment_history` → gecikmiş bakım) buna dayanıyor; terfi bunu daha da kritik yapıyor. Fikstür `Episode`'ları üzerinden yeniden kurulur |

### Yeni testler

1. `point_id` `(source, id)` için kararlı; farklı `source`, aynı `id` → farklı nokta
2. Aynı epizodu iki kez gömmek tek nokta bırakır
3. `video_key` dosya adından bağımsız; farklı içerik farklı anahtar; **okunamayan dosyada istisna atmaz**
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
    kayıtlardan kurulmuş bir `RunMemory`'nin render'ı `SEVERITY_LEVELS`'in üç
    değerinden hiçbirini içermez. Kayıtların `moment` metinleri o üç kelimeyi
    içermeyecek şekilde seçilir — yoksa test kendi verisini yakalar
22. **`POST /api/run` tohumlamayı ÇAĞIRIYOR** ← **B1'in regresyonu.** `patch("gozcu.ui.server.load_history")` ile: çağrıldı mı, `session.store` ile mi çağrıldı, dönüşü `session.archive_count`'a mı yazıldı. **Bu test olmadan B1 onarılıp kilitlenmemiş olur** — thread bir gün silinse 1026 test yeşil kalır ve arıza aynen geri gelir
23. `Session` `source` taşır ve `Supervisor`'a geçirir
24. Rozet arşiv sayısını taşır; tohumlama 0 dönerse 0, hiç koşmadıysa **anahtar yok**
25. **Emsal bloğu uydurma üretmiyor** (§8.1'in yapısal koruması): `RunMemory`'de
    geçen ama mevcut pencerede geçmeyen bir varlık için `_message()` çıktısı o
    varlığı **kanıt** dilinde sunmaz ve blok başlığı (*"bağlam — bu klibin kanıtı
    DEĞİL"*) render edilir. Blok görü çağrısına giriyor, oradan doğan `beats`
    epizoda ve teslim edilen `events[]`'e akıyor
    (`synthesizer.py:295` → `report.py:181`) — tek koruma prompt metni olamaz;
    bu depo tam olarak bu tür bir uydurmayı bir kez ağır ödedi
    ([models.py:149](../../../gozcu/models.py))

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
   epizot açılış anı, `events[]` an sayısı, koşu süresi ve **uydurma, göz kararı
   değil karşılaştırmayla**: aynı klibin §8.1 ÖNCESİ ve SONRASI `events[]`
   listeleri yan yana konur; sonrasındaki her yeni satır için "bu an klipte
   gerçekten var mı" sorusu tek tek cevaplanır. Öncesinde olmayan bir olay
   iddiası varsa §8.1 birleştirilmez.

**Güncellenecek dokümanlar** (kod değişikliğiyle aynı commit'te):
`.env.example` — dört yeni anahtar (`GOZCU_QDRANT_SCORE_THRESHOLD_RISK`,
`…_DIALOGUE`, `GOZCU_RECALL_WINDOW_N`, `GOZCU_RECALL_VISION`) dosyanın kendi
geleneğine uygun biçimde, gerekçesiyle; `docs/tasks/README.md:108-112` (hafıza
kurulum notu); `gozcu/fixtures/README.md:62` (`load_history` artık depoya
yazmıyor); `README.md` (tohumlamanın nereden çağrıldığı).

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
- **`archived` tesisatının sökülmesi** (`ui/session.py:86`, `run.py:399`) —
  **zaten bugün de ölü**: `Session.archived` taze bir `Store` üzerinde okuyor
  (`session.py:58`), yani her zaman boş küme. Bu değişiklik onu ölü hâle
  getirmiyor, ölü olduğunu kesinleştiriyor. Çalışıyor ve zarar vermiyor;
  sökülmesi ayrı bir temizlik görevi.
- **Dördüncü bir arşiv olayı uydurmak** — şartname §16 (jüriyi yanıltıcı bilgi).
