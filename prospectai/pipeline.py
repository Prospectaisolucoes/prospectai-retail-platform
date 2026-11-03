"""Synthetic retail Bronze/Silver/Gold pipeline. Standard library only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMAS = {
    "customers": ("customer_id", "customer_name", "region", "updated_at"),
    "products": ("product_id", "category", "unit_price", "updated_at"),
    "orders": ("order_id", "customer_id", "product_id", "quantity", "ordered_at", "status", "updated_at"),
    "payments": ("payment_id", "order_id", "amount", "payment_status", "updated_at"),
}
KEYS = {"customers": "customer_id", "products": "product_id", "orders": "order_id", "payments": "payment_id"}
VALID_STATUSES = {"approved", "pending", "cancelled"}


def cents(value: str) -> int:
    """Convert a nonnegative decimal money string to exact integer cents."""
    from decimal import Decimal, InvalidOperation
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError("invalid_amount")
        result = int(amount * 100)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid_amount") from exc
    return result


def timestamp(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid_timestamp") from exc
    return dt.isoformat(timespec="seconds")


def positive_id(value: str) -> int:
    try:
        number = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid_id") from exc
    if number <= 0:
        raise ValueError("invalid_id")
    return number


def generate(folder: Path, orders: int = 1000, seed: int = 42) -> None:
    """Write deterministic, synthetic CSVs with one controlled invalid order."""
    if orders < 1:
        raise ValueError("orders must be positive")
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    customers = [
        {"customer_id": str(i), "customer_name": f"Customer {i:04d}",
         "region": rng.choice(["SP", "RJ", "MG", "BA", "PR"]), "updated_at": "2025-01-01T00:00:00"}
        for i in range(1, 101)
    ]
    products = [
        {"product_id": str(i), "category": rng.choice(["Electronics", "Home", "Fashion", "Sports"]),
         "unit_price": f"{rng.randrange(1500, 120001) / 100:.2f}", "updated_at": "2025-01-01T00:00:00"}
        for i in range(1, 41)
    ]
    order_rows, payment_rows = [], []
    start = datetime(2025, 1, 1)
    for i in range(1, orders + 1):
        dt = start + timedelta(days=rng.randrange(365), hours=rng.randrange(24))
        product = rng.choice(products)
        qty = rng.randrange(1, 5)
        status = rng.choices(["approved", "pending", "cancelled"], weights=[80, 12, 8])[0]
        order_rows.append({
            "order_id": str(i), "customer_id": str(rng.randrange(1, 101)),
            "product_id": product["product_id"], "quantity": str(qty),
            "ordered_at": dt.isoformat(timespec="seconds"), "status": status,
            "updated_at": (dt + timedelta(hours=2)).isoformat(timespec="seconds"),
        })
        payment_rows.append({
            "payment_id": str(i), "order_id": str(i),
            "amount": f"{cents(product['unit_price']) * qty / 100:.2f}",
            "payment_status": "paid" if status == "approved" else "unpaid",
            "updated_at": (dt + timedelta(hours=3)).isoformat(timespec="seconds"),
        })
    order_rows.append({**order_rows[0], "order_id": str(orders + 1), "customer_id": "999999"})
    for entity, rows in zip(SCHEMAS, (customers, products, order_rows, payment_rows)):
        with (folder / f"{entity}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SCHEMAS[entity])
            writer.writeheader()
            writer.writerows(rows)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS runs(
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
            status TEXT NOT NULL, raw_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0, accepted_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bronze(
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            entity TEXT NOT NULL, source_file TEXT NOT NULL,
            line_number INTEGER NOT NULL, payload TEXT NOT NULL,
            payload_hash TEXT NOT NULL, loaded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rejects(
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            entity TEXT NOT NULL, line_number INTEGER NOT NULL,
            reason TEXT NOT NULL, payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS silver_customers(
            customer_id INTEGER PRIMARY KEY, customer_name TEXT NOT NULL,
            region TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS silver_products(
            product_id INTEGER PRIMARY KEY, category TEXT NOT NULL,
            unit_price_cents INTEGER NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS silver_orders(
            order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL
                REFERENCES silver_customers(customer_id),
            product_id INTEGER NOT NULL REFERENCES silver_products(product_id),
            quantity INTEGER NOT NULL, ordered_at TEXT NOT NULL,
            status TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS silver_payments(
            payment_id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES silver_orders(order_id),
            amount_cents INTEGER NOT NULL, payment_status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        DROP VIEW IF EXISTS gold_daily_sales;
        DROP VIEW IF EXISTS gold_category_sales;
        DROP VIEW IF EXISTS gold_region_sales;
        CREATE VIEW gold_daily_sales AS
            SELECT substr(o.ordered_at, 1, 10) AS day, COUNT(*) AS orders,
                   SUM(p.paid_cents) AS revenue_cents
            FROM silver_orders o
            JOIN (SELECT order_id, SUM(amount_cents) AS paid_cents
                  FROM silver_payments WHERE payment_status = 'paid'
                  GROUP BY order_id) p ON p.order_id = o.order_id
            WHERE o.status = 'approved'
            GROUP BY substr(o.ordered_at, 1, 10);
        CREATE VIEW gold_category_sales AS
            SELECT pr.category, COUNT(*) AS orders,
                   SUM(p.paid_cents) AS revenue_cents
            FROM silver_orders o
            JOIN silver_products pr ON pr.product_id = o.product_id
            JOIN (SELECT order_id, SUM(amount_cents) AS paid_cents
                  FROM silver_payments WHERE payment_status = 'paid'
                  GROUP BY order_id) p ON p.order_id = o.order_id
            WHERE o.status = 'approved'
            GROUP BY pr.category;
        CREATE VIEW gold_region_sales AS
            SELECT c.region, COUNT(*) AS orders,
                   SUM(p.paid_cents) AS revenue_cents
            FROM silver_orders o
            JOIN silver_customers c ON c.customer_id = o.customer_id
            JOIN (SELECT order_id, SUM(amount_cents) AS paid_cents
                  FROM silver_payments WHERE payment_status = 'paid'
                  GROUP BY order_id) p ON p.order_id = o.order_id
            WHERE o.status = 'approved'
            GROUP BY c.region;
    """)
    return con


