from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from text_normalizer import normalize_turkish
from collections import defaultdict, deque
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from local_ai import choose


# ==================================================
# SETTINGS
# ==================================================

BASE = Path(__file__).resolve().parent

load_dotenv(BASE / ".env")

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

if (
    not SESSION_SECRET
    or not ADMIN_USERNAME
    or not ADMIN_PASSWORD_HASH
    or len(SESSION_SECRET) < 32
):
    raise RuntimeError(
        "Yönetici ayarları eksik. "
        "Mevcut .env dosyasını kontrol edin."
    )

DB = BASE / "destek.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("destek")


# ==================================================
# DATABASE
# ==================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def connection():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA busy_timeout=20000")
    db.execute("PRAGMA foreign_keys=ON")

    return db


def init_db():
    with connection() as db:

        db.execute("PRAGMA journal_mode=WAL")

        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                response TEXT NOT NULL DEFAULT '',
                response_type TEXT NOT NULL DEFAULT 'pending',
                faq_id TEXT,
                ticket_number TEXT,
                created_at TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT NOT NULL UNIQUE,
                secret_hash TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'yeni',
                expert_reply TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS expert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                reply TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender TEXT NOT NULL
                    CHECK(sender IN ('customer', 'expert')),
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id)
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_ticket
            ON conversation_messages(ticket_id, id)
        """)

        # Expert-approved reusable information

        db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_ticket_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                normalized_question TEXT NOT NULL,
                answer TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
                    CHECK(active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_ticket_id)
                    REFERENCES tickets(id)
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_active
            ON knowledge_base(active)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_source
            ON knowledge_base(source_ticket_id)
        """)

        # Migrate old tickets only if conversation data
        # is not already present.

        old_tickets = db.execute(
            "SELECT * FROM tickets"
        ).fetchall()

        for ticket in old_tickets:

            exists = db.execute(
                """
                SELECT 1
                FROM conversation_messages
                WHERE ticket_id=?
                LIMIT 1
                """,
                (ticket["id"],)
            ).fetchone()

            if exists:
                continue

            db.execute(
                """
                INSERT INTO conversation_messages
                (ticket_id, sender, message, created_at)
                VALUES (?, 'customer', ?, ?)
                """,
                (
                    ticket["id"],
                    ticket["question"],
                    ticket["created_at"]
                )
            )

            replies = db.execute(
                """
                SELECT reply, created_at
                FROM expert_history
                WHERE ticket_id=?
                ORDER BY id
                """,
                (ticket["id"],)
            ).fetchall()

            last_reply = ""

            for item in replies:

                reply = (item["reply"] or "").strip()

                if not reply or reply == last_reply:
                    continue

                db.execute(
                    """
                    INSERT INTO conversation_messages
                    (ticket_id, sender, message, created_at)
                    VALUES (?, 'expert', ?, ?)
                    """,
                    (
                        ticket["id"],
                        reply,
                        item["created_at"]
                    )
                )

                last_reply = reply

            current_reply = (
                ticket["expert_reply"] or ""
            ).strip()

            if current_reply and current_reply != last_reply:

                db.execute(
                    """
                    INSERT INTO conversation_messages
                    (ticket_id, sender, message, created_at)
                    VALUES (?, 'expert', ?, ?)
                    """,
                    (
                        ticket["id"],
                        current_reply,
                        ticket["updated_at"]
                    )
                )


init_db()


# ==================================================
# APPLICATION
# ==================================================

app = FastAPI(
    title="Destek Merkezi",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE") == "true",
    max_age=60 * 60 * 8
)

app.mount(
    "/static",
    StaticFiles(directory=BASE / "static"),
    name="static"
)

templates = Jinja2Templates(
    directory=str(BASE / "templates")
)


# ==================================================
# SECURITY
# ==================================================

_rate = defaultdict(deque)
_rate_lock = Lock()


def throttle(request, name, count, seconds):

    address = (
        request.client.host
        if request.client
        else "unknown"
    )

    marker = (name, address)
    now = time.monotonic()

    with _rate_lock:

        hits = _rate[marker]

        while hits and now - hits[0] > seconds:
            hits.popleft()

        if len(hits) >= count:
            raise HTTPException(
                status_code=429,
                detail="Çok fazla istek. Biraz sonra tekrar deneyin."
            )

        hits.append(now)


