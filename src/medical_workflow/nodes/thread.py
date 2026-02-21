"""스레드 관리 및 종료 감지 노드"""

from typing import Dict, Any

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, thread_key, safe_llm_invoke
from medical_workflow.utils.helpers import symptom_thread_key


def _ensure_thread_defaults(t: Dict[str, Any]) -> Dict[str, Any]:
    t.setdefault("events", [])
    t.setdefault("memories", [])
    t.setdefault("reflections", [])
    t.setdefault("alarm_opt_in", None)
    return t


def _promote_to_diagnosis(
    thread: Dict[str, Any],
    patient_id: str,
    diagnosis: str,
    new_key: str,
    old_key: str,
) -> None:
    """Symptom thread를 diagnosis thread로 승격.

    - thread_type, diagnosis_key, thread_id를 diagnosis 기준으로 교체
    - THREAD_STORE에서 old_key를 제거하고 new_key로 재등록
    """
    thread["thread_type"]   = "diagnosis"
    thread["diagnosis_key"] = diagnosis
    thread["thread_id"]     = f"thread_{patient_id}_{diagnosis}"  # ID도 일관성 유지
    THREAD_STORE[new_key]   = thread
    if old_key in THREAD_STORE and old_key != new_key:
        del THREAD_STORE[old_key]


def _llm_names_match(llm, name_a: str, name_b: str, node_name: str) -> bool:
    """두 진단명이 동일 질환이거나 한 쪽이 다른 쪽의 표현·상위 개념인지 LLM 판단."""
    prompt = (
        f"'{name_a}'과(와) '{name_b}'은 동일 질환이거나, "
        f"한 쪽이 다른 쪽의 다른 표현·상위 개념(예: '종양'↔'폐암')인가?\n"
        "같은 환자의 연속 진료 맥락에서 판단하라.\n"
        'JSON만 출력: {"matches": true/false}'
    )
    result, _ = safe_llm_invoke(
        llm, prompt,
        node_name=node_name,
        fallback_value=None,
        parse_json=True,
        severity="medium",
    )
    return isinstance(result, dict) and bool(result.get("matches"))


def n_is_existing(s: WFState, llm) -> WFState:
    """
    스레드 존재 여부 확인 — 4단계 탐색, 절대 새 스레드를 만들지 않는 방향 우선.

    Step 1. 동일 diagnosis_key → 즉시 재사용
    Step 2. 다른 진단명의 active diagnosis thread → LLM 매칭 후 diagnosis_key 교체
    Step 3. Active symptom thread → LLM 매칭 후 diagnosis thread로 승격
    Step 4. 위 모두 없을 때만 is_existing=False (→ n_create_thread)
    """
    patient_id = s["patient_id"]
    diagnosis  = s["diagnosis_key"]

    # ── Step 1: 동일 진단명 스레드 ─────────────────────────────────────────
    key = thread_key(patient_id, diagnosis)
    if key in THREAD_STORE:
        return {**s, "is_existing": True}

    # ── Step 2: 다른 진단명의 active diagnosis thread 탐색 ──────────────────
    # thread_type != "symptom" 로 구분 (기존 thread 호환성 포함)
    active_diag_threads = {
        k: v for k, v in THREAD_STORE.items()
        if v.get("patient_id") == patient_id
        and v.get("thread_type") != "symptom"
        and v.get("status") == "active"
    }

    if active_diag_threads:
        # LLM으로 기존 진단 thread와 매칭 시도
        for _k, thread in active_diag_threads.items():
            existing_name = thread.get("diagnosis_key", "")
            if not existing_name or existing_name == diagnosis:
                continue
            if _llm_names_match(llm, diagnosis, existing_name, "diagnosis_thread_match"):
                # 동일 질환 확인 → diagnosis_key를 기존 thread 기준으로 교체 (일관성 유지)
                return {**s, "is_existing": True, "diagnosis_key": existing_name}

        # LLM 매칭 실패해도: active diagnosis thread가 있으면 가장 최근 것 재사용
        # 절대 새 thread 생성 안 함
        latest_k      = max(active_diag_threads.keys())
        existing_name = active_diag_threads[latest_k].get("diagnosis_key", diagnosis)
        return {**s, "is_existing": True, "diagnosis_key": existing_name}

    # ── Step 3: Active symptom thread 탐색 → 진단 thread로 승격 ────────────
    symptom_threads = {
        k: v for k, v in THREAD_STORE.items()
        if v.get("patient_id") == patient_id
        and v.get("thread_type") == "symptom"
        and v.get("status") == "active"
    }

    if not symptom_threads:
        # ── Step 4: 완전 신규 ────────────────────────────────────────────────
        return {**s, "is_existing": False}

    # LLM 매칭으로 관련 symptom thread 찾기
    for sym_key, sym_thread in symptom_threads.items():
        symptoms = sym_thread.get("symptom_keys", [])
        match_prompt = (
            f"진단명 '{diagnosis}'이(가) 아래 증상들로 나타날 수 있는 질환인가?\n"
            f"증상: {symptoms}\n"
            'JSON만 출력: {"matches": true/false}'
        )
        result, _ = safe_llm_invoke(
            llm, match_prompt,
            node_name="symptom_thread_match",
            fallback_value=None,
            parse_json=True,
            severity="medium",
        )
        if isinstance(result, dict) and result.get("matches"):
            _promote_to_diagnosis(sym_thread, patient_id, diagnosis, key, sym_key)
            return {**s, "is_existing": True}

    # Fallback: 매칭 실패해도 가장 최근 symptom thread를 승격 (새 thread 생성 방지)
    latest_key    = max(symptom_threads.keys())
    latest_thread = symptom_threads[latest_key]
    _promote_to_diagnosis(latest_thread, patient_id, diagnosis, key, latest_key)
    return {**s, "is_existing": True}


