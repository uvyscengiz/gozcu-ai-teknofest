# Konsol değişiklik listesi — şartnameye göre

**Tarih:** 25 Ağustos 2026 · **Durum:** öneri
**Kaynak:** TEKNOFEST Yapay Zekâ Dil Ajanları Teknik Şartnamesi (3. Senaryo)

---

## Neden bu liste

Şartnameden çıkan iki sert kısıt bugünkü konsolu doğrudan yanlışlıyor:

1. **Sunum 4 dakika, demo videosu 1 dakika** (§11). Konsol hikâyeyi kendi
   başına anlatmalı; bir insanın düğmeye basmasını bekleyen bir arayüz bu
   bütçeyi yakar.
2. **Bu bir çevrimdışı video.** Operatörün gerçekten müdahale edeceği bir
   an yok. Duraklamanın amacı müdahale ETMEK değil, *"gerçek zamanlı bir
   kurulumda ajan tam burada şunu yapardı"* demek. Bugünkü duraklama bunu
   göstermiyor, sadece engelliyor.

Ölçülen arıza (25 Ağustos, iz kaydı): döngü 4. pencerede durdu, operatör
Nöbetçi'ye altı kez "devam et sorun yok" yazdı, `konsol.bekle` **115 saniye**
açık kaldı ve video hiç ilerlemedi. Sohbet `resume`'u set etmiyor — yalnız
"Devam et" düğmesi ediyor.

---

## Puan tablosuyla eşleme

| Kriter | Ağırlık | Bugün | Bu liste sonrası |
| --- | ---: | --- | --- |
| Fonksiyonellik ve Senaryo Kapsamı | %35 | Dört anahtar üretiliyor ama **araç çağrıları arayüzde görünmüyor** | D2 araç şeridi |
| Teknik İmplementasyon ve Mimari | %35 | Var, ama görünmüyor | D2 + D6 |
| Otonomi ve Zekâ | %20 | Diyalog var; **kilitleniyor** | D1 + D4 |
| Yenilikçilik ve Yaratıcılık | %10 | — | D1 (müdahale kartı) + D3 |

---

## D1 — Duraklamayı KALDIR, yerine "müdahale kartı" koy ⭐ en yüksek etki

**Sorun.** `on_event` `session.resume.wait()` ile boru hattını kilitliyor
(`console.py:463`). Kilit yalnız "Devam et" düğmesiyle açılıyor. Çevrimdışı
bir kayıtta bu, gösterilecek bir şey üretmiyor — sadece demo süresini yiyor
ve kilitlenebiliyor.

**Değişiklik.** `on_event` **bloklamıyor**. Her yükseltme anında zaman
çizelgesine bir **müdahale kartı** basılıyor:

```
┌─ ⚠ 00:30 — MÜDAHALE ANI ────────────── risk: Yüksek ─┐
│ Gerçek zamanlı kurulumda ajan bu anda müdahale ederdi │
│                                                        │
│ GÖRDÜĞÜ    7 kişi, ıslak zemin, makine çıkışı hareketli│
│ DEDİĞİ     "Operatör, makine çıkışında personel var…"  │
│ ÇAĞIRDIĞI  ✓ open_safety_incident(episode_id=1, …)     │
│            ✓ radio_call(unit="vardiya", …)             │
│ ONAY İSTEDİĞİ  ⏸ halt_production_line(line_id="ST-1")  │
│ GEREKÇE    "Zemin ıslak + hareketli ekipman"           │
└────────────────────────────────────────────────────────┘
```

Bu, kullanıcının tam olarak istediği şey: *"gerçek zamanlı olsaydı ajanımız
burada şöyle müdahale ederdi, şu araçları çağırırdı."* Ve bloklamadığı için
video sonuna kadar akıyor.

**Canlı demo için kaçış kapısı.** `Adım adım` anahtarı (varsayılan KAPALI).
Açıkken eski davranış geri geliyor — jüri "durdurup gösterebilir misiniz"
derse hazır. Kapalıyken koşu tek parça akıyor.

