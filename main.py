#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 21 17:01:19 2025

@author: ohkwon
"""

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import random

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 나중에 여기에 진짜 로직을 넣으시면 됩니다!
def get_signal(ticker: str):
    responses = [
        {"action": "BUY", "msg": "강력 매수 추천! 🚀", "color": "#2ecc71"},
        {"action": "HOLD", "msg": "일단 관망하세요. ✋", "color": "#f1c40f"},
        {"action": "SELL", "msg": "지금이 매도 타이밍! 📉", "color": "#e74c3c"}
    ]
    return random.choice(responses)

@app.get("/")
async def home(request: request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze")
async def analyze(request: request, ticker: str = Form(...)):
    result = get_signal(ticker.upper())
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "ticker": ticker.upper(), 
        "result": result
    })