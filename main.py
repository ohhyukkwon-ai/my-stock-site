import os
import json
import re
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Professional Myeongri-Quant Center")
templates = Jinja2Templates(directory="templates")

# =========================
# ✅ 전역 초기화
# =========================
def _must_env(key: str) -> str:
    val = os.environ.get(key, "")
    if val is None:
        val = ""
    val = val.strip()
    if not val:
        raise RuntimeError(f"{key} is missing/empty")
    return val


OPENAI_API_KEY = _must_env("OPENAI_API_KEY")
VECTOR_STORE_ID = _must_env("OPENAI_VECTOR_STORE_ID")
ASSISTANT_ID = _must_env("OPENAI_ASSISTANT_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

print("✅ OPENAI init ok")
print("VECTOR_STORE_ID =", VECTOR_STORE_ID)
print("ASSISTANT_ID =", ASSISTANT_ID)
print("API_KEY_PREFIX =", OPENAI_API_KEY[:10])
print("RAW VECTOR_STORE_ID REPR =", repr(VECTOR_STORE_ID))


# =========================
# 입력 정규화(형식 흔들림 방지)
# =========================
def normalize_user_data(user_data: Dict[str, str]) -> Dict[str, str]:
    name = (user_data.get("name") or "").strip()
    gender = (user_data.get("gender") or "").strip()
    birth_date = (user_data.get("birth_date") or "").strip()
    birth_time = (user_data.get("birth_time") or "").strip()

    if not birth_time:
        birth_time = "모름"

    return {
        "name": name,
        "gender": gender,
        "birth_date": birth_date,
        "birth_time": birth_time,
    }


# =========================
# Vector Store 상태 점검
# =========================
def verify_vector_store() -> Dict[str, Any]:
    """
    Vector Store 연결 및 파일/인덱싱 상태 점검.
    """
    try:
        vs = client.beta.vector_stores.retrieve(VECTOR_STORE_ID)
        fc = vs.file_counts
        print(f"🔍 [VS] id={VECTOR_STORE_ID} file_counts={fc}")

        total = getattr(fc, "total", 0) or 0
        completed = getattr(fc, "completed", 0) or 0
        in_progress = getattr(fc, "in_progress", 0) or 0
        failed = getattr(fc, "failed", 0) or 0

        if total == 0:
            return {"ok": False, "reason": "empty", "detail": f"Vector Store에 파일이 없습니다. total={total}"}

        # 인덱싱 중이어도 VS는 살아있음(검색 품질/성공률은 떨어질 수 있음)
        if in_progress > 0:
            return {
                "ok": True,
                "reason": "indexing",
                "detail": f"인덱싱 진행 중입니다. completed={completed}, in_progress={in_progress}, failed={failed}, total={total}",
            }

        if failed > 0 and completed == 0:
            return {
                "ok": True,
                "reason": "index_failed",
                "detail": f"인덱싱 실패 파일이 있습니다. completed={completed}, failed={failed}, total={total}",
            }

        if completed > 0:
            return {"ok": True, "reason": "ready", "detail": f"정상입니다. completed={completed}, total={total}"}

        return {
            "ok": True,
            "reason": "unknown_state",
            "detail": f"파일은 있으나 상태가 애매합니다. completed={completed}, in_progress={in_progress}, failed={failed}, total={total}",
        }

    except Exception as e:
        # 권한/프로젝트 불일치/ID 오타면 여기로 떨어짐
        print(f"❌ [VS ERROR] retrieve failed: {repr(e)}")
        return {"ok": False, "reason": "retrieve_error", "detail": repr(e)}


# =========================
# 결과 파싱 유틸
# =========================
def extract_json_from_text(text: str) -> Optional[dict]:
    """
    모델이 JSON을 포함해서 출력했을 때 최대한 안전하게 JSON만 추출.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    raw = match.group(0).strip()
    try:
        return json.loads(raw)
    except Exception:
        return None


# =========================
# ✅ 프롬프트 생성 함수 (검증용으로 웹페이지에 출력)
# =========================
def build_prompt(user_data: Dict[str, str]) -> str:
    return f"""
[역할]
너는 업로드된 PDF('Bazi.pdf')를 기반으로만 답하는 "명리 기반 투자분석가"다.
PDF에 없는 일반 상식/임의 해석/외부 지식은 배제하라. 반드시 문서의 기준/용어/규칙을 따르라.

[중요: 입력값 검증]
아래 사용자 입력을 "input_echo"에 1글자도 바꾸지 말고 그대로 넣어라.
입력값이 다르게 들어왔다면 그 즉시 "status"에 '입력값 이상'이라고 표시하고 이유를 써라.

[사용자 정보(그대로 에코할 것)]
- name: {user_data['name']}
- gender: {user_data['gender']}
- birth_date: {user_data['birth_date']}
- birth_time: {user_data['birth_time']}

[출력 목표]
먼저 "사주 기본 리포트"로 사주 전반을 정리한 뒤, 그 기반 위에서 "투자 관점 분석"을 수행하라.
최종 출력은 반드시 아래 JSON 형식으로만 출력하라.

[분석 순서]
A. 사주 기본 리포트(전반)
1) 만세력 구성: 생년월일시로 사주팔자(연/월/일/시) 구성 및 일간(Day Master) 확정.
2) 강약/균형: 오행 분포, 기세/계절(월지), 조후 관점 등 PDF에서 제시한 기준으로 강약 판단.
3) 구조/격국: PDF에서 제시된 격국(Structure)·용신/희신 판별 절차를 따라 판정.
4) 성향 요약: 십신(Ten Gods) 배치가 의미하는 기질/의사결정 성향을 PDF 근거 중심으로 요약.
5) 리스크 성향(기본): PDF에 있는 "성향→행동" 규칙을 인용해, 과열/공포/우유부단 등 심리적 패턴을 정리.

