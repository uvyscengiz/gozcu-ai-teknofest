# Yol haritası

**Çok haftalık aşamalı plan iptal edildi.** Gerçek takvim dört gün: 23–26 Ağustos.
Güncel iş bölümü ve görev listesi **[docs/tasks/README.md](../tasks/README.md)**
içinde.

## Tamamlanan (yarışma öncesi)

- FFmpeg tabanlı video → kare çıkarma (`gozcu/frames.py`)
- Açık sözlüklü nesne tespiti, YOLOE (`gozcu/detect.py`)
- ByteTrack ile çoklu nesne takibi (`gozcu/track.py`)
- Hız / kayboluş / kişi sayısı sinyalleri (`gozcu/signals.py`)
- Kare bazlı VLM yorumlama, yapılandırılmış çıktı (`gozcu/interpret.py`)
- Gradio demo arayüzü (`app.py`)

Bu katman **donuk.** Yarışma süresince yeni özellik girmiyor. Bilinen kalite
açıkları (nesne tanıyıcıda yangın/duman sınıfı yok, açıklamalar genel geçer)
kabul edildi ve dokümantasyonda "bilinen sınırlar" olarak yazılacak — puan
cetvelinde görüntü işleme kalitesinin ayrı bir kalemi yok.

## Kalan iş

18 görev, dört günde. [docs/tasks/README.md](../tasks/README.md).

| Gün | Ana hedef |
|---|---|
| 23 Ağu | Sözleşme, depo, gateway, karar döngüsü |
| 24 Ağu | Yorumlayıcı, yönlendirici, sentezleyici + **uçtan uca ince dilim çalışıyor** |
| 25 Ağu | Hafıza, saha araçları, tesis dünyası, risk, raportör, guard, Nöbetçi, konsol |
| 26 Ağu | Çıktı sözleşmesi, KPI, paketleme. **12:00 kod dondurma** |

## Kapsam dışı bırakılanlar

Canlı kamera / RTSP girdisi · V-JEPA2 · vektör veritabanı · Türkçe-özel 14B
model geçişi · YOLO yeniden eğitimi · ses analizi / Whisper · çoklu video
senkronu · sesli etkileşim · PDF dışa aktarma · ayar paneli.

Gerekçe ve alternatifler için [tasarım spec'i §7](../superpowers/specs/2026-08-22-agentic-gozcu-design.md).
