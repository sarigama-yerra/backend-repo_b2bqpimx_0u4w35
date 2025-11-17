import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict
from datetime import datetime

from database import db, create_document, get_documents
from schemas import (
    User, Store, Product, Sale, InventoryAlert, TransferRequest,
    LoginRequest, LoginResponse, CreateResponse, MessageResponse, ProductStock, SaleItem
)

app = FastAPI(title="Inventory Management API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "مرحبا من واجهة برمجة المخزون"}


@app.get("/test")
def test_database():
    info = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "collections": []
    }
    try:
        if db is None:
            return info
        info["database"] = "✅ Connected"
        info["collections"] = db.list_collection_names()
        return info
    except Exception as e:
        info["database"] = f"❌ Error: {str(e)}"
        return info


# Utility helpers

def _collection(name: str):
    return db[name] if db is not None else None


def _recompute_alerts() -> List[InventoryAlert]:
    products = list(_collection("product").find({})) if _collection("product") else []
    alerts: List[InventoryAlert] = []
    for p in products:
        total = sum(stock.get("qty", 0) for stock in p.get("stocks", []))
        threshold = p.get("low_threshold", 5)
        level: Optional[str] = None
        if total == 0:
            level = "out"
        elif total <= threshold:
            level = "low"
        if level:
            alerts.append(InventoryAlert(sku=p["sku"], name=p["name"], level=level, total_qty=total))
    return alerts


# Auth (demo)
@app.post("/api/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    if payload.password.strip() == "":
        raise HTTPException(status_code=400, detail="كلمة المرور مطلوبة")
    # Demo token only
    return LoginResponse(token="demo-token", user={"email": payload.email, "name": "مستخدم"})


# Stores
@app.post("/api/stores", response_model=CreateResponse)
def create_store(store: Store):
    if _collection("store") is None:
        raise HTTPException(500, "قاعدة البيانات غير متاحة")
    if _collection("store").find_one({"id": store.id}):
        raise HTTPException(400, "يوجد فرع بنفس المعرّف")
    new_id = create_document("store", store)
    return CreateResponse(id=new_id)


@app.get("/api/stores", response_model=List[Store])
def list_stores():
    coll = _collection("store")
    docs = list(coll.find({})) if coll else []
    return [Store(**{k: v for k, v in d.items() if k != "_id"}) for d in docs]


# Products
@app.post("/api/products", response_model=CreateResponse)
def create_product(product: Product):
    coll = _collection("product")
    if coll is None:
        raise HTTPException(500, "قاعدة البيانات غير متاحة")
    if coll.find_one({"sku": product.sku}):
        raise HTTPException(400, "رمز المنتج موجود مسبقًا")
    new_id = create_document("product", product)
    return CreateResponse(id=new_id)


@app.get("/api/products", response_model=List[Product])
def list_products():
    coll = _collection("product")
    docs = list(coll.find({})) if coll else []
    return [Product(**{k: v for k, v in d.items() if k != "_id"}) for d in docs]


@app.post("/api/products/transfer", response_model=MessageResponse)
def transfer_stock(req: TransferRequest):
    coll = _collection("product")
    if coll is None:
        raise HTTPException(500, "قاعدة البيانات غير متاحة")
    p = coll.find_one({"sku": req.sku})
    if not p:
        raise HTTPException(404, "المنتج غير موجود")
    stocks: List[Dict] = p.get("stocks", [])
    from_item = next((s for s in stocks if s.get("store_id") == req.from_store_id), None)
    if not from_item or from_item.get("qty", 0) < req.qty:
        raise HTTPException(400, "كمية غير كافية في الفرع المصدر")
    to_item = next((s for s in stocks if s.get("store_id") == req.to_store_id), None)
    from_item["qty"] -= req.qty
    if to_item:
        to_item["qty"] += req.qty
    else:
        stocks.append({"store_id": req.to_store_id, "qty": req.qty})
    coll.update_one({"sku": req.sku}, {"$set": {"stocks": stocks, "updated_at": datetime.utcnow()}})
    return MessageResponse(message="تم نقل الكمية بنجاح")


# Sales
@app.post("/api/sales", response_model=CreateResponse)
def create_sale(sale: Sale):
    coll_prod = _collection("product")
    coll_sale = _collection("sale")
    if coll_prod is None or coll_sale is None:
        raise HTTPException(500, "قاعدة البيانات غير متاحة")

    # Deduct stock per item from the given store
    for item in sale.items:
        p = coll_prod.find_one({"sku": item.sku})
        if not p:
            raise HTTPException(404, f"المنتج {item.sku} غير موجود")
        stocks: List[Dict] = p.get("stocks", [])
        s_item = next((s for s in stocks if s.get("store_id") == sale.store_id), None)
        if not s_item or s_item.get("qty", 0) < item.qty:
            raise HTTPException(400, f"الكمية غير كافية للمنتج {item.name}")
        s_item["qty"] -= item.qty
        coll_prod.update_one({"sku": item.sku}, {"$set": {"stocks": stocks, "updated_at": datetime.utcnow()}})

    sale_id = create_document("sale", sale)
    return CreateResponse(id=sale_id)


@app.get("/api/sales", response_model=List[Sale])
def list_sales():
    coll = _collection("sale")
    docs = list(coll.find({}).sort("timestamp", -1)) if coll else []
    return [Sale(**{k: v for k, v in d.items() if k != "_id"}) for d in docs]


# Alerts
@app.get("/api/alerts", response_model=List[InventoryAlert])
def get_alerts():
    if _collection("product") is None:
        return []
    return _recompute_alerts()


# Reports
@app.get("/api/reports/summary")
def get_summary():
    coll_sale = _collection("sale")
    total_sales = 0.0
    count_sales = 0
    if coll_sale:
        for d in coll_sale.find({}):
            total_sales += float(d.get("total", 0))
            count_sales += 1
    return {"total_sales": total_sales, "count_sales": count_sales}


# WhatsApp alert webhook placeholder (to be implemented with Business API)
@app.post("/api/alerts/whatsapp", response_model=MessageResponse)
def send_whatsapp_alert(payload: Dict[str, str]):
    # Placeholder: Integrate WhatsApp Business Cloud API here
    return MessageResponse(message="تم إرسال تنبيه واتساب (وهمي)")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
