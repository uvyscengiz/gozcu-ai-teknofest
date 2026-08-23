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
