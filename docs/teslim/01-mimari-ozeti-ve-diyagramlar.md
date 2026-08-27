# ① Sistem mimarisinin genel özeti ve diyagramlar

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi
TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması — **3. Senaryo: Video Analiz
ve Karar Destek Sistemi**

Bu bölüm şartname §6'nın *"sistem mimarisinin genel özeti ve diyagramı"*
kalemidir. Anlatılan mimari **kodda çalışan mimaridir**; her kutunun altında
onu uygulayan dosya adı yazılıdır ve iddia edilen her sayının kaynağı
gösterilmiştir.

---

## 1. Bir cümlede

> **Sistem izlerken karar verir — izledikten sonra özetlemez.**

Bu, mimarinin tamamını belirleyen tercihtir. Yüklenen bir videoyu baştan sona
işleyip sonunda rapor yazan bir sistem bir **özetleyicidir**; içinde karar anı
yoktur. Gözcü videonun kendi saatinde ilerler ve **kritik ana geldiğinde orada
durur**: riski biçer, vardiya kayıtlarını ve ekipman geçmişini sorgular,
operatöre seslenir, aksiyon önerir ve saha sistemini arar. **Video henüz
bitmemiştir.** Kapanıştaki JSON ve kök neden raporu bu döngünün *sonucudur*,
yerine geçen şey değil.

Bunun kod tarafındaki karşılığı tek bir satırdır — `DecisionLoop.run()` bir
**generator**'dür ([`gozcu/loop.py:733`](../../gozcu/loop.py)): yükseltme
anında `yield` eder, çağıran taraf operatörle konuşur, `next()` döngüyü kaldığı
yerden sürdürür. Duraklama bir arayüz numarası değil, akışın kendisidir.

---

## 2. Katman diyagramı — uçtan uca akış

```
                         ┌──────────────────────────────┐
                         │      OPERATÖR (tarayıcı)     │
                         │   video yükler · konuşur ·   │
                         │   düzeltir · onaylar         │
                         └───────┬──────────────▲───────┘
                            HTTP │              │ SSE (tam durum)
                         ┌───────▼──────────────┴───────┐
   ARAYÜZ               │  FastAPI konsolu              │  gozcu/ui/server.py
   (bağımlılıksız       │  · /api/run  · /api/.../say   │  gozcu/ui/web/
    HTML/CSS/JS)        │  · adım modu · gateway kes    │  gozcu/ui/feed.py
                         └───────────────┬──────────────┘
                                         │ run_pipeline(...)
╔════════════════════════════════════════▼══════════════════════════════════╗
║  ①  ALGI KATMANI — tamamen YEREL, hiçbir model çağrısı yok                ║
║                                                                            ║
║   video.mp4                                                                ║
║      │                                                                     ║
║      ├─► ffmpeg      3 fps · 896 px kare çıkarma        gozcu/frames.py    ║
║      ├─► YOLOE       açık sözlüklü tespit, eşik 0.03    gozcu/detect.py    ║
║      │               sınıflar: person,forklift,truck,vehicle               ║
║      ├─► ByteTrack   kimlik ataması (persist=True)      gozcu/track.py     ║
║      ├─► Sinyaller   hız · kaybolan iz · kişi sayısı ·  gozcu/signals.py   ║
║      │               toplanma · sayım değişimi                             ║
║      └─► Triyaj      kare farkı enerjisi (modelsiz)     gozcu/motion.py    ║
║                                                                            ║
║   çıktı: Observation[]  (ts, detections[], signals)     gozcu/adapter.py   ║
╚═══════════════════════════════════════╦════════════════════════════════════╝
                                        ║
╔═══════════════════════════════════════▼════════════════════════════════════╗
║  ②  KARAR DÖNGÜSÜ — videonun kendi saati                gozcu/loop.py      ║
║                                                                            ║
║   Observation[] → 10 sn'lik PENCERE'lere bölünür                           ║
║   her pencere için: ucuz yerel taban → yönlendirici → (gerekirse) görü      ║
║   kritik anda ► yield LoopEvent ►  DURUR, operatörü bekler                 ║
╚═══════════════════════════════════════╦════════════════════════════════════╝
                                        ║ (ayrıntı: §4 ve §5)
╔═══════════════════════════════════════▼════════════════════════════════════╗
║  ③  AJAN KATMANI — süpervizör + uzman alt-ajanlar       gozcu/agents/      ║
║                                                                            ║
║   Yönlendirici · Yorumlayıcı · Sentezleyici · Risk Analisti ·              ║
║   Nöbetçi (süpervizör) · Raportör · Denetim                                ║
║                                                                            ║
║   araçlar: 7 saha sistemi + 4 süpervizör aracı          gozcu/tools/       ║
╚═══════════════════════════════════════╦════════════════════════════════════╝
                                        ║
                ┌───────────────────────╨───────────────────────┐
                ▼                                               ▼
╔═══════════════════════════════╗              ╔═══════════════════════════════╗
║ ④ DEPO — SQLite tek dosya     ║              ║ ⑤ EPİZODİK HAFIZA — Qdrant    ║
║   gozcu/store.py              ║              ║   gozcu/memory.py             ║
║   11 tablo + yazma günlüğü    ║              ║   bge-m3-embed, 1024 boyut    ║
║   (defterlerin tamamı)        ║              ║   ön ek: team37               ║
╚═══════════════════════════════╝              ╚═══════════════════════════════╝
                                        ║
╔═══════════════════════════════════════▼════════════════════════════════════╗
║  ⑥  TESLİM — şartnamenin dört anahtarı                  gozcu/report.py    ║
║      summary · events[] · risk · actions[]   (+ detail)  gozcu/guard.py    ║
╚════════════════════════════════════════════════════════════════════════════╝
```

