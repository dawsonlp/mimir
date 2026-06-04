# Mimir Change Outbox Development Plan

## Status

Implementation plan for CR-1.

Mimir-owned implementation phases 1-5 are complete in v5.5.0:

- `mimirdata.change_outbox` exists as a retained replay ledger.
- Artifact, relation, and embedding creates write domain row, provenance row,
  and outbox row atomically.
- Publisher state-machine helpers exist for claiming, publishing, retrying, and
  status reporting.
- Kafka publisher entry point exists at `python -m mimir.outbox_publisher`.
- User-facing event contract documentation exists in `docs/change-events.md`.

Remaining work is runtime validation and handoff: larnet service wiring, Kafka
smoke/failure tests, Efforts projection validation, and any release follow-up
documentation discovered by those tests.

Source architecture: [change-outbox-architecture.md](change-outbox-architecture.md)

## Objective

Implement a durable, replayable Mimir change-event stream for external projections while preserving Mimir's role as a generic storage substrate.

The implementation is not complete until all of these are true:

- Mimir writes create entity, provenance, and outbox rows atomically.
- Mimir publishes generic change events to Kafka through a separate publisher.
- Consumers can deduplicate events and resume by sequence.
- larnet can run the publisher service without owning Mimir event semantics.
- Efforts can validate a projection rebuild from Mimir changes.

## Development Principles

- Build the durable database invariant before the Kafka publisher.
- Keep Mimir event facts generic; no Efforts workflow semantics.
- Prefer small, testable internal seams over a large cross-service release.
- Treat Kafka as live delivery and Mimir outbox as retained replay ledger.
- Make failure modes observable before optimizing for throughput.
- Do not delete or compact outbox history until a separate lifecycle decision exists.

## Workstreams

### Mimir Core

Owns schema, write-path transactionality, event contract, publisher module, tests, and documentation.

### larnet Infrastructure

Owns compose service wiring, Kafka topic/retention configuration, environment variables, and local runtime verification.

### Efforts Validation

Owns consumer projection logic and the end-to-end validation trace.

## Phase 0: Readiness and Design Lock

Goal: freeze the v1 contract enough to implement safely.

Tasks:

- Confirm the architecture document is accepted by Mimir and larnet.
- Confirm `mimir.changes.v1` as the topic name.
- Confirm Kafka key is `{tenant_id}` for v1.
- Confirm v1 emitted entity types: artifact, relation, embedding.
- Confirm no standalone provenance-event emission by default.
- Confirm outbox rows are retained after publish.
- Decide whether larnet pre-creates `mimir.changes.v1` or the publisher only documents required topic settings.
- Decide whether public backfill API is in v1 or deferred.

Exit criteria:

- No unresolved disagreement on event ordering, replay source, or emitted entity types.
- Open questions are either answered or explicitly deferred.

## Phase 1: Outbox Schema

Goal: add durable storage for change events without changing API behavior.

Tasks:

- Add migration `008_change_outbox.up.sql`.
- Add down migration.
- Create `mimirdata.change_outbox`.
- Add indexes for unpublished rows, tenant sequence replay, and tenant entity lookup.
- Add database comments explaining replay and publication semantics.
- Add migration tests or integration checks where feasible.
- Update data model docs.

Exit criteria:

- Fresh database migrations create the outbox table.
- Existing databases can migrate forward.
- Unit/integration checks confirm schema shape and indexes.

Risk:

- Low. This phase is additive and should not change write behavior yet.

## Phase 2: Internal Outbox Model and Event Contract

Goal: make event construction deterministic before touching write transactions.

Tasks:

- Add internal schemas/models for `ChangeOutboxEvent`.
- Add event version constant: `event_version = 1`.
- Add payload builders for artifacts, relations, and embeddings.
- Add Kafka key builder using tenant id.
- Add serialization tests with fixed sample rows.
- Add validation that event payloads remain compact and do not include full artifact content by default.

Exit criteria:

- Event JSON contract is covered by unit tests.
- Payload builders are pure enough to test without database or Kafka.

Risk:

- Medium. Contract drift here will affect downstream consumers, so tests should pin examples.

## Phase 3: Transaction Refactor

Goal: make entity, provenance, and outbox writes atomic.

Tasks:

- Refactor `provenance_service.log_action` so callers can pass an existing database connection/transaction.
- Add an internal outbox insert function that accepts an existing connection.
- Refactor artifact create path:
  - insert artifact;
  - insert provenance;
  - insert outbox;
  - commit once.