def csrf_token(request):

    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(24)

    return request.session["csrf"]


def verify_csrf(request, token):

    stored = request.session.get("csrf", "")

    if not stored or not hmac.compare_digest(stored, token):
        raise HTTPException(
            status_code=403,
            detail="Güvenlik doğrulaması başarısız."
        )


def admin_or_401(request):

    if request.session.get("admin") != ADMIN_USERNAME:
        raise HTTPException(
            status_code=401,
            detail="Yetkisiz işlem."
        )


def check_password(password):

    try:
        salt_hex, hash_hex = ADMIN_PASSWORD_HASH.split(
            ":", 1
        )

        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            400_000
        )

        return hmac.compare_digest(
            calculated,
            bytes.fromhex(hash_hex)
        )

    except (ValueError, TypeError):
        return False


# ==================================================
# FAQ
# ==================================================

def load_faq():

    try:
        data = json.loads(
            (BASE / "sss.json").read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, list):
            return []

        result = []

        for index, item in enumerate(data):

            if not isinstance(item, dict):
                continue

            question = item.get("soru")
            answer = item.get("cevap")

            if (
                isinstance(question, str)
                and isinstance(answer, str)
                and question.strip()
                and answer.strip()
            ):
                result.append({
                    "id": str(index),
                    "soru": question.strip(),
                    "cevap": answer.strip()
                })

        return result[:250]

    except (OSError, ValueError):
        logger.exception("SSS dosyası okunamadı.")
        return []


# ==================================================
# KNOWLEDGE MATCHING
# ==================================================

STOP_WORDS = {
    "acaba", "ben", "bana", "bir", "bu",
    "da", "de", "icin", "ile", "mi",
    "mı", "mu", "mü", "nasıl", "ne",
    "siz", "sizce", "ve"
}


def normalize_text(text):
    return normalize_turkish(text)


def useful_tokens(text):

    return {
        word
        for word in normalize_text(text).split()
        if len(word) >= 2
        and word not in STOP_WORDS
    }


def knowledge_similarity(question_a, question_b):

    a = normalize_text(question_a)
    b = normalize_text(question_b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    tokens_a = useful_tokens(a)
    tokens_b = useful_tokens(b)

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a & tokens_b)

    if intersection == 0:
        return 0.0

    coverage = intersection / max(
        len(tokens_a),
        len(tokens_b)
    )

    sequence = SequenceMatcher(
        None, a, b
    ).ratio()

    if coverage < 0.75 or sequence < 0.84:
        return 0.0

    return (
        coverage * 0.45
        + sequence * 0.55
    )


