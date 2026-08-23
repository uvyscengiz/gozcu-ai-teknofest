# Puan cetveli eşlemesi

Her kriterin karşılığı sistemde nerede.

## Fonksiyonellik ve senaryo kapsamı — %35

| Kriter | Karşılığı |
|---|---|
| Senaryonun uçtan uca implementasyonu | Video yüklenir → `summary`/`events`/`risk`/`actions` JSON'u üretilir ([görev 17](../tasks/17-cikti-sozlesmesi.md)) |
| Mock fonksiyonların ajanın araçları olarak kullanılması | 7 saha sistemi aracı ([görev 09](../tasks/09-saha-araclari.md)), Nöbetçi tarafından çağrılıyor |
| Kararlı çalışma | Bozulmuş mod, geri çekilme yolları, tüm katmanlarda hata yakalama |

## Teknik implementasyon ve mimari — %35

| Kriter | Karşılığı |
|---|---|
| Ajan, araç, hafıza, prompt mühendisliği | Süpervizör + 4 uzman; 11 araç; SQLite epizodik hafıza + gömme/sıralama |
| Dinamik araç seçimi | Nöbetçi'nin 11 aracı; okuma/aksiyon karışımı seçimi gerçek bir karar yapıyor |
| Bağlam yönetimi | Tipli devir kayıtları; `duzeltme` tablosu ve düzeltme kaskadı |
| Çok adımlı karar zincirleri | Yönlendirici → yorumlayıcı → sentezleyici → risk → Nöbetçi → raportör |
| Hata işleme | Kademeli bozulma; guard açık başarısız oluyor; bozuk JSON'da güvenli varsayılan |
| Kod kalitesi, modülerlik | Sorumluluk başına bir dosya; her modülün kendi test dosyası |
| Mock sistem entegrasyonu | Aksiyon defteri; onay gerektiren geri dönüşsüz aksiyonlar |

## Otonomi ve zekâ — %20

| Kriter | Karşılığı |
|---|---|
| Niyet anlama ve akıl yürütme | Nöbetçi süpervizörü ([görev 14](../tasks/14-nobetci.md)) |
| İnisiyatif alma ve doğru soruyu sorma | `yukselt()` sorulmadan konuşur; `belirsizlik_notu` kameranın göremediğini adlandırır |
| Beklenmedik duruma tepki (bağlam değişimi, hata) | Her operatör turuna açık olay ekleniyor; gateway kesintisi bozulmuş modla karşılanıyor |
| Doğal ve insansı akış | Türkçe üslup kuralları promptta + 26 Ağustos üslup turu |

## Yenilikçilik — %10

| Kriter | Karşılığı |
|---|---|
| Özgün mimari | Kademeli model kullanımı — her karar yetecek en ucuz modele düşüyor, ölçülüp grafikleniyor |
| Beklenti ötesi özellikler | Kök neden raporu; devir defteri ile açıklanabilirlik; operatör onay akışı |
| Ek senaryo | Epizodik hafıza — bir olayı çok daha öncekine bağlama |
| Doküman ve sunum kalitesi | Bu klasör + [ekip planı artifact'i](https://claude.ai/code/artifact/d9aed59e-7a2e-45c0-b3e3-047e03edb7d6) |

## Odak

Puanın **%70'i** ilk iki kalemde ve ikisi de ajan mimarisi. Görüntü işleme
kalitesi cetvelde ayrı bir kalem değil — algı katmanı bu yüzden donuk.
