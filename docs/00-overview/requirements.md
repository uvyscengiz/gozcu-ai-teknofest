# Requirements

Source: team technical research document, competition şartname (spec) summary.

## Core requirements

| Requirement | Detail | Criticality |
|---|---|---|
| Video analysis | Analyze video content in context of scene coherence, temporal relationships, and event flow | High |
| Event detection | Identify event type, importance, and likely impact | High |
| Temporal awareness | Distinguish onset, development, and outcome phases of an event | High |
| Turkish natural language generation | Clear, understandable, context-appropriate Turkish summaries and recommendations | High |
| Action recommendation | Risk assessment + actionable operator recommendations | High |
| Structured output | JSON format, machine-processable | Mandatory |
| Local/offline operation | No external API, cloud, or closed-service dependency | Mandatory |
| vLLM serving | vLLM or comparable high-performance local serving | Mandatory |
| Open source | All components open source, reproducible | Mandatory |
| Agentic architecture | Dynamic, model-driven decision mechanisms — not static rule-based | Mandatory |

## Mock output format (illustrative)

```json
{
  "summary": "Forklift accident and injury risk observed in the video.",
  "events": [
    {"time": "00:15", "event": "Forklift tipped over"},
    {"time": "00:20", "event": "Person motionless on ground"}
  ],
  "risk": "High",
  "actions": [
    "Call medical team",
    "Secure the area"
  ]
}
```

See [02-architecture/system-design.md](../02-architecture/system-design.md#structured-output-design) for the full Pydantic schema and vLLM guided-decoding wiring.