Modellere erişim ①'de **hiç yoktur**: algı katmanı ağa çıkmaz. ②–⑥ arasındaki
her model çağrısı tek bir kapıdan, kademeli gateway istemcisinden geçer
([`gozcu/gateway.py`](../../gozcu/gateway.py)).

---

## 3. Ajan topolojisi ve model kademeleri

Topoloji **süpervizör + uzman alt-ajanlar**'dır. Tek bir ReAct ajanı ve dört
bağımsız ajan seçenekleri elenmiştir; belirleyici gerekçe şudur: puanın **%20'si
operatör diyalogudur** ve bu topolojide diyalog ajanı zincirin sonundaki bir
tüketici değil, sistemin merkezidir.

```
                    ┌───────────────────────────────────────┐
                    │             OPERATÖR                  │
                    └────────────────┬──▲───────────────────┘
                                     │  │  Türkçe diyalog
                    ┌────────────────▼──┴───────────────────┐
                    │   NÖBETÇİ  (süpervizör)               │  kademe: main
                    │   gozcu/agents/supervisor.py          │
                    │   · kendiliğinden haber verir         │
                    │   · göremediğini SORAR, uydurmaz      │
                    │   · bağlam değişse de açık olaya döner│
                    │   · 11 araç arasından seçer           │
                    └──┬────────┬────────┬─────────┬────────┘
                       │        │        │         │
        ┌──────────────▼──┐  ┌──▼─────┐ ┌▼────────┐│
        │  RİSK ANALİSTİ  │  │RAPORTÖR│ │ HAFIZA  ││        kademe: main / embed
        │  agents/risk.py │  │reporter│ │memory.py││
        │  YALNIZ OKUR:   │  │  .py   │ │ Qdrant  ││
        │  vardiya +      │  │kök     │ │anlamsal ││
        │  ekipman geçmişi│  │neden   │ │ arama   ││
        │  → seviye,      │  │raporu  │ └─────────┘│
        │    gerekçe,     │  └────────┘            │
        │    aday aksiyon │                        │
        └─────────────────┘                        │
                                                   ▼
                    ┌──────────────────────────────────────────────┐
                    │        7 MOCK SAHA SİSTEMİ ARACI             │
                    │        gozcu/tools/field_systems.py          │
                    │  OKUMA : query_shift_personnel               │
                    │          query_equipment_history             │
                    │  EYLEM : radio_call · dispatch_medical ·     │
                    │          site_alarm · open_safety_incident · │
                    │          halt_production_line (onay kapılı)  │
                    │  tek meşru kapı: tools/registry.call_tool    │
                    │  → her çağrı AKSİYON DEFTERİ'ne düşer        │
                    └──────────────────────────────────────────────┘

  ── döngü tarafı (operatörle konuşmayan, videoyu işleyen ajanlar) ──

   YÖNLENDİRİCİ ──► YORUMLAYICI ──► SENTEZLEYİCİ ──► (kapanışta) RİSK ANALİSTİ
   agents/router   agents/         agents/
   kademe: router  interpreter     synthesizer
   GÖRÜNTÜ GÖRMEZ  kademe: vlm     kademe: fast
   sinyal özeti    klip (mp4)      pencere+yorum → Epizot
   okur            okur            (başlangıç/gelişim/sonuç)

   DENETİM (guard) — operatöre giden metni ve teslim paketini süzer;
   gozcu/guard.py · kademe: guard · hiçbir koşulda teslimi ENGELLEMEZ
```

### Kademe tablosu — her karar yeten en ucuz modele düşer

| Katman | Kademe | İşi | Sıklık |
|---|---|---|---|
| Algı | **yerel** (YOLOE + ByteTrack) | Tespit, kimlik, sinyal, hareket enerjisi | Her kare |
| Yönlendirici | `router` | "Burada dikkat gerektiren bir şey var mı, kime gider?" | Pencere başına ≤1 |
| Yorumlayıcı | `vlm` | Tetiklenen 10 sn'lik klibi okur, ciddiyet biçer | Yalnız tetikte |
| Sentezleyici | `fast` | Gözlem + yorum → Epizot (fazlar, Türkçe özet, ön risk) | Epizot başına |
| Hafıza | `embed` (bge-m3, 1024) | Epizot arşivinde anlamsal arama | Sorgu başına |
| Nöbetçi / Risk / Raportör | `main` | Diyalog, derin risk, kök neden | Düşük |
| Denetim | `guard` | Operatöre giden metni süzer | Çıktı başına |

**Model kimlikleri yalnızca [`gozcu/config.py`](../../gozcu/config.py)'da
yaşar.** Başka hiçbir dosyada model adı yazmaz; organizasyon roster'ı
değiştirirse değişen tek dosya budur.

