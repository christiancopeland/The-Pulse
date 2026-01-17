"""
Centralized logging configuration for The Pulse.

Enhanced logging with:
- Session-based timestamped log files for debugging
- Rotating log files for long-term storage
- Function names and line numbers in output
- Separate console/file log levels
- Session start/end banners

Updated 2026-01-05: Enhanced with session-based logging from workshop-claude-migration.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from typing import Optional

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Rotating log file paths (persistent across sessions)
MAIN_LOG_FILE = LOG_DIR / "pulse.log"
ERROR_LOG_FILE = LOG_DIR / "pulse_errors.log"
DEBUG_LOG_FILE = LOG_DIR / "pulse_debug.log"

# Enhanced log format with function name
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
LOG_FORMAT_SIMPLE = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
TIME_FORMAT = "%H:%M:%S"

# File size limits for rotating handlers
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
BACKUP_COUNT = 5  # Keep 5 backup files

# Module-level state
_initialized = False
_session_log_file: Optional[Path] = None
_root_logger: Optional[logging.Logger] = None


def setup_logging(
    level: int = logging.DEBUG,
    console_level: int = logging.WARNING,
    file_level: int = logging.DEBUG,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_session_log: bool = True,
) -> logging.Logger:
    """
    Configure application-wide logging with console and file handlers.

    Args:
        level: Root logger level
        console_level: Console handler level (default WARNING to reduce noise)
        file_level: File handler level
        enable_console: Whether to log to console
        enable_file: Whether to log to rotating files
        enable_session_log: Whether to create session-specific timestamped log

    Returns:
        The root logger instance
    """
    global _session_log_file, _root_logger, _initialized

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    simple_formatter = logging.Formatter(LOG_FORMAT_SIMPLE, datefmt=DATE_FORMAT)
    console_formatter = logging.Formatter(
        "%(levelname)-8s | %(name)s | %(message)s"
    )

    if enable_console:
        # Console handler - warnings and errors only by default
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    if enable_file:
        # Main rotating file handler (INFO and above)
        main_handler = RotatingFileHandler(
            MAIN_LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        main_handler.setLevel(logging.INFO)
        main_handler.setFormatter(simple_formatter)
        root_logger.addHandler(main_handler)

        # Debug file handler (all levels including DEBUG)
        debug_handler = RotatingFileHandler(
            DEBUG_LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(debug_handler)

        # Error file handler (ERROR and CRITICAL only)
        error_handler = RotatingFileHandler(
            ERROR_LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(error_handler)

    if enable_session_log:
        # Session-specific log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _session_log_file = LOG_DIR / f"session_{timestamp}.log"

        session_handler = logging.FileHandler(
            _session_log_file,
            encoding="utf-8"
        )
        session_handler.setLevel(logging.DEBUG)
        session_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(session_handler)

    # Store reference
    _root_logger = root_logger
    _initialized = True

    # Log session startup banner
    _log_session_banner(root_logger, "START")

    return root_logger


def _log_session_banner(logger: logging.Logger, event: str = "START"):
    """Log a session start/end banner for easy identification in logs."""
    banner_char = "=" if event == "START" else "-"
    banner = banner_char * 70

    logger.info(banner)
    logger.info(f"THE PULSE - Session {event}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info(f"Log directory: {LOG_DIR}")
    if _session_log_file:
        logger.info(f"Session log: {_session_log_file.name}")
    logger.info(banner)


def shutdown_logging():
    """Gracefully shutdown logging with end banner."""
    if _root_logger:
        _log_session_banner(_root_logger, "END")
        logging.shutdown()


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Automatically initializes logging if not already done.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    if not _initialized:
        init_logging()
    return logging.getLogger(name)


def get_session_log_file() -> Optional[Path]:
    """Get the path to the current session's log file."""
    return _session_log_file


def init_logging(
    console_level: int = logging.WARNING,
    verbose: bool = False
):
    """
    Initialize logging if not already done.

    Args:
        console_level: Console log level (default WARNING)
        verbose: If True, set console to INFO level
    """
    global _initialized
    if not _initialized:
        if verbose:
            console_level = logging.INFO
        setup_logging(console_level=console_level)
        _initialized = True


def set_console_level(level: int):
    """
    Change console logging level at runtime.

    Args:
        level: New logging level (e.g., logging.DEBUG, logging.INFO)
    """
    if _root_logger:
        for handler in _root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                handler.setLevel(level)
                _root_logger.info(f"Console log level changed to {logging.getLevelName(level)}")
                break


def enable_verbose():
    """Enable verbose console logging (INFO level)."""
    set_console_level(logging.INFO)


def enable_debug():
    """Enable debug console logging (DEBUG level)."""
    set_console_level(logging.DEBUG)


def enable_quiet():
    """Enable quiet console logging (WARNING level only)."""
    set_console_level(logging.WARNING)


# Convenience function for quick debug logging
def log_debug(message: str, logger_name: str = "pulse"):
    """Quick debug log without getting a logger first."""
    get_logger(logger_name).debug(message)


def log_info(message: str, logger_name: str = "pulse"):
    """Quick info log without getting a logger first."""
    get_logger(logger_name).info(message)


def log_warning(message: str, logger_name: str = "pulse"):
    """Quick warning log without getting a logger first."""
    get_logger(logger_name).warning(message)


def log_error(message: str, logger_name: str = "pulse", exc_info: bool = False):
    """Quick error log without getting a logger first."""
    get_logger(logger_name).error(message, exc_info=exc_info)
