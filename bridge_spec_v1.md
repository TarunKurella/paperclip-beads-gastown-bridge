# Paperclip ↔ Beads ↔ Gastown Bridge Spec v1

## 1. Scope and Goals
A self-contained bridge that integrates Paperclip (source workflow), Beads (execution tracker), and Gastown (hook/assignment workflow) **without forking upstream projects**.

### Goals by phase
- **Phase 1 (Visibility):** mirror task status Paperclip → Beads and observe drift.
- **Phase 2 (Automation):** when Paperclip assignee appears/changes, attach corresponding Gastown hook.
- **Phase 3 (Hardening):** outbox, dedupe, distributed lease, DLQ, and reconciliation.

## 2. Source of Truth & Ownership
- **Task lifecycle source of truth:** Paperclip.
- **Operational mirror:** Beads status follows Paperclip through mapping.
- **Hook ownership:** Gastown hook assignment is derived from Paperclip assignee.
- **Bridge ownership:** bridge owns all integration state (sync snapshots, outbox, dedupe, leases).

## 3. Mapping Rules
### Status canonical model
Canonical values: `open`, `in_progress`, `blocked`, `done`.

### Paperclip → canonical
- `todo` → `open`
- `in_progress` → `in_progress`
- `blocked` → `blocked`
- `done` → `done`

### Beads → canonical
- `new` → `open`
- `active` → `in_progress`
- `blocked` → `blocked`
- `closed` → `done`

Mirror rule: for each shared item id, Beads is set to canonical(Paperclip) denormalized to Beads vocabulary.

## 4. Loop Prevention / Idempotency
- Every side-effectful command is represented as outbox event with **dedupe_key**.
- Dedupe keys examples:
  - `status:{item_id}:{target_status}`
  - `assign:{item_id}:{assignee}`
- Unique constraint on dedupe key prevents duplicate command issuance.
- Bridge never mirrors Beads back into Paperclip in v1 to avoid oscillation loops.

## 5. Reliability Model
- **Outbox table** persists pending integration actions.
- Worker processes pending events with retry + exponential backoff.
- After `max_retries`, event moved to **DLQ** (`status=dlq`).
- Reconciliation periodically scans for drift and repairs Beads state.
- Lease (`leases` table) enforces single active reconciler.

## 6. Conflict Policy
1. If Paperclip and Beads disagree, Paperclip wins.
2. Unknown statuses fail fast (validation error) and are surfaced in logs/tests.
3. Assignment conflicts (different Gastown hook state) are re-applied from Paperclip assignee during phase2/phase3 cycles.

## 7. Data Model (SQLite)
- `state_status(system, item_id, status, updated_at)`
- `outbox_events(event_id, dedupe_key UNIQUE, event_type, source_system, target_system, payload, status, retry_count, next_attempt_at, created_at)`
- `leases(name PRIMARY KEY, owner, expires_at)`
- `schema_migrations(name PRIMARY KEY)`

## 8. Rollout Plan
### Phase 1: Visibility sync
- read Paperclip + Beads snapshots
- compute canonical diffs
- enqueue status mirror outbox events
- process events

### Phase 2: Assignment automation
- read Paperclip assignees
- enqueue Gastown hook attach events
- process events

### Phase 3: Hardening
- enable lease-guarded reconciler
- enforce retry/backoff/DLQ on outbox failures
- periodic drift reconciliation

## 9. Non-goals (v1)
- Bi-directional status authority.
- Schema/control changes in upstream systems.
- Real-time event bus; polling + outbox is sufficient.
