"""Logger configuration for VitaSlice/ALM project.

Asynchronous logging version:
- Main threads enqueue log records quickly
- A dedicated background thread writes to file/console
"""

from __future__ import annotations

import atexit
import logging
import queue
import sys
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

__all__ = [
    "setup_logging",
    "update_log_file_dir",
    "install_qt_message_handler",
    "install_excepthook",
    "shutdown_logging",
]

_listener: QueueListener | None = None
_log_queue: queue.Queue | None = None


def _build_file_handler(logfile: Path, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        logfile,
        maxBytes=10_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    return handler


def _build_console_handler(level: int) -> logging.StreamHandler:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        fmt="%(levelname)s: %(message)s"
    ))
    return handler


def _start_listener(logger: logging.Logger, handlers: list[logging.Handler]) -> None:
    global _listener, _log_queue

    _log_queue = queue.Queue(-1)
    queue_handler = QueueHandler(_log_queue)

    # Remove handlers antigos
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    # O logger da app só envia para a fila
    logger.addHandler(queue_handler)

    # Thread em background faz a escrita real
    _listener = QueueListener(_log_queue, *handlers, respect_handler_level=True)
    _listener.start()


def shutdown_logging() -> None:
    global _listener
    if _listener is not None:
        try:
            _listener.stop()
        except Exception:
            pass
        _listener = None


def setup_logging(
    app_name: str = "VitaSlice",
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Configure asynchronous logging for console output and rotating log file.
    If log_dir is None, default path is:
        ~/ALM_logs/<app_name>
    Returns the main logger ('ALM').
    """
    logger = logging.getLogger("ALM")
    logger.setLevel(level)
    logger.propagate = False

    # Evitar reconfiguração duplicada
    if getattr(logger, "_alm_async_configured", False):
        return logger

    base = Path.home() / "ALM_logs" / app_name if log_dir is None else Path(log_dir)
    base.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = base / f"{app_name}_{ts}.log"

    file_handler = _build_file_handler(logfile, level)
    console_handler = _build_console_handler(level)

    _start_listener(logger, [file_handler, console_handler])

    # Reduzir ruído de libs externas
    logging.getLogger("napari").setLevel(logging.WARNING)
    logging.getLogger("vispy").setLevel(logging.WARNING)

    logger._alm_async_configured = True
    logger.info(f"Async logging started. File: {logfile}")

    atexit.register(shutdown_logging)
    return logger


def update_log_file_dir(logger: logging.Logger, new_dir: Path) -> None:
    """
    Switch the file handler directory to `new_dir`, creating a new log file.
    Keeps async logging enabled.
    """
    global _listener

    new_dir = Path(new_dir)
    new_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = new_dir / f"VitaSlice_{ts}.log"

    # Parar listener actual
    shutdown_logging()

    # Recriar handlers
    file_handler = _build_file_handler(logfile, logger.level)
    console_handler = _build_console_handler(logger.level)

    _start_listener(logger, [file_handler, console_handler])
    logger.info(f"Log directory updated to: {logfile.parent}")


def install_qt_message_handler(logger: logging.Logger) -> None:
    """Install a Qt message handler that forwards Qt messages to the logger."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        logger.debug("PySide6 is not available. Qt message handler was not installed.")
        return

    def _qt_handler(mode, context, message):
        if mode == QtMsgType.QtDebugMsg:
            logger.debug(message)
        elif mode == QtMsgType.QtInfoMsg:
            logger.info(message)
        elif mode == QtMsgType.QtWarningMsg:
            logger.warning(message)
        elif mode == QtMsgType.QtCriticalMsg:
            logger.error(message)
        elif mode == QtMsgType.QtFatalMsg:
            logger.critical(message)

    qInstallMessageHandler(_qt_handler)


def install_excepthook(logger: logging.Logger) -> None:
    """Install a global exception hook to log uncaught exceptions and show a QMessageBox."""
    def _hook(exctype, value, tb):
        logger.exception("Unhandled exception", exc_info=(exctype, value, tb))
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Unexpected error", f"{exctype.__name__}: {value}")
        except Exception:
            pass

    sys.excepthook = _hook