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
| Arayüz | Gradio | `gozcu/ui/console.py` |
| Test | pytest | `tests/` |

## Bilerek kullanmadıklarımız

| Teknoloji | Neden |
|---|---|
| LangGraph / LangMem | Üç günde öğrenme eğrisi riski; düz kod daha okunabilir ve aynı kalemleri karşılıyor |
| Yerel vLLM | Modeller organizasyonun sunucusunda; kurulum yükü yok |
| Vektör DB (FAISS/Chroma) | Bir vardiya birkaç yüz epizot; numpy kosinüs anlık. Bağımlılık riski, sıfır kazanç |
| PySceneDetect / Katna | Sahne bölme işini yönlendirici + sentezleyici yapıyor |
| `mlx-vlm` | Opsiyonel extra'ya taşındı — Apple Silicon dışında wheel'i yok, `uv sync` kırılıyordu |

## Model kademeleri

[03-planning/hardware.md](../03-planning/hardware.md) — hangi kademe ne iş
yapıyor ve neden.

## Mimari

Süpervizör (Nöbetçi) + uzman alt-ajanlar. Ayrıntı ve gerekçe için
[tasarım spec'i §3](../superpowers/specs/2026-08-22-agentic-gozcu-design.md).
