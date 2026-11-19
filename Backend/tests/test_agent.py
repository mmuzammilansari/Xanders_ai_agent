"""Offline tests: real API, graph, SQLite and Chroma; no provider calls."""
from contextlib import closing, nullcontext
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from openai import APIConnectionError
import httpx
from core import settings
from core.database import sqlite
from modules.knowledge import service as knowledge
from main import app
from modules.ai_agent import service
from modules.ai_agent.graph import build_graph
from modules.ai_agent.tools import fetch_menu, log_complaint


class FakeModel:
    def __init__(self):
        self.seen = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.seen.append(messages)
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="Zinger Burger costs Rs 850.")
        if messages[-1].content == "menu":
            return AIMessage(content="", tool_calls=[{
                "name": "fetch_menu", "args": {}, "id": "call-menu", "type": "tool_call"
            }])
        earlier = [m.content for m in messages if isinstance(m, HumanMessage)]
        return AIMessage(content="Earlier messages: " + " | ".join(earlier))


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.patch_auth = patch.dict("os.environ", {"AUTHENTICATED_KEY": "", "SECRET_KEY": ""})
        self.patch_auth.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.patch_data = patch.object(settings, "DATA_DIR", self.folder)
        self.patch_db = patch.object(settings, "DATABASE_PATH", self.folder / "test.sqlite3")
        self.patch_data.start()
        self.patch_db.start()
        self.model = FakeModel()
        self.graph = build_graph(model=self.model, tools=[fetch_menu])
        self.patch_graph = patch.object(service, "get_graph", return_value=self.graph)
        self.patch_graph.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.patch_graph.stop()
        self.patch_db.stop()
        self.patch_data.stop()
        self.patch_auth.stop()
        self.tmp.cleanup()

    def test_tool_loop_and_history_survive_new_client(self):
        result = self.client.post("/ai/chat", json={"query": "menu", "session_id": "sam"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("850", result.json()["answer"])
        saved = sqlite.load_messages("sam")
        self.assertEqual([m.type for m in saved], ["human", "ai", "tool", "ai"])
        self.assertEqual(saved[1].tool_calls[0]["id"], saved[2].tool_call_id)
        # A new app lifespan and a newly built graph load the same SQLite file.
        with TestClient(app) as restarted, patch.object(service, "get_graph", return_value=build_graph(model=FakeModel(), tools=[fetch_menu])):
            reply = restarted.post("/ai/chat", json={"query": "remember me", "session_id": "sam"})
            self.assertIn("menu | remember me", reply.json()["answer"])
        public = self.client.get("/ai/history", params={"session_id": "sam"}).json()
        self.assertEqual(len(public["messages"]), 4)
        self.assertEqual(public["messages"][0], {"role": "user", "content": "menu"})
        self.assertEqual(self.client.get("/ai/history?session_id=other").json()["messages"], [])
        other = self.client.post("/ai/chat", json={"query": "hello", "session_id": "other"})
        self.assertNotIn("menu", other.json()["answer"])

    def test_validation_and_failed_provider_do_not_save_partial_turn(self):
        for payload in [{"query": "hello"}, {"query": "   ", "session_id": "sam"}, {"query": "hi", "session_id": "bad id"}]:
            self.assertEqual(self.client.post("/ai/chat", json=payload).status_code, 422)
        self.assertEqual(self.client.get("/ai/history").status_code, 422)
        with patch.object(service, "get_graph", side_effect=RuntimeError("missing key")), self.assertLogs("modules.ai_agent.router", level="ERROR"):
            response = self.client.post("/ai/chat", json={"query": "hello", "session_id": "failed"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(sqlite.load_messages("failed"), [])

    def test_authentication_accepts_either_configured_key_name(self):
        with patch.dict("os.environ", {"AUTHENTICATED_KEY": "backend-secret", "SECRET_KEY": ""}):
            denied = self.client.get("/ai/history", params={"session_id": "sam"})
            allowed = self.client.get("/ai/history", params={"session_id": "sam"}, headers={"X-API-KEY": "backend-secret"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        with patch.dict("os.environ", {"AUTHENTICATED_KEY": "", "SECRET_KEY": "frontend-secret"}):
            allowed = self.client.get("/ai/history", params={"session_id": "sam"}, headers={"X-API-KEY": "frontend-secret"})
        self.assertEqual(allowed.status_code, 200)

    def test_order_tool_saves_order_and_items(self):
        from modules.ai_agent.tools import place_order

        result = place_order.invoke({
            "customer_name": "Sam",
            "phone": "03000000000",
            "items": [{"name": "Zinger Burger", "quantity": 2}],
        }, config={"configurable": {"session_id": "order-session"}})
        self.assertEqual(result["status"], "Pending")
        with closing(sqlite.connect()) as connection:
            order = connection.execute(
                "SELECT session_id, customer_name, phone FROM Orders WHERE order_id=?",
                (result["order_id"],),
            ).fetchone()
            items = connection.execute(
                "SELECT item_name, quantity FROM OrderItems WHERE order_id=?",
                (result["order_id"],),
            ).fetchall()
        self.assertEqual(order, ("order-session", "Sam", "03000000000"))
        self.assertEqual(items, [("Zinger Burger", 2)])
        from modules.ai_agent.service import get_order
        self.assertEqual(get_order(result["order_id"]), {
            "order_id": result["order_id"],
            "session_id": "order-session",
            "customer_name": "Sam",
            "phone": "03000000000",
            "status": "Pending",
            "items": [{"name": "Zinger Burger", "quantity": 2}],
        })
        self.assertEqual(get_order(-1), {"error": "Order not found."})

    def test_migrates_legacy_orders_named_chat_history(self):
        with closing(sqlite.connect()) as connection, connection:
            connection.execute('DROP TABLE "Orders"')
            connection.execute('DROP TABLE messages')
            connection.execute('CREATE TABLE "Orders" (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, message_json TEXT NOT NULL)')
            connection.execute('INSERT INTO "Orders" (session_id, message_json) VALUES (?, ?)', ("legacy", '{"type":"human","data":{"content":"hello"}}'))
        sqlite.init_database()
        with closing(sqlite.connect()) as connection:
            self.assertEqual(connection.execute('SELECT session_id, message_json FROM messages').fetchall(), [
                ("legacy", '{"type":"human","data":{"content":"hello"}}')
            ])
            order_columns = {row[1] for row in connection.execute('PRAGMA table_info("Orders")')}
            self.assertTrue({"customer_name", "phone", "session_id"}.issubset(order_columns))
        self.assertEqual(sqlite.load_messages("legacy")[0].content, "hello")

    def test_provider_and_loop_limit_return_502_without_saving(self):
        errors = [
            GraphRecursionError("step limit"),
            APIConnectionError(request=httpx.Request("POST", "https://example.invalid/chat")),
        ]
        for error in errors:
            logs = self.assertLogs("modules.ai_agent.router", level="ERROR") if isinstance(error, APIConnectionError) else nullcontext()
            with self.subTest(error=type(error).__name__), patch.object(service, "get_graph", side_effect=error), logs:
                response = self.client.post("/ai/chat", json={"query": "hello", "session_id": "failed"})
            self.assertEqual(response.status_code, 502)
            self.assertEqual(sqlite.load_messages("failed"), [])

    def test_complaint_validation_and_retry(self):
        args = {"customer_name": "Sam", "order_id": "INVALID", "phone": "03000000000", "complaint": "Wrong food delivered"}
        self.assertIn("error", log_complaint.invoke(args))
        args["order_id"] = "OR-1045"
        first = log_complaint.invoke(args)
        self.assertEqual(first["status"], "Pending")
        self.assertEqual(first["complaint_id"], log_complaint.invoke(args)["complaint_id"])
        with closing(sqlite.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0], 1)

    def test_rag_index_retrieves_source_and_checks_embedding_model(self):
        document = self.folder / "restaurant.txt"
        document.write_text("The Gulshan branch serves the special beef burger every day.\n\nThe restaurant was founded in Karachi in 2018 by two friends.")
        def fake_embeddings(texts):
            return [[1.0, 0.0] if "Gulshan" in text else [0.0, 1.0] for text in texts]
        with patch.object(settings, "KNOWLEDGE_PATH", document), patch.object(knowledge, "create_embeddings", side_effect=fake_embeddings):
            self.assertIn("empty", knowledge.search_knowledge("Gulshan"))
            self.assertEqual(knowledge.build_index(), 2)
            result = knowledge.search_knowledge("Gulshan")
            self.assertIn("Source: restaurant.txt", result)
            self.assertIn("beef burger", result)
            with patch.dict("os.environ", {"EMBEDDING_MODEL": "different-model"}):
                self.assertIn("Rebuild", knowledge.search_knowledge("Gulshan"))


if __name__ == "__main__":
    unittest.main()