Ölçülen gecikmeler (26 Ağustos canlı koşu, `config.py`'deki kayıt):
`router` 0,3–1,8 sn · `fast` 0,9–1,3 sn · `main` 0,8–2,6 sn · `guard` 0,1 sn ·
`vlm` 7,0–8,7 sn. Uzun olan yalnız görü kademesidir — mimarinin bütün maliyet
tasarrufu o çağrıyı **nereye harcayacağını seçmekten** gelir (§4).

---

## 4. Pencere karar akışı — mimarinin çekirdeği

Kare başına yönlendirme 10 dakikalık bir videoda ~600 model çağrısı ederdi.
Sistem karelere değil **10 saniyelik pencerelere** bakar (~60 çağrı) ve pencere
başına **en fazla bir görü çağrısı** yapar. Akış:

```
                        ┌─────────────────────────┐
                        │  PENCERE (10 sn, N kare)│
                        └────────────┬────────────┘
                                     │
                    ┌────────────────▼─────────────────┐
                    │  YEREL TABAN  passes_floor()     │   model yok, ağ yok
                    │  kişi var mı? iz kayboldu mu?    │
                    │  toplanma? eşik üstü hız?        │
                    └───────┬──────────────────┬───────┘
                     GEÇTİ  │                  │  GEÇEMEDİ
                            ▼                  ▼
            ┌───────────────────────┐   ┌──────────────────────────┐
            │  YÖNLENDİRİCİ (router)│   │  görü BÜTÇESİNDE mi?     │
            │  sinyal özeti + bu    │   │  (top-K hareket enerjisi)│
            │  pencerenin hareket   │   └────┬────────────────┬────┘
            │  enerjisi             │    EVET│                │HAYIR
            └───────────┬───────────┘        │                ▼
                        │                    │            ATLANIR
      ┌─────────────────┼──────────────┐     │        (kayda geçer)
      │                 │              │     │
   ignore          inspect /       close_    │
      │           open_episode /   episode   │
      │           update_episode /    │      │
      │           escalate            │      │
      ▼                 │             │      │
 açık epizot var mı? ───┤             │      │
   ya da bütçede mi?    │             │      │
      │ EVET            │             │      │
      └────────┬────────┴─────────────┼──────┘
               ▼                      │      (yönlendirici ATLANIR:
      ┌────────────────────┐          │       boş sinyal özetinde
      │ YORUMLAYICI (vlm)  │◄─────────┘       okunacak şey yok)
      │ 10 sn'lik mp4 klip │
      │ → severity:        │
      │   rutin/dikkat/OLAY│
      │ → anlar (beats)    │
      └─────────┬──────────┘
                │
      ┌─────────▼──────────────────────────────┐
      │  _may_open()  — epizot AÇILIŞ geçidi   │
      │  yalnız severity == "olay" açar;       │
      │  "rutin"/"dikkat" hiçbir şey uydurmaz  │
      └─────────┬──────────────────────────────┘
                ▼
      ┌────────────────────┐      ön risk "Yüksek"/"Kritik" ise
      │ SENTEZLEYİCİ (fast)│──────────────┐
      │ → Epizot           │              ▼
      │   başlangıç/       │      ╔═══════════════════════════╗
      │   gelişim/sonuç    │      ║  yield LoopEvent          ║
      └────────────────────┘      ║  ► DÖNGÜ BURADA DURUR     ║
                                  ║  ► Nöbetçi operatöre      ║
                                  ║    seslenir, araç çağırır ║
                                  ║  ► video HENÜZ BİTMEDİ    ║
                                  ╚═══════════════════════════╝
```

Bu akışın üç tasarım kararı, üç ayrı ölçülmüş arızanın onarımıdır:

**(a) Taban bir alarm kuralı değil, bir "ne zaman soralım" kuralıdır.**
Hareket sensörü hiçbir alarm sistemini kural tabanlı yapmaz — *neyin önemli
olduğuna* model karar verir, taban yalnızca *ne zaman sorulacağını* belirler.
Şartnamenin *"statik, yalnızca kural tabanlı çözümler düşük puanlanacaktır"*
maddesinin karşılığı budur.

**(b) Pahalı bakış, sayaçla değil kanıtla nişanlanır.** Görü bütçesi
`ceil(pencere_sayısı / 6)` kadardır ve koşunun **bütün** pencereleri arasından
**en yüksek kare-farkı enerjisine** sahip olanlara dağıtılır. Bu triyaj yerel
ve neredeyse bedavadır: 896 px karelerde **1,9 ms/kare**, 23 karelik bir klipte
44 ms — aynı klipteki tek bir görü çağrısı **3.493 ms** sürüyor, yani triyajın
tamamı o çağrının **%1,3'ü** kadar. Ölçümün kaydı `gozcu/loop.py`'nin modül
başındaki notta.

**(c) Bu numaranın sınırı açıkça yazılıdır.** Top-K sıralama videonun tamamının
önceden bilinmesine dayanır. Gerçek bir canlı yayında böyle bir liste yoktur;
orada kayan bir eşik ya da rezervuar örneklemesi gerekirdi. **Bu tasarım
genelleşmiyor ve genelleşiyormuş gibi anlatılmıyor.**

---

## 5. Kritik an — sekans diyagramı

Aşağıdaki dizi demo senaryosunun çekirdeğidir ve aynı zamanda kabul testidir
(`tests/test_dialog_senaryo.py`). Soldan sağa zaman akar; **hepsi video
bitmeden önce** olur.

```
 Algı   Döngü   Yönlend.  Görü    Sentez   Risk     Nöbetçi  Saha     Operatör
  │       │        │       │        │       │         │      araçları    │
  │ Obs[] │        │       │        │       │         │        │         │
  ├──────►│        │       │        │       │         │        │         │
  │       │ taban  │       │        │       │         │        │         │
  │       ├───────►│       │        │       │         │        │         │
  │       │        │ "escalate", güven 0.9  │         │        │         │
  │       │◄───────┤       │        │       │         │        │         │
  │       │  klip (10 sn mp4, base64)       │         │        │         │
  │       ├───────────────►│        │       │         │        │         │
  │       │   severity="olay", anlar[]      │         │        │         │
  │       │◄───────────────┤        │       │         │        │         │
  │       │ pencere + yorum         │       │         │        │         │
  │       ├────────────────────────►│       │         │        │         │
  │       │   Epizot(ön risk="Yüksek")      │         │        │         │
  │       │◄────────────────────────┤       │         │        │         │
  │       │                                 │         │        │         │
  │      ╔╧═══════════════════════════════════════════════════════════╗  │
  │      ║  yield LoopEvent — DÖNGÜ DURUR, video ilerlemiyor          ║  │
  │      ╚╤═══════════════════════════════════════════════════════════╝  │
  │       │                         │       │         │        │         │
  │       ├─────────────────────────────────────────► │        │         │
  │       │                         │       │  escalate(epizot)│         │
  │       │                         │       │         ├───────►│         │
  │       │                         │       │         │ query_shift_personnel
  │       │                         │       │         │◄───────┤ (KONUŞMADAN ÖNCE)
  │       │                         │       │         ├───────►│         │
  │       │                         │       │         │ dispatch_medical │
  │       │                         │       │         │◄───────┤         │
  │       │                         │       │         │ "B-Hattında istif aracı
  │       │                         │       │         │  devrildi, sağlık ekibi
  │       │                         │       │         │  yolda. Yerdeki kişi
  │       │                         │       │         │  hareket ediyor mu?
  │       │                         │       │         │  Bu açıdan göremiyorum."
  │       │                         │       │         ├──────────────────►│
  │       │                         │       │         │                   │
  │       │                         │       │         │  "araç devrilmedi,│
  │       │                         │       │         │   yük düştü"      │
  │       │                         │       │         │◄──────────────────┤
  │       │                         │       │ correct_observation         │
  │       │                         │       │◄────────┤ → düzeltme kaydı  │
  │       │                         │       │ risk YENİDEN biçilir,       │
  │       │                         │       │ İSG sınıflandırması değişir,│
  │       │                         │       │ kök neden raporuna yansır   │
  │       │                         │       │         ├───────►│         │
  │       │                         │       │         │ query_equipment_history
  │       │                         │       │         │◄───────┤ "fren bakımı
  │       │                         │       │         │         4 ay gecikmiş"
  │       │                         │       │         ├──────────────────►│
  │       │                         │       │         │ "Hattı durdurmak  │
  │       │                         │       │         │  için ONAY istiyorum"
  │      ╔╧═══════════════════════════════════════════════════════════╗  │
  │      ║  operatör "devam et" der → generator kaldığı yerden sürer  ║  │
  │      ╚╤═══════════════════════════════════════════════════════════╝  │
  │       │  ... video akmaya devam eder ...                             │
```

Diyagramdaki her ok **aksiyon defterine** (`action` tablosu) ve **devir
defterine** (`handoff` tablosu) tipli bir kayıt olarak düşer. Hiçbir şey ajan
sınırını serbest metin olarak geçmez.

### Neden bu sıra puan getiriyor

| Diyagramdaki an | Şartname kalemi |
|---|---|
| Sorulmadan haber verme | Otonomi — *"inisiyatif alma"* |
| Vardiya sorgusunun konuşmadan **önce** yapılması | Mimari — *"dinamik araç seçimi"* |
| "Bu açıdan göremiyorum" — uydurmak yerine sormak | Otonomi — *"doğru soruları sorma"* |
| Operatör düzeltmesinin rapora kadar yayılması | Mimari — *"bağlam yönetimi"* |
| Video bitmeden saha sisteminin aranması | Fonksiyonellik — *uçtan uca senaryo* |
| Hat durdurmanın onay istemesi | Mimari — insan döngüde |

---

## 6. Devir protokolü — açıklanabilirliğin omurgası

**Hiçbir şey ajan sınırını serbest metin olarak geçmez.** Her devir depoya
tipli bir kayıt olarak yazılır ([`gozcu/models.py::Handoff`](../../gozcu/models.py)):

```
 Handoff {
   ts            : 40.0                  ← videonun kaçıncı saniyesi
   source_agent  : "router"              ← perception | router | interpreter |
   target_agent  : "interpreter"           synthesizer | risk_analyst |
   reason        : "hız eşiği aşıldı…"     supervisor | reporter
   confidence    : 0.90
   payload_ref   : "window@40.0"
 }
```

Üç kazancı vardır:

1. **Puanlanan kalemin kanıtı.** Şartname §7 *"çok adımlı karar zincirleri"*ni
   ve *"bağlam yönetimi"*ni doğrudan puanlıyor; zincir ekranda okunuyor.
2. **Her sınırda bir test noktası.** Ajanlar birbirini mock'layarak
   sınanabiliyor.
3. **Açıklanabilirlik.** Şartname *"sistem çıktıları mümkün olduğunca
   açıklanabilir olmalıdır"* diyor; cevabı bir slayttaki iddia değil, ekranda
   izlenebilen bir karar zinciri.

Devrin kaynağı **dürüstçe** yazılır: yönlendiriciye hiç uğramamış bir zorunlu
örnek `source_agent="perception"` ile ve `[periyodik]` önekiyle deftere düşer —
böylece ölçüm katmanı, model kararlarını döngünün kendi kurallarından ayırt
edebilir ve manşet oranlar kirlenmez.

---

## 7. Veri modeli — SQLite tek dosya

Kurulum yok, tekrar üretilebilir: `git clone` ve tek komut. Vektör veritabanı
epizodik hafıza için ayrıdır (§8).

```
┌──────────────────────────────────────────────────────────────────────┐
│  gozcu/store.py — SQLite                                             │
│                                                                       │
│  ALGI                    AJAN KARARLARI            OPERATÖR          │
│  ┌─────────────┐        ┌──────────────┐        ┌───────────────┐    │
│  │observation  │        │ handoff      │        │ dialogue      │    │
│  │ ts,detect., │        │ kaynak→hedef │        │ rol, metin    │    │
│  │ signals     │        │ neden, güven │        └───────────────┘    │
│  └──────┬──────┘        └──────────────┘        ┌───────────────┐    │
│  ┌──────▼──────┐        ┌──────────────┐        │ correction    │    │
│  │window_record│        │ episode      │◄───────┤ hedef, alan,  │    │
│  │ taban? bütçe│───────►│ fazlar, özet │        │ eski→yeni     │    │
│  │ akıbet      │        │ katılımcılar │        └───────────────┘    │
│  └─────────────┘        │ ön risk,durum│        ┌───────────────┐    │
│  ┌─────────────┐        └──┬────────┬──┘        │ action        │    │
│  │interpretation│──────────┘        │           │ araç, param,  │    │
│  │ severity,    │        ┌──────────▼──┐        │ sonuç, aktör, │    │
│  │ anlar, token │        │ risk        │───────►│ onay durumu   │    │
│  └─────────────┘        │ seviye,     │        └───────────────┘    │
│                          │ gerekçe,    │                             │
│  ┌─────────────────┐    │ aday aksiyon│                             │
│  │episode_embedding│    └─────────────┘                             │
│  └─────────────────┘                                                 │
│                                                                       │
│  ╔═══════════════════════════════════════════════════════════════╗   │
│  ║  journal — küresel YAZMA SIRASI (seq)                         ║   │
│  ║  canlı besleme bu sıradan çizilir, `ts`'ten değil:            ║   │
│  ║  kesinti telafisi sonradan yazılan bir kaydı önceki bir video ║   │
│  ║  saniyesine koyabiliyor; `ts`'e göre dizmek onu yaşanmadığı   ║   │
│  ║  bir geçmişe taşırdı.                                          ║   │
│  ╚═══════════════════════════════════════════════════════════════╝   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 8. Epizodik hafıza

**Aranan şey epizot kayıtlarıdır** (metin), video parçaları değil. Her kayıt
zaten görü kademesinin betimlemesini, tespitleri ve sinyalleri taşır — damıtılmış
bir çok-kipli temsil. Video kodlayıcıya API erişimimiz yok ve **öyle bir şey
iddia edilmiyor.**

```
  "bu araçla daha önce bir olay olmuş muydu?"
              │
              ▼  gw.embed()  ·  bge-m3-embed, 1024 boyut
       ┌──────────────┐
       │ sorgu vektörü│
       └──────┬───────┘
              ▼  kosinüs
   ┌────────────────────────────────────────┐
   │  Qdrant — takım başına izole örnek     │   evren-vektor.ssyz.org.tr
   │  ön ek: team37 · koleksiyon: episodes  │   port 443 ZORUNLU, yalnız REST
   │  (anahtar yoksa süreç içi örneğe düşer │   (ön ek üzerinden gRPC yönlenmez)
   │   ve `memory_backend()` "local" der)   │
   └──────┬─────────────────────────────────┘
          ▼  top-k
   geçmiş epizotlar → Nöbetçi cevabı → **açık olaya kendiliğinden döner**
```

Yeniden sıralayıcı (`rerank`) **bilerek çağrılmıyor**: organizasyonun kendi
ölçümünde R@1 0,95'ten 0,55'e düşüyor. Alias `config.py`'da yalnız bütünlük
için duruyor.

---

## 9. Çıktı sözleşmesi

Şartname §5'in dört anahtarı **sözleşmedir**. Genişletilmiş katmanların
tamamı bir `try` içindedir; çöktüğünde dört anahtar yine üretilir.

```json
{
  "summary": "B-Hattı sevkiyat alanında istif aracı devrilmesi ve yaralanma riski gözlenmiştir.",
  "events": [
    {"time": "00:15", "event": "İstif aracı devrildi"},
    {"time": "00:20", "event": "Yerde hareketsiz kişi"}
  ],
  "risk": "Yüksek",
  "actions": ["Sağlık ekibini çağır", "Alanı güvenlik altına al"],

  "detail": {
    "episodes":          [ ... fazlarıyla epizotlar ... ],
    "risk_assessments":  [ ... seviye, gerekçe, önlenebilirlik ... ],
    "handoff_chain":     [ ... devir defteri ... ],
    "action_ledger":     [ ... çağrılan araçlar, onaylar ... ],
    "root_cause_report": { ... kök neden raporu ... }
  }
}
```

Üç kural:

- **`detail` fazlalıktır, yerine geçen şey değildir.** Şema:
  [`gozcu/models.py::PipelineOutput`](../../gozcu/models.py).
- **Bozulmuş koşuda `detail` `null` olur.** Dolu bir `detail` "o katmanlar
  gerçekten koştu" demektir; çöken bir koşuda bu iddia edilmez.
- **`actions[]` uydurulmuş cümleler değildir.** Liste, Risk Analisti'nin
  gerçekten bir araca bağladığı aday aksiyonlardan üretilir; insan okunur liste
  ile makine defteri birbirinden ayrışamaz.

Risk seviyeleri Türkçe kalır: `"Düşük" | "Orta" | "Yüksek" | "Kritik"`.

---

## 10. Hata ve kesinti mimarisi

Şartname bunu iki ayrı kalemden puanlıyor: Mimari (*"hata işleme"*) ve Otonomi
(*"beklenmedik durumlara karşı tepki"*). Demoda gateway **bilerek kesilir**
(`POST /api/run/{id}/gateway/cut`).

```
   NORMAL                          KESİNTİ                      DÖNÜŞ
  ┌────────┐                    ┌────────────┐              ┌────────────┐
  │ algı   │ yerel, etkilenmez  │ algı       │ ÇALIŞMAYA    │ algı       │
  │ döngü  │                    │ döngü      │ DEVAM EDER   │ döngü      │
  └───┬────┘                    └─────┬──────┘              └─────┬──────┘
      │ gw.ask("vlm")                 │ 3 deneme, sonra          │
      ▼                               ▼ is_degraded("vlm")=True  │
  ┌────────┐                    ┌────────────┐                   │
  │ görü   │                    │ pencere    │                   │
  │ yanıt  │                    │ ERTELENİR  │──────────────────►│
  └────────┘                    │ (deferred) │      catch_up()   │
                                └─────┬──────┘                   ▼
                                      │              ┌───────────────────────┐
                                      ▼              │ atlananlar yeniden    │
                                ┌────────────┐       │ işlenir, epizotlar    │
                                │ operatöre  │       │ late=True damgalanır: │
                                │ bozulma    │       │ "[Telafi — kesinti    │
                                │ BİLDİRİLİR │       │  sırasında atlanmıştı;│
                                └────────────┘       │  canlı uyarı değil.]" │
                                                     └───────────────────────┘
