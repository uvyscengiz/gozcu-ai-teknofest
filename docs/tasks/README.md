# Görevler

Her görev kendi dosyasında, kendi içinde tam. Bir görevi tek başına bir ajana
veya bir kişiye verebilirsin — dosyayı okumak yeterli, başka bir yere bakmasına
gerek yok.

**Kaynak doküman:** [tasarım spec'i](../superpowers/specs/2026-08-22-agentic-gozcu-design.md).
Çelişki halinde spec geçerlidir.

## Proje, üç cümlede

Gözcü, fabrika kamera kaydını izleyip olayları fark eden, riski değerlendiren ve
operatörle Türkçe konuşan bir karar destek sistemi. Video yüklenir, sistem onu
baştan sona işler ve **kritik ana geldiğinde orada durup karar verir** — video
bitmeden operatöre seslenir, saha sistemlerini arar. Kapanışta hem şartnamenin
istediği JSON'u hem kök neden raporunu üretir.

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, 3. senaryo. **GitHub teslimi:
26 Ağustos 23:59** (kod dondurma 12:00) · **Final: 27–28 Ağustos, Bilişim
Vadisi — Kocaeli, fiziki.** Kurallar ve teslim listesi:
[sartname.md](../00-overview/sartname.md).

## Durum

**Bütün özellik görevleri bitti. Geriye yalnız
[18 (paketleme)](18-paketleme.md) kaldı.**
[16 (konsol)](16-konsol.md) 25 Ağustos'ta indi (`0ce9e86`): operatör konsolu
`gozcu/ui/console.py`'de, `app.py` üç satıra düştü ve demo videosunun
çekileceği yüzey ayakta. Kod artık paketleniyor, yazılmıyor — 18'in kalemleri
prova, ölçüm koşusu, üslup turu, doküman ve teslim.

**Ama uçtan uca prova hâlâ yapılmadı:** sekiz demo anının gerçek modellerle
çalıştığını kimse izlemedi. 18'in ilk kalemi bu ve çekimden önce atlanamaz.

Kod dondurma **26 Ağustos 12:00**, GitHub teslimi **26 Ağustos 23:59**. Teslim
işin sonu değil: **27–28 Ağustos'ta Kocaeli'de fiziki final** var — 4 dakikalık
sunum ve içinde 1 dakikalık demo videosu. 18'in kalemleri ikisini birden
besliyor.

Günlere bölünmüş eski çizelge kaldırıldı: iş o sırayla ilerlemedi ve duran bir
plan, tamamlanmış bir görevi "seninki, başla" diye göstererek zarar veriyor.
Her görevin gerçek durumu aşağıdaki tabloda; tamamlananların dosyasında
`✅ TAMAMLANDI` bandı ve hangi commit'te indiği yazıyor.

## Görev listesi

| # | Görev | Bağımlı olduğu | Durum |
|---|---|---|---|
| [00](00-test-altyapisi.md) | Test altyapısı ve yerel gateway | — | ✅ 23 Ağu |
| [01](01-sozlesme.md) | Paylaşılan sözleşme (`models.py`) | 00 | ✅ 23 Ağu |
| [02](02-olay-deposu.md) | Olay deposu (SQLite) | 01 | ✅ 23 Ağu |
| [03](03-gateway.md) | Kademeli gateway istemcisi | 00 | ✅ 23 Ağu |
| [04](04-yorumlayici.md) | Yorumlayıcı adaptörü (VLM) | 01, 02, 03 | ✅ 23 Ağu |
| [05](05-karar-dongusu.md) | Olay anında karar döngüsü | 01, 02, 03 | ✅ 23 Ağu |
| [06](06-yonlendirici.md) | Yönlendirici ajanı | 01, 03 | ✅ 23 Ağu |
| [07](07-sentezleyici.md) | Sentezleyici (kareler → epizot) | 01, 02, 03, 06 | ✅ 23 Ağu |
| [08](08-hafiza.md) | Epizodik hafıza araması | 01, 02, 03, 07 | ✅ 23 Ağu |
| [09](09-tesis-dunyasi.md) | Tesis dünyası (fixture'lar) | 01, 02 | ✅ 23 Ağu |
| [10](10-saha-araclari.md) | Yedi saha sistemi aracı | 01, 02, 09 | ✅ 23 Ağu |
| [11](11-risk-analisti.md) | Risk analisti | 08, 10 | ✅ 23 Ağu |
| [12](12-raportor.md) | Raportör ve kök neden raporu | 01, 02, 03, 10, 11 | ✅ 23 Ağu |
| [13](13-guard.md) | Çıktı denetimi | 03 | ✅ 23 Ağu |
| [14](14-nobetci.md) | Nöbetçi süpervizör | 08, 09, 11, 12, 13 | ✅ 24 Ağu |
| [15](15-kpi.md) | KPI ve benchmark | 02 | ✅ 24 Ağu |
| [16](16-konsol.md) | Operatör konsolu | 14 | ✅ 25 Ağu |
| [17](17-cikti-sozlesmesi.md) | Çıktı sözleşmesi ve entegrasyon | hepsi | ✅ 25 Ağu |
| [18](18-paketleme.md) | Paketleme ve teslim | hepsi |  |
| [19](19-canli-akis.md) | Canlı akış konsolu (iki sekme) | 16, 17 | ✅ 26 Ağu |

Görev dosyaları artık birer **kayıt**: her biri ne yapıldığını, hangi
commit'te indiğini ve sonraki görevleri neyin bağladığını anlatıyor. Bir
dosyayı yeniden uygulamadan önce başındaki banda bak.

## Kurulum (her görev için aynı)

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v          # mevcut testler geçmeli
```

Modellere erişim için organizasyonun EVREN servisi kullanılıyor. **Adresleri
elle vermene gerek yok** — `gozcu/config.py` hem LLM ağ geçidini
(`https://evren-llmapi.ssyz.org.tr/v1`) hem vektör veritabanını
(`https://evren-vektor.ssyz.org.tr`, ön ek `team37`) doğru varsayılanla
taşıyor. Gereken tek şey **iki anahtar** ve ikisi de `.env` içine yazılıyor,
kabuğa değil:

```bash
cp .env.example .env
# .env içinde doldur:
#   GOZCU_GATEWAY_API_KEY=...        LLM ağ geçidi (bearer token)
#   GOZCU_QDRANT_API_KEY=qdr-team37-...   Qdrant — AYRI bir anahtar
uv run --env-file .env python app.py
```

`.env` içindeki `GOZCU_GATEWAY_BASE_URL` satırı yerel bir gateway'i işaret
ediyorsa gerçek servise **çıkılmaz** — ortam değişkeni `config.py`
varsayılanını ezer; yerel gateway'le çalışmıyorsan o satırı sil.

İki anahtar **farklı**: vektör veritabanı ağ geçidinden geçmiyor, ayrı adres
ve ayrı kimlik doğrulama. **Hiçbiri repoya girmez.** `GOZCU_QDRANT_API_KEY`
tanımlı değilse hiçbir şey patlamaz — epizodik hafıza sessizce süreç içi bir
Qdrant'a düşer ve koşuyla birlikte yok olur; `gozcu.memory.memory_backend()`
bunu `"local"` diye söyler. Saha notları:
[EVREN gateway](../06-references/evren-gateway.md).

Gateway'e erişimin yoksa **09, 10, 12, 13, 15** yine de tamamen çalışır —
hiçbiri gerçek model çağırmaz, testleri mock kullanır. Hafıza testleri de
çevrimdışı: hepsi süreç içi `QdrantClient(":memory:")` üzerinde koşuyor.

## Kurallar

- **TDD.** Önce testi yaz, kırmızı olduğunu gör, sonra minimum kodu yaz.
- **Türkçe çıktı.** Operatöre giden her metin Türkçe. Kısa cümle, saha
  terminolojisi (`istif aracı`, `vardiya amiri`, `yerde hareketsiz kişi`),
  edilgen çatıdan kaçın.
- **Risk seviyeleri tam olarak** `"Düşük" | "Orta" | "Yüksek" | "Kritik"`.
- **Model kimlikleri sadece `gozcu/config.py`'da.** Başka hiçbir yerde model adı
  yazmayacaksın.
- **Algı katmanı donuk.** `frames.py`, `detect.py`, `track.py`, `signals.py`
  değişmiyor.
- **Sık commit.** Her görev en az bir commit, testler yeşilken.

## Takıldığında

Görev dosyası bir kayıt: başındaki bant hangi commit'te indiğini,
`Tamamlanma notları` bölümü de sonraki görevleri neyin bağladığını söylüyor.
Kod ile dosya çelişirse **kod geçerlidir** — ve dosya düzeltilir.
