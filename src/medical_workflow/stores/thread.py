"""스레드 저장소 관리"""

from typing import Dict, Any, Optional
from medical_workflow.utils import thread_key


THREAD_STORE: Dict[str, Dict[str, Any]] = {}


def ensure_thread_defaults(t: Dict[str, Any]) -> Dict[str, Any]:
    """스레드 기본값 보장"""
    t.setdefault("events", [])
    t.setdefault("memories", [])
    t.setdefault("reflections", [])
    t.setdefault("alarm_opt_in", None)
    return t


def get_thread(patient_id: str, diagnosis_key: str) -> Optional[Dict[str, Any]]:
    """스레드 조회"""
    key = thread_key(patient_id, diagnosis_key)
    return THREAD_STORE.get(key)


def save_thread(patient_id: str, diagnosis_key: str, thread: Dict[str, Any]) -> None:
    """스레드 저장"""
    key = thread_key(patient_id, diagnosis_key)
    THREAD_STORE[key] = ensure_thread_defaults(thread)
