from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import random

app = FastAPI()

# 템플릿 파일이 들어있는 폴더 설정
templates = Jinja2Templates(directory="templates")

# 투자 신호를 결정하는 함수 (현재는 랜덤)
def get_signal(ticker: str):
    responses = [
        {"action": "BUY", "msg": "강력 매수 추천! 🚀", "color": "#2ecc71"},
        {"action": "HOLD", "msg": "일단 관망하세요. ✋", "color": "#f1c40f"},
        {"action": "SELL", "msg": "지금이 매도 타이밍! 📉", "color": "#e74c3c"}
    ]
    return random.choice(responses)

# 메인 페이지 (접속 시 처음 보이는 화면)
@app.get("/")
async def home(request: request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

# 분석 버튼을 눌렀을 때 작동하는 로직
@app.post("/analyze")
async def analyze(request: request, ticker: str = Form(...)):
    # 입력받은 티커를 대문자로 변환하여 신호 생성
    result = get_signal(ticker.upper())
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "ticker": ticker.upper(), 
        "result": result
    })
