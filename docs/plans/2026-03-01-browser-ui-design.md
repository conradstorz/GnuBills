# Browser UI Design — GnuCash Bill Processor v2.0

**Date:** 2026-03-01
**Branch:** browser-ui
**Status:** Approved

## Summary

Replace the tkinter GUI with a browser-based local web interface. The new UI is a state-aware dashboard that surfaces what needs attention and enables the right actions contextually — replacing the rigid linear workflow of the tkinter version.

## Requirements

- **Local only** — `localhost:8000`, no network access
- **State-aware dashboard** — vendor sync status, queued bills, unposted GnuCash bills all surfaced; actions greyed out when not applicable
- **Desktop icon launch** — click → server starts → browser opens automatically
- **Queue-first bill entry** — bills saved to `bills_to_process.txt` before GnuCash processing; external tools can pre-populate this queue
- **Smooth vendor lookup** — unknown vendor address lookup integrated inline during bill entry
- **Easy editing** — queued bills editable before processing; recent posted bills viewable

## Architecture

### Technology Stack

- **FastAPI** — web framework and route handling
- **Jinja2** — server-side HTML templates
- **HTMX** — partial page updates (vendored `htmx.min.js`, no CDN)
- **uvicorn** — ASGI server
- **launcher.pyw** — Windows launcher (no console window)

All existing modules (`gnucash_db.py`, `vendor_manager.py`, `config.py`, etc.) are imported as-is — no changes to those modules.

### File Layout

```
bill_processor/
  web/
    app.py              # FastAPI app, all routes
    templates/
      base.html
      dashboard.html
      bill_entry.html
      vendor_detail.html
    static/
      htmx.min.js       # vendored
      style.css
launcher.pyw            # Windows desktop launcher
```

### Process Lifecycle

A Windows desktop shortcut runs `launcher.pyw`, which:
1. Starts uvicorn as a subprocess
2. Calls `webbrowser.open("http://localhost:8000")`
3. Exits (no console window — `.pyw` extension)

A second launch attempt binds the same port and fails silently; the browser just navigates to the already-running server. The server runs until stopped via `/shutdown` endpoint or Task Manager.

## Dashboard Layout

```
┌─────────────────────────────────────────────────────┐
│  GnuCash Bill Processor                             │
├─────────────────────────────────────────────────────┤
│  VENDOR SYNC STATUS                                 │
│  ● In sync (47 vendors)          [Sync] ← greyed   │
│    — or —                                           │
│  ⚠ 3 vendors out of sync         [Sync] ← active   │
├─────────────────────────────────────────────────────┤
│  QUEUED BILLS  (in bills_to_process.txt)            │
│  ● None queued                                      │
│    — or —                                           │
│  ⚠ 2 bills queued     [Process All] [Process Each] │
│    Acme Electric  $123.45  memo  [Edit] [Remove]   │
├─────────────────────────────────────────────────────┤
│  ENTER A BILL                                       │
│  Vendor: [____________]  (live fuzzy search)        │
│  Amount: [____________]                             │
│  Memo:   [____________]                             │
│  Date:   [____________]                             │
│                                   [Add to Queue]   │
├─────────────────────────────────────────────────────┤
│  RECENT BILLS  (last 10, click to inspect/void)     │
│  2026-02-28  Acme Electric    $123.45  [posted]     │
│  2026-02-27  LG&E             $89.00   [posted]     │
└─────────────────────────────────────────────────────┘
```

**State-aware behaviors:**
- Sync button disabled (greyed) when vendors are in sync
- Queued Bills section collapsed when queue is empty
- Vendor field: HTMX live fuzzy search with 300ms debounce; "Add new vendor" inline when no match
- Dashboard auto-refreshes state widgets every 30 seconds via HTMX polling

## Data Flow

### Adding a Bill to the Queue

1. User types vendor name → HTMX GET `/vendors/search?q=...` → fuzzy match dropdown
2. If no match → "Add new vendor" expands inline → HTMX POST `/vendors/lookup-address` → address fields pre-filled → HTMX POST `/vendors/create`
3. User fills amount/memo/date → HTMX POST `/bills/queue` → bill appended to `bills_to_process.txt` → queue section refreshes

### Processing Queued Bills

1. User clicks "Process All" or "Process One" → HTMX POST `/bills/queue/process` or `/bills/queue/{index}/process`
2. Server runs `create_bill()` → `post_bill()` → `pay_bill()` per bill
3. On success: bill removed from queue, Recent Bills section updated
4. On failure: error fragment shown inline, bill remains in queue for retry

### External Tool Integration

External tools write bills directly to `data/bills_to_process.txt` in the existing CSV format. The dashboard picks them up on next poll or page load.

## API Routes

| Method | Path | Action |
|--------|------|--------|
| GET | `/` | Full dashboard page |
| GET | `/vendors/search` | Fuzzy search dropdown fragment |
| POST | `/vendors/sync` | Run vendor sync, return status fragment |
| POST | `/vendors/lookup-address` | Address lookup, return pre-filled form fragment |
| POST | `/vendors/create` | Create vendor in GnuCash + JSON cache |
| POST | `/bills/queue` | Add bill to `bills_to_process.txt` |
| DELETE | `/bills/queue/{index}` | Remove a queued bill |
| PATCH | `/bills/queue/{index}` | Edit a queued bill |
| POST | `/bills/queue/process` | Process all queued bills through GnuCash |
| POST | `/bills/queue/{index}/process` | Process one queued bill |
| GET | `/bills/{guid}` | Bill detail page |
| POST | `/bills/{guid}/void` | Void a posted bill |
| GET | `/status` | JSON health/state for dashboard polling |
| POST | `/shutdown` | Graceful server stop |

## Error Handling

- **Partial GnuCash failure**: Exception from `gnucash_db.py` propagates to route handler → error fragment returned showing which step failed → bill remains in queue for retry
- **Address lookup failure**: Returns "lookup unavailable, enter manually" fragment — form stays open with blank address fields
- **Concurrent writes**: Database lock from `gnucash_db.py` held only during write operations — UI stays responsive
- **Port already in use**: Second launcher invocation fails to bind; browser navigates to existing server

## Testing

- **`test_web_app.py`**: FastAPI `TestClient` — one test per route, happy path + error cases
- **Queue file operations**: Tested with `tmp_path` fixture — read/write/edit/delete
- **Vendor search endpoint**: Reuses existing `db_connection` fixture
- No browser automation (Selenium/Playwright) — HTMX fragments are plain HTML, fully testable via `TestClient`
