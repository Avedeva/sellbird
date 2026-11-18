"""Record the Sellbird local sales-agent workflow in an isolated demo home.

This captures only the dashboard viewport (silent WebM) and uses the real local
Ollama service. The recording demonstrates the application's Offline Mode; it
does not claim that the operating system was disconnected from networking.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
VIDEO = ROOT / "docs" / "evidence" / "sellbird-local-sales-demo.webm"
MODEL = "qwen3:8b"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def clean_environment(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("ANTHROPIC_", "OPENAI_", "GOOGLE_", "AZURE_")):
            env.pop(key, None)
    env["SELLBIRD_HOME"] = str(home)
    env["SELLBIRD_OLLAMA_URL"] = "http://127.0.0.1:11434"
    env["SELLBIRD_OLLAMA_MODEL"] = MODEL
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env.pop("SELLBIRD_OFFLINE", None)
    return env


def embedding_snapshot() -> Path | None:
    model_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots"
    if not model_dir.is_dir():
        return None
    candidates = sorted((p for p in model_dir.iterdir() if p.is_dir() and (p / "config.json").is_file()))
    return candidates[-1] if candidates else None


def main() -> int:
    if not PYTHON.is_file():
        raise SystemExit(f"Workspace venv not found: {PYTHON}")
    if not EDGE.is_file():
        raise SystemExit(f"Microsoft Edge executable not found: {EDGE}")
    VIDEO.parent.mkdir(parents=True, exist_ok=True)
    ollama_cli = shutil.which("ollama")
    if not ollama_cli:
        raise SystemExit("Ollama CLI is not available on PATH")
    warmup = subprocess.run(
        [ollama_cli, "run", MODEL, "Return only the word READY."],
        capture_output=True, text=True, timeout=180,
    )
    if warmup.returncode:
        raise RuntimeError("The local model warm-up failed; the recording was not started")

    with tempfile.TemporaryDirectory(prefix="sellbird-video-") as temp:
        home = Path(temp) / "home"
        home.mkdir()
        shutil.copy2(ROOT / "sellbird.yaml", home / "sellbird.yaml")
        env = clean_environment(home)
        embed_path = embedding_snapshot()
        if embed_path:
            env["SELLBIRD_EMBEDDING_MODEL_PATH"] = str(embed_path)

        seed = subprocess.run(
            [str(PYTHON), str(ROOT / "scripts" / "init_demo_data.py")],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=90,
        )
        if seed.returncode:
            raise RuntimeError(f"Could not seed isolated demo data: {seed.stderr[-1200:]}")
        seed_data = json.loads(seed.stdout)
        if seed_data.get("status") != "initialized":
            raise RuntimeError("The recording home was not newly initialized with synthetic data")

        port = free_port()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        server = subprocess.Popen(
            [str(PYTHON), "-m", "sellbird", "dashboard", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        try:
            token_file = home / "data" / "dashboard-token"
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Dashboard stopped during startup; see the temporary dashboard log")
                try:
                    token = token_file.read_text(encoding="ascii").strip()
                    with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                        break
                except (OSError, UnicodeError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Timed out waiting for the isolated dashboard")

            blocked_origins: list[str] = []
            start = time.monotonic()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(EDGE), headless=True,
                    args=["--disable-background-networking", "--disable-component-update"],
                )
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    record_video_dir=str(Path(temp) / "recording"),
                    record_video_size={"width": 1440, "height": 1000},
                    reduced_motion="reduce",
                )
                origin = f"http://127.0.0.1:{port}"

                def local_only(route):
                    url = route.request.url
                    if url.startswith(origin + "/") or url.startswith(origin + "?"):
                        route.continue_()
                    elif url.startswith(("data:", "blob:", "about:")):
                        route.continue_()
                    else:
                        from urllib.parse import urlsplit
                        blocked_origins.append(urlsplit(url).netloc or url[:80])
                        route.abort()

                context.route("**/*", local_only)
                page = context.new_page()
                page.goto(f"{origin}/sales-agent#token={token}", wait_until="domcontentloaded", timeout=30000)
                page.locator("#panel-overview").wait_for(state="visible", timeout=30000)
                page.locator("#company-select option").first.wait_for(state="attached", timeout=30000)
                page.add_style_tag(content="""
                  body{padding-bottom:100px!important}
                  #demo-caption{position:fixed;z-index:99999;left:0;right:0;bottom:0;
                    box-sizing:border-box;padding:14px 26px;background:#10243aee;color:#fff;
                    border-top:2px solid #46d6b2;font:16px/1.45 system-ui,sans-serif;
                    min-height:82px}
                  #demo-caption strong{display:block;color:#65e6c0;font-size:13px;
                    letter-spacing:.08em;text-transform:uppercase;margin-bottom:3px}
                  #demo-caption span{display:block;max-width:1300px}
                  #demo-cursor{position:fixed;z-index:100000;left:0;top:0;width:16px;height:16px;
                    margin:-8px;border:2px solid #fff;border-radius:50%;pointer-events:none;
                    box-shadow:0 0 0 2px #244bdb,0 2px 8px #0009;opacity:.85}
                """)
                page.evaluate("""() => {
                  const caption=document.createElement('div'); caption.id='demo-caption';
                  caption.innerHTML='<strong>Sellbird · Local sales workflow</strong><span></span>';
                  document.body.append(caption);
                  const cursor=document.createElement('div'); cursor.id='demo-cursor'; document.body.append(cursor);
                  document.addEventListener('pointermove',e=>{cursor.style.left=e.clientX+'px';cursor.style.top=e.clientY+'px';});
                }""")

                def caption(heading: str, text: str, pause_ms: int = 2500):
                    print(f"[video] {heading}", flush=True)
                    page.locator("#demo-caption span").evaluate(
                        "(el, v) => {el.parentElement.querySelector('strong').textContent=v[0]; el.textContent=v[1]}",
                        [heading, text],
                    )
                    page.wait_for_timeout(pause_ms)

                def click_panel(name: str):
                    page.locator(f'.nav[data-panel="{name}"]').click()
                    page.locator(f"#panel-{name}.active").wait_for(state="visible")

                def click_request(locator, predicate, label: str, timeout: int = 420000):
                    for attempt in range(2):
                        with page.expect_response(predicate, timeout=timeout) as response_info:
                            locator.click()
                        response = response_info.value
                        if response.status == 200:
                            print(f"[video] Completed: {label}", flush=True)
                            return response
                        if attempt == 0 and response.status in {408, 429, 500, 502, 503, 504}:
                            caption(label, "The local service returned a temporary error; the dashboard action is being retried once.", 3500)
                            continue
                        raise RuntimeError(f"{label} returned HTTP {response.status}: {response.text()[:600]}")
                    raise RuntimeError(f"{label} failed after one dashboard retry")

                def run_ai_button(button_selector: str, response_suffix: str, output_selector: str,
                                  heading: str, caption_text: str):
                    caption(heading, caption_text, 1800)
                    click_request(
                        page.locator(button_selector),
                        lambda response: response.request.method == "POST" and response.url.endswith(response_suffix),
                        heading,
                    )
                    page.locator(output_selector).wait_for(state="visible", timeout=15000)
                    caption(heading, "Completed with the configured local Ollama model. The result is displayed in the dashboard.", 1600)

                caption("Local-first sales agent",
                        "Synthetic demo workspace · Qwen3:8b through local Ollama · no real prospects or customer messages.", 5000)
                click_panel("system")
                page.locator("#model-status").wait_for(state="visible")
                caption("Local runtime",
                        "The app reports its local model, private loopback endpoint and hardware guidance. The sales data lives in this isolated demo home.", 5000)

                click_panel("setup")
                caption("Business and product context",
                        "One fictional seller has two distinct sample products. Profile, ICP, scores and outreach are kept in their selected product context.", 4500)
                run_ai_button("#generate-profile", "/generate-profile", "#profile-output",
                              "Generate business profile", "The profile is generated from the synthetic seller details and saved locally.")
                run_ai_button("#generate-icp", "/generate-icp", "#icp-output",
                              "Product 1 · ideal customer profile", "Qwen generates an editable ICP from Appointment Flow's own product context.")
                page.locator("#product-select").select_option(label="Lead Follow-up Desk (sample)")
                page.wait_for_timeout(1400)
                caption("Product separation",
                        "Switching products loads a separate ICP and prospect context for Lead Follow-up Desk.", 3000)
                run_ai_button("#generate-icp", "/generate-icp", "#icp-output",
                              "Product 2 · ideal customer profile", "The second ICP is generated and stored under its own product ID.")

                page.locator("#product-select").select_option(label="Appointment Flow (sample)")
                page.wait_for_timeout(1200)
                click_panel("prospects")
                row = page.locator("#prospect-list tr").filter(has_text="Northwind Roofing (sample)")
                row.wait_for(state="visible", timeout=15000)
                caption("Synthetic prospect list",
                        "Every record is marked as a sample. Research notes and signals are invented fixtures, not verified public sources.", 4500)

                actions = [
                    ("Cached analysis", "/analyze-research", "Research summary",
                     "Summarize only the cached sample note; the research result must retain its synthetic provenance."),
                    ("Buying signals", "/classify-signals", "Buying-signal evidence gate",
                     "The classifier checks evidence quality. A synthetic demo source cannot be saved as a verified buying signal."),
                    ("Problem", "/generate-problem", "Evidence-aware problem hypothesis",
                     "The output is a hypothesis based on the stored sample note, not a factual claim about a real business."),
                    ("Score", "/score", "Deterministic prospect score",
                     "Qualification shows product-specific factors and available data; the numeric score is deterministic."),
                    ("Draft email", "/generate-email", "Personalized email draft",
                     "The email remains a local draft. Nothing is sent, and synthetic contact fields are fictional."),
                ]
                for button, suffix, heading, text in actions:
                    caption(heading, text, 1000)
                    click_request(
                        row.get_by_role("button", name=button, exact=True),
                        lambda response, ending=suffix: response.request.method == "POST" and response.url.endswith(ending),
                        heading,
                    )
                    page.locator("#prospect-output").wait_for(state="visible")
                    caption(heading, "Completed and saved in the local workspace. Review the result and its evidence on screen.", 1800)

                if embed_path:
                    caption("Local embedding index", "Index the saved sample research with the cached Sentence Transformers model; network model downloads are disabled.", 1200)
                    click_request(
                        row.get_by_role("button", name="Index locally", exact=True),
                        lambda response: response.request.method == "POST" and response.url.endswith("/index-research"),
                        "Local embedding index", timeout=120000,
                    )
                    caption("Local embedding index", "The cached model indexed the stored source without fetching a model from the web.", 2500)

                page.locator("#product-select").select_option(label="Lead Follow-up Desk (sample)")
                page.wait_for_timeout(900)
                click_panel("replies")
                sample = page.get_by_role("button", name="Load sample · Please remove me", exact=False)
                sample.wait_for(state="visible", timeout=15000)
                sample.click()
                caption("Reply handling", "Load the explicitly labelled sample opt-out reply and classify it locally. The record is not a real customer message.", 2500)
                click_request(
                    page.locator("#classify-reply"),
                    lambda response: response.request.method == "POST" and response.url.endswith("/api/sales/conversations/classify"),
                    "Sample reply classification",
                )
                page.locator("#reply-output").wait_for(state="visible")
                caption("Reply classification", "The model returns a local classification for the marked sample reply; no email is sent.", 3000)

                click_panel("system")
                page.locator("#inference-logs").wait_for(state="visible")
                caption("Inference trace", "Recent workflow records show model, local endpoint and status. No external browser origin was allowed during this recording.", 4500)
                page.locator("#offline-toggle").check()
                page.wait_for_function("document.querySelector('#offline-toggle').checked")
                caption("Application Offline Mode",
                        "Fresh public research and discovery are disabled by the app toggle. This demo does not assert that Windows networking was disconnected.", 6000)
                click_panel("prospects")
                row = page.locator("#prospect-list tr").filter(has_text="Brightpath Dental (sample)")
                row.wait_for(state="visible")
                caption("Local workflow while app Offline Mode is on",
                        "The UI keeps saved records available. Next, a local cached analysis runs with the application Offline Mode enabled.", 3000)
                click_request(
                    row.get_by_role("button", name="Cached analysis", exact=True),
                    lambda response: response.request.method == "POST" and response.url.endswith("/analyze-research"),
                    "Offline-mode cached analysis",
                )
                page.locator("#prospect-output").wait_for(state="visible")
                caption("Offline-mode result", "Cached analysis completed locally with the app toggle on. OS-level network state is intentionally left unverified.", 5000)

                page.wait_for_timeout(2000)
                if blocked_origins:
                    raise RuntimeError(f"The browser attempted external origins: {sorted(set(blocked_origins))}")
                video = page.video
                context.close()
                video.save_as(str(VIDEO))
                browser.close()

            elapsed = time.monotonic() - start
            print(json.dumps({
                "video": str(VIDEO),
                "duration_seconds_approx": round(elapsed),
                "bytes": VIDEO.stat().st_size,
                "synthetic_demo_workspace": True,
                "browser_external_origins": [],
                "app_offline_mode_demonstrated": True,
                "os_network_disconnect": "unverified per user instruction",
                "audio": "silent; on-screen captions",
            }, indent=2))
            return 0
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=3)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlaywrightTimeoutError as exc:
        raise SystemExit(f"Timed out waiting for the dashboard workflow: {exc}") from exc
