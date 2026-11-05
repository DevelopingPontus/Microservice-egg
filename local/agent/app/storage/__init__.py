"""Raw Material Store (`app/storage/`): SQLite WAL persistence and lossless epoch pooling."""

from app.storage.database import (
    SCHEMA_SQL,
    configure_connection,
    get_db_connection,
    init_database,
)
from app.storage.repository import (
    DEFAULT_IKI_MIN_VALID_SAMPLES,
    ActivityBlockDTO,
    ActivityBlockRecordProtocol,
    EpochMetricsDTO,
    EpochRecordProtocol,
    EpochRepository,
    PooledTelemetryMetrics,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_epoch_metrics,
)

__all__ = [
    "ActivityBlockDTO",
    "ActivityBlockRecordProtocol",
    "DEFAULT_IKI_MIN_VALID_SAMPLES",
    "EpochMetricsDTO",
    "EpochRecordProtocol",
    "EpochRepository",
    "PooledTelemetryMetrics",
    "SCHEMA_SQL",
    "compute_shannon_entropy",
    "configure_connection",
    "get_db_connection",
    "init_database",
    "merge_dwell_distributions",
    "pool_epoch_metrics",
]
