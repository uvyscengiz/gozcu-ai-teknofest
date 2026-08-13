# Project Overview

## What we're building

For TEKNOFEST's Yapay Zeka Dil Ajanları Yarışması (AI Language Agents Competition), 3rd scenario category: a video analysis and decision-support agentic system. It watches high-volume fixed-camera footage (factory floors, security/CCTV, drone/operational footage), analyzes what's happening, and produces a Turkish-language report with risk assessment and recommended operator actions — entirely offline, entirely agentic (not rule-based).

Think of the system as replacing a human security operator who watches dozens of camera feeds at once, mentally narrates what's happening ("forklift got on, picked up a load, lifted it, then an accident happened while lifting"), and files reports when asked. The system's job is to do that narration and reporting automatically, then go further: connect events across a long time horizon (see [memory as the differentiator](#memory-as-the-core-differentiator) below).

## Competition category clarification

The competition has three categories. We are in **category 3**. Categories 1 and 2 (internal-enterprise text AI, and finance) are different problem shapes entirely — no video involved — so they aren't directly comparable competitors on technical approach, even though every team in category 3 is nominally solving "watch a video, produce a report."

## Core loop, in plain terms

1. A human operator, given no AI at all, watches a camera feed.
2. They narrate/log what they see, minute by minute, in their head or on paper: what object, what action, what changed.
3. When asked for a report, they synthesize: what happened, why (user error? mechanical failure? environmental?), who/what is at fault, severity.
4. Our system is that operator, automated — plus the ability to reason about *causes* and *consequences* (not just "what did I see"), because it can measure things a human can't (e.g., compute an object's speed from frame deltas rather than eyeballing it).

## Memory as the core differentiator

Off-the-shelf video-language models handle ~10–20 minutes of context before they lose track. Our bet: build a memory layer so the system connects an event now to relevant context from much earlier — e.g., "our soldiers entered this house 20 minutes ago; the house has now exploded; therefore our soldiers were very likely inside during the explosion, and here's the likely injury severity based on blast size" — rather than a generic "house exploded" report with no causal chain.

This is explicitly validated as the innovative angle by our advising professor (not an assumption we invented — see [05-decisions/decision-log.md](../05-decisions/decision-log.md#memory-as-the-innovation-angle)): current LLMs don't have this kind of long-horizon episodic memory built in, so building it ourselves is genuinely novel, not "explaining what already exists."

## Hard constraints (non-negotiable per competition rules)

- **Fully local/offline.** No cloud API, no external service dependency, at inference time.
- **Agentic architecture required.** Static rule-based solutions are explicitly scored down.
- **Structured output required.** JSON, machine-parseable.
- **Open source only,** reproducible.

See [requirements.md](requirements.md) for the full requirements table and [evaluation-mapping.md](../03-planning/evaluation-mapping.md) for how each scoring criterion maps to our design choices.

## Known open risk

Scope is currently too broad. The system as sketched needs to reason about *any* video content — a forklift accident, a kitchen fire, a bomb blast — with no defined domain boundary. Our professor flagged this directly: an overly broad interpretive scope will produce more failure modes even on simple examples. Plan is to **narrow scope for the competition submission** (most likely: industrial/factory safety incidents) and note broader generalization as future work. See [05-decisions/decision-log.md](../05-decisions/decision-log.md#scope-narrowing).
