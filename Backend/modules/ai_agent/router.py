import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from langgraph.errors import GraphRecursionError
from openai import APIError
from .schema import chat_payload
from . import service

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)
ai_agent_router = APIRouter(
    prefix="/ai",
    # Documents the middleware-protected header in OpenAPI so Swagger UI can
    # send it after the user authorizes with the configured server key.
    dependencies=[Depends(api_key_header)],
)
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
    except Exception as exc:
        logger.exception("Unexpected failure while handling a chat request")
        raise HTTPException(status_code=500, detail="The chat request could not be completed.") from exc
    return {"session_id": payload.session_id, "answer": answer}

@ai_agent_router.get("/history")
def get_history(session_id: str):
    return {"session_id": session_id, "messages": service.get_history(session_id)}

@ai_agent_router.get("/history/all")
def get_all_history():
    return {"messages": service.get_all_history()}

@ai_agent_router.get("/order")
def get_order(order_id: str):
    order = service.get_order(order_id)
    if "error" in order:
        raise HTTPException(status_code=404, detail=order["error"])
    return order
@ai_agent_router.get("/order/all")
def get_all_orders():
    return {"orders": service.get_all_orders()}
