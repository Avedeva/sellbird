"""FastAPI routes for the locally inferred, multi-product sales agent."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, Request, Response, status

from sellbird.hardware import detect_hardware, recommend_models
from sellbird.local_ai import LocalAIError, OllamaService
from sellbird.sales_research import ResearchError, research_prospect
from sellbird.sales_schemas import (
    BusinessProfile, CSVImportInput, CompanyInput, EmailInput, ICPProfile,
    ProductInput, ProspectDiscoveryInput, ProspectInput, ReplyInput, ResearchInput, WorkflowInput,
)
from sellbird.sales_store import DuplicateProspect, SalesStore
from sellbird.sales_workflows import SalesWorkflows, WorkflowInputError


router = APIRouter()


def _store(request: Request) -> SalesStore:
    from sellbird.workspace_home import current_home
    store = SalesStore(current_home().db_path)
    return store


async def _ready(request: Request) -> tuple[SalesStore, SalesWorkflows, OllamaService]:
    store = _store(request)
    await store.ensure()
    try:
        ai = OllamaService(store)
    except ValueError as exc:
        raise HTTPException(503, detail={"error": str(exc), "provider": "ollama-local"}) from exc
    return store, SalesWorkflows(store, ai), ai


def _offline_env() -> bool:
    return os.environ.get("SELLBIRD_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


async def _offline(store: SalesStore) -> bool:
    return _offline_env() or (await store.get_setting("offline_mode", "false")).lower() == "true"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkflowInputError):
        message = str(exc)
        return HTTPException(404 if "not found" in message.lower() else 400, detail={"error": message})
    if isinstance(exc, LocalAIError):
        return HTTPException(503, detail={"error": str(exc), "retryable": True, "provider": "ollama-local"})
    if isinstance(exc, ResearchError):
        return HTTPException(400, detail={"error": str(exc)})
    if isinstance(exc, DuplicateProspect):
        return HTTPException(409, detail={"error": str(exc)})
    if isinstance(exc, KeyError):
        return HTTPException(404, detail={"error": "Referenced company or product was not found"})
    if isinstance(exc, ValueError):
        return HTTPException(400, detail={"error": str(exc)})
    return HTTPException(500, detail={"error": "Sales-agent operation failed"})


async def _run_ai(store: SalesStore, task_type: str, payload: dict, operation):
    """Run locally now, retaining the exact request for an explicit later retry."""
    try:
        return await operation()
    except LocalAIError as exc:
        task_id = await store.save_task(f"ai:{task_type}", "queued", payload, str(exc))
        raise HTTPException(503, detail={"error": str(exc), "provider": "ollama-local",
                                         "status": "queued", "task_id": task_id,
                                         "retryable": True}) from exc


async def _retry_ai_task(store: SalesStore, workflows: SalesWorkflows, task: dict):
    args = task["result"]
    task_type = task["task_type"]
    operations = {
        "ai:business_profile": lambda: workflows.generate_profile(args["company_id"]),
        "ai:product_icp": lambda: workflows.generate_icp(args["product_id"]),
        "ai:research_summary": lambda: workflows.summarize_research(args["product_id"], args["prospect_id"]),
        "ai:buying_signals": lambda: workflows.classify_signals(args["product_id"], args["prospect_id"]),
        "ai:problem_statement": lambda: workflows.generate_problem(args["product_id"], args["prospect_id"]),
        "ai:email": lambda: workflows.generate_email(args["product_id"], args["prospect_id"], args["style"]),
        "ai:reply_classification": lambda: workflows.classify_reply(args["product_id"], args["reply_text"],
                                                                        args["sample"], args.get("prospect_id")),
    }
    operation = operations.get(task_type)
    if operation is None:
        raise HTTPException(409, detail={"error": "This task is not a retryable local AI workflow"})
    await store.update_task(task["id"], "running", args)
    try:
        result = await operation()
    except LocalAIError as exc:
        await store.update_task(task["id"], "queued", args, str(exc))
        raise HTTPException(503, detail={"error": str(exc), "provider": "ollama-local",
                                         "status": "queued", "task_id": task["id"],
                                         "retryable": True}) from exc
    except (WorkflowInputError, KeyError, ValueError) as exc:
        await store.update_task(task["id"], "failed", args, str(exc))
        raise _http_error(exc) from exc
    await store.update_task(task["id"], "completed", result)
    return {"task_id": task["id"], "status": "completed", "result": result}


@router.get("/api/health")
async def health(request: Request):
    store, _, ai = await _ready(request)
    return {"status": "ok", "application": "sellbird-local-sales-agent", "local_ai": await ai.health(),
            "database": "sqlite", "offline_mode": await _offline(store)}


@router.get("/api/system/hardware")
async def hardware():
    facts = detect_hardware()
    return {"hardware": facts, "recommendations": recommend_models(facts)}


@router.get("/api/system/models")
async def models(request: Request):
    store, _, ai = await _ready(request)
    health = await ai.health()
    installed = []
    if health["ollama_reachable"]:
        try:
            installed = await ai.tags()
        except LocalAIError:
            pass
    facts = detect_hardware()
    return {**health, "installed_models": installed,
            "recommendations": recommend_models(facts), "hardware": facts}


@router.get("/api/system/inference-logs")
async def inference_logs(request: Request, limit: int = 100):
    store, _, _ = await _ready(request)
    return {"logs": await store.inference_logs(max(1, min(limit, 500)))}


@router.get("/api/sales/offline-mode")
async def get_offline_mode(request: Request):
    store, _, ai = await _ready(request)
    return {"enabled": await _offline(store), "environment_forced": _offline_env(),
            "fresh_research_enabled": not await _offline(store), "local_ai": await ai.health()}


@router.put("/api/sales/offline-mode")
async def set_offline_mode(request: Request):
    store, _, _ = await _ready(request)
    if _offline_env():
        return Response(status_code=409, content='{"error":"Offline mode is forced by SELLBIRD_OFFLINE"}',
                        media_type="application/json")
    payload = await request.json()
    enabled = payload.get("enabled") if isinstance(payload, dict) else None
    if not isinstance(enabled, bool):
        raise HTTPException(422, detail={"error": "enabled must be a boolean"})
    await store.set_setting("offline_mode", str(enabled).lower())
    return {"enabled": enabled, "fresh_research_enabled": not enabled}


@router.get("/api/sales/overview")
async def overview(request: Request):
    store, _, ai = await _ready(request)
    return {"metrics": await store.dashboard_stats(), "local_ai": await ai.health(),
            "offline_mode": await _offline(store), "companies": await store.companies(),
            "products": await store.products(), "prospects": await store.prospects()}


@router.get("/api/sales/companies")
async def companies(request: Request):
    store, _, _ = await _ready(request)
    return {"companies": await store.companies()}


@router.post("/api/sales/companies", status_code=status.HTTP_201_CREATED)
async def create_company(payload: CompanyInput, request: Request):
    store, _, _ = await _ready(request)
    return await store.create_company(payload.model_dump())


@router.get("/api/sales/companies/{company_id}")
async def get_company(company_id: str, request: Request):
    store, _, _ = await _ready(request)
    result = await store.get_company(company_id)
    if not result:
        raise HTTPException(404, detail={"error": "Company was not found"})
    return result


@router.put("/api/sales/companies/{company_id}")
async def update_company(company_id: str, payload: CompanyInput, request: Request):
    store, _, _ = await _ready(request)
    result = await store.update_company(company_id, payload.model_dump())
    if not result:
        raise HTTPException(404, detail={"error": "Company was not found"})
    return result


@router.post("/api/sales/companies/{company_id}/generate-profile")
async def generate_profile(company_id: str, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        return await _run_ai(store, "business_profile", {"company_id": company_id},
                             lambda: workflows.generate_profile(company_id))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.put("/api/sales/companies/{company_id}/profile")
async def edit_profile(company_id: str, payload: BusinessProfile, request: Request):
    store, _, _ = await _ready(request)
    if not await store.get_company(company_id):
        raise HTTPException(404, detail={"error": "Company was not found"})
    profile = payload.model_dump()
    await store.save_profile(company_id, profile)
    return profile


@router.get("/api/sales/products")
async def products(request: Request, company_id: str | None = None):
    store, _, _ = await _ready(request)
    return {"products": await store.products(company_id)}


@router.post("/api/sales/products", status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductInput, request: Request):
    store, _, _ = await _ready(request)
    try:
        return await store.create_product(payload.model_dump())
    except (KeyError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/sales/products/{product_id}")
async def get_product(product_id: str, request: Request):
    store, _, _ = await _ready(request)
    result = await store.get_product(product_id)
    if not result:
        raise HTTPException(404, detail={"error": "Product was not found"})
    return result


@router.put("/api/sales/products/{product_id}")
async def update_product(product_id: str, payload: ProductInput, request: Request):
    store, _, _ = await _ready(request)
    if payload.company_id != (await store.get_product(product_id) or {}).get("company_id"):
        raise HTTPException(400, detail={"error": "Product company ownership cannot be changed"})
    result = await store.update_product(product_id, payload.model_dump(exclude={"company_id"}))
    if not result:
        raise HTTPException(404, detail={"error": "Product was not found"})
    return result


@router.post("/api/sales/products/{product_id}/generate-icp")
async def generate_icp(product_id: str, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        return await _run_ai(store, "product_icp", {"product_id": product_id},
                             lambda: workflows.generate_icp(product_id))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/sales/products/{product_id}/icp")
async def get_icp(product_id: str, request: Request):
    store, _, _ = await _ready(request)
    product = await store.get_product(product_id)
    if not product:
        raise HTTPException(404, detail={"error": "Product was not found"})
    return {"product_id": product_id, "icp": product.get("icp"), "generated_at": product.get("icp_generated_at")}


@router.put("/api/sales/products/{product_id}/icp")
async def edit_icp(product_id: str, payload: ICPProfile, request: Request):
    store, _, _ = await _ready(request)
    if not await store.get_product(product_id):
        raise HTTPException(404, detail={"error": "Product was not found"})
    icp = payload.model_dump()
    await store.save_icp(product_id, icp)
    return {"product_id": product_id, "icp": icp}


@router.get("/api/sales/prospects")
async def prospects(request: Request, company_id: str | None = None,
                    product_id: str | None = None):
    store, _, _ = await _ready(request)
    if product_id:
        product = await store.get_product(product_id)
        if not product or (company_id and product["company_id"] != company_id):
            raise HTTPException(400, detail={"error": "Product does not belong to the selected business"})
        company_id = product["company_id"]
    return {"prospects": await store.prospects(company_id, product_id)}


@router.post("/api/sales/prospects", status_code=status.HTTP_201_CREATED)
async def create_prospect(payload: ProspectInput, request: Request):
    store, _, _ = await _ready(request)
    try:
        return await store.create_prospect(payload.model_dump())
    except (KeyError, DuplicateProspect, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/sales/prospects/import")
async def import_prospects(request: Request):
    store, _, _ = await _ready(request)
    body = await request.json()
    try:
        payload = CSVImportInput.model_validate(body)
        company_id = payload.company_id
        if not company_id or not await store.get_company(company_id):
            raise KeyError("company_not_found")
        return await store.import_prospects(payload.csv_text, company_id)
    except (ValueError, KeyError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/sales/prospects/{prospect_id}")
async def get_prospect(prospect_id: str, request: Request, product_id: str | None = None):
    store, _, _ = await _ready(request)
    result = await store.get_prospect(prospect_id)
    if not result:
        raise HTTPException(404, detail={"error": "Prospect was not found"})
    result["research_sources"] = await store.research_sources(prospect_id)
    if product_id:
        result["artifacts"] = await store.artifacts(product_id, prospect_id)
    return result


async def _research_task(store: SalesStore, task_id: str, prospect_id: str, payload: ResearchInput):
    await store.update_task(task_id, "running")
    try:
        result = await research_prospect(store, prospect_id, max_pages=payload.max_pages,
                                         use_playwright=payload.use_playwright,
                                         offline=_offline_env() or (await store.get_setting("offline_mode", "false")).lower() == "true")
        await store.update_task(task_id, "completed", result)
    except Exception as exc:
        await store.update_task(task_id, "failed", error=str(exc))


@router.post("/api/sales/prospects/{prospect_id}/research", status_code=status.HTTP_202_ACCEPTED)
async def start_research(prospect_id: str, payload: ResearchInput, request: Request):
    store, _, _ = await _ready(request)
    prospect = await store.get_prospect(prospect_id)
    if not prospect:
        raise HTTPException(404, detail={"error": "Prospect was not found"})
    if await _offline(store):
        raise HTTPException(409, detail={"error": "Fresh public-web research is disabled in offline mode"})
    task_id = await store.save_task("public_web_research", "queued")
    asyncio.create_task(_research_task(store, task_id, prospect_id, payload))
    return {"task_id": task_id, "status": "queued"}


async def _run_discovery_task(store: SalesStore, task_id: str, args: dict):
    await store.update_task(task_id, "running", args)
    try:
        from sellbird.sales_discovery import discover_osm_prospects
        result = await discover_osm_prospects(store, **args)
        await store.update_task(task_id, "completed", result)
    except Exception as exc:
        await store.update_task(task_id, "failed", {"input": args}, str(exc))


@router.post("/api/sales/discover", status_code=status.HTTP_202_ACCEPTED)
async def start_prospect_discovery(payload: ProspectDiscoveryInput, request: Request):
    """Queue a free OpenStreetMap search and import sourced business records."""
    store = _store(request)
    await store.ensure()
    if await _offline(store):
        raise HTTPException(409, detail={"error": "Public prospect discovery is disabled in offline mode"})
    product = await store.get_product(payload.product_id)
    if not product or product["company_id"] != payload.company_id:
        raise HTTPException(400, detail={"error": "Select a product belonging to the chosen business"})
    from sellbird.sales_discovery import supported_osm_term
    if not supported_osm_term(payload.term):
        raise HTTPException(400, detail={
            "error": "OpenStreetMap does not map that business category. Try roofer, plumber, HVAC, "
                     "electrician, dentist, lawyer, contractor, or landscaper."
        })
    args = payload.model_dump()
    task_id = await store.save_task("public_osm_discovery", "queued", args)
    asyncio.create_task(_run_discovery_task(store, task_id, args))
    return {"task_id": task_id, "status": "queued", "provider": "OpenStreetMap"}


@router.get("/api/sales/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    store, _, _ = await _ready(request)
    result = await store.get_task(task_id)
    if not result:
        raise HTTPException(404, detail={"error": "Task was not found"})
    return result


@router.get("/api/sales/tasks")
async def list_tasks(request: Request, status_filter: str | None = None, limit: int = 100):
    store, _, _ = await _ready(request)
    return {"tasks": await store.tasks(status_filter, limit)}


@router.post("/api/sales/tasks/{task_id}/retry")
async def retry_task(task_id: str, request: Request):
    store, workflows, _ = await _ready(request)
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(404, detail={"error": "Task was not found"})
    return await _retry_ai_task(store, workflows, task)


@router.get("/api/sales/prospects/{prospect_id}/research")
async def get_research(prospect_id: str, request: Request):
    store, _, _ = await _ready(request)
    if not await store.get_prospect(prospect_id):
        raise HTTPException(404, detail={"error": "Prospect was not found"})
    return {"sources": await store.research_sources(prospect_id)}


@router.post("/api/sales/prospects/{prospect_id}/analyze-research")
async def analyze_research(prospect_id: str, payload: WorkflowInput, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        args = {"product_id": payload.product_id, "prospect_id": prospect_id}
        return await _run_ai(store, "research_summary", args,
                             lambda: workflows.summarize_research(**args))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/sales/prospects/{prospect_id}/classify-signals")
async def classify_signals(prospect_id: str, payload: WorkflowInput, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        args = {"product_id": payload.product_id, "prospect_id": prospect_id}
        return await _run_ai(store, "buying_signals", args,
                             lambda: workflows.classify_signals(**args))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/sales/prospects/{prospect_id}/generate-problem")
async def generate_problem(prospect_id: str, payload: WorkflowInput, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        args = {"product_id": payload.product_id, "prospect_id": prospect_id}
        return await _run_ai(store, "problem_statement", args,
                             lambda: workflows.generate_problem(**args))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/sales/prospects/{prospect_id}/score")
async def score_prospect(prospect_id: str, payload: WorkflowInput, request: Request):
    _, workflows, _ = await _ready(request)
    try:
        return await workflows.score(payload.product_id, prospect_id)
    except WorkflowInputError as exc:
        raise _http_error(exc) from exc


@router.post("/api/sales/prospects/{prospect_id}/generate-email")
async def generate_email(prospect_id: str, payload: EmailInput, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        args = {"product_id": payload.product_id, "prospect_id": prospect_id, "style": payload.style}
        return await _run_ai(store, "email", args, lambda: workflows.generate_email(**args))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/sales/conversations/classify")
async def classify_reply(payload: ReplyInput, request: Request):
    store, workflows, _ = await _ready(request)
    try:
        args = {"product_id": payload.product_id, "reply_text": payload.reply_text,
                "sample": payload.sample, "prospect_id": payload.prospect_id}
        return await _run_ai(store, "reply_classification", args,
                             lambda: workflows.classify_reply(
                                 product_id=args["product_id"], reply=args["reply_text"],
                                 sample=args["sample"], prospect_id=args["prospect_id"]))
    except (WorkflowInputError, LocalAIError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/sales/conversations/samples")
async def sample_conversations(request: Request, product_id: str | None = None):
    store, _, _ = await _ready(request)
    return {"conversations": await store.sample_conversations(product_id)}


@router.get("/api/sales/artifacts")
async def artifacts(request: Request, product_id: str | None = None,
                    prospect_id: str | None = None, workflow: str | None = None):
    store, _, _ = await _ready(request)
    return {"artifacts": await store.artifacts(product_id, prospect_id, workflow)}


@router.post("/api/sales/prospects/{prospect_id}/index-research")
async def index_research(prospect_id: str, request: Request):
    store, _, _ = await _ready(request)
    prospect = await store.get_prospect(prospect_id)
    if not prospect:
        raise HTTPException(404, detail={"error": "Prospect was not found"})
    try:
        from sellbird.local_embeddings import LocalEmbedder
        embedder = LocalEmbedder()
        sources = await store.research_sources(prospect_id)
        if not sources:
            raise HTTPException(409, detail={"error": "Research the prospect before indexing it"})
        vectors = embedder.embed([row["extracted_text"] for row in sources])
        for row, vector in zip(sources, vectors):
            await store.save_embedding(row["id"], str(embedder.path), vector)
        return {"indexed": len(sources), "model_path": str(embedder.path), "network_downloads": False}
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        from sellbird.local_embeddings import LocalEmbeddingError
        if isinstance(exc, LocalEmbeddingError):
            raise HTTPException(409, detail={"error": str(exc)}) from exc
        raise HTTPException(500, detail={"error": "Local embedding failed"}) from exc

