# Konsol — mini PRD

**Tarih:** 25 Ağustos 2026 · **Durum:** öneri, onay bekliyor
**Kaynak:** TEKNOFEST YZ Dil Ajanları Teknik Şartnamesi (3. Senaryo)
**Öncül:** [konsol değişiklik listesi](2026-08-25-konsol-degisiklik-listesi.md)

> Bu belgede **veri alanları uydurulmadı**; hepsi `gozcu/models.py`'dan
> okundu ve aşağıda tablo hâlinde. Ölçülmemiş her iddia `ÖLÇÜLMEDİ` diye
> işaretli.

---

## 1. Problem

Konsol şartnamenin istediklerinin çoğunu **üretiyor** ama **göstermiyor**, ve
tek bir düğme yüzünden kilitleniyor.

| Belirti | Kanıt |
| --- | --- |
| Boru hattı operatör bekleyip kilitleniyor | İz kaydı 25 Ağu: `konsol.bekle` **115 s** açık, video 4. pencerede durdu, operatör 6 kez "devam et" yazdı |
| Sohbet duraklamayı açmıyor | `resume.set()` yalnız `resume_btn.click`'te (`console.py:498`) |
| Nöbetçi "sorun yok"u kabul edemiyor | `supervisor.py:108`'de iki kural çıkışsız döngü kuruyor |
| **Araç çağrıları arayüzde yok** | `store.actions()` dolu; `screen` listesinde hiçbir bileşen onu okumuyor (`console.py:632`) |
| KPI'lar arayüzde yok | `bench/perception.json` + `benchmark/kpi.py` üretiyor, konsol göstermiyor |

## 2. Kısıtlar — şartnameden

1. **Sunum 4 dk, demo videosu 1 dk** (§11). Arayüz hikâyeyi kendi anlatmalı.
2. **Çevrimdışı video** (§3: "bir video sisteme yüklenir"). Gerçek müdahale
   yok; duraklamanın amacı *"gerçek zamanlı olsaydı ajan burada şunu
   yapardı"* demek.
3. **Metrikler demoda sunulmalı** (§4, zorunlu ifade).
4. **Mock fonksiyonlar ajanın araçları olarak başarıyla kullanılmalı** (§7,
   %35 kriterin maddesi).
5. **Zorlu koşullar gösterilmeli** (§6, "örn: bağlam değişimi denemesi").

---

## 3. Kapsam

**Dahil:** D1 müdahale kartı · D2 araç şeridi · D3 KPI paneli · D4 Nöbetçi
çıkışı · D5 zorlu koşul düğmeleri · D6 sekmeli düzen.

**Hariç — ve neden:**

| Yapılmayacak | Gerekçe |
| --- | --- |
| Sesli etkileşim | §6 "varsa" diyor, zorunlu değil. Yeni bağımlılık, çevrimdışı kısıtını riske atar. |
| Gerçek zamanlı kamera akışı | §3 yüklenen video istiyor. Müdahale kartı gerçek zamanlı iddiayı zaten anlatıyor. |
| Konsolu yeniden yazmak | Mevcut ağaç gerekenlerin çoğunu içeriyor; eksik olan görünürlük ve akış. |
| Algı katmanına dokunmak | 25 Ağu'da elden geçti (%11 → %93,1). Bu PRD ona hiç dokunmuyor. |

---

## 4. Veri sözleşmeleri — hepsi MEVCUT

Hiçbir yeni tablo, hiçbir şema değişikliği gerekmiyor.

| Model | Alanlar | Nerede kullanılacak |
| --- | --- | --- |
| `ActionRecord` | `ts`, `tool_name`, `params`, `result`, `actor`, `approval` | D2 araç şeridi, D1 kartın "ÇAĞIRDIĞI" satırı |
| `Episode` | `id`, `start_ts`, `end_ts`, `summary_tr`, `participants`, `preliminary_risk`, `state`, `beats`, **`event_ts`** | D1 kart başlığı |
| `RiskAssessment` | `episode_id`, `level`, `rationale_tr`, `preventable`, `proposed_actions` | D1 kartın "GEREKÇE" satırı |
| `Handoff` | `ts`, `source_agent`, `target_agent`, `reason`, `confidence` | D6 devir defteri (var) |
| `PipelineOutput` | `summary`, `events`, `risk`, `actions`, `detail` | D6 Çıktı sekmesi (var) |

**İki tuzak, ikisi de kod okunarak bulundu:**

