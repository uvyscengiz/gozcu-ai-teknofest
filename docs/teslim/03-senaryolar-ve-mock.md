
# ③ İmplemente edilen senaryolar ve mock fonksiyonlar

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"implemente edilen senaryolar ve mock fonksiyonlar"*
kalemidir.

---

## 1. Ana senaryo — şartnamenin kendi örneğiyle birebir

Şartname §3 *"Senaryo"* başlığı altında tek bir somut örnek veriyor:
fabrika ortamında **forklift devrilmesi + yerde hareketsiz kişi + personel
toplanması**, beklenen çıktı olarak zaman damgalı olay listesi, genel özet,
risk değerlendirmesi ve aksiyon önerileri. Gözcü bu senaryoyu birebir hedef
alıyor — kod tarafında kapsam *savunma sanayi üretim tesisi iş güvenliği*
olarak sabitlendi (bkz. [decision-log, 22-23 Ağustos](../decisions/decision-log.md)):
şartnamenin verdiği tek somut örnek zaten bir üretim tesisi kazası, ve
hocanın "kapsam çok geniş" uyarısı domain'i buraya daralttı.

Demo klipleri gerçek fabrika/depo videolarından derlenmiş kısa kesitler
(`data/clips/`) — forklift devrilmesi, yük düşmesi, yangın gibi kategoriler
altında. Bu akış [`tests/test_supervisor.py`](../../tests/test_supervisor.py)
ve [01-mimari §5](01-mimari-ozeti-ve-diyagramlar.md#5-kritik-an--sekans-diyagramı)'te
adım adım doğrulanıyor:

```
00:15  İstif aracı devrildi           → epizot açılır, ön risk "Yüksek"
                                       → DÖNGÜ DURUR
                                       → assess_risk() ÖNCE çağrılır:
                                         Risk Analisti kendi araç turunda
                                         search_timeline("istif aracı fren")
                                         çağırır → arşivde emsal bulunursa
                                         (ör. "IST-04 fren mesafesi uzadı",
                                         2026-08-12) risk gerekçesine girer
                                       → Nöbetçi operatöre seslenir:
                                         önce bir saha aracı (radio_call /
                                         dispatch_medical / site_alarm /
                                         open_safety_incident) KONUŞMADAN
                                         ÖNCE çağrılır, sonra mesaj yazılır.
                                         Emsal varsa açılış cümlesi onu
                                         deterministik olarak anar.
       "B-Hattında istif aracı devrildi, sağlık ekibi yolda.
        Yerdeki kişi hareket ediyor mu? Bu açıdan göremiyorum."
00:20  Operatör düzeltiyor: "araç devrilmedi, yük düştü"
                                       → correct_observation çağrılır,
                                         özet güncellenir, risk YENİDEN
                                         biçilir (assess_risk tekrar koşar)
                                       → "Hattı durdurmak için ONAY istiyorum"
       operatör "devam et" der         → generator kaldığı yerden sürer
00:35  Personel toplanması              → video akmaya devam eder
```

**Not — bu bölüm bir kez zaten yanlış yazılmıştı.** İlk taslakta bu
sıralamada `query_shift_personnel` ve `query_equipment_history` adlı iki
okuma aracı geçiyordu; ikisi de 26 Ağustos'taki mimari revizyonda kaldırıldı
ve yerlerine `search_timeline`/`search_documents` kondu — bkz.
[`gozcu/tools/field_systems.py`](../../gozcu/tools/field_systems.py)'in
modül başı notu ve [`tests/test_supervisor.py:190-193`](../../tests/test_supervisor.py).
Yukarıdaki sürüm güncel kodla (`gozcu/agents/risk.py`, `supervisor.py`)
doğrudan karşılaştırılarak düzeltildi.

Bu, şartnamenin §3'ündeki örnek çıktı biçimiyle **birebir** eşleşiyor:

```json
{
  "summary": "Videoda forklift kazası ve yaralanma riski gözlenmiştir.",
  "events": [
    {"time": "00:15", "event": "Forklift devrildi"},
    {"time": "00:20", "event": "Yerde hareketsiz kişi"}
  ],
  "risk": "Yüksek",
  "actions": ["Sağlık ekibini çağır", "Alanı güvenlik altına al"]
}
```

`gozcu/output/report.py::build_output` bu dört anahtarı — genişletilmiş
katmanların tamamı çökse bile — üretiyor; ayrıntı
[01-mimari §9](01-mimari-ozeti-ve-diyagramlar.md#9-çıktı-sözleşmesi)'da.

---

## 2. Mock fonksiyonlar — beş saha aksiyonu, tek meşru kapı

Şartnamenin §5'i *"mock fonksiyon örnekleri"* istiyor; Gözcü'de bunlar
[`gozcu/tools/field_systems.py`](../../gozcu/tools/field_systems.py)'te beş
düz Python fonksiyonu. Ajan "sağlık ekibini çağırın" diye bir cümle
yazmıyor — bu fonksiyonu gerçekten çağırıyor.

| Araç | Ne simüle ediyor | Dönen örnek |
|---|---|---|
| `radio_call(unit, message)` | Telsiz araması | `{"call_id": "2026-1001", "state": "delivered", "awaiting_reply": true}` |
| `dispatch_medical(location, urgency, description)` | Revir sağlık ekibi sevki | `{"team": "revir-1", "eta_minutes": 4, "state": "dispatched"}` |
| `site_alarm(zone, level)` | Bölgesel sesli alarm | `{"alarm_id": "2026-3001", "siren_state": "active"}` |
| `open_safety_incident(episode_id, classification, description)` | İSG olay kaydı açma | `{"record_no": "2026-4001", "state": "open"}` |
| `halt_production_line(line_id, rationale, approved)` | Üretim hattı durdurma — **iki fazlı** | onaysız: `{"state": "awaiting_approval"}` → onaylı: `{"state": "halted"}` |

**Tek meşru giriş noktası [`gozcu/tools/registry.py::call_tool`](../../gozcu/tools/registry.py).**
Fonksiyonların kendisi doğrudan çağrılabilir sade Python — ama doğrudan
çağrılan bir araç **aksiyon defterine hiç düşmez** ve
`halt_production_line`'ın onay kapısını atlar. Defter jürinin şeffaflık
ekranında okuduğu şey; deftere düşmeyen bir aksiyon olmamış sayılır.

**Onay kapısı yalnız `halt_production_line`'da — ve bu bilerek verilmiş bir
hüküm.** Diğer dördü *geri alınabilir ve ucuz*: yanlış çağrılan bir sağlık
ekibi geri döner, boşuna çalan bir siren susturulur. Buna karşılık
gecikmenin bedeli *can*: yerde hareketsiz bir kişi varken ekibi operatörün
onayını bekletmek, kaybedilen her saniyeyi bir onay ekranına ödemek
olurdu — bu yüzden dördü anında yürüyor. Hat durdurma ise *geri alması zor
ve pahalı* (vardiya planı, üretim çizelgesi, teslimat taahhüdü); ajanın tek
başına vereceği bir karar değil, kapıda bekliyor. `approved` bayrağını
model değil **aksiyon defteri** veriyor — ajan kendi hat durdurmasını
onaylayamaz.

### 26 Ağustos kararı: mock'lar artık her çağrıda başarıyor

İlk tasarımda dört aksiyon aracı (`dispatch_medical`, `site_alarm`,
`open_safety_incident`, `halt_production_line`) bölge/hat adı fikstürde
çözülemezse `zone_unresolved` gibi reddedici bir sonuç döndürüyordu —
gerekçe "uydurma bir bölgeye müdahale göndermek yanlış". Canlı koşuda bu
disiplin sahaya **tek müdahale bile ulaştırmadı**: gerçek bir devrilme
klibinde forklift ve operatör kamerada apaçık görünürken 23 karenin
23'ünde bölge çözülemedi, altı `dispatch_medical` ve altı `site_alarm`
çağrısının hepsi reddedildi. Bunlar gerçek sistemlere bağlı **mock**'lar —
olmayan bir riski (uydurma bölge adıyla yanlış yere müdahale) önlemek için
gerçek bir zararı (hiç müdahale olmaması) göze almak yanlış bir takastı.
Karar: bölge/hat çözülürse fikstürdeki gerçek veri kullanılır, çözülemezse
varsayılana düşülür — ama aksiyon **yine de yürür**. Ayrıntı:
[05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md).

---

## 3. Okuma araçları — mock fikstürden gerçek RAG'a

Şartname mock fonksiyonları *"ajanın araçları"* olarak görüyor; okuma
tarafında Gözcü sabit fikstür okumalarını bilerek terk edip gerçek anlamsal
arama araçlarına geçti:

| Araç | Ne yapıyor | Kim çağırıyor |
|---|---|---|
| `search_timeline(query)` | Epizot arşivinde (Qdrant, `team37/episodes`) anlamsal arama — *"bu araçla daha önce bir olay olmuş muydu?"* | Risk analisti, Nöbetçi |
| `search_documents(query)` | Operatörün yüklediği referans belgelerinde (vardiya listesi, ekipman kartı, prosedür) anlamsal arama | Risk analisti, Nöbetçi, Aksiyon Planlayıcı |

İkisi de [`gozcu/memory/episodic.py`](../../gozcu/memory/episodic.py)'de
tanımlı, `registry.call_tool`'dan **geçmiyor** — bir arşiv sorgusu sahada
hiçbir şeyi tetiklemiyor, dolayısıyla aksiyon defterine bir saha aksiyonu
gibi düşmemeli (`gozcu/agents/risk.py`'nin modül başı notu). Eskiden bu iki
işi `query_shift_personnel` ve `query_equipment_history` adlı, sabit
fikstür verisi döndüren mock okuma araçları görüyordu; bunlar kaldırıldı,
yerlerine gerçek belge yükleme + gömme + anlamsal arama zinciri kondu
(bkz. [06-ek-ozellikler.md](06-ek-ozellikler.md)) — bu, şartnamenin istediği
minimumun ötesinde bir mühendislik kararı.

---

## 4. Fikstür veri kümesi — tesisin sabit dünyası

Mock araçların ve raportörün okuduğu deterministik veri
[`gozcu/fixtures/`](../../gozcu/fixtures/) altında, JSON dosyaları hâlinde:

| Dosya | İçerik |
|---|---|
| `facility.json` | Bölgeler (`zone_id`, ad, takma adlar, hat kodu, revir ekibi/varış süresi), vardiyalar, senaryo tarihi |
| `equipment.json` | Ekipman bakım geçmişi — `overdue_maintenance_months()` buradan **hesaplanıyor**, elle yazılmıyor |
| `protocols.json` | Olay sınıfı + bölge + risk eşiğine göre eşleşen İSG prosedürleri |
| `prior_incidents.json` | Arşiv tohumu — koşu başında Qdrant'a gömülen geçmiş olaylar |

Bütün tarihler dosyalarda **sabit** (senaryo 15 Ağustos 2026'da geçiyor);
hiçbir değer `date.today()`'den hesaplanmıyor — aksi hâlde demo gerçek
zaman ilerledikçe kayar (dört ay gecikmiş bir bakım bir ay sonra beş ay
gecikmiş görünürdü).

**Bölge çözümleme tek yerden geçiyor** (`resolve_zone`): ajan bir yeri
`"B-Hattı"`, `"B"` ya da `"B-Hattı sevkiyat alanı"` diye üç farklı biçimde
söyleyebilir, üçü de aynı bölge kaydına oturur.

**Protokol eşleştirme deterministik, model karışmıyor**
(`match_protocols`): olay sınıfı birebir eşleşmeli, bölge listesi boşsa
tesis geneli sayılır, olayın riski protokolün `min_risk`'inin altındaysa
protokol hiç önerilmez. Bu, Aksiyon Planlayıcı'nın *"PRT-B-ÇARPMA
prosedürü vardı ve uygulanmadı"* gibi denetlenebilir bir "önlenebilirdi"
iddiası kurabilmesinin temeli (bkz. [06-ek-ozellikler.md](06-ek-ozellikler.md)).

---

## 5. Şartname §5 mock örneğiyle eşleşme tablosu

| Şartname §5 örneği | Gözcü'deki karşılığı |
|---|---|
| `summary` (kısa Türkçe özet) | `gozcu/output/report.py::build_output` — Raportör'ün `what_happened` alanı |
| `events[]` (zaman damgalı) | `Episode.beats` → mutlak video zamanı, `EventBeat` |
| `risk` (Türkçe enum) | `RiskAssessment.level` — Risk Analisti, `search_timeline`/`search_documents` ile araştırarak |
| `actions[]` | `ActionPlan.proposed_actions` — Aksiyon Planlayıcı, protokole bağlı; Nöbetçi'nin onay kapısından geçerek gerçekten çağrılıyor |

Çıktı sözleşmesinin tam biçimi ve `detail` altındaki genişletilmiş katmanlar
için [01-mimari §9](01-mimari-ozeti-ve-diyagramlar.md#9-çıktı-sözleşmesi).
