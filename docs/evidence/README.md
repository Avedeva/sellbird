# Browser QA evidence

Captured 2026-11-18 with headless Microsoft Edge against an isolated temporary FastAPI dashboard. The dashboard used a temporary home and authentication tokens, seeded only with the repository's clearly labelled synthetic demo data, and ran with `SELLBIRD_OFFLINE=1`.

The visual pass covered the Overview, Business & products, Prospects, Reply classification, and System & inference panels at a 1440 × 1000 desktop viewport. Setup and Prospects were also checked at 390 × 844. The checks found no document-level horizontal overflow, JavaScript page errors, or failed requests; the prospect table remains internally scrollable on narrow screens. OSM attribution was visible, and the profile/ICP JSON editors and Prospect toolbar fit their containers.

| Screenshot | View |
|---|---|
| `overview-desktop.png` | Overview with seeded businesses, products, prospects, and local model status |
| `setup-desktop.png` | Business profile and product editors |
| `setup-mobile.png` | Stacked business and product forms at 390 px |
| `prospects-desktop.png` | OSM discovery, attribution, import, and product workflow list |
| `prospects-mobile.png` | Responsive Prospect controls and internally scrollable list |
| `replies-desktop.png` | Sample reply classification panel |
| `system-desktop.png` | Offline mode, local model status, hardware, and recommendations |
| `sellbird-local-sales-demo.webm` | 8:42.92 silent, captioned dashboard recording with the synthetic multi-product workflows and the application Offline Mode segment |

All prospect and research values shown are synthetic. The browser pass did not submit public discovery or crawl a public website.

The recorded dashboard viewport is 1440 × 1000 at 25 fps. Browser requests to origins other than the local dashboard were blocked; none were attempted. The final segment enables Sellbird's application Offline Mode and runs a cached workflow. It does **not** show or claim an operating-system network disconnect.
