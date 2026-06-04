# Mimir Change Events

## Overview

Mimir can publish committed substrate writes as compact change events so external
systems can build read models, projections, caches, or integration workflows.

The feature is intentionally a **change stream**, not a workflow notification
system. Mimir reports generic facts about committed Mimir entities. It does not
emit application-specific concepts such as tasks, approvals, gates, obligations,
or disposition states.

## What Emits Events

Mimir emits v1 change events for committed creates of:

- artifacts;
- relations;
- embeddings.

Each event references the provenance event created for the same write.
Provenance events are not emitted as standalone Kafka events in v1.

## Architecture

Mimir uses a transactional outbox:

1. The API writes the domain row.
2. The API writes the provenance row.
3. The API writes the outbox row.
4. All three rows commit in one database transaction.
5. A separate publisher process reads unpublished outbox rows.
6. The publisher sends events to Kafka.
7. The publisher marks rows published only after Kafka acknowledgement.

The durable replay source is `mimirdata.change_outbox`. Kafka is the live
delivery stream.

## Topic and Key

| Item | Value |
|------|-------|
| Kafka topic | `mimir.changes.v1` |
| Kafka key | tenant id as a string |
| Event version | `1` |

Tenant-level keying preserves event order for related writes within a tenant.

## Event Envelope

All v1 events share this envelope:

```json
{
  "event_id": "019e9052-2ab7-71ca-b202-73d3104a8d73",
  "event_version": 1,
  "tenant_id": 1,
  "sequence": 12345,
  "entity_type": "artifact",
  "entity_id": "019e9052-4f16-7b94-9315-3d860b16cf55",
  "action": "create",
  "occurred_at": "2026-06-04T17:29:56.680899Z",
  "provenance_event_id": "019e9052-51aa-78d5-8a9e-42a6db30c2d0",
  "actor": {
    "type": "api_client",
    "id": "efforts"
  },
  "payload": {}
}
```

| Field | Description |
|-------|-------------|
| `event_id` | UUIDv7 event id. Consumers deduplicate with this field. |
| `event_version` | Event contract version. Current value is `1`. |
| `tenant_id` | Mimir tenant integer id. |
| `sequence` | Global outbox replay cursor. |
| `entity_type` | `artifact`, `relation`, or `embedding`. |
| `entity_id` | UUID of the changed entity. |
| `action` | Current v1 value is `create`. |
| `occurred_at` | Timestamp when the outbox row was created. |
| `provenance_event_id` | Matching provenance event for audit context. |
| `correlation_id` | Optional cross-write correlation id. Omitted when null. |
| `actor` | Optional actor copied from provenance context. |
| `payload` | Compact entity-specific facts. |

## Payloads

Artifact payload:

```json
{
  "artifact_type": "document",
  "parent_artifact_id": null,
  "source": "import",
  "source_system": "chatgpt",
  "external_id": "conv-123",
  "content_hash": "3780dde7ec167b0f9b2ae52ed5eb311a186b5561f5b882d60972a5f854459b73"
}
```

Relation payload:

```json
{
  "relation_type": "derived_from",
  "source_id": "019e9052-aaaa-7000-9000-000000000001",
  "target_id": "019e9052-bbbb-7000-9000-000000000002",
  "confidence": 1.0
}
```

Embedding payload:

```json
{
  "artifact_id": "019e9052-aaaa-7000-9000-000000000001",
  "embedding_type": "nomic-embed-text"
}
```

Payloads are intentionally compact. Artifact event payloads do not include full
artifact `content` or arbitrary `metadata` by default. Consumers that need the
full entity should fetch it from the Mimir API by `entity_id`.

## Delivery Semantics

Mimir provides at-least-once Kafka delivery.

Consumers must assume:

- duplicate events are possible;
- events should be deduplicated by `event_id`;
- `sequence` is the replay/resume cursor;
- Kafka retention may be finite;
- Kafka alone is not the durable replay guarantee.

Mimir retains outbox rows by default. A future release may expose an authenticated
backfill API or publisher replay mode. Until that exists, consumers that need
rebuilds beyond Kafka retention must coordinate directly against retained Mimir
outbox data or an operational replay process.

## Running the Publisher

The publisher is a separate process:

```bash
python -m mimir.outbox_publisher
```

Required environment:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Mimir PostgreSQL connection URL. |
| `POSTGRES_PASSWORD` | Yes | Required by Mimir settings validation. |
| `KAFKA_BOOTSTRAP_SERVERS` | Yes | Kafka bootstrap servers for the publisher. |
| `MIMIR_CHANGE_TOPIC` | No | Defaults to `mimir.changes.v1`. |
| `OUTBOX_BATCH_SIZE` | No | Rows claimed per batch. Default: `100`. |
| `OUTBOX_POLL_INTERVAL_SECONDS` | No | Idle poll interval. Default: `1.0`. |
| `OUTBOX_RETRY_BASE_SECONDS` | No | Base retry delay. Default: `1`. |
| `OUTBOX_RETRY_MAX_SECONDS` | No | Maximum retry delay. Default: `300`. |

In larnet, this should run as its own service using the Mimir API image after
Mimir migrations complete and Kafka is healthy.

## Consumer Offset Policy

Do not accept Kafka client defaults without analysis.

For event-log or projection-rebuild consumers, configure the consumer so offsets
move only after durable processing. For example:

```text
enable.auto.commit = false
auto.offset.reset = earliest
```

This warning applies regardless of Kafka client library. It is especially
important for Confluent clients because default consumer behavior can advance
offsets in ways that are inappropriate for replay-oriented consumers.

## What This Is Not

Change events are not:

- webhooks;
- a public REST notification endpoint;
- exactly-once delivery;
- a guarantee of infinite Kafka retention;
- an Efforts-specific workflow event model;
- a replacement for provenance history.

For audit trails, use provenance APIs. For live external projections, consume
`mimir.changes.v1`.
