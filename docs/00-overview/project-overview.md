# Proje özeti

## Ne inşa ediyoruz

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, **3. senaryo**: video analiz ve
karar destek sistemi.

Gözcü, bir savunma sanayi üretim tesisinin kamera kaydını izliyor, olayları fark
ediyor, riski değerlendiriyor ve nöbetçi operatörle Türkçe konuşuyor. Kapanışta
şartnamenin istediği yapılandırılmış JSON'u ve bir kök neden raporunu üretiyor.

## Mimarinin tek önemli tercihi

Yüklenen bir videoyu işlemenin iki yolu var:

**Önce izle, sonra özetle.** Video baştan sona işlenir, sonunda rapor çıkar,
aksiyonlar sonrasında konuşulur. Bu bir *özetleme* sistemidir — ortada karar anı
yoktur.

**Videonun kendi saatinde karar ver.** Sistem zaman çizelgesinde ilerler, kritik
ana geldiğinde **orada durur**: riski biçer, vardiya listesini sorgular,
operatöre seslenir, saha sistemini arar. Video henüz bitmemiştir.

İkincisini yapıyoruz. Şartnamenin puanladığı *çok adımlı karar zincirleri*,
*dinamik araç seçimi* ve *inisiyatif alma* kalemlerinin üçü de karar anı
gerektiriyor; bitmiş bir raporun üzerine sohbet etmek bunları karşılamıyor.

## Kontrol odası kadrosu

Tek bir yapay zekâ değil, herkesin tek bir işi olan bir vardiya kadrosu:

| Rol | İşi |
|---|---|
| Kameralar | Kim var, ne kadar hızlı, kim kadraj dışına çıktı — **yapay zekâ değil**, yerelde çalışır |
| Dispeçer | "Bu önemli mi, kime gider?" Kararların çoğu burada kapanır |
| Gözlemci | Sadece çağrılınca kareye bakar ve anlatır |
| Kâtip | Dağınık gözlemleri tek bir olaya birleştirir: başlangıç, gelişim, sonuç |
| İSG uzmanı | Riski biçer, geçmişi sorgular, her öneriyi bir araca bağlar |
| Vardiya amiri | Operatörle konuşan ajan. Kendisi seslenir, sorar, düzeltilir, saha sistemlerini arar |
| Raportör | Kök neden raporunu yazar — ve neyden emin olamadığını da yazar |
| Arşiv | Bütün olaylar aranabilir; bir olayı çok daha öncekine bağlamanın tek yolu |

Ajanlar birbirine **yazılı olarak** devrediyor. O devir kaydı sonradan "sistem
neden böyle karar verdi" sorusunun cevabı oluyor.

## Alan

**Savunma sanayi tesisi iş güvenliği.** Şartname *"savunma sanayi tesisleri veya
saha operasyonları"* diyor ve verdiği tek somut örnek forklift devrilmesi +
yerde hareketsiz kişi + personel toplanması — yani bir üretim tesisi. Teknik
kapsam fabrika iş güvenliği; dil, saha sistemleri ve sunum tesis kılığında.

Bu, hocanın 2026-08-13 görüşmesinde uyardığı "kapsam çok geniş" riskinin
kapanışı. Geniş genelleme gelecek çalışma olarak yazılıyor, mevcut yetenek diye
iddia edilmiyor.

## Sert kısıtlar

- **Girdi yüklenen video dosyası.** Canlı kamera / RTSP kapsamda değil.
- **Modeller organizasyonun gateway'inde**, OpenAI uyumlu API üzerinden.
- **Yapılandırılmış çıktı zorunlu:** `summary` · `events` · `risk` · `actions`.
- **Ajan mimarisi zorunlu** — statik kural tabanlı çözümler açıkça düşük puan alıyor.
- **Açık kaynak, tekrar üretilebilir.** Apache 2.0.
- **Bütün operatör çıktısı Türkçe.**

## Ayrıntı

[tasarım spec'i](../superpowers/specs/2026-08-22-agentic-gozcu-design.md) ·
[görevler](../tasks/README.md) ·
[karar günlüğü](../05-decisions/decision-log.md)
