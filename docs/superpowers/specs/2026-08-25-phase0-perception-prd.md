# 0. Faz (algı) iyileştirme — mini PRD

**Tarih:** 25 Ağustos 2026 · **Durum:** ✅ UYGULANDI (D1–D4), D5 ölçülüp reddedildi

> **Sonuç:** sayım duyarlılığı **%11 → %93,1**, varlık duyarlılığı
> **%72,4 → %99,1**, kaza saniyesi enerjide **%45,2 → %3,5 yüzdelik**.
> Tam kayıt: [decision-log](../../05-decisions/decision-log.md).
> D5 (içeri kaybolma) uygulandı, ölçüldü ve **hiçbir karara bağlanmadı** —
> iz parçalanması yüzünden saniyede 1,1–3,3 yanlış olay üretiyor.
**Taban ölçüm:** [`bench/perception.md`](../../../bench/perception.md) ·
**Koşucu:** `benchmark/perception.py`

> Bu belgedeki **her sayı ölçüldü.** Tahmin, benzetme ve "genelde şöyle olur"
> yok. Ölçülmemiş bir iddia varsa açıkça `ÖLÇÜLMEDİ` yazıyor.

---

## 1. Problem

Algı katmanı, tekstil fabrikası kaza kaydında (116 kare @ 1 fps, elle
etiketlenmiş) şunu yapıyor:

| Ölçüm | Şu an | Olması gereken |
| --- | --- | --- |
| Varlık duyarlılığı | **%72** | ≥%95 |
| Sayım duyarlılığı | **%11** | ≥%60 |
| Zirve kişi sayısı | **6** | ~22 (gerçek) |
| Kaza saniyesinde (t=49) görülen kişi | **0** | ≥1 |
| Kaza saniyesinin hareket enerjisi sırası | **53. / 116** | ilk 10 |

**Kararların olay anında verildiği bir mimaride en pahalı başarısızlık bu:**
karar döngüsü kusursuz çalışsa bile kaza saniyesinde bakacağı kanıt yok.

---

## 2. Kök nedenler — üçü de ölçüldü

### KN-1. Güven eşiği bu görüntü için felaket derecede yüksek

`YOLO_CONFIDENCE = 0.20`. Kalabalık bir karede (t=88, gerçek 20 kişi) modele
`conf=0.01` ile bakıldığında **60 kişi adayı** çıkıyor: 14'ü 0,05 üstünde,
10'u 0,10 üstünde, yalnız 5'i 0,20 üstünde.

**Model kalabalığı buluyor, boru hattı onu eşikte atıyor.** Bu bir tespit
kapasitesi sorunu değil, kalibrasyon sorunu — dış araştırma da bunu doğruluyor:
COCO ile eğitilmiş modeller seyrek, iyi aydınlatılmış yayalarda kalibre ve
kapalı/küçük/düşük kontrastlı örnekleri sistematik olarak düşük puanlıyor.

### KN-2. Takip katmanı tespiti hâlâ veto ediyor

25 Ağustos'ta `if box.id is None: continue` kaldırıldı, ama kayıp oradan
gelmiyordu. Ultralytics'in `model.track()` çağrısı, kare için ≥1 onaylı iz
üretirse `results.boxes`'ı **iz alt kümesiyle DEĞİŞTİRİYOR**. Kutular bizim
döngümüz onları görmeden yok oluyor. Sözleşme koda yazıldı, kütüphaneye
yazılmadı.

Ölçüldü — ve eşik düştükçe **kötüleşiyor**:

| conf | takipsiz kutu | takipten sonra | yok edilen |
| ---: | ---: | ---: | ---: |
| 0,20 | 266 | 159 | %40 |
| 0,05 | 770 | 334 | %57 |
| 0,03 | 1150 | 469 | **%59** |

### KN-3. Hareket triyajı olaya nişan alamıyor