**Maliyet:** ~2–3 saat. `console.py` `_analyse`/`on_event` + kart üreticisi.
**Risk:** düşük; `run_pipeline` zaten `on_event`'i opsiyonel çağırıyor.

---

## D2 — Araç çağrılarını GÖSTER ⭐ %35'lik kriterin görünmeyen yarısı

**Sorun.** Şartname §7 açıkça puanlıyor: *"Mock fonksiyonların ajanın araçları
olarak başarıyla kullanılması."* Yedi saha aracı var (`radio_call`,
`dispatch_medical`, `site_alarm`, `open_safety_incident`,
`halt_production_line`, `query_shift_personnel`, `query_equipment_history`),
hepsi `action` tablosuna yazılıyor — **ve arayüzde hiçbir yerde görünmüyorlar.**
Sadece kapanış JSON'unun içinde metin olarak varlar. Jüri araçların
çalıştığını göremiyor.

**Değişiklik.** Zaman çizelgesinin yanına **araç şeridi**: her çağrı için
video saniyesi, araç adı, parametreler, dönen sonuç, onay durumu
(`otomatik` / `onay bekliyor` / `onaylandı` / `reddedildi`).

Ayrıca üstte tek satırlık sayaç: `7 araçtan 5'i çağrıldı · 12 çağrı · 2 onay`.

**Maliyet:** ~1–1,5 saat. Veri zaten `store.actions()` içinde.
**Risk:** yok.

---

## D3 — KPI paneli ⭐ şartname bunu AÇIKÇA istiyor

**Sorun.** §4: *"Katılımcılar… kendi metriklerini tanımlamalıdır… Tanımlanan
metrikler, **demo ve raporlarda açık şekilde sunulmalıdır**."* Ayrıca §4
performans kalemlerini sayıyor: video işleme süresi, model inference süresi,
bellek/donanım kullanımı.

Hepsini üretiyoruz (`bench/perception.json`, `benchmark/kpi.py`, yeni
`gozcu/trace.py`) — konsolda hiçbiri yok.

**Değişiklik.** "Ölçüm" sekmesi:

- **Algı:** varlık duyarlılığı %99,1 · sayım duyarlılığı %93,1 · kaza
  saniyesi enerji yüzdeliği %3,5 *(elle etiketli kayıttan)*
- **Performans:** video süresi, işleme süresi, gerçek zaman katsayısı,
  kademe başına ortalama gecikme (`trace`'ten canlı)
- **Karar:** yönlendirici karar dağılımı, görü tetikleme oranı, Türkçe çıktı
  oranı
- Üstte sabit rozet şeridi: `RTF 0.35 · 12 pencere · 4 görü çağrısı · 1 epizot`

**Maliyet:** ~2 saat. Sayılar hazır; toplama + çizim işi.
**Risk:** yok.

---

## D4 — Nöbetçi'nin çıkışı olsun (kilitlenme düzeltmesi)

**Sorun.** `supervisor.py:108` promptunda iki kural birleşip **çıkışsız bir
döngü** kuruyor:

- *"Operatör seni düzeltirse `correct_observation` çağırırsın"* → "sorun yok"
  bir düzeltme olarak okunuyor
- *"Operatör konuyu değiştirirse cevaplarsın ama AÇIK OLAYI HATIRLATIRSIN"* →
  her cevapta olay yeniden gündeme geliyor

Operatör altı kez "devam et" dedi, ajan altı kez aynı onayı istedi. Şartname
§7 bunu doğrudan puanlıyor: *"Diyalogun doğal ve insansı bir akışta
ilerlemesi"* (%20 içinde). Bugünkü hâli bunun tersi.

**Değişiklik.** Prompta çıkış koşulu:

- Operatör bir olayı açıkça geçiştirdiyse **kabul et**, `correct_observation`
  ile kaydet ve **konuyu bırak**
- Aynı onayı **iki defadan fazla isteme**; ikinci retten sonra kararı
  operatöre yazıp sus
- Hatırlatma **bir kez**, her turda değil

**Maliyet:** ~1 saat + prova. **Risk:** orta — demo davranışını değiştirir,
sonrasında uçtan uca koşu şart.

---

## D5 — "Zorlu koşullar" tek tuşla gösterilsin

**Sorun.** §6 demo videosunda *"zorlu koşulları (örn: bağlam değişimi
denemesi) nasıl yönettiği"* isteniyor. Kesinti düğmeleri var
(`Bağlantıyı kes/geri ver`), bağlam değişimi için bir şey yok — ve 4 dakikada
elle yazmak zaman kaybı.

