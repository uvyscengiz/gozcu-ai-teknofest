# Test video korpusu

Kaynak: mentor dokümanındaki YouTube/TikTok/Kaggle bağlantıları. Medya dosyaları
gitignore'da; versiyonlanan şeyler kaynak listesi, etiketler, katalog ve betikler.

**Özet:** 32 kaynak video (104 dk, 1.6 GB) + 127 kullanılabilir kesit.
Ayrıntılı liste: [catalog.md](catalog.md).

## Dizin yapısı

| Yol | İçerik | Versiyonlu |
|---|---|---|
| `sources.tsv` | Kaynak listesi: `slot ⇥ kategori ⇥ url ⇥ amaç` | ✓ |
| `labels.tsv` | Kesit başına `verdict ⇥ etiket ⇥ not` | ✓ |
| `catalog.md` / `catalog.json` | Üretilen indeks (elle düzenlenmez) | ✓ |
| `shots.json` | Çekim yapısı analizi (`classify.py` üretir) | ✓ |
| `raw/<kategori>/` | İndirilmiş orijinaller + yt-dlp `.info.json` | ✗ |
| `clips/<kategori>/<video>/` | Derlemelerden ayrılmış kesitler | ✗ |
| `clips/_elenen/` | `ele` işaretli kesitlerin arşivi (silinmedi) | ✗ |
| `scenes/` | PySceneDetect sahne CSV'leri | ✗ |
| `index-sheets/` | Kaynak başına tek tabakada tüm kesitler — etiketleme için | ✗ |
| `thumbs/` | Tek kesiti yakından incelemek için kontak sayfası (`sheets.py`) | ✗ |

## Akış

```bash
./fetch.sh                 # sources.tsv'deki tekil videoları indirir (1080p cap, mp4)
./fetch-playlists.sh 10    # askeri oynatma listelerinden ilk N videoyu indirir
find raw -name '*.mp4' | xargs -P 8 -n 1 ./detect-one.sh   # sahne tespiti
./classify.py              # çekim yapısına göre sınıflandırır -> shots.json
./split.py                 # 'derleme' işaretlileri kesitlere ayırır
./verify.sh                # yarım kalmış/bozuk kesitleri bulur
../.venv/bin/python index-sheets.py   # etiketleme tabakalarını üretir (PIL gerekir)
./prune.sh                 # labels.tsv'de 'ele' olanları arşive taşır
./catalog.py               # catalog.md + catalog.json'u yeniden üretir
```

## Çekim yapısına göre sınıflandırma

`classify.py` her ham videoyu sahne sınırlarına göre üç gruba ayırır:

| Tip | Ölçüt | Anlamı | İşlem |
|---|---|---|---|
| `surekli` | ≤2 sahne veya ort. ≥45 sn | Tek kesintisiz CCTV kaydı | Olduğu gibi kullanılır |
| `derleme` | Orta yoğunlukta kesme, ort. ≥4.5 sn | Ayrı olaylar arka arkaya | Kesitlere bölünür |
| `montaj` | Ort. <4.5 sn | Müzik/kurgu montajı | Bölmek anlamsız, bütün kullanılır |

Otomatik sınıflandırma iki videoda yanıldı, elle düzeltildi (`shots.json` içinde
`duzeltme` alanı):

- **`multi-event--OlRDWS2E0EY`** — sabit IP kamera. Tespit edilen 6 "kesme" ışık
  ve hareket kaynaklı yanlış pozitif; gerçek kesme yok. Bütün kullanılmalı,
  zaten amacı uzun sürekli akışta küçük olayları yakalamak.
- **`forklift-cause--V8ZmOgMlyRE`** — iki sahne aynı olayın öncesi ve sonrası.
  Bölmek sebep-sonuç zincirini koparır ki testin amacı tam olarak o zincir.

**Genel kural:** bölme yalnızca kesmeler *farklı olayları* ayırdığında doğru.
Tek olayın tekrar/açı değişimlerinde bölme, testin ölçmek istediği nedenselliği
yok eder.

## Doküman ile uyuşmayan kategori

`youtu.be/-8oYzSP5Vbw` dokümanda "Fabrika genel kaza anları" başlığı altında
geçiyor ama içeriği tamamen **motosiklet kask-kamerası trafik kazaları**.
`trafik` kategorisine taşındı. Proje kapsamı endüstriyel güvenliğe daraltıldığı
için ana senaryo dışında; farklı olay tipi ayırt etme testinde kullanılabilir.

## Erişilemeyen kaynaklar

yt-dlp 2026.08.19'a güncellendikten sonra TikTok kaynağı da indi. Geriye kalan
engel tamamen YouTube yaş kısıtlaması — oturum çerezi gerektiriyor, bilinçli
olarak atlandı.

| Kaynak | Sorun |
|---|---|
| `youtu.be/jEdp6Aj-4hE` (fabrika iş kazaları) | Yaş kısıtlaması |
| `youtu.be/8r5uyR54F-8` (askeri operasyon) | Yaş kısıtlaması |
| Askeri playlist'lerden 5 video | Yaş kısıtlaması |
| Askeri playlist'lerden 1 video (`YSynj8J4R4Y`) | Video kaldırılmış |
| Kaggle `unidpro/car-accident-video` | API anahtarı yok; trafik senaryosu kapsam dışı |

Askeri kategoride yaş kısıtlaması sistematik bir engel: playlist'lerden istenen
20 videonun 6'sı bu yüzden alınamadı. Daha fazla askeri materyal gerekirse
`--cookies-from-browser` tek çözüm.

Askeri kayıtların bir kısmı **grafik içerik** taşıyor (yaralı/ölü görüntüleri,
gözaltı sahneleri). Demo ve sunumda kullanılacak kesitler bu açıdan ayrıca
gözden geçirilmeli.

## Hâlâ eksik olan senaryolar

Mentor dokümanının "EKSİK VİDEOLAR" bölümünden:

- **Uzun süreli askeri operasyon videosu (hafıza testi).** Askerler bir yapıya
  girer, araya alakasız olaylar girer, ~15 dk sonra yapı patlar. Test: sistem
  sadece "patlama oldu" mu diyecek, yoksa 15 dk önceki girişi hatırlayıp
  nedensel bağı mı kuracak.
  → **Kısmi karşılık:** `pl2-02--O2A_KBTxB00` (15:20) tek bir şehir içi
  operasyonun haber belgeseli: devriye, zirhli araç hareketi, havadan
  hedefleme ve bina vuruşu aynı zaman çizgisinde. Kurgulu olduğu için ideal
  değil ama uzun ufuklu hafıza testinin ilk denemesi için kullanılabilir.
- **Uzun süreli fabrika çalışma videosu**, kaza son bölümde olacak şekilde.
  → **Kısmi karşılık:** `forklift-normal--2gL1vMvYQQQ` (9:20) ve
  `forklift-normal--BBcLqG3OYSA` (5:42) kazasız uzun fabrika kayıtları. Sonlarına
  bir kaza kesiti eklenerek sentetik olarak üretilebilir.
- **FPV drone / SİHA saldırı görüntüleri** — kaynak bulunamadı.
