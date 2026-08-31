"""In-process daily expiry scheduler for local Qinglong containers.

The worker deliberately has no remote-server code path. It only reads the
local Docker daemon and the local metadata file, so adding a remote server to
the panel cannot make it eligible for automatic stopping.
"""

import logging
import os
import threading
import time
from datetime import datetime

from docker_manager import list_instances, stop_instance
from expiry_rules import LOCAL_TZ, is_due, local_today, parse_date
from metadata_store import load_metadata, metadata_transaction


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    LOGGER.addHandler(_log_handler)
LOGGER.propagate = False


def _bounded_env_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        LOGGER.warning('%s is invalid; using %d', name, default)
        return default
    if not minimum <= value <= maximum:
        LOGGER.warning('%s is outside %d-%d; using %d', name, minimum, maximum, default)
        return default
    return value


CHECK_HOUR = _bounded_env_int('EXPIRY_CHECK_HOUR', 0, 0, 23)
CHECK_MINUTE = _bounded_env_int('EXPIRY_CHECK_MINUTE', 5, 0, 59)
CHECK_INTERVAL_SECONDS = _bounded_env_int('EXPIRY_CHECK_INTERVAL', 30, 10, 3600)
_worker_thread = None
_worker_lock = threading.Lock()
_last_run_date = None


def _eligible(metadata, instance, today):
    if instance.get('status') != 'running':
        return False
    item = metadata.get(f"local:{instance['id']}", {})
    try:
        return is_due(item.get('end_date'), today=today)
    except ValueError:
        return False


def run_expiry_check(now=None, dry_run=False):
    """Stop due local instances and return an auditable result list.

    ``dry_run`` performs the same eligibility checks but does not call Docker.
    The function is intentionally synchronous so it can be covered with a
    fake Docker manager in tests.
    """
    today = local_today(now)
    metadata = load_metadata()
    instances = list_instances()
    due = [instance for instance in instances if _eligible(metadata, instance, today)]
    results = []

    for instance in due:
        num = int(instance['id'])
        key = f'local:{num}'
        result = {'server_id': 'local', 'instance_id': num, 'action': 'stop', 'status': 'planned'}
        if dry_run:
            results.append(result)
            continue

        # Keep the metadata lock from the final date check through docker stop.
        # A concurrent renewal waits briefly instead of being stopped afterward.
        with metadata_transaction() as current:
            item = current.get(key, {})
            try:
                due_now = is_due(item.get('end_date'), today=today)
            except ValueError:
                due_now = False
            if not due_now:
                result['status'] = 'skipped_changed'
                results.append(result)
                continue
            result['end_date'] = item.get('end_date')
            try:
                stop_instance(num)
            except Exception as exc:
                result['status'] = 'failed'
                result['error'] = str(exc)
                item['expiry_state'] = 'failed'
                item['last_expiry_error'] = str(exc)
                item['last_expiry_action_at'] = datetime.now(LOCAL_TZ).isoformat()
            else:
                result['status'] = 'stopped'
                item['expiry_state'] = 'stopped'
                item['stopped_by_expiry'] = True
                item['last_expiry_error'] = ''
                item['last_expiry_action_at'] = datetime.now(LOCAL_TZ).isoformat()
                item['expiry_stopped_for'] = item.get('end_date', '')
        results.append(result)

    LOGGER.info(
        'expiry check date=%s local_instances=%d due=%d dry_run=%s results=%s',
        today.isoformat(),
        len(instances),
        len(due),
        dry_run,
        results,
    )
    return results


def _should_run(now):
    local_date = local_today(now)
    scheduled = now.hour > CHECK_HOUR or (now.hour == CHECK_HOUR and now.minute >= CHECK_MINUTE)
    return scheduled and _last_run_date != local_date


def _worker_loop():
    global _last_run_date
    while True:
        now = datetime.now(LOCAL_TZ)
        if _should_run(now):
            try:
                run_expiry_check(now=now)
            except Exception:
                LOGGER.exception('daily expiry check failed')
            else:
                _last_run_date = local_today(now)
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_expiry_scheduler():
    """Start exactly one daemon thread in the ql_manager process."""
    global _worker_thread
    if os.environ.get('EXPIRY_SCHEDULER_ENABLED', 'true').lower() in ('0', 'false', 'no'):
        LOGGER.info('expiry scheduler disabled by environment')
        return None
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return _worker_thread
        _worker_thread = threading.Thread(target=_worker_loop, name='expiry-scheduler', daemon=True)
        _worker_thread.start()
        LOGGER.info('expiry scheduler started; daily check at %02d:%02d Asia/Shanghai', CHECK_HOUR, CHECK_MINUTE)
        return _worker_thread
