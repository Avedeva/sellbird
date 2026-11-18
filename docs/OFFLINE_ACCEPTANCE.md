# Offline acceptance and demo runbook

## Prepare while online

1. Install Sellbird dependencies and Ollama. Pull the exact model tag, for example `ollama pull qwen3:4b`.
2. Start Ollama and confirm `ollama list` includes the selected tag.
3. Start the Sellbird dashboard and open `/sales-agent`.
4. Run `python scripts/init_demo_data.py` to seed clearly marked synthetic sample records. These are demonstration data, not actual prospects or conversations.
5. If demonstrating local embeddings, install Sentence Transformers, download `all-MiniLM-L6-v2`, and set `SELLBIRD_EMBEDDING_MODEL_PATH` as described in [Local AI Setup](LOCAL_AI_SETUP.md).
6. Verify model availability in **System & inference**. Keep the model loaded once before disconnecting if the machine is memory constrained.
7. For the offline segment, seed/import prospects and research while online. Product-scoped OpenStreetMap discovery uses public Nominatim/Overpass services and is unavailable after networking is disabled.

## Automated local-model acceptance

The opt-in integration test calls the installed local Ollama model and exercises the required workflow with two separate products. It intercepts HTTPX requests and rejects non-loopback/non-private destinations. It requires an installed Ollama daemon and real model; mocked transport unit tests are not evidence of a successful local-model acceptance run.

```powershell
$env:SELLBIRD_RUN_LOCAL_ACCEPTANCE = "1"
$env:SELLBIRD_OFFLINE = "1"
python -m pytest -q tests/acceptance/test_offline_sales_workflow.py
```

The test exercises local business profile generation, product-specific ICP generation, cached research synthesis, buying-signal classification, problem hypothesis, deterministic scoring, personalized email and sample reply classification. It checks successful local inference logs and that no request left a local/private host.

For the evaluator's final test, disconnect the computer from Wi-Fi/Ethernet or disable networking at the operating-system level after the model has downloaded. The HTTP interception is an additional application-level guard; it does not physically disconnect the host.

## Manual 5–10 minute demonstration

1. **0:00–0:45 — Start and status.** Open the Local AI Sales Agent page. Show the configured Ollama tag, hardware report, and model status.
2. **0:45–1:45 — Configure seller.** Select the synthetic business, inspect its local inputs, and generate or edit the business profile.
3. **1:45–2:45 — Compare products.** Select each synthetic product, show its distinct details and ICP, then generate or edit one product-specific ICP.
4. **2:45–4:00 — Prospect and cached research.** Select the synthetic prospect and open its labelled cached research. Keep fresh web research off for the offline segment.
5. **4:00–5:30 — Intelligence.** Generate research summary and buying signals. Point to stored source URLs and exact excerpts; if evidence is insufficient, show that status instead of claiming a signal.
6. **5:30–6:30 — Qualification.** Generate the problem hypothesis and deterministic score; show factor weights, evidence and missing fields.
7. **6:30–7:30 — Outreach and reply.** Draft an email, edit/copy it, load a labelled sample conversation, and classify the reply.
8. **7:30–8:30 — Local trace.** Show the local inference log (workflow, model, endpoint, status and duration) and queued-task retry behavior if useful.
9. **8:30–10:00 — Offline proof.** Disconnect networking, refresh the page, and repeat one local generation plus cached analysis/scoring/reply classification. Show that fresh website research is disabled and that no cloud service is involved.

## Evidence to retain for submission

- Test command, exact environment/model tag, date, and full pytest summary.
- A screenshot or log from the **System & inference** view showing a successful Ollama request to the configured private/loopback endpoint.
- A screenshot of the two product contexts and their separate ICPs.
- A screenshot of a cached-source excerpt with its stored URL and of the evidence-backed score/email.
- A short video showing the manual offline segment after network disconnection.

## Current environment record

On 2026-11-18, the full Windows suite passed after the final sales-workflow and reply-route changes: **3,523 passed, 191 skipped, 9 warnings in 267.20 seconds**. The focused workflow, local-inference, and reply-route selection passed **13 tests**; the local embedding route acceptance passed separately. Compileall, JavaScript syntax, metadata parsing, `git diff --check`, and the seven-check source audit also passed. The audit made no network requests. Desktop and 390 × 844 mobile browser QA passed separately; see [Testing](TESTING.md) and [browser evidence](evidence/README.md).

The installed `qwen3:8b` model is Q4_K_M; a direct local Ollama CLI prompt completed. The application-level test passed: **1 passed in 425.90 seconds**, with eight successful local inference records and no external HTTPX attempts. The silent, captioned UI recording is [`sellbird-local-sales-demo.webm`](evidence/README.md), 8:42.92 long. It shows Sellbird's app Offline Mode, then runs cached analysis locally. The PC's operating-system network state was not checked, per the user's instruction to leave the OS-level offline case unverified. The HTTP guard and UI toggle are not physical network-disconnect evidence.

The local embedding index handler passed in the workspace `.venv` against the cached Sentence Transformers model with Hugging Face offline flags: **1 passed in 11.66 seconds**. It wrote a normalized 384-dimensional vector to temporary SQLite. Install the optional `local-embeddings` extra and set `SELLBIRD_EMBEDDING_MODEL_PATH` in another environment before UI indexing there.
