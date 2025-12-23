import os
import json
import re
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI(title="Professional Myeongri-Quant Center")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID")

def verify_vector_store():
    """Vector Store가 정상이고 파일이 포함되어 있는지 검증합니다."""
    try:
        # 라이브러리 버전이 낮으면 여기서 AttributeError가 발생하므로 
        # requirements.txt 업데이트가 필수입니다.
        vs = client.beta.vector_stores.retrieve(VECTOR_STORE_ID)
        file_count = vs.file_counts.completed
        print(f"🔍 [검증] Vector Store ID: {VECTOR_STORE_ID} | 연결된 파일 수: {file_count}")
        return file_count > 0
    except Exception as e:
        # 에러 메시지를 더 구체적으로 찍어서 원인을 파악합니다.
        print(f"❌ [검증 실패] Vector Store 오류: {str(e)}")
        return False

def get_pro_myeongri_analysis(user_data: dict):
    # 1. 연결 검증 실행
    if not verify_vector_store():
        return {"status": "연결 오류", "analysis": "PDF 지식 저장소(Vector Store) 연결에 실패했거나 파일이 없습니다.", "color": "#e74c3c"}

    # 2. 명리학 전문 프레임워크를 반영한 프롬프트
    prompt = f"""
    [명리학 전문 분석 지침]
    사용자 정보: {user_data['name']}, {user_data['gender']}, 생년월일시: {user_data['birth_date']} {user_data['birth_time']}

    분석 단계:
    1. 사주팔자 도출: 생년월일시를 바탕으로 만세력을 구성하고 일간(Day Master)을 확정하라.
    2. PDF 지식 대조: 업로드된 'Bazi.pdf'에서 일간의 특성, 십신(Ten Gods)의 배치, 격국(Structure)론을 찾아내어 이 사주의 '강약'과 '용신(Useful God)'을 판별하라.
    3. 3개년 투자 로드맵: 2026(병오), 2027(정미), 2028(무신)년의 세운(Annual Luck)과 사용자의 용신/희신 관계를 PDF의 '운세 해석 법칙'에 대입하여 구체적 투자 비중을 산출하라.

    응답 규칙:
    - PDF에 없는 일반적인 내용은 배제하고, 반드시 문서 내의 특수 해석법을 인용하라.
    - 출력은 반드시 아래 JSON 형식을 유지하라:
    {{
        "analysis": "일간 및 격국 분석, 용신 판별 결과 (PDF 근거 포함)",
        "year_1": "2026년: 운세에 따른 자산 배분 전략 및 주의사항",
        "year_2": "2027년: 운세에 따른 자산 배분 전략 및 주의사항",
        "year_3": "2028년: 운세에 따른 자산 배분 전략 및 주의사항",
        "status": "현재 대운/세운 기반 투자 심리 상태",
        "color": "길흉에 따른 색상(#2ecc71:길, #f1c40f:평범, #e74c3c:흉)"
    }}
    """

    try:
        # 고정된 어시스턴트 대신 매번 최적화된 설정을 주입합니다.
        assistant = client.beta.assistants.create(
            name="Pro Myeongri Analyst",
            instructions="너는 'Bazi.pdf'의 모든 내용을 암기한 명리학 대가다. 문서의 전문 용어를 사용하여 깊이 있는 분석을 제공하라.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}}
        )

        thread = client.beta.threads.create(messages=[{"role": "user", "content": prompt}])
        run = client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant.id)

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            ai_raw = messages.data[0].content[0].text.value
            
            # JSON 파싱 강화
            result = {"analysis": "데이터 파싱 중...", "status": "분석 완료", "color": "#3498db"}
            json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
            if json_match:
                result.update(json.loads(json_match.group()))
            
            client.beta.assistants.delete(assistant.id)
            return result
        return {"status": "시간 초과", "analysis": "분석이 너무 깊어 응답이 지연되었습니다.", "color": "#e74c3c"}

    except Exception as e:
        return {"status": "시스템 에러", "analysis": f"오류: {str(e)}", "color": "#e74c3c"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, name: str = Form(...), birth_date: str = Form(...), birth_time: str = Form("모름"), gender: str = Form(...)):
    user_data = {"name": name, "birth_date": birth_date, "birth_time": birth_time, "gender": gender}
    result = get_pro_myeongri_analysis(user_data)
    return templates.TemplateResponse("index.html", {"request": request, "user": user_data, "result": result})