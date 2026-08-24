# EVREN çıkarım servisi — saha notları

Organizasyonun yarışma için açtığı model servisi. Bu dosya iki kaynağı
birleştiriyor: resmî dokümantasyonun on iki sayfası ve **24 Ağustos 2026'da
kendi anahtarımızla yaptığımız canlı ölçümler.** Ölçülen her satırın yanında
ne zaman ve nasıl doğrulandığı yazıyor; doğrulanmamış hiçbir şey burada
kesinmiş gibi anlatılmıyor.

**Dokümantasyon:** <https://evren-teknofest.ssyz.org.tr> ·
**Takım:** `team37`

## 1. Adresler

| Adres | Ne için |
|---|---|
| `https://evren-llmapi.ssyz.org.tr/v1` | **Model çıkarım API'si.** OpenAI uyumlu. Bütün model çağrıları buraya. |
| `https://evren-vektor.ssyz.org.tr` | Qdrant 1.19.0 — takım başına **izole örnek**, ağ geçidinden geçmiyor. |
| `https://evren-chat.ssyz.org.tr` | Tarayıcı sohbet arayüzü; entegrasyon için gerekli değil. |

`evren-teknofest.ssyz.org.tr` **dokümantasyon sitesidir, gateway değil.**
`/v1/models` oraya sorulursa 404 döner.

Kimlik doğrulama takıma e-postayla verilen bearer token ile. e-Devlet, platform
hesabı ve SSO **geçerli değil**. Anahtarsız istek 401 alır; anonim erişim yok.
Anahtar `.env` içinde `GOZCU_GATEWAY_API_KEY` olarak duruyor ve **repoya
girmiyor**.

## 2. En tehlikeli davranış: bilinmeyen model adı sessizce yönlendiriliyor

> Bilinmeyen bir model adı gönderildiğinde sistem **404 dönmüyor**, isteği
> sessizce `llm-fast` hedefine yönlendiriyor.

Bunun bizim için anlamı somut: 24 Ağustos'a kadar `config.py`'daki yedi takma
ad **tahmindi ve hepsi yanlıştı** (`Qwen3-8B`, `Qwen3-VL-30B-A3B`, …). Gerçek
gateway'e bağlansaydık hiçbir hata almayacaktık — görü çağrıları bir **metin
modeline** gidecek, sistem "çalışacak" ve çıktı sessizce çöp olacaktı.

Görev 00'ın uyarısı ("bir harf hatası sessiz 400 demek") fazla iyimserdi:
400 en azından gürültü çıkarır. Sessiz yönlendirme çıkarmaz.

**Sonuç:** model adları yalnız `gozcu/config.py`'da yaşıyor (CLAUDE.md kuralı)
ve o kural sayesinde düzeltme tek dosyalık bir düzenleme oldu.

## 3. On model

Ölçümler organizasyonun kendi ölçümleri; `[canlı]` işaretliler bizim
doğruladıklarımız.

| Alias | Kullanım | Ölçülen dayanak | Bağlam |
|---|---|---|---|
| `llm-fast` | Belge okuma, sınıflandırma, JSON, araç çağırma | medyan 0,91 s | 262.144 |
| `llm-large` | Bilgi ağırlıklı; tek çağrıda video + özet + JSON | TR-MMLU %79,6 | 262.144 |
| `vlm` | Ayrılmış video analizi | 180 s / 720p → 25,0 s | 262.144 |
| `router` | Ajan içi hafif yönlendirme | 8 B | 40.960 |
| `guard` | İçerik güvenliği sınıflandırması | 4 B | 32.768 |
| `bge-m3-embed` | Birincil getirici | R@1 0,95 · **dim 1024** `[canlı]` | 8.192 |
| `embed` | İlk üçte kesin yakalama | R@3 1,00 · **dim 2560** `[canlı]` | 32.768 |
| `bge-m3-sparse` | Sözcüksel eşleşme | R@1 0,65 tek başına | 8.192 |
| `bge-m3-colbert` | Geç etkileşim skorlaması | çıktı `[N, 1024]` | 8.192 |
| `rerank` | Yeniden sıralama — **önerilmiyor** | R@1 0,95 → **0,55** | 32.768 |

