## Summary of Diagnosis

The measured pattern — full localization capacity at very low confidence thresholds (60 candidates at conf=0.01, only 5 above 0.20), combined with worsening confidence at higher `imgsz` — is consistent with two well-documented, independent phenomena rather than one bug: (1) COCO-trained detectors are calibrated on sparse, well-lit, unoccluded pedestrians and systematically under-score occluded/small/low-contrast crowd instances, and (2) upsampling low-detail footage past its native optical resolution does not add real information and pushes small objects into a scale regime the network was not trained to score confidently. Below is an artifact-by-artifact breakdown answering each question, with licence, measured deltas, and integration cost against an Ultralytics 8.4/MPS pipeline.[^1][^2][^3][^4]

## 1. CrowdHuman/Dense-Pedestrian Pretrained Detector Weights

| Artifact | Weight URL | Licence | Input res | Reported metric | Box type | Ultralytics integration cost |
|---|---|---|---|---|---|---|
| YOLOv5m-CrowdHuman (person+head, 2 classes) | github.com/SibiAkkash/yolov5-crowdhuman, github.com/MahenderAutonomo/yolov5-crowdhuman (same `crowdhuman_yolov5m.pt`) [^5][^6] | Repo is unlicensed/MIT-adjacent (check each fork; underlying YOLOv5 is AGPL-3.0 via Ultralytics) | 640 (trained on CrowdHuman default) | No MR⁻² reported in repo README; community benchmark only | Full-body person + separate head class | Medium — YOLOv5 `.pt` loads directly via `torch.hub` or legacy `ultralytics/yolov5`, but YOLO11 pipeline (`ultralytics` 8.x) needs the checkpoint re-wrapped since v5 and v8+/v11 use different model classes. Practical path: run as a standalone secondary detector, not merged into the v11 checkpoint. |
| CrowdHuman visible+full body (2-class) YOLOv5m | github.com/Whiffe/yolov5-visible-and-full-person-crowdhuman → `crowdhuman_vbody_yolov5m.pt` [^7] | Same YOLOv5/AGPL lineage, no separate stated licence | 640 | Not reported | Distinguishes visible-body vs full-body class explicitly (class 1 = visible person, class 0 = head) — directly useful for your occlusion problem since "visible body" boxes are trained to match what's actually seen, not the hallucinated full extent | Medium, same caveat as above |
| YOLOv8n-CrowdHuman (yakhyo/yolov8-crowdhuman) [^8][^9] | GitHub Releases page, `.pt` and `.onnx` | Repo licence unspecified — check before commercial use | Trained at standard YOLOv8 default (640) | Not stated in indexed pages; check repo for val results | Person only (full-body, single class) | Low — YOLOv8 checkpoints load natively in `ultralytics` package (v8/v11 share the same loader family), so this is your easiest drop-in swap for the COCO YOLO11m person class. |
| YOLOv8 Head Detection (Owen718/Head-Detection-Yolov8) [^10] | Google Drive link in repo, CrowdHuman-derived head labels reformatted to YOLO format | Repo does not state a licence — treat as research-only until confirmed | Not specified, YOLOv8 default | Not reported in indexed content | Head-only boxes | Low — same YOLOv8/`ultralytics` load path |
| Darknet YOLOv4-CrowdHuman (jkjung-avt) [^11] | Requires self-training via provided scripts + Colab notebook; no ready-made `.weights` hosted (must train yourself, ~hours on Colab) | MIT (repo) / CrowdHuman data terms | 416 or 608 (config-selectable) | Not reported centrally | Person + head, Darknet format | High — needs conversion to PyTorch/Ultralytics format; not a direct drop-in |
| darknet-crowdhuman (alaksana96) | **Dead link** — author explicitly states weights are lost [^12] | N/A | N/A | N/A | N/A | Not usable — flagging so you don't waste time chasing it |