def normalize(entity: str, row: dict) -> tuple:
    if any(row.get(field) is None or not str(row[field]).strip() for field in SCHEMAS[entity]):
        raise ValueError("missing_required_value")
    key = positive_id(row[KEYS[entity]])
    updated = timestamp(row["updated_at"])
    if entity == "customers":
        return key, row["customer_name"].strip(), row["region"].strip(), updated
    if entity == "products":
        price = cents(row["unit_price"])
        if price <= 0:
            raise ValueError("invalid_unit_price")
        return key, row["category"].strip(), price, updated
    if entity == "orders":
        customer, product = positive_id(row["customer_id"]), positive_id(row["product_id"])
        qty = positive_id(row["quantity"])
        if row["status"] not in VALID_STATUSES:
            raise ValueError("invalid_order_status")
        return key, customer, product, qty, timestamp(row["ordered_at"]), row["status"], updated
    order = positive_id(row["order_id"])
    if row["payment_status"] not in {"paid", "unpaid"}:
        raise ValueError("invalid_payment_status")
    return key, order, cents(row["amount"]), row["payment_status"], updated


def check_references(con: sqlite3.Connection, entity: str, record: tuple) -> None:
    if entity == "orders":
        if not con.execute("SELECT 1 FROM silver_customers WHERE customer_id=?", (record[1],)).fetchone():
            raise ValueError("missing_customer")
        if not con.execute("SELECT 1 FROM silver_products WHERE product_id=?", (record[2],)).fetchone():
            raise ValueError("missing_product")
    elif entity == "payments":
        if not con.execute("SELECT 1 FROM silver_orders WHERE order_id=?", (record[1],)).fetchone():
            raise ValueError("missing_order")