def find_knowledge(question):

    normalized = normalize_text(question)

    if not normalized:
        return None

    with connection() as db:

        exact = db.execute(
            """
            SELECT *
            FROM knowledge_base
            WHERE active=1
              AND normalized_question=?
            ORDER BY id DESC
            LIMIT 2
            """,
            (normalized,)
        ).fetchall()

        if len(exact) == 1:
            return dict(exact[0])

        if len(exact) > 1:
            return None

        rows = db.execute(
            """
            SELECT *
            FROM knowledge_base
            WHERE active=1
            ORDER BY id DESC
            """
        ).fetchall()

    candidates = []

    for row in rows:

        score = knowledge_similarity(
            question,
            row["question"]
        )

        if score >= 0.88:
            candidates.append(
                (score, dict(row))
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    if len(candidates) > 1:

        difference = (
            candidates[0][0] - candidates[1][0]
        )

        if difference < 0.06:
            return None

    return candidates[0][1]


def validate_knowledge(question, answer):

    question = question.strip()
    answer = answer.strip()

    if not 8 <= len(question) <= 500:
        raise HTTPException(
            status_code=422,
            detail="Öğretilecek soru 8-500 karakter arasında olmalı."
        )

    if not 10 <= len(answer) <= 3000:
        raise HTTPException(
            status_code=422,
            detail="Öğretilecek cevap 10-3000 karakter arasında olmalı."
        )

    normalized = normalize_text(question)

    if not normalized:
        raise HTTPException(
            status_code=422,
            detail="Geçersiz soru."
        )

    return question, answer, normalized


def insert_knowledge(db, ticket_id, question, answer):

    question, answer, normalized = validate_knowledge(
        question,
        answer
    )

    duplicate = db.execute(
        """
        SELECT id
        FROM knowledge_base
        WHERE active=1
          AND normalized_question=?
        LIMIT 1
        """,
        (normalized,)
    ).fetchone()

    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=(
                "Bu soru bilgi bankasında zaten mevcut. "
                "Görüşme kapatılmadı."
            )
        )

    existing = db.execute(
        """
        SELECT id, question
        FROM knowledge_base
        WHERE active=1
        """
    ).fetchall()

    for item in existing:

        similarity = knowledge_similarity(
            question,
            item["question"]
        )

        if similarity >= 0.90:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Bilgi bankasında çok benzer bir soru var. "
                    "Çelişkiyi önlemek için görüşme kapatılmadı."
                )
            )

    now = utc_now()

    cursor = db.execute(
        """
        INSERT INTO knowledge_base
        (
            source_ticket_id,
            question,
            normalized_question,
            answer,
            active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (
            ticket_id,
            question,
            normalized,
            answer,
            now,
            now
        )
    )

    return cursor.lastrowid


# ==================================================
# MODELS
# ==================================================

class Question(BaseModel):
    message: str = Field(
        min_length=2,
        max_length=2500
    )


class TicketLookup(BaseModel):
    number: str = Field(
        min_length=1,
        max_length=30
    )

    key: str = Field(
        min_length=10,
        max_length=100
    )


class CustomerMessage(TicketLookup):
    message: str = Field(
        min_length=1,
        max_length=5000
    )


# ==================================================
# TICKET HELPERS
# ==================================================

def get_ticket_with_key(db, number, key):

    ticket = db.execute(
        """
        SELECT *
        FROM tickets
        WHERE ticket_number=?
        """,
        (number,)
    ).fetchone()

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Görüşme bulunamadı."
        )

    calculated = hashlib.sha256(
        key.encode()
    ).hexdigest()

    if not hmac.compare_digest(
        ticket["secret_hash"],
        calculated
    ):
        raise HTTPException(
            status_code=404,
            detail="Görüşme bulunamadı."
        )

    return ticket


def get_conversation(db, ticket_id):

    rows = db.execute(
        """
        SELECT id, sender, message, created_at
        FROM conversation_messages
        WHERE ticket_id=?
        ORDER BY id
        """,
        (ticket_id,)
    ).fetchall()

    return [dict(row) for row in rows]


def make_ticket(question):

    number = "DST-" + secrets.token_hex(5).upper()
    key = secrets.token_urlsafe(32)
    now = utc_now()

    with connection() as db:

        cursor = db.execute(
            """
            INSERT INTO tickets
            (
                ticket_number,
                secret_hash,
                question,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'yeni', ?, ?)
            """,
            (
                number,
                hashlib.sha256(
                    key.encode()
                ).hexdigest(),
                question,
                now,
                now
            )
        )

        db.execute(
            """
            INSERT INTO conversation_messages
            (ticket_id, sender, message, created_at)
            VALUES (?, 'customer', ?, ?)
            """,
            (
                cursor.lastrowid,
                question,
                now
            )
        )

    return number, key


# ==================================================
# CUSTOMER HOME
# ==================================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    faq = load_faq()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "faq": faq[:6],
            "faq_count": len(faq)
        }
    )


# ==================================================
# CUSTOMER QUESTION
# ==================================================

@app.post("/api/sor")
def ask(question: Question, request: Request):

    throttle(request, "ask", 20, 60)

    message = question.message.strip()

    if len(message) < 2:
        raise HTTPException(
            status_code=422,
            detail="Sorunuzu yazın."
        )

    faq = load_faq()

    match = choose(message, faq)

    if match:

        with connection() as db:
            db.execute(
                """
                INSERT INTO messages
                (
                    question,
                    response,
                    response_type,
                    faq_id,
                    created_at
                )
                VALUES (?, ?, 'sss', ?, ?)
                """,
                (
                    message,
                    match["cevap"],
                    match.get("id"),
                    utc_now()
                )
            )

        return {
            "type": "answer",
            "text": match["cevap"],
            "source": "faq"
        }

    knowledge = find_knowledge(message)

    if knowledge:

        with connection() as db:
            db.execute(
                """
                INSERT INTO messages
                (
                    question,
                    response,
                    response_type,
                    faq_id,
                    created_at
                )
                VALUES (?, ?, 'knowledge', ?, ?)
                """,
                (
                    message,
                    knowledge["answer"],
                    str(knowledge["id"]),
                    utc_now()
                )
            )

        return {
            "type": "answer",
            "text": knowledge["answer"],
            "source": "knowledge"
        }

    number, key = make_ticket(message)

    with connection() as db:
        db.execute(
            """
            INSERT INTO messages
            (
                question,
                response,
                response_type,
                ticket_number,
                created_at
            )
            VALUES (?, ?, 'ticket', ?, ?)
            """,
            (
                message,
                "Uzman talebine aktarıldı.",
                number,
                utc_now()
            )
        )

    return {
        "type": "ticket",
        "text": "Sorunuz uzman ekibimize iletildi.",
        "ticket_number": number,
        "ticket_key": key
    }


# ==================================================
# CUSTOMER CONVERSATION
# ==================================================

@app.post("/api/talep-durumu")
def ticket_status(
    query: TicketLookup,
    request: Request
):

    throttle(
        request,
        "ticket_status",
        60,
        60
    )

    with connection() as db:

        ticket = get_ticket_with_key(
            db,
            query.number,
            query.key
        )

        messages = get_conversation(
            db,
            ticket["id"]
        )

    return {
        "number": ticket["ticket_number"],
        "question": ticket["question"],
        "status": ticket["status"],
        "reply": ticket["expert_reply"],
        "updated": ticket["updated_at"],
        "messages": messages
    }


@app.post("/api/talep-mesaj")
def customer_reply(
    data: CustomerMessage,
    request: Request
):

    throttle(
        request,
        "customer_reply",
        20,
        60
    )

    text = data.message.strip()

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Boş mesaj gönderilemez."
        )

    with connection() as db:

        ticket = get_ticket_with_key(
            db,
            data.number,
            data.key
        )

        now = utc_now()

        db.execute(
            """
            INSERT INTO conversation_messages
            (ticket_id, sender, message, created_at)
            VALUES (?, 'customer', ?, ?)
            """,
            (
                ticket["id"],
                text,
                now
            )
        )

        # A customer's new message reopens the ticket.

        db.execute(
            """
            UPDATE tickets
            SET status='yeni',
                updated_at=?
            WHERE id=?
            """,
            (
                now,
                ticket["id"]
            )
        )

    return {
        "ok": True,
        "status": "yeni"
    }


# ==================================================
# EXPERT DASHBOARD
# ==================================================

@app.get("/uzman", response_class=HTMLResponse)
def expert(request: Request):

    if request.session.get("admin") != ADMIN_USERNAME:

        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "csrf": csrf_token(request),
                "error": (
                    request.query_params.get("hata") == "1"
                )
            }
        )

    with connection() as db:

        tickets = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM tickets
                ORDER BY
                    (status = 'cozuldu'),
                    updated_at DESC,
                    id DESC
                LIMIT 200
                """
            ).fetchall()
        ]

        counts = {
            row["status"]: row["c"]
            for row in db.execute(
                """
                SELECT status, COUNT(*) AS c
                FROM tickets
                GROUP BY status
                """
            )
        }

        recent_messages = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM messages
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
        ]

        total_messages = db.execute(
            """
            SELECT COUNT(*)
            FROM messages
            """
        ).fetchone()[0]

    return templates.TemplateResponse(
        request,
        "expert.html",
        {
            "tickets": tickets,
            "counts": counts,
            "recent_messages": recent_messages,
            "total_messages": total_messages,
            "csrf": csrf_token(request)
        }
    )


