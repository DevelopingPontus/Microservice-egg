"""SQLite WAL persistence layer and lossless pooling for 30-second telemetry epochs."""

from app.storage.database import configure_connection, get_db_connection, init_database
from app.storage.repository import (
    EpochMetricsDTO,
    EpochRepository,
    PooledTelemetryMetrics,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_epoch_metrics,
)

__all__ = [
    "EpochMetricsDTO",
    "EpochRepository",
    "PooledTelemetryMetrics",
    "configure_connection",
    "compute_shannon_entropy",
    "get_db_connection",
    "init_database",
    "merge_dwell_distributions",
    "pool_epoch_metrics",
]
