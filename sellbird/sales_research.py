"""Robots-aware, bounded public-site research with a persistent offline cache."""

from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from sellbird.public_http import UnsafeURLError, public_http_client
from sellbird.sales_store import SalesStore


USER_AGENT = "SellbirdLocalResearchBot/1.0"
MAX_TEXT_CHARS = 20000
PAGE_DELAY_SECONDS = 0.6


class ResearchError(RuntimeError):
    pass


def _normalize_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ResearchError("Prospect website is missing")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ResearchError("Research URL must be a public HTTP(S) website")
    try:
        address = ipaddress.ip_address(parts.hostname)
        if not address.is_global:
            raise ResearchError("Research URL must resolve to a public host")
    except ValueError:
        if parts.hostname.lower() in {"localhost"} or parts.hostname.lower().endswith(".localhost"):
            raise ResearchError("Local and private websites cannot be researched")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))


def _extract(html: bytes, url: str) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for item in soup.select("script,style,noscript,svg,canvas,nav,footer,header,form,iframe"):
        item.decompose()
    body = soup.body or soup
    text = " ".join(body.get_text(" ", strip=True).split())[:MAX_TEXT_CHARS]
    links = []
    # Use Scrapy's URL/link canonicalization when installed; the bounded crawl
    # still fetches every page through public_http_client, which pins DNS and
    # blocks private addresses. BeautifulSoup remains the always-available
    # extraction path for deployments without the optional Scrapy package.
    scrapy_hrefs = None
    try:
        from scrapy.http import HtmlResponse
        from scrapy.linkextractors import LinkExtractor

        response = HtmlResponse(url=url, body=html, encoding="utf-8")
        scrapy_hrefs = [link.url for link in LinkExtractor(unique=True).extract_links(response)]
    except ImportError:
        pass
    anchors = [(urljoin(url, anchor.get("href", "")), anchor.get_text(" ", strip=True))
               for anchor in soup.select("a[href]")]
    if scrapy_hrefs is not None:
        label_by_url = {href: label for href, label in anchors}
        candidates = [(href, label_by_url.get(href, "")) for href in scrapy_hrefs]
    else:
        candidates = anchors
    for href, label in candidates:
        label = " ".join(label.lower().split())
        path = urlsplit(href).path.lower()
        if any(term in (label + " " + path) for term in
               ("about", "product", "service", "solution", "career", "news", "press", "company")):
            links.append(href)
    return title[:300], text, links


async def _robots(client, root: str, target: str) -> bool:
    parts = urlsplit(root)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    try:
        response = await client.get(robots_url)
    except Exception:
        return False
    if response.status_code in {401, 403, 429, 503} or response.status_code >= 500:
        return False
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines() if response.status_code == 200 else [])
    return parser.can_fetch(USER_AGENT, target)


async def _fetch(client, root: str, target: str) -> tuple[str, str, str, list[str]]:
    if not await _robots(client, root, target):
        raise ResearchError(f"robots.txt or the site response does not permit fetching {target}")
    await asyncio.sleep(PAGE_DELAY_SECONDS)
    response = await client.get(target, headers={"User-Agent": USER_AGENT})
    if response.status_code in {401, 403, 407, 429}:
        raise ResearchError(f"The public site denied access (HTTP {response.status_code})")
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        return target, "", "", []
    title, text, links = _extract(response.content, str(response.url))
    return str(response.url), title, text, links


async def _playwright_page(client, root: str, target: str) -> tuple[str, str, str]:
    """Render JS while every network request still uses the guarded HTTP client.

    Chromium is never allowed to connect directly: requests are fulfilled from
    `public_http_client`, which pins DNS results and rejects private addresses.
    Cross-origin resources and requests outside robots.txt are blocked.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ResearchError("Playwright is unavailable; install its browser runtime to render JS sites") from exc
    target_origin = (urlsplit(target).scheme, urlsplit(target).netloc)
    resources = 0
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            raise ResearchError("Playwright Chromium is not installed; run `playwright install chromium`") from exc
        try:
            page = await browser.new_page(user_agent=USER_AGENT)

            async def fulfill(route):
                nonlocal resources
                req_url = route.request.url
                parts = urlsplit(req_url)
                if (parts.scheme, parts.netloc) != target_origin or resources >= 16:
                    await route.abort()
                    return
                resources += 1
                try:
                    if not await _robots(client, root, req_url):
                        await route.abort()
                        return
                    response = await client.get(req_url, headers={"User-Agent": USER_AGENT})
                    if response.status_code >= 400 or str(response.url) != req_url:
                        await route.abort()
                        return
                    await route.fulfill(status=response.status_code, body=response.content,
                                        content_type=response.headers.get("content-type", "application/octet-stream"))
                except Exception:
                    await route.abort()

            await page.route("**/*", fulfill)
            await page.goto(target, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(500)
            html = await page.content()
            title, text, _links = _extract(html.encode("utf-8"), target)
            return target, title, text
        finally:
            await browser.close()


async def research_prospect(store: SalesStore, prospect_id: str, *, max_pages: int = 4,
                            use_playwright: bool = False, offline: bool = False) -> dict:
    if offline:
        raise ResearchError("Fresh website research is disabled in offline mode; use the prospect's cached sources")
    prospect = await store.get_prospect(prospect_id)
    if not prospect:
        raise ResearchError("Prospect was not found")
    root = _normalize_url(prospect.get("website") or prospect.get("source_url", ""))
    parsed = urlsplit(root)
    async with public_http_client(timeout=12, headers={"User-Agent": USER_AGENT}) as client:
        try:
            initial_url, title, text, links = await _fetch(client, root, root)
        except UnsafeURLError as exc:
            raise ResearchError("Website resolves to a private or restricted address and was blocked") from exc
        if use_playwright and len(text) < 600:
            try:
                initial_url, title, rendered = await _playwright_page(client, root, root)
                if len(rendered) > len(text):
                    text = rendered
                    _, _, links = _extract(rendered.encode("utf-8"), initial_url)
            except ResearchError:
                # Preserve HTML extraction already obtained and surface its
                # status in the response; there is no alternate network route.
                pass
        if text:
            await store.save_research_source(prospect_id, initial_url, title, text)
        same_host = []
        failures = []
        for link in links:
            target = urlsplit(link)
            if (target.scheme in {"http", "https"} and target.netloc.lower() == parsed.netloc.lower()
                    and target.path and target.path != "/" and "#" not in target.path):
                clean = urlunsplit((target.scheme, target.netloc, target.path, "", ""))
                if clean not in same_host and clean != root:
                    same_host.append(clean)
        pages = [{"url": initial_url, "title": title, "characters": len(text)}] if text else []
        for target in same_host[:max(0, max_pages - 1)]:
            try:
                final_url, page_title, page_text, _ = await _fetch(client, root, target)
            except Exception as exc:
                # Per-page failures should not erase other evidence; never
                # bypass robots, access controls, or the guarded transport.
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                failures.append({"url": target, "error": str(exc)[:240]})
                continue
            if page_text:
                await store.save_research_source(prospect_id, final_url, page_title, page_text)
                pages.append({"url": final_url, "title": page_title, "characters": len(page_text)})
        return {"prospect_id": prospect_id, "pages_saved": len(pages), "pages": pages,
                "research_status": "cached" if pages else "insufficient_data",
                "warnings": failures,
                "note": "Public pages only; extracted statements remain source-attributed and unverified beyond their source."}

