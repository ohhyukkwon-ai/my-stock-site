from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import random

app = FastAPI()

# 템플릿 파일 폴더 설정
templates = Jinja2Templates(directory="templates")

# 투자 신호 결정 함수 (현재 랜덤)
def get_signal(ticker: str):
    responses = [
        {"action": "BUY", "msg": "강력 매수 추천! 🚀", "color": "#2ecc71"},
        {"action": "HOLD", "msg": "일단 관망하세요. ✋", "color": "#f1c40f"},
        {"action": "SELL", "msg": "지금이 매도 타이밍! 📉", "color": "#e74c3c"}
    ]
    return random.choice(responses)

# 메인 홈 페이지 (26번째 줄 수정됨)
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

# 분석 버튼 클릭 시 로직 (32번째 줄 수정됨)
@app.post("/analyze")
async def analyze(request: Request, ticker: str = Form(...)):
    result = get_signal(ticker.upper())
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "ticker": ticker.upper(), 
        "result": result
    })
