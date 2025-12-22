import yfinance as yf
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import random

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_expert_analysis(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        # 1. 기술적 분석을 위해 최근 1개월 데이터 로드
        hist = stock.history(period="1mo")
        info = stock.info
        
        if hist.empty: return None

        curr = hist['Close'].iloc[-1]
        prev = hist['Close'].iloc[-2]
        change_pct = ((curr - prev) / prev) * 100

        # 2. RSI(상대강도지수) 계산 (14일 기준)
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))

        # 3. 전문가 퀀트 스코어 계산 로직 (RSI + 변동성 반영)
        score = 50 + (change_pct * 5)
        if rsi < 30: score += 20 # 과매도 구간 가산점
        if rsi > 70: score -= 20 # 과매수 구간 감점
        score = max(0, min(100, int(score)))

        # 4. 점수별 코멘트 및 색상 설정

        if score >= 80:
            status, msg, color = "강력 매수", "차트가 예술이네요. 제 딸에게도 사주고 싶은 종목입니다! 🚀", "#2ecc71"
        elif score >= 60:
            status, msg, color = "매수 검토", "흐름이 나쁘지 않아요. 조금씩 담아볼까요? 👍", "#3498db"
        elif score >= 40:
            status, msg, color = "관망", "폭풍전야 같네요. 커피 한 잔 마시며 지켜보시죠. ✋", "#f1c40f"
        else:
            status, msg, color = "매도/회피", "지금은 소나기를 피할 때입니다. 일단 도망가세요! 📉", "#e74c3c"

        return {
            "price": round(curr, 2),
            "change": round(change_pct, 2),
            "rsi": round(rsi, 1),
            "mcap": f"{info.get('marketCap', 0) / 1e12:.2f}T", # 조 단위 시총
            "pe": info.get('trailingPE', 'N/A'),
            "score": score,
            "status": status,
            "color": color,
            "summary": info.get('longBusinessSummary', '정보 없음')[:150] + "..."
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

# 홈 페이지 (52번째 줄: Request 대문자 확인!)
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

# 분석 페이지 (POST)
@app.post("/analyze")
async def analyze(request: Request, ticker: str = Form(...)):
    ticker = ticker.upper()
    result = get_expert_analysis(ticker)
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "ticker": ticker, 
        "result": result
    })