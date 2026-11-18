"""OpenTelemetry Provider initialization for metrics."""

import contextlib
import logging

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger("egg.observability.otel")


class OTelTelemetryManager:
    """Manages OpenTelemetry MeterProvider and Resource lifecycle."""

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

        self._meter_provider: MeterProvider | None = None
        self._metric_reader: PeriodicExportingMetricReader | None = None

        self._initialize()

    def _initialize(self) -> None:
        if not self._enable_otlp:
            logger.info("OTLP export disabled by configuration; using in-memory provider.")
            self._meter_provider = MeterProvider(resource=self._resource)
            metrics.set_meter_provider(self._meter_provider)
            return

        try:
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
            logger.info("OpenTelemetry OTLP metric exporter initialized on %s", self._otlp_endpoint)
        except Exception as ex:
            logger.warning(
                "Could not initialize OTLP gRPC metric exporter (%s); using local provider.",
                ex,
            )
            self._meter_provider = MeterProvider(resource=self._resource)
            metrics.set_meter_provider(self._meter_provider)

    @property
    def meter(self) -> metrics.Meter:
        """Active OpenTelemetry Meter."""
        if self._meter_provider is not None:
            return self._meter_provider.get_meter(self._service_name, self._service_version)
        return metrics.get_meter(self._service_name, self._service_version)

    def shutdown(self) -> None:
        """Flush and shutdown OpenTelemetry MeterProvider."""
        if self._meter_provider is not None:
            with contextlib.suppress(Exception):
                self._meter_provider.shutdown()
