# Teknoloji yığını

Gerçekten kullandıklarımız. LangGraph, LangMem, yerel vLLM, PySceneDetect ve
Katna **kullanılmadı** — o plan uygulanmadan önce iptal edildi.

## Ajan katmanı — kütüphane yok

Ajan orkestrasyonu için framework kullanmıyoruz. Süpervizör döngüsü düz Python:
`gozcu/agents/supervisor.py` içinde bir tool-call döngüsü.

Gerekçe: LangGraph üç günde öğrenme eğrisi riski, ve şartnamenin puanladığı şey
framework adı değil *dinamik araç seçimi*, *bağlam yönetimi*, *çok adımlı karar
zincirleri*. Bunların üçü de okunabilir düz kodla daha net gösteriliyor — kod
kalitesi de ayrı bir puan kalemi.

Hafıza için LangMem yerine kendi epizodik deposu: SQLite + gömme + kosinüs.

## Katman katman

| Katman | Ne kullanıyoruz | Dosya |
|---|---|---|
| Video I/O | FFmpeg, OpenCV | `gozcu/frames.py` |
| Nesne tespiti | Ultralytics **YOLOE** (açık sözlüklü) | `gozcu/detect.py` |
| Takip | ByteTrack (Ultralytics `persist=True`) | `gozcu/track.py` |
| Sinyaller | Hız, kayboluş, kişi sayısı — düz Python | `gozcu/signals.py` |
| Tipler | Pydantic v2 | `gozcu/models.py` |
| Depo | SQLite (stdlib `sqlite3`) | `gozcu/store.py` |
| Model erişimi | `openai` istemcisi → organizasyonun LiteLLM gateway'i | `gozcu/gateway.py` |
| Hafıza araması | numpy kosinüs + reranker | `gozcu/memory.py` |
| Arayüz | FastAPI + SSE + bağımlılıksız HTML/CSS/JS | `gozcu/ui/server.py`, `gozcu/ui/web/` |
| Test | pytest | `tests/` |

**Arayüz 27 Ağustos 2026'da Gradio'dan taşındı.** Sebep tek bir cümlede:
Gradio'nun `SCREEN_SLOTS = 13` protokolü kısmi güncellemeyi imkânsız
kılıyor ve **eksik bir çıktıyı hata vermeden yutuyordu** — o bileşen
sessizce tazelenmiyor, jüri bayat veri görüyordu. Ayrıca video üzerine
kutu katmanı ve zaman çizelgesine olay işaretçisi konamıyordu; şartname
§7'nin puanladığı "kararın olayla aynı anda görülmesi" tam olarak buydu.
Gerekçenin tamamı: [Görev 21](../tasks/21-web-konsolu.md) ·
[karar günlüğü, 27 Ağustos](../05-decisions/decision-log.md).

Durum tarayıcıya SSE ile **tam durum** olarak akıyor (kısmi çerçeve yok —
Gradio'nun yuttuğu arızayı yeni taşıyıcıda üretirdi); komutlar sıradan
`POST`. **Harici ağ bağımlılığı yok:** CDN, font, analitik hiçbiri —
`gozcu/ui/web/` altındaki her şey depodan servis ediliyor.

## Bilerek kullanmadıklarımız

| Teknoloji | Neden |
|---|---|
| LangGraph / LangMem | Üç günde öğrenme eğrisi riski; düz kod daha okunabilir ve aynı kalemleri karşılıyor |
| Yerel vLLM | Modeller organizasyonun sunucusunda; kurulum yükü yok |
| Vektör DB (FAISS/Chroma) | Bir vardiya birkaç yüz epizot; numpy kosinüs anlık. Bağımlılık riski, sıfır kazanç |
| PySceneDetect / Katna | Sahne bölme işini yönlendirici + sentezleyici yapıyor |
| `mlx-vlm` | Opsiyonel extra'ya taşındı — Apple Silicon dışında wheel'i yok, `uv sync` kırılıyordu |
| Gradio | 27 Ağustos'ta emekliye ayrıldı (yukarıdaki tabloya bak); 13 yuvalı çıktı protokolü kısmi güncellemeyi imkânsız kılıyordu |
| WebSocket | Trafik tek yönlü: sunucu durum yayınlıyor, komutlar `POST`. SSE'de yeniden bağlanma tarayıcının kendi işi ve tel `curl` ile okunabiliyor |
| Ön yüz framework'ü (React/Vue…) | Üç görünüm, beş JS modülü, derleme adımı yok. Bir bundler'ın kazancı yok, teslim riski var |

## Model kademeleri

[03-planning/hardware.md](../03-planning/hardware.md) — hangi kademe ne iş
yapıyor ve neden.

## Mimari

Süpervizör (Nöbetçi) + uzman alt-ajanlar. Ayrıntı ve gerekçe için
[tasarım spec'i §3](../superpowers/specs/2026-08-22-agentic-gozcu-design.md).