`bge-m3-sparse` ve `bge-m3-colbert` yalnız `/pooling/<alias>` ucundan
alınıyor; `/v1/embeddings` üzerinde **501** dönüyor.

Bütün ağırlıklar BF16, kuantizasyon yok. Sekiz H200, tek tahsis.

## 4. Video yolu — `vlm`

`vlm` = `Qwen/Qwen3-VL-32B-Instruct`. Video örnekleme **2,0 fps, en fazla 520
kare**, süre tavanı **260 s**, kodlayıcı piksel bütçesi 140 MP.

### `vlm` görüntü kabul etmiyor — ve bu bir arıza değil

```json
{"error": {"message": "At most 0 image(s) may be provided in one request.", "code": 400}}
```

Model görüntü yeteneğine sahip; **bu kurulum kodlayıcı piksel bütçesinin
tamamını video çözünürlüğüne ayırdığı için görüntü kapasitesi bilinçli olarak
sıfır.** Yani sınırlama modelin değil, servisin.

**Görüntü göndermek isteyen `llm-fast` veya `llm-large` kullanır — ikisi de
istek başına en fazla İKİ görüntü kabul eder.** İkisi de doğal olarak çok
modlu.

### İstek biçimi

```python
{"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}}
```

Satır içi base64 — çekilebilir URL değil. (Bu, "veri yerelde kalsın" öncülüyle
de tutarlı: URL isteyen bir gateway görüntüyü almak için dışarı çıkardı.)

### Canlı ölçümümüz `[canlı, 24 Ağu]`

Gerçek forklift devrilme klibinden kesilmiş **10 saniyelik** pencere
(`ffmpeg -t 10 -vf scale=1280:-2 -c:v libx264`):

| | |
|---|---|
| Klip | 431 KB · base64 561 KB |
| Süre | **11,4 s** |
| Token | 8.285 |
| Çıktı | Doğru Türkçe analiz; **kareler arası değişimi** okuyor ("hafif dalgalanma", "sallanıyor", "dengesizlik"), pencereden izleyenleri fark ediyor, iş güvenliği hükmü veriyor |

Bu, üç durağan karenin veremeyeceği bir şey: devrilme bir **hareket** olayı ve
model zaman içindeki değişimi anlatıyor.

### Maliyet ve parçalama

- Kısa klip önerilir: 60 s ≈ 18 s, 180 s ≈ 25 s. Uzun klip ek bilgi
  vermiyor, yalnız maliyeti artırıyor — geçiş noktası ötesi zaten küçültülüyor.
- **Ön ek önbelleği (prefix caching) 4,8× hızlanma sağlıyor:** aynı videoya
  ardışık sorgular 17,8 s → 4,7 → 4,1 → 3,7 s.
- Uzun içerik **parçalara bölünerek** gönderilmeli. Bizim 10 saniyelik
  pencerelerimiz zaten tam olarak bu.

## 5. Yapılandırılmış çıktı ve araç çağırma

**Strict JSON şeması destekleniyor** `[canlı]` —
`response_format={"type": "json_schema", …, "strict": True}`.

İki şey ölçüldü ve ikisi de önemli:

1. **Sertleştirilmiş şemamız kabul edildi** ve geçerli enum değerleriyle JSON
   döndü.
2. **Ham (sertleştirilmemiş) şema da kabul edildi** — yani `maxLength` /
   `minimum` bir 400 üretmiyor. Ama **backend onları uygulamıyor da:**
   `rationale` alanı 200 karakter sınırına rağmen çok daha uzun geldi ve
   pydantic doğrulaması patladı.

> **Sonuç: doğrulamadan önce kesme (sanitise-before-validate) zorunlu.**
> Şemadaki uzunluk sınırı bir temenni; tek gerçek koruma Python tarafındaki
> kesme. Bu, kod tabanında zaten uygulanan kural — canlı olarak doğrulandı.

**Araç çağırma çalışıyor** `[canlı]`: kendi `TOOL_SCHEMAS`'ımız değiştirilmeden
kabul edildi, `llm-fast` ilk denemede `query_equipment_history` aracını doğru
argümanla çağırdı. Dokümana göre `llm-fast` ile `llm-large` arasında araç
çağırma ve JSON üretiminde **ölçülebilir fark yok**.

