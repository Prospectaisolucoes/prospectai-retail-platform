import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from prospectai.pipeline import cents, connect, generate, load, report


class RetailPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.db = self.root / "warehouse.db"
        generate(self.data, orders=200, seed=42)

    def tearDown(self):
        self.temp.cleanup()

    def append(self, entity, record):
        with (self.data / f"{entity}.csv").open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames={
                "customers": ("customer_id", "customer_name", "region", "updated_at"),
                "products": ("product_id", "category", "unit_price", "updated_at"),
                "orders": ("order_id", "customer_id", "product_id", "quantity", "ordered_at", "status", "updated_at"),
                "payments": ("payment_id", "order_id", "amount", "payment_status", "updated_at"),
            }[entity])
            writer.writerow(record)

    def test_load_and_quarantine_orphan(self):
        result = load(self.data, self.db)
        self.assertEqual(result, {"raw": 541, "rejected": 1, "accepted": 540})
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM silver_orders").fetchone()[0], 200)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM bronze").fetchone()[0], 541)
            self.assertEqual(con.execute("SELECT reason FROM rejects").fetchone()[0], "missing_customer")

    def test_reprocess_is_idempotent(self):
        load(self.data, self.db)
        before = report(self.db)["gold"]
        load(self.data, self.db)
        self.assertEqual(report(self.db)["gold"], before)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM silver_payments").fetchone()[0], 200)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM runs WHERE status='success'").fetchone()[0], 2)

    def test_multiple_paid_payments_do_not_duplicate_orders(self):
        load(self.data, self.db)
        before = report(self.db)["gold"]
        with sqlite3.connect(self.db) as con:
            order_id = con.execute(
                "SELECT o.order_id FROM silver_orders o JOIN silver_payments p "
                "ON p.order_id=o.order_id WHERE o.status='approved' AND p.payment_status='paid' LIMIT 1"
            ).fetchone()[0]
            con.execute(
                "INSERT INTO silver_payments VALUES(?,?,?,?,?)",
                (99999, order_id, 1025, "paid", "2026-01-01T00:00:00"),
            )
            con.execute(
                "INSERT INTO silver_payments VALUES(?,?,?,?,?)",
                (99998, order_id, 999999, "unpaid", "2026-01-01T00:00:00"),
            )
        after = report(self.db)["gold"]
        for view in before:
            self.assertEqual(after[view][0], before[view][0], view)
            self.assertEqual(after[view][1], before[view][1] + 1025, view)

    def test_orphan_product_and_payment_quarantined(self):
        self.append("orders", {
            "order_id": "500", "customer_id": "1", "product_id": "99999",
            "quantity": "1", "ordered_at": "2025-02-01T00:00:00",
            "status": "approved", "updated_at": "2026-02-01T00:00:00",
        })
        self.append("payments", {
            "payment_id": "500", "order_id": "99999", "amount": "10.25",
            "payment_status": "paid", "updated_at": "2026-02-01T00:00:00",
        })
        result = load(self.data, self.db)
        self.assertEqual(result["rejected"], 3)
        with sqlite3.connect(self.db) as con:
            reasons = {r[0] for r in con.execute("SELECT reason FROM rejects")}
            self.assertEqual(reasons, {"missing_customer", "missing_product", "missing_order"})
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_older_update_cannot_overwrite_newer(self):
        load(self.data, self.db)
        with sqlite3.connect(self.db) as con:
            original = con.execute("SELECT status FROM silver_orders WHERE order_id=1").fetchone()[0]
        with (self.data / "orders.csv").open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows, fields = list(reader), reader.fieldnames
        rows[0]["status"] = "cancelled" if original != "cancelled" else "approved"
        rows[0]["updated_at"] = "2020-01-01T00:00:00"
        with (self.data / "orders.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        load(self.data, self.db)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT status FROM silver_orders WHERE order_id=1").fetchone()[0], original)

    def test_invalid_schema_rolls_back(self):
        (self.data / "products.csv").write_text("wrong,columns\n1,2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid_schema"):
            load(self.data, self.db)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM bronze").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def test_money_validation(self):
        self.assertEqual(cents("10.25"), 1025)
        for value in ("10.251", "-1", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cents(value)

    def test_generator_is_deterministic(self):
        other = self.root / "other"
        generate(other, orders=200, seed=42)
        for name in ("customers", "products", "orders", "payments"):
            self.assertEqual((self.data / f"{name}.csv").read_bytes(), (other / f"{name}.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
