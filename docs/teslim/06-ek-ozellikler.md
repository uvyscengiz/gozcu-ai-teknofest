
# Bölüm 6 — Eklenen ek özellikler veya senaryolar

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"eklenen ek özellikler veya senaryolar (varsa)"*
kalemidir — şartname §7'nin *"yenilikçilik ve yaratıcılık"* (%10) kalemini
besliyor. Aşağıdakilerin hiçbiri şartnamenin zorunlu tuttuğu bir madde
değil; hepsi kod tabanında gerçekten çalışıyor ve dosya referanslarıyla
gösteriliyor.

---

## 1. Çapraz video epizodik hafıza — Qdrant destekli emsal arama

Şartname yalnız *"video içeriğinin özetlenmesi"*ni istiyor; Gözcü bunun
ötesinde **videolar arası** bir hafıza taşıyor.
[`gozcu/memory/episodic.py`](../../gozcu/memory/episodic.py) her kapanan
epizodu (Türkçe özet + katılımcılar) Qdrant'a gömüyor; risk analisti ve
Nöbetçi kendi anlamsal sorgularıyla (`search_timeline`) *"bu ekipmanla
daha önce bir olay olmuş muydu?"* diye arşive sorabiliyor.

```
    OLAY KAPANDI ──► embed_episode() ──► Qdrant (team37/episodes)
                                              │
    SONRAKİ VİDEO,                            │  search_timeline("query")
    farklı bir olay ────────────────────────►│
                                              ▼
                                   emsal bulunursa Risk Analisti'nin
                                   gerekçesine ve Nöbetçi'nin açılış
                                   cümlesine deterministik olarak girer
```

Üç mühendislik kararı bunu güvenilir kılıyor:

