"""Stable public interface for dashboard read models."""
from services.dashboard_service import build_dashboard_context, serialize_dashboard_context

__all__ = ["build_dashboard_context", "serialize_dashboard_context"]
