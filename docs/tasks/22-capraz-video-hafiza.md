# Görev 22 — Çapraz video epizodik hafıza + koşu içi kısa süreli hafıza

> ## ✅ TAMAMLANDI — 27 Ağustos 2026, `a20b931`…`35538d9`
>
> **Hafıza yazılmıştı ve testleri geçiyordu; üretim yolundan hiç
> çağrılmıyordu.** Bu görev iki hafızayı da canlı koşuya bağladı: videolar
> arası **epizodik arşiv** (Qdrant, `team37`) ve koşu içi **kısa süreli
> bağlam** (`gozcu/recall.py`). Arşiv artık koşunun SQLite deposuna hiç
> girmiyor; nokta kimliği koşu içi rowid yerine `uuid5(source:episode_id)`
> ve `source` videonun içerik hash'i.
>
> Depo genelinde **1099 test** geçiyor, kırmızı yok.
>
> **Bitmedi sayılan üç kalem var ve hepsi ölçüm borcu**
> ([açık borç](#açık-borç--bitmiş-değil)): **eşik kalibrasyonu koşulmadı**
> (yani alaka süzmesi YOK, B4 açık), **§12.8'in k04/k05 canlı ölçümü
> yapılmadı** (spec bunu §8.1'in birleştirme ön koşulu sayıyor) ve
> **§12'nin sekiz doğrulama adımı koşulmadı**.

**Spec:** [2026-08-27-capraz-video-hafiza-design.md](../superpowers/specs/2026-08-27-capraz-video-hafiza-design.md)
(iki kör inceleme turu) ·
**Plan:** [2026-08-27-capraz-video-hafiza.md](../superpowers/plans/2026-08-27-capraz-video-hafiza.md)
(18 görev) · **Bağımlılık:** [08](08-hafiza.md), [14](14-nobetci.md),
[17](17-cikti-sozlesmesi.md)

## Bağlam — dokuz arıza, koşturularak ölçülmüş

Hafızanın kodu [Görev 08](08-hafiza.md)'de yazılmıştı ve testleri yeşildi.
Canlı koşuda ölçüldüğünde dokuz arıza çıktı; hepsi test edilmemiş bir
**bağlanma noktasında** duruyordu, kodun kendisinde değil.

| # | Arıza | Nasıl ölçüldü |
|---|---|---|
| **B1** | `load_history()` hiçbir yerden çağrılmıyor — yalnız testlerden | Üretim yolunda tek çağrı yok; arşiv her koşuda boş |
| **B2** | Kapanmayan epizot arşive **hiç** girmiyor | Gömmenin tek yolu `_on_close` ve o da yalnız `close_episode` dalında; gerçek demo klibinde epizot videonun sonuna kadar açık kalıyor |
| **B3** | Koşular birbirini eziyor | Nokta kimliği koşu içi SQLite rowid; iki videodan iki epizot → **1 nokta** |
| **B4** | Alaka eşiği yok | Alakasız sorgu ("kantinde yemek kuyruğu uzadı") üç kaydın **üçünü de** döndürdü — 0,743 / 0,557 / 0,371 |
| **B5** | Emsalin kökeni yok | `Episode` hangi videodan/tarihten geldiğini taşımıyor |
| **B6** | Hafıza hiçbir ekranda görünmüyor | Emsal yalnız prompt'a giriyor; jüri prompt görmez |
| **B7** | Yerel Qdrant eşzamanlı erişimde güvenli değil | Vektör şekil çakışması; `search_timeline`'ın geniş `except`'i yutuyor → 400 sorgunun 6'sı sessizce boş dönüyor |
| **B8** | Aynı videonun ikinci koşusu emsal listesini ikizliyor | Aynı `source`'tan iki nokta |

Buna koşu içi körlük eklendi: görü katmanı her pencereye **sıfırdan**
bakıyordu — bir önceki pencerede ne olduğunu bilmiyordu, yönlendirici de
sentezleyici de süpervizör de bilmiyordu.

## Mimari karar

> **SQLite (`Store`) koşu kapsamlı KALIR. Qdrant, uzun süreli hafızanın TEK
> adresidir.** Arşiv, koşunun deposuna hiç girmez.

Kalıcı SQLite denendi ve reddedildi: videolar arası `open_episode` sızması
(ikinci koşu, birincinin epizodunu açık görüyor → video B video A'nın olayına
kaynaşıyor), defter birikmesi ve altı ayrı çıktı sözleşmesi arızası. Gerekçe
ve reddedilen alternatifler [karar günlüğünde](../05-decisions/decision-log.md).

## Ne yapıldı

| Görev | Commit | İş |
|---|---|---|
| 0 | `a20b931` | `scripts/reset_memory.py` — koleksiyon sıfırlama aracı, onaysız hiçbir şey silmiyor |
| 1 + 2 | `dd0fd84` | Nokta kimliği `uuid5(source:episode_id)`; `Episode` köken alanları (`source`, `occurred_at`, `actions_taken`) |
| 3 | `6600aa5` | `source` zinciri — epizot köken damgasını doğuşta alıyor (`video_key` → oturum → sentezleyici) |
| 4 | `7d8046c` | `actions_taken` epizodun zaman penceresindeki saha çağrılarından doluyor |
| 5 | `b1b6084` | Arşiv yalnız Qdrant'ta yaşar; `load_history` depoya yazmayı bıraktı, ölü defter silindi |
| 6 | `d4f93ae` | **B1** — tohumlama üretimden çağrılıyor (`POST /api/run` → `_seed_archive`) |
| 7 + 8 | `8335417` | **B2** — koşu sonu gömme süpürmesi (`_sweep_unembedded`) + `archive` bayrağı |
| 9 | `5f6ce1f` | Skorlu emsal (`Precedent`); dışlama hesaplanan UUID ile, Qdrant tarafında |
| 10 | `66fc77d` | Eşik iskeleti (`None`), kaynak tekilleştirmesi, koşulsuz kilit (**B7**, **B8**) |
| 11 | `13f8447` | **B6** — emsal teslim JSON'unda (`detail.risk_assessments[].precedents`) ve yükseltme cümlesinde |
| 12 | `232c824` | EMSAL kartı ve arşiv rozeti — hafıza ekranda görünüyor |
| 13 | `10841dd` | Fikstür tutarlılığı — IST-04'ün bağlanmamış arıza kaydı arşive terfi etti |
| 14 | `766b32a` | `RunMemory` (`gozcu/recall.py`) — koşu içi kısa süreli hafıza |
| 15 | `af2242b` | Görü çağrısı önceki pencereleri görüyor (`ÖNCEKİ PENCERELER` bloğu) |
| 16 | `35538d9` | Yönlendirici, digest ve süpervizör geçmişi hatırlıyor |
| 17 | bu commit | `scripts/calibrate_memory.py` + dokümanlar |

Aralarda beş doküman düzeltme commit'i var (`d572d50`, `867e025`, `caeafe1`,
`e164829` ve `0715660`); hepsi plandaki kod bloklarında bulunan uygulama
hatalarını ve bir yeniden adlandırmanın bozduğu Türkçe yorumu düzeltiyor.

### Yeni dosyalar

| Dosya | Sorumluluk |
|---|---|
| `gozcu/recall.py` | `RunMemory` — hiyerarşik sınır: son N pencere + her `"olay"` penceresi kalıcı |
| `scripts/reset_memory.py` | Koleksiyonu düşürüp fikstürlerle yeniden tohumlar; `GOZCU_MEMORY_RESET=1` olmadan **hiçbir şey silmez** |
| `scripts/calibrate_memory.py` | Üç sorgu ailesiyle eşik ölçer; hiçbir şey **yazmaz**, sayıları basar |

### Yeni `.env` anahtarları

| Anahtar | Varsayılan | Ne yapıyor |
|---|---|---|
| `GOZCU_QDRANT_SCORE_THRESHOLD_RISK` | boş → `None` | Risk analistinin cümle sorgusu için alaka eşiği |
| `GOZCU_QDRANT_SCORE_THRESHOLD_DIALOGUE` | boş → `None` | Süpervizörün soru sorgusu için alaka eşiği |
| `GOZCU_RECALL_WINDOW_N` | `4` | Kaç pencere tam detayla taşınıyor |
| `GOZCU_RECALL_VISION` | `1` | Bloğun görü çağrısına girip girmediği |

## Açık borç — bitmiş değil

Üçü de **canlı ağ** ya da **yıkıcı bir koleksiyon sıfırlaması** istediği için
uygulama turunda koşturulmadı. Kod tarafı hazır; koşan yok.

1. **Eşik kalibrasyonu koşulmadı — B4 AÇIK.**
   `QDRANT_SCORE_THRESHOLD_RISK` ve `…_DIALOGUE` bugün **`None`**, yani
   **alaka süzmesi yok**: alakasız bir sorgu arşivdeki her kaydı geri
   getirmeye devam ediyor. `0.0` bir yedek değil — kosinüs negatif skor
   üretebilir ve `0.0` negatifleri süzer, yani ölçülmemiş bir eşiktir; bu
   yüzden korumasız hâl bilerek `None`. Tek koruma risk promptundaki "arşiv
   kaydı ilgisizse KULLANMA" satırı ve o bir prompt satırı, bir garanti
   değil. Kapatan adım: planın Görev 17 / Adım 2–3.

   ```bash
   GOZCU_MEMORY_RESET=1 uv run --env-file .env python scripts/reset_memory.py
   uv run --env-file .env python scripts/calibrate_memory.py
   ```

   **Sıfırlama önce koşmak zorunda:** canlı koleksiyonda ölçüldü — üç nokta,
   üçü de `prior_incidents.json` fikstürü, kimlikleri tamsayı ve payload'da
   `source` alanı yok. Yeni kimlik şemasıyla çakışmazlar ama silinmezlerse
   aynı üç fikstür arşivde **iki kez** durur.

2. **§12.8'in k04/k05 canlı ölçümü yapılmadı.** Spec bunu Görev 15'in
   (`ÖNCEKİ PENCERELER` bloğu) **birleştirme ön koşulu** sayıyor: aynı klibin
   blok öncesi ve sonrası `events[]` listeleri yan yana konacak ve
   sonrasındaki her yeni satır için "bu an klipte gerçekten var mı" sorusu
   tek tek cevaplanacaktı. Kod birleşti, ölçüm borcu duruyor — yani bloğun
   teslim edilen `events[]`'e uydurma sokup sokmadığı **bilinmiyor**. Yapısal
   koruma yerinde (blok başlığı bağlamı kanıttan ayırıyor, derecelendirme
   taşınmıyor) ve testi var; eksik olan canlı karşılaştırma.
   Kaçış kapısı: `GOZCU_RECALL_VISION=0` bloğu yalnız görü çağrısından
   çıkarır, diğer üç bağlanma çalışmaya devam eder.

3. **§12'nin sekiz doğrulama adımı koşulmadı.** Beat 5'in canlı sınanması,
   emsalli karar zinciri, ETA sorusu, teslim JSON'unun temizliği, ikinci
   video, prova dayanıklılığı ve kısa süreli hafızanın önce/sonrası.
   Sekizi de gerçek modeller ve gerçek Qdrant istiyor.

> **Arşiv kapsamı — beklenen bir bulgu.** Arşivdeki üç kayıt fren, hatalı
> istifleme ve kask; demo klipleri **forklift devrilmesi**. Kalibre edilmiş
> bir eşik büyük ihtimalle sıfır emsal döndürecek ve beat 5 dürüstçe ama işe
> yaramaz şekilde "kayıt bulunamadı" diyecek. **Dördüncü bir olay
> UYDURULMAZ** (şartname §16); skorlar düşükse bu bir bulgu olarak karar
> günlüğüne yazılır ve kapsam genişletmesi ayrı bir ürün sahibi kararıdır.

## Kabul

- [x] Nokta kimliği `uuid5(source:episode_id)`; farklı `source`, aynı sıra
      numarası → farklı nokta
- [x] `load_history` sonrası `store.episodes()` **boş**; `events[]` hayalet
      `00:00` satırı taşımıyor
- [x] `POST /api/run` tohumlamayı çağırıyor ve dönüşü `session.archive_count`'a
      yazıyor (B1'in regresyon testi)
- [x] Koşu sonunda **açık kalan** epizot gömülüyor (B2'nin regresyon testi)
- [x] `run_pipeline(archive=False)` hiçbir nokta yazmıyor — hem `_on_close`
      hem süpürme yolunda
- [x] Aynı `source`'lu emsal listede bir kez görünüyor; tekilleştirme `top_k`
      kesiminden **önce**
- [x] `source is None` olan noktalar tekilleştirmeye girmiyor
- [x] `RiskAssessment.precedents` teslim JSON'unun `detail`'inde görünüyor
- [x] EMSAL kartı skorla çiziliyor; emsal yoksa satır **hiç** basılmıyor
- [x] Arşiv rozeti: tohumlama 0 dönerse 0, hiç koşmadıysa **anahtar yok**
- [x] `RunMemory` sınırı hiyerarşik: rutin pencereler kayar, `"olay"`
      pencereleri kalır
- [x] Yorumlayıcı bloğu derecelendirme **sızdırmıyor**
- [x] `uv run pytest tests/ -q` → **1099 geçiyor**
- [ ] Eşikler kalibre edildi ve `config.py`'a yazıldı
- [ ] §12.8'in k04 + k05 canlı ölçümü yapıldı
- [ ] §12'nin sekiz doğrulama adımı koşturuldu

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Arşiv koşunun deposuna GİRMEZ.** `load_history` yalnız Qdrant'a gömüyor.
  Onu `Store`'a geri yazan her değişiklik dört şeyi birden bozar: fikstürler
  `00:00` damgasıyla şartnamenin puanlanan `events[]` dizisine girer, `risk`
  yedeği kayar, `perception.blind` itirafı hiç tetiklenmez ve kök neden
  raporu kirlenir. Bu dördü bir kez birlikte oldu.
- **`load_history(gw, store)`'daki `store` bir depo DEĞİL, indeks anahtarı.**
  Anahtarsız modda `build_client()` süreç içi bir Qdrant döndürüyor ve
  istemciler tutamak başına bir `WeakKeyDictionary`'de tutuluyor. Ölçüldü:
  `store_A` ile tohumlayıp `store_B` ile aramak **0 sonuç** veriyor.
  Parametreyi "kullanılmıyor" diye silen bir temizlik tohumlamayı üretimde
  sessizce faydasız hâle getirir.
- **Eşik `None` iken süzme YOK ve bu bir eksiklik olarak taşınıyor.** `0.0`'a
  düşürmek bir onarım değil, ölçülmemiş bir eşik koymaktır: kosinüs negatif
  skor üretebilir. Sayılar yalnız `scripts/calibrate_memory.py`'nin
  koşusundan gelir ve `config.py`'a **hangi koşudan geldikleri yorumla**
  yazılır.
- **Kimliksiz nokta (`source is None`) tek kovaya konmaz.** `None` bir kaynak
  değil, kaynağın yokluğu: bu değişiklikten önce yazılmış her nokta onu
  taşıyor. Hepsini aynı kovaya koymak "aynı videonun ikizi" ile "kökeni
  bilinmeyen üç ayrı olay"ı aynı şeye çevirir ve arşivi tek emsale indirir —
  B8'i onarırken B4'ten beter bir şey yapmış olurduk.
- **Gömme kademesi bozuksa sayı SIFIR ve bu bir yalan değil.** "3 olay
  yüklendi" demek, arama hiçbir şey bulamazken sistemin çalıştığını sanmak
  demektir. Aynı disiplin `scripts/calibrate_memory.py`'de de var: hiçbir
  fikstür gömülemezse script sayı basmaz, hata döner.
- **`archive` bayrağı iki yola BİRDEN ulaşmak zorunda.** `_on_close`'un koşu
  ortasındaki gömmesi ve koşu sonu süpürmesi; yalnız birini kapatmak
  sızıntıyı kapatmaz. Ölçüm koşusu (`benchmark/run.py`) `archive=False`
  geçiyor — benchmark'ın epizotları gerçek bir olayın kaydı değil ve
  paylaşılan `team37` koleksiyonunu kirletirlerdi.
- **`run_pipeline`'ın yeni parametreleri imzanın SONUNA eklenir.** Araya
  sokulan bir parametre konumsal çağrıları sessizce kaydırır;
  `test_new_parameters_are_appended_not_inserted` iki parametrenin sırasını
  birden koruyor.
- **`route`'a üçüncü konumsal parametre EKLENMEDİ.** `DecisionLoop` onu iki
  argümanla çağırıyor; `RunMemory` `run.py`'deki kapanışla yakalanıyor.
  `loop.py`, `_may_open` kapısı ve `_route_accepts_energy` bu işten haberdar
  olmadı ve olmamalı.
- **Kısa süreli hafıza `severity` tutuyor ama RENDER ETMİYOR.** Epizot
  açılışının tek kapısı o; geçmiş derecelendirmeleri gören model kendini
  doğrulayan bir döngüye girer.
- **Yerel Qdrant kilidi KOŞULSUZ.** "Yalnız yerel istemciyi sar" koşulu
  cazip ama yanlış: koşul bir gün yanlış tarafa düşerse B7 regresyonu sessizce
  geri gelir ve geniş `except` onu yutar. Uzak istemcide kilidin ölçülebilir
  bir bedeli yok.
