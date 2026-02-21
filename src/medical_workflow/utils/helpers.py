"""일반 헬퍼 함수"""

import re
from datetime import datetime

# 암 병기 패턴: "1기", "2A기", "stage III", "Stage IIIb" 등
_CANCER_STAGE_RE = re.compile(
    r'\s*(?:stage\s*)?(?:[IVX]{1,4}[AB]?기?|[1-4][AB]?기)',
    re.IGNORECASE,
)


def normalize_cancer_diagnosis(name: str) -> str:
    """암 계열 진단명에서 병기(1기, 2기, stage III 등) 정보를 제거한다.

    Examples:
        "폐암 2기"         → "폐암"
        "유방암 1기"       → "유방암"
        "위암 3A기"        → "위암"
        "대장암 stage IV"  → "대장암"
    """
    if "암" not in name:
        return name
    cleaned = _CANCER_STAGE_RE.sub("", name).strip()
    return cleaned if cleaned else name


def thread_key(patient_id: str, diagnosis_key: str) -> str:
    """진단명 기반 스레드 키"""
    return f"{patient_id}::{diagnosis_key}"


def symptom_thread_key(patient_id: str, symptom_summary: str) -> str:
    """증상 기반 임시 스레드 키"""
    return f"{patient_id}::symptom::{symptom_summary}"


def now_iso() -> str:
    """현재 시각을 ISO 포맷으로 반환"""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