**Değişiklik.** "Zorlu koşul" düğme grubu:

| Düğme | Ne yapar | Neyi gösterir |
| --- | --- | --- |
| Bağlam değiştir | Hazır alakasız mesaj gönderir ("bugün hava nasıl?") | Ajan cevaplar ama açık olayı bırakmaz |
| Kademe kes | (var) VLM kademesini düşürür | Kesintide bozulmadan çalışma + telafi |
| Yanlış bilgi ver | "Orada kimse yok" der | `correct_observation` + düzeltme kaydı |

**Maliyet:** ~45 dakika. **Risk:** yok.

---

## D6 — Düzen: tek uzun kaydırma yerine sekmeler

**Sorun.** Her şey alt alta; 4 dakikalık sunumda jüri aşağı kaydırmayı
izliyor. Ekran görüntüsünde alt yarı (sohbet, defter, JSON, rapor) hiç
görünmüyor.

**Değişiklik.**

- Üstte **sabit rozet şeridi** (durum + KPI özeti) — hep görünür
- Sekmeler: **Canlı izleme** (video + çizelge + müdahale kartları) ·
  **Nöbetçi** (sohbet + onaylar + zorlu koşul düğmeleri) · **Çıktı**
  (dört anahtar JSON + kök neden) · **Ölçüm** (D3)
- Zaman çizelgesi tıklanabilir: bir olaya tıklayınca video o saniyeye atlıyor

**Maliyet:** ~2 saat. **Risk:** düşük, ama Gradio 6 sekme davranışı prova
istiyor.

---

## Önerilen sıra

| # | İş | Süre | Kriter |
| --- | --- | ---: | --- |
| 1 | **D1** müdahale kartı, duraklama kalkıyor | 2–3 s | %10 + %20 |
| 2 | **D2** araç şeridi | 1–1,5 s | **%35** |
| 3 | **D4** Nöbetçi çıkışı | 1 s | %20 |
| 4 | **D3** KPI paneli | 2 s | şartname zorunlu |
| 5 | **D5** zorlu koşul düğmeleri | 45 dk | %35 + demo |
| 6 | **D6** sekmeli düzen | 2 s | %10 |

**Sadece 1+2+4 yapılırsa** (≈5 saat) en büyük üç boşluk kapanıyor:
kilitlenme, görünmeyen araçlar, ve "gerçek zamanlı olsaydı ne olurdu"
anlatısı.

---

## Yapılmayacaklar

- **Sesli etkileşim.** §6 "varsa" diyor, zorunlu değil. Metin etkileşimi
  zaten net gösteriliyor; ses yeni bir bağımlılık ve çevrimdışı kısıtı
  riske atar.
- **Gerçek zamanlı kamera akışı.** Şartname yüklenen video istiyor
  (§3 "Operasyon sahasında bir video sisteme yüklenir"). Müdahale kartı
  gerçek zamanlı iddiayı zaten anlatıyor.
- **Konsolu yeniden yazmak.** Mevcut ağaç şartnamenin istediklerinin çoğunu
  zaten içeriyor; eksik olan görünürlük ve akış.
