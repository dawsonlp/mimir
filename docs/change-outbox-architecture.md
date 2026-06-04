# Mimir Change Outbox Architecture

## Status

Approved architectural direction for CR-1, pending technical design and implementation.

## Context

Efforts requested a Mimir change-event stream so external read models can rebuild projections from Mimir writes. This is a valid substrate-level need, not an Efforts-specific workflow request.

Mimir currently stores append-only artifacts, relations, embeddings, provenance events, and AGE graph projections. larnet provides Kafka and can orchestrate a Mimir publisher service, but Mimir does not currently emit write events.

The requirement is not merely "notify someone that something happened." The requirement is:

- committed Mimir writes become visible to external consumers;
- event publication survives process crashes and Kafka outages;
- consumers can replay or backfill enough change history to rebuild projections;
- events remain generic Mimir substrate facts, not Efforts workflow events.

## Decision

Mimir will implement a transactional change outbox and a Mimir-owned Kafka publisher service.

The outbox is the durable source of Mimir change facts. Kafka is the delivery stream for consumers. larnet may orchestrate the publisher, but Mimir owns the schema, event contract, publisher behavior, and compatibility guarantees.

## Goals

- Publish committed creates for Mimir substrate entities.
- Preserve Mimir's mechanism-not-policy boundary.
- Avoid lost events when the API process or Kafka fails.
- Support projection rebuilds with explicit replay/backfill semantics.
- Keep the first event contract compact, stable, and versioned.
- Make delivery guarantees honest and testable.

## Non-Goals

- No Efforts-specific concepts such as gates, obligations, asks, todos, approval states, or disposition workflow.
- No truth adjudication or semantic interpretation.
- No guarantee of exactly-once delivery to Kafka consumers.
- No direct coupling between Mimir request handlers and Kafka acknowledgements.
- No requirement that Kafka alone retain infinite history.

## Architecture

### Components

1. Mimir API write path
   - Creates the domain row.
   - Creates the provenance row.
   - Creates the outbox row.
   - Commits all three in one database transaction.

2. `mimirdata.change_outbox`
   - Durable ledger of Mimir change events.
   - Retained by default.
   - Records publication state separately from event occurrence.

3. Mimir outbox publisher
   - Long-running service started by larnet or another runtime.
   - Reads unpublished outbox rows.
   - Publishes to Kafka.
   - Marks rows published only after Kafka acknowledgement.

4. Kafka topic `mimir.changes.v1`
   - Live delivery stream for external consumers.
   - At-least-once delivery.
   - Consumers deduplicate by `event_id`.

## Database Schema

Initial schema:

```sql
CREATE TABLE mimirdata.change_outbox (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    tenant_id int NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,

    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    action text NOT NULL,

    occurred_at timestamptz NOT NULL DEFAULT now(),
    sequence bigint GENERATED ALWAYS AS IDENTITY,

    provenance_event_id uuid,
    correlation_id uuid,

    actor_type text,
    actor_id text,

    payload jsonb NOT NULL DEFAULT '{}'::jsonb,

    published_at timestamptz,
    publish_attempts int NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error text,

    CONSTRAINT change_outbox_action_check
        CHECK (action IN ('create'))
);

CREATE INDEX idx_change_outbox_unpublished
ON mimirdata.change_outbox (next_attempt_at, sequence)
WHERE published_at IS NULL;

CREATE INDEX idx_change_outbox_tenant_sequence
ON mimirdata.change_outbox (tenant_id, sequence);

CREATE INDEX idx_change_outbox_tenant_entity
ON mimirdata.change_outbox (tenant_id, entity_type, entity_id);
```

Rationale:

- `id` is the external event id and deduplication key.
- `sequence` gives a simple global ordering cursor independent of timestamp precision.
- `tenant_id, sequence` supports tenant-scoped replay.
- `published_at` records delivery state without deleting replay history.
- `next_attempt_at` persists retry timing across publisher restarts.
- `payload` carries compact entity-specific facts.

## Atomic Write Requirement

The API write path must be refactored so entity creation, provenance creation, and outbox insertion occur in the same transaction.