**Important caveat on MR⁻²/AP numbers**: none of the community CrowdHuman-YOLO repos in the search results publish a rigorous MR⁻²/AP table comparable to academic detectors. The academic benchmark numbers that *do* exist are from two-stage/anchor-based research detectors, not the YOLO ports above:

- Anchor-Pair Network (APN): MR⁻² 55.43% on CrowdHuman val, an 11.59% relative improvement over its own baseline.[^13][^1]
- Adaptive-NMS + Faster R-CNN/RFB: 49.73% MR⁻² on CrowdHuman, 10.8% on CityPersons.[^2]

This is a meaningful gap in your evidence base: **the publicly downloadable YOLO-CrowdHuman checkpoints are community forks without rigorous published MR⁻²/AP tables**, whereas the detectors with rigorous published metrics (APN, Adaptive-NMS Faster R-CNN) do not ship convenient Ultralytics-loadable `.pt` files. Practically, your best move is to treat the YOLOv8n/YOLOv8-crowdhuman checkpoint  as a low-cost swap-in test (native `ultralytics` loader, full-body, single class) and empirically re-run your same 116-frame protocol against it — you already have the harness.[^8][^9]

## 2. Head Detection as an Occlusion-Robust Alternative

Head-only detection is a **recognized standard technique** for dense/occluded crowd counting, not a workaround — the CVPR 2021 CroHD benchmark and its HeadHunter detector were built specifically because heads survive occlusion that eliminates torso/leg visibility.[^14][^15]

| Artifact | Weight/source | Licence | Input res | Metric | Notes |
|---|---|---|---|---|---|
| HeadHunter (ResNet-50 + FPN, two-stage) [^14][^16][^17] | github.com/Sentient07/HeadHunter — code + `pretrained_model` checkpoint loading supported, but public link availability for pretrained weights should be verified in-repo | Academic/research use per SCUT-HEAD terms | Trained at 1000×600 (median training-set resolution) [^14] | Purpose-built for small-head detection in crowded scenes; strong MOTA/IDF1 on CroHD tracking benchmark [^18] | PyTorch native, but NOT Ultralytics-format — requires standalone integration (Faster R-CNN/FPN style, not YOLO), so budget real integration time |
| SCUT-HEAD Dataset + reference models [^19][^20][^21] | github.com/HCIILAB/SCUT-HEAD-Dataset-Release (Google/Baidu Drive), Roboflow universe hosts for retrained YOLO versions | "Free to academic community for research purpose usage only" — **not commercially licensed** [^19] | Varies by trainer | 4,405 images / 111,251 heads labeled including occluded portions | If Burs Vadisi is commercial, this licence blocks direct redistribution of SCUT-HEAD-trained weights without checking terms |
| YOLOv5m-CrowdHuman head class [^5][^6][^7] | Same repos as Q1, use `--heads` flag | Same caveats as Q1 | 640 | Not separately reported for head-only mode | Cheapest integration since it's the same weight file you'd already be testing for person detection — just switch class filter |
| SHWD / Safety-Helmet-Wearing-Dataset head+helmet [^22] | BaiduDrive/GoogleDrive, MXNet/GluonCV format | Not explicitly stated | Configurable "short side" | mAP 88.5 (darknet backbone) on helmet+head task, not directly CrowdHuman-comparable | Requires MXNet→PyTorch conversion; overkill unless helmet detection is also relevant to your factory setting |

**Documented failure modes of head-counting** relevant to your factory floor:
- Small head size at range/low resolution reduces detectability similarly to person detection — HeadHunter was explicitly trained at a resolution chosen to keep heads legible, implying head detection does not escape the resolution-dependent detection floor, it just shifts the failure point later (heads are smaller targets than full bodies, so they still shrink out at extreme range/compression).[^23][^14]
- Head-to-person count conversion introduces bias if people wear headgear, look away, or heads are cropped by low camera angle — none of your search results quantify this bias for factory CCTV specifically, so treat person-per-head ≈ 1 as an approximation to validate empirically on your 116-frame set.
- Identity/tracking failure modes (ID switches, fragmentation under dense occlusion) are documented in the CroHD tracking benchmarks even for HeadHunter-based trackers.[^18]

