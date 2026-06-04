"""Kafka publisher for retained Mimir change outbox rows."""

import asyncio
import logging
import signal
from dataclasses import dataclass

from confluent_kafka import KafkaException, Producer

from mimir.config import Settings, get_settings
from mimir.database import close_pool, get_connection, init_pool
from mimir.services.change_outbox import (
    ChangeOutboxRow,
    build_kafka_key,
    calculate_retry_delay_seconds,
    fetch_unpublished_events,
    get_outbox_status,
    mark_published,
    record_publish_failure,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxPublisherConfig:
    """Runtime configuration for the outbox publisher."""

    kafka_bootstrap_servers: str
    topic: str
    batch_size: int
    poll_interval_seconds: float
    retry_base_seconds: int
    retry_max_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> OutboxPublisherConfig:
        if not settings.kafka_bootstrap_servers:
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS is required for the publisher")

        return cls(
            kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.mimir_change_topic,
            batch_size=settings.outbox_batch_size,
            poll_interval_seconds=settings.outbox_poll_interval_seconds,
            retry_base_seconds=settings.outbox_retry_base_seconds,
            retry_max_seconds=settings.outbox_retry_max_seconds,
        )


class KafkaChangeProducer:
    """Thin acknowledgement-oriented wrapper around confluent-kafka Producer."""

    def __init__(self, *, bootstrap_servers: str) -> None:
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})

    async def publish(self, *, topic: str, row: ChangeOutboxRow) -> None:
        event = row.event
        loop = asyncio.get_running_loop()
        delivery = loop.create_future()

        def on_delivery(error, _message) -> None:
            if error is None:
                loop.call_soon_threadsafe(delivery.set_result, None)
            else:
                loop.call_soon_threadsafe(delivery.set_exception, KafkaException(error))

        self._producer.produce(
            topic,
            key=build_kafka_key(event.tenant_id),
            value=event.model_dump_json(exclude_none=True).encode("utf-8"),
            on_delivery=on_delivery,
        )

        while not delivery.done():
            self._producer.poll(0.1)
            await asyncio.sleep(0)

        await delivery

    def close(self) -> None:
        self._producer.flush(5)


async def run_once(
    *,
    config: OutboxPublisherConfig,
    producer: KafkaChangeProducer,
) -> int:
    """Drain one due batch from the outbox.

    Returns the number of rows claimed from the database. Failed rows remain
    unpublished and receive a persisted retry time.
    """
    async with get_connection() as conn:
        rows = await fetch_unpublished_events(conn=conn, limit=config.batch_size)
        for row in rows:
            event = row.event
            try:
                await producer.publish(topic=config.topic, row=row)
            except Exception as exc:
                retry_after_seconds = calculate_retry_delay_seconds(
                    row.publish_attempts,
                    base_seconds=config.retry_base_seconds,
                    max_seconds=config.retry_max_seconds,
                )
                await record_publish_failure(
                    conn=conn,
                    event_id=event.event_id,
                    error=str(exc),
                    retry_after_seconds=retry_after_seconds,
                )
                logger.warning(
                    "change_outbox_publish_failed",
                    extra={
                        "event_id": str(event.event_id),
                        "tenant_id": event.tenant_id,
                        "sequence": event.sequence,
                        "entity_type": event.entity_type,
                        "retry_after_seconds": retry_after_seconds,
                    },
                )
            else:
                await mark_published(conn=conn, event_id=event.event_id)
                logger.info(
                    "change_outbox_published",
                    extra={
                        "event_id": str(event.event_id),
                        "tenant_id": event.tenant_id,
                        "sequence": event.sequence,
                        "entity_type": event.entity_type,
                    },
                )

        await conn.commit()
        return len(rows)


async def run_forever(config: OutboxPublisherConfig) -> None:
    """Run the publisher until interrupted."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await init_pool()
    producer = KafkaChangeProducer(bootstrap_servers=config.kafka_bootstrap_servers)
    try:
        while not stop_event.is_set():
            claimed = await run_once(config=config, producer=producer)
            if claimed == 0:
                async with get_connection() as conn:
                    status = await get_outbox_status(conn=conn)
                logger.info(
                    "change_outbox_idle",
                    extra={
                        "unpublished_count": status.unpublished_count,
                        "oldest_unpublished_age_seconds": (
                            status.oldest_unpublished_age_seconds
                        ),
                    },
                )
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=config.poll_interval_seconds
                    )
                except TimeoutError:
                    pass
    finally:
        producer.close()
        await close_pool()


async def async_main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    config = OutboxPublisherConfig.from_settings(settings)
    await run_forever(config)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
