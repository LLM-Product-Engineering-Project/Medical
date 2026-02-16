"""일반 헬퍼 함수"""

from datetime import datetime


def thread_key(patient_id: str, diagnosis_key: str) -> str:
    """스레드 저장소 키 생성"""
    return f"{patient_id}::{diagnosis_key}"


def now_iso() -> str:
    """현재 시각을 ISO 포맷으로 반환"""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