## 3. Dense-Crowd NMS: What the Evidence Actually Shows

This is the area with the clearest quantitative, non-marketing evidence in your question set.

**Soft-NMS and Adaptive-NMS — measured recall gains, not just latency changes:**
- Adaptive-NMS on CityPersons/CrowdHuman achieves 10.8% MR⁻² (CityPersons) and 49.73% MR⁻² (CrowdHuman), beating standard greedy NMS baselines, with the paper explicitly targeting the crowd-suppression problem you're describing.[^2]
- The "One Proposal, Multiple Predictions" CVPR 2020 paper reports a stark before/after: standard NMS+FPN recall on *crowded* subsets falls to 54.4% vs recall of 63.7% on sparse subsets at the same confidence — a direct measurement of the crowd-specific recall penalty from IoU-based NMS — and their method raises crowd recall from 54.4% to 63.3% (+8.9 points) while leaving sparse-scene recall roughly unchanged.[^24]
- PS-RCNN reports +4.49% recall and +2.92% AP over baseline on CrowdHuman by explicitly handling secondary (occluded) instances, and separately notes NMS@0.5 imposes a hard recall ceiling around 90.9% even given perfect ground-truth boxes fed into it — meaning NMS itself, not detection quality, caps achievable recall in dense scenes.[^25]
- Note one caveat directly from the data: in the "One Proposal" paper, Soft-NMS showed *zero* improvement over standard NMS in one high-confidence-threshold (0.8) test regime, because at that threshold NMS and Soft-NMS collapse to nearly the same behavior — the recall benefit of Soft-NMS is threshold-dependent and not guaranteed at all operating points. This is a useful "commonly repeated but not universally true" flag: Soft-NMS is not a free lunch at every confidence setting.[^24]

**NMS-free heads (YOLOv10, YOLO26) — evidence is mixed and largely COCO-general, not crowd-specific:**
- YOLOv10's core innovation is "consistent dual assignments" enabling NMS-free inference, evaluated primarily for latency/parameter efficiency on COCO, not on CrowdHuman-style dense-occlusion benchmarks.[^26][^27]
- The YOLOv10 paper itself reports that for the smaller variants (N and S), one-to-many training *with* NMS still outperforms NMS-free training by 1.0% and 0.5% AP respectively — i.e., even on general COCO, NMS-free is not unambiguously better; it trades a small accuracy loss for latency/determinism gains.[^27]
- No result in your search set demonstrates NMS-free heads measurably improving crowd-specific recall versus Soft-NMS/Adaptive-NMS on CrowdHuman. **Flag: the "NMS-free improves dense-crowd recall" claim is not supported by measured crowd-specific evidence in the available literature — its documented benefit is latency and deployment simplicity, not crowd recall**.[^26][^27]
- YOLO26's NMS-free framework does claim better small-object handling (maintaining precision "for objects occupying less than 1% of image area") but this is a general small-object claim, not a crowd-occlusion-specific benchmark.[^28]

**Integration cost**: Ultralytics natively supports adjustable `iou` (NMS threshold) and `agnostic_nms` flags in `model.predict()`, so testing a lower IoU threshold (e.g., 0.3–0.4 instead of default 0.7) costs zero engineering effort — try this before any architecture change. True Soft-NMS/Adaptive-NMS requires patching the postprocessing step (not exposed as a built-in flag in standard Ultralytics), which is a moderate custom-code effort (a few hundred lines, borrowing from the Adaptive-NMS/Soft-NMS reference implementations cited above).

## 4. Low-Confidence + Temporal Persistence Filtering

The established name for this general strategy in the tracking literature is **track-supported low-confidence recovery**, formalized by ByteTrack's two-stage association:[^29][^30][^31]

