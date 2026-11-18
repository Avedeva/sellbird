"""Free public OpenStreetMap discovery imported into the product workspace."""

from __future__ import annotations

import asyncio
import time

import httpx

from sellbird.collectors.discover import (
    DiscoveryQuery,
    PROVIDERS,
    OpenStreetMap,
    is_junk,
    resolve_coordinates,
)
from sellbird.sales_store import DuplicateProspect, SalesStore
from sellbird.state import StateManager


class ProspectDiscoveryError(ValueError):
    """The local discovery source cannot answer the requested search."""


_geocode_lock = asyncio.Lock()
_overpass_lock = asyncio.Lock()
_last_geocode_at = 0.0
_last_overpass_at = 0.0


def supported_osm_term(term: str) -> bool:
    provider = PROVIDERS.get("osm")
    return bool(provider and provider._tags(term))


async def discover_osm_prospects(
    store: SalesStore,
    *,
    company_id: str,
    product_id: str,
    term: str,
    location: str,
    radius_km: int = 25,
    limit: int = 25,
) -> dict:
    """Search a single mapped trade near a geocoded place and persist results.

    OpenStreetMap supplies business listing facts only. It does not provide
    contact names, email addresses, company size, or revenue; those fields stay
    empty until the user supplies or a permitted source verifies them.
    """
    product = await store.get_product(product_id)
    if not product:
        raise ProspectDiscoveryError("The selected product was not found")
    if product["company_id"] != company_id:
        raise ProspectDiscoveryError("The selected product does not belong to this business")

    provider = PROVIDERS.get("osm")
    if provider is None:
        raise ProspectDiscoveryError("No free public discovery provider is enabled")
    if not provider._tags(term):
        raise ProspectDiscoveryError(
            "OpenStreetMap does not map that business category. Try a supported trade such as roofer, "
            "plumber, HVAC, electrician, dentist, lawyer, contractor, or landscaper."
        )

    state = StateManager(store.db_path)
    await state.init_db()
    query = DiscoveryQuery(term=term, location=location, limit=limit)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        global _last_geocode_at, _last_overpass_at
        async with _geocode_lock:
            cached = await state.get_setting(f"geo:{location.strip().lower()}")
            if not cached:
                wait = 1.1 - (time.monotonic() - _last_geocode_at)
                if wait > 0:
                    await asyncio.sleep(wait)
                _last_geocode_at = time.monotonic()
            await resolve_coordinates(state, [query], radius_km=radius_km, client=client)
        if not query.coordinate:
            raise ProspectDiscoveryError(
                f"Could not locate {location!r}. Check the place name and try again."
            )
        async with _overpass_lock:
            wait = OpenStreetMap.MIN_INTERVAL - (time.monotonic() - _last_overpass_at)
            if wait > 0:
                await asyncio.sleep(wait)
            _last_overpass_at = time.monotonic()
            businesses = await provider.fetch(client, {}, query)

    imported = []
    duplicates = 0
    filtered = 0
    for business in businesses[:limit]:
        if not business.name or is_junk(business.domain, business.name):
            filtered += 1
            continue
        provenance = {"company_name": "extracted", "source_url": "extracted"}
        for key, value in (("website", business.website), ("industry", business.category),
                           ("location", business.location), ("phone", business.phone)):
            if value:
                provenance[key] = "extracted"
        try:
            imported.append(await store.create_prospect({
                "company_id": company_id,
                "company_name": business.name[:200],
                "website": business.website[:1000],
                "industry": business.category[:200],
                "location": (business.location or location)[:300],
                "company_description": "",
                "employee_count": None,
                "revenue_range": "",
                "contact_name": "",
                "job_title": "",
                "business_email": "",
                "phone": business.phone[:100],
                "source_url": business.source_url[:2000],
                "external_id": business.external_id,
                "field_provenance": provenance,
            }))
        except DuplicateProspect:
            duplicates += 1

    return {
        "provider": "OpenStreetMap",
        "term": term,
        "location": location,
        "radius_km": radius_km,
        "found": len(businesses),
        "imported": len(imported),
        "duplicates": duplicates,
        "filtered": filtered,
        "prospects": imported,
        "coverage_note": "OSM coverage varies. Missing website, contact, size, and revenue fields are left blank.",
    }
