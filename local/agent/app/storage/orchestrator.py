"""Folder orchestrator for local SQLite WAL persistence and lossless epoch pooling."""

from collections.abc import Sequence
from pathlib import Path

from app.storage.database import init_database
from app.storage.repository import (
    DEFAULT_IKI_MIN_VALID_SAMPLES,
    ActivityBlockDTO,
    ActivityBlockRecordProtocol,
    EpochMetricsDTO,
    EpochRecordProtocol,
    EpochRepository,
    PooledTelemetryMetrics,
    pool_epoch_metrics,
)


class StorageOrchestrator:
    """Folder orchestrator coordinating SQLite WAL initialization, CRUD, and pooling math."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        repository: EpochRepository | None = None,
        iki_min_valid_samples: int = DEFAULT_IKI_MIN_VALID_SAMPLES,
    ) -> None:
        self._db_path = Path(db_path)
        self._repository = repository if repository is not None else EpochRepository(self._db_path)
        self._iki_min_valid_samples = iki_min_valid_samples

    @property
    def db_path(self) -> Path:
        """Database file path managed by this orchestrator."""
        return self._db_path

    @property
    def repository(self) -> EpochRepository:
        """Underlying async epoch repository."""
        return self._repository

    async def initialize(self) -> None:
        """Ensure SQLite WAL pragmas, tables, and indexes exist."""
        await init_database(self._db_path)

    async def insert_epoch(self, epoch: EpochRecordProtocol) -> int:
        """Persist a single 30-second epoch record and return its primary key id."""
        return await self._repository.insert_epoch(epoch)

    async def fetch_epochs_in_range(
        self,
        start_time: float,
        end_time: float,
    ) -> list[EpochMetricsDTO]:
        """Fetch persisted epochs within [start_time, end_time] ordered chronologically."""
        return await self._repository.fetch_epochs_in_range(start_time, end_time)

    async def count_epochs(self) -> int:
        """Return total number of persisted 30-second epoch rows."""
        return await self._repository.count_epochs()

    def pool_epochs(self, epochs: Sequence[EpochRecordProtocol]) -> PooledTelemetryMetrics:
        """Losslessly pool a sequence of epochs using the configured IKI sample threshold."""
        return pool_epoch_metrics(
            epochs,
            iki_min_valid_samples=self._iki_min_valid_samples,
        )

    async def insert_activity_block(self, block: ActivityBlockRecordProtocol) -> int:
        """Persist a sealed activity block and return its primary key id."""
        return await self._repository.insert_activity_block(block)

    async def fetch_activity_blocks_in_range(
        self,
        start_time: float,
        end_time: float,
    ) -> list[ActivityBlockDTO]:
        """Fetch persisted activity blocks within [start_time, end_time] ordered chronologically."""
        return await self._repository.fetch_activity_blocks_in_range(start_time, end_time)

    async def fetch_recent_activity_blocks(self, limit: int = 10) -> list[ActivityBlockDTO]:
        """Fetch the most recent N sealed activity blocks ordered newest first."""
        return await self._repository.fetch_recent_activity_blocks(limit=limit)

    async def count_activity_blocks(self) -> int:
        """Return total number of persisted activity blocks."""
        return await self._repository.count_activity_blocks()
