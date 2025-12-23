#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
import time
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from openai import OpenAI


app = FastAPI(title="Quant Strategy Dashboard (Render + RAG)")
templates = Jinja2Templates(directory="templates")

# OpenAI client (API Key는 환경변수 OPENAI_API_KEY로 자동 인식)
oa_client = OpenAI()



@app.get("/debug/yahoo")
def debug_yahoo():
    t = yf.Ticker("AAPL")

    # yfinance 버전에 따라 session 접근이 달라짐
    s = getattr(getattr(t, "_data", None), "session", None)
    if s is None:
        s = getattr(getattr(t, "_data", None), "_session", None)

    if s is None:
        return {"error": "yfinance session not found on this version"}

    url = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
    r = s.get(url, timeout=10)

    return {
        "status": r.status_code,
        "content_type": r.headers.get("content-type", ""),
        "preview": (r.text or "")[:200],
    }


# -----------------------------
# Utilities
# -----------------------------
def format_mcap(v: float | int | None) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    v = float(v)
    if v >= 1e12:
        return f"{v/1e12:.2f}T"
    if v >= 1e9:
        return f"{v/1e9:.2f}B"
    if v >= 1e6:
        return f"{v/1e6:.2f}M"
    if v >= 1e3:
        return f"{v/1e3:.2f}K"
    return f"{v:.0f}"


def safe_num(x, nd=2, na="N/A"):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return na
        return round(float(x), nd)
    except Exception:
        return na


def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    if close is None or len(close) < period + 1:
        return None

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    val = rsi.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def score_and_message(rsi: float | None, pe: float | None, change_pct: float | None) -> dict:
    # "매수/매도 지시" 대신 "매력도/주의"로 표현
    score = 50

    if rsi is not None:
        if rsi < 30:
            score += 20
        elif rsi > 70:
            score -= 20
        else:
            score += int(10 - abs(rsi - 50) / 2)

    if pe is not None and not np.isnan(pe):
        if pe < 15:
            score += 10
        elif pe < 30:
            score += 5
        elif pe > 60:
            score -= 10
        elif pe > 40:
            score -= 5

    if change_pct is not None:
        if change_pct > 5:
            score -= 5
        elif change_pct < -5:
            score += 3

    score = max(0, min(100, int(score)))

    if score >= 75:
        color = "#2ecc71"
        status = "긍정(우호적)"
        msg = "지표상 우호 구간일 수 있으나, 변동성/이벤트 리스크를 함께 점검하세요."
    elif score >= 55:
        color = "#f1c40f"
        status = "중립(관망/선별)"
        msg = "핵심 지표가 혼재합니다. 분할 접근·리스크 관리가 유리합니다."
    else:
        color = "#e74c3c"
        status = "주의(방어적)"
        msg = "단기 과열 또는 펀더멘털 부담 신호일 수 있습니다. 포지션 크기/손실 제한을 우선하세요."

    return {"score": score, "color": color, "status": status, "msg": msg}


def fetch_ticker_summary(info: dict) -> str:
    summary = info.get("longBusinessSummary") or info.get("shortBusinessSummary")
    if summary:
        return summary

    name = info.get("longName") or info.get("shortName") or ""
    sector = info.get("sector") or "N/A"
    industry = info.get("industry") or "N/A"
    country = info.get("country") or "N/A"
    return f"{name} | Sector: {sector} | Industry: {industry} | Country: {country}"


def analyze_ticker(ticker: str) -> dict:
    t = yf.Ticker(ticker)

    hist = t.history(period="3mo", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        raise ValueError("가격 데이터를 불러오지 못했습니다. 티커를 확인하세요.")

    close = hist["Close"].dropna()
    last_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2]) if len(close) >= 2 else last_price
    change_pct = ((last_price - prev_price) / prev_price) * 100 if prev_price != 0 else 0.0

    rsi = compute_rsi(close, period=14)

    info = {}
    try:
        info = t.get_info() or {}
    except Exception:
        info = {}

    mcap = info.get("marketCap")
    pe = info.get("trailingPE") or info.get("forwardPE")

    msgpack = score_and_message(rsi, pe, change_pct)

    return {
        "price": safe_num(last_price, 2),
        "change": safe_num(change_pct, 2),
        "rsi": safe_num(rsi, 2, na="N/A"),
        "mcap": format_mcap(mcap),
        "pe": safe_num(pe, 2, na="N/A"),
        "score": msgpack["score"],
        "color": msgpack["color"],
        "status": msgpack["status"],
        "msg": msgpack["msg"],
        "summary": fetch_ticker_summary(info),
    }