`window_energy` küresel bir ortalama. Yoğun bir fabrika zemininde hareket her
yerde yüksek; tek kişilik bir savrulma toplam kütlede yuvarlama hatası.
Kaza saniyesi 116 karenin 53.'sü çıktı. Modülün kendi docstring'i bu bedeli
zaten öngörmüş ("10 saniyelik sakin bir pencerenin içindeki 1 saniyelik bir
olay ortalamada seyrelir") — manşet olayımız tam olarak o bedeli ödedi.

---

## 3. YAPMAYACAKLARIMIZ — ölçülüp elenen fikirler

Bunlar makul görünüyor, popüler tavsiyede geçiyor, ve **bu görüntüde ölçülüp
yanlış çıktılar.** Tekrar gündeme gelmesinler diye yazılıyor.

| Fikir | Neden hayır |
| --- | --- |
| **Çözünürlüğü artır** (896 → 1280) | **Ters etki, ölçüldü.** t=88'de kişi güveni 640'ta 0,647; 896'da 0,159; 1280'de sıfır tespit. Kaynak 960x720 ve gerçek optik detay o kadar; büyütmek gürültüyü esnetiyor ve nesneleri modelin kalibre olduğu ölçek dağılımının dışına itiyor. Ultralytics'in kendi kılavuzu da bunu söylüyor: `imgsz` nominal piksele değil **gerçek detaya** göre seçilir. |
| **Daha büyük model** (11m / 11l / 26m) | **Ters etki, ölçüldü.** conf 0,05'te sayım duyarlılığı: 11n %89,7 · 11s %79,3 · 11l %64,1 · 11m %56,6. En küçük model kazanıyor. Büyük modeller daha iyi kalibre ve belirsiz kanıtı kendinden emin biçimde reddediyor; bu görüntüde istediğimizin tersi. |
| **YOLO26 / NMS'siz mimari** | Ölçüldü: yolo26s/26m, yolo11n'i geçemedi. Dış araştırma da doğruluyor — NMS'siz başlıkların kalabalık duyarlılığını artırdığına dair **ölçülmüş kanıt yok**; belgelenen kazanç gecikme ve basitlik. YOLOv10 makalesi küçük ölçeklerde NMS'siz eğitimin AP'yi %0,5–1,0 **düşürdüğünü** kendi yazıyor. |
| **NMS IoU eşiğini düşür** (0,3–0,4) | **Yön yanlış, ölçüldü.** Ultralytics'te `iou` bastırma eşiği: düşük = daha çok bastır. F1: iou 0,3 → %72,2 · 0,7 → %82,4 · 0,8 → **%82,8** · 0,9 → %67,7. Kalabalıkta istediğimiz **yüksek** eşik. (Dış araştırma bunu ters önerdi; ölçüm düzeltti.) |
| **SAHI / karo bazlı çıkarım** | Kaynak zaten 960x720; karolamak native detayı çoğaltmıyor. `set_classes` + takip ile entegrasyon riski, kazancı ölçülmemişken kabul edilemez. |
| **ReID / BoTSORT derin ayarı** | `track.py` docstring'i bu yolu zaten ölçüp çıkmaz ilan etmiş. Sorun tracker ayarı değil, tracker'ın **veto yetkisi**. |

---

## 4. Değişiklikler

Etki/maliyet sırasına göre. **D1 ve D2 ölçülmüş, tahmin değil.**

### D1 — Güven eşiği 0,20 → 0,03 · *maliyet: bir satır*

`gozcu/config.py`'da `YOLO_CONFIDENCE` varsayılanı. Tek satır, model değişmiyor,
`detect.py` ve `track.py`'a dokunulmuyor.

**Ölçülen etki (uçtan uca, gerçek boru hattı):**

| | conf 0,20 | conf 0,03 |
| --- | ---: | ---: |
| Varlık duyarlılığı | %72,4 | **%97,4** |
| Sayım duyarlılığı | %11,0 | **%31,0** |
| Zirve kişi | 6 | **21** |
| t=49'da kişi | 0 | **1** |

**Bedeli:** olaysız kontrol klibinde (12 kare, gerçek 0 kişi) yanlış pozitif
0 → **3 kutu / 3 kare**. `config.py`'daki eski not "0,10 ilk yanlış pozitifi
getiriyor" diyordu; o gözlem doğru ama **eksik** — karşılığında sayım
duyarlılığı üç katına çıkıyor. Bir güvenlik sisteminde 12 karede 3 fazladan
kutu, 20 kişilik bir kalabalığı 1 kişi saymaktan iyidir.

### D2 — Takibin vetosunu kaldır: tespit kayıttır, kimlik bir JOIN'dir · *maliyet: 1–2 saat*

`track_video()` artık `model.track()`'in döndürdüğü kutuları kullanmayacak.
Yerine:

1. `model.predict()` **tek kutu kaynağı** (kayıt budur),
2. ilişkilendirme ayrı çalışır ve `track_id`'yi kutulara **ekler**,
3. kimlik atanamazsa kutu **yine de geçer**.

Ultralytics'in yerleşik ByteTrack'i (`tracker="bytetrack.yaml"`) bu iş için
BoTSORT'tan daha uygun: ikinci aşaması düşük güvenli kutuları bilerek mevcut
izlere bağlıyor — yani D1'in ürettiği zayıf tespitleri **kurtarmak** onun
tasarım amacı. (Sınırı da kayda geçsin: ByteTrack yalnız **zaten kurulmuş**
izleri kurtarır; hiçbir karede eşiği geçmemiş bir kişiyi kurtarmaz.)

**Ölçülen etki — D1 ile birleşik:**

| | takiple | takipsiz |
| --- | ---: | ---: |
| conf 0,03 sayım duyarlılığı | %31,0 | **%83,4** |
| conf 0,03 zirve kişi | 21 | **27** |

D1'den sonra **baskın kayıp bu.** İkisi birlikte: sayım duyarlılığı
%11 → **%83**, yani **7,6 kat**.

### D3 — Kare hızını yükselt (1 fps → 4–5 fps) · *maliyet: env değişkeni + 1–2 saat sonuç yönetimi*

`GOZCU_FRAME_FPS`. Üç şeyi birden düzeltiyor:

- **Takip ilişkilendirmesi 1 fps'te yapısal olarak ölü** (`track.py` docstring'i
  bunu zaten yazıyor). 5 fps'te ardışık kutular örtüşüyor ve ByteTrack'in
  kurtarma aşaması gerçekten çalışabiliyor.
