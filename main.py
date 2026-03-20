from fastapi import FastAPI, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import razorpay
import io
import random
import string
import hashlib
import os

from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# DATABASE
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DATABASE ----------------
DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True)
    password = Column(String)

class Token(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"))

Base.metadata.create_all(bind=engine)

# ---------------- RAZORPAY ----------------
RAZORPAY_KEY_ID = os.getenv("rzp_test_STXYkGXEsjoOlw")
RAZORPAY_SECRET = os.getenv("BzbxKlVdnAxDTLAX47p0Qae4")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_SECRET))

# ---------------- FUNCTIONS ----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def generate_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def create_pdf(text):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    content = []
    for line in text.split("\n"):
        content.append(Paragraph(line, styles["Normal"]))

    doc.build(content)
    buffer.seek(0)
    return buffer

# ---------------- ROUTES ----------------

@app.get("/")
def home():
    return {"status": "Simple SaaS Running 🚀"}

# 🔐 REGISTER
@app.post("/register")
def register(data: dict):
    db = SessionLocal()

    existing = db.query(User).filter(User.email == data["email"]).first()
    if existing:
        db.close()
        return {"status": "user_exists"}

    user = User(
        email=data["email"],
        password=hash_password(data["password"])
    )

    db.add(user)
    db.commit()
    db.close()

    return {"status": "registered"}

# 🔐 LOGIN
@app.post("/login")
def login(data: dict):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data["email"]).first()

    if not user or not verify_password(data["password"], user.password):
        db.close()
        return {"status": "failed"}

    db.close()
    return {"status": "success", "user_id": user.id}

# 💳 CREATE ORDER
@app.post("/create-order")
def create_order():
    order = client.order.create({
        "amount": 2900,
        "currency": "INR",
        "payment_capture": 1
    })
    return order

# 💰 VERIFY PAYMENT
@app.post("/verify-payment")
async def verify_payment(data: dict):
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        })

        token = generate_token()

        db = SessionLocal()
        db_token = Token(token=token, user_id=data["user_id"])
        db.add(db_token)
        db.commit()
        db.close()

        return {"status": "success", "token": token}

    except Exception as e:
        return {"status": "failed", "error": str(e)}

# 📤 UPLOAD
@app.post("/upload")
async def upload(file: UploadFile = File(...), user_id: int = Header(None)):

    db = SessionLocal()
    token = db.query(Token).filter(Token.user_id == user_id).first()
    db.close()

    if not token:
        return {"error": "Payment Required"}

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    output = f"""
IMPORTANT QUESTIONS:
1. Define main concept
2. Explain key features
3. Write short note
4. Advantages and disadvantages
5. Long answer question

SHORT NOTES:
{text[:500]}

REVISION POINTS:
- Key topics revise karo
- Important definitions yaad karo
"""

    pdf = create_pdf(output)

    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=notes.pdf"}
    )

# 📊 ADMIN
# ---------------- ADMIN ----------------
@app.get("/admin/stats")
def admin_stats():

    db = SessionLocal()

    total_users = db.query(User).count()
    paid_users = db.query(Token).count()

    revenue = paid_users * 29  # ₹29 per user

    db.close()

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "revenue": revenue
    }