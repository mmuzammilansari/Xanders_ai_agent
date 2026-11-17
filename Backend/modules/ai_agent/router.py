import logging

from fastapi import APIRouter, HTTPException
from langgraph.errors import GraphRecursionError
from openai import APIError
from .schema import chat_payload
from . import service

ai_agent_router = APIRouter(prefix="/ai")
logger = logging.getLogger(__name__)

@ai_agent_router.post("/chat")
def initiate_chat(payload: chat_payload):
    try:
        answer = service.chat(payload.query, payload.session_id)
    except (APIError, GraphRecursionError) as exc:
        logger.exception("AI provider failed while handling a chat request")
        raise HTTPException(status_code=502, detail="The AI provider could not complete the request.") from exc
    except RuntimeError as exc:
        logger.exception("AI service is unavailable")
        raise HTTPException(status_code=503, detail="The AI service is not configured correctly.") from exc
    return {"session_id": payload.session_id, "answer": answer}

@ai_agent_router.get("/history")
def get_history(session_id: str):
    return {"session_id": session_id, "messages": service.get_history(session_id)}