# ==================================================
# EXPERT AUTHENTICATION
# ==================================================

@app.post("/uzman/giris")
def expert_login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form("")
):

    throttle(request, "admin_login", 8, 300)

    verify_csrf(request, csrf)

    valid_username = hmac.compare_digest(
        username,
        ADMIN_USERNAME
    )

    valid_password = check_password(password)

    if not (valid_username and valid_password):

        time.sleep(0.4)

        return RedirectResponse(
            "/uzman?hata=1",
            status_code=303
        )

    request.session.clear()
    request.session["admin"] = ADMIN_USERNAME

    csrf_token(request)

    return RedirectResponse(
        "/uzman",
        status_code=303
    )


@app.post("/uzman/cikis")
def expert_logout(
    request: Request,
    csrf: str = Form("")
):

    admin_or_401(request)
    verify_csrf(request, csrf)

    request.session.clear()

    return RedirectResponse(
        "/uzman",
        status_code=303
    )


# ==================================================
# EXPERT CONVERSATION PAGE
# ==================================================

@app.get(
    "/uzman/gorusme/{ticket_id}",
    response_class=HTMLResponse
)
def expert_conversation(
    request: Request,
    ticket_id: int
):

    admin_or_401(request)

    with connection() as db:

        ticket = db.execute(
            """
            SELECT *
            FROM tickets
            WHERE id=?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Görüşme bulunamadı."
            )

    return templates.TemplateResponse(
        request,
        "conversation.html",
        {
            "ticket": dict(ticket),
            "csrf": csrf_token(request)
        }
    )


# ==================================================
# EXPERT CONVERSATION API
# ==================================================

@app.get("/uzman/api/gorusme/{ticket_id}")
def expert_get_messages(
    request: Request,
    ticket_id: int
):

    admin_or_401(request)

    throttle(
        request,
        "expert_poll",
        120,
        60
    )

    with connection() as db:

        ticket = db.execute(
            """
            SELECT *
            FROM tickets
            WHERE id=?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Görüşme bulunamadı."
            )

        messages = get_conversation(
            db,
            ticket_id
        )

    return {
        "status": ticket["status"],
        "question": ticket["question"],
        "messages": messages,
        "expert_reply": ticket["expert_reply"] or ""
    }


