import os
import json
import re
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Professional AI Quant Dashboard")
templates = Jinja2Templates(directory="templates")

# OpenAI 설정 (Render 환경변수에 반드시 입력되어야 함)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

def get_ai_analysis(ticker: str):
    if not VECTOR_STORE_ID:
        return {"score": 0, "status": "설정 오류", "msg": "Vector Store ID가 설정되지 않았습니다.", "color": "#95a5a6"}

    try:
        # 1. 임시 어시스턴트 생성 (매 요청마다 최신 PDF 지식 검색)
        assistant = client.beta.assistants.create(
            name="Quant Analyst",
            instructions="너는 퀀트 투자 전문가다. 반드시 JSON 형식으로만 답하라.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}}
        )

        # 2. 쓰레드 생성 및 분석 요청
        thread = client.beta.threads.create(
            messages=[{
                "role": "user",
                "content": f"티커 {ticker}에 대해 우리 PDF 전략을 기반으로 분석해줘. 결과는 반드시 이 JSON 형식으로만 줘: {{\"score\": 85, \"status\": \"긍정\", \"msg\": \"조언 내용\", \"color\": \"#2ecc71\"}}"
            }]
        )

        # 3. 실행 및 완료 대기
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            ai_raw = messages.data[0].content[0].text.value
            
            # --- 강력한 JSON 추출 로직 ---
            result = {"score": 50, "status": "분석 완료", "color": "#3498db", "msg": ai_raw} # 기본값
            try:
                # 텍스트 중간에 섞인 { } 형태를 찾아냄
                json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    result.update(parsed) # 성공 시 AI가 준 값으로 업데이트
            except:
                pass # 파싱 실패 시 원문 텍스트를 msg에 담은 기본값 사용
            
            client.beta.assistants.delete(assistant.id) # 정리
            return result
            
        return {"score": 0, "status": "지연", "msg": "AI 응답 시간이 초과되었습니다.", "color": "#e74c3c"}

    except Exception as e:
        return {"score": 0, "status": "에러 발생", "msg": str(e), "color": "#e74c3c"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, ticker: str = Form(...)):
    ticker = ticker.upper().strip()
    result = get_ai_analysis(ticker)
    return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "result": result})