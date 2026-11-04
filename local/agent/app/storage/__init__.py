"""SQLite WAL persistence layer and lossless pooling for 30-second telemetry epochs."""

from app.storage.database import configure_connection, get_db_connection, init_database
from app.storage.orchestrator import StorageOrchestrator
from app.storage.repository import (
    DEFAULT_IKI_MIN_VALID_SAMPLES,
    EpochMetricsDTO,
    EpochRecordProtocol,
    EpochRepository,
    PooledTelemetryMetrics,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_epoch_metrics,
)

__all__ = [
    "DEFAULT_IKI_MIN_VALID_SAMPLES",
    "EpochMetricsDTO",
    "EpochRecordProtocol",
    "EpochRepository",
    "PooledTelemetryMetrics",
    "StorageOrchestrator",
    "configure_connection",
    "compute_shannon_entropy",
    "get_db_connection",
    "init_database",
    "merge_dwell_distributions",
    "pool_epoch_metrics",
]
