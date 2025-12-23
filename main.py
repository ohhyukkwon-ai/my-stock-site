import os
import time
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Professional AI Quant Dashboard")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

def get_ai_analysis(ticker: str):
    if not VECTOR_STORE_ID:
        return {"score": 0, "status": "설정 오류", "msg": "Vector Store ID가 없습니다.", "color": "#95a5a6"}

    try:
        # 1. 임시 어시스턴트 생성 (RAG 기능 활성화)
        assistant = client.beta.assistants.create(
            name="Quant Analyst",
            instructions="너는 업로드된 PDF 투자 전략을 기반으로 종목을 분석하는 전문가다.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}}
        )

        # 2. 쓰레드 생성 및 메시지 전달
        thread = client.beta.threads.create(
            messages=[{
                "role": "user",
                "content": f"{ticker} 종목에 대해 우리 PDF 전략 문서의 관점으로 분석해줘. 점수(0-100), 상태, 조언을 포함한 JSON 형식으로 답해줘."
            }]
        )

        # 3. 실행 및 완료 대기 (poll)
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            ai_raw = messages.data[0].content[0].text.value
            
            # JSON 파싱 로직
            import json, re
            json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
            result = json.loads(json_match.group()) if json_match else {}
            
            # 임시 어시스턴트 삭제 (정리)
            client.beta.assistants.delete(assistant.id)
            
            return result
        else:
            return {"score": 0, "status": "분석 실패", "msg": "AI가 응답을 생성하지 못했습니다.", "color": "#e74c3c"}

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