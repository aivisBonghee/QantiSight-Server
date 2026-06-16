import json

import google.generativeai as genai
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.chat_tools import TOOL_DECLARATIONS, execute_tool

SYSTEM_PROMPT = """당신은 QantiSight AI 어시스턴트입니다. 병리 슬라이드 QC(Quality Control) 시스템을 도와주는 전문 AI입니다.

역할:
- QC 결과 조회 및 분석 (장기/염색 일치율, 품질 점수, 병변량 등)
- 케이스 검색 및 필터링
- 서버별 데이터 위치 안내
- 병리 QC 관련 질문 답변

규칙:
- 사용 가능한 도구를 활용하여 실제 DB 데이터를 조회하고 정확한 답변을 제공하세요.
- 답변은 한국어로, 간결하게 제공하세요.
- 숫자 데이터는 구체적으로 제공하세요.
- 추측하지 말고, 데이터가 없으면 없다고 말하세요.

QC 시스템 컨텍스트:
- 장기(Organ): Breast, Stomach, Bladder, Thyroid, Colon, Brain
- 염색(Stain): HE, HER2, ER, PR, KI67
- AI 모델은 장기 분류, 염색 분류(HE/IHC-nuclear/IHC-membrane), 종양 세포 검출을 수행합니다.
- IHC-nuclear은 ER/PR/KI67 패턴, IHC-membrane은 HER2 패턴입니다.
- QC 점수: 0-100 (≥85 PASS, 70-84 CONDITIONAL, 50-69 FAIL-RESCAN, <50 FAIL-CRITICAL)
- 상태: WAITING(대기), PROCESSING(분석중), DONE(완료), ERROR(오류), CONFIRMED(확인)
"""

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    parts: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    genai.configure(api_key=settings.gemini_api_key)

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        tools=[{"function_declarations": TOOL_DECLARATIONS}],
        system_instruction=SYSTEM_PROMPT,
    )

    gemini_history = []
    for msg in req.history:
        gemini_history.append({"role": msg.role, "parts": [msg.parts]})

    chat_session = model.start_chat(history=gemini_history)

    def generate():
        try:
            response = chat_session.send_message(req.message)

            for _ in range(5):
                function_calls = [
                    part.function_call
                    for part in response.parts
                    if part.function_call.name
                ]

                if not function_calls:
                    break

                parts = []
                for fc in function_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    yield f"data: {json.dumps({'type': 'tool', 'name': tool_name}, ensure_ascii=False)}\n\n"

                    result = execute_tool(tool_name, tool_args, db)

                    parts.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={
                                    "result": json.dumps(
                                        result, ensure_ascii=False, default=str
                                    )
                                },
                            )
                        )
                    )

                response = chat_session.send_message(
                    genai.protos.Content(parts=parts)
                )

            text = response.text
            chunk_size = 30
            for i in range(0, len(text), chunk_size):
                yield f"data: {json.dumps({'type': 'text', 'content': text[i:i + chunk_size]}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
