"""OpenTelemetry Provider initialization for metrics, traces, and logs."""

import contextlib
import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("egg.observability.otel")


class OTelTelemetryManager:
    """Manages OpenTelemetry MeterProvider, TracerProvider, and Resource lifecycle."""

    def __init__(
        self,
        *,
        service_name: str = "egg-telemetry",
        service_version: str = "0.2.0",
        otlp_endpoint: str = "http://127.0.0.1:4317",
        enable_otlp: bool = True,
    ) -> None:
        self._service_name = service_name
        self._service_version = service_version
        self._otlp_endpoint = otlp_endpoint
        self._enable_otlp = enable_otlp

        self._resource = Resource.create(
            {
                "service.name": self._service_name,
                "service.version": self._service_version,
                "host.type": "human-user",
            }
        )

        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self._logger_provider: LoggerProvider | None = None
        self._metric_reader: PeriodicExportingMetricReader | None = None
        self._span_processor: BatchSpanProcessor | None = None
        self._log_processor: BatchLogRecordProcessor | None = None
        self._logging_handler: LoggingHandler | None = None

        self._initialize()

    def _initialize(self) -> None:
        """Initialize Providers and Exporters."""
        if not self._enable_otlp:
            logger.info("OTLP export disabled by configuration; using in-memory providers.")
            self._tracer_provider = TracerProvider(resource=self._resource)
            self._meter_provider = MeterProvider(resource=self._resource)
            self._logger_provider = LoggerProvider(resource=self._resource)
            trace.set_tracer_provider(self._tracer_provider)
            metrics.set_meter_provider(self._meter_provider)
            set_logger_provider(self._logger_provider)
            return

        try:
            # Metrics
            metric_exporter = OTLPMetricExporter(endpoint=self._otlp_endpoint, insecure=True)
            self._metric_reader = PeriodicExportingMetricReader(
                metric_exporter,
                export_interval_millis=2000,
            )
            self._meter_provider = MeterProvider(
                resource=self._resource,
                metric_readers=[self._metric_reader],
            )
            metrics.set_meter_provider(self._meter_provider)

            # Traces
            span_exporter = OTLPSpanExporter(endpoint=self._otlp_endpoint, insecure=True)
            self._span_processor = BatchSpanProcessor(span_exporter)
            self._tracer_provider = TracerProvider(resource=self._resource)
            self._tracer_provider.add_span_processor(self._span_processor)
            trace.set_tracer_provider(self._tracer_provider)

            # Logs (via OTLP HTTP receiver on 4318 for robust JSON/HTTP pipeline)
            log_endpoint = self._otlp_endpoint.replace(":4317", ":4318") + "/v1/logs"
            log_exporter = OTLPLogExporter(endpoint=log_endpoint)
            self._log_processor = BatchLogRecordProcessor(log_exporter)
            self._logger_provider = LoggerProvider(resource=self._resource)
            self._logger_provider.add_log_record_processor(self._log_processor)
            set_logger_provider(self._logger_provider)

            # Attach OTel LoggingHandler to python root/sre logger
            self._logging_handler = LoggingHandler(
                level=logging.INFO,
                logger_provider=self._logger_provider,
            )
            logging.getLogger("egg.sre").addHandler(self._logging_handler)

            logger.info("OpenTelemetry OTLP exporters initialized on %s", self._otlp_endpoint)
        except Exception as ex:
            logger.warning(
                "Could not initialize OTLP gRPC exporter (%s); falling back to local providers.",
                ex,
            )
            self._tracer_provider = TracerProvider(resource=self._resource)
            self._meter_provider = MeterProvider(resource=self._resource)
            self._logger_provider = LoggerProvider(resource=self._resource)
            trace.set_tracer_provider(self._tracer_provider)
            metrics.set_meter_provider(self._meter_provider)
            set_logger_provider(self._logger_provider)

    @property
    def tracer(self) -> trace.Tracer:
        """Active OpenTelemetry Tracer."""
        return trace.get_tracer(self._service_name, self._service_version)

    @property
    def meter(self) -> metrics.Meter:
        """Active OpenTelemetry Meter."""
        return metrics.get_meter(self._service_name, self._service_version)

    def shutdown(self) -> None:
        """Flush and shutdown all OpenTelemetry SDK providers."""
        if self._logging_handler is not None:
            with contextlib.suppress(Exception):
                logging.getLogger("egg.sre").removeHandler(self._logging_handler)
        if self._tracer_provider is not None:
            with contextlib.suppress(Exception):
                self._tracer_provider.shutdown()
        if self._meter_provider is not None:
            with contextlib.suppress(Exception):
                self._meter_provider.shutdown()
        if self._logger_provider is not None:
            with contextlib.suppress(Exception):
                self._logger_provider.shutdown()