def n_create_symptom_thread(s: WFState, llm) -> WFState:
    """증상 임시 스레드 생성 (진단명 미확정 방문용)"""
    patient_id      = s["patient_id"]
    symptom_summary = s.get("symptom_summary", "증상불명")
    symptom_keys    = s.get("symptom_keys") or []

    key = symptom_thread_key(patient_id, symptom_summary)

    if key not in THREAD_STORE:
        THREAD_STORE[key] = _ensure_thread_defaults({
            "thread_id":       f"thread_{patient_id}_symptom_{symptom_summary}",
            "patient_id":      patient_id,
            "thread_type":     "symptom",
            "diagnosis_key":   None,
            "symptom_keys":    symptom_keys,
            "symptom_summary": symptom_summary,
            "status":          "active",
        })

    t = THREAD_STORE[key]
    return {**s, "thread_id": t["thread_id"], "thread": t}


def n_create_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    THREAD_STORE[key] = _ensure_thread_defaults(
        {
            "thread_id":     f"thread_{s['patient_id']}_{s['diagnosis_key']}",
            "patient_id":    s["patient_id"],
            "thread_type":   "diagnosis",          # n_is_existing 탐색에 필수
            "diagnosis_key": s["diagnosis_key"],
            "status":        "active",
        }
    )
    t = THREAD_STORE[key]
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": t.get("alarm_opt_in")}


def n_load_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    t = THREAD_STORE[key]
    _ensure_thread_defaults(t)
    # state에 명시적인 값(True/False)이 있으면 유지, 없으면 thread 캐시 사용
    state_opt = s.get("alarm_opt_in")
    alarm_opt_in = state_opt if state_opt in (True, False) else t.get("alarm_opt_in")
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": alarm_opt_in}


_CLOSURE_KEYWORDS = (
    "완치", "완전관해", "관해", "완쾌", "종결",
    "치료 완료", "치료 종료", "치료완료", "치료종료",
    "추적관찰 종료", "추적 관찰 종료",
    "더 이상 치료 불필요", "재발 없음으로 종결",
    "정상 판정", "정상으로 돌아",
    "회복된 것으로", "회복되었습니다", "회복하셨",  # 회복 선언 표현
)


def n_detect_closure(s: WFState, llm) -> WFState:
    # 진단명이 없는 증상 스레드는 종료 판단 불가 → 계속 유지
    if not s.get("diagnosis_key"):
        return {**s, "should_close": False}

    # ── 규칙 기반 1차 체크: disease_status ────────────────────────────────
    # LLM 추출 시 disease_status에 종료 신호가 명시된 경우 즉시 종결 처리.
    # doctor_text LLM 판단보다 구조화된 필드를 우선한다.
    disease_status = (s.get("disease_status") or "").strip()
    if disease_status and any(kw in disease_status for kw in _CLOSURE_KEYWORDS):
        return {**s, "should_close": True}

    # ── LLM 기반 2차 체크: doctor_text ────────────────────────────────────
    diag = s.get("diagnosis_key", "")
    status_hint = f"\n현재 상태(disease_status): {disease_status}" if disease_status else ""
    prompt = f"""
이 진료 기록에서 "{diag}" 질환의 관리를 종료한다는 명확한 신호가 있는가?{status_hint}

종료 신호 예시 (이런 표현이 있으면 true):
- "완치 판정", "완전관해(CR) 확인", "완쾌", "더 이상 치료가 필요하지 않음"
- "치료를 종료합니다", "치료가 완료되었습니다"
- "추적 관찰도 종료합니다", "정기 검진도 필요 없습니다"
- "정상으로 돌아왔습니다", "재발 소견 없음으로 종결"
- "회복된 것으로 보입니다", "증상이 소실되었습니다", "다 나으셨습니다"
  → 위처럼 회복·증상 소실을 의사가 선언했다면, 뒤에 "재발 시 내원해주세요"가
    붙어 있어도 이는 일반적인 퇴원 안내이므로 should_close = true로 판단한다.

종료가 아닌 경우 (이런 표현이면 false):
- 경과 관찰, 재진 예약, 다음 치료 일정 (회복 선언 없이 추적만 언급)
- 치료 반응 확인, 용량 조절, 약 교체
- 추적관찰 예약, 정기 검사 안내

중요: "비슷한 증상이 나타나면 내원해주세요" 같은 재발 주의 문구는 퇴원 시
표준 안내 문구이며, 그 자체로는 종료를 막지 않는다. 회복·소실 선언이 함께
있으면 should_close = true로 반환한다.

종료 신호가 명확하지 않으면 반드시 false로 반환한다.
JSON만 출력:
{{"should_close": true/false, "reason": "한 줄 근거"}}

전사:
{s.get("doctor_text", "")}
"""
    fallback = {"should_close": False, "reason": "LLM 오류 — 보수적 유지"}
    out, error = safe_llm_invoke(
        llm, prompt,
        node_name="detect_closure",
        fallback_value=fallback,
        parse_json=True,
        severity="medium"
    )

    should_close = bool(out.get("should_close", False)) if isinstance(out, dict) else False

    new_state = {**s, "should_close": should_close}
    if error:
        errors = list(s.get("errors", []))
        errors.append(error)
        new_state["errors"] = errors
        warnings = list(s.get("warnings", []))
        warnings.append("ℹ️ 치료 종료 여부를 판단할 수 없어 진료를 계속합니다.")
        new_state["warnings"] = warnings

    return new_state


def n_close_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    if key in THREAD_STORE:
        THREAD_STORE[key]["status"] = "closed"
    return s