- Stage 1 matches high-confidence detections (above `track_high_thresh`, typically 0.5–0.7) to existing tracks via Kalman-filter-predicted IoU.[^32][^29]
- Stage 2 matches remaining low-confidence detections (below `track_high_thresh` but above `track_low_thresh`, commonly ~0.1) only to tracks that are *already established and unmatched in Stage 1* — it does not use low-confidence detections to *start* new tracks, deliberately preventing "ghost tracks" from noise.[^33][^32]
- This is a documented, published mechanism (ByteTrack, ECCV 2022) already implemented in Ultralytics' built-in tracker (`model.track(tracker='bytetrack.yaml')`), and the emergentmind/deepwiki summaries confirm this two-stage design is the current standard reference implementation, not a novel research idea you'd need to build from scratch.[^30][^34]

**Direct answer to your framing question**: ByteTrack already *is* the "accept a weak detection only if it persists/associates" technique you're describing — it is exactly a temporal-persistence filter for low-confidence boxes, gated by prior track existence rather than a fixed N-frame counter. Running your detector at conf=0.05–0.10 and feeding all boxes into ByteTrack (rather than pre-filtering at 0.20) should let genuine crowd members that flicker below threshold get recovered via Stage 2 association, provided they were seen at higher confidence in at least one prior frame to seed the track. The risk specific to your case: with 22 overlapping people and heavy occlusion, initial track seeding (Stage 3, high-confidence-only) may itself fail for people who are *never* above 0.20 in any frame — ByteTrack does not solve missing initial detections, only fragmentation of already-detected tracks.[^31][^35][^30]

**Refinements found in the literature** (not required, but relevant): "Adaptive Confidence Threshold for ByteTrack" (2023) explores dynamically adjusting the confidence split rather than using ByteTrack's fixed threshold, and a 2025 Nature Scientific Reports paper proposes replacing plain IoU in Stage 2 with EIoU to improve occlusion-heavy matching precision — both are extensions you could adopt if default ByteTrack under-recovers on your footage, but they are incremental refinements, not prerequisites.[^36][^37]

**Integration cost**: Very low. Ultralytics has built-in ByteTrack support; you would only need to lower your detector's `conf` parameter passed into `model.track()` (e.g., conf=0.05–0.1) and tune `track_low_thresh`/`track_high_thresh` in the tracker YAML — no new code required beyond parameter changes.

## 5. Confidence Calibration via Preprocessing (CLAHE/Gamma) — Measured, Not Folklore, But Effect Size Is Modest and Context-Dependent

This is a real, measured phenomenon with multiple independent quantitative studies, though the magnitude varies and is not universally positive:

| Study/context | Technique | Measured effect | Citation |
|---|---|---|---|
| Pothole detection, YOLOv11, driving speeds | Adaptive Gamma Correction + CLAHE | Recall increase ≈0.10 across all tested speeds vs baseline | [^38] |
| Underwater object detection, YOLOv8 | CLAHE alone | Confidence improved 4.7%, particularly for small/low-contrast targets; PSNR/SSIM gains 15%/9% | [^39] |
| Underwater, opaque vs. translucent objects | CLAHE | +8% avg confidence for opaque objects, but **−13% confidence and −44% detection count for translucent objects** — a documented failure mode where CLAHE actively hurts certain object classes | [^40] |
| Tunnel low-light helmet detection, YOLOX | CLAHE alone | +1.13% mAP over baseline; combined with other enhancements up to +4.23% mAP | [^41] |
| Night driving, YOLOv8 + OpenCV | Gamma + CLAHE + bilateral filtering | 97–98% mAP maintained, 12–14% processing time reduction (efficiency claim, not pure accuracy gain) | [^42] |
| General plant/stomata micrograph pipeline | Gamma + CLAHE combined | Precision 0.93→0.94, recall 0.91→0.92, mAP@50 0.95→0.96 — small but consistent gains | [^43] |

