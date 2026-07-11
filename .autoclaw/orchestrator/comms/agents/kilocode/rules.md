# Cross-Agent Coordination — Kilocode (`kilocode`)

You (`agent_id = kilocode`) have been added to this project's AutoClaw
fleet. Your coordination role: **worker**.

**Authoritative contract:** docs/AGENT_SESSION_PROTOCOL.md (the canonical
six-phase agent session protocol). Read it before acting.

## Your mailbox
- Inbox:   .autoclaw/orchestrator/comms/inboxes/kilocode/
- Shared:  .autoclaw/orchestrator/comms/inboxes/shared/
- State:   .autoclaw/orchestrator/comms/inboxes/kilocode/_state/
- Done:    .autoclaw/orchestrator/comms/inboxes/kilocode/processed/

## Lifecycle (per cycle)
1. Write a heartbeat to
   .autoclaw/orchestrator/comms/heartbeats/kilocode.json
   ({ agent_id, session_id, timestamp, status, current_task, sprint }).
2. SYNC your inbox + shared/; move handled messages to processed/.
3. CLAIM one in-scope, unclaimed, dependency-satisfied task with a
   create-exclusive write to comms/claims/<task-id>.json (fail if it
   exists — the filesystem is the mutex).
4. WORK in your claimed scope only.
5. REPORT: broadcast task_complete to shared/, send review_request to the
   other assigned agents, vote on open consensus/active/ items.

## How you are revived
- loop_mechanism:    plain-message
- keepalive_template: templates/keepalive/kilocode.md

When your heartbeat goes stale, the orchestrator's `/orchestrate revive
kilocode` renders that template (with your last task + stall duration)
and delivers it via the plain-message path.

## Shared memory — the Knowledge Graph
This project keeps a durable, queryable Knowledge Graph of decisions, findings,
and learned patterns (fed by the orchestrator, `/learn`, and the `kg.record`
MCP tool). Before re-deriving something, recall what the team already knows:
- `kg.search` (MCP tool) — semantic recall of past decisions/findings/patterns.
- `kg.traverse` (MCP tool) — walk relations out from a recalled thought.
- Humans browse + visualize it via the **AutoClaw: Knowledge Graph — Browse &
  Visualize** command (`autoclaw.kg.browse`).

## Hard rules
- Never edit outside your claimed scope.
- Never re-process a message already in processed/.
- Never claim a task whose claim file you do not own.
- Report honestly — failed tests are reported as failed.
