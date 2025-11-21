"""Service dependency factories."""
from __future__ import annotations

import logging

from docflow.core.providers.gemini import GeminiProvider

from .config import ServiceConfig


def get_provider(cfg: ServiceConfig) -> GeminiProvider:
    return GeminiProvider(project=cfg.gcp_project, location=cfg.location)


def get_logger() -> logging.Logger:
    logger = logging.getLogger("docflow.service")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
