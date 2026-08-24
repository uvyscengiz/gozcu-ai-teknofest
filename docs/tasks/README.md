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

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, 3. senaryo. **Teslim: 26 Ağustos 23:59.
Kod dondurma: 26 Ağustos 12:00.**

## Takvim

| Gün | `uvyscengiz` | `Xana-bit` | `beyzaalive` | `rumeysaoru` |
|---|---|---|---|---|
| **23 Ağu** | 00, 01, 02, 03, 05 | — | — | — |
| **24 Ağu** | 04, 06, 07 + konsol iskeleti + `run.py` bağlama | — | — | — |
| **25 Ağu** | 08, 11, 14 | 09, 10 | 12, 13 | 16 (konsolu genişlet) |
| **26 Ağu öğlene kadar** | 17 | demo çekimi | Türkçe üslup turu | 15 + benchmark koşusu |
| **26 Ağu öğleden sonra** | **[Görev 18 — paketleme](18-paketleme.md), herkes.** Kod dondurma 12:00 | | | |

### 24 Ağustos çıkış kriteri

İkinci solo günün sonunda şu doğru olmalı:

```bash
uv run python app.py     # bir klip yükle → dört anahtarlı JSON arayüzde görünsün
```

İyi olması gerekmiyor. **Çalışması** gerekiyor. 25'inde üç kişi ya genişletecekleri
çalışan bir sisteme gelir, ya da önce anlamaları gereken boş bir iskelete — ve
ikincisinden bir günle dönüş yok. Gün kayıyorsa entegrasyondan önce **Görev 07**
kesilir.

## Görev listesi

| # | Görev | Sahip | Gün | Bağımlı olduğu | Durum |
|---|---|---|---|---|---|
| [00](00-test-altyapisi.md) | Test altyapısı ve yerel gateway | uvyscengiz | 23 | — | ✅ 23 Ağu |
| [01](01-sozlesme.md) | Paylaşılan sözleşme (`models.py`) | uvyscengiz | 23 | 00 | ✅ 23 Ağu |
| [02](02-olay-deposu.md) | Olay deposu (SQLite) | uvyscengiz | 23 | 01 | ✅ 23 Ağu |
| [03](03-gateway.md) | Kademeli gateway istemcisi | uvyscengiz | 23 | 00 | ✅ 23 Ağu |
| [04](04-yorumlayici.md) | Yorumlayıcı adaptörü (VLM) | uvyscengiz | 24 | 01, 02, 03 | ✅ 23 Ağu |
| [05](05-karar-dongusu.md) | Olay anında karar döngüsü | uvyscengiz | 23 | 01, 02, 03 | ✅ 23 Ağu |
| [06](06-yonlendirici.md) | Yönlendirici ajanı | uvyscengiz | 24 | 01, 03 | ✅ 23 Ağu |
| [07](07-sentezleyici.md) | Sentezleyici (kareler → epizot) | uvyscengiz | 24 | 01, 02, 03, 06 | ✅ 23 Ağu |
| [08](08-hafiza.md) | Epizodik hafıza araması | uvyscengiz | 25 | 01, 02, 03, 07 | ✅ 23 Ağu |
| [09](09-tesis-dunyasi.md) | Tesis dünyası (fixture'lar) | Xana-bit | 25 | 01, 02 | ✅ 23 Ağu |
| [10](10-saha-araclari.md) | Yedi saha sistemi aracı | Xana-bit | 25 | 01, 02, 09 | ✅ 23 Ağu |
| [11](11-risk-analisti.md) | Risk analisti | uvyscengiz | 25 | 08, 10 | ✅ 23 Ağu |
| [12](12-raportor.md) | Raportör ve kök neden raporu | beyzaalive | 25 | 01, 02, 03, 10, 11 | ✅ 23 Ağu |
| [13](13-guard.md) | Çıktı denetimi | beyzaalive | 25 | 03 | ✅ 23 Ağu |
| [14](14-nobetci.md) | Nöbetçi süpervizör | uvyscengiz | 25 | 08, 09, 11, 12, 13 | ✅ 24 Ağu |
| [15](15-kpi.md) | KPI ve benchmark | rumeysaoru | 26 | 02 | ✅ 24 Ağu |
| [16](16-konsol.md) | Operatör konsolu | rumeysaoru | 25 | 14 |  |
| [17](17-cikti-sozlesmesi.md) | Çıktı sözleşmesi ve entegrasyon | uvyscengiz | 26 | hepsi |  |
| [18](18-paketleme.md) | Paketleme ve teslim | hepimiz | 26 | hepsi |  |

**Cold-start görevleri: 09, 10, 12, 13, 15.** Sahipleri 25'inde bu kod tabanını
ilk kez görüyor. Bu görevlerin hiçbiri entegrasyon yolunda değil, hiçbiri kimseyi
bloke etmiyor, hepsi tek komutla doğrulanıyor. Bir cold-start görevini anlamak
için konuşmak gerekiyorsa **görev yanlış yazılmış** — sahibinden soru sormasını
beklemek yerine görev yeniden yazılır.

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

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