def load(folder: Path, db: Path) -> dict[str, int]:
    """Load atomically; quarantine bad rows, preserve Bronze, upsert only newer versions."""
    counts = {"raw": 0, "rejected": 0, "accepted": 0}
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    con = connect(db)
    try:
        with con:
            con.execute("INSERT INTO runs(run_id, started_at, status) VALUES(?, ?, 'running')", (run_id, now))
            for entity, fields in SCHEMAS.items():
                with (folder / f"{entity}.csv").open(newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    if reader.fieldnames is None or set(reader.fieldnames) != set(fields) or len(reader.fieldnames) != len(fields):
                        raise ValueError(f"{entity}: invalid_schema")
                    for line_number, row in enumerate(reader, 2):
                        counts["raw"] += 1
                        payload = json.dumps(row, sort_keys=True, ensure_ascii=False)
                        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                        con.execute(
                            "INSERT INTO bronze(run_id,entity,source_file,line_number,payload,payload_hash,loaded_at) VALUES(?,?,?,?,?,?,?)",
                            (run_id, entity, f"{entity}.csv", line_number, payload, digest, now),
                        )
                        try:
                            record = normalize(entity, row)
                            check_references(con, entity, record)
                        except (ValueError, TypeError, OverflowError) as exc:
                            counts["rejected"] += 1
                            con.execute(
                                "INSERT INTO rejects(run_id,entity,line_number,reason,payload) VALUES(?,?,?,?,?)",
                                (run_id, entity, line_number, str(exc), payload),
                            )
                            continue
                        target_columns = tuple(
                            "unit_price_cents" if col == "unit_price" else
                            "amount_cents" if col == "amount" else col for col in fields
                        )
                        updates = ",".join(f"{col}=excluded.{col}" for col in target_columns if col != KEYS[entity])
                        sql = (
                            f"INSERT INTO silver_{entity} ({','.join(target_columns)}) "
                            f"VALUES ({','.join('?' for _ in record)}) "
                            f"ON CONFLICT({KEYS[entity]}) DO UPDATE SET {updates} "
                            f"WHERE excluded.updated_at > silver_{entity}.updated_at"
                        )
                        con.execute(sql, record)
                        counts["accepted"] += 1
            con.execute(
                "UPDATE runs SET ended_at=?, status='success', raw_count=?, rejected_count=?, accepted_count=? WHERE run_id=?",
                (datetime.now(timezone.utc).isoformat(), counts["raw"], counts["rejected"], counts["accepted"], run_id),
            )
        return counts
    finally:
        con.close()


def report(db: Path) -> dict:
    con = connect(db)
    try:
        return {
            "latest_run": con.execute(
                "SELECT status, raw_count, rejected_count, accepted_count FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone(),
            "gold": {
                name: con.execute(f"SELECT COALESCE(SUM(orders),0), COALESCE(SUM(revenue_cents),0) FROM {name}").fetchone()
                for name in ("gold_daily_sales", "gold_category_sales", "gold_region_sales")
            },
        }
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ProspectAI synthetic retail pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--orders", type=int, default=1000)
    gen.add_argument("--seed", type=int, default=42)
    ingestion = commands.add_parser("load")
    ingestion.add_argument("--input", type=Path, required=True)
    ingestion.add_argument("--db", type=Path, required=True)
    summary = commands.add_parser("report")
    summary.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.output, args.orders, args.seed)
        print(json.dumps({"generated_orders": args.orders, "output": str(args.output)}))
    elif args.command == "load":
        print(json.dumps(load(args.input, args.db), sort_keys=True))
    else:
        print(json.dumps(report(args.db), sort_keys=True))


if __name__ == "__main__":
    main()