- **Kaza yarım saniyelik bir savrulma.** 1 fps'te tek örnek — muhtemelen
  hareket bulanıklığıyla. 5 fps'te beş şans.
- Kör kareler "kör saniye" olmaktan çıkıyor: bir saniyenin 5 örneğinin hepsi
  birden kaçırmalı.

**Kritik gözlem — bu VLM bütçesine mal OLMUYOR.** `gozcu/run.py:_clip_for`
görü kademesine kaynak videodan kesilmiş bir mp4 gönderiyor, bizim çıkardığımız
kareleri değil. Kare hızı ile görü maliyeti zaten ayrık. Şu anda gerçek zaman
katsayısı **0,14** — harcanmayan bütçe var.

`ÖLÇÜLMEDİ:` 5 fps'te duyarlılığın nereye gittiği. D1+D2'den sonra ölçülmeli.

**Yan etki uyarısı:** `vanished_tracks` "ardışık K karede yok" olmalı, yoksa
200 ms'lik bir kesinti "iz kayboldu" diye okunur ve `loop.py`'ın taban
kontrolünü su basar.

### D4 — Hareket triyajını hücre bazlı z-skora çevir · *maliyet: 1–2 saat*

Küresel ortalama yerine 8x6 ızgara; her hücre kendi son ~20–30 saniyelik
temeline göre z-skor; kare skoru = hücrelerin en büyüğü. Pencere toplaması
ortalama değil **ilk-k ortalaması**.

**Neden:** yoğun bir zeminde olayı ayırt eden şey mutlak hareket miktarı değil,
**o bölgenin kendi normalinden sapması.** Küresel büyüklük bunu asla
sıralayamaz.

`ÖLÇÜLMEDİ:` t=49'un yeni sıralaması. Başarı ölçütü: ilk 10.

### D5 — İçeri kaybolma + hız sıçraması kanalı · *maliyet: 2–3 saat, D2+D3'e bağlı*

"Makineye kapılan işçi" sinyal olarak şudur: **hızlanan ve sonra kare kenarına
DEĞMEDEN kaybolan bir iz.** `signals.py` iki bileşeni de zaten hesaplıyor;
bugün gürültü olmalarının sebebi 1 fps parçalanması.

Ayrıca `agents/interpreter.py:_context` şu an her kaybolmayı "kadraj dışına
çıkan" diye anlatıyor — makineye çekilen bir insan için **tam tersi**.

---

## 5. Kapsam dışı

