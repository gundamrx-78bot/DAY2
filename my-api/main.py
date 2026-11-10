import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# 로컬에선 .env를 읽고, Railway에선 Variables가 이미 들어 있음
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
FRONT_ORIGINS = [
    o.strip() for o in os.getenv("FRONT_ORIGINS", "").split(",") if o.strip()
] or ["http://localhost:5500", "http://127.0.0.1:5500"]  # 로컬 프론트 기본값

sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="my-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v")
def health2():
    return {"s": 100, "t": 200}


@app.get("/db-check")
def db_check():
    # 테이블 없이도 Supabase에 키로 접속되는지만 확인한다 (데이터는 돌려주지 않음)
    try:
        sb.auth.admin.list_users(page=1, per_page=1)
    except Exception as e:
        raise HTTPException(status_code=502, detail="Supabase 연결 실패: " + type(e).__name__)
    return {"supabase": "connected"}