**Synthesis**: CLAHE/gamma preprocessing produces measured, real but modest gains (typically 1–5 percentage points in mAP/confidence, occasionally up to ~10 points in recall for specific low-light cases) — this is **not folklore**, it is repeatedly measured across independent studies. However, effect size is task- and content-dependent, and at least one study shows CLAHE can *degrade* detection for specific visual object types (translucent/reflective materials)  — relevant to your "blown-out window" condition, since CLAHE applied to an already-blown-out bright region can behave unpredictably. **Recommendation**: test CLAHE as a cheap, low-risk experiment on your existing 116-frame set (a few lines of OpenCV before feeding frames to YOLO), since it requires no retraining and the published effect sizes suggest a plausible few-point confidence gain, but do not expect it to single-handedly close a 15x gap in candidate count.[^38][^39][^40][^41][^43]

**Integration cost**: Very low — `cv2.createCLAHE()` or a simple gamma LUT applied as a preprocessing step before `model.predict()`; no pipeline architecture change.

## 6. Upscaling Above Native Detail: Documented, Expected Behavior

Your finding is consistent with explicit guidance from the Ultralytics maintainers and community, not an anomaly:

- Ultralytics' own GitHub issue guidance states directly: "The image resolution isn't important. The object size after getting resized to `imgsz` is what's important. You should choose an `imgsz` that doesn't make your objects too small after being resized". This implies `imgsz` should track true optical detail (how large/legible the object *actually* is), not the file's nominal pixel dimensions — upscaling a 960×720 frame's already-blurry, low-detail person to appear "larger" at imgsz=896 does not add resolvable detail, it just stretches noise and blur across more pixels, which is consistent with your confidence collapse (0.647→0.159).[^3]
- A 2026 controlled study of YOLOv11 variants found a resolution-dependent "detection floor" — below a certain object-area-to-image ratio, detection collapses regardless of model capacity, and increasing input resolution only helps up to the point where it reflects genuine additional optical information; past that, larger models detect somewhat smaller objects than lighter ones, but all model sizes hit the same floor eventually.[^23]
- Community guidance (Ultralytics support forum) reiterates `imgsz` as the primary lever for small-object detection, but this guidance implicitly assumes the *source* has enough true detail to reveal at higher `imgsz` — it does not claim that upscaling a fundamentally low-detail source will help, and the same thread recommends **tiling/cropping to preserve native detail per-region** rather than blanket upscaling as the actual effective technique when detail is limited.[^4]

**Standard guidance synthesized**: choose `imgsz` based on the *smallest legible object's* true optical footprint in native pixels, not the source frame's nominal resolution — and if people occupy few actual detail-bearing pixels (e.g., in the dim, blown-out, compressed regions of your footage), the correct move is not resizing but **tiling** the 960×720 frame into overlapping crops run at native or near-native `imgsz`, preserving true detail per-person rather than diluting it via interpolation. This directly explains why 640 outperformed 896 for you: at 640 the objects retained more of their "real" relative scale versus the trained distribution; at 896, interpolation inflated apparent size without adding information, moving objects outside the confidence-calibrated scale range the model learned on COCO.[^4][^23]

## Prioritized Action List for Your Pipeline