# -----------------------------
# RAG (Vector Store only, no local PDFs)
# -----------------------------
# 간단 캐시 (동일 티커 반복시 비용/지연 감소)
_RAG_CACHE: dict[str, tuple[float, str, str]] = {}
_RAG_TTL_SEC = 60 * 10  # 10분


def _parse_rag_blocks(text: str) -> Tuple[str, str]:
    """
    모델이 아래 형식으로 내보내도록 유도:
      RAG_MSG: ...
      RAG_SUMMARY: ...
    """
    rag_msg = ""
    rag_summary = ""

    # 라인 기반 우선 파싱
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("RAG_MSG:"):
            rag_msg = s.replace("RAG_MSG:", "", 1).strip()
        elif s.startswith("RAG_SUMMARY:"):
            rag_summary = s.replace("RAG_SUMMARY:", "", 1).strip()

    # 형식이 어긋난 경우 fallback(너무 길지 않게)
    if not rag_msg and text:
        rag_msg = text.strip().splitlines()[0][:240]
    if not rag_summary and text:
        rest = "\n".join(text.strip().splitlines()[1:]).strip()
        rag_summary = rest[:700] if rest else ""

    return rag_msg, rag_summary


def rag_commentary_from_vectorstore(ticker: str, result: dict) -> Tuple[str, str]:
    """
    Render 서버는 PDF를 갖고 있지 않고, Vector Store ID만 가진다.
    요청마다 file_search로 관련 chunk를 찾아 전략 코멘트를 생성한다.
    """
    vs_id = os.environ.get("OPENAI_VECTOR_STORE_ID")
    if not vs_id:
        return "", ""

    cache_key = f"{ticker}:{result.get('score')}:{result.get('rsi')}:{result.get('pe')}:{result.get('change')}"
    now = time.time()
    if cache_key in _RAG_CACHE:
        ts, m, s = _RAG_CACHE[cache_key]
        if now - ts < _RAG_TTL_SEC:
            return m, s

    user_query = f"""
티커: {ticker}

현재 지표(대시보드):
- Price: {result.get("price")}
- Change(%): {result.get("change")}
- RSI(14): {result.get("rsi")}
- PER: {result.get("pe")}
- Score: {result.get("score")} / Status: {result.get("status")}

요청:
- 업로드된 PDF 지식(퀀트 전략/팩터/리스크관리/백테스트/거래비용/리밸런싱 등)에서
  위 지표를 해석할 때 도움이 되는 원칙/체크리스트/주의점을 찾아 간결히 요약.
- 매수/매도 지시 금지. 수익 보장/단정 예측 금지.
- 문서 근거 기반으로만 말해라.
- 출력 형식(꼭 지켜):
  RAG_MSG: (2~3문장, 220자 이내)
  RAG_SUMMARY: (2~4문장, 500자 이내)
"""

    resp = oa_client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": (
                    "너는 퀀트 리서치 어시스턴트다. "
                    "사용자가 제공한 지표를 문서 지식에 근거해 해석하되, "
                    "단정적 예측/매수매도 지시는 하지 않는다."
                ),
            },
            {"role": "user", "content": user_query},
        ],
        tools=[{
            "type": "file_search",
            "vector_store_ids": [vs_id],
        }],
    )

    text = (resp.output_text or "").strip()
    rag_msg, rag_summary = _parse_rag_blocks(text)

    _RAG_CACHE[cache_key] = (now, rag_msg, rag_summary)
    return rag_msg, rag_summary


# -----------------------------
# Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, ticker: str = Form(...)):
    ticker = (ticker or "").strip().upper()

    try:
        result = analyze_ticker(ticker)

        # RAG 결합 (Vector Store 검색 기반)
        rag_msg, rag_summary = rag_commentary_from_vectorstore(ticker, result)

        if rag_msg:
            base = (result.get("msg") or "").strip()
            result["msg"] = (base + " " + rag_msg).strip()

        if rag_summary:
            base_sum = (result.get("summary") or "").strip()
            result["summary"] = (base_sum + "\n\n[PDF 기반 전략 메모]\n" + rag_summary).strip()

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "ticker": ticker, "result": result},
        )

    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "ticker": ticker,
                "result": {
                    "price": "N/A",
                    "change": 0,
                    "rsi": "N/A",
                    "mcap": "N/A",
                    "pe": "N/A",
                    "score": 0,
                    "color": "#e74c3c",
                    "status": "오류",
                    "msg": f"분석 실패: {str(e)}",
                    "summary": "티커가 정확한지 확인하거나 잠시 후 다시 시도하세요.",
                },
            },
        )