Current behavior is not sufficient where entity creation commits before provenance logging. CR-1 requires a stronger invariant:

> If a Mimir write commits, the corresponding change event obligation is committed with it.

If any part of the entity/provenance/outbox write fails, the whole transaction must roll back.

## Event Contract

Topic:

```text
mimir.changes.v1
```

Kafka key:

```text
{tenant_id}
```

Rationale:

- Tenant-level ordering is more important than entity-level partition distribution for v1.
- Projection rebuilds often depend on related artifact, relation, and provenance ordering.
- Hot partitions are acceptable for the initial local-first and early production use cases.

Message payload:

```json
{
  "event_id": "019e9052-2ab7-71ca-b202-73d3104a8d73",
  "event_version": 1,
  "tenant_id": 1,
  "sequence": 12345,
  "entity_type": "relation",
  "entity_id": "019e9052-4f16-7b94-9315-3d860b16cf55",
  "action": "create",
  "occurred_at": "2026-06-04T01:49:24.535Z",
  "provenance_event_id": "019e9052-51aa-78d5-8a9e-42a6db30c2d0",
  "correlation_id": "019e9052-7000-744e-87de-2f2fa9d85f3c",
  "actor": {
    "type": "api_client",
    "id": "efforts"
  },
  "payload": {
    "relation_type": "derived_from",
    "source_id": "019e9052-aaaa-7000-9000-000000000001",
    "target_id": "019e9052-bbbb-7000-9000-000000000002"
  }
}
```

### Entity Payloads

Artifact event payload should include:

- `artifact_type`
- `parent_artifact_id`
- `source`
- `source_system`
- `external_id`
- `content_hash`

Relation event payload should include:

- `relation_type`
- `source_id`
- `target_id`
- `confidence`

Embedding event payload should include:

- `artifact_id`
- `embedding_type`

Provenance events should not be emitted as separate change events in v1 unless a concrete consumer needs audit-log projection. Artifact, relation, and embedding events should reference their corresponding `provenance_event_id`.

## Publisher Behavior

The publisher should:

1. Select due unpublished rows ordered by `sequence`.
2. Lock rows with `FOR UPDATE SKIP LOCKED`.
3. Publish each row to Kafka with key `{tenant_id}`.
4. Mark `published_at` only after Kafka acknowledgement.
5. Increment `publish_attempts`, store `last_error`, and set `next_attempt_at` on failure.
6. Retry failed rows with backoff.
7. Expose health information.

Selection sketch:

```sql
SELECT *
FROM mimirdata.change_outbox
WHERE published_at IS NULL
  AND next_attempt_at <= now()
ORDER BY sequence
LIMIT 100
FOR UPDATE SKIP LOCKED;
```

Delivery semantics:

- At least once.
- Not exactly once.
- Consumers must deduplicate by `event_id`.
- Consumers should treat `sequence` as the replay cursor.

## Kafka Client Decision

Mimir's v1 publisher may use `confluent-kafka` for producer-only Kafka delivery.

Rationale:

- The current publisher is a producer, not a Kafka consumer. It does not hold or
  advance a Kafka read offset.
- The publisher waits for producer delivery acknowledgement before marking a
  retained outbox row as published.
- `confluent-kafka` is actively maintained and is backed by `librdkafka`, which
  is a mature Kafka client library.
- Python has no Apache-maintained Kafka client in the Apache Kafka main project;
  non-Java clients are independent projects.
- `kafka-python` is again actively releasing and remains a viable future option,
  especially where pure Python packaging is preferred, but it does not remove
  the need for explicit offset configuration in consumer use cases.

Constraint:

Confluent Kafka client defaults must not be accepted without analysis for any
Mimir consumer or replay tool. Confluent consumer defaults include automatic
offset commit behavior and default tailing behavior that can conflict with
event-log replay semantics. Any Mimir-owned Kafka consumer must explicitly
choose offset behavior for its use case.

For event-log or projection-rebuild consumers, require explicit configuration
equivalent to:

```text
enable.auto.commit = false
auto.offset.reset = earliest
```

