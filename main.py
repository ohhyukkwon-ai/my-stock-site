from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import yfinance as yf
import random

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_expert_logic(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        # 최근 5일간의 데이터를 가져와서 흐름 분석
        hist = stock.history(period="5d")
        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        # 재미 요소: 퀀트 스코어 (0~100점) 계산
        # 전일 대비 상승했으면 기본 점수 부여 + 랜덤 변동성 추가
        score = 50 + (change_pct * 10) + random.randint(-5, 5)
        score = max(0, min(100, int(score)))

        # 점수에 따른 전문가 코멘트
        if score >= 80:
            status, msg, color = "강력 매수", "차트가 예술이네요. 제 딸에게도 사주고 싶은 종목입니다! 🚀", "#2ecc71"
        elif score >= 60:
            status, msg, color = "매수 검토", "흐름이 나쁘지 않아요. 조금씩 담아볼까요? 👍", "#3498db"
        elif score >= 40:
            status, msg, color = "관망", "폭풍전야 같네요. 커피 한 잔 마시며 지켜보시죠. ✋", "#f1c40f"
        else:
            status, msg, color = "매도/회피", "지금은 소나기를 피할 때입니다. 일단 도망가세요! 📉", "#e74c3c"

        return {
            "price": round(current_price, 2),
            "change": round(change_pct, 2),
            "score": score,
            "status": status,
            "msg": msg,
            "color": color
        }
    except:
        return None

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze")
async def analyze(request: Request, ticker: str = Form(...)):
    ticker = ticker.upper()
    data = get_expert_logic(ticker)
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "ticker": ticker, 
        "result": data
    })