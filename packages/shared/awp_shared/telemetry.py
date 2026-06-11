"""
OpenTelemetry setup. One helper, called once per process with a
service name, wires a tracer provider that batches spans to Jaeger over OTLP/HTTP.

Each process (API, worker) calls setup_telemetry() with its own service.name so
Jaeger shows them as distinct services in the same trace.
"""
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_initialized = False


def setup_telemetry(service_name: str) -> None:
    """Idempotent: safe to call more than once; only the first call configures."""
    global _initialized
    if _initialized:
        return

    base = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    # BatchSpanProcessor exports spans in the background so it never blocks a request.
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str = "awp"):
    return trace.get_tracer(name)
