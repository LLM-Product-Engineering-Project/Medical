"""
하위 호환성 유지를 위한 래퍼
새 코드는 medical_workflow.stores.* 및 medical_workflow.utils.* 를 직접 import 하세요
"""

# 저장소는 stores 패키지에서 import
from medical_workflow.stores.thread import THREAD_STORE, get_thread, ensure_thread_defaults
from medical_workflow.stores.visit import VISIT_STORE, upsert_visit_record

# 유틸리티는 utils 패키지에서 import
from medical_workflow.utils import (
    safe_llm_invoke,
    parse_json_safely,
    thread_key,
    now_iso,
)

# 하위 호환성을 위한 재export
__all__ = [
    "THREAD_STORE",
    "VISIT_STORE",
    "get_thread",
    "ensure_thread_defaults",
    "upsert_visit_record",
    "thread_key",
    "now_iso",
    "parse_json_safely",
    "safe_llm_invoke",
]
