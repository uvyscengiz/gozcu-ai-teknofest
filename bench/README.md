# `bench/` — ölçüm çıktıları

Benchmark koşusunun ürettiği her şey burada. **`runs/` değil:** orası
`.gitignore`'da ve ultralytics'in kendi çıktıları için kullanılıyor; teslim
kalemi olan ölçüm sonuçları versiyonlanan bir dizinde durmalı.

| Dosya | Ne | Üreten |
| --- | --- | --- |
| `kpi.schema.json` | `kpi.json`'un sözleşmesi (elle yazıldı, versiyonlanır) | — |
| `kpi.json` | ham sonuçlar: klip başına **ve** toplu | `benchmark/run.py` |
| `kpi.md` | Türkçe rapor | `benchmark/report.py` |
| `decision-distribution.png` | sunuma giden tek grafik | `benchmark/report.py` |
| `stores/` | klip başına SQLite deposu (ikili, `.gitignore`'da) | `benchmark/run.py` |

```bash
uv run --env-file .env python -m benchmark.run
uv run python -m benchmark.report
```

## `kpi.json` neyi vaat eder, neyi etmez

Şema `kpi.schema.json`; anahtar adları oradan okunur, koddan tahmin edilmez.
Üç noktayı burada da yazmak gerekiyor çünkü tablonun kendisi bunları
söyleyemez:

- **Ölçülemeyen her KPI `null`.** `0` "ölçtük, sıfır çıktı" demek. Boş koşu
  için tek sözleşme `null`; `nan` zaten geçerli JSON değil.
- **`decision_distribution` beş kovalı.** Beşincisi `degraded`: kesinti
  yüzünden `confidence=0.0` ile kapanan devirler. Bunlar dört karar kovasının
  dışında tutuluyor, çünkü aksi hâlde tamamen çökmüş bir koşu "kararların
  %100'ü en ucuz kademede kapandı" diye okunurdu. `aggregate.status` bu payın
  ne kadar büyüdüğünü tek kelimeyle söyler.
- **`vision_tokens` bir maliyet tablosu değil.** Sistemde `tokens` yalnız
  `Interpretation` kaydında kalıcı hâle geliyor; yönlendirici, ana model,
  denetim, gömme ve yeniden sıralama kademelerinin token'ları hiçbir yerde
  yazmıyor.

## Ön koşullar

`benchmark/kpi.py` fikstürsüz ve gateway'siz çalışır; **koşu öyle değil.**
Video dosyaları (`data/clips/`, `.gitignore`'da), ayakta bir gateway ve Görev
17'nin `run_pipeline`'ı gerekiyor. Eksik olan varsa `benchmark/run.py`
başlamadan durur — sıfırlarla dolu bir `kpi.json` çökme değil, ölçüm gibi
görünen bir hiçtir.

Olay pencereleri (`benchmark/ground_truth.csv`) el işi: `start_s` / `end_s`
boşsa o klip zaman sapması ölçümüne girmez ve raporda "etiketsiz" olarak
sayılır. Buraya tahmin yazılmaz.