Offsets must be committed only after the consumer has durably processed the
event, or the consumer must use explicit assignment/seek behavior for replay.
This requirement applies regardless of whether the client library is
`confluent-kafka`, `kafka-python`, or another Kafka client.

## Replay and Retention

The durable replay source is Mimir's `change_outbox`, not Kafka alone.

Kafka topic retention in larnet may be finite. Therefore Kafka should be treated as the live delivery stream unless the deployment explicitly configures long or infinite retention.

Mimir should retain outbox rows by default. A future lifecycle policy may archive or compact old rows, but that must be a deliberate storage decision, not an implementation side effect.

For consumers that need to rebuild after Kafka retention has expired, Mimir should eventually expose one of:

- an authenticated change-backfill API, filtered by tenant and `after_sequence`;
- or a publisher replay mode that republishes retained outbox rows from a requested sequence.

The first implementation may defer the public backfill surface, but it must not delete published outbox rows by default.

## Optional Wake-Up Notification

Postgres `LISTEN/NOTIFY` may be used only as a wake-up optimization:

- insert outbox row transactionally;
- trigger `NOTIFY mimir_outbox`;
- publisher wakes and drains rows;
- publisher also polls periodically.

`LISTEN/NOTIFY` is not the durable event source.

## larnet Integration

larnet should add a service similar to:

```yaml
larnet-mimir-outbox-publisher:
  image: dawsonlp/mimir-api:latest
  container_name: larnet-mimir-outbox-publisher
  command: ["python", "-m", "mimir.outbox_publisher"]
  environment:
    DATABASE_URL: postgresql://${MIMIR_PG_USER:-mimir}:${MIMIR_PG_PASSWORD:-mimir_dev_password}@larnet-mimir-postgres:5432/${MIMIR_PG_DB:-mimir}
    POSTGRES_PASSWORD: ${MIMIR_PG_PASSWORD:-mimir_dev_password}
    KAFKA_BOOTSTRAP_SERVERS: larnet-kafka:29092
    MIMIR_CHANGE_TOPIC: mimir.changes.v1
  networks:
    - larnet
  restart: unless-stopped
  depends_on:
    larnet-mimir-migrate:
      condition: service_completed_successfully
    larnet-kafka:
      condition: service_healthy
```

larnet should also document Kafka retention for `mimir.changes.v1`. If larnet does not pre-create topics, the publisher or deployment docs must specify the expected topic configuration.

## Testing

Required tests:

- Unit test event payload construction.
- Unit test outbox insertion for artifact, relation, and embedding creates.
- Unit test publisher selection ordering and retry state transitions.
- Integration test: create artifact through API, observe outbox row.
- Integration test: create relation through API, observe Kafka message.
- Integration test: simulate Kafka failure, verify outbox row remains unpublished and is retried.
- Contract test: consumer can deduplicate by `event_id` and resume from `sequence`.

## Implementation Sequence

1. Add `change_outbox` migration.
2. Refactor provenance logging so it can participate in caller-owned transactions.
3. Refactor artifact/relation/embedding create paths into single entity/provenance/outbox transactions.
4. Add outbox event construction and schema tests.
5. Add publisher module.
6. Add larnet publisher service.
7. Add Kafka integration tests.
8. Validate Efforts trace: Fact -> derived Ask/Todo -> relation provenance -> projection rebuild.

## Open Questions

- Should Mimir expose a public change-backfill API in the first implementation, or defer it until after Kafka live delivery is validated?
- Should event payloads include artifact `metadata` for all artifact changes, or should consumers fetch artifacts by ID when needed?
- Should larnet pre-create `mimir.changes.v1` with explicit retention, or should the publisher create/validate the topic?
- Should the publisher run inside the API image or a slimmer sibling image?

## Final Position

The transactional outbox plus Mimir-owned publisher is the correct CR-1 architecture.

The larnet proposal is accepted as the baseline, with these required amendments:

- Kafka key by tenant for v1.
- Treat Mimir outbox, not Kafka alone, as durable replay source.
- Refactor writes so entity, provenance, and outbox rows commit atomically.
- Do not emit separate provenance change events by default.
- Retain outbox rows by default until an explicit lifecycle policy exists.
- Define compact per-entity payload contracts before implementation.
