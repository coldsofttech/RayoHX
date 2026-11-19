"""Diagnostics: explaining failures, checking the network and streams, and safe reports."""

from rayohx.platform.diagnostics.explain import Explanation, category_of, explain
from rayohx.platform.diagnostics.network import NetworkReport, NetworkStep, probe_network
from rayohx.platform.diagnostics.registry import ReportRegistry
from rayohx.platform.diagnostics.sanitize import Sanitizer, contains_secret
from rayohx.platform.diagnostics.service import DiagnosticReport, DiagnosticsService
from rayohx.platform.diagnostics.stream import Finding, StreamReport, diagnose_stream

__all__ = [
    "DiagnosticReport",
    "DiagnosticsService",
    "Explanation",
    "Finding",
    "NetworkReport",
    "NetworkStep",
    "ReportRegistry",
    "Sanitizer",
    "StreamReport",
    "category_of",
    "contains_secret",
    "diagnose_stream",
    "explain",
    "probe_network",
]
