"""SQLite stores LangChain message JSON; SQL parameters keep values separate from SQL."""
import json
import sqlite3
from contextlib import closing
from langchain_core.messages import messages_from_dict, messages_to_dict
from core import settings


def connect():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(settings.DATABASE_PATH, timeout=30)

def init_database():
    with closing(connect()) as connection, connection:
        # Older versions accidentally used the name `Orders` for chat history.
        # Migrate it before creating the real order tables, preserving all rows.
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "Orders" in tables:
            columns = {row[1] for row in connection.execute('PRAGMA table_info("Orders")')}
            if {"session_id", "message_json"}.issubset(columns) and not {"customer_name", "phone"}.issubset(columns):
                if "messages" not in tables:
                    connection.execute('ALTER TABLE "Orders" RENAME TO messages')
                else:
                    connection.execute(
                        'INSERT INTO messages (session_id, message_json) '
                        'SELECT session_id, message_json FROM "Orders"'
                    )
                    connection.execute('DROP TABLE "Orders"')

        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_json TEXT NOT NULL
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                order_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                complaint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
            )
        """)
        connection.execute("""
                CREATE TABLE IF NOT EXISTS Orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
            )
        """)
        connection.execute("""
                CREATE TABLE IF NOT EXISTS OrderItems (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES Orders(order_id) ON DELETE CASCADE,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1
            )
        """)
        connection.execute("PRAGMA user_version = 1")

def save_complaint(customer_name, order_id, phone, complaint):
    values = (customer_name, order_id, phone, complaint)
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id FROM complaints WHERE customer_name=? AND order_id=? AND phone=? AND complaint=?",
            values,
        ).fetchone()
        if row is None:
            cursor = connection.execute(
                "INSERT INTO complaints (customer_name, order_id, phone, complaint) VALUES (?, ?, ?, ?)",
                values,
            )
            row = (cursor.lastrowid,)
    return {"complaint_id": row[0], "status": "Pending"}








# def connect():
#     settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
#     return sqlite3.connect(settings.DATABASE_PATH, timeout=30)


def load_messages(session_id):
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT message_json FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return messages_from_dict([json.loads(row[0]) for row in rows])

def load_orders(order_id):
    with closing(connect()) as connection:
        order_row = connection.execute(
            "SELECT order_id, session_id, customer_name, phone, status "
            "FROM Orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if order_row is None:
            return []
        items = connection.execute(
            "SELECT item_name, quantity FROM OrderItems "
            "WHERE order_id = ? ORDER BY item_id",
            (order_id,),
        ).fetchall()
    return [{
        "order_id": order_row[0],
        "session_id": order_row[1],
        "customer_name": order_row[2],
        "phone": order_row[3],
        "status": order_row[4],
        "items": [{"name": name, "quantity": quantity} for name, quantity in items],
    }]
    
def load_all_orders():
    with closing(connect()) as connection:
        order_rows = connection.execute(
            "SELECT order_id, session_id, customer_name, phone, status FROM Orders ORDER BY order_id"
        ).fetchall()
        orders = []
        for order_row in order_rows:
            items = connection.execute(
                "SELECT item_name, quantity FROM OrderItems WHERE order_id = ? ORDER BY item_id",
                (order_row[0],),
            ).fetchall()
            orders.append({
                "order_id": order_row[0],
                "session_id": order_row[1],
                "customer_name": order_row[2],
                "phone": order_row[3],
                "status": order_row[4],
                "items": [{"name": name, "quantity": quantity} for name, quantity in items],
            })
    return orders
def load_all_messages():
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT session_id, message_json FROM messages ORDER BY id"
        ).fetchall()
    return [(session_id, messages_from_dict([json.loads(message_json)])[0])
            for session_id, message_json in rows]

def append_messages(session_id, messages):
    # One transaction: save all messages for a successful turn together.
    rows = [(session_id, json.dumps(message)) for message in messages_to_dict(messages)]
    with closing(connect()) as connection, connection:
        connection.executemany(
            "INSERT INTO messages (session_id, message_json) VALUES (?, ?)", rows
        )


def order(session_id, customer_name, phone, items):  # items = [("burger", 2), ("fries", 1)]
    with closing(connect()) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "INSERT INTO Orders (session_id, customer_name, phone) VALUES (?, ?, ?)",
            (session_id, customer_name, phone),
        )
        order_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO OrderItems (order_id, item_name, quantity) VALUES (?, ?, ?)",
            [(order_id, name, qty) for name, qty in items],
        )
    return {"order_id": order_id, "status": "Pending"}



# def order(session_id, customer_name, phone, items):
#     items_json = json.dumps(items, sort_keys=True)  # ["burger", "fries"] -> string
#     values = (session_id, customer_name, phone, items_json)
#     with closing(connect()) as connection, connection:
#         connection.execute("BEGIN IMMEDIATE")
#         row = connection.execute(
#             "SELECT order_id FROM Orders WHERE session_id=? AND customer_name=? AND phone=? AND items=?",
#             values,
#         ).fetchone()
#         if row is None:
#             cursor = connection.execute(
#                 "INSERT INTO Orders (session_id, customer_name, phone, items) VALUES (?, ?, ?, ?)",
#                 values,
#             )
#             row = (cursor.lastrowid,)
#     return {"order_id": row[0], "status": "Pending"}
