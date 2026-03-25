"""Database table creation and helper functions using raw sqlite3."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import settings


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    db_path = settings.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_tables():
    """Create all tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL DEFAULT '',
            user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'uploading',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            results_json TEXT,
            total_items INTEGER,
            verklysing_matches INTEGER,
            bc_matches INTEGER,
            gaps_total INTEGER,
            gaps_high INTEGER,
            output_path TEXT,
            api_calls INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            elapsed_seconds REAL,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS product_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            description TEXT NOT NULL,
            unit TEXT DEFAULT 'STK',
            unit_price REAL,
            category TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_product_catalog_sku ON product_catalog(sku);
        CREATE INDEX IF NOT EXISTS idx_product_catalog_category ON product_catalog(category);

        CREATE TABLE IF NOT EXISTS analysis_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


# --- User helpers ---

def create_user(email: str, name: str, password_hash: str, is_admin: bool = False) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        (email, name, password_hash, int(is_admin)),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id: int):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def user_count() -> int:
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


# --- Analysis helpers ---

def create_analysis(project_name: str, user_id: int) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO analyses (project_name, user_id, status) VALUES (?, ?, 'uploading')",
        (project_name, user_id),
    )
    conn.commit()
    analysis_id = cur.lastrowid
    conn.close()
    return analysis_id


def get_analysis(analysis_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT a.*, u.name as user_name, u.email as user_email "
        "FROM analyses a JOIN users u ON a.user_id = u.id "
        "WHERE a.id = ?",
        (analysis_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_analyses() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT a.*, u.name as user_name, u.email as user_email "
        "FROM analyses a JOIN users u ON a.user_id = u.id "
        "ORDER BY a.created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_analysis(analysis_id: int, **kwargs):
    conn = get_db()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [analysis_id]
    conn.execute(f"UPDATE analyses SET {sets} WHERE id = ?", values)
    conn.commit()
    conn.close()


def complete_analysis(analysis_id: int, results: dict):
    """Save final results to the analysis row."""
    conn = get_db()
    conn.execute(
        """UPDATE analyses SET
            status = 'done',
            completed_at = ?,
            results_json = ?,
            total_items = ?,
            verklysing_matches = ?,
            bc_matches = ?,
            gaps_total = ?,
            gaps_high = ?,
            output_path = ?,
            api_calls = ?,
            cost_usd = ?,
            elapsed_seconds = ?
        WHERE id = ?""",
        (
            datetime.now().isoformat(),
            json.dumps(results, ensure_ascii=False),
            results.get("total_items", 0),
            results.get("verklysing_matches", 0),
            results.get("bc_matches", 0),
            results.get("gaps_total", 0),
            results.get("gaps_high", 0),
            results.get("output_path", ""),
            results.get("api_stats", {}).get("api_calls", 0),
            results.get("api_stats", {}).get("cost_usd", 0.0),
            results.get("elapsed_seconds", 0.0),
            analysis_id,
        ),
    )
    conn.commit()
    conn.close()


def fail_analysis(analysis_id: int, error_message: str):
    conn = get_db()
    conn.execute(
        "UPDATE analyses SET status = 'error', error_message = ? WHERE id = ?",
        (error_message, analysis_id),
    )
    conn.commit()
    conn.close()


# --- Analysis files helpers ---

def add_analysis_file(analysis_id: int, file_type: str, filename: str, file_path: str, file_size: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO analysis_files (analysis_id, file_type, filename, file_path, file_size) VALUES (?, ?, ?, ?, ?)",
        (analysis_id, file_type, filename, file_path, file_size),
    )
    conn.commit()
    conn.close()


def get_analysis_files(analysis_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM analysis_files WHERE analysis_id = ? ORDER BY file_type",
        (analysis_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analysis_file(analysis_id: int, file_type: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM analysis_files WHERE analysis_id = ? AND file_type = ?",
        (analysis_id, file_type),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# --- Product catalog helpers ---

def import_catalog_csv(csv_path: str) -> int:
    """Import product catalog from CSV. Replaces all existing catalog data."""
    import csv

    conn = get_db()
    conn.execute("DELETE FROM product_catalog")

    count = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="|")
        batch = []
        for row in reader:
            price = None
            try:
                price = float(row.get("ein_verd", "").replace(",", "."))
            except (ValueError, TypeError):
                pass

            batch.append((
                row.get("nr", "").strip(),
                row.get("lysing", "").strip().strip('"'),
                row.get("grunn_maelieining", "STK").strip(),
                price,
                row.get("kodi_yfirflokks_voru", "").strip(),
            ))
            count += 1

            if len(batch) >= 500:
                conn.executemany(
                    "INSERT INTO product_catalog (sku, description, unit, unit_price, category) VALUES (?, ?, ?, ?, ?)",
                    batch,
                )
                batch = []

        if batch:
            conn.executemany(
                "INSERT INTO product_catalog (sku, description, unit, unit_price, category) VALUES (?, ?, ?, ?, ?)",
                batch,
            )

    conn.commit()
    conn.close()
    return count


def get_catalog_stats() -> dict:
    """Get product catalog statistics."""
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM product_catalog").fetchone()[0]
        categories = conn.execute("SELECT COUNT(DISTINCT category) FROM product_catalog").fetchone()[0]
        with_price = conn.execute("SELECT COUNT(*) FROM product_catalog WHERE unit_price IS NOT NULL AND unit_price > 0").fetchone()[0]
        imported = conn.execute("SELECT MAX(imported_at) FROM product_catalog").fetchone()[0]
    except Exception:
        conn.close()
        return {"count": 0, "categories": 0, "with_price": 0, "imported_at": None}
    conn.close()
    return {"count": count, "categories": categories, "with_price": with_price, "imported_at": imported}


def get_catalog_products() -> list[dict]:
    """Get all products from the catalog."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM product_catalog ORDER BY category, sku").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_catalog(query: str, limit: int = 50) -> list[dict]:
    """Search catalog by SKU or description."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM product_catalog WHERE sku LIKE ? OR description LIKE ? LIMIT ?",
        (f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_catalog_categories() -> list[dict]:
    """Get all categories with product counts."""
    conn = get_db()
    rows = conn.execute(
        "SELECT category, COUNT(*) as count FROM product_catalog GROUP BY category ORDER BY category"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
