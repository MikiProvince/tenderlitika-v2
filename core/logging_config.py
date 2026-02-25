from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

_REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def bind_request_id(request_id: str) -> contextvars.Token:
    return _REQUEST_ID_CTX.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    _REQUEST_ID_CTX.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _REQUEST_ID_CTX.get("-")
        return True


_RESERVED_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", _REQUEST_ID_CTX.get("-")),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key in payload:
                continue
            try:
                json.dumps({key: value})
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def _is_true(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_level(value: str | None) -> str:
    level = (value or "INFO").strip().upper()
    if level not in logging._nameToLevel:
        return "INFO"
    return level


def setup_logging() -> None:
    level_name = _normalize_level(os.getenv("LOG_LEVEL"))
    log_json = _is_true(os.getenv("LOG_JSON"))
    log_file = (os.getenv("LOG_FILE") or "").strip()
    uvicorn_access = _is_true(os.getenv("LOG_UVICORN_ACCESS"))

    root = logging.getLogger()
    root.setLevel(level_name)
    root.handlers.clear()

    formatter: logging.Formatter
    if log_json:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | req=%(request_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    context_filter = ContextFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level_name)
    console.setFormatter(formatter)
    console.addFilter(context_filter)
    root.addHandler(console)

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level_name)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        root.addHandler(file_handler)

    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level_name)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = True
    access_logger.setLevel(level_name if uvicorn_access else "WARNING")

    logging.captureWarnings(True)