```

Aynı felsefe her katmanda tekrarlanır:

| Arıza | Davranış |
|---|---|
| Gateway yanıt vermiyor | 3 deneme; metin kademelerinde 90 sn, görü kademesinde 1800 sn zaman aşımı (ayrı — ölçülen bir asılma koşuyu dondurmuştu) |
| Yorumlayıcı `None` döndü | Kesinti ise ertelenir; bozuk JSON / kesilemeyen klip ise **ertelenmez** (yoksa her telafide yeniden sorulur ve hiç kurtulmaz) |
| Qdrant anahtarı yok | Süreç içi örneğe düşer, patlamaz; `memory_backend()` bunu `"local"` diye **söyler** |
| Genişletilmiş katman çöktü | Dört anahtar yine döner, `detail=null` |
| Denetim "uygunsuz" dedi | Yalnız not düşer — teslim **hiçbir koşulda** engellenmez |
| Algı katmanı hiç göremedi | "Kayda değer olay tespit edilmedi" **denmez**; körlük ayrı bir cümleyle bildirilir (`PerceptionHealth.blind_summary`) |

Son satır bir dürüstlük kuralıdır: *"baktım, bir şey yoktu"* ile *"hiçbir şey
göremedim"* aynı cümleyle anlatılamaz.

---

## 11. Operatör konsolu

`app.py` üç satırdır; ekran [`gozcu/ui/server.py`](../../gozcu/ui/server.py)'dedir.

```
   TARAYICI                                    SUNUCU
   ┌───────────────────────┐                   ┌──────────────────────────┐
   │ video + kutu katmanı  │◄── /video (Range) │ FastAPI                  │
   │ zaman çizelgesi       │◄── /detections    │                          │
   │ canlı besleme         │◄══ /events (SSE)  │ ┌──────────────────────┐ │
   │ karar zinciri         │    TAM durum,     │ │ run_pipeline()       │ │
   │ araç/onay çubuğu      │    kısmi çerçeve  │ │ AYRI İŞ PARÇACIĞI    │ │
   │ ölçüm paneli          │    YOK            │ │                      │ │
   └──────────┬────────────┘                   │ │ on_event(...) ───────┼─┼─►
              │ POST                            │ │   BLOKLAR ve bekler  │ │ operatör
              │ /say · /resume · /approve       │ │   → videonun saati   │ │ "devam"
              │ /step-mode · /gateway/cut       │ │     gerçekten durur  │ │ deyince
              └────────────────────────────────►│ └──────────────────────┘ │ sürer
                                                └──────────────────────────┘