- Refactor relation create path the same way.
- Refactor embedding create path the same way.
- Preserve current API responses and error behavior.
- Ensure duplicate UUID/relation conflict still rolls back all related writes.
- Add tests proving no outbox row exists when the domain insert fails.
- Add tests proving outbox rows include the matching `provenance_event_id`.

Exit criteria:

- All create paths have one transaction boundary.
- Domain row, provenance row, and outbox row are all present or all absent.
- Existing API unit and integration tests still pass.

Risk:

- High. This is the core behavioral refactor.

Gate:

- Do not start Kafka publisher implementation until this phase is passing.

## Phase 4: Outbox Query and Publisher State Machine

Goal: implement publisher database behavior before Kafka integration.

Tasks:

- Add repository functions:
  - fetch unpublished rows ordered by `sequence`;
  - lock rows with `FOR UPDATE SKIP LOCKED`;
  - mark row published;
  - record publish failure and increment attempts.
- Add retry/backoff policy.
- Add batch size setting.
- Add tests for ordering, lock query construction, publish success, and failure update.
- Add health/status function that reports unpublished count and oldest unpublished age.

Exit criteria:

- Publisher state transitions are tested without Kafka.
- Failure does not mark rows published.
- Successful acknowledgement is the only path to `published_at`.

Risk:

- Medium. Correctness depends on clear state transitions.

## Phase 5: Kafka Publisher Module

Goal: publish retained outbox events to Kafka with honest at-least-once semantics.

Tasks:

- Add Kafka client dependency only if necessary and scoped to backend runtime.
- Record Kafka client selection rationale, including why producer-only
  `confluent-kafka` use is acceptable and why consumer defaults cannot be
  inherited without analysis.
- Add `mimir.outbox_publisher` module.
- Read config:
  - `KAFKA_BOOTSTRAP_SERVERS`;
  - `MIMIR_CHANGE_TOPIC`;
  - batch size;
  - poll interval;
  - retry/backoff settings.
- Publish with key `{tenant_id}`.
- Wait for Kafka acknowledgement before marking published.
- Log event id, tenant id, sequence, entity type, and failures.
- Add graceful shutdown handling.
- Add local smoke command documentation.

Exit criteria:

- Publisher can drain synthetic outbox rows to a Kafka topic.
- Re-running publisher does not lose unpublished rows.
- Duplicate delivery remains possible and documented.

Risk:

- Medium-high. Kafka client behavior and container runtime need direct validation.

## Phase 6: larnet Integration

Goal: run the publisher as infrastructure without moving ownership out of Mimir.

Tasks for larnet:

- Add `larnet-mimir-outbox-publisher` service.
- Use `dawsonlp/mimir-api` image and command `python -m mimir.outbox_publisher`.
- Wire Mimir database URL, Kafka bootstrap servers, and topic name.
- Add dependency on Mimir migration completion and Kafka health.
- Decide topic configuration:
  - pre-create topic with explicit retention; or
  - document auto-create behavior and retention limits.
- Add docs entry in larnet service table and port/runtime reference.

Exit criteria:

- `docker compose up -d` starts publisher after Mimir and Kafka.
- Publisher remains healthy when no rows are pending.
- Publisher drains rows when Mimir creates artifacts/relations.

Risk:

- Medium. larnet wiring is simple, but topic retention semantics must not be overstated.

## Phase 7: Integration and Failure Testing

Goal: prove the design survives ordinary failure modes.

Tests:

- Create artifact through API, observe outbox row.
- Create artifact through API, observe Kafka event.
- Create relation through API, observe relation payload.
- Stop Kafka, create artifact, confirm outbox row remains unpublished.
- Restart Kafka/publisher, confirm row publishes.
- Force duplicate publish scenario if possible, confirm consumer can deduplicate by `event_id`.
- Verify tenant-key ordering for a small chain:
  - artifact create;
  - artifact create;
  - relation create.
- Verify published rows remain in outbox and can be queried by `tenant_id, sequence`.

Exit criteria:

- No observed lost event after DB commit.
- At-least-once behavior is demonstrated.
- Replay cursor exists and works from retained outbox rows.

Risk:

- High. This phase is where architectural claims meet actual runtime behavior.

## Phase 8: Efforts Validation Trace

