import os
import json
import re
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Pure AI Quant Strategy Center")
templates = Jinja2Templates(directory="templates")

# OpenAI 설정
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

def get_ai_analysis(ticker: str):
    if not VECTOR_STORE_ID:
        return {"score": 0, "status": "설정 오류", "msg": "Vector Store ID를 확인해주세요.", "color": "#95a5a6"}

    prompt = f"""
    티커: {ticker}
    요청: 업로드된 퀀트 투자 전략 PDF를 기반으로 이 종목의 매력도를 분석하라.
    출력 형식(JSON): 
    {{
        "score": 점수(0-100),
        "status": "상태(긍정/주의/관망)",
        "msg": "전략적 조언(3문장 이내)",
        "color": "색상코드(#2ecc71/#f1c40f/#e74c3c)"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 퀀트 전략 PDF 기반 주식 분석 전문가다."},
                {"role": "user", "content": prompt}
            ],
            tools=[{"type": "file_search"}]
        )
        
        # JSON 응답 파싱
        ai_raw = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("Invalid AI Response")

    except Exception as e:
        return {
            "score": 0, "status": "분석 지연", "color": "#e74c3c",
            "msg": f"분석 중 오류 발생: {str(e)}"
        }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, ticker: str = Form(...)):
    ticker = ticker.upper().strip()
    result = get_ai_analysis(ticker)
    return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "result": result})