# ==================================================
# EXPERT SEND MESSAGE
# ==================================================

@app.post("/uzman/api/gorusme/{ticket_id}/yanit")
def expert_send_message(
    request: Request,
    ticket_id: int,
    answer: str = Form(...),
    status: str = Form("inceleniyor"),
    csrf: str = Form("")
):

    admin_or_401(request)
    verify_csrf(request, csrf)

    throttle(request, "expert_send", 30, 60)

    answer = answer.strip()

    if not answer or len(answer) > 10000:
        raise HTTPException(
            status_code=422,
            detail="Geçerli bir mesaj yazın."
        )

    # The conversation cannot be closed
    # through an ordinary message.

    if status != "inceleniyor":
        raise HTTPException(
            status_code=422,
            detail=(
                "Görüşmeyi sonlandırmak için "
                "'Görüşmeyi Sonlandır' butonunu kullanın."
            )
        )

    now = utc_now()

    with connection() as db:

        ticket = db.execute(
            """
            SELECT id, status
            FROM tickets
            WHERE id=?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Görüşme bulunamadı."
            )

        if ticket["status"] == "cozuldu":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Bu görüşme kapatılmış. "
                    "Müşteri yeni mesaj gönderirse yeniden açılır."
                )
            )

        db.execute(
            """
            INSERT INTO conversation_messages
            (ticket_id, sender, message, created_at)
            VALUES (?, 'expert', ?, ?)
            """,
            (
                ticket_id,
                answer,
                now
            )
        )

        db.execute(
            """
            UPDATE tickets
            SET status='inceleniyor',
                expert_reply=?,
                updated_at=?
            WHERE id=?
            """,
            (
                answer,
                now,
                ticket_id
            )
        )

        db.execute(
            """
            INSERT INTO expert_history
            (ticket_id, reply, status, created_at)
            VALUES (?, ?, 'inceleniyor', ?)
            """,
            (
                ticket_id,
                answer,
                now
            )
        )

    return {
        "ok": True,
        "status": "inceleniyor"
    }


# ==================================================
# CLOSE CONVERSATION AND OPTIONAL LEARNING
# ==================================================

@app.post("/uzman/api/gorusme/{ticket_id}/sonlandir")
def close_conversation(
    request: Request,
    ticket_id: int,
    learn: str = Form(...),
    question: str = Form(""),
    answer: str = Form(""),
    csrf: str = Form("")
):

    admin_or_401(request)
    verify_csrf(request, csrf)

    throttle(
        request,
        "expert_close",
        20,
        60
    )

    if learn not in ("yes", "no"):
        raise HTTPException(
            status_code=422,
            detail="Geçersiz öğrenme tercihi."
        )

    if learn == "yes":
        question, answer, _ = validate_knowledge(
            question,
            answer
        )

    knowledge_id = None

    with connection() as db:

        # One transaction for knowledge approval
        # and conversation closure.

        db.execute("BEGIN IMMEDIATE")

        ticket = db.execute(
            """
            SELECT *
            FROM tickets
            WHERE id=?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Görüşme bulunamadı."
            )

        if ticket["status"] == "cozuldu":
            raise HTTPException(
                status_code=409,
                detail="Bu görüşme zaten sonlandırılmış."
            )

        if learn == "yes":

            # Only the expert-edited question and answer
            # are entered into the knowledge base.
            # The raw conversation is not imported.

            knowledge_id = insert_knowledge(
                db,
                ticket_id,
                question,
                answer
            )

        now = utc_now()

        db.execute(
            """
            UPDATE tickets
            SET status='cozuldu',
                updated_at=?
            WHERE id=?
            """,
            (
                now,
                ticket_id
            )
        )

        db.execute(
            """
            INSERT INTO expert_history
            (ticket_id, reply, status, created_at)
            VALUES (?, ?, 'cozuldu', ?)
            """,
            (
                ticket_id,
                "",
                now
            )
        )

    return {
        "ok": True,
        "status": "cozuldu",
        "learned": learn == "yes",
        "knowledge_id": knowledge_id,
        "message": (
            "Bilgi bankasına eklendi ve görüşme sonlandırıldı."
            if learn == "yes"
            else "Bilgi bankasına eklenmeden görüşme sonlandırıldı."
        )
    }


