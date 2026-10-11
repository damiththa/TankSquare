# TankSquare — Archify System Architecture

This document renders the live, repository-backed **Archify v3.0 System Architecture Diagram** for **TankSquare** (`https://github.com/damiththa/TankSquare`).

[![TankSquare Archify System Architecture](./architecture/tanksquare-architecture.svg)](./architecture/tanksquare-architecture.html)

---

## 🔗 Interactive Archify Views & Artifacts

| Artifact / Endpoint | Description |
| :--- | :--- |
| **[`docs/architecture/tanksquare.architecture.json`](./architecture/tanksquare.architecture.json)** | Authoritative **Archify v3.0** specification (`schema_version: 1`, `quality_profile: "showcase"`, `visual_preset: "blueprint"`) with verified repository source file & line-range citations. |
| **[`docs/architecture/tanksquare-architecture.svg`](./architecture/tanksquare-architecture.svg)** | Standalone SVG rendered in the Archify `blueprint` showcase theme so **GitHub Markdown renders it natively inline** above and in `README.md`. |
| **[`docs/architecture/tanksquare-architecture.html`](./architecture/tanksquare-architecture.html)** | Full interactive **Archify v3.0 Viewer** (pan/zoom, guided views, trace animation, semantic radar, and clickable GitHub source beacons). |
| **[Live `DEV` Interactive Viewer (`/architecture`)](https://tanksquare-api-dev-339694762975.us-central1.run.app/architecture)** | Hosted directly on Cloud Run (`tanksquare-api-dev`) from [`app/static/architecture.html`](../app/static/architecture.html). |
| **[`.github/workflows/archify.yml`](../.github/workflows/archify.yml)** | GitHub Actions workflow that runs the official `tt-a1i/archify` CLI on `ubuntu-latest` (Node.js 20) to validate and render the diagram on GitHub. |

---

## 🔄 Ongoing Architectural Maintenance Rule

> **Mandatory Workflow Rule:** Whenever any architectural, router, service, storage, or CI/CD change is made to TankSquare:
> 1. **Catch & Remind:** Flag the architectural impact and remind the team before finalizing the change.
> 2. **Update Specification:** Update [`docs/architecture/tanksquare.architecture.json`](./architecture/tanksquare.architecture.json) (components, boundaries, connections, guided views, cards, and `sources` line ranges).
> 3. **Re-Compile Artifacts:** Run `python3 scripts/render_archify.py` (and/or the GitHub Actions `Render & Verify Archify Architecture` workflow) so `docs/architecture/tanksquare-architecture.svg`, `docs/architecture/tanksquare-architecture.html`, and `app/static/architecture.html` stay 100% synchronized.