1. Swap in the YOLOv8-CrowdHuman checkpoint  as a same-format test against your existing 116-frame harness — lowest integration cost, direct comparability, most likely single largest lift given COCO's sparse-person bias.[^9][^8][^1]
2. Feed detections at conf≈0.05–0.10 directly into Ultralytics' built-in ByteTrack rather than pre-filtering at 0.20 — this is the standard, already-implemented mechanism for exactly your stated goal (temporal persistence recovering weak detections).[^30][^31]
3. Lower NMS IoU threshold (e.g., 0.3–0.4) via the built-in `iou=` parameter — free experiment, directly targets your dense-crowd suppression issue, with academic evidence that IoU-based NMS imposes a hard recall ceiling in crowds.[^25][^24]
4. Test CLAHE/gamma preprocessing as a cheap addition — expect a modest, not transformative, gain (low single digits to ~10 points depending on the metric), and watch specifically for adverse interaction with your blown-out window region.[^40][^38]
5. Replace blanket upscaling with tiled/cropped inference at native or near-native `imgsz` per tile, rather than resizing the whole frame upward — directly addresses your imgsz finding with the closest thing to standard guidance available.[^23][^4]
6. Treat head detection (YOLOv8 head models, YOLOv5-CrowdHuman head class) as a fallback specifically for the heaviest-occlusion frames, with awareness that SCUT-HEAD-derived weights carry academic-only licence terms if Burs Vadisi's use case is commercial.[^10][^19]
7. Flag explicitly to any stakeholders: NMS-free architectures (YOLOv10/YOLO26) are not evidenced as a crowd-recall fix in the available literature — their documented benefit is latency/simplicity, and even the YOLOv10 paper shows a slight AP cost for small models — so this should not be prioritized as a crowd-density solution.[^27][^28]

---

## References