- **Kart damgası `event_ts` olmalı, `start_ts` DEĞİL.** `start_ts` pencerenin
  sınırı; `event_ts` olayın gerçekten başladığı an (`models.py`, `Episode`
  docstring'i bunu açıkça yazıyor). Kartta pencere sınırını göstermek olayı
  10 saniyeye kadar yanlış yere koyar.
- **Onay kapısı tek araçta:** `NEEDS_APPROVAL = {"halt_production_line"}`
  (`tools/registry.py:20`). Kart "ONAY İSTEDİĞİ" satırını yalnız bu araç
  için gösterecek; diğer altısı `approval="not_required"` ile geçiyor ve
  onları "onay bekliyor" diye çizmek yanlış olur.

---

## 5. Değişiklikler

### D1 — Duraklama kalkıyor, yerine müdahale kartı

**Ne.** `on_event` artık `session.resume.wait()` çağırmıyor. Her yükseltmede
zaman çizelgesine bir kart basılıyor ve koşu devam ediyor.

**Kart içeriği** (hepsi mevcut alanlardan):

| Satır | Kaynak |
| --- | --- |
| Başlık: `⚠ MM:SS — MÜDAHALE ANI` | `episode.event_ts` |
| Risk rozeti | `RiskAssessment.level` |
| Banner: "Gerçek zamanlı kurulumda ajan bu anda müdahale ederdi" | sabit metin |
| GÖRDÜĞÜ | `episode.summary_tr`, `episode.participants` |
| DEDİĞİ | `nobetci.escalate()` metni (diyalog defterinde) |
| ÇAĞIRDIĞI | `actions` içinde `approval == "not_required"` olanlar |
| ONAY İSTEDİĞİ | `approval in ("pending", "approved", "rejected")` |
| GEREKÇE | `RiskAssessment.rationale_tr` |

**`Adım adım` anahtarı** (varsayılan **KAPALI**): açıkken eski bloklama
davranışı geri geliyor. Jüri "durdurup gösterin" derse hazır; kapalıyken koşu
tek parça akıyor.

**Kabul ölçütü**
- Anahtar kapalıyken 115 s'lik video **hiç düğmeye basılmadan** sonuna kadar
  koşuyor.
- Her epizot için tam bir kart üretiliyor; boş satır yerine "—" yazıyor.
- Anahtar açıkken eski duraklama davranışı birebir korunuyor.
- `run_pipeline` imzası **değişmiyor** (`on_event` zaten opsiyonel).

---

### D2 — Araç şeridi ⭐ %35'in görünmeyen yarısı

**Ne.** `store.actions()` çıktısı arayüzde bir tabloya çiziliyor:

| MM:SS | Araç | Parametreler | Sonuç | Durum |
| --- | --- | --- | --- | --- |
| 00:30 | `open_safety_incident` | `episode_id=1, classification=…` | `ref=ISG-0007` | otomatik |
| 00:31 | `halt_production_line` | `line_id=ST-1` | — | ⏸ onay bekliyor |

Üstte sayaç: **`7 araçtan N'i çağrıldı · M çağrı · K onay`**.

**Kabul ölçütü**
- Yedi aracın tamamı isimleriyle listede görünebiliyor.
- `actor` alanı ayırt ediliyor: ajanın çağırdığı ile operatörün tetiklediği
  aynı görünmüyor.
- Çağrı yoksa tablo boş değil, "Henüz araç çağrılmadı" yazıyor — boş bir
  tablo "araçlar çalışmıyor" gibi okunur.

---

### D3 — KPI paneli (şartname zorunlu)

**Ne.** "Ölçüm" sekmesi, üç blok:

| Blok | Kaynak | Örnek |
| --- | --- | --- |
| Algı | `bench/perception.json` | varlık %99,1 · sayım %93,1 · kaza enerji yüzdeliği %3,5 |
| Performans | `gozcu.trace` (canlı) + koşu süresi | RTF, kademe başına ortalama gecikme, kare sayısı |
| Karar | `benchmark/kpi.py` fonksiyonları, canlı `store` üzerinde | karar dağılımı, görü tetikleme oranı, Türkçe çıktı oranı |

**Kabul ölçütü**
- Ölçülemeyen her hücrede `ölçülemedi` yazıyor, `0` yazmıyor —
  `benchmark/kpi.py` ile aynı sözleşme.
- Panel koşu **bitmeden** de dolmaya başlıyor (canlı sayaçlar).

---

### D4 — Nöbetçi'nin çıkışı

**Ne.** `supervisor.py` sistem promptuna üç kural:

1. Operatör bir olayı açıkça geçiştirdiyse **kabul et**,
   `correct_observation` ile kaydet, **konuyu bırak**.
2. Aynı onayı **iki defadan fazla isteme**; ikinci retten sonra kararı
   deftere yaz ve sus.
3. Açık olay hatırlatması **bir kez**, her turda değil.

**Kabul ölçütü**
- "Devam et sorun yok" üç kez yazıldığında ajan üçüncüde aynı onayı
  **istemiyor**.
- Açık olay yine de kayıtta duruyor (susmak, unutmak değil).
- Mevcut süpervizör testleri yeşil kalıyor.

**Risk: ORTA.** Prompt davranışı demoyu etkiler; sonrasında uçtan uca prova
şart.

---

### D5 — Zorlu koşul düğmeleri

| Düğme | Ne yapar | Neyi gösterir | Durum |
| --- | --- | --- | --- |
| Bağlam değiştir | Hazır alakasız mesaj gönderir | Ajan cevaplar, açık olayı bırakmaz | yeni |
| Kademe kes / geri ver | VLM kademesini düşürür | Bozulmadan çalışma + telafi | **var** |
| Yanlış bilgi ver | "Orada kimse yok" der | `correct_observation` + düzeltme kaydı | yeni |

**Kabul ölçütü:** her düğme tek tıkla, elle yazmadan senaryoyu tetikliyor.

---

### D6 — Sekmeli düzen

- Üstte **sabit rozet şeridi**: durum + `RTF · pencere · görü çağrısı · epizot`
- Sekmeler: **Canlı izleme** · **Nöbetçi** · **Çıktı** · **Ölçüm**
- Zaman çizelgesinde bir olaya tıklayınca video o saniyeye atlıyor

**Kabul ölçütü:** 1280x800'de hiçbir sekme dikey kaydırma istemiyor.

---

## 6. Başarı ölçütleri

| Ölçüt | Hedef | Nasıl doğrulanır |
| --- | --- | --- |
| Müdahalesiz tam koşu | 115 s video, **0 düğme** | elle koşu |
| Demo süresi | anlatı ≤ **4 dk**, video ≤ **1 dk** | kronometre |
| Araç görünürlüğü | çağrılan her araç ekranda | D2 tablosu |
| KPI görünürlüğü | üç blok da dolu | Ölçüm sekmesi |
| Diyalog kilitlenmesi | yok | D4 kabul ölçütü |
| Testler | tamamı yeşil | `uv run pytest tests/ -v` |

---

## 7. Riskler

| Risk | Karşılık |
| --- | --- |
| D4 prompt değişikliği demoyu bozabilir | Uçtan uca prova; süpervizör testleri koruma |
| Gradio 6 sekme davranışı | D6 en sona alındı; düşerse tek sütun düzeni kalır |
| Kart kalabalık görünebilir | Boş satır çizilmiyor, "—" yazılıyor |
| `Adım adım` yolu bakımsız kalır | Testte iki yol da koşuluyor |
| Kod dondurma | Sıra etki/maliyete göre; 1+2+4 tek başına teslim edilebilir |

---

## 8. Uygulama sırası

| # | İş | Süre | Kriter |
| --- | --- | ---: | --- |
| 1 | **D2** araç şeridi | 1–1,5 s | **%35** |
| 2 | **D1** müdahale kartı | 2–3 s | %20 + %10 |
| 3 | **D4** Nöbetçi çıkışı | 1 s | %20 |
| 4 | **D3** KPI paneli | 2 s | şartname zorunlu |
| 5 | **D5** zorlu koşul düğmeleri | 45 dk | %35 + demo |
| 6 | **D6** sekmeli düzen | 2 s | %10 |

D2 önce: en ucuz, en yüksek ağırlıklı kriter, ve D1'in kartı zaten onun
verisini kullanıyor.

**Her adım:** önce test (kırmızı), sonra kod, sonra `uv run pytest tests/ -v`
tam yeşil, sonra commit. Konsol testleri `tests/test_console.py`'da ve saf
fonksiyonları (renderer'lar) Gradio olmadan sınanabiliyor — kart ve şerit
üreticileri **saf fonksiyon** olarak yazılacak ki aynı şey burada da geçerli
olsun.
