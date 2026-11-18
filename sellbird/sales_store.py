"""Product-scoped SQLite persistence for the local sales-agent workflows."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return uuid.uuid4().hex


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(row: aiosqlite.Row | None) -> dict | None:
    return dict(row) if row else None


def _with_json(row: dict | None, *columns: str) -> dict | None:
    if row is None:
        return None
    for column in columns:
        raw = row.get(column)
        try:
            row[column.removesuffix("_json")] = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            row[column.removesuffix("_json")] = {}
        row.pop(column, None)
    return row


MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sales_companies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        industry TEXT NOT NULL DEFAULT '',
        website TEXT NOT NULL DEFAULT '',
        company_size TEXT NOT NULL DEFAULT '',
        target_geography TEXT NOT NULL DEFAULT '',
        business_model TEXT NOT NULL DEFAULT '',
        existing_sales_information TEXT NOT NULL DEFAULT '',
        profile_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sales_companies_name ON sales_companies(name);

    CREATE TABLE IF NOT EXISTS sales_products (
        id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL REFERENCES sales_companies(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        features_json TEXT NOT NULL DEFAULT '[]',
        benefits_json TEXT NOT NULL DEFAULT '[]',
        target_market TEXT NOT NULL DEFAULT '',
        pricing TEXT NOT NULL DEFAULT '',
        value_proposition TEXT NOT NULL DEFAULT '',
        competitive_differentiation TEXT NOT NULL DEFAULT '',
        customer_pain_points_json TEXT NOT NULL DEFAULT '[]',
        sales_positioning TEXT NOT NULL DEFAULT '',
        icp_criteria_json TEXT NOT NULL DEFAULT '{}',
        scoring_weights_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(company_id, name)
    );
    CREATE INDEX IF NOT EXISTS idx_sales_products_company ON sales_products(company_id);

    CREATE TABLE IF NOT EXISTS sales_icps (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL REFERENCES sales_products(id) ON DELETE CASCADE,
        icp_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(product_id)
    );

    CREATE TABLE IF NOT EXISTS sales_prospects (
        id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL REFERENCES sales_companies(id) ON DELETE CASCADE,
        company_name TEXT NOT NULL,
        website TEXT NOT NULL DEFAULT '',
        industry TEXT NOT NULL DEFAULT '',
        location TEXT NOT NULL DEFAULT '',
        company_description TEXT NOT NULL DEFAULT '',
        employee_count INTEGER,
        revenue_range TEXT NOT NULL DEFAULT '',
        contact_name TEXT NOT NULL DEFAULT '',
        job_title TEXT NOT NULL DEFAULT '',
        business_email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '',
        field_provenance_json TEXT NOT NULL DEFAULT '{}',
        research_status TEXT NOT NULL DEFAULT 'not_researched',
        researched_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sales_prospects_company ON sales_prospects(company_id);
    CREATE INDEX IF NOT EXISTS idx_sales_prospects_name ON sales_prospects(company_id, company_name);
    CREATE INDEX IF NOT EXISTS idx_sales_prospects_email ON sales_prospects(company_id, business_email);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_prospects_identity
        ON sales_prospects(company_id, lower(company_name), lower(contact_name), lower(business_email));

    CREATE TABLE IF NOT EXISTS sales_research_sources (
        id TEXT PRIMARY KEY,
        prospect_id TEXT NOT NULL REFERENCES sales_prospects(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ok',
        title TEXT NOT NULL DEFAULT '',
        extracted_text TEXT NOT NULL DEFAULT '',
        content_sha256 TEXT NOT NULL DEFAULT '',
        UNIQUE(prospect_id, url, content_sha256)
    );
    CREATE INDEX IF NOT EXISTS idx_sales_sources_prospect ON sales_research_sources(prospect_id, fetched_at);

    CREATE TABLE IF NOT EXISTS sales_artifacts (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL REFERENCES sales_products(id) ON DELETE CASCADE,
        prospect_id TEXT REFERENCES sales_prospects(id) ON DELETE CASCADE,
        workflow TEXT NOT NULL,
        content_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sales_artifacts_scope
        ON sales_artifacts(product_id, prospect_id, workflow, created_at);

    CREATE TABLE IF NOT EXISTS sales_signals (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL REFERENCES sales_products(id) ON DELETE CASCADE,
        prospect_id TEXT NOT NULL REFERENCES sales_prospects(id) ON DELETE CASCADE,
        category TEXT NOT NULL,
        supporting_evidence TEXT NOT NULL,
        source_url TEXT NOT NULL DEFAULT '',
        confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
        product_relevance TEXT NOT NULL DEFAULT '',
        business_implication TEXT NOT NULL DEFAULT '',
        potential_opportunity TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sales_signals_scope
        ON sales_signals(product_id, prospect_id, created_at);

    CREATE TABLE IF NOT EXISTS sales_conversations (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL REFERENCES sales_products(id) ON DELETE CASCADE,
        prospect_id TEXT REFERENCES sales_prospects(id) ON DELETE SET NULL,
        reply_text TEXT NOT NULL,
        is_sample INTEGER NOT NULL DEFAULT 0,
        classification_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sales_inference_logs (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        workflow TEXT NOT NULL,
        model TEXT NOT NULL DEFAULT '',
        endpoint TEXT NOT NULL,
        status TEXT NOT NULL,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_sales_inference_created ON sales_inference_logs(created_at DESC);

    CREATE TABLE IF NOT EXISTS sales_tasks (
        id TEXT PRIMARY KEY,
        task_type TEXT NOT NULL,
        status TEXT NOT NULL,
        result_json TEXT NOT NULL DEFAULT '{}',
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sales_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sales_embeddings (
        source_id TEXT PRIMARY KEY REFERENCES sales_research_sources(id) ON DELETE CASCADE,
        model_path TEXT NOT NULL,
        vector_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE sales_prospects ADD COLUMN external_id TEXT NOT NULL DEFAULT '';
    DROP INDEX IF EXISTS uq_sales_prospects_identity;
    CREATE UNIQUE INDEX uq_sales_prospects_identity
        ON sales_prospects(company_id, lower(company_name), lower(contact_name), lower(business_email))
        WHERE external_id = '';
    CREATE UNIQUE INDEX uq_sales_prospects_external_id
        ON sales_prospects(company_id, external_id)
        WHERE external_id <> '';
    """,
)


