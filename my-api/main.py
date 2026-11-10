import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# 로컬에선 .env를 읽고, Railway에선 Variables가 이미 들어 있음
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
FRONT_ORIGINS = [
    o.strip().rstrip("/") for o in os.getenv("FRONT_ORIGINS", "").split(",") if o.strip()
] or ["http://localhost:5500", "http://127.0.0.1:5500"]  # 로컬 프론트 기본값

sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="my-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],  # 쓰는 방식만 허용
    allow_headers=["Content-Type"],
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


# ---------- 장바구니 ----------
# 가격은 항상 서버가 정한다. 화면이 보낸 가격은 믿지 않고 product_id와 수량만 받는다.
PRODUCTS = [
    {"id": "hallabong", "name": "한라봉 선물세트", "price": 25000, "emoji": "🍊", "desc": "새콤달콤 제주 한라봉 3kg"},
    {"id": "blackpork", "name": "제주 흑돼지 오겹살", "price": 38000, "emoji": "🐖", "desc": "구이용 600g 냉장"},
    {"id": "omegi", "name": "오메기떡 세트", "price": 18000, "emoji": "🍡", "desc": "쫀득한 전통 떡 12개입"},
    {"id": "choco", "name": "감귤 초콜릿", "price": 9000, "emoji": "🍫", "desc": "귤 껍질을 넣은 달콤한 초콜릿"},
    {"id": "galchi", "name": "제주 은갈치", "price": 32000, "emoji": "🐟", "desc": "손질해서 보내는 은갈치 2마리"},
    {"id": "tea", "name": "한라산 녹차", "price": 14000, "emoji": "🍵", "desc": "한라산 자락에서 키운 녹차 40g"},
]
PRODUCT_BY_ID = {p["id"]: p for p in PRODUCTS}
CART_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class AddItem(BaseModel):
    product_id: str
    qty: int = Field(1, ge=1, le=99)


class SetQty(BaseModel):
    qty: int = Field(ge=0, le=99)


def check_cart_id(cart_id: str):
    if not CART_ID_RE.match(cart_id):
        raise HTTPException(status_code=400, detail="cart_id 형식이 올바르지 않아요")


def check_product(product_id: str):
    if product_id not in PRODUCT_BY_ID:
        raise HTTPException(status_code=404, detail="없는 상품이에요")


def db_error(e: Exception):
    msg = str(e)
    if "cart_items" in msg and ("PGRST205" in msg or "does not exist" in msg or "schema cache" in msg):
        raise HTTPException(status_code=503, detail="Supabase에 cart_items 테이블이 없어요. cart.sql을 먼저 실행해 주세요")
    raise HTTPException(status_code=502, detail="Supabase 오류: " + type(e).__name__)


def cart_view(cart_id: str):
    rows = sb.table("cart_items").select("product_id,qty").eq("cart_id", cart_id).execute().data
    qty_by_id = {r["product_id"]: r["qty"] for r in rows}
    items = []
    for p in PRODUCTS:  # 상품 목록 순서대로 보여 준다
        if p["id"] in qty_by_id:
            q = qty_by_id[p["id"]]
            items.append({**p, "qty": q, "subtotal": p["price"] * q})
    return {
        "items": items,
        "count": sum(i["qty"] for i in items),
        "total": sum(i["subtotal"] for i in items),
    }


@app.get("/products")
def products():
    return PRODUCTS


@app.get("/cart/{cart_id}")
def get_cart(cart_id: str):
    check_cart_id(cart_id)
    try:
        return cart_view(cart_id)
    except Exception as e:
        db_error(e)


@app.post("/cart/{cart_id}/items")
def add_item(cart_id: str, body: AddItem):
    check_cart_id(cart_id)
    check_product(body.product_id)
    try:
        cur = (
            sb.table("cart_items").select("qty")
            .eq("cart_id", cart_id).eq("product_id", body.product_id).execute().data
        )
        qty = min(99, (cur[0]["qty"] if cur else 0) + body.qty)
        sb.table("cart_items").upsert(
            {"cart_id": cart_id, "product_id": body.product_id, "qty": qty},
            on_conflict="cart_id,product_id",
        ).execute()
        return cart_view(cart_id)
    except Exception as e:
        db_error(e)


@app.patch("/cart/{cart_id}/items/{product_id}")
def set_qty(cart_id: str, product_id: str, body: SetQty):
    check_cart_id(cart_id)
    check_product(product_id)
    try:
        if body.qty == 0:
            sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()
        else:
            sb.table("cart_items").upsert(
                {"cart_id": cart_id, "product_id": product_id, "qty": body.qty},
                on_conflict="cart_id,product_id",
            ).execute()
        return cart_view(cart_id)
    except Exception as e:
        db_error(e)


@app.delete("/cart/{cart_id}/items/{product_id}")
def remove_item(cart_id: str, product_id: str):
    check_cart_id(cart_id)
    check_product(product_id)
    try:
        sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()
        return cart_view(cart_id)
    except Exception as e:
        db_error(e)


@app.delete("/cart/{cart_id}")
def clear_cart(cart_id: str):
    check_cart_id(cart_id)
    try:
        sb.table("cart_items").delete().eq("cart_id", cart_id).execute()
        return cart_view(cart_id)
    except Exception as e:
        db_error(e)
