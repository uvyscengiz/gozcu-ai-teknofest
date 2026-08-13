# Gözcü AI — TEKNOFEST Docs Vault

Unified knowledge base for the TEKNOFEST Yapay Zeka Dil Ajanları Yarışması (3rd scenario) project: a fully local/offline agentic AI system that watches video (factory floor, CCTV, drone footage), understands events over time, and produces Turkish natural-language summaries, risk assessments, and operator actions.

Built by merging: the team's technical research document and the guidance call with our advising PhD professor (2026-08-13).

## How this vault is organized

| Folder | Contents |
|---|---|
| [00-overview](00-overview/) | What the project is, competition requirements, evaluation criteria |
| [01-research](01-research/) | Prior art: industry examples, GitHub reference projects |
| [02-architecture](02-architecture/) | Tech stack, model strategy, system + pipeline design, structured output, local serving |
| [03-planning](03-planning/) | Roadmap, hardware requirements, KPIs/metrics |
| [04-mentor-guidance](04-mentor-guidance/) | Professor call: summary + raw transcript |
| [05-decisions](05-decisions/) | Consolidated decision log and open action items |
| [06-references](06-references/) | All external sources/links in one place |

## Start here

- New to the project? Read [00-overview/project-overview.md](00-overview/project-overview.md).
- Want the current plan of record? Read [05-decisions/decision-log.md](05-decisions/decision-log.md) — it reconciles the research doc's original plan with the professor's corrections.
- Need to know what to do next? Read [05-decisions/action-items.md](05-decisions/action-items.md).

## Key facts (as of 2026-08-13)

- **Competition category:** 3rd category — video-in, report-out. Other teams in categories 1 (internal-doc/text AI) and 2 (finance) are *not* direct competitors on approach, contrary to an early assumption corrected on the call.
- **Hard constraints:** fully local/offline (no cloud/API dependency), agentic (not rule-based), structured JSON output required.
- **Differentiator we're betting on:** long-horizon memory — connecting an event now to context from hours earlier (e.g. "soldiers entered this house 20 minutes before it exploded"), which off-the-shelf LLMs don't do natively (see [05-decisions/decision-log.md](05-decisions/decision-log.md#memory-as-the-innovation-angle)).
- **Immediate risk flagged by the professor:** scope is currently too broad (analyzing *any* video, from forklift accidents to bomb blasts). Needs narrowing before build starts.
