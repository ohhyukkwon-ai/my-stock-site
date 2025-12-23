import os
import json
import re
import time
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Myeongri-Investment Strategy Center")
templates = Jinja2Templates(directory="templates")

# OpenAI 설정 (Render 환경변수에 OPENAI_API_KEY와 OPENAI_VECTOR_STORE_ID가 설정되어야 함)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

def get_myeongri_analysis(user_data: dict):
    if not VECTOR_STORE_ID:
        return {"status": "설정 오류", "analysis": "Vector Store ID를 확인해주세요.", "color": "#95a5a6"}

    # 명리학적 분석을 위한 프롬프트 구성
    prompt = f"""
    사용자 정보:
    - 이름: {user_data['name']}
    - 생년월일: {user_data['birth_date']}
    - 태어난 시: {user_data['birth_time']}
    - 성별: {user_data['gender']}

    요청사항:
    1. 우리 PDF 문서에 기술된 명리학적 원칙을 바탕으로 이 사용자의 사주 특징을 분석하라.
    2. 이를 반영하여 향후 3년(2026~2028년) 동안의 투자 방향을 제시하라.
    3. 반드시 아래 JSON 형식으로만 응답하라(다른 설명 금지):
    {{
        "analysis": "개인 사주 분석 요약 (2줄)",
        "year_1": "2026년 전략",
        "year_2": "2027년 전략",
        "year_3": "2028년 전략",
        "status": "종합 투자 성향",
        "color": "색상코드(#2ecc71 등)"
    }}
    """

    try:
        # 1. 임시 어시스턴트 생성 (file_search 도구 활성화)
        assistant = client.beta.assistants.create(
            name="Myeongri Analyst",
            instructions="너는 업로드된 명리학 PDF 지식을 기반으로 개인의 운세와 투자 전략을 연결하는 전문가다.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}}
        )

        # 2. 쓰레드 생성 및 메시지 전달
        thread = client.beta.threads.create(
            messages=[{"role": "user", "content": prompt}]
        )

        # 3. 실행 및 완료 대기
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            ai_raw = messages.data[0].content[0].text.value
            
            # JSON 추출 및 파싱 로직 강화
            result = {"analysis": ai_raw, "status": "분석 완료", "color": "#3498db"} # 기본값
            try:
                json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
                if json_match:
                    result.update(json.loads(json_match.group()))
            except:
                pass
            
            client.beta.assistants.delete(assistant.id)
            return result
        return {"status": "지연", "analysis": "AI 응답 지연", "color": "#e74c3c"}

    except Exception as e:
        return {"status": "에러", "analysis": str(e), "color": "#e74c3c"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request, 
    name: str = Form(...), 
    birth_date: str = Form(...), 
    birth_time: str = Form("모름"),
    gender: str = Form(...)
):
    user_data = {
        "name": name, "birth_date": birth_date, 
        "birth_time": birth_time, "gender": gender
    }
    # 폼 필드 매핑 확인: ticker 필드 없이 위 4개 데이터로 분석 진행
    result = get_myeongri_analysis(user_data)
    return templates.TemplateResponse("index.html", {
        "request": request, "user": user_data, "result": result
    })