"""
Centralised logger for the Streamlit app.

Usage:
    from logger import log
    log.info("Watch loaded", extra={"watch_id": "W-0042"})
    log.error("API call failed", exc_info=True)

Writes to logs/app.log with daily rotation (7-day retention).
Also echoes to stderr so `nohup` captures it in the nohup.out fallback.
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = TimedRotatingFileHandler(
    _LOG_FILE,
    when="midnight",
    backupCount=7,
    encoding="utf-8",
)
_file_handler.setFormatter(_fmt)

_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_fmt)

log = logging.getLogger("jdm_watch")
log.setLevel(logging.DEBUG)
if not log.handlers:
    log.addHandler(_file_handler)
    log.addHandler(_stream_handler)