- **Model değişimi.** Ölçüldü ve kazanç marjinal: en iyi aday (yolo11n @0,08,
  F1 %82,4) ile mevcut model (YOLOE @0,03, F1 %83,7) arasında fark yok.
  YOLOE ayrıca `forklift` kelimesini taşıyor ve COCO'da forklift sınıfı **yok**
  — senaryonun açıkça istediği şey. Model değiştirmenin getirisi sıfıra yakın,
  riski gerçek. **Model kalıyor.**
- **CrowdHuman ağırlıkları.** Dış araştırma bunu ilk sıraya koydu; indirilebilir
  YOLO-CrowdHuman kontrolleri topluluk fork'ları, **lisansları belirsiz** ve
  yayımlanmış MR⁻² tabloları yok. Şartname "açık kaynak" diyor ve jüri
  kurulum/lisans belgesine bakıyor. Belirsiz lisanslı ağırlık teslime girmez.
- **CLAHE / gama ön işleme.** Dış araştırmada ölçülmüş ama etkisi mütevazı
  (1–5 puan) ve bir çalışmada belirli nesnelerde **zarar veriyor**. Bizim
  kadrajımızda patlamış bir pencere var. D1–D2 yanında gürültü; istenirse
  sonra ölçülür.
- Ajan katmanı, VLM, risk analisti, konsol.

---

## 6. Başarı ölçütleri

`uv run python -m benchmark.perception <video>` ile, aynı etiketlerle:

| Ölçüm | Taban | Hedef | D1+D2 ile ölçülen |
| --- | ---: | ---: | ---: |
| Varlık duyarlılığı | %72,4 | ≥%95 | **%97,4** ✅ |
| Sayım duyarlılığı | %11,0 | ≥%60 | **%83,4** ✅ |
| Zirve kişi (gerçek 22) | 6 | ≥15 | **27** ⚠️ fazla sayıyor |
| t=49'da kişi | 0 | ≥1 | **1** ✅ |
| Kontrol klibinde yanlış pozitif | 0 | ≤5 kutu/12 kare | **3** ✅ |
| t=49 enerji sırası | 53. | ilk 10 | D4 sonrası ölçülecek |

**Tek klibe aşırı uyum riski gerçek.** Her değişiklik üç klipte birden
koşulmalı: bu tekstil klibi + raf çökmesi (`k03`) + olaysız kontrol
(`fire-single-k03`). Etiket dosyası `benchmark/perception_truth.json` bunu
destekliyor (video başına kayıt).

---

## 7. Riskler

| Risk | Karşılık |
| --- | --- |
| conf 0,03 yanlış pozitif getiriyor | Ölçüldü: 12 karede 3 kutu. D2'nin ByteTrack'i bunları zamansal tutarlılıkla ayıklamalı — **ölçülmeli**. |
| Zirve 27 > gerçek 22 (fazla sayım) | Duyarlılık için kabul edilen bir bedel. Ajan katmanının ihtiyacı **eşik ve eğilim** ("kalabalık, artıyor, ≥10"), tam sayım değil. |
| Algıyı iyileştirmek boru hattını yine bozabilir | Bu bir kez oldu (decision-log, 25 Ağu: k05'te epizot 1→0). Değişiklikten sonra **uçtan uca** koşu şart, yalnız 0. Faz ölçümü değil. |
| Kod dondurma | Bkz. aşağıdaki not. |

> **Takvim çelişkisi — karar gerekiyor.** `CLAUDE.md` kod dondurmayı
> **26 Ağustos 12:00** diye yazıyor (yani ~16 saat). Bu doğruysa yalnız
> **D1 + D2** yapılmalı: ikisi birlikte ~2 saat, ölçülmüş getirisi 7,6 kat, ve
> ikisi de küçük ve geri alınabilir. D3–D5 dondurma sonrasına kalır. Takvim
> değiştiyse sıra D1 → D2 → D3 → D4 → D5 olarak devam eder.

---

## 8. Uygulama sırası

1. **D1** (bir satır) → ölç → commit
2. **D2** (takip vetosu) → ölç → uçtan uca koşu → commit
3. Üç klipli mini takım kur, D1+D2'yi üçünde de doğrula
4. *(dondurma izin verirse)* D3 → D4 → D5, her biri kendi ölçümüyle

Her adım `bench/perception.json`'a yazar; taban dosyası korunuyor, böylece
her değişikliğin işareti (+/−) görünür.
