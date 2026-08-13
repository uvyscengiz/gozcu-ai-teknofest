# KPIs & Metrics

The competition spec asks participants to define their own metrics. Proposed metrics below.

## Detection metrics

| Metric | Definition | Target |
|---|---|---|
| Event detection precision | Correctly detected events / total detections | > 0.80 |
| Event recall | Correctly detected events / actual events | > 0.75 |
| Critical-event capture rate | Rate at which critical events are detected | > 0.90 |
| Timestamp error | Detected time − actual time | < 3 seconds |
| False positive rate | Rate of false alarms | < 0.15 |

## Quality metrics

| Metric | Definition | Measurement method |
|---|---|---|
| Summary quality | Clarity and accuracy of the Turkish summary | Human evaluation (1–5) |
| Action recommendation accuracy | Feasibility and consistency of recommendations | Human evaluation (1–5) |
| Risk assessment accuracy | Fit between assessed risk level and ground truth | Ground-truth comparison |

## Performance metrics

| Metric | Definition | Target |
|---|---|---|
| Video processing time | Total processing time / video duration | < 3x real-time |
| VLM inference time | VLM analysis time per scene | < 5 seconds |
| LLM inference time | Structured-output generation time | < 3 seconds |
| Memory usage | Peak VRAM usage | < 24GB (single GPU) |
| GPU utilization | GPU compute utilization | > 60% |