B. 투자 관점 분석(사주 기본 리포트 기반)
6) 투자 체질/스타일: A에서 확정한 용신/희신/기신과 십신 조합을 바탕으로
   - 선호 자산/국면(분산, 변동성, 현금 비중 등)을 PDF의 해석 규칙에 매핑
   - 강점(잘하는 국면)과 약점(취약 국면)을 명확히 정리
7) 3개년 투자 로드맵(문서 기반 규칙 적용)
   - 2026(병오), 2027(정미), 2028(무신) 세운을 PDF의 "운세 해석 법칙"에 대입
   - 각 연도별로: 리스크 온/오프, 포지션/현금 비중 가이드, 피해야 할 행동
   - 반드시 "왜 그런지"를 PDF의 규칙/개념을 근거로 설명

[응답 규칙]
- PDF에 없는 내용은 추론/확장하지 말 것.
- 출력은 오직 JSON 1개만. 설명 텍스트/머리말/후기 금지.

[JSON 출력 형식]
{{
  "input_echo": {{
    "name": "{user_data['name']}",
    "gender": "{user_data['gender']}",
    "birth_date": "{user_data['birth_date']}",
    "birth_time": "{user_data['birth_time']}"
  }},
  "saju_overview": "사주 기본 리포트 요약",
  "analysis": "투자 관점 분석",
  "year_1": "2026년(병오) 전략",
  "year_2": "2027년(정미) 전략",
  "year_3": "2028년(무신) 전략",
  "status": "현재 운세 기반 투자 심리/컨디션 한줄 요약",
  "color": "색상코드"
}}
""".strip()


# =========================
# ✅ 핵심 분석 함수 (인자 2개 받는 버전으로 '하나만' 존재해야 함)
# =========================
def get_pro_myeongri_analysis(user_data: dict, prompt_text: str) -> Dict[str, Any]:
    vs_check = verify_vector_store()
    if not vs_check["ok"]:
        return {
            "input_echo": user_data,
            "saju_overview": "",
            "analysis": f"PDF 문서를 읽어올 수 없습니다.\n- 사유: {vs_check['reason']}\n- 상세: {vs_check['detail']}",
            "year_1": "",
            "year_2": "",
            "year_3": "",
            "status": "지식 저장소 연결 실패",
            "color": "#e74c3c",
        }

    if vs_check["reason"] == "indexing":
        print("⚠️ Vector Store is indexing. File search may be limited.")

    try:
        thread = client.beta.threads.create(messages=[{"role": "user", "content": prompt_text}])

        # 결과 흔들림 줄이기(지원되면 적용)
        try:
            run = client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=ASSISTANT_ID,
                temperature=0.2,
            )
        except TypeError:
            run = client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=ASSISTANT_ID,
            )

        print("RUN_STATUS =", run.status)
        if getattr(run, "last_error", None):
            print("RUN_LAST_ERROR =", run.last_error)

        if run.status != "completed":
            err = getattr(run, "last_error", None)
            return {
                "input_echo": user_data,
                "saju_overview": "",
                "analysis": f"분석 실행이 완료되지 않았습니다.\n- run.status={run.status}\n- last_error={err}",
                "year_1": "",
                "year_2": "",
                "year_3": "",
                "status": "에러",
                "color": "#e74c3c",
            }

        messages = client.beta.threads.messages.list(thread_id=thread.id)
        ai_raw = messages.data[0].content[0].text.value

        parsed = extract_json_from_text(ai_raw)
        if parsed and isinstance(parsed, dict):
            return {
                "input_echo": parsed.get("input_echo", user_data),
                "saju_overview": parsed.get("saju_overview", ""),
                "analysis": parsed.get("analysis", ai_raw),
                "year_1": parsed.get("year_1", ""),
                "year_2": parsed.get("year_2", ""),
                "year_3": parsed.get("year_3", ""),
                "status": parsed.get("status", "분석 완료"),
                "color": parsed.get("color", "#3498db"),
            }

        # JSON이 안 오면 raw를 analysis에라도 넣어 표시
        return {
            "input_echo": user_data,
            "saju_overview": "",
            "analysis": ai_raw,
            "year_1": "",
            "year_2": "",
            "year_3": "",
            "status": "분석 완료(비정형)",
            "color": "#3498db",
        }

    except Exception as e:
        return {
            "input_echo": user_data,
            "saju_overview": "",
            "analysis": f"예외 발생: {repr(e)}",
            "year_1": "",
            "year_2": "",
            "year_3": "",
            "status": "에러",
            "color": "#e74c3c",
        }


# =========================
# 라우팅
# =========================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # prompt_text는 첫 진입에 없으니 None
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "result": None, "user": None, "prompt_text": None},
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    name: str = Form(...),
    birth_date: str = Form(...),
    birth_time: str = Form("모름"),
    gender: str = Form(...),
):
    user_data = normalize_user_data(
        {"name": name, "birth_date": birth_date, "birth_time": birth_time, "gender": gender}
    )

    # ✅ 폼 입력이 제대로 들어오는지 로그로 확인
    print("✅ [FORM NORMALIZED] =", user_data)

    # ✅ 프롬프트를 여기서 생성하고, 검증용으로 템플릿에 전달
    prompt_text = build_prompt(user_data)
    print("✅ [PROMPT LENGTH] =", len(prompt_text))

    result = get_pro_myeongri_analysis(user_data, prompt_text)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user_data, "result": result, "prompt_text": prompt_text},
    )