class DuplicateProspect(ValueError):
    """The CSV or manual input repeats a company/contact identity."""


class SalesStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.db_path, timeout=30)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield db
        finally:
            await db.close()

    async def ensure(self) -> None:
        async with self.connect() as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("""CREATE TABLE IF NOT EXISTS sales_schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)""")
            async with db.execute("SELECT COALESCE(MAX(version), 0) FROM sales_schema_migrations") as cur:
                current = (await cur.fetchone())[0]
            for version, sql in enumerate(MIGRATIONS, start=1):
                if current >= version:
                    continue
                script = ("BEGIN IMMEDIATE;\n" + sql +
                          f"\nINSERT OR IGNORE INTO sales_schema_migrations(version, applied_at) VALUES ({version}, '{_now()}');\nCOMMIT;")
                await db.executescript(script)

    async def create_company(self, data: dict) -> dict:
        now, company_id = _now(), _id()
        fields = ("name", "description", "industry", "website", "company_size",
                  "target_geography", "business_model", "existing_sales_information")
        async with self.connect() as db:
            await db.execute(
                f"INSERT INTO sales_companies(id,{','.join(fields)},created_at,updated_at) "
                f"VALUES(?,{','.join('?' for _ in fields)},?,?)",
                (company_id, *(data[k] for k in fields), now, now),
            )
            await db.commit()
        return await self.get_company(company_id)

    async def update_company(self, company_id: str, data: dict) -> dict | None:
        fields = ("name", "description", "industry", "website", "company_size",
                  "target_geography", "business_model", "existing_sales_information")
        async with self.connect() as db:
            cursor = await db.execute(
                f"UPDATE sales_companies SET {','.join(f'{k}=?' for k in fields)},updated_at=? WHERE id=?",
                (*(data[k] for k in fields), _now(), company_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                return None
        return await self.get_company(company_id)

    async def get_company(self, company_id: str) -> dict | None:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_companies WHERE id=?", (company_id,)) as cur:
                return _with_json(_decode(await cur.fetchone()), "profile_json")

    async def companies(self) -> list[dict]:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_companies ORDER BY created_at DESC") as cur:
                return [_with_json(dict(r), "profile_json") for r in await cur.fetchall()]

    async def create_product(self, data: dict) -> dict:
        now, product_id = _now(), _id()
        mapping = {
            "company_id": "company_id", "name": "name", "description": "description",
            "features": "features_json", "benefits": "benefits_json", "target_market": "target_market",
            "pricing": "pricing", "value_proposition": "value_proposition",
            "competitive_differentiation": "competitive_differentiation",
            "customer_pain_points": "customer_pain_points_json", "sales_positioning": "sales_positioning",
            "icp_criteria": "icp_criteria_json", "scoring_weights": "scoring_weights_json",
        }
        columns = ["id", *(mapping.values()), "created_at", "updated_at"]
        values = [product_id] + [
            _json(data[k]) if col.endswith("_json") else data[k]
            for k, col in mapping.items()
        ] + [now, now]
        async with self.connect() as db:
            if not await self._exists(db, "sales_companies", data["company_id"]):
                raise KeyError("company_not_found")
            await db.execute(
                f"INSERT INTO sales_products({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                values,
            )
            await db.commit()
        return await self.get_product(product_id)

    @staticmethod
    async def _exists(db, table: str, key: str) -> bool:
        async with db.execute(f"SELECT 1 FROM {table} WHERE id=?", (key,)) as cur:
            return await cur.fetchone() is not None

    async def get_product(self, product_id: str) -> dict | None:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_products WHERE id=?", (product_id,)) as cur:
                row = _decode(await cur.fetchone())
            return await self._product_details(db, row)

    async def _product_details(self, db, row: dict | None) -> dict | None:
        if not row:
            return None
        _with_json(row, "features_json", "benefits_json", "customer_pain_points_json",
                   "icp_criteria_json", "scoring_weights_json")
        async with db.execute("SELECT icp_json,created_at FROM sales_icps WHERE product_id=?", (row["id"],)) as cur:
            icp = await cur.fetchone()
        row["icp"] = json.loads(icp["icp_json"]) if icp else None
        row["icp_generated_at"] = icp["created_at"] if icp else None
        return row

    async def products(self, company_id: str | None = None) -> list[dict]:
        async with self.connect() as db:
            sql, args = "SELECT * FROM sales_products", ()
            if company_id:
                sql += " WHERE company_id=?"
                args = (company_id,)
            sql += " ORDER BY created_at DESC"
            async with db.execute(sql, args) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            return [await self._product_details(db, row) for row in rows]

    async def update_product(self, product_id: str, data: dict) -> dict | None:
        mapping = {
            "name": "name", "description": "description", "features": "features_json",
            "benefits": "benefits_json", "target_market": "target_market", "pricing": "pricing",
            "value_proposition": "value_proposition", "competitive_differentiation": "competitive_differentiation",
            "customer_pain_points": "customer_pain_points_json", "sales_positioning": "sales_positioning",
            "icp_criteria": "icp_criteria_json", "scoring_weights": "scoring_weights_json",
        }
        values = [_json(data[k]) if col.endswith("_json") else data[k] for k, col in mapping.items()]
        async with self.connect() as db:
            cur = await db.execute(
                f"UPDATE sales_products SET {','.join(f'{col}=?' for col in mapping.values())},updated_at=? WHERE id=?",
                (*values, _now(), product_id),
            )
            await db.commit()
            if not cur.rowcount:
                return None
        return await self.get_product(product_id)

    async def save_profile(self, company_id: str, profile: dict) -> None:
        async with self.connect() as db:
            await db.execute("UPDATE sales_companies SET profile_json=?,updated_at=? WHERE id=?",
                             (_json(profile), _now(), company_id))
            await db.commit()

    async def save_icp(self, product_id: str, icp: dict) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO sales_icps(id,product_id,icp_json,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(product_id) DO UPDATE SET icp_json=excluded.icp_json,created_at=excluded.created_at",
                (_id(), product_id, _json(icp), _now()),
            )
            await db.commit()

    async def create_prospect(self, data: dict) -> dict:
        now, prospect_id = _now(), _id()
        fields = ("company_id", "company_name", "website", "industry", "location", "company_description",
                  "employee_count", "revenue_range", "contact_name", "job_title", "business_email", "phone",
                  "source_url", "external_id")
        async with self.connect() as db:
            if not await self._exists(db, "sales_companies", data["company_id"]):
                raise KeyError("company_not_found")
            query = ("INSERT INTO sales_prospects(id," + ",".join(fields) +
                     ",field_provenance_json,created_at,updated_at) VALUES(" +
                     ",".join("?" for _ in range(len(fields) + 4)) + ")")
            values = tuple(None if key == "employee_count" else (data.get(key) or "") for key in fields)
            try:
                await db.execute(query, (prospect_id, *values,
                                         _json(data.get("field_provenance", {})), now, now))
            except aiosqlite.IntegrityError as exc:
                if "unique constraint" in str(exc).lower():
                    raise DuplicateProspect("A prospect with this company and contact identity already exists") from exc
                raise ValueError("Prospect data violates a storage constraint") from exc
            await db.commit()
        return await self.get_prospect(prospect_id)

    async def import_prospects(self, csv_text: str, company_id: str) -> dict:
        reader = csv.DictReader(io.StringIO(csv_text))
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row")
        aliases = {
            "company": "company_name", "company name": "company_name", "website": "website",
            "industry": "industry", "location": "location", "description": "company_description",
            "company description": "company_description", "employees": "employee_count",
            "employee count": "employee_count", "revenue": "revenue_range", "revenue range": "revenue_range",
            "contact": "contact_name", "contact name": "contact_name", "name": "contact_name",
            "title": "job_title", "job title": "job_title", "email": "business_email",
            "business email": "business_email", "phone": "phone", "source url": "source_url",
            "source_url": "source_url",
        }
        imported, skipped, errors = [], [], []
        for line, raw in enumerate(reader, start=2):
            item = {"company_id": company_id, "field_provenance": {}}
            for header, value in raw.items():
                target = aliases.get((header or "").strip().lower().replace("_", " "))
                if target and value and value.strip():
                    item[target] = value.strip()
                    item["field_provenance"][target] = "imported"
            if not item.get("company_name"):
                errors.append({"row": line, "error": "missing company name"})
                continue
            if item.get("employee_count"):
                try:
                    item["employee_count"] = int(item["employee_count"].replace(",", ""))
                except ValueError:
                    item["employee_count"] = None
            try:
                imported.append(await self.create_prospect(item))
            except DuplicateProspect:
                skipped.append({"row": line, "reason": "duplicate"})
            except (ValueError, KeyError) as exc:
                errors.append({"row": line, "error": str(exc)[:200]})
        return {"imported": len(imported), "skipped": len(skipped), "errors": errors,
                "prospects": imported, "duplicates": skipped}

    async def get_prospect(self, prospect_id: str) -> dict | None:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_prospects WHERE id=?", (prospect_id,)) as cur:
                return _with_json(_decode(await cur.fetchone()), "field_provenance_json")

    async def prospects(self, company_id: str | None = None,
                        product_id: str | None = None) -> list[dict]:
        async with self.connect() as db:
            if product_id:
                sql = ("SELECT p.*,(SELECT json_extract(a.content_json,'$.score') FROM sales_artifacts a "
                       "WHERE a.prospect_id=p.id AND a.product_id=? AND a.workflow='score' "
                       "ORDER BY a.created_at DESC LIMIT 1) AS priority_score FROM sales_prospects p")
                args = [product_id]
            else:
                sql, args = "SELECT p.*,NULL AS priority_score FROM sales_prospects p", []
            if company_id:
                sql += " WHERE p.company_id=?"
                args.append(company_id)
            sql += " ORDER BY COALESCE(priority_score,-1) DESC,p.updated_at DESC"
            async with db.execute(sql, args) as cur:
                return [_with_json(dict(r), "field_provenance_json") for r in await cur.fetchall()]

    async def save_research_source(self, prospect_id: str, url: str, title: str, text: str, status="ok") -> dict:
        fetched = _now()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        async with self.connect() as db:
            source_id = _id()
            await db.execute(
                "INSERT INTO sales_research_sources(id,prospect_id,url,fetched_at,status,title,extracted_text,content_sha256) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(prospect_id,url,content_sha256) DO UPDATE SET "
                "fetched_at=excluded.fetched_at,status=excluded.status,title=excluded.title,extracted_text=excluded.extracted_text",
                (source_id, prospect_id, url, fetched, status, title, text, digest),
            )
            await db.execute("UPDATE sales_prospects SET research_status=?,researched_at=?,updated_at=? WHERE id=?",
                             ("cached" if status == "ok" else status, fetched, fetched, prospect_id))
            await db.commit()
            async with db.execute("SELECT * FROM sales_research_sources WHERE prospect_id=? AND url=? AND content_sha256=?",
                                  (prospect_id, url, digest)) as cur:
                return dict(await cur.fetchone())

    async def research_sources(self, prospect_id: str) -> list[dict]:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_research_sources WHERE prospect_id=? ORDER BY fetched_at DESC",
                                  (prospect_id,)) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def save_artifact(self, product_id: str, prospect_id: str | None, workflow: str,
                            content: dict, evidence: list | None = None) -> dict:
        artifact_id, created = _id(), _now()
        async with self.connect() as db:
            await db.execute("INSERT INTO sales_artifacts(id,product_id,prospect_id,workflow,content_json,evidence_json,created_at) "
                              "VALUES(?,?,?,?,?,?,?)",
                             (artifact_id, product_id, prospect_id, workflow, _json(content), _json(evidence or []), created))
            await db.commit()
        return {"id": artifact_id, "product_id": product_id, "prospect_id": prospect_id,
                "workflow": workflow, "content": content, "evidence": evidence or [], "created_at": created}

    async def artifacts(self, product_id: str | None = None, prospect_id: str | None = None,
                        workflow: str | None = None) -> list[dict]:
        clauses, args = [], []
        for key, val in (("product_id", product_id), ("prospect_id", prospect_id), ("workflow", workflow)):
            if val is not None:
                clauses.append(f"{key}=?")
                args.append(val)
        sql = "SELECT * FROM sales_artifacts" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY created_at DESC"
        async with self.connect() as db:
            async with db.execute(sql, args) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        for row in rows:
            row["content"] = json.loads(row.pop("content_json"))
            row["evidence"] = json.loads(row.pop("evidence_json"))
        return rows

    async def save_signals(self, product_id: str, prospect_id: str, signals: list[dict]) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM sales_signals WHERE product_id=? AND prospect_id=?", (product_id, prospect_id))
            for signal in signals:
                await db.execute(
                    "INSERT INTO sales_signals(id,product_id,prospect_id,category,supporting_evidence,source_url,confidence,product_relevance,business_implication,potential_opportunity,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (_id(), product_id, prospect_id, signal["category"], signal["supporting_evidence"],
                     signal.get("source_url", ""), signal["confidence"], signal.get("product_relevance", ""),
                     signal.get("business_implication", ""), signal.get("potential_opportunity", ""), _now()),
                )
            await db.commit()

    async def signals(self, product_id: str, prospect_id: str) -> list[dict]:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_signals WHERE product_id=? AND prospect_id=? ORDER BY created_at DESC",
                                  (product_id, prospect_id)) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def save_conversation(self, product_id: str, prospect_id: str | None, reply: str,
                                result: dict, sample: bool) -> dict:
        conversation_id, created = _id(), _now()
        async with self.connect() as db:
            await db.execute("INSERT INTO sales_conversations(id,product_id,prospect_id,reply_text,is_sample,classification_json,created_at) "
                              "VALUES(?,?,?,?,?,?,?)",
                             (conversation_id, product_id, prospect_id, reply, int(sample), _json(result), created))
            await db.commit()
        return {"id": conversation_id, "product_id": product_id, "prospect_id": prospect_id,
                "reply_text": reply, "is_sample": sample, "classification": result, "created_at": created}

    async def sample_conversations(self, product_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM sales_conversations WHERE is_sample=1"
        args = ()
        if product_id:
            sql += " AND product_id=?"
            args = (product_id,)
        sql += " ORDER BY created_at DESC"
        async with self.connect() as db:
            async with db.execute(sql, args) as cur:
                rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["is_sample"] = bool(row["is_sample"])
            row["classification"] = json.loads(row.pop("classification_json"))
        return rows

    async def log_inference(self, workflow: str, model: str, endpoint: str,
                            status: str, duration_ms: int, error: str = "") -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO sales_inference_logs(id,created_at,workflow,model,endpoint,status,duration_ms,error) "
                              "VALUES(?,?,?,?,?,?,?,?)",
                             (_id(), _now(), workflow, model, endpoint, status, duration_ms, error[:500]))
            await db.commit()

    async def inference_logs(self, limit: int = 100) -> list[dict]:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_inference_logs ORDER BY created_at DESC LIMIT ?", (limit,)) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def dashboard_stats(self) -> dict:
        async with self.connect() as db:
            result = {}
            tables = {
                "companies": "sales_companies", "products": "sales_products", "prospects": "sales_prospects",
                "buying_signals": "sales_signals",
            }
            for key, table in tables.items():
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                    result[key] = (await cur.fetchone())[0]
            for key, workflow in (("outreach_generated", "email"), ("recent_research", "research_summary")):
                async with db.execute("SELECT COUNT(*) FROM sales_artifacts WHERE workflow=?", (workflow,)) as cur:
                    result[key] = (await cur.fetchone())[0]
            latest_score = ("SELECT COUNT(DISTINCT a.prospect_id) FROM sales_artifacts a "
                            "WHERE a.workflow='score' AND json_extract(a.content_json,'$.score')>=? "
                            "AND a.prospect_id IS NOT NULL AND NOT EXISTS ("
                            "SELECT 1 FROM sales_artifacts newer WHERE newer.workflow='score' "
                            "AND newer.product_id=a.product_id AND newer.prospect_id=a.prospect_id "
                            "AND (newer.created_at>a.created_at OR "
                            "(newer.created_at=a.created_at AND newer.rowid>a.rowid)))")
            async with db.execute(latest_score, (70,)) as cur:
                result["qualified_prospects"] = (await cur.fetchone())[0]
            async with db.execute(latest_score, (85,)) as cur:
                result["high_priority_prospects"] = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM sales_tasks WHERE status IN ('queued','running')") as cur:
                result["pending_tasks"] = (await cur.fetchone())[0]
            return result

    async def save_task(self, task_type: str, status: str, result: dict | None = None, error: str = "") -> str:
        task_id, now = _id(), _now()
        async with self.connect() as db:
            await db.execute("INSERT INTO sales_tasks(id,task_type,status,result_json,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                             (task_id, task_type, status, _json(result or {}), error[:500], now, now))
            await db.commit()
        return task_id

    async def update_task(self, task_id: str, status: str, result: dict | None = None,
                          error: str = "") -> None:
        async with self.connect() as db:
            await db.execute("UPDATE sales_tasks SET status=?,result_json=?,error=?,updated_at=? WHERE id=?",
                             (status, _json(result or {}), error[:500], _now(), task_id))
            await db.commit()

    async def get_task(self, task_id: str) -> dict | None:
        async with self.connect() as db:
            async with db.execute("SELECT * FROM sales_tasks WHERE id=?", (task_id,)) as cur:
                row = _decode(await cur.fetchone())
        if row:
            row["result"] = json.loads(row.pop("result_json"))
        return row

    async def tasks(self, status: str | None = None, limit: int = 100) -> list[dict]:
        async with self.connect() as db:
            if status:
                query = "SELECT * FROM sales_tasks WHERE status=? ORDER BY updated_at DESC LIMIT ?"
                args = (status, max(1, min(limit, 500)))
            else:
                query = "SELECT * FROM sales_tasks ORDER BY updated_at DESC LIMIT ?"
                args = (max(1, min(limit, 500)),)
            async with db.execute(query, args) as cur:
                rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["result"] = json.loads(row.pop("result_json"))
        return rows

    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.connect() as db:
            async with db.execute("SELECT value FROM sales_settings WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO sales_settings(key,value,updated_at) VALUES(?,?,?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                             (key, value, _now()))
            await db.commit()

    async def save_embedding(self, source_id: str, model_path: str, vector: list[float]) -> None:
        async with self.connect() as db:
            await db.execute("INSERT INTO sales_embeddings(source_id,model_path,vector_json,created_at) VALUES(?,?,?,?) "
                             "ON CONFLICT(source_id) DO UPDATE SET model_path=excluded.model_path,"
                             "vector_json=excluded.vector_json,created_at=excluded.created_at",
                             (source_id, model_path, _json(vector), _now()))
            await db.commit()

    async def research_index(self, prospect_id: str) -> list[dict]:
        async with self.connect() as db:
            async with db.execute("SELECT s.id,s.url,s.title,s.extracted_text,e.model_path,e.vector_json "
                                  "FROM sales_research_sources s JOIN sales_embeddings e ON e.source_id=s.id "
                                  "WHERE s.prospect_id=?", (prospect_id,)) as cur:
                rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["vector"] = json.loads(row.pop("vector_json"))
        return rows

