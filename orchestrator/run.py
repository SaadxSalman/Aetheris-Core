"""Uvicorn entrypoint:  python run.py"""
from __future__ import annotations

import uvicorn

from aetheris.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "aetheris.api:app",
        host=settings.ORCHESTRATOR_HOST,
        port=settings.ORCHESTRATOR_PORT,
        reload=bool(settings.APP_DEBUG),
        log_level=settings.APP_LOG_LEVEL.lower(),
        ws="none",
    )
