# Ads Engine — Changelog

All notable changes to this project are documented here.
Entries are listed in reverse chronological order (newest first).

---

## Format

Each entry includes:
- **Date**
- **Who** (name or initials)
- **What changed** — file(s) touched
- **Why** — the reason / intent
- **Notes** — anything relevant for the writeup (decisions made, things tried, things rejected)

---

## Log

### 2026-03-25 — Aryan
**Initial codebase review + orientation**
- Files reviewed: all of `engine/`, `dashboard/`, `config/`, `brief.html`, `CLAUDE.md`
- Established full understanding of pipeline architecture: intake → generation → review → deploy → track → decide → regress
- Confirmed storage is flat JSON files under `data/` (no database yet)
- Identified open workstreams: asset generation (Alex), Meta/Google API integration (stubs), Slack webhook, scheduler

---

<!-- Add new entries above this line -->
