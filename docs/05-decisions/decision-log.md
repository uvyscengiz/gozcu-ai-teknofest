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
