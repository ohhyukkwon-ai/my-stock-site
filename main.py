import os
import json
import re
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Professional Myeongri-Quant Center")
templates = Jinja2Templates(directory="templates")

# ⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇⬇
# ✅ 여기에 넣는다 (전역 초기화 영역)
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID", "").strip()
if not VECTOR_STORE_ID:
    raise RuntimeError("OPENAI_VECTOR_STORE_ID is missing/empty")

api_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing/empty")

client = OpenAI(api_key=api_key)

print("VECTOR_STORE_ID =", VECTOR_STORE_ID)
print("API_KEY_PREFIX =", api_key[:10])
# ⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆⬆

# OpenAI 설정 (Render 환경변수에 반드시 입력되어야 함)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

def verify_vector_store():
    if not VECTOR_STORE_ID:
        print("❌ VECTOR_STORE_ID missing")
        return False

    try:
        vs = client.beta.vector_stores.retrieve(VECTOR_STORE_ID)
        fc = vs.file_counts  # completed / in_progress / failed / total 등
        print(f"🔍 VS={VECTOR_STORE_ID} file_counts={fc}")

        # total이 0이면 진짜로 비어있음
        if getattr(fc, "total", 0) == 0:
            return False

        # in_progress가 있으면 "실패"가 아니라 "대기"로 처리하는 게 맞음
        if getattr(fc, "in_progress", 0) > 0:
            return True  # 또는 별도 상태로 반환

        # failed가 있으면 콘솔에서 파일 상태 확인 필요
        if getattr(fc, "failed", 0) > 0:
            print("⚠️ Some files failed to index")
            return True  # VS는 살아있음. 다만 파일 문제.

        return getattr(fc, "completed", 0) > 0

    except Exception as e:
        print(f"❌ Vector Store retrieve error: {repr(e)}")
        return False


def get_pro_myeongri_analysis(user_data: dict):
    # 1. 연결 검증 실행
    if not verify_vector_store():
        return {"status": "지식 저장소 연결 실패", "analysis": "PDF 문서를 읽어올 수 없습니다. Vector Store 설정을 확인하세요.", "color": "#e74c3c"}

    # 2. 명리학 전문 프레임워크를 반영한 프롬프트
    prompt = f"""
    [명리학 전문 분석 지침]
    사용자 정보: {user_data['name']}, {user_data['gender']}, 생년월일시: {user_data['birth_date']} {user_data['birth_time']}

    분석 단계:
    1. 사주팔자 도출: 생년월일시를 바탕으로 만세력을 구성하고 일간(Day Master)을 확정하라.
    2. PDF 지식 대조: 업로드된 'Bazi.pdf'에서 일간의 특성, 십신(Ten Gods)의 배치, 격국(Structure)론을 찾아내어 이 사주의 '강약'과 '용신(Useful God)'을 판별하라.
    3. 3개년 투자 로드맵: 2026(병오), 2027(정미), 2028(무신)년의 세운(Annual Luck)과 사용자의 용신/희신 관계를 PDF의 '운세 해석 법칙'에 대입하여 구체적 투자 비중을 산출하라.

    응답 규칙:
    - PDF에 없는 일반적인 내용은 배제하고, 반드시 문서 내의 특수 해석법을 인용하라.
    - 출력은 반드시 아래 JSON 형식을 유지하라:
    {{
        "analysis": "일간 및 격국 분석, 용신 판별 결과 (PDF 근거 포함)",
        "year_1": "2026년 전략",
        "year_2": "2027년 전략",
        "year_3": "2028년 전략",
        "status": "현재 운세 기반 투자 심리",
        "color": "색상코드"
    }}
    """

    try:
        assistant = client.beta.assistants.create(
            name="Pro Myeongri Analyst",
            instructions="너는 업로드된 명리학 PDF를 완벽히 이해한 전문가다. 문서의 전문 용어를 사용하여 깊이 있는 분석을 제공하라.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}}
        )

        thread = client.beta.threads.create(messages=[{"role": "user", "content": prompt}])
        run = client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant.id)

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            ai_raw = messages.data[0].content[0].text.value
            
            result = {"analysis": ai_raw, "status": "분석 완료", "color": "#3498db"}
            json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
            if json_match:
                result.update(json.loads(json_match.group()))
            
            client.beta.assistants.delete(assistant.id)
            return result
        return {"status": "시간 초과", "analysis": "분석 지연 중", "color": "#f1c40f"}

    except Exception as e:
        return {"status": "에러", "analysis": str(e), "color": "#e74c3c"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # 메인 페이지 접속 시 실행되는 부분 (Not Found 해결)
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request, 
    name: str = Form(...), 
    birth_date: str = Form(...), 
    birth_time: str = Form("모름"),
    gender: str = Form(...)
):
    user_data = {"name": name, "birth_date": birth_date, "birth_time": birth_time, "gender": gender}
    result = get_pro_myeongri_analysis(user_data)
    return templates.TemplateResponse("index.html", {"request": request, "user": user_data, "result": result})