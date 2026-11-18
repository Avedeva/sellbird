# Repeatable local demo script

Target time: 7–10 minutes after dependencies and a model are installed. The demo uses clearly marked synthetic records; it does not represent real prospects or customer interactions. Keep public discovery optional during a demo because it needs internet access and public OSM service capacity.

## Prepare once

1. Create/activate the environment and install the application as described in the [README](../README.md).
2. Install Ollama, fetch `qwen3:4b` (or a hardware-appropriate local model), and start the Ollama service.
3. Run `python scripts/init_demo_data.py`. The script creates one synthetic business, two products, sample prospects, cached sample notes, and sample replies; it is idempotent.
4. Start `sellbird dashboard`, sign in through the normal dashboard flow, and open **Local AI Sales Agent**.

## Recorded demo

On Windows, the completed 8:42.92 silent, captioned recording is [`docs/evidence/sellbird-local-sales-demo.webm`](evidence/README.md). It shows the local model status, separate products and ICPs, synthetic prospect workflows, evidence handling, scoring, an unsent email draft, sample opt-out classification, inference logs, and a cached analysis with the app's Offline Mode toggle enabled. It uses a temporary workspace and does not change the normal Sellbird database.

To record a fresh run after installing Playwright, Edge, Ollama with `qwen3:8b`, and the optional cached embedding model:

```powershell
.\.venv\Scripts\python.exe scripts\record_demo_video.py
```

The recorder blocks non-local browser origins and aborts if a displayed workflow fails after one retry. The recording demonstrates the **application** Offline Mode only; the PC's network adapter state was not checked.

## Live walkthrough

1. **Show local status (about 1 minute).** On Overview, show the configured model and hardware status. Confirm that the service is reported as local Ollama.
2. **Show product separation (1 minute).** Select **Appointment Flow (sample)**, then **Lead Follow-up Desk (sample)**. Explain that each has a separate ICP and score context.
3. **Generate and edit local context (2 minutes).** In Business & products, run Generate business profile. In each product context, run Generate product ICP and show the editable JSON. Outputs depend on the locally installed model and can vary.
4. **Show provenance and prioritization (1 minute).** Open Prospects, inspect sample provenance/empty fields, filter by industry or location, and run Score. The numeric score is deterministic and the ordered list is specific to the selected product.
5. **Show grounded workflows (2 minutes).** Select a prospect with cached sample notes, run Cached analysis, Buying signals, Problem, and Draft email. Point out evidence/source references and that the email remains a draft.
6. **Show reply handling (1 minute).** Load a stored sample conversation, leave the sample flag checked, and classify it. The fixture is synthetic and should remain labelled as a sample.
7. **Optional public discovery (1–3 minutes, internet required).** Select a supported category and place under Prospects, then start Search OpenStreetMap. Show that the task status completes, attribution is visible, duplicate OSM objects are skipped, and unavailable contact/employee/revenue data remains blank. Skip this step when offline or when a public service is rate-limited.
8. **Show offline boundary (1 minute).** Enable Offline Mode, explain that fresh public research/discovery is disabled while saved artifacts and local inference remain usable, then turn it back off if the machine stays online.

## Evidence to capture

- A screenshot of Overview with local-model status and selected business/product.
- A screenshot of a product-specific score/evidence output and synthetic-data labels.
- If a real offline demonstration was performed, record the model tag, OS network-disconnect method, test command, and timestamp separately in the final acceptance report. Do not infer offline success from the UI toggle alone.