```

Üç tasarım kararı:

- **SSE her zaman tam durum taşır.** Kısmi güncelleme yok; yeniden bağlanma
  bedavaya çözülür. (Gradio'nun 13 yuvalı protokolü eksik bir çıktıyı hata
  vermeden yutuyor ve jüriye bayat veri gösteriyordu — 27 Ağustos'ta bu yüzden
  emekliye ayrıldı.)
- **Harici ağ bağımlılığı sıfır.** CDN yok, font yok, analitik yok, ön yüz
  framework'ü yok — `gozcu/ui/web/` altındaki her şey depodan servis edilir.
  Final ağsız bir salonda.
- **Duraklama gerçektir.** `on_event` olayın tam anında, boru hattı iş
  parçacığında çağrılır ve orada bloklar. "Devam et" düğmesi bir animasyonu
  değil, generator'ın kendisini sürdürür.

---

## 12. Yerellik ve bağımsızlık

Şartname *"offline ve yerel ortamda çalışmalı, dış API veya kapalı servis
bağımlılığı olmamalı, vLLM benzeri yerel model servisleme kullanılmalı"* diyor.
Karşılığı:

| Bileşen | Nerede koşuyor |
|---|---|
| Algı katmanının tamamı (ffmpeg, YOLOE, ByteTrack, sinyaller, triyaj) | **Bizim makinemizde**, ağa hiç çıkmadan |
| Depo (SQLite) | **Bizim makinemizde**, tek dosya |
| Arayüz (FastAPI + statik dosyalar) | **Bizim makinemizde**, harici kaynak yok |
| LLM/VLM/gömme | Organizasyonun **EVREN** servisinde — 8 × NVIDIA H200 üzerinde **vLLM**, BF16, kuantizasyon yok |
| Vektör veritabanı | EVREN'in takım başına izole Qdrant örneği |

EVREN, şartnamenin yerellik koşulunun **organizasyon tarafından sağlanmış
hâlidir**: modeller yarışmanın kendi altyapısında, OpenAI uyumlu bir API'nin
arkasında. Ticari hiçbir kapalı servis (OpenAI, Anthropic, Google…)
kullanılmıyor; kod tabanında böyle bir istemci yok. Tek bağımlılık `openai`
Python **istemci kütüphanesidir** ve yalnızca OpenAI-uyumlu protokolü konuştuğu
için seçilmiştir — `base_url` yapılandırılabilir, kendi vLLM'imize
yönlendirildiğinde değişen tek şey `config.py`'daki bir satırdır.

---

## 13. Kod haritası

| Dosya | Sorumluluk |
|---|---|
| `app.py` | Üç satır: konsolu açar |
| `gozcu/config.py` | **Tek gerçek kaynak**: model kimlikleri, eşikler, adresler |
| `gozcu/frames.py` · `detect.py` · `track.py` · `signals.py` · `adapter.py` | Algı katmanı (yerel) |
| `gozcu/motion.py` | Kare farkı enerjisi — görü bütçesinin nişancısı |
| `gozcu/loop.py` | **Karar döngüsü** — pencereler, taban, bütçe, generator |
| `gozcu/gateway.py` | Kademeli model istemcisi, yeniden deneme, bozulma bayrağı |
| `gozcu/agents/router.py` | Yönlendirici — dikkat mekanizması |
| `gozcu/agents/interpreter.py` | Yorumlayıcı — klip → ciddiyet + anlar |
| `gozcu/agents/synthesizer.py` | Sentezleyici — pencereler → Epizot |
| `gozcu/agents/risk.py` | Risk analisti — yalnız okur, aday aksiyonları araca bağlar |
| `gozcu/agents/supervisor.py` | **Nöbetçi** — operatörün konuştuğu ajan |
| `gozcu/agents/reporter.py` | Raportör — kök neden raporu |
| `gozcu/guard.py` | Denetim — engellemez, not düşer |
| `gozcu/tools/field_systems.py` · `registry.py` | Yedi mock saha sistemi ve tek meşru kapısı |
| `gozcu/fixtures/` | Tesis dünyası: personel, ekipman, bakım geçmişi, arşiv |
| `gozcu/memory.py` | Epizodik hafıza (Qdrant) |
| `gozcu/store.py` · `models.py` | Depo ve paylaşılan sözleşme |
| `gozcu/report.py` | Dört anahtarın derlendiği yer |
| `gozcu/ui/` | Konsol (FastAPI + SSE + statik ön yüz) |
| `benchmark/` · `bench/` | Ölçüm kodu ve çıktıları |
| `tests/` | pytest — her ajan sınırı ve demo senaryosu |

---

## 14. Ölçülmüş rakamlar

Yalnız gerçekten ölçülenler. Kaynağı olmayan sayı bu belgede yer almaz.

**Algı katmanı** — `bench/perception.md`, elle etiketlenmiş 347 kare:

| Ölçüm | Değer |
|---|---|
| Varlık duyarlılığı | %99 |
| Sayım duyarlılığı | %93 |
| Sıfır tespit oranı | %2 |
| Gerçek zaman katsayısı | 0,35 (1,0 altı = canlı akışa yetişir) |
| Ortalama mutlak sapma | 2,3 kişi/kare |

**Gecikmeler** — 26 Ağustos canlı koşu (`gozcu/config.py` kaydı):
`router` 0,3–1,8 sn · `fast` 0,9–1,3 sn · `main` 0,8–2,6 sn · `guard` 0,1 sn ·
`vlm` 7,0–8,7 sn.

**Triyaj maliyeti:** 1,9 ms/kare — tek bir görü çağrısının (3.493 ms) **%1,3'ü**.

> ⚠️ **Uçtan uca KPI koşusu henüz tamamlanmadı.** `bench/kpi.json` bugün
> `status: "degraded"` okuyor: beş klipten dördü `unmeasured`, biri kısmî.
> Karar dağılımı, kritik olay yakalama oranı ve zaman damgası sapması
> **ölçülmedi** — bu belgede o sayılar bilerek boş bırakıldı ve sunuma da
> tahmin edilmiş bir yüzde konmayacak. Bölüm ⑦ bu koşu tamamlandığında
> yazılacak.

---

## 15. Bilinen sınırlar

Bunları yazmak, saklamaktan daha çok puan getirir — şartname
açıklanabilirliği doğrudan puanlıyor.

- **Nesne tanıyıcıda yangın/duman sınıfı yok.** YOLOE açık sözlüklü çalışıyor
  ama yangının ne sınıfı, ne izi, ne hızı var — yalnız görünür. Bu yüzden
  yangın klipleri ancak zorunlu görü örneklemesiyle yakalanabiliyor.
- **Görü kademesinin betimlemeleri genel geçer olabiliyor.** Fabrikaya özel
  ince ayrım (bir yükün düşmesi ile aracın devrilmesi) her zaman ayırt
  edilemiyor — demo senaryosundaki operatör düzeltmesi tam da bu yüzden
  gerçekçi bir düzeltmedir.
- **Canlı kamera / RTSP kapsam dışı.** `FrameSource` soyutlaması duruyor ve
  canlı bir kaynak aynı arayüze takılabilir, ama **test edilmiş bir canlı mod
  yoktur ve iddia edilmiyor.**
- **Top-K görü bütçesi canlı yayına genelleşmiyor** (§4c).
- **Hafıza epizot metnini gömüyor**, ham video parçasını değil (§8).
- **Ses/konuşma analizi yok.** Bas-konuş (STT) yalnız operatörün *girdisi*
  için, opsiyonel bir ekstra.
- **`events[]` olaydan önceki pencereleri taşımaz.** Bu kasıtlı: ölçülen bir
  arızada epizot, park hâlindeki bir kamyonun yanından geçen biri yüzünden
  00:00'da açılmış ve kazanın gerçekleştiği 40–50. saniyeyi yutmuştu.

---

## 16. Şartname eşleştirmesi

| Şartname beklentisi (§4) | Mimarideki karşılığı |
|---|---|
| Çoklu ortam anlama, sahne bütünlüğü | Epizot: pencereler kaynaşarak başlangıç/gelişim/sonuç fazlarına dönüşüyor (§4, §7) |
| Olay tespiti ve anlamsal yorumlama | Algı (düşük seviye) → Yorumlayıcı → Sentezleyici → Risk Analisti köprüsü (§3) |
| Zamansal farkındalık | Epizot fazları + `events[]` zaman damgaları + döngünün videonun saatinde ilerlemesi (§4) |
| Türkçe üretim ve özetleme | Bütün operatör metinleri Türkçe; risk seviyeleri Türkçe enum (§9) |
| Aksiyon önerisi ve karar desteği | Aday aksiyonlar **araca bağlı**; araçlar video ortasında çağrılıyor (§5) |
| Yapılandırılmış ve açıklanabilir çıktı | Dört anahtar + `detail`; devir defteri ekranda okunuyor (§6, §9) |
| Yerel çalışma ve bağımsızlık | §12 |
| Model servisleme (vLLM) | EVREN'de vLLM; kademeli yönlendirme kaynak optimizasyonu (§3, §12) |
| Performans ve ölçeklenebilirlik | Pencere başına ≤1 görü çağrısı; yerel triyaj çağrının %1,3'ü (§4) |
| Ölçümleme ve KPI | `benchmark/` + `bench/` — kısmî, §14'te dürüstçe işaretli |
| Minimum statik yapı | Taban *ne zaman soracağını* belirler; *neyin önemli olduğuna* model karar verir (§4a) |
| Açık kaynak ve şeffaflık | Apache 2.0, tekrar üretilebilir kurulum, açık fikstür veri kümesi |

---

### Kaynaklar

- Plan-of-record: [tasarım spec'i](../superpowers/specs/2026-08-22-agentic-gozcu-design.md)
- Yarışma kuralları: [sartname.md](../00-overview/sartname.md)
- Kararların gerekçesi: [decision-log.md](../05-decisions/decision-log.md)
- Teknoloji yığını: [tech-stack.md](../02-architecture/tech-stack.md)
- EVREN saha notları: [evren-gateway.md](../06-references/evren-gateway.md)
