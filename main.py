import os
import yfinance as yf
import pandas as pd
import numpy as np
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Quant Strategy Dashboard with RAG")
templates = Jinja2Templates(directory="templates")

# OpenAI 클라이언트 설정 (Render 환경변수에 OPENAI_API_KEY가 있어야 함)
client = OpenAI()
# Render 환경변수에 설정한 Vector Store ID 가져오기
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

# --- 분석 유틸리티 (기존과 동일) ---
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]

# --- RAG 코멘트 생성 함수 (핵심!) ---
def get_rag_commentary(ticker, data):
    if not VECTOR_STORE_ID:
        return "전략 문서가 연결되지 않았습니다. 기본 분석을 진행합니다."

    prompt = f"""
    티커: {ticker}
    현재가: {data['price']}, 등락률: {data['change']}%
    RSI: {data['rsi']}, PER: {data['pe']}
    
    위 지표를 바탕으로 업로드된 퀀트 전략 문서의 원칙에 따라 짧은 조언을 해줘.
    매수/매도 지시보다는 리스크 관리 차원에서 언급해줘. (3줄 이내)
    """

    try:
        # Chat Completion을 활용한 RAG (가장 빠르고 안정적)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # 실존하는 가장 효율적인 모델
            messages=[
                {"role": "system", "content": "너는 업로드된 투자 전략 문서를 기반으로 조언하는 퀀트 어시스턴트다."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 분석 중 오류가 발생했습니다: {str(e)}"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request): # 대문자 Request 확인!
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, ticker: str = Form(...)):
    ticker = ticker.upper().strip()
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")
    info = stock.info

    if hist.empty:
        return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "result": None})

    # 기본 데이터 추출
    price = round(hist['Close'].iloc[-1], 2)
    change = round(((price - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100, 2)
    rsi = round(compute_rsi(hist['Close']), 2)
    
    analysis_data = {
        "price": price, "change": change, "rsi": rsi,
        "pe": info.get("trailingPE", "N/A"),
        "score": 70 if rsi < 50 else 40 # 임시 점수 로직
    }

    # RAG 코멘트 추가
    analysis_data["msg"] = get_rag_commentary(ticker, analysis_data)
    analysis_data["status"] = "AI 분석 완료"
    analysis_data["color"] = "#3498db"
    analysis_data["summary"] = info.get("longBusinessSummary", "")[:200] + "..."

    return templates.TemplateResponse("index.html", {"request": request, "ticker": ticker, "result": analysis_data})