# ==================================================
# LEGACY EXPERT ENDPOINT
# ==================================================

@app.post("/uzman/yanit/{ticket_id}")
def expert_reply_legacy(
    request: Request,
    ticket_id: int,
    status: str = Form(...),
    answer: str = Form(""),
    csrf: str = Form("")
):

    admin_or_401(request)
    verify_csrf(request, csrf)

    # Do not allow the old form to bypass
    # the learning decision.

    if status == "cozuldu":
        raise HTTPException(
            status_code=422,
            detail=(
                "Görüşmeyi kapatmak için konuşma ekranındaki "
                "'Görüşmeyi Sonlandır' butonunu kullanın."
            )
        )

    if status not in ("yeni", "inceleniyor"):
        raise HTTPException(
            status_code=422,
            detail="Geçersiz durum."
        )

    answer = answer.strip()

    if len(answer) > 10000:
        raise HTTPException(
            status_code=422,
            detail="Yanıt çok uzun."
        )

    now = utc_now()

    with connection() as db:

        ticket = db.execute(
            """
            SELECT id, status
            FROM tickets
            WHERE id=?
            """,
            (ticket_id,)
        ).fetchone()

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail="Talep bulunamadı."
            )

        if ticket["status"] == "cozuldu":
            raise HTTPException(
                status_code=409,
                detail="Bu görüşme kapatılmış."
            )

        db.execute(
            """
            UPDATE tickets
            SET status=?,
                updated_at=?
            WHERE id=?
            """,
            (
                status,
                now,
                ticket_id
            )
        )

        if answer:

            db.execute(
                """
                INSERT INTO conversation_messages
                (ticket_id, sender, message, created_at)
                VALUES (?, 'expert', ?, ?)
                """,
                (
                    ticket_id,
                    answer,
                    now
                )
            )

            db.execute(
                """
                UPDATE tickets
                SET expert_reply=?
                WHERE id=?
                """,
                (
                    answer,
                    ticket_id
                )
            )

        db.execute(
            """
            INSERT INTO expert_history
            (ticket_id, reply, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                ticket_id,
                answer,
                status,
                now
            )
        )

    return RedirectResponse(
        "/uzman",
        status_code=303
    )


# ==================================================
# EXISTING KNOWLEDGE DEACTIVATION
# ==================================================

@app.post("/uzman/api/bilgi/{knowledge_id}/pasif")
def deactivate_knowledge(
    request: Request,
    knowledge_id: int,
    csrf: str = Form("")
):

    admin_or_401(request)
    verify_csrf(request, csrf)

    with connection() as db:

        cursor = db.execute(
            """
            UPDATE knowledge_base
            SET active=0,
                updated_at=?
            WHERE id=?
              AND active=1
            """,
            (
                utc_now(),
                knowledge_id
            )
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Aktif bilgi kaydı bulunamadı."
            )

    return {
        "ok": True,
        "message": "Bilgi pasifleştirildi."
    }