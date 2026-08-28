# Kullanılan veri seti — herkese açık kaynaklar

Şartname §10 depodan üç şey istiyor: bağımlılıkların eksiksiz listesi
([pyproject.toml](../../pyproject.toml), [uv.lock](../../uv.lock)),
çalıştırma adımlarının tamamı ([teslim/04](../teslim/04-kurulum-calistirma.md))
ve **kullanılan veri setinin herkese açık indirilebilir bağlantısı** — bu
dosya o üçüncü kalemdir.

## Neden burada, dosya olarak değil

Korpus **kamuya açık YouTube/TikTok videolarından** derlendi; medya
dosyalarının kendisi telif sebebiyle depoya konmuyor ve konamaz. Depoda
versiyonlanan şey kaynak listesi — aşağıdaki bağlantılar herkese açık ve
tek tek indirilebilir.

Bağlantılar `data/sources.tsv` dosyasından geliyor; o dosya `5564d06`
("restructure project — clean root") ile depo kökü temizlenirken kaldırıldı,
içeriği buraya taşındı.

## Kaynak listesi

| Slot | Kategori | Bağlantı | Amaç |
|---|---|---|---|
| `fire-single` | yangın | https://youtu.be/lleF2nmlkMY | Tekli algılama: videoda sadece yangın var |
| `multi-event` | karışık | https://youtu.be/OlRDWS2E0EY | Çoklu algılama: her yerde farklı şeyler, büyük olay yok |
| `forklift-accident` | forklift | https://youtu.be/qOPnf-YRuk8 | Forklift kaza anı, kısa |
| `forklift-compilation` | forklift | https://youtu.be/N9bG-sOU6LE | Derleme — kısa forklift kazaları |
| `forklift-normal` | forklift | https://youtu.be/2gL1vMvYQQQ | Fabrika çalışma kaydı, kaza yok (süreç takibi) |
| `forklift-normal` | forklift | https://youtu.be/BBcLqG3OYSA | Fabrika çalışma kaydı, kaza yok (süreç takibi) |
| `forklift-cause` | forklift | https://youtu.be/P2X2Do5m0hY | Kaza anı + sebep algılama |
| `forklift-cause` | forklift | https://youtu.be/Spig3ulTqxw | Kaza anı + sebep algılama |
| `forklift-cause` | forklift | https://youtu.be/6iCOp5MzXE4 | Kaza anı + sebep algılama |
| `forklift-cause` | forklift | https://youtu.be/V8ZmOgMlyRE | Kaza anı + sebep algılama |
| `forklift-cause` | forklift | https://www.tiktok.com/@forklifthero/video/7491923795838553366 | Kaza anı + sebep algılama (TikTok) |
| `factory-accidents` | fabrika | https://youtu.be/UuNsheZUgtE | Fabrika genel kaza anları (derleme) |
| `factory-accidents` | fabrika | https://youtu.be/jEdp6Aj-4hE | Fabrika farklı iş kazası anları (derleme) |
| `traffic-moto` | trafik | https://youtu.be/-8oYzSP5Vbw | Motosiklet kask-kamerası trafik kazaları |
| `military` | askeri | https://youtu.be/MImbyEHJTkM | Askeri operasyon |
| `military` | askeri | https://youtu.be/hE14s_Z-1-Q | Askeri operasyon |
| `military` | askeri | https://youtu.be/8r5uyR54F-8 | Askeri operasyon |
| `military-playlist` | askeri | https://youtube.com/playlist?list=PLakEHcmK8B8WPrVTZO6Fdzfgqb6gI93SR | Askeri operasyon oynatma listesi |
| `military-playlist` | askeri | https://youtube.com/playlist?list=PLCCgfjUwnRFYobTH6fQkbDcHcYFfNuRhk | Askeri operasyon oynatma listesi |
| `synthetic-bodycam` | sentetik | https://youtube.com/shorts/nlXwNwilt8I | Bodycam oyunu — sentetik üretim kaynağı |
| `synthetic-bodycam` | sentetik | https://youtube.com/shorts/_NoifbuniNM | Bodycam oyunu — sentetik üretim kaynağı |
| `synthetic-bodycam` | sentetik | https://youtube.com/shorts/wR-zo-dinUc | Bodycam oyunu — sentetik üretim kaynağı |
| `synthetic-bodycam` | sentetik | https://youtu.be/KVkPToQGVAQ | Bodycam oyunu — sentetik üretim kaynağı |

Kapsam kararı (savunma sanayi tesisi iş güvenliği —
[decision-log](../decisions/decision-log.md), 22-23 Ağustos) alındıktan sonra
fiilen kullanılan alt küme **forklift** ve **yangın** kategorileridir;
askeri/trafik/sentetik satırlar araştırma döneminden kalma ve üretim yoluna
girmedi.

## Ölçümde kullanılan klipler

[`benchmark/ground_truth.csv`](../../benchmark/ground_truth.csv)'nin beş
satırı yukarıdaki **iki** kaynaktan kesilmiş kesitlere karşılık geliyor:

| Klip | Kaynak |
|---|---|
| `forklift-compilation--N9bG-sOU6LE-k03 / -k05 / -k09` | https://youtu.be/N9bG-sOU6LE |
| `fire-single--lleF2nmlkMY-k01 / -k03` | https://youtu.be/lleF2nmlkMY |

Algı ölçümünün ([teslim/07 §2](../teslim/07-olcumleme.md)) elle etiketlenmiş
347 karesi de aynı korpustan bir tekstil fabrikası kazası klibinden geliyor;
etiketler [`benchmark/perception_truth.json`](../../benchmark/perception_truth.json)
içinde **versiyonlanıyor**.

## Yerel dizin düzeni

Benchmark koşucusu ([`benchmark/run.py`](../../benchmark/run.py)) klipleri
depo kökündeki `data/` dizinine göre arar; `ground_truth.csv`'deki yollar o
dizine görelidir:

```
data/
└── clips/
    ├── forklift/forklift-compilation--N9bG-sOU6LE/*.mp4
    └── yangin/fire-single--lleF2nmlkMY/*.mp4
```

Bu dizin **depoda yok** — yukarıdaki bağlantılardan indirilip (ör. `yt-dlp`)
bu düzene yerleştirilmesi gerekiyor. Dosyalar yoksa `preflight()` koşuyu
sessizce sıfırlarla doldurmak yerine yüksek sesle durdurur.