Goal: validate CR-1 against the user who asked for it.

Trace:

1. Efforts creates a Fact artifact with a client UUIDv7.
2. Efforts creates derived Ask/Todo artifacts.
3. Efforts links claims back to Facts through relations.
4. Mimir emits change events for each committed write.
5. Efforts consumes `mimir.changes.v1`.
6. Efforts builds a projection from events.
7. Efforts simulates consumer downtime.
8. Efforts resumes from sequence or backfills from Mimir outbox.

Exit criteria:

- Efforts can rebuild the intended projection without scraping arbitrary API responses.
- Any remaining gaps are classified as CR-1 follow-up, CR-2 provenance depth, or Efforts-owned projection logic.
- Any Kafka consumer used in validation explicitly disables unsafe default offset
  movement for replay semantics, or documents why a different offset policy is
  correct for that specific consumer.

Risk:

- Medium. This may reveal payload fields that are missing from the v1 contract.

## Phase 9: Release and Documentation

Goal: ship without hiding operational constraints.

Tasks:

- Update Mimir docs:
  - data model;
  - architecture;
  - operations;
  - event contract;
  - delivery semantics.
- Update larnet docs:
  - publisher service;
  - topic name;
  - retention warning;
  - startup order.
- Add release notes.
- Version Mimir API and client if client support changes.
- Build and publish Docker image.
- Trigger release workflow if PyPI/client changes are included.

Exit criteria:

- Release notes state at-least-once delivery and retained outbox replay source.
- Docs do not imply exactly-once delivery or infinite Kafka retention.
- larnet and Mimir docs agree.

## Stop/Go Gates

### Gate A: Before Transaction Refactor

Require:

- outbox schema accepted;
- event contract tests written;
- no unresolved event ordering decision.

### Gate B: Before Publisher

Require:

- atomic entity/provenance/outbox writes passing;
- failure rollback tests passing.

### Gate C: Before larnet Runtime

Require:

- publisher state machine tested;
- Kafka publish smoke test passing locally.
- Kafka client decision documented, including the prohibition on accepting
  Confluent consumer defaults for event-log/replay consumers without analysis.

### Gate D: Before Release

Require:

- integration failure tests passing;
- larnet compose verified;
- Efforts validation trace either complete or explicitly deferred with rationale.

## Implementation Tickets

1. `OUTBOX-001`: Add change outbox migration. **Done in v5.5.0.**
2. `OUTBOX-002`: Add event contract models and payload builders. **Done in v5.5.0.**
3. `OUTBOX-003`: Refactor provenance logging for caller-owned transactions. **Done in v5.5.0.**
4. `OUTBOX-004`: Refactor artifact create transaction and outbox write. **Done in v5.5.0.**
5. `OUTBOX-005`: Refactor relation create transaction and outbox write. **Done in v5.5.0.**
6. `OUTBOX-006`: Refactor embedding create transaction and outbox write. **Done in v5.5.0.**
7. `OUTBOX-007`: Add publisher repository/state machine. **Done in v5.5.0.**
8. `OUTBOX-008`: Add Kafka publisher module. **Done in v5.5.0.**
9. `OUTBOX-009`: Add larnet publisher service. **Pending outside this repo.**
10. `OUTBOX-010`: Add failure-mode integration tests. **Pending runtime validation.**
11. `OUTBOX-011`: Run Efforts validation trace. **Pending consumer validation.**
12. `OUTBOX-012`: Publish docs and release. **Mimir docs/release done for v5.5.0; larnet/Efforts follow-up remains.**

## Development Cadence

Recommended cadence:

- Implement one phase at a time.
- After each phase, run backend unit tests and relevant integration tests.
- After phases 3, 5, 6, and 8, write a short decision/update note in `comms/inbox` or the relevant project comms directory.
- Do not merge larnet service changes until the Mimir publisher command exists.
- Do not ask Efforts to validate until Mimir and larnet can produce real Kafka events.

## Residual Risks

- Kafka retention may be misread as durable replay unless docs are precise.
- Kafka client defaults may be misread as correct replay behavior unless
  consumer offset policy is explicitly configured and tested.
- Atomic write refactor may expose hidden assumptions in current service tests.
- Publisher dependency may increase backend image footprint.
- Tenant-key ordering may become a throughput bottleneck later.
- Payload minimization may require consumers to fetch more often than expected.

These are acceptable for v1 if documented and tested.
