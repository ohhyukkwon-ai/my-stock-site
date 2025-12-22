import yfinance as yf
import pandas as pd
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_enhanced_analysis(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        # 기술적 지표를 위해 1개월치 데이터 로드
        hist = stock.history(period="1mo")
        info = stock.info # 기업 기본 정보
        
        if hist.empty: return None

        curr = hist['Close'].iloc[-1]
        prev = hist['Close'].iloc[-2]
        change_pct = ((curr - prev) / prev) * 100

        # 1. RSI 계산 (간이형)
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))

        # 2. 이동평균선 확인
        ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        trend = "상승세" if ma5 > ma20 else "하락세"

        # 3. 퀀트 스코어 로직 강화
        score = 50 + (change_pct * 5) + (10 if rsi < 30 else -10 if rsi > 70 else 0)
        score = max(0, min(100, int(score)))

        return {
            "price": round(curr, 2),
            "change": round(change_pct, 2),
            "rsi": round(rsi, 1),
            "trend": trend,
            "mcap": f"{info.get('marketCap', 0) / 1e12:.2f}T", # 조 단위 시총
            "pe": info.get('trailingPE', 'N/A'),
            "score": score,
            "summary": info.get('longBusinessSummary', '')[:200] + "..." # 기업 한줄 소개
        }
    except:
        return None

@app.get("/")
async def home(request: request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze")
async def analyze(request: request, ticker: str = Form(...)):
    ticker = ticker.upper()
    result = get_enhanced_analysis(ticker)
    return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "result": result})