import threading
from app.batch import run_all

_lock = threading.Lock()
_state = {"running": False, "last_result": None, "last_error": None}


def get_state():
    return dict(_state)


def _worker():
    try:
        code = run_all()
        _state["last_result"] = code
        _state["last_error"] = None
    except Exception as exc:
        _state["last_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _state["running"] = False
        _lock.release()


def start_collection() -> bool:
    if not _lock.acquire(blocking=False):
        return False
    _state["running"] = True
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return True
