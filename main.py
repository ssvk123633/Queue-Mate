from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llm import chat
from tools import (
    book_token, get_queue_status, init_db, create_otp, verify_otp,
    register_visitor, complete_token,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import sqlite3
import os

app = FastAPI(title="Smart Queue Buddy")

# Add CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Msg(BaseModel):
    message: str
    history: list = []

class TokenRequest(BaseModel):
    name: str
    counter: str

class VisitorRequest(BaseModel):
    name: str
    phone: str
    age: int
    place: str
    counter: str

class OTPRequest(BaseModel):
    phone: str

class OTPVerifyRequest(BaseModel):
    phone: str
    otp: str

COUNTERS = [
    "Hospital - OPD", "Hospital - Emergency", "Hospital - Pharmacy",
    "Mall - Customer Service", "Mall - Parking Desk",
    "Theatre - Ticket Counter", "Police Station - Help Desk", "Police Station - Reporting",
    "Bank - Cash Counter", "Government Office - Enquiry",
    "Railway - Ticket Counter", "Bus Station - Booking",
]

init_db()

@app.post("/chat")
def chat_endpoint(m: Msg):
    try:
        reply = chat(m.message, m.history)
        return {"reply": reply, "language": "auto", "style": "multilingual-public-service"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI chat service unavailable: {exc}") from exc

@app.post("/tokens")
def token_endpoint(request: TokenRequest):
    name = request.name.strip()
    counter = request.counter.strip()
    if not name or not counter:
        raise HTTPException(status_code=400, detail="Name and counter are required")
    return book_token(name, counter)

@app.get("/queue/status")
def queue_status(token_no: int):
    if token_no < 1:
        raise HTTPException(status_code=400, detail="Invalid token number")
    return get_queue_status(token_no)

@app.get("/queue/board")
def queue_board(place: str | None = None):
    init_db()
    conn = sqlite3.connect("queue.db")
    result = []
    counters = COUNTERS
    if place:
        counters = [counter for counter in COUNTERS if counter.startswith(place + " -")]
    for counter in counters:
        waiting_row = conn.execute(
            "SELECT COUNT(*) FROM tokens WHERE status='waiting' AND counter=?", (counter,)
        ).fetchone()
        last_row = conn.execute(
            "SELECT COALESCE(MAX(token_no), 0) FROM tokens WHERE counter=?", (counter,)
        ).fetchone()
        waiting = waiting_row[0]
        last = last_row[0]
        result.append({
            "name": counter,
            "place": counter.split(" - ")[0],
            "serving": max(last - waiting, 0),
            "waiting": waiting,
        })
    conn.close()
    return {"counters": result}

@app.get("/")
@app.get("/index.html")
def frontend():
    page = Path(__file__).resolve().parent / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(page)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "ai_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "chat_style": "multilingual-public-service",
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
    }

@app.post("/visitors/register")
def visitor_register(request: VisitorRequest):
    if not request.name.strip() or not request.phone.strip() or not request.place.strip() or not request.counter.strip():
        raise HTTPException(status_code=400, detail="Name, phone, place, and counter are required")
    if not request.phone.isdigit() or len(request.phone) != 10:
        raise HTTPException(status_code=400, detail="Phone must contain 10 digits")
    if request.age < 1 or request.age > 120:
        raise HTTPException(status_code=400, detail="Age must be between 1 and 120")
    return register_visitor(request.name.strip(), request.phone.strip(), request.age, request.place.strip(), request.counter.strip())

@app.post("/otp/send")
def send_otp(request: OTPRequest):
    if not request.phone.isdigit() or len(request.phone) != 10:
        raise HTTPException(status_code=400, detail="Phone must contain 10 digits")
    otp = create_otp(request.phone)
    # Demo mode: return OTP for local testing. Replace with SMS provider in production.
    return {"sent": True, "phone_hint": "••••••" + request.phone[-4:], "demo_otp": otp}

@app.post("/otp/verify")
def verify_otp_endpoint(request: OTPVerifyRequest):
    if not verify_otp(request.phone, request.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    return {"verified": True, "phone": request.phone}

@app.post("/tokens/{token_no}/complete")
def complete_queue_token(token_no: int):
    if token_no < 1:
        raise HTTPException(status_code=400, detail="Invalid token number")
    return complete_token(token_no)

@app.get("/admin/users")
def admin_users(place: str | None = None, search: str | None = None):
    init_db()
    conn = sqlite3.connect("queue.db")
    conn.row_factory = sqlite3.Row
    query = "SELECT visitor_id, name, phone, age, place, counter, verified, created_at FROM visitors WHERE 1=1"
    params = []
    if place:
        query += " AND place=?"
        params.append(place)
    if search:
        query += " AND (name LIKE ? OR phone LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY visitor_id DESC"
    rows = conn.execute(query, params).fetchall()
    users = [dict(row) for row in rows]
    conn.close()
    return {"users": users, "count": len(users)}