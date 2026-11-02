"""
VetGPT backend — FastAPI service exposing a RAG-powered pet care chat endpoint.

Run locally:
    uvicorn app.main:app --reload --port 8000

Endpoints:
    GET  /health          -> liveness check
    POST /chat            -> { "message": str, "history": [...] } -> answer + sources
    POST /reindex          -> rebuilds the FAISS index from data/knowledge_base
"""
from typing import List, Optional
import secrets

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import config
from app import rag
from app import petnova_data as petdata

app = FastAPI(
    title="PetNova API",
    description="PetNova AI pet-care chat and private pet-care workspace APIs",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None


class Source(BaseModel):
    content: str
    metadata: dict


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    try:
        answer, docs = rag.answer_query(req.message)
    except Exception:
        # Do not expose provider credentials or internal details to API clients.
        raise HTTPException(status_code=502, detail="The AI service could not generate a response. Please try again later.")

    sources = [Source(content=d.page_content, metadata=d.metadata) for d in docs]
    return ChatResponse(answer=answer, sources=sources)


@app.post("/reindex")
def reindex(x_reindex_key: Optional[str] = Header(default=None)):
    # Reindexing can consume significant resources. Disable it unless configured.
    configured_key = config.REINDEX_API_KEY
    if len(configured_key) < 32:
        raise HTTPException(status_code=503, detail="Reindexing is disabled on this deployment.")
    if not x_reindex_key or not secrets.compare_digest(x_reindex_key, configured_key):
        raise HTTPException(status_code=401, detail="Invalid reindex credentials.")
    try:
        rag.build_index()
        # Force the in-memory vectorstore to reload on next query
        rag._vectorstore = None
        return {"status": "reindexed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"reindex failed: {exc}")


# --- PetNova accounts and saved pet-care workspace ---
# This feature set is deliberately separate from /chat so the existing LLM
# chatbot continues to work even when account features are not configured.

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class PetCreate(BaseModel):
    name: str
    species: str
    breed: str = ""
    birth_date: str = ""
    weight: Optional[float] = None
    notes: str = ""


class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    birth_date: Optional[str] = None
    weight: Optional[float] = None
    notes: Optional[str] = None


class HealthRecordCreate(BaseModel):
    pet_id: int
    title: str
    record_type: str = "General"
    record_date: str
    notes: str = ""


class ReminderCreate(BaseModel):
    pet_id: Optional[int] = None
    title: str
    due_at: str
    notes: str = ""


class ReminderUpdate(BaseModel):
    completed: bool


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to access your PetNova workspace.")
    user_id = petdata.verify_token(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired. Please sign in again.")
    user = petdata.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account not found. Please sign in again.")
    return user


def _issue_session(user):
    try:
        token = petdata.create_token(user["id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"token": token, "user": user}


@app.post("/auth/register")
def register(req: RegisterRequest):
    name, email, password = req.name.strip(), req.email.strip(), req.password
    if len(name) < 2 or len(name) > 80:
        raise HTTPException(status_code=422, detail="Name must be between 2 and 80 characters.")
    if len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if len(password) < 10 or len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be between 10 and 128 characters.")
    try:
        user = petdata.register_user(name, email, password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _issue_session(user)


@app.post("/auth/login")
def login(req: LoginRequest):
    user = petdata.authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return _issue_session(user)


@app.get("/auth/me")
def who_am_i(user=Depends(current_user)):
    return {"user": user}


@app.get("/pets")
def get_pets(user=Depends(current_user)):
    return {"pets": petdata.list_pets(user["id"])}


@app.post("/pets", status_code=201)
def add_pet(req: PetCreate, user=Depends(current_user)):
    if not req.name.strip() or len(req.name) > 80:
        raise HTTPException(status_code=422, detail="Pet name must be between 1 and 80 characters.")
    if req.species not in {"Dog", "Cat", "Bird", "Rabbit", "Other"}:
        raise HTTPException(status_code=422, detail="Choose a supported species.")
    if req.weight is not None and (req.weight <= 0 or req.weight > 500):
        raise HTTPException(status_code=422, detail="Weight must be between 0 and 500 kg.")
    return {"pet": petdata.create_pet(user["id"], req.model_dump())}


@app.patch("/pets/{pet_id}")
def edit_pet(pet_id: int, req: PetUpdate, user=Depends(current_user)):
    data = req.model_dump(exclude_unset=True)
    if "species" in data and data["species"] not in {"Dog", "Cat", "Bird", "Rabbit", "Other"}:
        raise HTTPException(status_code=422, detail="Choose a supported species.")
    if "weight" in data and data["weight"] is not None and (data["weight"] <= 0 or data["weight"] > 500):
        raise HTTPException(status_code=422, detail="Weight must be between 0 and 500 kg.")
    pet = petdata.update_pet(user["id"], pet_id, data)
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found.")
    return {"pet": pet}


@app.delete("/pets/{pet_id}")
def remove_pet(pet_id: int, user=Depends(current_user)):
    if not petdata.delete_pet(user["id"], pet_id):
        raise HTTPException(status_code=404, detail="Pet not found.")
    return {"status": "deleted"}


@app.get("/health-records")
def get_health_records(pet_id: Optional[int] = None, user=Depends(current_user)):
    if pet_id is not None and not petdata.get_pet(user["id"], pet_id):
        raise HTTPException(status_code=404, detail="Pet not found.")
    return {"records": petdata.list_records(user["id"], pet_id)}


@app.post("/health-records", status_code=201)
def add_health_record(req: HealthRecordCreate, user=Depends(current_user)):
    if not req.title.strip() or len(req.title) > 120:
        raise HTTPException(status_code=422, detail="Record title must be between 1 and 120 characters.")
    try:
        record = petdata.create_record(user["id"], req.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"record": record}


@app.delete("/health-records/{record_id}")
def remove_health_record(record_id: int, user=Depends(current_user)):
    if not petdata.delete_record(user["id"], record_id):
        raise HTTPException(status_code=404, detail="Health record not found.")
    return {"status": "deleted"}


@app.get("/reminders")
def get_reminders(user=Depends(current_user)):
    return {"reminders": petdata.list_reminders(user["id"])}


@app.post("/reminders", status_code=201)
def add_reminder(req: ReminderCreate, user=Depends(current_user)):
    if not req.title.strip() or len(req.title) > 120:
        raise HTTPException(status_code=422, detail="Reminder title must be between 1 and 120 characters.")
    try:
        reminder = petdata.create_reminder(user["id"], req.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"reminder": reminder}


@app.patch("/reminders/{reminder_id}")
def edit_reminder(reminder_id: int, req: ReminderUpdate, user=Depends(current_user)):
    reminder = petdata.update_reminder(user["id"], reminder_id, req.completed)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"reminder": reminder}


@app.delete("/reminders/{reminder_id}")
def remove_reminder(reminder_id: int, user=Depends(current_user)):
    if not petdata.delete_reminder(user["id"], reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"status": "deleted"}