1. [CrowdHuman: A Benchmark for Detecting Human in a Crowd](https://www.semanticscholar.org/paper/CrowdHuman:-A-Benchmark-for-Detecting-Human-in-a-Shao-Zhao/03a65d274dc6caea94f6ab344e0b4969575327e3) - The cross-dataset generalization results of CrowdHuman dataset demonstrate state-of-the-art performa...

2. [Adaptive NMS: Refining Pedestrian Detection in a Crowd - ar5iv](https://ar5iv.labs.arxiv.org/html/1904.03629) - Pedestrian detection in a crowd is a very challenging issue. This paper addresses this problem by a ...

3. [What value should I use for --imgsz when my dataset ...](https://github.com/ultralytics/ultralytics/issues/20258) - You should use what's suitable for your object size. The image resolution isn't important. The objec...

4. [Improve detection of small object in an image - Support](https://community.ultralytics.com/t/improve-detection-of-small-object-in-an-image/1748) - You can try increasing imgsz . That's really the only parameter that affects small object detection.

5. [GitHub - MahenderAutonomo/yolov5-crowdhuman: Head and Person detection using yolov5. Detection from crowd.](https://github.com/MahenderAutonomo/yolov5-crowdhuman) - Head and Person detection using yolov5. Detection from crowd. - MahenderAutonomo/yolov5-crowdhuman

6. [GitHub - SibiAkkash/yolov5-crowdhuman: YOLOv5, CrowdHuman, Trained model](https://github.com/SibiAkkash/yolov5-crowdhuman) - YOLOv5, CrowdHuman, Trained model. Contribute to SibiAkkash/yolov5-crowdhuman development by creatin...

7. [GitHub - Whiffe/yolov5-visible-and-full-person-crowdhuman](https://github.com/Whiffe/yolov5-visible-and-full-person-crowdhuman) - Contribute to Whiffe/yolov5-visible-and-full-person-crowdhuman development by creating an account on...

8. [Getting Started | yakhyo/yolov8-crowdhuman | DeepWiki](https://deepwiki.com/yakhyo/yolov8-crowdhuman/1.1-getting-started) - This page provides a step-by-step guide for setting up the `yolov8-crowdhuman` environment. It cover...

9. [YOLOv8 trained on CrowdHuman dataset and supports ...](https://github.com/yakhyo/yolov8-crowdhuman) - Human/person detection using YOLOv8 trained on CrowdHuman dataset with ONNX Runtime inference. Featu...

10. [GitHub - Owen718/Head-Detection-Yolov8: This repo provides a YOLOv8 model, finely trained for detecting human heads in complex crowd scenes, with the CrowdHuman dataset serving as training data. To boost accessibility and compatibility, I've reconstructed the labels in the CrowdHuman dataset, refining its annotations to perfectly match the YOLO format.](https://github.com/Owen718/Head-Detection-Yolov8) - This repo provides a YOLOv8 model, finely trained for detecting human heads in complex crowd scenes,...

11. [GitHub - jkjung-avt/yolov4_crowdhuman: A tutorial on training a DarkNet YOLOv4 model for the CrowdHuman dataset](https://github.com/jkjung-avt/yolov4_crowdhuman) - A tutorial on training a DarkNet YOLOv4 model for the CrowdHuman dataset - jkjung-avt/yolov4_crowdhu...

12. [GitHub - alaksana96/darknet-crowdhuman: YOLO Detector for the CrowdHuman Dataset. Detects people and heads. Contains training instructions on how to convert between CrowdHuman and Darknet annotations](https://github.com/alaksana96/darknet-crowdhuman) - YOLO Detector for the CrowdHuman Dataset. Detects people and heads. Contains training instructions o...

13. [Crowded Human Detection via an Anchor-pair Network](https://openaccess.thecvf.com/content_WACV_2020/papers/Zhu__Crowded_Human_Detection_via_an_Anchor-pair_Network_WACV_2020_paper.pdf)

14. [[PDF] Tracking Pedestrian Heads in Dense Crowd - CVF Open Access](https://openaccess.thecvf.com/content/CVPR2021/papers/Sundararaman_Tracking_Pedestrian_Heads_in_Dense_Crowd_CVPR_2021_paper.pdf)

15. [Tracking Pedestrian Heads in Dense Crowd - CVF Open Access](https://openaccess.thecvf.com/content/CVPR2021/html/Sundararaman_Tracking_Pedestrian_Heads_in_Dense_Crowd_CVPR_2021_paper.html) - by R Sundararaman · 2021 · Cited by 150 — Moreover, we also propose a new head detector, HeadHunter,...

16. [Sentient07/HeadHunter: Code for the head detector ...](https://github.com/Sentient07/HeadHunter) - Code for the head detector (HeadHunter) The head_detection module can be installed using pip in orde...

17. [HeadHunter/README.md at master · Sentient07/HeadHunter](https://github.com/Sentient07/HeadHunter/blob/master/README.md) - Code for the head detector (HeadHunter) proposed in our CVPR 2021 paper Tracking Pedestrian Heads in...

18. [Tracking Pedestrian Heads in Dense crowd](https://openaccess.thecvf.com/content/CVPR2021/supplemental/Sundararaman_Tracking_Pedestrian_Heads_CVPR_2021_supplemental.pdf)

19. [HCIILAB/SCUT-HEAD-Dataset-Release](https://github.com/HCIILAB/SCUT-HEAD-Dataset-Release) - SCUT HEAD is a large-scale head detection dataset, including 4405 images labeld with 111251 heads. -...

20. [SCUT_HEAD_B Object Detection Dataset and Pre-Trained Model by SCUTHEADB](https://universe.roboflow.com/scutheadb/scut_head_b-kmv7x) - 2390 open source SCUTHEADB images plus a pre-trained SCUT_HEAD_B model and API. Created by SCUTHEADB

21. [SCUT-HEAD Part A Object Detection Dataset by Viet Hoang Head](https://universe.roboflow.com/viet-hoang-head/scut-head-part-a) - 2000 open source heads images. SCUT-HEAD Part A dataset by Viet Hoang Head

22. [Safety helmet wearing detect dataset, with pretrained model](https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset) - Safety helmet wearing detect dataset, with pretrained model - njvisionpower/Safety-Helmet-Wearing-Da...

23. [Paper Title (use style: paper title) - ijsdr.org](https://www.ijsdr.org/papers/IJSDR2602003.pdf)

24. [[PDF] Detection in Crowded Scenes: One Proposal, Multiple Predictions](https://openaccess.thecvf.com/content_CVPR_2020/papers/Chu_Detection_in_Crowded_Scenes_One_Proposal_Multiple_Predictions_CVPR_2020_paper.pdf)

25. [PS-RCNN: DETECTING SECONDARY HUMAN INSTANCES IN A CROWD VIA PRIMARY](https://arxiv.org/pdf/2003.07080.pdf)

26. [YOLOv10: Real-Time End-to-End Object Detection](https://arxiv.org/abs/2405.14458) - Over the past years, YOLOs have emerged as the predominant paradigm in the field of real-time object...

27. [YOLOv10: Real-Time End-to-End Object Detection - arXiv.org](https://arxiv.org/html/2405.14458?_immersive_translate_auto_translate=1)

28. [YOLO26: An Analysis of NMS-Free End to End Framework ...](https://arxiv.org/html/2601.12882v1)

29. [ByteTrack — Multi-Object Tracking Algorithm | Trackers](https://trackers.roboflow.com/develop/trackers/bytetrack/) - ByteTrack improves multi-object tracking by associating every detection box — including low-confiden...

30. [Core Algorithm | FoundationVision/ByteTrack | DeepWiki](https://deepwiki.com/FoundationVision/ByteTrack/3-core-algorithm) - This document provides an overview of ByteTrack's core multi-object tracking algorithm and its key a...

31. [An Introduction to BYTETrack: Multi-Object Tracking by ...](https://datature.io/blog/introduction-to-bytetrack-multi-object-tracking-by-associating-every-detection-box) - In this article, we explore BYTETrack, a simple MOT Tracker with SOTA performance and highly adaptab...

32. [ByteTrack Tracker | chen-yuzhi/YOLO11-AU-IR | DeepWiki](https://deepwiki.com/chen-yuzhi/YOLO11-AU-IR/8.2-bytetrack-tracker) - The ByteTrack tracker is a high-performance multi-object tracking (MOT) algorithm implemented in the...

33. [An Improved Association Pipeline for Multi-Person Tracking](https://openaccess.thecvf.com/content/CVPR2023W/E2EAD/papers/Stadler_An_Improved_Association_Pipeline_for_Multi-Person_Tracking_CVPRW_2023_paper.pdf)

34. [ByteTrack: Efficient Object Tracking](https://www.emergentmind.com/topics/bytetrack) - Any unmatched tracklets from the first phase are then processed against the low-confidence detection...

35. [ByteTrack - Multi-Object Tracking Project](https://www.cs.carleton.edu/cs_comps_archive/2526/object_tracking_comps_2026/dist/bytetrack.html)

36. [Adaptive Confidence Threshold for ByteTrack in Multi- ...](https://arxiv.org/html/2312.01650v1) - It extends the SORT algorithm [17] by adding a second data association for tracks with lower confide...

37. [A two stage multi object tracking algorithm with transformer and attention mechanism](https://www.nature.com/articles/s41598-025-16389-4) - In the field of engineering safety, multi-object tracking encounters difficulties in effectively con

38. [Adaptive Gamma Correction and CLAHE for Low Light ...](https://scholar.unhas.ac.id/en/publications/adaptive-gamma-correction-and-clahe-for-low-light-conditions-on-p/) - The results showed a significant improvement in detection performance with an average recall increas...

39. [[PDF] An AI-Driven Real-Time Vision-Based System for Underwater Object ...](https://bspublications.net/9789347311062/bsp.sacad2025.60.pdf)

40. [International Scientific Conference Engineering for Rural ...](https://www.iitf.lbtu.lv/conference/proceedings2025/Papers/TF071.pdf)

41. [improved YOLOX approach for low-light and small object ...](https://academic.oup.com/jcde/article/10/3/1158/7177527) - Abstract. Tunnel construction sites pose a significant safety risk to workers due to the low-light c...

42. [Night-time Video/Image Enhancement and Object Detection Using YOLOv8and OpenCV](https://zenodo.org/records/19683508) - ABSTRACT This work proposes a computationally efficient pipeline to perform real-time nighttime obje...

43. [Improved Accuracy of Stomata Micrograph Classification ...](https://www.scitepress.org/Papers/2025/142751/142751.pdf)