## 6. `guard` bir sınıflandırıcı — talimat takip etmiyor

`[canlı, 24 Ağu]` Gerçek çıktı biçimi:

```
Safety: Safe
Categories: None
```
```
Safety: Unsafe
Categories: Violent
```

Türkçe `uygun`/`uygunsuz` **dönmüyor**. Görev 13'ün ilk hâli
`"uygunsuz" in content` diye bakıyordu; canlı olarak doğrulandı ki o kontrol
**`Safety: Unsafe` için de False dönüyor** — yani guard gerçekten uygunsuz
içeriği de temiz sayıp geçirecekti. Sevk edilen `parse_verdict` iki biçimi de
doğru okuyor.

Not: gerçek bir iş kazası anlatısı (`istif aracı devrildi, sağlık ekibi
çağrıldı`) **`Safe` döndü** — yani teslim taramasının yanlış pozitifle raporu
işaretlemesi endişesi bu örnekte gerçekleşmedi.

## 7. Sınırlar, zaman aşımı, kapasite

| | |
|---|---|
| İstek zaman aşımı | **1800 s, her katmanda aynı.** OpenAI istemcisinin 600 s varsayılanı bağlantıyı modelden önce keser; istek sunucuda işlenmeye devam eder ama sonuç alınamaz. |
| İstek gövdesi | 256 MB |
| Kota / hız sınırı | **Yok.** Anahtarımızda `max_parallel_requests: null` `[canlı]` |
| Kapasite | Video yolunda ~6,4 tam uzunlukta istek/dakika, **bütün takımlar ortak** |
| Kuyruk | Beklemek normal; arıza değil. Tüm takımlar aynı anda 3 dk'lık klip gönderse kuyruk ~7 dk'da boşalır |
| Port | Yalnız TCP 443, TLS 1.2/1.3 |
| Akış | SSE destekli, yanıt arabelleklemesi kapalı |
| Kullanım | `GET /key/info` `[canlı]` |

## 8. Vektör veritabanı

Qdrant 1.19.0, **takım başına izole örnek** (paylaşımlı örnekte ayrılmış alan
değil), ayrı yoldan erişiliyor.

Karar günlüğündeki *"API'den bir video kodlayıcıya erişimimiz yok ve olmayan
bir şeyi iddia etmiyoruz"* gerekçesi hâlâ geçerli, ama *"vektör DB yok"*
öncülü **artık doğru değil.** SQLite + numpy kosinüs çözümümüz çalışıyor ve
bir vardiya birkaç yüz epizot demek — geçiş zorunluluk değil, tercih.

## 9. Bunun Gözcü'ye maliyeti

Ayrı bir değerlendirme notu olarak tutuluyor; özet:

| Konu | Durum |
|---|---|
| `config.py` takma adları + base URL + 1800 s zaman aşımı | ✅ düzeltildi |
| Görev 04 — üç base64 **kare** gönderiyor | ❌ **yeniden yazılmalı**: `vlm` görüntüyü reddediyor, video istiyor |
| Görev 08 — `rerank` çağrısı | ⚠️ organizasyon önermiyor (R@1 0,95 → 0,55) |
| Görev 13 — `parse_verdict` | ✅ gerçek çıktı biçimini doğru okuyor `[canlı]` |
| Görev 06 — `rationale` kesme | ✅ canlı olarak gerekli olduğu doğrulandı |
| Gateway sertleştirmesi | ✅ kabul ediliyor; kesme zorunluluğu doğrulandı |
| Ön ek önbelleği (4,8×) | 🔎 değerlendirilmedi — pencere başına ayrı klip mi, tek video + çok soru mu |
| Qdrant | 🔎 isteğe bağlı; mevcut çözüm çalışıyor |

## 10. Yeniden üretilebilirlik

Bütün ağırlıklar BF16, kuantizasyon yok; KV önbelleği `auto` (fp8 kapalı).
Video budama (`--video-pruning-*`), `expandable_segments`, FlashInfer
örnekleyici ve DeepGEMM **bilinçli olarak kapalı**. Raporda modelin
kuantize edilmediğinin belirtilmesi öneriliyor — kuantize bir model farklı
bir model sayılmalı.
