"""Atomic, process-safe persistence for panel metadata."""

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager

from config import PANEL_DATA_DIR


METADATA_FILE = os.path.join(PANEL_DATA_DIR, 'instance_metadata.json')
LOCK_FILE = os.path.join(PANEL_DATA_DIR, 'instance_metadata.lock')
_thread_lock = threading.RLock()


def _ensure_directory():
    os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)


def _read_unlocked():
    if not os.path.exists(METADATA_FILE):
        return {}
    try:
        with open(METADATA_FILE, 'r', encoding='utf-8') as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_unlocked(metadata):
    os.makedirs(os.path.dirname(METADATA_FILE), exist_ok=True)
    directory = os.path.dirname(METADATA_FILE)
    fd, temporary = tempfile.mkstemp(prefix='.instance_metadata.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, METADATA_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def metadata_transaction():
    """Lock, load and atomically save metadata around one mutation."""
    _ensure_directory()
    with _thread_lock, open(LOCK_FILE, 'a+', encoding='utf-8') as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            metadata = _read_unlocked()
            yield metadata
        except Exception:
            raise
        else:
            _write_unlocked(metadata)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def load_metadata():
    _ensure_directory()
    with _thread_lock, open(LOCK_FILE, 'a+', encoding='utf-8') as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)
        try:
            return _read_unlocked()
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def save_metadata(metadata):
    _ensure_directory()
    with _thread_lock, open(LOCK_FILE, 'a+', encoding='utf-8') as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            _write_unlocked(metadata)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
