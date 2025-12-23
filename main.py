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
    """Vector Store 연결 및 파일 포함 여부를 실시간 검증합니다."""
    try:
        # openai>=1.30.0 버전에서만 정상 작동하는 코드입니다.
        vs = client.beta.vector_stores.retrieve(VECTOR_STORE_ID)
        file_count = vs.file_counts.completed
        print(f"🔍 [검증] Vector Store ID: {VECTOR_STORE_ID} | 연결된 파일 수: {file_count}")
        return file_count > 0
    except Exception as e:
        print(f"❌ [검증 실패] 라이브러리 버전 또는 ID 오류: {str(e)}")
        return False

def get_pro_myeongri_analysis(user_data: dict):
    if not verify_vector_store():
        return {"status": "지식 저장소 연결 실패", "analysis": "PDF 문서를 읽어올 수 없습니다. 라이브러리 버전을 확인하세요.", "color": "#e74c3c"}

    prompt = f"""
    [명리학 전문 분석 프레임워크]
    사용자: {user_data['name']}, {user_data['gender']}, {user_data['birth_date']} {user_data['birth_time']}

    분석 지침:
    1. 'Bazi.pdf'에 명시된 일간(Day Master) 해석법을 적용하라.
    2. 격국론과 십신(Ten Gods)의 배치를 통해 사주의 강약을 판별하라.
    3. 2026~2028년의 투자 방향을 PDF에 기재된 운세 해석 원칙에 따라 구체적 JSON으로 응답하라.
    """

    try:
        assistant = client.beta.assistants.create(
            name="Pro Myeongri Analyst",
            instructions="너는 업로드된 명리학 PDF를 완벽히 이해한 전문가다.",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}}
        )

        thread = client.beta.threads.create(messages=[{"role": "user", "content": prompt}])
        run = client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant.id)

        if run.status == 'completed':
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            ai_raw = messages.data[0].content[0].text.value
            
            result = {"analysis": "데이터 파싱 중...", "status": "분석 완료", "color": "#3498db"}
            json_match = re.search(r'\{.*\}', ai_raw, re.DOTALL)
            if json_match:
                result.update(json.loads(json_match.group()))
            
            client.beta.assistants.delete(assistant.id)
            return result
    except Exception as e:
        return {"status": "에러", "analysis": str(e), "color": "#e74c3c"}