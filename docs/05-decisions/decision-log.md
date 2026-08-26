# Decision Log

This reconciles the team's original technical research document against the 2026-08-13 mentor call. Where the call confirmed, corrected, or overrode something in the original plan, that's marked explicitly. Treat this file as the plan of record — it supersedes the research doc wherever they conflict.

## Competitive positioning

- **Original framing (research doc + early call):** differentiate by producing maximally detailed, multi-theory, multi-line interpretive reports (e.g. bomb-blast severity estimation) vs. competitors' assumed single-line reports; also an early assumption that *all* teams the professor advises are direct competitors on the same approach.
- **Correction:** the "all teams = same approach" assumption was wrong — there are 3 competition categories, and only category-3 teams (video-in, report-out) are actually comparable competitors. See [00-overview/project-overview.md](../00-overview/project-overview.md#competition-category-clarification).
- **Correction:** "more detail = more advantage" is not a safe framing on its own. Doing maximally deep interpretation across an *unbounded* domain (bomb analysis one moment, forklift speed the next, a kitchen mishap after that) increases failure surface even on simple cases, because there's no defined scope. **Decision: narrow the domain for the competition submission**, most likely to industrial/factory workplace-safety incidents, and explicitly state in the writeup that broader generalization is planned future work rather than claiming the broad scope as a current capability.
- **Status:** open — team acknowledged even "factory workplace accident" alone is still fairly broad; exact scope boundary still needs to be nailed down. Track in [action-items.md](action-items.md).

## Memory as the innovation angle

- **Original framing:** batch per-minute summaries into 10-minute chunks, then summarize batches of 10-minute chunks, to build a long-horizon running context — enabling the system to connect a morning event to an evening consequence.
- **Professor's correction to a supporting assumption:** the premise "AI already has memory as good as or better than ours" is false — current LLMs have underdeveloped memory (bounded by attention/context-window length, nothing more).
- **Professor's validation of the plan itself:** *because* that memory doesn't already exist in off-the-shelf models, building it ourselves is genuinely innovative — this is confirmed as the innovation angle, not just an assumption the team invented. Confirmed independently by the professor as "quite innovative" ("bayağı inovatif bir şey").
- **Mechanism, precisely:** not vector search magic — see [02-architecture/system-design.md](../02-architecture/system-design.md#how-the-embeddingretrieval-mechanism-actually-works-professors-explanation). Chunk video → embed chunks into a vector DB → embed text queries into the same space for semantic comparison → decode retrieved vectors back to text via a **generative model from a compatible model family**.
- **Status:** confirmed direction. This is the headline differentiator to build and to lead with in the pitch.

## Object detection model choice

- **Original plan:** YOLO for object detection, open-source, standard choice.
- **Confirmed by professor:** YOLO is sufficient and recommended specifically because embedding/VLM models (Qwen, Gemini, etc.) can tell you *that* an object is present but not *where* (pixel-level localization) — YOLO fills that gap, which matters for downstream speed/trajectory calculations (e.g. computing a forklift's actual turn speed from frame-to-frame pixel displacement, near-100% accurate, vs. an LLM's unreliable guess).
- **Explicitly rejected:** using raw OpenCV as the primary detector. Too low-level/manual; YOLO and comparable detectors are already built on OpenCV internals specifically so we don't reimplement that layer from scratch.
- **Open question:** whether the Facebook segment-editing model the professor mentioned already does what YOLO does for us — if so, consolidate to one model. Action item to evaluate, see [action-items.md](action-items.md).

## Video/VLM model shortlist

- **Confirmed:** Qwen2.5-VL (prefer newer versions over the older LAVA-style approach) — strong Turkish support, multimodal embedding capability, vLLM-compatible.
- **Added per professor, not in the original research doc:** JEPA / JEPA 2 (Meta) — small (~300–400M params, runs even on phone-class hardware), add to the video-understanding shortlist as a first-section item.
- **Added per professor:** Facebook's segment-editing model — evaluate alongside YOLO for potential consolidation.
- **Uncertain, flagged by professor himself as "recalling, not certain":** the Qwen-vs-Gemini multimodal-embedding architecture comparison and chronology (Qwen believed to predate Gemini's multimodal embedding by about a month; Gemini claims a single fused vector across modalities, Qwen was recalled as using separate token streams per modality before fusion). Worth an independent verification pass before citing this as fact anywhere external-facing (jury docs, README).

## Agentic framework

- **Confirmed:** LangGraph for orchestration — no objection from the professor; matches the "no static rule-based solutions" competition requirement.
- **Confirmed:** most of the surrounding pipeline (frame extraction, detection, vector DB wiring) can and should be built manually — professor's view is this is "not particularly hard," not a reason to reach for extra frameworks beyond LangGraph.
- **Note:** the research doc's original phrase "LangCraft" was a mishearing/typo for LangGraph in the live call — corrected throughout this vault.

## Local-only serving

- **Confirmed, non-negotiable:** no cloud service dependency for the text/video LLMs, including at the level of "which model variant" (must be a local/offline release, not a cloud-bound one). Ollama or LM Studio (llama.cpp-family backends) are acceptable local-serving options alongside vLLM.
- **Confirmed:** JEPA's small footprint means VRAM is a non-issue for that model specifically; the constrained resource is really the LLM/VLM pair (see [03-planning/hardware.md](../03-planning/hardware.md)).

## Turkish video model (stretch goal)

- **New idea from professor, not in original scope:** attempt to produce a Turkish-specialized video model derived from Qwen's video model (adapting tokenizer + embeddings), drawing on the professor's own PhD-era model-building experience. Explicitly framed as "if time allows" — a stretch goal, not a committed deliverable. Tracked in [03-planning/roadmap.md](../03-planning/roadmap.md#stage-5-stretch-features).

## Day 1 checkpoint — local VLM run (2026-08-17)

Satisfies the "run at least one VLM locally on at least one image/video" checkpoint from [Roadmap sequencing](#roadmap-sequencing) below. Ran Qwen2.5-VL-3B-Instruct-4bit locally via mlx-vlm (Mac, Apple Silicon — see [03-planning/hardware.md](../03-planning/hardware.md) for why vLLM itself isn't viable on Mac) against a real factory-fire video.

- **Confirmed root cause of a garbage/repetition failure mode:** feeding the model native-resolution frames (2560×1440 from a "4K" source file) breaks single-image generation into pure repeated-token garbage (`!!!!...`), regardless of decoding params. Downscaling to ~896×504 fixed it completely. **Decision: frame downscaling to ~896px width is now a mandatory pipeline step**, not an optimization — this isn't about speed, generation is simply broken above some undetermined resolution threshold with this model/quant.
- **Confirmed:** whole-video mode (passing all sampled frames in one call, `--video` + `--fps`) causes content collapse — the model correctly identifies the scene once, then repeats near-identical text across the rest of the requested timeline items instead of describing distinct moments.
- **Confirmed:** per-frame independent captioning (one image, one caption, looped) avoids that collapse — captions vary and stay roughly on-topic (fire, smoke, wood structure) frame to frame.
- **New risk, more serious than the resolution bug — hallucinated specifics:** per-frame captions repeatedly invented a location (flip-flopping between South Korea, South Africa, South Asia, Georgia across frames of the same scene) and fabricated precise-sounding casualty/statistics ("24 people survived," "12 dead, 46 injured," "$471,853 donated") with no basis in the actual pixels. The model is pattern-matching to "factory fire news article" templates, not describing observed content.
- **Why this matters:** Stage 3's risk-assessment/action-recommendation module ([02-architecture/model-strategy.md](../02-architecture/model-strategy.md)) cannot consume raw VLM narration unconstrained — an ungrounded model confidently stating fake casualty counts is a reliability problem for a safety-relevant system, not a minor accuracy gap. Reinforces (doesn't just theoretically support) the existing plan to ground interpretation in YOLO detections ([Object detection model choice](#object-detection-model-choice)) rather than trusting free-form VLM text alone.
- **Status:** baseline capability established (scene-type recognition works even at 3B/4-bit). Open follow-up: test whether an explicit "describe only what's visible, do not invent counts/locations/statistics" prompt constraint suppresses the hallucination behavior — not yet tested. Tracked in [action-items.md](action-items.md).

## Day 1 checkpoint — local YOLO run (2026-08-17)

Satisfies the "run YOLO at least once locally" checkpoint from [Roadmap sequencing](#roadmap-sequencing). Ran stock `yolo11n.pt` (COCO-pretrained, no fine-tuning) on the same factory-fire video used for the VLM checkpoint above.

- **Confirmed:** across all 865 detected frames, YOLO reliably detects **person** (1005 boxes) — this is the useful, actionable signal for a safety/accident system (human presence and pixel location near a hazard), and matches why YOLO was chosen over VLM-only detection (see [Object detection model choice](#object-detection-model-choice)).
- **Expected, not a bug:** YOLO has no COCO class for fire/smoke/burning-structure, so it forces the hazard into the nearest visually-similar known class — **"train"** (653 boxes) — for most of the video. A stock general-purpose detector doing this outside its training distribution is expected behavior, not a defect.
- **Implication:** stock COCO YOLO is usable now for person-localization, but not for hazard classification itself. Sharpens the existing open question about the Facebook segment-editing model / whether a dedicated fire-smoke detector or fine-tuned YOLO classes are needed — this run is concrete evidence that gap exists, not just a theoretical concern.
- **Status:** baseline capability established. Person detection is reliable enough to build on for Stage 1; hazard-class detection needs either fine-tuning or a second specialized model before it's trustworthy.

## Day 1 checkpoint — local SAM2 run (2026-08-17)

Satisfies the "run a segmentation model at least once locally" checkpoint. Ran `sam2.1_t.pt` (Meta/Facebook AI Research's SAM 2, tiny variant, via Ultralytics) in automatic "segment everything" mode on one downscaled frame from the factory-fire video — best available match for the professor's vaguely-recalled "Facebook segment-editing model" (see [Video/VLM model shortlist](#object-detection-model-choice); exact model name was never confirmed by the professor, this is our best identification, not verified against the original source).

- **Confirmed:** SAM2 runs locally and produces genuine region-level masks (8 distinct segments on the one test frame) without any prompt — works as expected for "segment everything" mode.
- **New infra finding:** inference ran on **CPU**, not Apple's Metal (MPS) backend — 41.8s for one 1024×1024 frame via Ultralytics' default device selection. At that rate, segmenting a full video frame-by-frame is impractical without forcing MPS/GPU device explicitly. Not yet investigated why MPS wasn't picked up automatically.
- **Status:** baseline capability established. Not yet evaluated against the actual open question (whether it subsumes YOLO's role) — that comparison needs the same video run through both and a deliberate side-by-side, not yet done.

## Day 1 checkpoint — local V-JEPA 2 run (2026-08-17)

Satisfies the "run JEPA at least once locally" checkpoint. Ran `facebook/vjepa2-vitl-fpc64-256` (ViT-L, 64-frames-per-clip variant — the base encoder is only published at fpc64, not fpc16) via `transformers.AutoModel` on 64 frames (~2 fps) sampled from the factory-fire video.

- **Confirmed:** runs locally, produces real embeddings — encoder output shape `(1, 8192, 1024)`, predictor output same shape. No text/hallucination risk here by construction — it's a pure embedding model, not a generative one, which matches why it's positioned in the architecture as a lightweight building block for the memory/vector-DB mechanism ([system-design.md](../02-architecture/system-design.md#how-the-embeddingretrieval-mechanism-actually-works-professors-explanation)), not as a scene-interpretation model like Qwen2.5-VL.
- **Note:** despite the "~300-400M params, runs on phone-class hardware" framing in the original research (see [prior-art.md](../01-research/prior-art.md)), the ViT-L variant used here is larger than that description suggests — smaller JEPA variants weren't tested in this checkpoint. Worth reconciling params-vs-variant before citing the phone-class-hardware claim externally.
- **Status:** baseline capability established (loads, runs, produces sane-looking embedding statistics). Not yet tested: whether these embeddings are actually useful for the planned retrieval mechanism (e.g. do semantically similar video chunks land close together in this space) — that's a real validation step still ahead, not just running the model once.

## Roadmap sequencing

- **Original open question (from Üveys, on the call):** "where do we even start — jumping straight into LangGraph doesn't seem to make sense; what's the roadmap?"
- **Professor's answer, confirmed as the plan of record:** don't add pipeline complexity yet. First, quickly:
  1. Study embedding models (Qwen's embedding specifically) — how vectors are processed inside the model.
  2. Every team member runs at least one VLM locally on at least one image (video if possible) before the next meeting, and documents what the code is doing step by step.
  3. Establish **current baseline capability** — what can the system actually do *right now* — before planning what to build next. Explicit warning against skipping this: a system that appears to work brilliantly on one example is not evidence of anything if you don't know your baseline; a plausible failure could still lose the whole project.
  4. Keep the gap between meetings short — don't over-extend the research phase.
- **Status:** confirmed, supersedes jumping directly into Stage 1 of the original roadmap. See [action-items.md](action-items.md) for the literal checklist.

---

## 2026-08-22/23 — Yarışma sprinti kararları

Bu bölüm, dört günlük sprint öncesinde alınan ve **yukarıdaki her şeyi geçersiz
kılan** kararları tutuyor. Plan-of-record artık
[tasarım spec'i](../superpowers/specs/2026-08-22-agentic-gozcu-design.md).

### Girdi: yüklenen video dosyası. Canlı akış kapsam dışı

- **Önceki yön:** gerçek zamanlı RTP/RTSP kamera işleme ana eksen olacaktı.
- **Karar:** şartnamenin senaryosu net — *"Operasyon sahasında bir video sisteme
  yüklenir."* Fonksiyonellik (%35) *"belirtilen senaryoların uçtan uca
  implementasyonu"*nu puanlıyor. Canlı akış test edilmeden iddia edilmiyor;
  RTSP tamamen kesildi.
- `FrameSource` soyutlaması yine de var — karar döngüsünün kareleri okuma yolu o.
  Dokümantasyon "canlı kaynak aynı arayüze takılır" diyebilir, "test edilmiş
  canlı mod" diyemez.

### Kararlar olay anında veriliyor, rapor sonrasında değil

- **Tartışma:** yüklenen bir videoda tool çağrıları ne zaman olmalı?
- **Karar:** videonun kendi zaman çizelgesinde, kritik anda. Sistem orada durup
  operatörle konuşuyor, saha sistemini arıyor — video bitmeden.
- **Gerekçe:** rapor sonrası tool çağırmak *özetleme* olur. Şartnamenin
  puanladığı *çok adımlı karar zincirleri*, *dinamik araç seçimi* ve *diyalog
  sırasında inisiyatif alma* kalemlerinin üçü de karar anı gerektiriyor.
- **Sonucu:** `KararDongusu.calistir()` bir generator; yükseltmede `yield`
  edip duruyor. Bu olmadan tez sadece retorik kalırdı.

### Alan: savunma sanayi tesisi iş güvenliği

- Şartname *"savunma sanayi tesisleri veya saha operasyonları"* diyor ve verdiği
  tek somut örnek forklift devrilmesi + yerde hareketsiz kişi + personel
  toplanması — yani bir üretim tesisi.
- Teknik kapsam fabrika iş güvenliği; dil, saha sistemleri ve sunum tesis
  kılığında. Bu, hocanın "kapsam çok geniş" uyarısının kapanışı.

### Modeller organizasyonun gateway'inde

- **Önceki plan:** yerel GPU'da vLLM, RTX 3090/4090 sınıfı donanım, bulut GPU
  bütçesi.
- **Gerçek:** organizasyon bütün modelleri kendi sunucusunda ayağa kaldırıp
  OpenAI uyumlu bir gateway veriyor. Yerel GPU yok, vLLM kurulum yükü yok.
- **Sonucu:** her model çağrısı ağ üzerinden paylaşımlı bir kaynağa gidiyor.
  Her kareyi görsel modele sokmak imkânsız — tetiklemeli yorumlama zorunluluk
  oldu. Ve bozulmuş mod tasarımın parçası hâline geldi.

### Topoloji: süpervizör + uzman alt-ajanlar

- **Değerlendirilen alternatifler:** (a) tek ReAct ajanı, (b) 4 bağımsız ajan,
  (c) 1 süpervizör + uzmanlar tool olarak.
- **Karar: (c).** Belirleyici argüman: puanın %20'si diyalog, ve bu topolojide
  diyalog ajanı sistemin merkezinde duruyor — (b)'de zincirin sonundaki bir
  tüketici olurdu. (b)'nin bütün mimari iddialarını (uzmanlaşma, çok adımlı
  zincir, devir) bir hareketli parça eksiğiyle koruyor.

### Framework kullanılmıyor

- **Önceki plan:** LangGraph + LangMem.
- **Karar:** düz Python. Süpervizör döngüsü ~60 satır.
- **Gerekçe:** üç günde öğrenme eğrisi riski, ve şartnamenin puanladığı şey
  framework adı değil *dinamik araç seçimi*, *bağlam yönetimi*, *çok adımlı
  karar zincirleri*. Kod kalitesi de ayrı bir kalem; okunabilir düz kod burada
  daha iyi savunuluyor.
- Hafıza için LangMem yerine SQLite + gömme + numpy kosinüs. Vektör DB yok:
  bir vardiya birkaç yüz epizot demek, kaba kuvvet anlık.

### Algı katmanı donduruldu

- `frames.py`, `detect.py`, `track.py`, `signals.py` yarışma boyunca değişmiyor.
- Bilinen kalite açıkları (nesne tanıyıcıda yangın/duman sınıfı yok, VLM
  açıklamaları genel geçer) **kabul edildi** ve dokümantasyonda "bilinen
  sınırlar" olarak yazılacak.
- **Gerekçe:** puanın %70'i ajan mimarisi ve senaryo bütünlüğünde. Görüntü
  işleme kalitesi puan cetvelinde ayrı bir kalem değil.

### Hafıza: video değil, olay kayıtları gömülüyor

- **Hocanın önerisi:** video segmentlerini vektör uzayına gömmek.
- **Karar:** epizot kayıtlarının metnini gömüyoruz. Her kayıt zaten görsel
  yorumu, tespitleri ve sinyalleri içeriyor — damıtılmış bir temsil.
- **Gerekçe:** API'den bir video kodlayıcıya erişimimiz yok ve olmayan bir şeyi
  iddia etmiyoruz. Bu haliyle de tez ayakta: bir olayı çok daha öncekine
  bağlamak, context penceresine sığandan fazlasını hatırlamak.

### Görev 00 tamamlandı — test altyapısı ve yerel gateway (2026-08-23)

`f45259c`. Diğer 18 görev açıldı. Kalıcı olan kararlar:

- **`mlx-vlm` opsiyonel oldu** (`mac` extra'sı). Gerekçe sanıldığı gibi "Linux'ta
  wheel yok" değildi — `mlx 0.32.0` `manylinux_2_35` wheel'i yayınlıyor ve
  `mlx-metal` zaten darwin işaretli. Gerçek gerekçe: glibc 2.35 öncesi ve musl
  dağıtımlar, ve Apple Silicon dışında hiçbir işe yaramayacak ~1 GB'lık indirme.
  **Sonucu:** Mac'te günlük komut `uv sync --extra dev --extra mac`; yalnız
  `--extra dev` `mlx-vlm`'i siler.
- **Yerel gateway yolu (b) seçildi.** Organizasyonun gateway'i 23 Ağustos'ta
  hazır değildi. `scripts/gen-litellm-config.py` yedi kademeyi tek yerel uca
  yönlendiriyor; varsayılan arka uç Ollama (`localhost:11434`, `qwen2.5:7b`).
  Adres geldiğinde değişecek tek yer `.env`.
- **`.env` yalnız `uv run --env-file .env` ile okunuyor.** `python-dotenv`
  bilinçli olarak eklenmedi. `--env-file` dosya yoksa hata verdiği için
  test/doğrulama yolunda kullanılmıyor.
- **`litellm[proxy]`, düz `litellm` değil.** Düz paketin CLI'ı `--config` ile
  ölüyor.
- **Doğrulamalar PATH'e güvenmiyor.** `~/.pyenv/shims/pytest` yüzünden
  `uv run pytest --version`, venv boşken bile başarılı oluyor. Paket varlığı
  `uv.lock` ve `.venv/bin` üzerinden ölçülür.
- **Worktree kullanılmıyor**; ana çalışma ağacında dal açılıyor. Doğrulamalar
  `.venv`'i doğrudan okuyor.
- **Görev 03'e borç:** üretici yedi model adını kopyalıyor; 03 `MODELS`'i
  `gozcu/config.py`'a eklediğinde üretici oradan import etmeli.


### Görev 01 tamamlandı — paylaşılan sözleşme (2026-08-23)

`fdfd393`. `gozcu/models.py` indi, 4 test yeşil. Kalıcı olan kararlar:

- **Beşinci anahtar `detail`, `ayrintili` değil.** Bu spec (§4) ve Görev
  01/17 dosyaları `ayrintili` yazıyordu; ama sınıf adı `Detail` ve bütün alt
  anahtarlar (`episodes`, `risk_assessments`, `handoff_chain`,
  `action_ledger`, `root_cause_report`) çoktan İngilizceye geçmişti — spec'in
  gösterdiği Türkçe alt anahtarlar (`epizotlar`, `devir_zinciri`, …) artık
  hiçbir yerde yok. Yarım kalmış bir geçişti. CLAUDE.md'nin değişmez kuralı
  ("JSON anahtarı … İngilizce") ve anahtarı adıyla `detail` diye anması
  belirleyici oldu. **Şartnamenin dört anahtarı bundan etkilenmiyor** —
  `summary`/`events`/`risk`/`actions` zaten şartname tarafından dayatılıyor.
  Görev 01 ve 17 dosyaları güncellendi; bu spec bölümü bayat.
- **Sözleşme ile donuk algı katmanı arasında ad uyuşmazlığı var, bilerek.**
  `Detection` `label`/`box: tuple[float, ...]` diyor; `detect.DetectedObject`
  ve `track.TrackedObject` `class_name`/`bbox: tuple[int, ...]` kullanıyor.
  Algı katmanı donuk olduğu için sözleşme onun adlarına uydurulmadı;
  **çeviriyi Görev 17'nin adaptörü yapacak** (`class_name→label`,
  `bbox→box`, int→float). `Signals` ise `signals.FrameSignals` ile birebir,
  düz kopya — tek istisna `gathering`, algı katmanında hesaplanmıyor,
  Görev 17 `person_count >= 3` ile türetiyor.
- **`extra="forbid"` tek yerden geliyor.** Bütün tipler `Base`'i genişletiyor.
  Yeni tip eklerken `BaseModel` yazılırsa şema sessizce gevşer — bu yüzden
  sözleşmeye giren her tip `Base`'den miras alır.
- **`gozcu/schema.py` yerinde bırakıldı.** İçindeki `FrameEvent` /
  `PipelineResult` donuk algı yolunun (`interpret.py`, `run.py`) hâlâ
  kullandığı tipler; `models.py` onların yerine geçmiyor. Görev 17
  entegrasyonu bittiğinde ölü kalırsa orada silinir.

### Görev 02 tamamlandı — olay deposu (2026-08-23)

`6dc96bf` (depo) + `998487d` (denetçi ve süpürme). 6 test yeşil, toplam 13.

- **Denetçinin Türkçe kimlik kontrolü delikti ve gerçek bir hatayı kaçırdı.**
  `scripts/check-tasks.py` deseni `(?![\w])` ile bitiyordu; `_` de `\w` olduğu
  için `epizot_embedding` ve `test_epizot_guncelle` "temiz" raporlanıyordu.
  Sınır artık `[A-Za-z0-9]` — `_` ayraç sayılıyor. Delik kapanınca **altı görev
  dosyasında 17 ihlal** ortaya çıktı (02, 04, 06, 07, 14, 15); hepsi
  yeniden adlandırıldı. **Ders:** yeşil bir denetçi, denetçinin kapsamı kadar
  değerli. Yeni bir kural eklerken önce onu ihlal eden bir örnekle kırmızı
  olduğunu gör.
- **Türkçe adların sakladığı dört gerçek kusur** (hiçbiri test tarafından
  yakalanmıyordu, hepsi kendi görevinin gününde patlayacaktı):
  1. `02` — `embeddings()` var olmayan `epizot_embedding` tablosunu okuyordu.
  2. `05` — `_obs(ts, kisi=0, hiz=None)` yardımcısı, iki çağrı yerinde
     `person_count=1` ile çağrılıyordu → `TypeError`.
  3. `07` — `_synthesise` geri düşüşü `s.phase = "gelisim"` atıyordu; şema
     `development` istiyor → `ValidationError`.
  4. `05`/`07` — karar tablosu yönlendirici enum'unu `create_episode` diye
     anıyordu; o bir `Store` metodu, enum değeri `open_episode`.
  Ayrıca `15`'in imza listesi `AgentName`'i Türkçe sayıyor ve var olmayan
  alanlar (`Yorum.token`, `Epizot.baslangic_ts`, `Devir.kaynak_ajan`) adlandırıyordu.
- **Depo tek açık epizot garantisi vermiyor.** `open_episode()` açık satırların
  sonuncusunu döndürüyor. Bu değişmezi **Görev 05 koruyacak**, depo değil.
  Aynı boşluk Görev 14'ün "tam olarak bir bekleyen onay" beklentisinde de var.
  Eş zamanlı iki olayın desteklenip desteklenmeyeceği ürün kararı olarak açık —
  şimdilik tek olay varsayılıyor, çünkü görev dosyalarının tarif ettiği bu.
- **`_insert` yer tutucuları `["?"] * n` ile üretiyor.** Dosyadaki taslak
  `"?" * n` yazıyordu; bu string tekrarı, `", ".join` da onu karakter karakter
  birleştiriyor. İki yuvada tesadüfen doğru sonuç veriyor, üçüncüde bozuluyor.

#### Denetçinin kök sınırı: kara liste asla tamamlanmaz

Türkçe kimlik kontrolü sabit bir kök listesine bakıyor. Sınır düzeltildikten
sonra bile listede olmayan kelimeler elendi: Görev 16'nın imza bloğu
`Store.episodes()`'i `.baslangic_ts, .ozet_tr, .on_risk, .durum` diye
belgeliyordu — şemadaki adlar `start_ts, summary_tr, preliminary_risk, state`.
Konsolu yazan kişi `AttributeError` alacaktı ve o kişi 25 Ağustos'ta bu kod
tabanını ilk kez görüyor. Aynı blokta `talk(operator_metni)` ve
`approve(..., onay)` vardı; Görev 14 ile birlikte düzeltildi.

**Kalıcı çözüm kara listeyi büyütmek değil:** denetçi, görev dosyalarındaki
`Model.alan` referanslarını `gozcu/models.py`'daki gerçek alanlara karşı
doğrulamalı. O zaman kontrol "bu kelime Türkçe mi" değil "bu alan var mı"
olur — ve Türkçe olmayan uydurma alan adlarını da yakalar. Henüz yazılmadı.

### Görev 03 tamamlandı — kademeli gateway (2026-08-23)

`2db4dad`. 18 test yeşil, toplam 31.

#### Bozulma sözleşmesi değişti: her kademe bozulabilir

- **Önceki tasarım:** yalnız `vlm`, `fast`, `rerank` bozulabilir; diğer her
  kademe `GatewayError` atar.
- **Sorun:** Görev 06 `router`, Görev 12 `main` kademesini çağırıyor ve
  **ikisi de zarifçe bozulduğunu varsayan testler taşıyordu** — o testler
  yalnız gateway bir `Mock` olduğu için geçiyordu. Gerçek gateway'de
  `route()` ve rapor üretimi yakalanmamış `GatewayError` ile düşecekti.
  Görev 13'ün `degraded` dalı da aynı sebeple ölü koddu.
- **Karar: her kademe bozulabilir.** `ask()` kesintide istisna atmaz; boş
  içerikli `degraded=True` bir `Response` döner. `embed()` `[]` döner.
- **Gerekçe:** CLAUDE.md'nin çıktı sözleşmesi kuralı — şartnamenin dört
  anahtarı genişletilmiş katmanlar çökse bile üretilir. Bir kademe kesintisi
  bir koşuyu düşürüyorsa o kural tutulamaz. Demo gününde zayıf ama geçerli bir
  rapor, hiç rapor olmamasından iyidir.
- **`GatewayError` korundu ama anlamı değişti:** artık yalnız kayıtlı olmayan
  bir kademe adı istendiğinde atılıyor — yani kesinti değil, yazım hatası.
  `except GatewayError` bundan sonra kesinti işleme *değildir*.

#### `is_degraded()` kademe başına oldu — global bayrak canlı bir hataydı

Eski hâli `bool(self._broken)` döndürüyordu. Görev 03'ün kendi metni
reranker'ın gerçek gateway'de 400 vermesini **beklenen** sayıyor; o ilk
başarısızlık global bayrağı latch'liyor, Görev 05 bunu "görü katmanı çöktü"
diye okuyor, her pencereyi erteliyor ve `catch_up()` kalıcı olarak hiçbir şey
yapmıyor. Yani *bozulması beklenen* bir kademe bütün sistemi durduruyordu.
Artık `is_degraded(tier)` kademe sorar, `is_degraded()` "herhangi biri" demek
ve konsol/KPI göstergesi içindir. Görev 05 `is_degraded("vlm")` çağıracak.

Bununla birlikte iki küçük kusur daha kapandı: `inject_failure()` artık önceki
enjeksiyonun yerine geçiyor ve kaydedilmiş bozulmayı temizliyor (bayat bir
kademe adı yeni enjeksiyonun kapsamını sessizce genişletiyordu), ve bozulmuş
yanıtlar gerçek `latency_ms` taşıyor (eskiden 0 idi, KPI'yı yanıltırdı).

#### Model kimlikleri tek yerde toplandı

Görev 00'ın bıraktığı borç kapandı: `scripts/gen-litellm-config.py` yedi model
adını kopyalamak yerine `gozcu.config.MODELS`'i import ediyor. **Gotcha:**
`pyproject.toml` `package = false` diyor, yani `gozcu` yalnız pytest'in
rootdir eklemesiyle import edilebiliyor; script'in kendi başına koşabilmesi
için depo kökünü `sys.path`'e eklemesi gerekti. Üretilen `litellm-config.yaml`
değişiklik öncesiyle bayt bayt aynı.

**Açık ürün sorusu:** yedi model takma adı hâlâ doğrulanmamış tahmin.
Organizasyonun gateway'i görülmedi ve Görev 00'ın uyardığı gibi bir harf
hatası sessiz 400 demek. Artık tek dosyada (`config.py`) ve `GOZCU_MODEL_*`
ile geçersiz kılınabiliyor, ama gerçek liste 25 Ağustos'tan önce alınmalı.

### Görev 05 tamamlandı — olay anında karar döngüsü (2026-08-23)

`cf7b81e`. 17 test yeşil, toplam 48. 23 Ağustos bloğu kapandı.

#### Tek açık epizot değişmezini **döngü** koruyor — başka hiçbir katman korumuyor

Görev 02'nin notu bu boşluğu bırakmıştı, Görev 05'in metni de "döngü korur"
diyordu; **ama kodu `store.open_episode()`'u hiç çağırmıyordu.** Yükseltme dalı
ve `catch_up` koşulsuz `"open_episode"` yazıyordu. Somut senaryo: 00:00'da
yükseltme A epizotunu açar, 00:10'da ikinci yükseltme B'yi açar,
`open_episode()` artık B'yi döndürür, sonraki kapanış B'yi kapatır ve **A
sonsuza dek açık kalır** — şartnamenin `events[]` listesi aynı forklifti iki
kez sayar. Üç katman da (yönlendirici promptu, döngü, depo) korumasızdı ve
hiçbir test kapsamıyordu.

Artık `DecisionLoop._resolve()` açık epizot varken `open_episode` kararını
`update_episode`'a indiriyor. **Bu tek koruma noktası:** depo izin veriyor,
prompt yasaklamıyor. Görev 07 `open_episode`'un daima yeni epizot açtığı,
`update_episode`'un `store.open_episode()`'a kaynaştığı kuralını bozarsa
değişmez sessizce düşer.

#### Yield kanalı ikiye ayrıldı: `LoopEvent(episode, late)`

`run()` canlı yükseltmeleri, sondaki `catch_up()` ise kesinti sonrası geri
doldurulan epizotları **aynı kanaldan** veriyordu; Görev 17 de yield edilen her
şeye `supervisor.escalate()` çağırıyordu. Yani kesinti sırasında kaçırılıp
sonradan kurtarılan bir olay, operatöre **şimdi oluyormuş gibi** duyurulacaktı.

Karar: geç keşfedilen bir olayı saklamak bir güvenlik sistemi için kabul
edilemez, bayat bir olayı canlı kriz gibi duyurmak ise yanıltıcı. Orta yol
zorunlu — duyuruluyor ama damgalanıyor. `models.py` `LoopEvent` kazandı
(CLAUDE.md eksik tipin oraya eklenmesini zaten söylüyor). İki tüketici de
(16, 17) henüz yazılmamıştı, yani bu değişikliğin bugünkü maliyeti sıfır.

#### Erteleme yalnız gerçek kesintide

Döngü `interpretation is None` gördüğü her pencereyi erteliyordu. Ama
`interpret` bozuk JSON'da ve eksik karede de `None` dönüyor: o pencereler
kalıcı olarak kuyruğa giriyor ve **her `catch_up`'ta VLM'e yeniden soruluyordu**
— hiç kurtulmayan bir döngü. Üstelik `close_episode` pencereleri tasarım gereği
hiç yorumlanmıyor, yani hepsi ertelemeye uygun görünüyordu. Artık koşul
`needs_vision and interpretation is None and is_degraded()`.

#### Demo beat 6 iki sürücüde de ölüydü

`is_degraded` enjekte edilen sıfır argümanlı bir callable ve varsayılanı
`lambda: False`. **Ne Görev 16 ne Görev 17 onu geçiriyordu** — dolayısıyla
`deferred` hiç dolmuyor, `catch_up()` ölü kod, "bağlantı kesilir, gelince
açığı kapatır" beat'i sessizce hiçbir şey yapmıyordu. Jüriye gösterilecek
kesinti hikâyesi buydu. İki görev dosyasına da
`is_degraded=lambda: gw.is_degraded("vlm")` yazıldı; kademe argümanı zorunlu.

#### Tekrarlayan desen: sahte iş birlikçi sözleşmeyi onaylıyor

Bugün üçüncü kez: bir test yalnızca iş birlikçi `Mock` (ya da burada
`object()`) olduğu için geçiyor, gerçek nesnenin şekli farklı. Görev 06/12'de
bozulma, Görev 02'de gömme yolu, burada `interpret=lambda w: object()` —
gerçekte `Interpretation | None` dönüyor ve `synthesize` `.description`
okuyor. **Kural:** enjekte edilen sahte iş birlikçi gerçek tipin şeklini
taşımalı; `object()` ve şekilsiz `Mock` sözleşme kanıtı değildir.

#### Görsel kademe satır içi base64 alıyor — çünkü gateway'in varlık sebebi bu

**Açık soruydu, kapandı (Üveys, 23 Ağustos).** Görev 04 kareleri
`data:image/jpeg;base64,...` olarak gönderiyor; gateway'in bunun yerine
çekilebilir bir URL isteme ihtimali sorulmuştu.

**Cevap: satır içi almak zorunda.** Organizasyon modelleri kendi sunucusunda
ayağa kaldırıyor, çünkü amaç **verinin yerelde kalması**. URL isteyen bir
gateway, görüntüyü almak için dışarıya çıkmak ya da kareleri erişilebilir bir
yere koymamızı istemek zorunda kalırdı — her iki durumda da veri zaten dışarı
sızmış olurdu ve gateway'in varlık sebebi ortadan kalkardı. Yani bu bir tahmin
değil, mimarinin kendi öncülünden çıkan sonuç.

**Kalan risk, küçük ama sıfır değil:** öncül doğru olsa bile içerik biçimi
(çok parçalı `content` dizisi, `image_url` alanı) sunucuya göre değişebilir.
Bozulursa Görev 04'ün `_message` kurucusu tek düzeltme noktası; gateway'in
kendisi ya da başka hiçbir modül değişmez.

### Görev 04 tamamlandı — yorumlayıcı adaptörü (2026-08-23)

`89f7c21`. 34 test yeşil, toplam 84.

#### Strict şema: sistemin sessizce hiçbir şey üretmemesine bir alan uzaklıktaydı

`_VisionResponse.notable_event`'in varsayılanı var, dolayısıyla pydantic onu
`required` listesinden düşürüyor. OpenAI **strict** structured outputs ise her
alanın `required` içinde olmasını şart koşuyor. Zinciri sonuna kadar izle:
gerçek gateway 400 → denemeler tükeniyor → `degraded=True` → yorumlayıcı
**her pencere için** `None` → `DecisionLoop` her pencereyi erteliyor → sistem
çalışıyor görünüyor ve hiçbir şey üretmiyor. **Beş testin hepsi yeşildi**,
çünkü `gw = Mock()` şemayı hiç kullanmıyordu.

Düzeltme zaten kod tabanında vardı: `gozcu/interpret.py:136-142` bu
`required` geçersiz kılmasını taşıyor ve orada olma sebebi ampirik. Görev 04
onu atmıştı. Artık `strict_schema()` tek kapı: her alanı `required` yapıyor,
`additionalProperties: false` koyuyor, `maxLength`'i siliyor (strict arka
uçlar yaygın olarak reddediyor; sınır pydantic modelinde kalıyor, kesme
Python'da yapılıyor) ve dizileri sınırlıyor.

> **⚠️ Bu paragrafın kuralı Görev 06'da aşıldı.** Burada konan
> "her çağıran `strict_schema()`'i çağırsın" kuralı unutulabilir olduğu için
> düştü; sertleştirme artık `Gateway.ask()`'in içinde ve kimse onu elle
> çağırmıyor. Aşağıdaki Görev 06 girdisine bak.

Test mutasyonla doğrulandı: `required` geçersiz kılması geri alındığında iki
test kırmızıya dönüyor. Sadece "geçiyor" demek bu hatayı beş kez kaçırdı.

#### `interpret.py`'nin ampirik korumaları taşındı, yeniden yazılmadı

Görev 04 promptu ve şemayı sıfırdan yazıp dört korumayı birden atıyordu:
`required` geçersiz kılması, `notable_event` yer tutucu backstop'u (bir gerçek
karede 4/4 tekrarlanmış), `maxItems` kaçak tekrar sınırı ve kesilmiş açıklama
onarımı. Bunların hiçbiri teorik değil — hepsi izlenmiş bir arıza ve
yorumlarında tekrar sayıları yazıyor. Yeniden yazmak her birini jüri önünde
yeniden kazanmak olurdu.

#### Pencere başına üç kare

Ortadaki tek kare yerine ilk/orta/son. Devrilen forklift bir **hareket**
olayı; tek kare onu ya ayakta ya çoktan yerde gösterir, ikisi de olayı
anlatmaz. Yönlendirici hangi pencerenin görüye gideceğini zaten süzdüğü için
maliyet yalnız işaretlenmiş pencerelerde artıyor. Kısa pencerede indeksler
çakışırsa tekilleştiriliyor, kare eksikse eldekiyle devam ediliyor.

#### `Gateway.ask()` üretim parametreleri alıyor

`interpret.py` `max_tokens=300` ve `temperature=0.3` kullanıyordu, ama Görev
03'ün `ask()`'ı bunları geçirecek bir yol bırakmamıştı — yani kaçak tekrarı
asıl frenleyen tavan erişilemezdi. `ask()` artık ikisini de opsiyonel alıyor;
verilmezse istekte hiç görünmüyorlar. Mevcut 18 gateway testi değişmeden
geçiyor.

#### `interpret.py` ve `schema.py` şimdilik duruyor

Görev 17 `run.py`'ı baştan yazınca ikisi de tek çağıranını kaybedip ölü kod
olacak. Bugün silinmediler çünkü mevcut `run.py` hâlâ onları kullanıyor;
Görev 17'ye açık bir silme adımı yazıldı. Adaptör onlardan import etmiyor —
korumaların sertleştirilmiş kopyalarına kendisi sahip.

### Görev 06 tamamlandı — yönlendirici, ve şema sertleştirmesi gateway'e taşındı (2026-08-23)

`f9e5029` (gateway) + `768635d` (yönlendirici). 17 test yeşil, toplam 106.

#### Görev 04'ün düzeltmesi yarım kalmıştı — kural, düzelttiği hatanın şeklindeydi

Görev 04 `strict_schema()`'i yazdı ve **"her çağıran onu çağırmayı hatırlasın"**
kuralını koydu. İki sorun çıktı:

1. **Kural zaten unutulmuştu.** Kuralı yazdığım anda Görev 06, 07 ve 12'nin
   üçü de şemayı çıplak geçiriyordu. Yani koruma, koruduğu hatayla aynı
   şekle sahipti: unutulduğunda görünmez, önemli olduğunda ölümcül.
2. **Fonksiyonun kendisi eksikti.** Yalnız `maxLength`'i söküyordu.
   `RouterDecision.confidence` `Field(ge=0, le=1)` yüzünden
   `minimum`/`maximum` basıyor ve sertleştirmeden sağ çıkıyorlardı —
   ölçülerek doğrulandı, tahmin değil.

**Karar: sertleştirme gateway'in içine taşındı.** `strict_schema` artık
`gozcu/gateway.py`'da ve `ask()` kendisine verilen her şemayı kendisi
sertleştiriyor. Çağıranın hatırlaması gereken bir şey kalmadı — unutulabilir
bir kural, kural değildir. `interpreter.py` yalnız yeniden ihraç ediyor.
Sökülen anahtar kümesi büyüdü: `maxLength, minLength, pattern, format,
minimum, maximum, exclusiveMinimum, exclusiveMaximum, multipleOf`.
`maxItems` bilerek duruyor — ampirik bir kaçak tekrar arızasını frenliyor.

#### `ask()` şemasız son bir deneme yapıyor

Organizasyonun gateway'ini kimse görmedi; şema desteğinin ne kadar katı
olduğunu bilmiyoruz. Reddedilen bir şema ile gerçek bir kesinti **ayırt
edilemiyordu**: ikisi de denemeleri tüketip kademeyi `degraded` bırakıyordu,
yani sağlıklı bir kademe sonsuza dek ölü sayılabilirdi. Artık şemalı istek
tükenirse şemasız bir deneme daha yapılıyor; kademe yalnız o da başarısız
olursa bozuk işaretleniyor. Enjekte edilmiş kesintide yedek **çalışmıyor** —
kasıtlı kesinti kesinti olarak kalmalı.

**Bedeli, ve bunu her ajan bilmek zorunda:** `maxLength`, `minimum`/`maximum`
ve `pattern` artık tele hiç çıkmıyor, dolayısıyla model sınır dışı değer
döndürebilir ve **doğrulamadan önce temizlik ajanın işi**. Yönlendirici
`rationale`'ı kesiyor ve `confidence`'ı 0..1'e kıstırıyor; yoksa geçerli bir
karar `ValidationError`'a düşüp `ignore`'a çökerdi. Ayrıca dönen içerik
şemasız yedekten gelmiş olabilir — ayrıştırıcılar iyi biçimli JSON varsaymamalı.

#### `mmss` 99:59'da sınırlanıyor

Saat taşması yoktu: `mmss(6000)` `"100:00"` üretiyordu ve bu
`EventSummary.time`'ın `^\d{2}:\d{2}$` desenini ihlal ediyor — Görev 17'de
doğrulama hatası. Demo klipleri dakikalarla ölçüldüğü için tam saat desteği
kapsam dışı, ama sessizce geçersiz string üretmesi kabul edilemezdi.

### Görev 07 tamamlandı — sentezleyici (2026-08-23)

`b2d8f08`. 30 test yeşil, toplam 136. 24 Ağustos bloğu da kapandı.

#### Hayalet epizot: açık epizot yokken gelen `close_episode`

Kapanış kararı, açık epizot yokken açılış dalına düşüyordu: **tam teşekküllü
kapalı bir epizot uyduruyor** (`state="closed"`, `phase="outcome"`), modelden
bir özet istiyor, devir kaydı yazıyor ve gömme geri çağrısını tetikliyordu —
hiç yaşanmamış bir olay için. `DecisionLoop._resolve()` yalnız `open_episode`'u
indiriyor, dolayısıyla yönlendiriciden arka arkaya gelen iki kapanış
şartnamenin `events[]` listesine bir hayalet olay koyuyordu. Hiçbir test
kapsamıyordu.

Artık açık epizot yoksa kapanış **hiçbir şey yapmıyor**: epizot yok, devir
yok, `on_close` yok, model çağrısı bile yok.

**Asimetri bilerek:** `update_episode` açık epizot yokken yeni bir tane
açıyor (döngü depo boşken bir güncelleme yönlendirebilir), `close_episode`
açmıyor. İki dalı "sadeleştirip" birleştiren, hayalet epizotu geri getirir —
bu yüzden kodda Türkçe bir uyarı notu duruyor.

#### Üç ayrı geri düşüş metni, çünkü tek metin guard'ı test edilemez kılıyor

Boş içerik guard'ı yazıldıktan **sonra bile** mutasyon testinde hiçbir testi
düşürmüyordu: `json.loads("")` zaten aynı `except`'e düşüyor, yani guard'ın
varlığı ile yokluğu gözlenemez durumdaydı. Çözüm guard'ı değil **çıktısını**
değiştirmek oldu: `DEGRADED_SUMMARY` / `EMPTY_SUMMARY` / `UNREADABLE_SUMMARY`.

"Kademe sustu", "kademe boş döndü" ve "kademe çöp döndü" **farklı arızalar**;
denetim defteri bunları ayırt edebilmeli. Genel bir kural olarak da doğru:
iki farklı hata yolu aynı gözlenebilir sonucu üretiyorsa, aralarındaki farkı
test edemezsin — ve test edemediğin dal sessizce ölür.

#### Devir kaydının saati donuyordu

`Handoff.ts = episode.start_ts` yüzünden güncelleme yolunda devir kaydı
epizodun **ilk** anını taşıyordu; uzun bir epizot boyunca devir defterinin
saati duruyordu. Artık geçerli pencerenin ts'i yazılıyor, böylece Görev 15/16
zaman çizelgeleri kronolojik okunuyor.

### Görev 08 tamamlandı — epizodik hafıza araması (2026-08-23)

`1cdb29b`. 14 test yeşil, toplam 152.

#### Prosa çalışmaz: Görev 07'de yazdığım üç kuraldan ikisi kodda yoktu

Görev 07 kapanınca 08'in dosyasına üç `on_close` kuralı yazmıştım: boş
vektörü yazma, asla istisna atma, `episode.id` ile anahtarla. **Kodu yalnız
üçüncüsünü tutuyordu.** `save_embedding` koşulsuzdu ve `embed_episode`
`ValueError` atıyordu.

Bu, `strict_schema()` kuralıyla aynı arıza: **koruma, insanın okuduğu yere
yazılırsa unutulur; yalnız testin dayattığı yere yazılırsa unutulmaz.**
İkisi de artık kodda ve mutasyonla doğrulandı.

#### Görev 09'un sahibine kurulmuş bir tuzak vardı

`docs/tasks/09-tesis-dunyasi.md` fixture'ları `embed_episode` üzerinden
tohumluyor. Gömme kademesi o an bozuksa N tane boş satır düşüyordu ve
`np.asarray` düzensiz diziye takılıp **sonraki her aramayı** `ValueError` ile
öldürüyordu. Görev 09 bir cold-start görevi: sahibi bu kod tabanını 25
Ağustos'ta ilk kez görüyor ve hatanın nedenini bulma şansı yok.

Şimdi iki katman koruyor: yazma yolu boş vektörü hiç kaydetmiyor, okuma yolu
da boş ve boyutu uyuşmayan satırları eliyor. **Tek katman yeterdi ama ikisi
de duruyor** — tohumlama zaten yazılmış bir tabloyu bozamaz.

#### Arama kendi epizodunu döndürüyordu

`search_timeline`'ın dışlaması yoktu ve Görev 11 sorguyu `episode.summary_tr`
ile, yani gömülen metnin **birebir kendisiyle** yapıyor. Sonuç: "bunu daha
önce gördük mü?" sorusunun cevabı olayın kendisi. Jüri önünde görünür.
`exclude_id` eklendi; Görev 11'in çağrısı düzeltildi.

#### `rerank` aday düşürüyordu

Kapsam dışı indeksleri süzüyor ama tekrarları ayıklamıyor ve modelin
atladığı indeksleri geri koymuyordu — yani kısmi bir yanıt **sessizce aday
siliyordu**. Artık her zaman tam bir permütasyon dönüyor: modelin sırası
önce, kalanlar orijinal sırayla arkasına.

#### `numpy` bildirilmemişti

Doğrudan kullanılıyor ama `pyproject.toml`'da yok; yalnız `ultralytics`
üzerinden geçişli olarak geliyordu. Bugün çalışıyor, bağımlılık ağacı
budandığı gün kırılırdı — ve `ultralytics` ~1 GB'lık bir görü yığını, yani
paketleme turunda budanması makul. Açıkça eklendi.

### Görev 09 tamamlandı — tesis dünyası (2026-08-23)

`c6d82ec`. 11 test yeşil, toplam 163. İlk cold-start görevi.

#### Sertifikasyon hikâyesi kesildi — kök neden tamamen mekanik

**Ürün kararı (Üveys, 23 Ağustos).** Spec'in §5 tablosu
`vardiya_personel_sorgula`'yı "bu kişi forklift için ehliyetli değil"
çıkarımıyla gerekçelendiriyordu. Fixture'lar bunu **desteklemiyordu**:
B-Hattı'nın tek forklift operatörü M.K.'nın ehliyeti vardı, ehliyetsiz kişi
ise araca hiç dokunmayan sevkiyat personeliydi. Yani risk analisti o çıkarımı
hiçbir zaman yapamazdı.

İki seçenek vardı: veriyi hikâyeye uydurmak ya da hikâyeyi kesmek. **Hikâye
kesildi** — operatör ehliyetli, kök neden fren/bakım zinciri.
`certifications` alanı duruyor (gerçekçi vardiya verisi), ama artık bir
hikâye taşımıyor. Spec'in ilgili satırı üstü çizilerek işaretlendi.

**Bunun bedeli ve neden önemli:** kök neden artık **tek** zincire dayanıyor.
Önceden iki bağımsız iplik vardı (ehliyetsiz operatör + geciken bakım), biri
zayıfsa diğeri taşırdı. Artık yedek yok: bakım tarihleri tutmazsa ya da arıza
kaydı olay arşiviyle çelişirse, rapor kendi verisinin yalanladığı bir şey
iddia eder. Bu yüzden zincirin iç tutarlılığı artık bir düzen meselesi değil,
**doğruluk meselesi**.

#### Olay tarihi sabit: 15 Ağustos 2026

**Ürün kararı.** Hiçbir şey `date.today()`'den türemiyor — demo aylar sonra
oynatıldığında sayılar kaymasın diye. `SCENARIO_DATE` tek kaynak.

`overdue_maintenance_months` artık **saklanan bir sayı değil, türetilen bir
sonuç**: her `operation_type` için son kaydın `next_due`'sundan
`SCENARIO_DATE`'e kaç tam ay geçtiği. Eskiden `overdue_maintenance_months: 4`
diye sabit yazılıydı ve kendi tarihleriyle çelişiyordu (gerçek fark ~7.5 ay).
IST-07 bilerek temiz (0) — kontrol vakası.

Ekipman arıza kaydı ile olay arşivi aynı forklift hakkında **farklı şeyler**
söylüyordu. Artık 2026-08-12 olayı iki yerde de `OLY-2026-0812` kimliğiyle
tek olay olarak duruyor.

#### Eksik olan iskele: bölge, kişi kimliği, vardiya saatleri

Demo senaryosunun iki merkezî aracı — `dispatch_medical(location)` ve
`halt_production_line(line_id)` — çözecek bir şey bulamıyordu: tesisin
bölgeleri hiç tanımlı değildi. Kişiler baş harflerden ibaretti, yani hiçbir
epizot bir insana bağlanamıyordu. `at_time` parametresinin karşılığı yoktu.
Üçü de eklendi: `zones`/`production_lines`, `PRS-00X` kimlikleri, `shifts`.

#### `load_history` yalan söylüyordu

Sayaç `embed_episode`'un sonucuna bakmadan artıyordu ve fonksiyon
`return n or len(incidents)` ile bitiyordu: bozuk gömme kademesinde "3 yüklendi"
diyordu, gerçekte 0 vektör yazılmışken. Testi bunu yakalayamıyordu çünkü
`gw` bir `Mock`'tu — onuncu kez aynı desen. Artık yalnız gerçekten yazılan
sayılıyor, `or` yedeği silindi, ve ikinci çağrı bozuk kademede atlananları
telafi ediyor.

#### `shift amiri` → `vardiya amiri`

**Ürün kararı.** Operatöre görünen metin Türkçe olacak (CLAUDE.md); `shift`
İngilizce. Aynı şekilde Türkçe cümlelerin içindeki `personnel` → `personel`,
ve `participants` artık İngilizce bir kelime yerine kararlı kimlikler taşıyor
(`["IST-04", "PRS-001"]`).

### Görev 10 tamamlandı — yedi saha aracı (2026-08-23)

`198801e`. 23 test yeşil, toplam 186. Xana-bit'in iki görevi de kapandı.

#### `halt_production_line` gerçekten iki fazlı oldu

**Ürün kararı (Üveys, 23 Ağustos).** Spec iki faz vaat ediyordu; kod tek
fazlıydı. Operatör Görev 14'te onayladıktan sonra araç yeniden çağrıldığında
hâlâ `awaiting_approval: True` dönüyordu — yani onay çubuğu kapanıyor ama hat
hiçbir zaman "durduruldu" demiyordu. **Hiçbir şeye yol açmayan bir onay
tiyatrodur** ve jürinin okuduğu şey aksiyon defteri.

Artık onaysız çağrı `awaiting_approval: True`, onaylı çağrı
`state: "halted"` ve `awaiting_approval` anahtarı **hiç yok**. İki çağrı da
deftere düşüyor, yani "ajan önerdi → operatör onayladı → hat durdu" zinciri
kayıttan okunabiliyor.

#### Ajan kendi kendini onaylayamıyor

Bu, görevde istenmemişti ama doğrusu bu: `halt_production_line` şemada bir
`approved` alanı ilan ediyor, fakat `call_tool` modelin gönderdiği değeri
**ezip** defterdeki onay durumuna bakıyor. Yani tek doğruluk kaynağı aksiyon
defteri; ajan `approved: True` yollasa bile `awaiting_approval` alıyor.

İnsan-döngüde tasarımın bütün iddiası bu tek özellikte duruyor: onay
mekanizması, onaylanacak tarafın erişebildiği bir alansa onay değildir.

#### Enum tanımsızdı, ve güvenli taraf yukarısı

`dispatch_medical` `urgency == "critical"` diye dallanıyordu ama hiçbir şema
sözcük dağarcığını kısıtlamıyordu. Türkçe promptla çalışan bir sistemde
modelin `"kritik"` yazması gayet olası — ve o durumda **kritik bir sevk
sessizce normale düşüyordu**. CLAUDE.md'nin "bir kez ayrıştılar ve sistem
sessizce öldü" dediği arıza tam olarak bu.

Enum artık `("normal", "critical")` ve şemada ilan ediliyor. Tanınmayan bir
değer **`critical`'a düşüyor**, normale değil: bir güvenlik sisteminde güvenli
başarısızlık yukarı kaçmaktır, aşağı değil. Yanına `unrecognised_urgency`
bayrağı konuyor ki sessiz olmasın.

#### Defterdeki her kaydın saati sıfırdı

`call_tool` her `ActionRecord`'a `ts=0.0` yazıyordu. O defter Görev 17'de
`detail.action_ledger` olarak teslim ediliyor, yani jüriye giden kayıtta hiçbir
aksiyonun zamanı yoktu. Artık çağıran taraf **video zamanını** geçiriyor —
bu sistemde "ajan hattı ne zaman durdurdu" sorusunun cevabı bir sunucu saati
değil, görüntüdeki an.

#### Uydurulmuş veri: `eta = 8`

`dispatch_medical` bölge çözülemediğinde `eta = 8` döndürüyordu — diğer her
değerin gerçek fixture verisi olduğu bir alanda, hiçbir yerden gelmeyen makul
görünüşlü bir sayı. Fixture'lar artık gerçek ETA'ları (2/5/7) tanımlıyor;
çözülemeyen bölge `zone_unresolved` diyor. Aynı şekilde `site_alarm` serbest
metni yankılamak yerine `resolve_zone` çağırıyor.

#### Doküman tablosu koda üç yıl geriden bakıyordu

Araç tablosu hâlâ Türkçe dönüş anahtarları (`cagri_id`, `yanit_bekleniyor`,
`onay_bekliyor`) belgeliyordu; kod İngilizce dönüyor. **`check-tasks.py` bunu
yakalayamaz** — Türkçe taraması yalnız ```python bloklarını okuyor, markdown
tablolarını hiç görmüyor. Bu, denetçinin bilinen üçüncü kör noktası
(JSON fixture anahtarları ve markdown tabloları hâlâ denetimsiz).

### Görev 11 tamamlandı — risk analisti (2026-08-23)

`dd803fd`. 17 test yeşil, toplam 203.

#### Analist hiçbir araç çağırmıyordu — kök neden iddiası dayanaksızdı

**Ürün kararı (Üveys, 23 Ağustos).** `assess_risk` tek bir model çağrısı
yapıyor, `tools=` geçmiyor, `call_tool`'a hiç uğramıyordu. Sonuç: Görev 12'nin
kök neden raporunda iddia ettiği **"4 ay gecikmiş fren bakımı"** rakamı
sistemde hiçbir yerden üretilmiyordu. `overdue_maintenance_months` doğru
hesaplanıyor, fixture'lar akşam bunun için yeniden yazıldı — ve kimse
sormuyordu. Analist yalnızca arşiv metnindeki bulanık "gecikmiş fren bakımı"
ifadesini görebiliyordu.

Bu bir doğruluk sorunundan fazlası: raporu aksiyon defteriyle karşılaştıran
bir jüri, **arkasında hiçbir kanıt olmayan bir iddia** bulurdu.

Artık iki turlu: ilk `ask` okuma araçlarını sunuyor, model çağırırsa her çağrı
`call_tool` üzerinden koşuyor (`ts=episode.start_ts`), sonuçlar `role:"tool"`
mesajlarıyla geri veriliyor ve ikinci `ask` nihai değerlendirmeyi üretiyor.
Ekipman kimliği modelin tahmininden değil, `episode.participants`'tan geliyor.

**Yan fayda:** şartnamenin puanladığı *dinamik araç seçimi* ve *çok adımlı
karar zinciri* artık iddia değil, defterden okunabilen bir davranış.

#### Analist yalnızca okuyabilir — iki katman

Görevde istenmemişti ama onay tasarımının kendi mantığından çıkıyor: analist
bütün kayda erişebilseydi, bir olayı **analiz ederken** yan etki olarak hattı
durdurabilir ya da sağlık ekibi çağırabilirdi. Bu, Görev 14'ün onay kapısını
kırmazdı — **hiç girmezdi**. Ajanın kendini onaylayamamasıyla aynı ilke:
insan-döngüde garanti, ancak etrafından dolaşacak yol yoksa geçerlidir.

İki katman: yalnız `READ_TOOLS` şemaları sunuluyor, VE sunulmamış bir araç
çağrılırsa çalıştırma katmanı reddediyor. Sunulmamak bir garanti değil.

#### Prompt kataloğu şemadan üretiliyor

`urgency` enum'u (`normal`/`critical`) prompta elle yazılmıyor;
`TOOL_SCHEMAS`'tan türetiliyor. Elle yazılan bir enum listesi şemadan ayrışır —
CLAUDE.md'nin "bir kez ayrıştılar ve sistem sessizce öldü" dediği şey.
Türetilen bir liste ayrışamaz. Aynı desen bugün üçüncü kez: sertleştirmeyi
gateway'e taşımak, kuralı teste bağlamak, katalogu şemadan üretmek —
**hatırlanması gereken kural yerine, unutulması imkânsız yapı.**

#### Kesme yalnız üst alanda değil, iç içe de

`rationale_tr` (800) ve **her** `proposed_actions[*].description_tr` (200).
`maxLength` artık tele çıkmadığı için taşma bekleniyor ve korumasız bir
`ValidationError` gerçek bir değerlendirmeyi yedek kabuğa çeviriyordu. İç içe
listeyi atlamak, hatanın yarısını düzeltip diğer yarısını bırakmak olurdu.

### Görev 12 tamamlandı — raportör ve kök neden raporu (2026-08-23)

`a8cf363`. 22 test yeşil, toplam 225.

#### CLAUDE.md'nin adıyla uyardığı hata, canlı hâlde bulundu

`SYSTEM_PROMPT` modele **`guven_sinirlari`** alanını doldurmasını söylüyordu;
şemadaki ad `confidence_limits`. Yani model var olmayan bir anahtarı
dolduracak, gerçek alan **boş** kalacaktı — ve raporun "neyi bilemiyorum"
bölümü, yani dürüstlüğünü taşıyan tek alan, sessizce kaybolacaktı.

CLAUDE.md bunu adıyla yazmış: *"Prompt bir enum sayıyorsa değerleri şemadakiyle
birebir aynı olmalı. Bunlar bir kez birbirinden ayrıldı ve sistem sessizce ölü
hâle geldi."* Denetçi de yakalayamıyordu: §3 docstring gövdelerini eliyor,
§4'ün listesi bu adı içermiyor.

**Düzeltme kuralla değil yapıyla:** prompt'un ilan ettiği alan listesi artık
`RootCauseReport.model_json_schema()`'dan **türetiliyor**. Elle yazılan liste
ayrışır; türetilen ayrışamaz. Ajan bunu istenen sınırın ötesine taşıdı —
kesme haritası (`LENGTH_LIMITS`) da aynı şemadan okunuyor, yani uzunluk
sınırlı yeni bir alan otomatik olarak hem duyuruluyor hem kesiliyor. Bölüm
başlıkları da paylaşılan sabit; kanıt kuralı var olmayan bir bölümü
işaret edemiyor.

Bugün dördüncü kez aynı ders: **hatırlanması gereken kural yerine, unutulması
imkânsız yapı.**

#### Rakam ile tahmin arasındaki fark, raporun bütün mesele

"4 ay gecikmiş fren bakımı" iki yoldan gelebiliyordu: aksiyon defterindeki
türetilmiş `overdue_maintenance_months` değerinden, ya da arşiv metnindeki
bulanık "gecikmiş fren bakımı" ifadesinden modelin uydurmasıyla. **İkisi de
aynı görünüyordu** ve prompt aralarında hiçbir ayrım yapmıyordu.

Bir sanayi kazasının nedenini açıklayan bir belgede bu fark her şeydir. Prompt
artık her rakamın, tarihin ve kimliğin verilen kayıttan gelmesini şart
koşuyor; kanıt yoksa rapor tahmin etmek yerine **bilmediğini yazıyor**. Testi
defterdeki türetilmiş değeri tohumlayıp prompta ulaştığını doğruluyor.

Aynı sebeple araç sonuçları deftere **budanmadan** basılıyor: budama, raporun
alıntılaması gereken rakamı düşürebilir. Bağlam baskısı olursa bütçe Görev
17'de ayarlanacak, raportörde değil.

#### Rapor saklanmıyor, döndürülüyor

Dosya `detail`'den, Görev 14'ten ve Görev 17'den **hiç söz etmiyordu**; sahibi
`what_happened` alanının şartnamenin `summary`'si olduğunu öğrenemezdi. Artık
modül docstring'i söylüyor. Bu, cold-start ölçütünün ihlaliydi: dosya tek
başına doğru uygulanamıyordu.

### Görev 13 tamamlandı — çıktı denetimi (2026-08-23)

`ec0eca6`. 38 test yeşil, toplam 263. Cold-start dosyalarının sonuncusu.

#### Guard, gerçek gateway'de kalıcı bir no-op olacaktı

`MODELS["guard"]` = `Qwen3Guard-Gen-4B`. Qwen3Guard-Gen bir **sınıflandırıcı**,
talimat takip eden bir sohbet modeli değil — gateway'in reranker için zaten
güvenmediği kategori. Prompt ondan Türkçe `uygun`/`uygunsuz` demesini istiyor,
kod da `"uygunsuz" in content` diye bakıyordu. Sınıflandırıcı kendi etiket
biçimini basar, o alt dize hiç eşleşmez ve **her metin sonsuza dek denetimden
geçer**. Yedi testin hepsi yeşildi, çünkü `gw` bir `Mock`'tu: testler,
modelin hiç üretmeyeceği bir yanıt biçiminin ayrıştırılmasını doğruluyordu.

Artık `parse_verdict` iki biçimi de kabul ediyor. Naif kontrole geri dönmek
**14 testi** düşürüyor.

#### `uygun değil` onay sayılıyordu

Doğal bir Türkçe olumsuzlama, kontrolü tam tersine çeviriyordu: `"uygunsuz"`
alt dizesi yok, dolayısıyla metin temiz kabul ediliyordu. Olumsuzlamalar artık
olumlu belirteçten **önce** sınanıyor.

`tartışmalı`/`controversial` bilerek `unknown`: model ikili bir hüküm
vermekten kaçınmışsa, onu temiz saymak yalan, kirli saymak aşırı engelleme
olur.

#### "Tarandı ve temiz" ile "taranamadı" ayrı şeyler

İkisi de fail-open — metin her hâlükârda gidiyor. Ama ikisini aynı sonuca
indirgemek, denetim kaydında bir kesintiyi temiz rapordan ayırt edilemez
kılıyordu. Ayrım artık tip düzeyinde (`Screening.screened`), sihirli bir
string değil.

#### Teslim edilen paket de taranıyor

**Ürün kararı (Üveys, 23 Ağustos).** Guard yalnız operatör diyaloğunu
tarıyordu; jürinin okuduğu `summary`/`actions`/kök neden raporu taranmadan
gidiyordu. Artık `screen_delivery` teslimden hemen önce çalışıyor.

**`unsafe` çıkarsa paket boşaltılmıyor, işaretleniyor.** Bir güvenlik
sınıflandırıcısının gerçek bir iş kazası anlatısını "şiddet içerikli" diye
işaretlemesi fazlasıyla olası; yanlış pozitif yüzünden jüriye giden raporu
silmek şartnamenin dört anahtar sözleşmesini çiğnerdi. Tarama alanları
**şekle göre** geziliyor, elle yazılmış bir alan listesiyle değil — yani
Görev 12'nin raporu değişse bile ayrışamaz.

#### Blanket `except` silindi

Görev 03/06'dan beri hiçbir kademe kesintide istisna atmıyor; `GatewayError`
ise artık "bilinmeyen kademe", yani yazım hatası demek — yutulmaması gereken
tek şey. Onu yakalayan geniş `except`, üretimde ulaşılamayan bir dalı canlı
tutan sahte bir testle ayakta duruyordu. İkisi de gitti; yerine `GatewayError`'ın
yukarı çıktığını doğrulayan bir test kondu.

### Görev 14 tamamlandı — Nöbetçi süpervizör (2026-08-24)

`463a74c`. 39 test yeşil, toplam 302. Projenin en büyük dosyası.

#### Beşinci prompt/şema ayrışması — ve bu bir demo beat'ini öldürüyordu

`SYSTEM_PROMPT` modele **`gozlem_duzelt`** aracını çağırmasını söylüyordu;
şemada tanımlı ad `correct_observation`. Model var olmayan bir ad üretecek,
**operatör düzeltme akışı hiç tetiklenmeyecek** ve `correction_propagation`
KPI'ı sıfır okuyacaktı — sessizce, bütün testler yeşilken.

Bugün beşinci kez. Diğer dördü: Görev 05'in yönlendirici enum yorumu, Görev
12'nin `guven_sinirlari`, Görev 10'un Türkçe dönüş anahtarları, Görev 11'de
prompta hiç ulaşmayan `urgency` enum'u. Hepsinin ortak kökü aynı: **bir liste
elle yazıldığında ayrışır.** Katalog artık `ALL_TOOL_SCHEMAS`'tan türetiliyor
ve prompta girmiş her aracın şemada var olduğunu doğrulayan bir test var.

#### Tek onay yuvası

**Ürün kararı (Üveys, 24 Ağustos).** `pending_approval()` bekleyen satırların
**sonuncusunu** döndürüyordu: ikinci bir bekleyen kayıt doğduğunda eskisi
sonsuza dek görünmez ama `"pending"` kalıyordu. Operatör gördüğü şeyi
onaylarken, görmediği bir aksiyon kuyrukta asılı kalıyordu — ve Görev 16'nın
onay çubuğu bayat satırda yeniden açılıyordu.

Artık bekleyen bir kapılı aksiyon varken ikincisi **reddediliyor**: deftere
hiçbir şey yazılmıyor, operatöre Türkçe bir `[SİSTEM]` notu dönüyor.
Konsolun gösterdiği ile defterin tuttuğu ayrışamaz.

#### Yalnız hat durdurma kapılı — ve bu bilinçli

**Ürün kararı.** `dispatch_medical`, `radio_call`, `site_alarm`,
`open_safety_incident` onaysız çalışıyor: geri alınabilir, düşük maliyetli ve
**gecikmesi can alan** eylemler. `halt_production_line` ise gerçek ekonomik
sonucu olan, geri alması zor bir eylem — o bekliyor.

Gerekçe modül docstring'ine Türkçe yazıldı, çünkü açıklanmazsa okuyan kişi
"kapı unutulmuş" diye düşünüp ya "düzeltir" ya da şüphede kalır. Jüri de
sorabilir: ajan ne zaman kendi başına davranır, ne zaman insana sorar?
Cevap kodun içinde durmalı.

#### Onay başarısı görünmüyordu

`approve()` `{"state": "approved", **result}` döndürüyordu ve
`halt_production_line`'ın kendi `state: "halted"` değeri onay durumunu
**eziyordu** — hiçbir çağıran onayın başarılı olduğunu göremiyordu. Sonuç
artık iç içe: `{"state": ..., "action_id": ..., "result": {...}}`.
`not_pending` durumu da çift çalıştırmayı engelliyor.

#### Diyaloğun saati sıfırdı

`DialogueTurn` ve `Correction` `ts=0.0` ile yazılıyordu, yani kök neden
raporundaki her diyalog satırı `00:00` görünüyordu. Aksiyon defterinde aynı
hata Görev 10'da düzeltilmişti; burada diyalog tarafında duruyordu.

### Görev 15 tamamlandı — KPI ve benchmark (2026-08-24)

`b08fce8`. 58 test yeşil, toplam 361.

#### Ölçen görevin arızası, arıza gibi görünmez

15 diğer her şeyi ölçüyor; buradaki bir hata çökme değil, **sonuç** gibi
görünür. Bulunanlar bunu doğruladı: `turkish_output_rate` hiç yazılmamıştı ama
import ediliyordu (bütün testler hata veriyordu), `timestamp_drift` canlı bir
`NameError` taşıyordu, ve `correction_propagation` **yapısal olarak 1.0'dan
başka bir şey döndüremiyordu**.

#### `Episode.start_ts` aynı sütunda iki farklı birim taşıyordu

Canlı epizotlar **video saniyesi** (192.5), arşiv fixture'ları ise **epoch
saniyesi** (1786567260.0) yazıyordu. Bunu Görev 09'da fixture'ları yeniden
yazarken ben soktum. `mmss()`'in 99:59 sınırlaması sayesinde çökmüyordu —
daha kötüsü, **makul görünen yanlış bir saat** üretiyordu: arşiv olayları
raporda ve konsolda `99:59` diye görünüyordu.

Arşiv epizotları artık `start_ts=0.0` ve süre `end_ts`'te; mutlak tarih zaten
`occurred_at`/`date` alanlarında duruyordu. **Ders:** bir sınırlama (clamp)
geçersiz veriyi geçerli görünen veriye çevirdiğinde, hatayı gizler.

#### Manşet kova aynı zamanda toplam arıza kovasıydı

**Ürün kararı (Üveys, 24 Ağustos).** `closed_at_router` hem "ucuza süzdük"
hem "her şey çöktü" demekti: bozulmuş yönlendirici `ignore`'a düşüyor,
`TARGET.get(..., "perception")` de bilinmeyen kararları oraya yolluyordu.
Yani **tamamen kırık bir koşu, mümkün olan en gurur verici grafiği** üretirdi.

Enstrümantasyon zaten vardı ve kimse okumuyordu: `route()` bozulmuş yedeğine
`confidence=0.0` yazıyor — yorumunda "ölçümde gerçek bir kararla karışmasın"
diye. `gw.is_degraded()` de KPI göstergesi için belgelenmiş, hiç
kullanılmamıştı. Artık beşinci kova `degraded` ve her koşu `measured` /
`degraded` / `unmeasured` damgası taşıyor; ortalamalar yalnız ölçülmüş
klipler üzerinden.

#### Başarısız olamayan bir KPI, ölçüm değildir

`correction_propagation` `_apply_correction`'ın davranışı yüzünden hep 1.0
dönüyordu: `replace()` tutmazsa düzeltme metni **sonuna ekleniyor**, yani
"yeni değer özet içinde mi" sorusu her zaman evet. Sıfır vakası testi de
depoyu elle kurup süpervizörü baypas ettiği için geçiyordu.

Yeniden kapsamlandırıldı: gerçek ayırt edici, var olmayan bir `episode_id`'ye
işaret eden düzeltme. Sıfır düzeltmede artık `None` dönüyor — eskiden 1.0
dönüyordu, yani **operatörle hiç konuşmamış bir koşu tam puan alıyordu.**

#### Veriyi uydurmamak

`tokens_by_model` → `vision_tokens`. Token yalnız `Interpretation`'da
saklanıyor, dolayısıyla model başına maliyet iddiası verinin taşımadığı bir
iddiaydı. Aynı ilkeyle `benchmark/ground_truth.csv` **işaretlenmemiş**
pencerelerle geliyor: `timestamp_drift_s` bir insan klipleri etiketleyene
kadar `null` okuyor. Uydurulmuş bir doğruluk verisi, ölçüm değil süstür.

`benchmark/run.py` da Görev 17 gelmeden **çalışmayı reddediyor** (çıkış kodu 2,
Türkçe mesaj) — eksik ön koşul, ölçülmüş sıfırlarla karıştırılamasın diye.

#### Artefaktlar izlenen dizine

**Ürün kararı.** `runs/` hem `.gitignore`'da hem ultralytics'in kullanımında.
Benchmark çıktıları artık `bench/` altında, şeması `bench/kpi.schema.json`
olarak commit'li — jüri sayıları üreten kodla birlikte görebilsin.

### Gerçek gateway geldi — EVREN keşfi ve Qdrant'a geçiş (2026-08-24)

`08305b5` (keşif + config) · `7d6a473` (Qdrant). Toplam 368 test yeşil.
Saha notları: [evren-gateway.md](../06-references/evren-gateway.md).

#### Yedi takma adın hepsi yanlıştı — ve gateway bunu SÖYLEMİYOR

En önemli bulgu bir hata değil, bir **davranış**: bilinmeyen bir model adı
404 almıyor, sessizce `llm-fast`'e yönlendiriliyor. Tahmin ettiğimiz adlarla
bağlansaydık tek bir hata bile görmeyecektik; **görü çağrıları bir metin
modeline gidecek**, sistem "çalışacak", çıktı sessizce çöp olacaktı.

Görev 00 "bir harf hatası sessiz 400 demek" diye uyarmıştı; fazla iyimsermiş.
400 en azından duyulur.

Düzeltme tek dosyaydı — CLAUDE.md'nin "model kimlikleri yalnız `config.py`'da"
kuralı tam olarak bunun için vardı ve bugün karşılığını verdi.

#### Kör verilmiş üç karar canlı olarak doğrulandı

- **`guard` bir sınıflandırıcı.** Gerçek çıktı `Safety: Unsafe / Categories:
  Violent`. Görev 13'ün ilk hâlindeki `"uygunsuz" in content` kontrolü bu
  dizede de **False** dönüyor — yani guard gerçekten uygunsuz içeriği temiz
  sayıp geçirecekti. Ölçüldü, doğrulandı; sevk edilen `parse_verdict` iki
  biçimi de okuyor.
- **Doğrulamadan önce kesme zorunlu.** Gateway `maxLength`'i kabul ediyor ama
  **uygulamıyor**: 200 karakter sınırlı `rationale` çok daha uzun geldi ve
  pydantic patladı. Görev 06'nın kesme kuralı olmasa gerçek bir karar
  `ignore` yedeğine çökerdi.
- **Strict JSON şeması ve araç çağırma çalışıyor.** Kendi `TOOL_SCHEMAS`'ımız
  değiştirilmeden kabul edildi.

Fazla yaptığımız tek şey: `maxLength`/`minimum` sökmek gerekmiyordu, ham şema
da kabul ediliyor. Zararsız — ve o kısıtlar zaten uygulanmadığı için sökmek
yanlış da değil.

#### `vlm` görüntü değil video istiyor

`At most 0 image(s) may be provided`. Sınırlama modelin değil kurulumun:
kodlayıcı piksel bütçesinin tamamı video çözünürlüğüne ayrılmış. Görüntü
gönderen `llm-fast`/`llm-large` kullanır — **istek başına en fazla iki**.

Yani Görev 04'ün üç kare gönderen tasarımı **hiçbir kademede çalışmıyor**.
Gerçek 10 saniyelik forklift penceresi `vlm`'e gönderildi: 11,4 s, 431 KB,
düzgün Türkçe analiz ve **kareler arası değişimi** okuyor. Üç durağan karenin
yaklaşmaya çalıştığı şey buydu; artık taklit etmeye gerek yok.

#### Ön ek önbelleği (4,8×) reddedildi — çözünürlük kazanıyor

Ölçek klip süresine bağlı: 15 s → 0,95 · 60 s → 0,47 · 180 s → 0,28. İki
tokenin altındaki nesne çözülemiyor. Bütün klibi bir kez yükleyip önbellekten
yararlanmak bizi 0,47'ye düşürürdü. **"Yerde hareketsiz kişi" küçük ve düşük
kontrastlı bir hedef** — pencere başına ayrı kısa klip, hızdan önemli.

#### SQLite + numpy → Qdrant

**Ürün kararı (Üveys, 24 Ağustos).** Vektör veritabanı bir gereklilik;
takımların tamamı kullanacak. Karar günlüğünün eski "vektör DB yok" öncülü
zaten geçersizdi — organizasyon takım başına **izole** bir Qdrant veriyor.

Taşınırken hiçbir garanti geri alınmadı: `embed_episode` hâlâ istisna atmıyor
ve bozuk gömme kademesinde hiçbir şey yazmıyor; `exclude_id` artık Python'da
değil Qdrant'ın `must_not`/`HasIdCondition` filtresiyle; **Qdrant erişilemezse
arama boş dönüyor, çökmüyor** — gateway'le aynı felsefe.

`rerank` çağrısı kaldırıldı: organizasyonun kendi ölçümü onu **zararlı**
buluyor (R@1 0,95 → 0,55).

**Sessiz düşüşe karşı `memory_backend()`:** anahtar yokken istemci süreç içi
Qdrant'a düşüyor ve sistem tamamen sağlıklı görünüyor — ama hafıza süreçle
birlikte yok oluyor. Düşüşün kendisi kabul edilebilir, **görünmezliği değil**;
bu yüzden backend tek kelimeyle dışarı veriliyor, `kpi.run_status` ile aynı
gerekçe.

**Düzeltme:** `Store.save_embedding`/`embeddings` ölü sanılmıştı, değil —
`fixtures/loader.py` onları "zaten gömüldü" idempotenlik kümesi olarak
okuyor. Görev 17/18 borcu: loader'ın kontrolü Qdrant'a taşınınca defter
yazımı, iki metot ve `episode_embedding` tablosu birlikte ölür.

### Görev 04 yeniden yazıldı — kare değil video (2026-08-25)

`886342a`. 41 test yeşil, toplam 375. **Canlı gateway'de doğrulandı.**

#### Üç kare hiçbir kademede çalışmıyordu

`vlm` görüntü kabul etmiyor (`At most 0 image(s)`, HTTP 400) çünkü kodlayıcı
piksel bütçesinin tamamı videoya ayrılmış; `llm-fast`/`llm-large` ise istek
başına en fazla **iki** görüntü alıyor. Yani üç kare gönderen tasarım üç
kademenin üçünde de düşerdi — biri 400 ile, ikisi sınır aşımıyla.

Artık pencere bir **video klibi** olarak gidiyor:
`{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,…"}}`.

**Bu bir gerileme değil, iyileşme.** Üç kare, hareketi yaklaşık olarak
anlatmak için seçilmişti — devrilme bir hareket olayı ve tek kare onu ya
ayakta ya çoktan yerde gösterir. Model artık hareketin kendisini görüyor.

Canlı sonuç (10 s'lik gerçek forklift penceresi, 431 KB, `vlm`, 4,8 s):

> *"Bir forklift, başka bir forklifti yükleyerek yüksek bir konumda tutuyor.
> Yüklenmiş forklift, **hafifçe sallanıyor**; alttaki forklift sabit durumda.
> Arka planda bina penceresinde iki kişi izliyor."*
> `notable_event: "yüklenmiş forkliftin hafif sallanması"`

"Hafifçe sallanıyor" tam olarak üç durağan karenin veremeyeceği cümle.

#### Pencereler birleştirilmiyor — çözünürlük hızdan önce

Ön ek önbelleği aynı video üzerinde 4,8× hızlanma veriyor ve tek seferde
yükleyip çok soru sormayı cazip kılıyor. **Reddedildi.** Ölçek klip süresine
bağlı: 15 s → 0,95 · 30 s → 0,65 · 60 s → 0,47 · 180 s → 0,28. İşlenmiş
karede bir token 32×32 piksel ve iki tokenin altındaki nesne çözülemiyor.

`WINDOW_S` = 10 s bu cetvelin iyi ucunda. **Yerde hareketsiz bir kişi küçük ve
düşük kontrastlı bir hedef** — onu kaybetmek, kazanılan saniyelerden pahalı.
Gerekçe `interpret`'in Türkçe docstring'inde duruyor ki sonradan "optimize
eden" biri pencereleri birleştirmesin.

#### `MAX_TOKENS` 400 → 1024

400 canlıda cümlenin ortasında kesiyordu. Diğer duvar ters yönde: akıl
yürütme açıkken dar bir tavan **boş dize** döndürüyor (128/256/512'nin üçü de
sıfır karakter üretmiş), çünkü düşünme izi bütçeyi tüketiyor ve ayrıştırıcı
izi siliyor. Akıl yürütme kapalı kalıyor; 1024 hem 300+200 karakterlik Türkçe
yükü hem JSON zarfını rahat taşıyor, hem de kaçak dizi tekrarına karşı
anlamlı bir tavan olmayı sürdürüyor.

#### Boş içerik guard'ı yine yük taşımıyordu

Mutasyon testinde guard silindiğinde hiçbir test düşmedi: `json.loads("")`
zaten aynı yedeğe düşüyordu. Bugün üçüncü kez aynı desen — **iki farklı hata
yolu aynı gözlenebilir sonucu üretiyorsa aradaki farkı test edemezsin.**
`_parse` geçerli bir nesne döndürecek şekilde yamalanınca guard tek üretici
hâline geldi ve mutant öldü.

### Görev 17 tamamlandı — uçtan uca entegrasyon (2026-08-25)

`4e1a979` + `84286e8`. 33 yeni test, toplam 409.

#### Belgelenmiş ama hiç çağrılmayan `assess_risk`

17'nin metni "kapanışta risk analisti koşar" diyordu; **kodu `assess_risk`'i
hiç çağırmıyordu.** Risk yalnız `Supervisor.escalate` üzerinden deftere
düşüyordu ve `benchmark/run.py` boru hattını başsız (`nobetci=None`)
çağırıyor. Sonucu: her başsız koşuda — yani **her benchmark koşusunda** —
`store.risks()` boş, dolayısıyla `actions[]` kalıcı olarak `[]` ve `risk`
sessizce `preliminary_risk`'e düşüyordu.

Şartnamenin dört anahtarından ikisi içi boş, ve hiçbir şey hata vermiyor.
Ölçen görevin kendisi (Görev 15) de bunu göremezdi: sayı üretiliyordu, yalnız
yanlış sayıydı.

Artık `assess_risk` `on_close` içinde çağrılıyor, ayrıca koşu sonunda hâlâ
açık epizotlar için bir süpürme var. Başsız koşu doğrulandı: `risk="Kritik"`
(ön risk `"Yüksek"`in üstüne çıkıyor) ve `actions=["Sağlık ekibini çağır"]`.

#### `detail` artık bir şey ifade ediyor

Önceden çöküş dalı da `build_output` çağırıyordu, yani `detail` her hâlükârda
doluydu ve dosyanın "çöküşte `detail=None`" vaadi tutulmuyordu.

Ayrım şimdi anlamlı: **tamamen bozulmuş** bir koşu dört anahtarı `detail`
dolu döndürüyor (katmanlar çalıştı, bulacak bir şey yoktu); **çöken** bir
genişletilmiş yol `detail=None` döndürüyor. Dolu bir `detail`, o katmanların
gerçekten koştuğu anlamına geliyor.

#### Testler yeşilken arayüz ölüydü

Görev 17'ye "`app.py`'a dokunma" dedim ve dokunulmadı: `import app` çalışıyor,
`tests/test_smoke.py` geçiyor. Ama `run_pipeline`'ın dönüş şekli altından
değişti ve `_annotate_all_frames` hâlâ `timestamp_s`/`detected_objects`/
`description` okuyordu — **yeşil takım, ölü düğme.** Bu depoda bugün tekrar
tekrar çıkan arızanın ta kendisi, bu kez benim kuralımın içinden.

`app.py` yeni `EventSummary(time, event)` şekline asgari olarak uyarlandı ve
render yolu artık şemaya karşı sınanıyor (eski alan adlarına dönüldüğünde test
kırmızı). Görev 16 dosyanın tamamını konsolla değiştirecek.

**Ders:** "dokunma" bir dosyayı korumaz; onu besleyen sözleşme değişirse dosya
zaten kırılmıştır. Korunması gereken şey dosya değil, **davranış**.

#### Silinenler

`gozcu/interpret.py` ve `gozcu/schema.py` — `run.py` tek çağıranlarıydı.

### Görev 16 tamamlandı — operatör konsolu (2026-08-25)

`0ce9e86`. 47 yeni test, toplam 467. Son özellik görevi.

#### Gradio 5 değil 6.24 — ve bunu saf fonksiyon testleri asla yakalayamazdı

`Chatbot(type=...)` artık yok, `theme` `launch()`'a taşınmış. İlk `build()`
çağrısı `TypeError` attı. Konsolun bütün mantığı saf fonksiyonlarda test
edilseydi takım yemyeşil kalır, arayüz açılmazdı — bu depoda **üçüncü kez**
aynı arıza olurdu.

Bu yüzden `tests/test_console.py` artık `build()`'i gerçekten çağırıyor ve her
işleyicinin 11 ekran yuvasının hepsini doldurduğunu doğruluyor. Bir sonraki
Gradio API kayması sessizce değil, kırmızı olarak gelecek.

#### `catch_up()`'ın tutamağı yoktu

`DecisionLoop` örneği `run_pipeline`'ın içinde yereldi, yani konsolun
"Bağlantıyı geri ver" düğmesi onu çağıramıyordu — demo beat 6'nın yarısı
dekoratifti. `run_pipeline` iki geri çağrı kazandı: `on_event(LoopEvent)`
(yapısal `late` bayrağı; öncesinde yalnız `LATE_NOTICE` string'ini aramakla
anlaşılıyordu) ve `on_loop_ready(loop)`. İkisi de sona eklendi, konumsal sıra
bozulmadı.

Geri çağrılar `_invoke()`'tan geçiyor ve bir istisna `run.CallbackFailed`'e
sarılıyor: **konsol hatası yukarı çıkıyor, kademe kesintisi hâlâ bozuluyor.**
Öncesinde geniş `except Exception` ikisini de yutuyordu.

#### Diyalog filtresi ters yönde de yanlış olabilirdi

Kolay olan `role != "system"` filtresi denetim satırlarını temizler — ama
`_fault`'un bozulma metinlerini ve `LATE_NOTICE`'ı da siler. Yani **demo beat
6 ekrandan tamamen kaybolurdu.** Doğru filtre yalnız `AUDIT_PREFIX` ile
başlayan system satırlarını gizliyor; testi iki yönde de sınıyor.

#### Zaman çizelgesi liste, bindirme değil

Gradio'da video sürgüsü üzerine risk renkli işaret koymanın bir ilkeli yok ve
dondurmaya bir gün var. Video'nun yanında renk kodlu epizot listesi: `mmss`,
Türkçe özet, risk seviyesi. Dürüst ve inşa edilebilir.

#### Kare küçük resimleri kaldırıldı

`_annotate_frame`/`_annotate_all_frames` gitti: gösterim için kare başına YOLO
koşturmak **ikinci bir tam tespit turu** demek. Konsol epizot listesi
gösteriyor.

### Canlı benchmark: sistem hiçbir şey ölçmüyordu (2026-08-25)

`020e31f`. Etiketli beş klip üzerinde ilk gerçek koşu: **`status: degraded`,
5 klipten 0'ı ölçüldü, bütün KPI'lar `null`.**

Görev 15'in "bozulmuş koşuyu manşetten ayır" kararı tam da bunun için vardı:
benchmark, hiçbir şey görmemiş bir sistem için **gurur verici bir grafik
üretmedi**, sıfır ürettiğini söyledi.

#### Üç ayrı neden, üçü de yalnız canlı koşuda görünür

**1. Taban kör kalıyordu.** `k03` ("depoda raf/yük çökmesi") 23 gözlem üretti
ve **hiç tespit yoktu** — `YOLO_CLASSES` `person,vehicle` ve çöken bir raf
ikisi de değil. `passes_floor()` üç pencerede de düştü, yönlendirici hiç
çağrılmadı, epizot açılmadı, dört anahtar boş döndü.

Taban "ne zaman soralım" diye tasarlanmıştı; sıfır tespitte sessizce
"hiç sorma" diyor. **Ürün kararı (Üveys):** her `FORCED_SAMPLE_EVERY`
(=6) pencerede bir, taban düşse de sorulacak. 10 dakikalık videoda ~10 ek
çağrı, en ucuz 8B kademede; %90 süzme iddiası ayakta kalıyor.

Sayaç başta **dolu** başlıyor (`_PRIMED`): k03 yalnız 3 pencere, soğuk sayaçla
N=6 hiç ateşlenmez ve düzeltme kanıtlanamazdı.

**2. Yönlendirici gerçek modelde çok tutucuydu.** Üç kişi toplanması +
hız 4.2 → `ignore`, güven **1.0**. Prompt mock'lara karşı yazılmıştı ve 8B
router onu hiç görmemişti. Dört turda, sabit altı pencerelik prob setinde
**2/6 → 6/6**; sessiz pencere hâlâ doğru şekilde `ignore` (aşırı düzeltme yok).

**3. Ve asıl sürpriz: yönlendirici kaçıyordu.** Temel turda 6 çağrının 4'ü
**~243 saniye** sürüp ayrıştırılamaz içerik döndürdü — strict-JSON kod
çözümünde kaçak tekrar. Hepsi `_fallback`'e düşüp `ignore` olarak göründü.
Yani "tutucu yönlendirici" davranışının bir kısmı tutuculuk değildi;
**`ignore` kılığında dört dakikalık bir zaman aşımıydı.**
`MAX_DECISION_TOKENS = 256` ile bütün çağrılar 2,2 s altına indi.

**Ders:** bozulmuş moda düşen bir yedek, düştüğü sebebi de gizler. Üç farklı
arıza (kör taban, kötü prompt, kaçak kod çözme) ekranda **aynı tek kelimeyi**
üretiyordu: `ignore`.

### Algı katmanının dondurması kaldırıldı — sistem gerçek görüntüde kördü (2026-08-25)

`27d9e66` · `205052f` · `5641860`. 539 test yeşil.

#### Üç filtre, üçü de makul, birlikte tam körlük

Raf çökmesi klibinde sistem "Kayda değer olay tespit edilmedi" dedi, riski
"Düşük" biçti, `participants` boştu ve kök neden raporu **"yapısal yorgunluk"**
uydurup **"dış darbe kaydedilmedi"** diye yazdı. Gerçekte: forklift geniş bir
yükle rafa çarpıyor, raf çöküyor, operatör araçtan atlayıp kaçıyor.

Ölçüldü, tahmin edilmedi:

| # | Filtre | Bu klipteki etkisi |
|---|---|---|
| 1 | `YOLO_CLASSES = "person,vehicle"` | "vehicle" fazla soyut bir istem: aynı forklift 0,25; "forklift" densе 0,30 |
| 2 | `YOLO_CONFIDENCE = 0.35` | görüntüdeki tespitler 0,11–0,34 — hepsi eleniyor |
| 3 | `track.py`: `if box.id is None: continue` | tracker 6 kutu görüyor, **0 kimlik atıyor**, altısı da atılıyor |

Kare kare gerçek: `t=3–11s vehicle 0,11–0,25` (yaklaşan forklift) ·
`t=12–16s —` (çöküş, toz ve bulanıklık) · `t=17–18s person 0,12/0,14`
(kalkıp koşan operatör). Klip tam olarak anlatılan şeyi içeriyordu; biz
hepsini süzüyorduk.

#### Dondurma kaldırıldı

Dondurma 23 Ağustos'ta **takvim** gerekçesiyle konmuştu ve o gün doğruydu.
Ama gerçek gateway ve gerçek görüntü görülmeden konmuştu. **Bozuk bir sistemi
dondurmak onu bozuk tutar.** CLAUDE.md gerekçesiyle güncellendi.

#### Takip artık filtre değil, zenginleştirme

1 fps'te BoTSORT **yapısal olarak aç**: bir saniyelik boşlukta IoU eşleşmesi
tam da `FLOOR_VELOCITY >= 1.0`'ın hedeflediği hızlı harekette başarısız.
Sıfır kimlik bir uç durum değil, beklenen davranış. Sonuç: `velocities` ve
`vanished_tracks` bu boru hattında **neredeyse ölü sinyaller**; taşıyan
şeyler `person_count` ve hareket enerjisi. Bu yüzden tracker'a yatırım
yapılmadı (BoTSORT ayarı, optik akış, re-ID — hepsi bilerek reddedildi).

Tespit kayıt, takip kimlik ekler: `track_id: int | None`. `person_count`
bütün nesneleri sayıyor; `velocities`/`vanished_tracks` yalnız kimliği
olanları. İki tuzak bağımsız incelemeden geldi ve ikisi de test edildi:
`None` anahtarlar `current_by_id`'de çakışıp **farklı fiziksel nesneler
arasında hayalet hız** hesaplatıyordu, ve `vanished_tracks` yönlendirici
özetine `[None]` sızdırıyordu.

#### Körlüğü "olay yok" diye çevirmek

En değerli düzeltme buydu. `motion.py` "veri yok" ile "sıfır" ayrımını
titizlikle yapıyor; teslim katmanı o ayrımı çöpe atıp **yokluğu kanıt
sayıyordu**. Artık sıfır epizotlu koşu ikiye ayrılıyor:

> Algı katmanı bu kayıtta güvenilir tespit üretemedi (… kare farkı zirvesi
> 102,2 — görüntüde belirgin hareket var); olay olup olmadığı
> **DOĞRULANAMADI**. Bu bir "olay yok" hükmü değildir — kaydı bir operatör
> gözden geçirmeli.

Kök neden raporu da artık "dış darbe kaydedilmedi" gibi bir yokluk iddiası
kuramıyor.

#### Algıyı iyileştirmek boru hattını bozdu

Zenginleştirme **demo klibini geriletti** ve bunu iki bağımsız temel koşu
ölçtü: k05'te taban deseni `++--++++` → `++++++++`, epizot **1 (Yüksek,
00:30) → 0**. Sebep: kimliksiz insanları saymak 3. ve 4. pencereyi tabandan
geçiriyor, zorunlu görü örneği ise **yalnız tabandan düşen** pencerelere
gidiyordu — yani 00:30'daki devrilmeyi bulan bakış ortadan kalkıyor ve
yönlendirici sekiz kez `ignore` diyordu.

Ders öncekilerden farklı: burada bir koruma sinyali atmıyordu; **bir alt
katman iyileşince, üst katmanın gizlice ona bağımlı olduğu ortaya çıktı.**
Taban iki iş yapıyordu — yönlendirici sorulsun mu, ve görü nereye baksın —
ve yalnız biri onun işiydi.

Düzeltme: hareket enerjisi bütçeyi **bütün** pencereler üzerinde nişanlıyor.
Yönlendirici `ignore` derse ve pencere bütçede seçiliyse yine de bakılıyor —
`ignore` dalı, başka hiçbir şeyin bakmadığı tek dal. Üst sınır değişmedi
(10 dakikalık videoda ≤60 çağrı); değişen, hep-`ignore` bir koşunun 0 yerine
en çok 10 görü çağrısı ödemesi. **Artış düzeltmenin ta kendisi.**

#### Bilinen sınırlar (bilerek yapılmadı)

1. **Taban ve pencere özeti nesne körü.** k03'ün altı forklift tespiti depoya
   ulaşıyor ama `passes_floor()` ve `window_digest()` yalnız kişi/hız/kaybolan/
   toplanma okuyor. "Herhangi bir tespit tabanı geçirsin" maddesi bilerek
   EKLENMEDİ: park hâlinde kadrajda duran bir forkliftte her pencere geçer,
   yönlendirici video başına ~60 kez koşar ve yarışmanın puanladığı maliyet
   triyajı çöker. Tutarlı çözüm taban + özet + yönlendirici kurallarının
   birlikte değişmesi ve yeniden ölçülmesi.
2. **k03'te `participants` hâlâ boş.** Oradaki kişiler 0,12/0,14 puan alıyor;
   eşiği 0,10'a çekmek boş koridor kontrolünde ilk yanlış pozitifi getiriyor.
   Eşik manzarayı düzeltmek için indirilmedi.

### 0. Faz için taban ölçümü kuruldu — algı katmanı sayılarla (2026-08-25)

Algının zayıf olduğu biliniyordu ama **ne kadar zayıf olduğu bilinmiyordu.**
Bir öncekiler ("23 karenin 23'ünde sıfır tespit") tek bir klipteki gözlemdi;
karşılaştırılabilir bir taban yoktu, yani bundan sonraki hiçbir değişikliğin
iyileştirme mi gerileme mi olduğu söylenemezdi.

Ölçüm artık var: `benchmark/perception.py`, etiketler
`benchmark/perception_truth.json`, çıktı `bench/perception.json` +
`bench/perception.md`. Gateway istemiyor — YOLO yerel, ajan katmanı yok.

#### Neden `benchmark/run.py` yetmedi

O modül ajan katmanını ölçüyor: karar dağılımı, görü tetikleme oranı, Türkçe
çıktı payı. Hepsi doğru KPI'lar ve hepsi **algı katmanı kör olsa bile
üretilir** — kör bir koşu `kpi.json`'da "kararların %100'ü en ucuz kademede
kapandı" diye görünür. İki ölçüm birbirinin yerine geçmiyor.

#### Taban (tekstil fabrikası kazası, 116 kare @ 1 fps)

Video: bir işçi kumaşı silindire beslerken makineye kapılıyor (t=49 s),
ardından fabrika çalışanları toplanıyor (t=70'ten sonra sürekli 8+ kişi).
Etiketler el işi: her 8. saniye, 2× büyütülmüş kareye bakan bir insan sayarak.
Kalabalık karelerde sayım `±` ile veriliyor, saklanmıyor.

    varlık duyarlılığı      %72   (116 karenin 32'sinde SIFIR tespit)
    sayım duyarlılığı       %11   (ortalama 9,7 kişi var, 1,1 kişi görülüyor)
    zirve kişi sayısı        6    (gerçek zirve 22)
    kimlik atama oranı      %67   (19 ayrı kimlik)
    gerçek zaman katsayısı  0,14

**Kaza saniyesinde algı sıfır kişi görüyor** ve o saniye hareket enerjisinde
116 karenin **53.'sü** — tam ortalama. Yani ne tespit, ne triyaj o ana
bakmıyor. Bu, kararların olay anında verildiği bir mimaride en pahalı
başarısızlık: karar döngüsü doğru çalışsa bile bakacağı bir kanıt yok.

#### İkinci bulgu: takip katmanı hâlâ tespit eliyor

25 Ağustos'ta `if box.id is None: continue` kaldırıldı ve sözleşme "tespit
kayıttır, takip yalnız kimlik ekler" oldu. Süzgeç gerçekten kaldırıldı — ama
**yetmiyor.** Ölçüldü:

    takiple (boru hattı)   159 kutu    sayım duyarlılığı %11    zirve  6
    takipsiz (detect)      266 kutu    sayım duyarlılığı %22    zirve 10

Takip **41 karede kutu eledi, 0 karede ekledi.** Kayıp o `continue`'dan
gelmiyor; `model.track()` kutuları döngü onları görmeden önce eliyor
(elenenler düşük güvenli olanlar: medyan güven 0,44'ten 0,55'e çıkıyor).
Sözleşme koda yazıldı, kütüphaneye yazılmadı.

Varlık duyarlılığı ve sıfır tespit oranı iki yolda da aynı (%72 / %28) — yani
takip "bir şey gördük mü"ye mal olmuyor, "kaç tane gördük"ün yarısına mal
oluyor. Bu yüzden ölçüm ikisini yan yana yazıyor: tek sayı "algı zayıf" der,
iki sayı hangi katmanın ne kadarını yediğini söyler.

#### Ölçümün kendi kuralları

- **Manşet, sayıma değil varlığa dayanıyor.** Kalabalık bir CCTV karesinde
  kişi sayısı elle bile tam sayılamaz; "karede insan var mı" tartışmasızdır.
  `presence_recall` yalnız etiket `persons_present_every_frame: true` diyorsa
  üretiliyor — o iddia yokken üretilen sayı neyin duyarlılığı olduğunu
  söyleyemez.
- **`count_recall` `min()` ile sınırlı.** Sınırsız olsaydı gürültülü bir
  katman kaçırdığı kareleri fazla saydığı karelerle kapatır ve kör bir koşu
  %100 duyarlı görünürdü.
- **Ölçülemeyen her şey `None`.** `bench/kpi.json` ile aynı kural.
- **Rapor `.json` ile aynı komutta yazılıyor.** Ayrı komut olsaydı biri koşup
  diğeri koşmayabilir ve tabloyu okuyan kişi eski sayılara bakardı.

#### Bu ölçüm neyi ölçMÜYOR

Tek video, tek kurulum tipi (tavan CCTV, loş, tekstil). Buradan "sistem %72
duyarlı" çıkarılamaz — çıkarılabilecek şey "bu kayıtta %72" ve bir sonraki
değişikliğin bu sayıyı nereye götürdüğü. Yangın/duman gibi sınıfsız tehlikeler
zaten YOLO'nun işi değil (VLM'in işi) ve bu ölçüme hiç girmiyor.

### 0. Faz elden geçti — sayım duyarlılığı %11 → %93 (2026-08-25)

Taban ölçümü kurulduktan sonra beş değişiklik denendi (D1–D5). **Dördü
tuttu, biri ölçülüp reddedildi.** Sıra ve gerekçeler aşağıda; her sayı
`benchmark/perception.py` ile üretildi.

| | Taban | Şimdi |
| --- | ---: | ---: |
| Varlık duyarlılığı | %72,4 | **%99,1** |
| Sayım duyarlılığı | %11,0 | **%93,1** |
| Zirve kişi (gerçek 22) | 6 | 30 |
| Kaza saniyesinde kişi | 0 | 1 |
| Kaza enerji yüzdeliği | %45,2 | **%3,5** |
| Yok edilen kutu | %40 | %0 |
| Gerçek zaman katsayısı | 0,13 | 0,35 |

Ortalama sapma 8,6 kişi/kareden **2,3**'e indi; ortalama gerçek 9,7, ortalama
sayılan 10,7.

#### D1 — eşik 0,20 → 0,03: sorun modelde değildi

20 kişinin bulunduğu tek bir karede modele `conf=0.01` ile sorulunca **60
kişi adayı** dönüyor. Model kalabalığı buluyordu; boru hattı onu kapıda
eliyordu. Tek satır, sayım duyarlılığı %11 → %31.

#### D2 — takibin vetosu: doğru fikir, yanlış katman

25 Ağustos'ta kaldırılan `if box.id is None: continue` doğru bir düzeltmeydi
ama kayıp oradan gelmiyordu: **`model.track()` bir kare için en az bir onaylı
iz üretirse `results.boxes`'ı iz alt kümesiyle DEĞİŞTİRİYOR.** Kutular bizim
döngümüz görmeden yok oluyordu ve `botsort.yaml`'daki hiçbir eşik bunu
değiştirmiyor — bu bir ayar değil, bir postprocess semantiği.

Artık `model.track()` hiç çağrılmıyor. `detect_objects` kayıt,
`attach_track_ids` kimliği iliştirir. Sayım duyarlılığı %31 → %83.

**Ders:** bir sözleşmeyi koda yazmak, onu kütüphaneye yazmaz. Sözleşmenin
tutup tutmadığını ölçen bir sayı (`tracking_cost.boxes_lost`) olmasaydı bu
düzeltme "zaten yapılmış" sayılmaya devam ederdi.

#### D3 — kare hızı 1 → 3 fps ve bir ÖLÇÜM hatası

1 fps'in gerekçesi "görü bütçesini koruma"ydı ve **yanlıştı**: görü
kademesine giden şey `run.py:_clip_for`'un kaynak videodan kestiği mp4, bizim
kareler değil. Kare hızı ile VLM maliyeti zaten ayrıktı.

İlk ölçüm "5 fps daha kötü" dedi (%83 → %70) ve bu **ölçüm hatasıydı**:
ffmpeg'in `fps` filtresi farklı hızlarda aynı kaynak karesini seçmiyor —
1 fps'teki t=8 ile 5 fps'teki t=8 farklı görüntüler (ortalama mutlak fark
3–13 gri seviye). Etiketler 1 fps çıkarımına göre işaretlendiği için kare
bazlı karşılaştırma geçersizdi. `benchmark/perception.py:per_second` bunun
için var; saniye bazlı bakınca 5 fps %96,6 çıkıyor.

3 seçildi: 5'in kazandığı 3,5 puan gerçek zaman katsayısını 0,33'ten 1,03'e
çıkarıyor, yani görü çağrılarına bütçe kalmıyor.

Yan sonuç: `vanished_tracks` artık **saniye** cinsinden eşikli
(`vanish_after_s`) ve bir iz **bir kez** bildiriliyor. 5 fps'te eski tanım
200 ms'lik bir kesintiyi kaybolma sayıyordu.

#### D4 — triyaj: küresel büyüklük değil, yerel sapma

Kaza saniyesi enerjide 116 karenin 53.'südü. Yoğun bir fabrika zemininde
hareket her yerde yüksek; olayı ayırt eden şey **o bölgenin kendi
normalinden sapması**. 6x8 ızgara, hücre başına z-skor, kare skoru =
hücrelerin en büyüğü. `window_energy` de düz ortalamadan `TOP_K`
ortalamasına geçti — eski docstring bedeli zaten yazıyordu.

Kaza saniyesi **%45,2 → %3,5 yüzdelik** (13. / 347).

İki arıza testlerde yakalandı: iki ayrı geçiş kareyi iki kez okuyordu; ve
24 karelik temel 9 karelik bir koşuda hiç dolmayıp bütün skorları sessizce
`None` yapıyordu.

#### D5 — REDDEDİLDİ: fikir sağlam, iz kalitesi yetmiyor

"Makineye kapılan işçi" sinyal olarak *hızlanıp kadraj kenarına değmeden
kaybolan bir iz*. Uygulandı, ölçüldü, **çalışmadı**:

    min_established_s   içeri kaybolma   saniye başına
          1,0                381              3,30
          8,0                128              1,11

Hiçbir eşikte sinyal gürültünün üstüne çıkmıyor. Sebep tespit değil **iz
parçalanması**: ~25 gerçek kişi için 500'den fazla kimlik. Alan hesaplanıyor
ama hiçbir karara bağlanmıyor — ne `passes_floor`'a, ne prompt'a. Saniyede
iki kez "bir insan makineye kapıldı" diyen bir sinyal, bir güvenlik
sisteminde sessiz kalmaktan kötüdür.

Yan ürün olarak **gerçek bir hata** düzeldi: `interpreter._context` her
kaybolmayı "kadraj dışına çıkan" diye anlatıyordu — makineye kapılan bir
insan için tam tersi. Ayrıca pencerenin ORTA karesini okuyordu; sakin bir
orta kare 9. saniyedeki olayı gizliyordu. İkisi de düzeldi.

#### Ölçülüp ELENEN yollar

Popüler tavsiyede geçiyorlar ve bu görüntüde **ölçülüp yanlış çıktılar**;
`gozcu/config.py` bunları tekrar denenmesin diye taşıyor.

- **Çözünürlüğü artırmak** — TERS ETKİ. Kişi güveni 640'ta 0,647; 896'da
  0,159; 1280'de sıfır tespit. Kaynak 960x720 ve gerçek optik detay o kadar.
- **Daha büyük model** — TERS ETKİ. conf 0,05'te sayım duyarlılığı:
  11n %89,7 · 11s %79,3 · 11l %64,1 · 11m %56,6.
- **YOLO26 / NMS'siz mimari** — yolo11n'i geçemedi.
- **NMS iou 0,3–0,4** — YÖN YANLIŞ; kalabalıkta yüksek eşik gerekiyor
  (F1: 0,3 %72,2 · 0,7 %82,4 · 0,8 %82,8).
- **Model değiştirmek** — en iyi aday (yolo11n @0,08, F1 %82,4) mevcut
  modelle (YOLOE @0,03, F1 %83,7) berabere; YOLOE ayrıca `forklift`
  kelimesini taşıyor ve COCO'da forklift sınıfı yok.
- **CrowdHuman ağırlıkları** — indirilebilir kontroller topluluk fork'ları,
  lisansları belirsiz. Şartname "açık kaynak" diyor; belirsiz lisanslı
  ağırlık teslime girmez.

#### Üç klipte doğrulandı — tek klibe aşırı uyum yok

| Klip | Sonuç |
| --- | --- |
| Kontrol (olaysız, 36 kare) | 3 kişi kutusu / 3 kare, zirve 1 — yanlış pozitif düşük |
| Raf çökmesi k03 (69 kare) | 26 kişi + 40 forklift kutusu. **Bu klip eskiden 23 karede 0 tespit veriyordu.** decision-log'daki "k03'te `participants` hâlâ boş" sınırı kalktı. |
| Demo k05 (231 kare) | 348 kişi + 739 diğer sınıf kutusu |

#### Açık kalan

- **`passes_floor` artık ayırt etmiyor.** Varlık duyarlılığı %99 olunca
  `person_count > 0` neredeyse her pencerede doğru. Taban "ne zaman
  sorulacağını" belirliyordu; artık hep soruyor. 115 s'lik videoda ~12
  pencere olduğu için maliyet kabul edilebilir, ama taban bir şey yapmıyor
  ve bu bilinerek bırakıldı.
- **İz parçalanması.** ~25 kişi için 500+ kimlik. `velocities` ve
  `vanished_tracks` bundan zarar görüyor ve D5 bu yüzden reddedildi.
  Sıradaki iş burası.
- **Fazla sayım.** Zirve 30, gerçek 22. Ajan katmanının ihtiyacı eşik ve
  eğilim olduğu için kabul edildi, ama duyarlılık için ödenen bedel bu.

### Konsol şartnameye göre elden geçti (2026-08-25)

Şartname yeniden okundu ve iki sert kısıt bugünkü konsolu doğrudan
yanlışladı: **sunum 4 dakika, demo videosu 1 dakika** (§11), ve **bu bir
çevrimdışı kayıt** (§3 "bir video sisteme yüklenir"). Bekleyen bir arayüz o
bütçeyi yiyor, ve operatörün gerçekten müdahale edeceği bir an yok.

Plan: [konsol PRD](../superpowers/specs/2026-08-25-konsol-prd.md).

#### En büyük bulgu: araçlar çalışıyordu, GÖRÜNMÜYORDU

Yedi saha aracının çağrıları `store.actions()`'a yazılıyor ve arayüzde
**hiçbir yerde** görünmüyordu — yalnız kapanış JSON'unun içinde metin olarak.
Şartname §7 bunu açıkça puanlıyor: *"Mock fonksiyonların ajanın araçları
olarak başarıyla kullanılması"*, %35'lik kriterin maddesi. Jüri, araçların
çalıştığını göremiyordu. En ucuz puan kaybı buydu ve veri zaten depodaydı.

#### Duraklama kalktı, müdahale kartı geldi

`on_event` artık `resume.wait()` çağırmıyor. Ölçülen arıza (iz kaydı):
`konsol.bekle` **115 saniye** açık kaldı, video 4. pencerede durdu, operatör
altı kez "devam et sorun yok" yazdı — ve sohbet `resume`'u hiç set etmiyordu
(`resume.set()` yalnız `resume_btn.click`'te).

Yerine her yükseltme bir **kart**: ne gördü, ne dedi, hangi araçları çağırdı,
hangileri için onay istedi, gerekçesi ne. Üstünde tek cümle: *"Gerçek zamanlı
kurulumda ajan bu anda müdahale ederdi."* Anlatı korundu, engel kalktı.

**Kart damgası `event_ts`, `start_ts` DEĞİL.** `models.Episode` docstring'i
`start_ts`'in pencere sınırı olarak kalmak zorunda olduğunu yazıyor; kartta
onu göstermek olayı 10 saniyeye kadar yanlış yere koyardı. Başlığı "MÜDAHALE
ANI" olan bir kartta doğru olması gereken tek sayı bu.

`Adım adım` anahtarı (varsayılan KAPALI) eski davranışı birebir geri
getiriyor. Eski duraklama testi silinmedi — anahtar AÇIK koşuyor.

#### Nöbetçi'nin kilitlenmesi

Promptta iki kural çıkışsız bir döngü kuruyordu: her düzeltme
`correct_observation` istiyor, her cevap açık olayı yeniden gündeme
getiriyordu. Operatör altı kez "devam et" dedi, ajan altı kez aynı onayı
istedi. Çıkış kuralları eklendi: geçiştirmeyi **kabul et ve konuyu bırak**,
aynı onayı **iki defadan fazla isteme**, hatırlatmayı **bir kez** yap.

#### Yuvaları sayıyla indekslemek bir kez ısırdı

Ekran yuvaları 11'den 15'e çıktı. Araya iki yuva eklendiğinde testteki
`final[7]` sessizce başka bir bileşeni okumaya başladı. Yuvalar artık
`SLOT` sözlüğüyle ADIYLA indeksleniyor ve iki koruma testi
(`SLOT` ile `SCREEN_SLOTS` ayrışamaz, `_refresh`/`_blank` tam sayıda değer
döndürür) bunu bir daha sessiz bırakmıyor.

#### Ayrıca

- **KPI paneli** (§4 zorunlu): algı bloğu `bench/perception.json`'dan
  **okunuyor**, hesaplanmıyor — 35 saniyelik bir ölçümü demo sırasında
  koşturmak sunum bütçesini yer. Analiz başlatılmadan da görünüyor.
- **Zorlu koşul düğmeleri** (§6): bağlam değiştir · yanlış bilgi ver · yetki
  dışı iste. Bilinmeyen anahtar sessizce boş mesaj göndermiyor.
- **Sekmeli düzen**: Canlı izleme · Müdahaleler · Nöbetçi · Çıktı · Ölçüm.
  Rozet şeridi ve durum çubuğu sekmelerin dışında.
- Sayılar Türkçe ondalık virgülüyle (`%99,1`) — depodaki bütün metin öyle.

### Donmanın gerçek sebebi: metin kademesi 1800 saniye bekliyordu (2026-08-26)

"Rastgele takılıyor" şikâyeti üç gün boyunca algı katmanına, ffmpeg'e ve
konsolun duraklamasına yıkıldı. İz kaydı açılınca sebep bir bakışta görüldü:

    [00:38:34 +180.1s] → fast.ask     model=llm-fast yük=0.01MB
    [00:56:55 +1281.3s] ⋯ fast.ask    hâlâ çalışıyor, 1101.2 s

**`fast.ask` 1106 saniye asılı kaldı ve hâlâ sürüyordu.** Tek bir deneme bile
bitmediği için `GATEWAY_RETRIES` hiç tetiklenmedi; kesinti dalı da çalışmadı.
Koşu bozulmadı, **dondu** — ve bu ikisi ekranda aynı görünüyor.

Sebep `GATEWAY_TIMEOUT_S = 1800`. O değer VİDEO çağrıları için seçilmişti
(kendi yorumu bunu yazıyor) ama **her kademeye** uygulanıyordu. Aynı koşuda
ölçülen normal gecikmeler:

    router 0,3–1,8 s · fast 0,9–1,3 s · main 0,8–2,6 s · guard 0,1 s
    vlm    7,0–8,7 s   ← uzun olan yalnız bu

Metin kademelerinin 1800 saniyeye ihtiyacı yok. `GATEWAY_TEXT_TIMEOUT_S = 90`
eklendi (ölçülen en yavaş metin çağrısının otuz katı) ve uzun zaman aşımı
`LONG_TIMEOUT_TIERS = {"vlm"}` ile sınırlandı. En kötü hâl 90 dakikadan
**4,5 dakikaya** indi, ve asılma artık kesintiye dönüşüyor: kademe `degraded`
işaretleniyor, dört anahtar yine üretiliyor.

**Ders:** bir zaman aşımı, en yavaş çağrıya göre seçilip herkese uygulanırsa
en hızlı çağrının arıza süresi de en yavaşınki kadar olur. Zaman aşımı
kademenin kendi ölçüsüne bağlanmalı.

Ayrıca: iz kaydında iç ve dış adım aynı anda kalp atışı üretiyordu; 18 dakika
asılı kalan bir çağrıda bu 440 satırlık gürültü demek. `step(heartbeat=False)`
eklendi ve iç deneme artık susuyor.

### Şartname repoya taşındı; final tarihi yanlış biliniyordu (2026-08-26)

Yarışma kuralları depoda hiçbir yerde yazılı değildi. Her yeni oturumda
şartname PDF'i dışarıdan yapıştırılıyordu — pahalı, tekrarlı ve en kötüsü
**sessizce eskiyen** bir alışkanlık: yapıştırılan sürümün güncel olup olmadığını
kimse kontrol etmiyordu.

[`docs/00-overview/sartname.md`](../00-overview/sartname.md) bunun karşılığı.
Şartnamenin on yedi bölümü, takvim, teslim listesi, puan cetveli ve
organizasyonun 24–25 Ağustos e-postaları tek dosyada; her satırın hangi
kaynaktan geldiği işaretli. CLAUDE.md ve `docs/README.md` oraya işaret ediyor.

**Taşıma sırasında iki hata çıktı.**

**1. Final tarihi.** Depodaki bütün bantlar *"Teslim: 26 Ağustos 23:59"*
diyordu ve orada bitiyordu. Şartname §11 (*"yarışmanın son 24 saati fiziki
ortamda"*) ile 25 Ağustos tarihli e-posta birlikte okununca gerçek şu:
26 Ağustos yalnız **çevrimiçi sürecin** kapanışı; yarışma **27–28 Ağustos'ta
Bilişim Vadisi Kocaeli kampüsünde, takımın tüm üyeleriyle fiziken** bitiyor.
Yani teslim gecesi son gün sanılıyordu, oysa ertesi gün sunum vardı.

**2. Sunum süresi.** Görev 18 tek bir *"4 dakikaya sığdığı prova edilir"*
satırı taşıyordu, ama iki ayrı video olduğu yazılı değildi: teslim paketindeki
**≤10 dakikalık** demo videosu jüri incelemesi için, sunumda oynatılan
**1 dakikalık** video ondan ayrı bir kurgu. İkisini karıştırmak sunumda
dört dakikanın çeyreğini yanlış videoya harcamak demekti.

Ayrıca: `docs/README.md` hâlâ *"algı katmanı donuk"* diyordu — o karar
25 Ağustos'ta kaldırılmıştı ve CLAUDE.md ile çelişiyordu. Düzeltildi.

**Ders:** dışarıdan her oturumda yapıştırılan bir belge, depoda olmadığı için
denetlenmiyor da. Şartname repoya girdiği anda iki tane bayat tarih ortaya
çıktı.

**Repoya girmeyen:** e-posta ekran görüntüleri. İçlerinde takımın LLM bearer
token'ı, Qdrant anahtarı ve arayüz parolası açık hâlde duruyor; depo `public`
yapılacağı için commit'lenmiş bir anahtar geri alınamaz.

### Ajan araçlarını çağırmıyordu — üçe bir kaybediyordu (2026-08-26)

Ölçülen arıza: canlı koşuda yönlendirici 12 pencerenin çoğunda 0,90–0,95
güvenle yükseltti, Nöbetçi **7 kez** çağrıldı, risk analisti Orta/Yüksek
biçti — ve `store.actions()` **boştu**. Yedi saha aracının hiçbiri
çağrılmadı. Şartname §7 bunu doğrudan puanlıyor ("Mock fonksiyonların ajanın
araçları olarak başarıyla kullanılması", %35 kriterin maddesi).

Önce ağ geçidi suçlandı; ölçüldü ve **suçsuz çıktı**: gerçek şemalarla
doğrudan sorulduğunda `llm-large` da `llm-fast` de doğru araçları doğru
parametrelerle çağırıyor. Sorun promptta.

#### Üç "önce sor" baskısı, bir "çağır" kuralı

    - Kameradan göremediğini UYDURMAZSIN, operatöre SORARSIN
    - Geri dönüşü zor aksiyonlarda İZİN İSTERSİN
    - escalate(): "Operatöre kendin haber ver. Belirsizlik varsa SOR."

Karşısında tek bir kural vardı ("geri alınabilir aksiyonları beklemeden
çağırırsın") ve son sözü söyleyen `escalate()`'in kendi mesajıydı — o da
"sor" diyordu. Model üçe bir kaybetti ve operatörü sorguya çekti: koruyucu
ekipman takılı mı, ekipman çalışıyor mu, zemin ne kadar kaygan.

#### Onay kapısı kaldırıldı

`NEEDS_APPROVAL` **boşaltıldı**. Bu araçlar `field_systems`'te birer sözlük
döndüren mock: ne gerçek bir hat duruyor, ne gerçek bir sağlık ekibi çıkıyor.
Olmayan bir eylemi kapılamak, ajanı yarışmanın puanladığı davranıştan
alıkoyuyordu.

Makine **silinmedi**: `call_tool`, `_refuse_second_gate` ve konsolun onay
çubuğu yerinde. `GOZCU_NEEDS_APPROVAL="halt_production_line"` ile kapı geri
geliyor ve `gated` fixture'ı o yolu sınamaya devam ediyor — gerçek saha
sistemlerine bağlanan bir kurulumda gereken şey o.

Kapısız iki fazlı araç bir tuzak doğurdu ve testle yakalandı: `call_tool`
`approved`'ı yalnız kapılı araçlarda dolduruyordu, yani kapı boşalınca
`halt_production_line` sonsuza dek `awaiting_approval` döndürecekti — ajan
aracı çağırsa bile hiçbir şey olmadan. Kapısız kurulumda tek faz var: eylem.

#### Prompt: önce eylem, sonra soru

`ESCALATION_INSTRUCTION` ayrı bir sabit oldu ve artık şunu diyor: *önce
gerekli saha araçlarını çağır, sonra ne yaptığını anlat ve en fazla iki soru
sor.* Sistem promptuna da açık kural eklendi ve araçlar **adıyla** sayıldı —
soyut kalan kural modele uygulanmıyordu.

Belirsizlik kuralı silinmedi, **daraltıldı**: uydurma yasağı artık aracı
çağırmayı değil, görülmeyeni ANLATMAYI yasaklıyor.

#### Ölçülen sonuç

Aynı epizot, gerçek modellerle:

    öncesi: 0 araç çağrısı, operatöre üç soru
    sonrası: 4 araç çağrısı — dispatch_medical, radio_call, site_alarm,
             open_safety_incident — ardından ne yapıldığının özeti ve iki soru

**Ders:** bir davranış kuralı promptta kaç kez tekrarlandığıyla değil, kaç
karşı kuralla yarıştığıyla kazanıyor. Sayım yapılmamıştı.

### Klip kesme kaynağı BÜYÜTÜYORDU — üç kat hız, yarı token (2026-08-26)

İz kaydı `görü.klip-kes`'i koşunun en pahalı tek kalemi olarak gösterdi:
375 saniyelik bir koşuda **97,8 saniye**, bütün görü çağrılarının toplamından
(83,6 s) fazla. Sebebi ffmpeg'in yavaşlığı değildi.

`CLIP_SCALE = "scale=1280:-2"` 24 Ağustos'ta canlı ölçülmüştü — ama o ölçüm
**1280'den geniş** bir kaynaktan yapılmıştı; orada 1280 bir küçültme. Bizim
kaydımız 960x720 ve aynı ifade onu 1280x960'a **büyütüyordu.** Büyütme hiçbir
bilgi eklemiyor: yalnız kodlama süresi, bayt, base64 yükü ve token ekliyor.

`evren-gateway.md`'nin "çözünürlük hızdan önce gelir" kuralı kaynağın altına
İNMEMEYİ söylüyor. Üstüne çıkmayı değil. Kural yanlış tarafa uygulanmıştı.

#### Ölçüm (aynı 10 s pencere, 960x720 kaynak)

    scale=1280:-2                 1,86 s   2,23 MB   1280x960 ← büyütülmüş
    min(1280,iw)                  1,05 s   1,52 MB   960x720
    min(1280,iw) + veryfast       0,59 s   1,22 MB   960x720   ← seçilen
    min(1280,iw) + ultrafast      0,31 s   3,78 MB   960x720   ← reddedildi
    -c:v copy                     0,04 s   2,28 MB   960x720

`ultrafast` bir tuzak: en hızlı kodlama ama **kaynaktan bile büyük** dosya.
Kazanılan saniye base64 yükünde ve token sayısında geri veriliyor.

#### Gerçek gateway'de doğrulandı

Aynı pencere, aynı soru:

    eski: 2,17 MB · 8,4 s · 12.418 token
    yeni: 1,18 MB · 5,3 s ·  7.018 token

Cevap kalitesi düşmedi — **arttı**: yeni klipte model "bir işçi makinenin
üzerine çıkmış" ve "koruyucu ekipman yok" ayrıntılarını da yakalıyor.
Beklenen bir şey, çünkü bilgi içeriği aynı; büyütülmüş kare yalnız
enterpolasyon gürültüsü taşıyordu.

#### Kazanç

Pencere başına 10,3 s → 5,9 s. On iki pencerede **123 s → 71 s**, ve
64.800 token tasarrufu. Kazanç iki yerden geliyor: kodlama hızı ve daha
küçük yükün görü çağrısını hızlandırması.

**Ders:** "canlı ölçüldü" bir sabiti dokunulmaz yapmıyor. Ölçümün hangi
girdiyle yapıldığı sabitin kendisi kadar önemli, ve o girdi değişince sabit
sessizce yanlış tarafa çalışabiliyor.

### Şemalı kod çözümü kaçıyordu — 183 saniyelik `fast.ask` (2026-08-26)

ffmpeg düzeltmesinden sonraki ilk tam koşu 598 saniye sürdü ve iz kaydı
sebebi tek satırda gösterdi:

    ✓ fast.deneme   91857 ms   1/3
    ✓ fast.deneme  183161 ms   1/3

Aynı koşuda **router 0,4 s · guard 0,2 s · embed 0,1 s · main 0,9–4,6 s ·
vlm 6,4–17,1 s.** Yani ne bağlantıda ne ağ geçidinde genel bir sorun vardı;
yalnız **şemalı** `llm-fast` çağrısı kaçıyordu. İki çağrı tek başına
275 saniye — koşunun neredeyse yarısı.

`Gateway.ask`'in kendi docstring'i bu arızayı **zaten tarif ediyordu**: *"üst
sınır olmadan strict-JSON şema kod çözümü kaçak tekrara girip `max_tokens`
tükenene kadar yineliyor."* Ama tavan yalnız GÖRÜ çağrısına konmuştu
(`interpreter.MAX_TOKENS = 1024`). Sentezleyici, yönlendirici, risk analisti
ve raportör tavansızdı — dördü de şemalı.

#### Zaman aşımı bunu neden yakalamadı

`GATEWAY_TEXT_TIMEOUT_S = 90` konmuştu ve çağrı **183 saniye** sürdü. Çelişki
değil: httpx'in `timeout`'u **işlem başına**, toplam değil. Okuma zaman aşımı
"bir sonraki veri parçasını kaç saniye beklerim" demek. Model token üretmeye
devam ettikçe parçalar akıyor ve sayaç her seferinde sıfırlanıyor.

İki arıza, iki koruma:

| Arıza | Belirti | Koruma |
| --- | --- | --- |
| Bağlantı **ölü** | hiç veri gelmiyor | `GATEWAY_TEXT_TIMEOUT_S` |
| Kod çözümü **kaçıyor** | veri geliyor, bitmiyor | `SCHEMA_MAX_TOKENS` |

Zaman aşımı 1106 saniyelik donmayı çözdü ve doğruydu; bu ondan farklı bir
arıza ve ayrı bir korumaya ihtiyacı vardı.

#### Tavan çağrı yerine değil, GEÇİDE kondu

`SCHEMA_MAX_TOKENS = 2048`, `Gateway.ask` içinde: şema verilmiş ve tavan
verilmemişse otomatik uygulanıyor. Dört ayrı çağrı yerini tek tek yamalamak
aynı arızayı beşinci çağrı yerinde geri getirirdi — ve sessiz hâli 183
saniyelik bir kilit demek.

2048 bilerek geniş: **128, 256 ve 512 ölçülmüş ve üçü de boş dize
üretmişti** (akıl yürütme izi bütçeyi yiyor, bkz. `interpreter.MAX_TOKENS`).
Dar bir tavan kaçak kod çözümünü değil, çıktının kendisini öldürür.

#### Aynı koşuda doğrulanan ffmpeg kazancı

    klip kesme   1.836–2.532 ms  →  405–660 ms
    token        13.196–13.528   →  4.923–8.714

**Ders:** bir docstring arızayı doğru tarif edip yanlış yerde çözebilir.
Tarif kod tabanında duruyordu; eksik olan, korumanın bütün çağrı yerlerini
kapsayan tek bir yere konmasıydı.

---

## 26 Ağustos — Konsol beş sekmeden ikiye: oluş sırasında besleme

**Görev 19** · `gozcu/ui/feed.py`, `gozcu/ui/console.py`, `gozcu/store.py`,
`gozcu/loop.py` · [spec](../superpowers/specs/2026-08-26-canli-akis-konsolu-design.md)

### Sekmeler işi YANLIŞ eksende bölüyordu

25 Ağustos'ta eklenen beş sekme doğru bir sorunu çözdü (4 dakikalık sunumda
uzun kaydırma) ama bölme ekseni **kaynaktı**: devirler bir sekmede, araç
çağrıları başkasında, süpervizörün konuşması üçüncüde. Hepsi aynı on saniyede
olup bitmiş şeylerdi.

Şartname §7 puanın %35'ini teknik mimariye veriyor ve alt başlığında **"çok
adımlı karar zincirleri"** yazıyor. Zincir sistemde vardı; ekranda bir arada
yoktu. Yeni eksen **zaman**: `CANLI` olan biteni, `RAPOR` teslim edileni.

### Sıra `seq`, `ts` DEĞİL

Beslemenin sırası `Store.journal()`'ın küresel yazma sırası. `ts` ile
sıralamak iki ayrı sebeple yanlış:

1. **Beraberlik.** Bir pencerenin bütün üretimi `window[0].ts` civarına
   düşüyor ve satır kimlikleri tablo başına artıyor — beraberliği çözecek
   alan yok. Sabit bir "boru hattı sırası" uydurmak ekrana yaşanmamış bir
   sıra bastırırdı.
2. **Telafi.** `catch_up()` sonradan yazılan bir kaydı **önceki** bir video
   saniyesine koyuyor. `ts` sıralaması onu yaşanmadığı bir geçmişe taşır.

Damga ekranda duruyor ve hangi saniyeye ait olduğunu zaten söylüyor.

### Anlık görüntü, çünkü epizot değişiyor

Defter satırını canlı satıra çözmek, koşunun başındaki bir girdiye epizodun
**sonundaki** özetini, riskini ve anlarını bastırırdı — ekran o an
söylenmemiş bir şeyi söylemiş gibi görünürdü. Değişen kayıtlar (epizot,
aksiyon onayı) kendi anlık görüntüsünü taşıyor; değişmeyenler canlı
çözülüyor ve kayamazlar.

`origin` alanı `update_episode`'un iki çağıranını ayırıyor: sentezleyici
kaynaştırıyor, süpervizör operatörün sözüyle **düzeltiyor**. Tek satıra
düşerlerse insan müdahalesi model çıktısı gibi görünür ve %20'lik otonomi
kriteri tam olarak bu ayrımı soruyor.

### Depo kilidi — gizli bir arıza, defterle ölümcül

Konsolda iki yazar iş parçacığı var: boru hattı ve Gradio olay iş parçacığı
(`talk`, onay, `catch_up`). **Ölçüldü:** kilitsiz 400+400 yazmada aynı
`lastrowid` iki kez dağıtıldı ve `InterfaceError` atıldı. Kilitle 800 yazma,
800 benzersiz, sıfır hata.

`sqlite3.threadsafety == 3` tek bir `execute`i güvenli kılıyor ama iki
ardışık `execute` + `lastrowid` okumasını **kılmıyor**. `console.py` bunu
docstring'inde *"Depoda kilit yok"* diye yazıyordu; bugüne kadar sessizdi,
defterle birlikte beslemenin bütün sırasını karıştıracaktı.

**Ders:** kod tabanı arızayı biliyordu ve yazmıştı. Yazılı olmak ölçülmüş
olmak değildir.

### `column-reverse` — sonuç doğru, mekanizma sanılan değil

Besleme kalp atışında (1 s) bütünüyle yeniden çiziliyor; düz bir kaydırma
kutusu her çizimde tepeye zıplar. `column-reverse` çözüyor — ama
**sabitlenerek değil, yeniden doğarak**: DOM tamamen değişiyor ve taze bir
`column-reverse` kaydırıcı `scrollTop = 0` ile, yani görsel altta başlıyor.

Tarayıcıda ölçüldü: üç ardışık tam `innerHTML` değişiminde `scrollTop` 0
kaldı, alt kenardaki girdi her seferinde en yeni olan oldu (3 → 12 → 18).

Bedeli: jüri geçmişi okumak için yukarı kaydırdıysa bir sonraki çizim onu en
alta atardı. Bu yüzden `_feed_slot` dizeyi karşılaştırıp değişmemişse
**`gr.skip()`** döndürüyor. `feed_html`'in deterministik olma zorunluluğu
buradan geliyor.

### Susmak, uydurmaktan iyidir

Tanınmayan defter kaynağı, silinmiş satıra işaret eden girdi ve bilinmeyen
risk seviyesi — üçü de sessizce atlanıyor ya da kendi rengine düşüyor.
Arşiv epizotları (`load_history`) beslemeye hiç girmiyor: beslemede
"sentezleyici olay açtı" diye görünürlerse bu videoda olmamış bir şey iddia
edilir.

### Kör inceleme: besleme üç yerde yalan söylüyordu

Uygulama bittikten ve 830 test yeşile döndükten SONRA koşan kör bir inceleme,
beslemenin üç ayrı yerde olmamış bir şey söylediğini buldu — hiçbiri testte
görünmüyordu çünkü testler benim kurduğum dünyayı sınıyordu, sistemin
gerçek çağrı grafiğini değil.

1. **Risk analistinin araçları süpervizöre yazılıyordu.** `assess_risk`
   `Supervisor.escalate`'in İÇİNDE koşuyor ve `call_tool`'u varsayılan
   `actor="agent"` ile çağırıyor; besleme `agent → supervisor` eşlemesi
   yapıyordu. `ActionRecord.caller` eklendi.
2. **Kendiliğinden rozeti komşuluktan türetiliyordu** ve türetme iş
   parçacıkları arasında kırılıyor. Artık yazma anında kaydediliyor.
3. **Müdahale kartı yanlış cümleyi alıntılayabiliyordu** — `ts` anahtarlı
   arama, yükseltmeden önceki bir sohbet cevabına düşüyordu.

**Ders:** "her satır hangi ajanın ürettiğini söyler" diye bir sözleşme
yazmak, o sözleşmeyi tutmaya yetmiyor. Atıf, veriyi ÜRETEN yerde
kaydedilmediği sürece tüketen yerde tahmin edilir — ve tahmin sessizce
yanlış olur. Aynı ders anlık görüntü kuralında bir kez daha çıktı:
`window_record` "değişmez" sayılmıştı, `set_window_outcome` eklenince
ilk satır geriye dönük düzeltilmiş akıbeti göstermeye başladı.

---

## 26 Ağustos — Gerçek bir koşu, testlerin göremediği beş yalan

**Görev 20** · [görev dosyası](../tasks/20-dogruluk.md)

872 test yeşildi ve sistem yine de dört ayrı yerde olmamış şeyler söylüyordu.
Hepsi ancak elle etiketli olmayan, gerçek bir fabrika videosu koşturulup
besleme okunduğunda göründü.

### Bir katmanın arıza metni, başka bir katmanın verisi oldu

En ağırı buydu. Sentezleyici boş döndü, epizot özeti *"Sentez katmanı boş
yanıt döndürdü"* oldu, süpervizör bu metni `kritik olay:` diye prompt'ta
gördü ve üstüne bir dünya kurdu: **var olmayan bir bölge** (`Sentez Hattı`),
oraya alarm, telsizle operatör çağrısı, sağlık ekibi. Hiçbiri yaşanmamıştı.

Saha araçları dürüsttü — hepsi `zone_unresolved` döndürdü — ve ajan okumadı.

**Ders:** bir tanı metni, tüketen katman onu tanıyamadığı sürece veridir.
"Anlaşılır bir hata mesajı yazmak" yetmiyor; **yapısal** bir işaret gerekiyor
(`Episode.summary_source`), çünkü bir sonraki katman metni okumuyor, kullanıyor.

### Ölçülmüş bir arıza, ayrım yapılmadığı için kullanılamıyordu

`config.SCHEMA_MAX_TOKENS` yorumu "dar tavan boş dize üretir, çünkü akıl
yürütme izi bütçeyi yiyor" diye **zaten yazıyordu**. Ama `Gateway.ask`
`finish_reason` okumuyordu, yani çalışırken "bütçe bitti" ile "model sustu"
ayırt edilemiyordu ve o ölçüm hiçbir işe yaramıyordu.

**Ders:** bir arızayı belgelemek onu görünür kılmıyor. Ayrımı **koşarken**
taşıyan bir alan yoksa, belge yalnızca sonradan okuyanın işine yarar.

### Görü kademesi dekoratifti

Yönlendirici görüntü görmüyor (tasarım gereği) ve `inspect` diyor. `inspect`
dalı görüyü çağırıyor, parasını ödüyor ve **sonucu atıyordu** —
`notable_event` yalnız `_forced_sample` içinde okunuyordu. 00:05'te
yorumlayıcı "bir forklift başka bir forkliftin üstünde" dedi, olay 00:40'ta
açıldı: kameranın gördüğü şeyin kararla ilgisi yoktu.

**Ders:** bir katmanın çağrılıyor olması, kullanıldığı anlamına gelmiyor.
"Görü katmanımız var" ile "görü katmanı kararı etkiliyor" arasındaki fark,
testlerde değil çağrı grafiğinde duruyor.

### Sayı, "neyi kaçırdı"yı cevaplamıyor

Algı kalitesi yalnız `bench/perception.json`'daki oranlarla görülebiliyordu.
`gozcu/annotate.py` artık kutuları, iz kimliklerini ve **pencere başına
yönlendirme kararını** karelere çiziyor; taban geçemeyen pencere kırmızı, yani
hiçbir katmanın bakmadığı anlar bakışta görünüyor.

**Ders:** bir ölçüm neyin yanlış olduğunu söyler, nerede olduğunu değil.
25 Ağustos'ta 23 karede sıfır tespit çıkmıştı ve bu ancak elle bakılarak
anlaşılmıştı — çünkü katmanın gördüğünü gösteren hiçbir yüzey yoktu.

---

## 26 Ağustos — ikinci canlı koşu: beş yeni yalan, dürüstlük onarımları

**Kaynak:** [tasarım spec'i](../superpowers/specs/2026-08-26-run-truthfulness-fixes-design.md)
· [plan](../superpowers/plans/2026-08-26-run-truthfulness-fixes.md) ·
commit'ler `6e93c05`..`bccbb01`.

Görev 20'nin onardığı beş yalandan sonra aynı forklift devrilme klibiyle
koşulan İKİNCİ bir canlı koşu, beş YENİ arıza zinciri ölçtü — hiçbiri Görev
20'nin 872 testiyle görünmüyordu, çünkü testler yine sistemin kurduğu dünyayı
sınıyordu, gerçek çağrı grafiğini değil. Üç karar burada kayda geçiyor;
tamamı için gerekçe ve reddedilen alternatif spec'in ilgili bölümünde.

### Bölge doğrulaması kaldırıldı

**Eski karar** (`field_systems` docstring'i, Görev 10): bölge/hat adı
fikstürde çözülemezse araç `zone_unresolved` / `line_unresolved` /
`zone_has_no_line` döndürsün — gerekçe *"serbest metne siren çaldırmak
olmayan bir bölge uydurmaktır."*

**Ters ölçüm:** aynı klipte gerçek bir forklift devrilmesinde **6/6
`dispatch_medical` VE 6/6 `site_alarm` çağrısı `zone_unresolved` döndü**;
forklift ve operatör kamerada apaçık görünürken sahaya **sıfır** mock
müdahale ulaştı. Disiplin olmayan bir riski (uydurma bölge adıyla yanlış yere
müdahale) önlerken gerçek bir zararı (hiç müdahale olmaması) göze almıştı —
yanlış takas.

**Yeni kural:** mock her adı kabul eder ve her çağrı başarıyla döner. Bölge
çözülürse fikstürdeki gerçek ekip/ETA/hat kullanılır; çözülemezse sabit bir
varsayılana düşülür, ama aksiyon yine yürür. Bilinmezlik kaybolmuyor — model
neyi bilmediğini defterde `zone_id=None` ile taşımaya devam ediyor, yalnız
artık müdahaleyi engellemiyor.

**Elenen alternatif:** bölge adlarını tool şemasına `enum` olarak koymak.
Reddedildi çünkü katı şema modeli, bölgeyi **bilmediğinde** de geçerli bir ad
seçmeye zorlardı — "kırmızı kamyon önü" yerine rastgele ama geçerli görünen
uydurma-ama-geçerli bir "B-Hattı" yazılırdı; serbest metnin dürüstlüğü
(neyin bilinmediği okunabilir kalması) kaybolurdu. Mock'un her adı kabul
etmesi hem müdahaleyi hem bu dürüstlüğü koruyor.

`gozcu/tools/field_systems.py`, `gozcu/tools/registry.py` (`_incident_guard`
artık `NO_SUCH_EPISODE`'u reddetmiyor; yineleme kısa devresi — aynı epizoda
ikinci kayıt `duplicate` + ilk `record_no` — korunuyor).

### Token politikası

**Ölçüm:** `SCHEMA_MAX_TOKENS=2048` tavanında pencerelerin **~%60'ı**
tükendi, her tükenme genişletme-tekrarı mekanizmasını tetikleyip
**20–50 saniyelik** ikinci bir denemeye düştü; raportör kademesinde 4096'lık
tavan da yetmedi ve `summary` bir arıza kaydı (*"Rapor katmanı boş yanıt
döndürdü"*) olarak teslim edildi — şartnamenin `risk: "Kritik"` alanının
hemen yanında.

**Yeni kural:** genişletme-tekrarı mekanizması tamamen silindi. Tek cömert
sigorta: şemalı çağrı tavanı 8192, raportör çağrısı 16384. Tekrar yok —
tükenirse tükenir, ikinci deneme maliyeti bir daha ödenmez.

**Reddedilen alternatif — tavanı tamamen kaldırmak:** tavansız şemalı çağrı
canlıda **1106 saniye** asılı ölçüldü (kaçak kod çözümü) ve httpx zaman aşımı
bunu **yakalamadı** — bağlantı ölü değildi, yalnızca çok yavaştı. Sigortasız
sadelik donan bir demo demek; tavan bu yüzden korundu, yalnız tekrarı atıldı.

`gozcu/gateway.py`, `gozcu/config.py`, `gozcu/agents/reporter.py`.

### Yükseltme kipleri

**Ölçüm:** aynı açık epizot **6 kez** yükseltildi → **18 saha çağrısı**,
**7 risk değerlendirmesi**, kopya dolu bir `actions[]` listesi ve pencere
başına 30–60 saniyelik gereksiz maliyet — model kendi geçmişinde 15 başarılı
çağrı dururken talimat "ÖNCE saha araçlarını çağır" dediği için tekrar
çağırdı.

**Yeni kural:** süpervizör epizot başına yükseltme sayısını tutar. **İlk
yükseltme** tam müdahale (risk değerlendirmesi + araç turu + duyuru).
**Sonraki yükseltmeler** "gelişme" kipine düşer: `assess_risk` yeniden
koşmaz (depodaki son değerlendirme okunur), talimat aynı aracı aynı
gerekçeyle tekrar çağırmayı yasaklar ve yalnız 1–2 cümlelik gelişme
bildirmesini ister; yeni bir ihtiyaç doğarsa yeni araç çağrısı yine mümkün.

**Reddedilen alternatif — döngü tarafında bastırma** (aynı epizot için
ikinci `yield`'i risk yükselmedikçe susturmak): reddedildi çünkü bu koşuda
ilk yükseltme 00:19'da (yakın-temas anında) geldi, çarpma (~00:35) ve
devrilme (~00:45) **sonraki** yükseltmelerde oldu, ve sentezleyicinin ön
riski koşu boyunca Orta/Yüksek bandında sabit kaldığı için "risk yükselince
yeniden seslen" kuralı hiç tetiklenmezdi — **kaza operatörden saklanmış
olurdu.** Karar bu yüzden davranış katmanında: seslenme sıklığı aynen kalır,
kesilen yalnız mükerrer müdahale ve mükerrer analiz.

`gozcu/agents/supervisor.py`.

### Ek not — ölçülecek borç

`notable_event` eşiği (epizodun ne zaman açılacağını belirleyen sinyal
tetiği) bu turda **dokunulmadı**. Aynı koşuda epizot 00:00'da, sakin sahnede
açılmıştı ve bu ayrı bir kök nedendi — an tavanının (`MAX_EPISODE_BEATS`)
12'den 48'e çıkarılması ve baş+son tutma kuralı bu erken açılmanın iki
zararını (an kaybı, 00:00 damgalı müdahale kartı) başka yoldan kapattı, ama
eşiğin kendisini sıkılaştırmadı. Eşik değişikliği ölçüm ister; kod
dondurmadan saatler önce ölçüsüz bir prompt ayarı yapılmadı.

### Doğrulama — aynı klipte (k04) önce/sonra ölçümü

Onarımlar aynı videoyla (`forklift-compilation--N9bG-sOU6LE-k04.mp4`, 98,8 s)
canlı olarak doğrulandı; konsolun kurduğu oturumun aynısı (Store + Gateway +
Supervisor). Ölçüm iki yeni arıza daha ortaya çıkardı ve ikisi de onarıldı.

| Ölçüt | Önce | Sonra |
|---|---|---|
| Başarısız saha çağrısı | 12/18 `zone_unresolved` | **0** |
| Açılan İSG kaydı | 0 (6 çağrı uydurma kimlikle reddedildi) | **1** (gerçek `episode_id`) |
| Saha çağrısı | 18 (aynı olaya 6 kez tekrar) | **4** (bir kez, hepsi başarılı) |
| Risk değerlendirmesi | 7 | **2** (ilk yükseltme + koşu sonu tazeleme) |
| `events[]` | 12 an, 00:00–00:19 — **kaza listede yok** | **48 an, 00:00–01:37** |
| `summary` | "Rapor katmanı boş yanıt döndürdü…" | gerçek olay anlatısı |
| `risk` | Kritik | Kritik |
| Şema bütçesi tekrarı | ~6 pencerede 20–50 s'lik ikinci deneme | **0** |
| Uydurma | "sentez hattı durdu" (yaşanmadı) | **yok** |

Süre 821 s'den 473–735 s bandına indi; bandın genişliği ağ geçidi
gecikmesinden (tek tek pencerelerde 135–142 s'lik model tarafı asılmalar),
yapısal kazanç ise sabit: bütçe tekrarı sıfır.

**Ölçümün bulduğu iki yeni arıza:**

1. **Bayat risk.** İki kipli yükseltme epizot başına tek değerlendirme
   bıraktı ve o değerlendirme İLK yükseltmenin anına (00:19, ramak kala)
   aitti; 01:39'da forklift devrilip yerde bir kişi varken teslim edilen
   `risk` hâlâ "Yüksek"ti. `_sweep_stale_risk` artık epizodun sonu son
   değerlendirmeden yeniyse bir kez daha biçiyor — `risk` "Kritik"e,
   `actions[]` 2'den 6'ya çıktı (`689fc3c`).
2. **Kendi notumuzun sızdırdığı isim.** Karantina arıza metnini kesti ama
   yerine koyduğumuz not "Sentez kademesi" diye başlıyordu; model bunu
   BÖLGE ADI sandı ve dört saha çağrısının, telsiz mesajının ve teslim
   edilen özetin içine soktu (JSON'da 14 kez). Aynı yalan sınıfı, bir
   seviye ötede. Beş model-yüzlü nottan iç katman adı silindi ve bir
   regresyon nöbetçisi testi eklendi (`900c4e7`); sonraki koşuda
   "sentez/kademe/katman" teslim çıktısında sıfır kez geçiyor.

---

## 26 Ağustos — an tavanı kazanın kendisini siliyordu

Yukarıdaki turun "Ek not — ölçülecek borç" bölümü `MAX_EPISODE_BEATS`'in
12'den 48'e çıkarılıp baş+son tutma kuralına geçildiğini, ama eşiğin
kendisinin ölçülmediğini kaydetmişti. Üçüncü bir canlı koşu (aynı forklift
klibi, 98,8 s, 10 pencere, pencere başına 6 an — 60 an üretildi) o kuralın
kendisini ölçtü: **teslim edilen liste tam 48 andı ve kesim sınırı
`beats[23]=39.7sn → beats[24]=60.0sn`'de duruyordu.** Pencere başına an
sayısı 0-3, 6-9 pencerelerinde 6'şar, **4 ve 5 numaralı pencerelerde
(40–60sn) sıfırdı** — forkliftin kamyona çarpıp devrildiği tam o aralık.
On iki an üretilip parası ödendi, sonra atıldı; parkta duran kamyonun on
iki anı "ilk" olduğu için korundu. Üç ayrı canlı koşuda aynı kesim
(39.7→60.0) birebir tekrarlandı.

**Kök neden pozisyonel kalmıştı.** Önceki kural yalnız-baştı (00:19'dan
sonrasını atardı); yerine konan baş+son kuralı ortayı attı. İkisi de HANGİ
anın tutulacağına an listede NEREDE durduğuna bakarak karar veriyordu, an
içerikte ne anlattığına değil — kazanın 40–60sn'ye denk gelmesi tümüyle
şanstı, bir sonraki klipte kaza baştan veya sondan da düşebilirdi.

**Onarım:** `_merge_beats` artık HİÇBİR anı atmıyor; kırpma dalı tamamen
kaldırıldı ve onunla birlikte `MAX_EPISODE_BEATS` sabiti silindi
(`gozcu/models.py`, `gozcu/agents/synthesizer.py`). Her an bir pencerenin
zaten ödenmiş VLM çağrısının çıktısı — atmanın ilkeli bir gerekçesi yok.
Büyümeyi artık dedup anahtarı (`round(ts,1), text`: aynı pencereyi yeniden
kaynaştırmak listeye hiçbir şey eklemez) ve epizodun kapsadığı FARKLI
yorumlanan pencere sayısı × pencere başına an tavanı (`MAX_BEATS=6`,
`interpreter.py`'nin `beats` şeması) sınırlıyor.

**Ders:** bir tavanı "geçici olarak daha cömert yap" ölçüme dayanmıyorsa
aynı hatayı büyütülmüş biçimde geri getirir. 12→48 iyileşme gibi göründü
çünkü kazayı bu sefer sakladı; kuralın kendisi hâlâ pozisyoneldi ve bir
sonraki koşuda aynı yeri tekrar buldu.

`gozcu/models.py`, `gozcu/agents/synthesizer.py`,
`tests/test_synthesizer.py`.
