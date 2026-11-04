"""30-second epoch buffer, periodic scheduler, and 60s/90s activity block chunker."""

from app.engine.buffer import EpochBuffer
from app.engine.chunker import ActivityBlockChunker, BlockSealedCallback, is_zero_input_epoch
from app.engine.orchestrator import EngineOrchestrator
from app.engine.protocols import (
    DEFAULT_HYSTERESIS_SEAL_EPOCHS,
    DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS,
    DEFAULT_SRE_CRITICAL_THRESHOLD,
    DEFAULT_SRE_WARNING_THRESHOLD,
    ActivityBlockPersistenceProtocol,
    BlockEvaluatorProtocol,
    EngineDimensionEvalProtocol,
    EnginePooledMetricsProtocol,
    EpochPersistenceProtocol,
    EpochSnapshot,
    InputLifecycleProtocol,
    SealedActivityBlock,
    SyntheticBurstSourceProtocol,
    WindowSourceProtocol,
)
from app.engine.scheduler import EpochFlushCallback, EpochScheduler, SchedulerDiagnostics
from app.engine.sre import (
    DEFAULT_DIMENSION_WEIGHTS,
    GOLDEN_SIGNAL_LABELS,
    SREHealthReport,
    SREObservabilityRecorder,
    evaluate_sre_health,
)

__all__ = [
    "ActivityBlockChunker",
    "ActivityBlockPersistenceProtocol",
    "BlockEvaluatorProtocol",
    "BlockSealedCallback",
    "DEFAULT_DIMENSION_WEIGHTS",
    "DEFAULT_HYSTERESIS_SEAL_EPOCHS",
    "DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS",
    "DEFAULT_SRE_CRITICAL_THRESHOLD",
    "DEFAULT_SRE_WARNING_THRESHOLD",
    "EngineDimensionEvalProtocol",
    "EngineOrchestrator",
    "EnginePooledMetricsProtocol",
    "EpochBuffer",
    "EpochFlushCallback",
    "EpochPersistenceProtocol",
    "EpochScheduler",
    "EpochSnapshot",
    "GOLDEN_SIGNAL_LABELS",
    "InputLifecycleProtocol",
    "SREHealthReport",
    "SREObservabilityRecorder",
    "SchedulerDiagnostics",
    "SealedActivityBlock",
    "SyntheticBurstSourceProtocol",
    "WindowSourceProtocol",
    "evaluate_sre_health",
    "is_zero_input_epoch",
]
