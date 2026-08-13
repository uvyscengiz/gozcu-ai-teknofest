# Evaluation Criteria Mapping

How the competition's scoring criteria map to our design choices.

## Functionality & scenario coverage (35%)

| Criterion | Our solution |
|---|---|
| End-to-end scenario implementation | 6-stage pipeline (video → perception → VLM → timeline → risk → JSON) |
| Mock functions used as agent tools | LangGraph tool definitions (8 tools) |
| System stability | Error handling, fallback, Docker containerization |

## Technical implementation & architecture (35%)

| Criterion | Our solution |
|---|---|
| Agentic components (agent, tools, memory, prompt engineering) | LangGraph + LangMem + Pydantic + system prompts |
| Dynamic tool selection | ReAct pattern, conditional edges |
| Context management | Working memory, scene-context propagation |
| Multi-step decision chains | LangGraph graph-based workflow |
| Error handling | Fallback nodes, retry logic |
| Code quality, modularity | Modular Python package, type hints, Pydantic |
| Mock system integration | Tool functions as agent tools |

## Autonomy & intelligence (20%)

| Criterion | Our solution |
|---|---|
| Understanding user intent | LLM-based intent parsing |
| Reasoning | ReAct pattern, chain-of-thought prompting |
| Taking initiative | Agent's dynamic tool selection |
| Response to unexpected situations | Error handling, context switching |
| Natural dialogue flow | Turkish LLM (Turkish-LLM-14B) |

## Innovation & creativity (10%)

| Criterion | Our solution |
|---|---|
| Additional scenarios | Audio analysis, multi-video sync, RTSP streaming |
| Beyond-expectation features | Web dashboard, PDF report, configuration panel |
| Original architecture | YOLO-VLM hybrid pattern + agentic orchestration |
| Documentation quality | Detailed README, architecture diagram, setup guide |

Cross-reference: [00-overview/requirements.md](../00-overview/requirements.md) for the raw requirements this scoring maps against, and [05-decisions/decision-log.md](../05-decisions/decision-log.md) for where the professor pushed back on the original "differentiation" framing (see the "competitive positioning" entry).