- **Nokta kimliği içerikten türetiliyor** (`point_id(source, episode_id)`,
  video içeriğinin sha256'sı + epizot no), SQLite'ın rowid'inden değil —
  aksi hâlde iki ayrı videonun "1. epizotları" aynı Qdrant noktasında
  çakışırdı.
- **Yedek özetli epizotlar arşive hiç girmiyor** (`embed_episode`,
  `summary_source == "fallback"` kontrolü) — bir iç arıza metni gelecekteki
  bir arama sonucuna "geçmişte olmuş bir olay" diye karışmasın diye.
- **Emsal alaka eşikleri kalibre edildi, tahmin edilmedi**
  (`GOZCU_QDRANT_SCORE_THRESHOLD_RISK=0.54`,
  `GOZCU_QDRANT_SCORE_THRESHOLD_DIALOGUE=0.47`) — canlı `team37`
  koleksiyonuna karşı üç sorgu ailesi (yakın/diyalog/alakasız) ölçülerek
  seçildi; ikisi ayrı çünkü risk analisti arşivi bir **cümleyle**
  sorguluyor, Nöbetçi ise modelin yazdığı bir **soruyla** — soru-cümle
  kosinüsü sistematik olarak cümle-cümle kosinüsünden düşük.

Arşiv koşunun kendi SQLite deposuna hiçbir şey yazmıyor — yalnız Qdrant'ta
yaşıyor; ayrıntı: [04-kurulum-calistirma.md §6](04-kurulum-calistirma.md).

---

## 2. Operatör belgesi RAG'ı — sabit fikstürden gerçek doküman aramasına

Bir başka anlamsal arama, **ayrı bir Qdrant koleksiyonunda**
(`documents`): operatör vardiya listesi, ekipman kartı, prosedür gibi
belgeleri yükleyebiliyor; sistem bunları [MarkItDown](https://github.com/microsoft/markitdown)
ile metne çeviriyor (PDF, DOCX, PPTX, XLSX destekli), gömüyor ve
`search_documents` aracıyla arattırıyor.

**Belgeler ile epizotlar bilerek ayrı koleksiyonda.** `search_timeline`
dönen her noktayı bir `Episode` diye geri kuruyor; bir vardiya talimatı
oraya yazılsaydı ajan onu geçmiş bir **olay** sanırdı. Ayrı koleksiyon bu
karışmayı yapısal olarak imkânsız kılıyor
([`gozcu/core/config.py::QDRANT_DOCUMENT_COLLECTION`](../../gozcu/core/config.py)'nin
notu).

Bu, şartnamenin verdiği ilk tasarımdan (`query_shift_personnel`,
`query_equipment_history` adlı, sabit fikstür verisi döndüren iki mock
araç) bilinçli bir sapma: 26 Ağustos'ta bu iki araç kaldırıldı, yerine
operatörün **gerçekten yüklediği** belgelerde çalışan bir arama zinciri
kondu (bkz. [`gozcu/tools/field_systems.py`](../../gozcu/tools/field_systems.py)'in
modül başı notu). Şartnamenin istediği minimum bir mock fonksiyon
seviyesindeyken, Gözcü burada gerçek bir RAG boru hattı kurdu.

---

## 3. Koşu içi kısa süreli hafıza — pencereler arası bağlam

Görü kademesi her pencereye **sıfırdan** bakıyor: bir klip gidiyor, bir
açıklama dönüyor, sonraki pencere öncekini hiç bilmiyor. 2. dakikadaki bir
dengesizlik 5. dakikadaki devrilmenin bağlamı olamıyordu.
[`gozcu/memory/recall.py::RunMemory`](../../gozcu/memory/recall.py) bunu
kapatıyor: modelsiz, ajansız bir veri yapısı — koşunun kendi geçmişini
tutuyor ve iki katmanlı bir sınırla büyüyor: **son N pencere** tam
detayla + **`severity == "olay"` olan her pencere kalıcı olarak**
(rutin pencereler kayar, olaylar asla düşmez).

Bu blok görü çağrısına ("ÖNCEKİ PENCERELER — bu klibin kanıtı DEĞİL"
başlığıyla, kanıtla karışmasın diye) ve Nöbetçi'nin `query_current_run`
aracına giriyor — operatör *"bu videoda daha önce ne olmuştu?"* diye
sorduğunda cevap buradan geliyor.

---

## 4. Kök neden raporu — şartnamenin istemediği ama jüri için değerli çıktı

Şartnamenin dört anahtarı `summary` · `events` · `risk` · `actions`;
Gözcü kapanan her koşuda beşinci, isteğe bağlı bir belge daha üretiyor:
[`gozcu/agents/reporter.py::generate_root_cause_report`](../../gozcu/agents/reporter.py).
Rapor `detail.root_cause_report` altında teslim ediliyor ve dört kuralla
çerçeveleniyor:

- **Operatör düzeltmesi kazanır.** Operatör bir gözlemi düzelttiyse rapor
  eski değeri açıkça **GEÇERSİZ** işaretler, yeni değeri esas alır.
- **Her sayı ve kimlik kanıta dayanır.** Rapordaki her rakam (ör.
  `open_safety_incident`'in ürettiği kayıt no) aksiyon defterinden geliyor;
  model kaynağını cümle içinde belirtmek zorunda.
- **Kesin hüküm yok.** "Muhtemel kök neden" der, `confidence_limits`
  alanında neyi bilemediğini açıkça yazar — model o alanı boş bırakırsa
  bile bir yer tutucu metin devreye giriyor, rapor kendini mutlak bir hüküm
  gibi sunmasın diye.
- **"Önlenebilirdi" iddiası bir prosedür kimliğine bağlı olmalı.** Aksiyon
  Planlayıcı'nın eşleştirdiği bir prosedür yoksa rapor "önlenebilirdi"
  demiyor, tanımlı bir prosedürün bulunmadığını yazıyor.

---

## 5. Denetim (guard) — çıktı tarafında etik/yanlılık kontrolü

Şartnamenin etik maddesi sistemin *"Türkçe konuşan tüm bireyler için adil,
kapsayıcı ve yanlılıktan arındırılmış"* olmasını istiyor.
[`gozcu/output/guard.py`](../../gozcu/output/guard.py) bunun kod
karşılığı: hem operatöre giden her diyalog cümlesini (`screen_text`), hem
**teslimden hemen önce** jüriye giden paketin tamamını
(`screen_delivery`) bir güvenlik sınıflandırıcısından geçiriyor. İki kural
onu tanımlıyor:

- **Kritik uyarı asla engellenmez.** "Yerde hareketsiz kişi var" mesajını
  yutan bir denetim katmanı, hiç denetim olmamasından kötüdür.
- **Denetim çökerse metin geçer.** Kademe susarsa metin olduğu gibi
  ilerler; bir denetim katmanının sistemin tamamını susturabilmesi kabul
  edilemez.

`guard` kademesindeki model bir **güvenlik sınıflandırıcısı**, talimat
takip eden bir sohbet modeli değil — kendi etiket biçimini
basabiliyor (`Safety: Unsafe` gibi). `parse_verdict()` bu yüzden üç
biçimi birden tanıyor (Türkçe hüküm, sınıflandırıcı etiketi, Türkçe
olumsuzlama — `"uygun değil"`) ve tanımadığı her cevabı `"unknown"`
sayıyor: metni geçirir ama **temiz** demez.

---

## 6. Çok turlu operatör diyaloğu — bağlam yönetimi

Şartname §7'nin *"bağlam yönetimi"* ve *"otonomi ve zeka"* kalemleri
somut kod davranışlarına karşılık geliyor
([`gozcu/agents/supervisor.py`](../../gozcu/agents/supervisor.py)):

- **Geçmiş budaması.** `Supervisor._prune_history()` sistem promptu + son
  açık olayın `[SİSTEM]` satırı + son `SUPERVISOR_HISTORY_TURNS` (8) turu
  koruyor; geri kalanı **görünümden** kırpıyor, deftere yazılan tam kaydı
  değil — konsolun şeffaflık ekranı ile modele giden istek farklı uzunlukta
  olabiliyor.
- **Operatör düzeltmesi risk analizine yayılıyor.** `correct_observation`
  çağrıldığında yalnız bir kayıt eklenmiyor; epizot özeti güncelleniyor ve
  risk **yeniden** biçiliyor (`assess_risk` tekrar koşuyor).
- **Tek bekleyen onay değişmezi.** `pending_approval()` aynı anda yalnız
  bir bekleyen aksiyon garantiliyor — ikinci bir kapılı aksiyon denemesi
  yürütülmeden reddediliyor, yoksa birinci kalıcı olarak görünmez olurdu.
- **Belge bağlamı her turda tazeleniyor.** `_refresh_document_context()`
  operatörün koşu **ortasında** yüklediği bir belgeyi bir sonraki turda
  görebilmesini sağlıyor.

---

## 7. Operatör konsolu — üç görünüm, canlı akış

Şartname bir arayüz şart koşmuyor; Gözcü [`gozcu/ui/`](../../gozcu/ui/)
altında FastAPI + SSE + bağımlılıksız HTML/CSS/JS ile üç görünümlü bir
konsol sunuyor (ayrıntı: [04-kurulum-calistirma.md](04-kurulum-calistirma.md)):

| Görünüm | İçerik |
|---|---|
| Operasyon | Video + kutu katmanı, zaman çizelgesi, olay günlüğü, onay çubuğu |
| Şeffaflık | Devir zinciri (`handoff` defteri), araç çağrı günlüğü, pencere defteri |
| Performans | KPI'lar, karar dağılımı, algı ölçümü |

SSE her zaman **tam durum** taşıyor (kısmi güncelleme yok — bir önceki
Gradio konsolunun 13 yuvalı protokolü eksik bir çıktıyı hatasız yutup
jüriye bayat veri gösteriyordu, bu yüzden 27 Ağustos'ta emekliye ayrıldı).
Ekranda ayrıca bilinçli olarak eklenen bir **kesinti simülasyonu**
düğmesi var (`POST /api/run/{id}/gateway/cut`) — jüri önünde hata işleme
davranışını canlı göstermek için.

---

## 8. Kütüphane ekranı — koşular arası kalıcı kayıt

Koşu deposu (SQLite) varsayılan olarak `:memory:` — koşu bitince her şey
gidiyor. [`gozcu/memory/library.py`](../../gozcu/memory/library.py) bunun
dışında, **diske** yazılan iki ayrı defter tutuyor: operatörün yüklediği
belgeler (`var/library/documents/`) ve her koşunun sonunda yazılan rapor
(`var/library/reports/`). Bu, "daha önce analiz edilenler" listesinin koşu
biter bitmez kaybolmasını önlüyor — şartnamenin istemediği ama demoyu
tekrarlanabilir kılan bir ek katman.

---

## 9. Deterministik protokol eşleştirme — model kanaatinden fazlası

Aksiyon Planlayıcı'nın müdahale önerileri bir modelin serbest kanaati
değil: [`gozcu/fixtures/loader.py::match_protocols`](../../gozcu/fixtures/loader.py)
olay sınıfı + bölge + risk eşiğine göre **deterministik** olarak tesisin
yazılı prosedürlerini süzüyor, model yalnız aralarından seçiyor. Model
susarsa protokolün adımları birebir plana düşüyor (deterministik yedek).
Bunun getirdiği somut kazanım: raportörün *"PRT-B-ÇARPMA prosedürü vardı
ve uygulanmadı"* gibi bir "önlenebilirdi" iddiası artık modelin kanaati
değil, denetlenebilir bir kayıt.

---

## 10. Bas-konuş (STT) — isteğe bağlı sesli girdi

Operatör kutusuna mikrofonla metin yazdırma, tamamen yerel çalışan
`faster-whisper` ile (ayrı bir `stt` ekstrası; kurulu değilse uç `501`
döner, mikrofon düğmesi devre dışı çizilir — uydurulmuş bir transkript
asla dönmez). Şartnamenin *"sesli etkileşim (varsa)"* notuna karşılık
gelen, tamamen isteğe bağlı bir katman; ayrıntı:
[04-kurulum-calistirma.md](04-kurulum-calistirma.md).
