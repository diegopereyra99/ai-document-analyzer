"""Service configuration (environment-backed)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ServiceConfig:
    default_model: str
    gcp_project: Optional[str]
    location: str
    pubsub_topic_results: Optional[str]
    default_temperature: float


def load_service_config() -> ServiceConfig:
    return ServiceConfig(
        default_model=os.environ.get("DOCFLOW_DEFAULT_MODEL", "gemini-2.5-flash"),
        gcp_project=os.environ.get("DOCFLOW_GCP_PROJECT"),
        location=os.environ.get("DOCFLOW_LOCATION", "us-central1"),
        pubsub_topic_results=os.environ.get("DOCFLOW_PUBSUB_TOPIC_RESULTS"),
        default_temperature=float(os.environ.get("DOCFLOW_DEFAULT_TEMPERATURE", "0.0")),
    )
