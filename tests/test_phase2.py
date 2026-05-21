"""
Phase 2 — Data Pipeline Tests
Run: python -m pytest tests/test_phase2.py -v -p no:warnings
"""
import pytest
from app.utils.normalizer import normalize_name


VALID_CSV = b"""source,sku,category,product_name,price
Carrefour,SKU001,Vegetables,Fresh Tomatoes,25.99
Carrefour,SKU002,Dairy,Full Cream Milk,32.00
Spinneys,SP001,Meat,Chicken Breast 500g,89.00
"""

MISSING_COL_CSV = b"""source,sku,product_name
Carrefour,SKU001,Tomatoes
"""

ZERO_PRICE_CSV = b"""source,sku,category,product_name,price
Carrefour,SKU999,Vegetables,Bad Product,0
"""

DUPLICATE_SKU_CSV = b"""source,sku,category,product_name,price
Carrefour,DUP001,Vegetables,Tomato,20.00
Carrefour,DUP001,Vegetables,Tomato Again,21.00
"""


# ── Normalizer unit tests ──────────────────────────────────────────────────────
class TestNormalizer:
    def test_strips_units(self):
        assert "tomato" in normalize_name("Fresh Tomatoes 1kg")

    def test_removes_arabic(self):
        result = normalize_name("طماطم Fresh Tomatoes")
        assert "طماطم" not in result
        assert "tomato" in result

    def test_removes_noise_words(self):
        result = normalize_name("Premium Fresh Organic Chicken Breast")
        assert "premium" not in result
        assert "organic" not in result
        assert "chicken" in result

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_case_insensitive(self):
        assert normalize_name("BEEF STEAK") == normalize_name("beef steak")


# ── CSV upload integration tests ───────────────────────────────────────────────
async def test_upload_requires_auth(client):
    r = await client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("p.csv", VALID_CSV, "text/csv")},
    )
    assert r.status_code == 403


async def test_upload_valid_csv(auth_client):
    r = await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("products.csv", VALID_CSV, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_rows"] == 3
    assert data["errors"] == 0


async def test_upload_missing_column(auth_client):
    r = await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("bad.csv", MISSING_COL_CSV, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_rows"] == 0   # no valid rows


async def test_upload_zero_price_skipped(auth_client):
    r = await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("zero.csv", ZERO_PRICE_CSV, "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["skipped"] >= 1


async def test_upload_infile_duplicate_skipped(auth_client):
    r = await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("dup.csv", DUPLICATE_SKU_CSV, "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    # Only 1 of the 2 duplicate SKUs should be inserted
    assert data["total_rows"] <= 2
    assert data["skipped"] >= 1


async def test_list_products(auth_client):
    r = await auth_client.get("/api/v1/products/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_product_stats(auth_client):
    r = await auth_client.get("/api/v1/products/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_products" in data
    assert "sources" in data


async def test_list_products_filter_by_source(auth_client):
    r = await auth_client.get("/api/v1/products/?source=Carrefour")
    assert r.status_code == 200
    for p in r.json():
        assert p["source"] == "Carrefour"


async def test_list_products_search(auth_client):
    # Upload known data first
    await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("s.csv", VALID_CSV, "text/csv")},
    )
    r = await auth_client.get("/api/v1/products/?q=Tomato")
    assert r.status_code == 200
