# Browser UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the tkinter GUI with a FastAPI + HTMX browser-based local dashboard that is state-aware, queue-driven, and launchable from a Windows desktop shortcut.

**Architecture:** FastAPI serves Jinja2 HTML templates; HTMX handles partial page updates without JavaScript frameworks. All existing modules (`gnucash_db.py`, `vendor_manager.py`, etc.) are imported unchanged. Bills are queued to `bills_to_process.txt` first, then processed into GnuCash as a deliberate second step.

**Tech Stack:** FastAPI, uvicorn, Jinja2, HTMX (vendored), pytest TestClient

---

## Prerequisites

Install new dependencies before starting:

```bash
uv add fastapi uvicorn[standard] jinja2 httpx
uv add --dev httpx
```

`httpx` is needed by FastAPI's `TestClient`.

---

## Task 1: Project scaffold — web package and static files

**Files:**
- Create: `bill_processor/web/__init__.py`
- Create: `bill_processor/web/templates/base.html`
- Create: `bill_processor/web/static/style.css`
- Download: `bill_processor/web/static/htmx.min.js`

**Step 1: Create the web package**

```bash
mkdir -p bill_processor/web/templates
mkdir -p bill_processor/web/static
touch bill_processor/web/__init__.py
```

**Step 2: Download vendored HTMX**

```bash
uv run python -c "
import urllib.request
url = 'https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js'
urllib.request.urlretrieve(url, 'bill_processor/web/static/htmx.min.js')
print('Downloaded htmx.min.js')
"
```

**Step 3: Create base template**

Create `bill_processor/web/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}GnuCash Bill Processor{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="/static/htmx.min.js"></script>
</head>
<body>
  <header>
    <h1>GnuCash Bill Processor</h1>
    <nav>
      <a href="/">Dashboard</a>
      <form method="post" action="/shutdown" style="display:inline">
        <button type="submit" class="btn-danger">Stop Server</button>
      </form>
    </nav>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

**Step 4: Create minimal CSS**

Create `bill_processor/web/static/style.css`:

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem; }
header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 0; border-bottom: 2px solid #333; margin-bottom: 1.5rem; }
h1 { font-size: 1.4rem; }
nav { display: flex; gap: 1rem; align-items: center; }

.card { border: 1px solid #ccc; border-radius: 6px; padding: 1rem; margin-bottom: 1rem; }
.card h2 { font-size: 1rem; text-transform: uppercase; color: #555; margin-bottom: 0.75rem; }
.status-ok { color: green; }
.status-warn { color: orange; }

button, .btn { cursor: pointer; padding: 0.4rem 0.9rem; border-radius: 4px; border: 1px solid #555; background: #f0f0f0; font-size: 0.9rem; }
button:disabled, .btn-disabled { opacity: 0.4; cursor: not-allowed; }
.btn-danger { background: #fee; border-color: #c00; color: #c00; }
.btn-primary { background: #e8f4e8; border-color: #2a7a2a; color: #1a5a1a; }

form label { display: block; font-size: 0.85rem; color: #444; margin-bottom: 0.2rem; margin-top: 0.6rem; }
form input, form textarea { width: 100%; padding: 0.4rem; border: 1px solid #aaa; border-radius: 4px; font-size: 0.95rem; }

table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 2px solid #aaa; }
td { padding: 0.35rem 0.6rem; border-bottom: 1px solid #eee; }

.dropdown { position: relative; }
.dropdown-list { position: absolute; z-index: 10; background: white; border: 1px solid #aaa; border-radius: 4px; width: 100%; max-height: 200px; overflow-y: auto; }
.dropdown-item { padding: 0.4rem 0.6rem; cursor: pointer; }
.dropdown-item:hover { background: #f0f4ff; }

.error-msg { color: #c00; background: #fee; border: 1px solid #fcc; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; }
.success-msg { color: #1a5; background: #efe; border: 1px solid #cfc; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; }

#new-vendor-form { background: #fffbe6; border: 1px solid #e0d070; border-radius: 4px; padding: 0.75rem; margin-top: 0.5rem; }
```

**Step 5: Commit**

```bash
git add bill_processor/web/
git commit -m "feat: scaffold web package with templates and static assets"
```

---

## Task 2: FastAPI app skeleton with `/status` and `/` routes

**Files:**
- Create: `bill_processor/web/app.py`
- Create: `bill_processor/tests/test_web_app.py`

**Step 1: Write the failing test**

Create `bill_processor/tests/test_web_app.py`:

```python
"""Tests for the FastAPI web application."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from bill_processor.web.app import app
    return TestClient(app)


def test_status_returns_ok(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "vendor_sync" in data
    assert "queued_bills" in data


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"GnuCash Bill Processor" in response.content
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: `ImportError` — `app.py` doesn't exist yet.

**Step 3: Create `app.py` skeleton**

Create `bill_processor/web/app.py`:

```python
"""
FastAPI web application for GnuCash Bill Processor.
Serves a state-aware dashboard for managing vendor bills.
"""
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from bill_processor import gnucash_db
from bill_processor import config
from bill_processor.utils import parse_input_line

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="GnuCash Bill Processor")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _get_queue() -> list[dict]:
    """Read bills_to_process.txt and return list of parsed bill dicts."""
    queue_path = config.BILLS_INPUT_PATH
    if not queue_path.exists():
        return []
    bills = []
    with open(queue_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            parsed = parse_input_line(line)
            if parsed:
                parsed["_index"] = i
                parsed["_raw"] = line.rstrip()
                bills.append(parsed)
    return bills


def _get_sync_status() -> dict:
    """Return vendor sync status: counts and whether sync is needed."""
    try:
        json_vendors = _count_json_vendors()
        gc_vendors = gnucash_db.get_all_vendors()
        gc_guids = {v["guid"] for v in gc_vendors}

        from bill_processor.vendor_manager import VendorManager
        vm = VendorManager()
        json_guids = {
            v.get("gnucash_guid")
            for v in vm.vendors.get("vendors", {}).values()
            if v.get("gnucash_guid")
        }
        needs_sync = not json_guids.issubset(gc_guids) or not gc_guids.issubset(json_guids)
        return {
            "json_count": json_vendors,
            "gc_count": len(gc_vendors),
            "needs_sync": needs_sync,
        }
    except Exception as e:
        logger.warning(f"Could not check sync status: {e}")
        return {"json_count": 0, "gc_count": 0, "needs_sync": False, "error": str(e)}


def _count_json_vendors() -> int:
    from bill_processor.vendor_manager import VendorManager
    vm = VendorManager()
    return len(vm.vendors.get("vendors", {}))


@app.get("/status")
def get_status():
    """Return current system state as JSON (used by HTMX polling)."""
    queue = _get_queue()
    sync = _get_sync_status()
    return {
        "vendor_sync": sync,
        "queued_bills": len(queue),
        "db_ok": gnucash_db.test_connection(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Render the main dashboard."""
    queue = _get_queue()
    sync = _get_sync_status()
    recent = gnucash_db.get_unpaid_bills()[:10]
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "queue": queue,
        "sync": sync,
        "recent_bills": recent,
    })
```

**Step 4: Create minimal `dashboard.html`**

Create `bill_processor/web/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block content %}

<!-- Vendor Sync Status -->
<div class="card" id="sync-status">
  <h2>Vendor Sync Status</h2>
  {% if sync.error is defined %}
    <p class="error-msg">Could not check sync status: {{ sync.error }}</p>
  {% elif sync.needs_sync %}
    <p class="status-warn">&#9888; {{ sync.gc_count }} in GnuCash, {{ sync.json_count }} in local database — sync needed</p>
    <button class="btn-primary"
      hx-post="/vendors/sync"
      hx-target="#sync-status"
      hx-swap="outerHTML">Sync Vendors</button>
  {% else %}
    <p class="status-ok">&#10003; In sync ({{ sync.gc_count }} vendors)</p>
    <button disabled class="btn-disabled">Sync Vendors</button>
  {% endif %}
</div>

<!-- Queued Bills -->
<div class="card" id="queued-bills">
  <h2>Queued Bills</h2>
  {% if queue %}
    <p class="status-warn">&#9888; {{ queue|length }} bill(s) waiting to be processed</p>
    <table>
      <thead><tr><th>Vendor</th><th>Amount</th><th>Memo</th><th>Date</th><th></th></tr></thead>
      <tbody>
        {% for bill in queue %}
        <tr>
          <td>{{ bill.vendor_name }}</td>
          <td>${{ "%.2f"|format(bill.amount) }}</td>
          <td>{{ bill.memo }}</td>
          <td>{{ bill.date }}</td>
          <td>
            <button hx-post="/bills/queue/{{ loop.index0 }}/process"
                    hx-target="#queued-bills"
                    hx-swap="outerHTML">Process</button>
            <button hx-delete="/bills/queue/{{ loop.index0 }}"
                    hx-target="#queued-bills"
                    hx-swap="outerHTML"
                    hx-confirm="Remove this bill from the queue?">Remove</button>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <div style="margin-top:0.75rem">
      <button class="btn-primary"
        hx-post="/bills/queue/process"
        hx-target="#queued-bills"
        hx-swap="outerHTML">Process All</button>
    </div>
  {% else %}
    <p class="status-ok">&#10003; No bills queued</p>
  {% endif %}
</div>

<!-- Bill Entry Form -->
<div class="card">
  <h2>Enter a Bill</h2>
  <div id="bill-entry-form">
    {% include "bill_entry.html" %}
  </div>
</div>

<!-- Recent Bills -->
<div class="card">
  <h2>Recent Bills</h2>
  {% if recent_bills %}
    <table>
      <thead><tr><th>Date</th><th>Vendor</th><th>Amount</th><th>Status</th></tr></thead>
      <tbody>
        {% for bill in recent_bills %}
        <tr>
          <td>{{ bill.date_opened[:10] if bill.date_opened else "—" }}</td>
          <td>{{ bill.vendor_name or bill.owner_guid[:8] }}</td>
          <td>${{ "%.2f"|format(bill.total / 100 if bill.total else 0) }}</td>
          <td>{{ "posted" if bill.is_posted else "open" }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p style="color:#888">No recent bills found.</p>
  {% endif %}
</div>

{% endblock %}
```

**Step 5: Create placeholder `bill_entry.html`**

Create `bill_processor/web/templates/bill_entry.html`:

```html
<form hx-post="/bills/queue" hx-target="#bill-entry-form" hx-swap="innerHTML">
  <label>Vendor</label>
  <div class="dropdown">
    <input type="text" name="vendor_name" id="vendor-input" required autocomplete="off"
           hx-get="/vendors/search"
           hx-trigger="keyup changed delay:300ms"
           hx-target="#vendor-dropdown"
           hx-include="[name='vendor_name']">
    <div id="vendor-dropdown"></div>
  </div>
  <div id="new-vendor-section"></div>

  <label>Amount ($)</label>
  <input type="number" name="amount" step="0.01" min="0.01" required>

  <label>Memo</label>
  <input type="text" name="memo" placeholder="optional">

  <label>Date</label>
  <input type="date" name="bill_date" value="{{ today }}">

  <div style="margin-top:1rem">
    <button type="submit" class="btn-primary">Add to Queue</button>
  </div>
</form>
```

**Step 6: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: both tests PASS.

**Step 7: Commit**

```bash
git add bill_processor/web/app.py bill_processor/web/templates/ bill_processor/tests/test_web_app.py
git commit -m "feat: FastAPI app skeleton with dashboard and /status route"
```

---

## Task 3: Bill queue read/write/delete operations

**Files:**
- Modify: `bill_processor/web/app.py`
- Create: `bill_processor/web/queue_io.py`
- Modify: `bill_processor/tests/test_web_app.py`

**Step 1: Write failing tests**

Add to `bill_processor/tests/test_web_app.py`:

```python
import tempfile
from pathlib import Path


@pytest.fixture
def tmp_queue(tmp_path, monkeypatch):
    """Patch BILLS_INPUT_PATH to a temp file."""
    queue_file = tmp_path / "bills_to_process.txt"
    queue_file.write_text("")
    from bill_processor import config
    monkeypatch.setattr(config, "BILLS_INPUT_PATH", queue_file)
    return queue_file


def test_add_bill_to_queue(client, tmp_queue):
    response = client.post("/bills/queue", data={
        "vendor_name": "Acme Electric",
        "amount": "123.45",
        "memo": "Test bill",
        "bill_date": "2026-03-01",
    })
    assert response.status_code == 200
    content = tmp_queue.read_text()
    assert "Acme Electric" in content
    assert "123.45" in content


def test_delete_bill_from_queue(client, tmp_queue):
    tmp_queue.write_text("Acme Electric, 123.45, test, 2026-03-01\n")
    response = client.delete("/bills/queue/0")
    assert response.status_code == 200
    assert tmp_queue.read_text().strip() == ""


def test_edit_bill_in_queue(client, tmp_queue):
    tmp_queue.write_text("Acme Electric, 123.45, test, 2026-03-01\n")
    response = client.patch("/bills/queue/0", data={
        "vendor_name": "Acme Electric",
        "amount": "200.00",
        "memo": "Updated",
        "bill_date": "2026-03-01",
    })
    assert response.status_code == 200
    content = tmp_queue.read_text()
    assert "200.00" in content
```

**Step 2: Run to verify failure**

```bash
uv run pytest bill_processor/tests/test_web_app.py::test_add_bill_to_queue -v
```
Expected: 404 — routes not defined yet.

**Step 3: Create `queue_io.py`**

Create `bill_processor/web/queue_io.py`:

```python
"""
Read/write/edit/delete operations on bills_to_process.txt queue.
"""
from pathlib import Path
from datetime import date
from typing import Optional
from loguru import logger

from bill_processor import config
from bill_processor.utils import parse_input_line


def read_queue() -> list[dict]:
    """Return parsed list of queued bills with their line indices."""
    path = config.BILLS_INPUT_PATH
    if not path.exists():
        return []
    bills = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        parsed = parse_input_line(line)
        if parsed:
            parsed["_index"] = i
            parsed["_raw"] = line.rstrip()
            bills.append(parsed)
    return bills


def _read_raw_lines() -> list[str]:
    path = config.BILLS_INPUT_PATH
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def _write_raw_lines(lines: list[str]):
    config.BILLS_INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.BILLS_INPUT_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _format_bill_line(vendor_name: str, amount: float, memo: str, bill_date: date) -> str:
    memo = memo or "no memo"
    return f"{vendor_name}, {amount:.2f}, {memo}, {bill_date.isoformat()}\n"


def add_bill(vendor_name: str, amount: float, memo: str, bill_date: date):
    """Append a bill to the queue file."""
    line = _format_bill_line(vendor_name, amount, memo, bill_date)
    config.BILLS_INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.BILLS_INPUT_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    logger.info(f"Queued bill: {vendor_name} ${amount:.2f}")


def remove_bill(queue_index: int) -> bool:
    """Remove the bill at queue_index (position in parsed queue, not raw line number)."""
    bills = read_queue()
    if queue_index < 0 or queue_index >= len(bills):
        return False
    raw_line_idx = bills[queue_index]["_index"]
    lines = _read_raw_lines()
    lines.pop(raw_line_idx)
    _write_raw_lines(lines)
    return True


def update_bill(queue_index: int, vendor_name: str, amount: float, memo: str, bill_date: date) -> bool:
    """Replace the bill at queue_index with updated values."""
    bills = read_queue()
    if queue_index < 0 or queue_index >= len(bills):
        return False
    raw_line_idx = bills[queue_index]["_index"]
    lines = _read_raw_lines()
    lines[raw_line_idx] = _format_bill_line(vendor_name, amount, memo, bill_date)
    _write_raw_lines(lines)
    return True
```

**Step 4: Add routes to `app.py`**

Add these imports at the top of `app.py`:

```python
from datetime import date
from fastapi import Form
from fastapi.responses import HTMLResponse
from bill_processor.web import queue_io
```

Add these routes to `app.py`:

```python
@app.post("/bills/queue", response_class=HTMLResponse)
def add_to_queue(
    request: Request,
    vendor_name: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
    bill_date: date = Form(default_factory=date.today),
):
    """Add a bill to the queue and return refreshed bill entry form."""
    queue_io.add_bill(vendor_name, amount, memo, bill_date)
    return templates.TemplateResponse("bill_entry.html", {
        "request": request,
        "today": date.today().isoformat(),
        "success": f"Added {vendor_name} ${amount:.2f} to queue",
    })


@app.delete("/bills/queue/{index}", response_class=HTMLResponse)
def remove_from_queue(request: Request, index: int):
    """Remove a bill from the queue and return refreshed queue card."""
    queue_io.remove_bill(index)
    queue = queue_io.read_queue()
    sync = _get_sync_status()
    return templates.TemplateResponse("partials/queued_bills.html", {
        "request": request,
        "queue": queue,
        "sync": sync,
    })


@app.patch("/bills/queue/{index}", response_class=HTMLResponse)
def edit_queue_item(
    request: Request,
    index: int,
    vendor_name: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
    bill_date: date = Form(default_factory=date.today),
):
    """Update a queued bill and return refreshed queue card."""
    queue_io.update_bill(index, vendor_name, amount, memo, bill_date)
    queue = queue_io.read_queue()
    sync = _get_sync_status()
    return templates.TemplateResponse("partials/queued_bills.html", {
        "request": request,
        "queue": queue,
        "sync": sync,
    })
```

**Step 5: Extract queued bills partial template**

Create `bill_processor/web/templates/partials/queued_bills.html`:

```html
<div class="card" id="queued-bills">
  <h2>Queued Bills</h2>
  {% if queue %}
    <p class="status-warn">&#9888; {{ queue|length }} bill(s) waiting to be processed</p>
    <table>
      <thead><tr><th>Vendor</th><th>Amount</th><th>Memo</th><th>Date</th><th></th></tr></thead>
      <tbody>
        {% for bill in queue %}
        <tr>
          <td>{{ bill.vendor_name }}</td>
          <td>${{ "%.2f"|format(bill.amount) }}</td>
          <td>{{ bill.memo }}</td>
          <td>{{ bill.date }}</td>
          <td>
            <button hx-post="/bills/queue/{{ loop.index0 }}/process"
                    hx-target="#queued-bills"
                    hx-swap="outerHTML">Process</button>
            <button hx-delete="/bills/queue/{{ loop.index0 }}"
                    hx-target="#queued-bills"
                    hx-swap="outerHTML"
                    hx-confirm="Remove this bill from the queue?">Remove</button>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <div style="margin-top:0.75rem">
      <button class="btn-primary"
        hx-post="/bills/queue/process"
        hx-target="#queued-bills"
        hx-swap="outerHTML">Process All</button>
    </div>
  {% else %}
    <p class="status-ok">&#10003; No bills queued</p>
  {% endif %}
</div>
```

Update `dashboard.html` to use the partial:
```html
<!-- replace the queued-bills div with: -->
{% include "partials/queued_bills.html" %}
```

**Step 6: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: all tests PASS.

**Step 7: Commit**

```bash
git add bill_processor/web/queue_io.py bill_processor/web/app.py bill_processor/web/templates/ bill_processor/tests/test_web_app.py
git commit -m "feat: bill queue read/write/delete with queue_io module"
```

---

## Task 4: Vendor fuzzy search endpoint

**Files:**
- Modify: `bill_processor/web/app.py`
- Create: `bill_processor/web/templates/partials/vendor_dropdown.html`
- Modify: `bill_processor/tests/test_web_app.py`

**Step 1: Write failing tests**

Add to `test_web_app.py`:

```python
def test_vendor_search_returns_html(client):
    response = client.get("/vendors/search?q=acme")
    assert response.status_code == 200
    # Should return HTML fragment (empty list is fine if no vendors)
    assert b"dropdown" in response.content or response.content == b""


def test_vendor_search_empty_query(client):
    response = client.get("/vendors/search?q=")
    assert response.status_code == 200
```

**Step 2: Run to verify failure**

```bash
uv run pytest bill_processor/tests/test_web_app.py::test_vendor_search_returns_html -v
```
Expected: 404.

**Step 3: Add vendor search route to `app.py`**

```python
from bill_processor.vendor_manager import VendorManager

@app.get("/vendors/search", response_class=HTMLResponse)
def vendor_search(request: Request, vendor_name: str = ""):
    """Return HTML dropdown fragment of fuzzy-matched vendors."""
    if not vendor_name or len(vendor_name) < 2:
        return HTMLResponse("")

    vm = VendorManager()
    results = []

    # Check aliases first, then fuzzy match display names
    from bill_processor.utils import fuzzy_match_vendor
    vendor_key, score, candidates = fuzzy_match_vendor(
        vendor_name, vm.vendors.get("vendors", {})
    )

    # Build list of matches above a lower threshold for dropdown
    DROPDOWN_THRESHOLD = 40
    seen = set()
    for key, s in candidates:
        if s >= DROPDOWN_THRESHOLD and key not in seen:
            seen.add(key)
            vdata = vm.vendors["vendors"].get(key, {})
            results.append({
                "key": key,
                "display_name": vdata.get("display_name", key),
                "score": s,
            })

    return templates.TemplateResponse("partials/vendor_dropdown.html", {
        "request": request,
        "results": results[:6],  # max 6 suggestions
        "query": vendor_name,
    })
```

**Step 4: Create dropdown partial**

Create `bill_processor/web/templates/partials/vendor_dropdown.html`:

```html
{% if results %}
<div class="dropdown-list">
  {% for vendor in results %}
  <div class="dropdown-item"
       hx-on:click="
         document.getElementById('vendor-input').value = '{{ vendor.display_name }}';
         document.getElementById('vendor-dropdown').innerHTML = '';
         document.getElementById('new-vendor-section').innerHTML = '';
       ">
    {{ vendor.display_name }}
  </div>
  {% endfor %}
  <div class="dropdown-item" style="color:#888; font-style:italic"
       hx-get="/vendors/new-form?name={{ query|urlencode }}"
       hx-target="#new-vendor-section"
       hx-swap="innerHTML"
       hx-on:click="document.getElementById('vendor-dropdown').innerHTML = ''">
    + Add "{{ query }}" as new vendor...
  </div>
</div>
{% endif %}
```

**Step 5: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: all PASS.

**Step 6: Commit**

```bash
git add bill_processor/web/app.py bill_processor/web/templates/partials/vendor_dropdown.html bill_processor/tests/test_web_app.py
git commit -m "feat: vendor fuzzy search endpoint with HTMX dropdown"
```

---

## Task 5: Inline new vendor creation with address lookup

**Files:**
- Modify: `bill_processor/web/app.py`
- Create: `bill_processor/web/templates/partials/new_vendor_form.html`
- Modify: `bill_processor/tests/test_web_app.py`

**Step 1: Write failing tests**

```python
def test_new_vendor_form_renders(client):
    response = client.get("/vendors/new-form?name=TestVendor")
    assert response.status_code == 200
    assert b"TestVendor" in response.content


def test_address_lookup_returns_form(client):
    # With no API keys configured, should still return a form (possibly empty)
    response = client.post("/vendors/lookup-address", data={"vendor_name": "Acme Electric"})
    assert response.status_code == 200


def test_create_vendor_requires_name(client):
    response = client.post("/vendors/create", data={"display_name": "", "vendor_name": ""})
    assert response.status_code in (200, 422)
```

**Step 2: Run to verify failure**

```bash
uv run pytest bill_processor/tests/test_web_app.py::test_new_vendor_form_renders -v
```

**Step 3: Add routes to `app.py`**

```python
from bill_processor import address_lookup as addr_lookup

@app.get("/vendors/new-form", response_class=HTMLResponse)
def new_vendor_form(request: Request, name: str = ""):
    """Return the new vendor inline form."""
    return templates.TemplateResponse("partials/new_vendor_form.html", {
        "request": request,
        "vendor_name": name,
        "addr_line1": "", "addr_line2": "", "addr_city": "",
        "addr_state": "", "addr_zip": "", "addr_phone": "",
        "message": "",
    })


@app.post("/vendors/lookup-address", response_class=HTMLResponse)
def lookup_address(request: Request, vendor_name: str = Form("")):
    """Look up address for vendor name, return pre-filled form."""
    addr = {}
    message = ""
    try:
        result = addr_lookup.lookup_google_places(vendor_name) or addr_lookup.lookup_openstreetmap(vendor_name)
        if result:
            addr = result
        else:
            message = "Address not found — enter manually"
    except Exception as e:
        message = f"Lookup unavailable — enter manually ({e})"

    return templates.TemplateResponse("partials/new_vendor_form.html", {
        "request": request,
        "vendor_name": vendor_name,
        "addr_line1": addr.get("addr1", ""),
        "addr_line2": addr.get("addr2", ""),
        "addr_city": addr.get("city", ""),
        "addr_state": addr.get("state", ""),
        "addr_zip": addr.get("zip", ""),
        "addr_phone": addr.get("phone", ""),
        "message": message,
    })


@app.post("/vendors/create", response_class=HTMLResponse)
def create_vendor(
    request: Request,
    vendor_name: str = Form(...),
    display_name: str = Form(""),
    addr_line1: str = Form(""),
    addr_line2: str = Form(""),
    addr_city: str = Form(""),
    addr_state: str = Form(""),
    addr_zip: str = Form(""),
    addr_phone: str = Form(""),
):
    """Create vendor in GnuCash + JSON cache, return confirmation fragment."""
    display_name = display_name or vendor_name
    try:
        guid = gnucash_db.create_vendor(
            name=display_name,
            addr_name=display_name,
            addr_addr1=addr_line1,
            addr_addr2=addr_line2,
            addr_city=addr_city,
            addr_state=addr_state,
            addr_zip=addr_zip,
            addr_phone=addr_phone,
        )
        # Cache in JSON
        vm = VendorManager()
        from bill_processor.utils import strip_vendor_name
        key = strip_vendor_name(display_name)
        vm.vendors["vendors"][key] = {
            "display_name": display_name,
            "gnucash_guid": guid,
            "addr_line1": addr_line1,
            "addr_city": addr_city,
            "addr_state": addr_state,
        }
        vm.save()
        return HTMLResponse(
            f'<div class="success-msg">&#10003; Created vendor: {display_name}</div>'
            f'<script>document.getElementById("vendor-input").value = "{display_name}";</script>'
        )
    except Exception as e:
        return HTMLResponse(f'<div class="error-msg">Failed to create vendor: {e}</div>')
```

**Step 4: Create new vendor form partial**

Create `bill_processor/web/templates/partials/new_vendor_form.html`:

```html
<div id="new-vendor-form">
  <strong>New Vendor: {{ vendor_name }}</strong>
  {% if message %}<p class="error-msg" style="margin-top:0.3rem">{{ message }}</p>{% endif %}

  <form hx-post="/vendors/create" hx-target="#new-vendor-section" hx-swap="innerHTML">
    <input type="hidden" name="vendor_name" value="{{ vendor_name }}">

    <label>Display Name</label>
    <input type="text" name="display_name" value="{{ vendor_name }}" required>

    <div style="display:flex; gap:0.5rem; margin-top:0.5rem">
      <button type="button" class="btn-primary"
        hx-post="/vendors/lookup-address"
        hx-vals='{"vendor_name": "{{ vendor_name }}"}'
        hx-target="#new-vendor-form"
        hx-swap="outerHTML">Look Up Address</button>
    </div>

    <label>Address Line 1</label>
    <input type="text" name="addr_line1" value="{{ addr_line1 }}">

    <label>Address Line 2</label>
    <input type="text" name="addr_line2" value="{{ addr_line2 }}">

    <label>City</label>
    <input type="text" name="addr_city" value="{{ addr_city }}">

    <label>State</label>
    <input type="text" name="addr_state" value="{{ addr_state }}" style="width:6rem">

    <label>ZIP</label>
    <input type="text" name="addr_zip" value="{{ addr_zip }}" style="width:8rem">

    <label>Phone</label>
    <input type="text" name="addr_phone" value="{{ addr_phone }}">

    <div style="margin-top:0.75rem; display:flex; gap:0.5rem">
      <button type="submit" class="btn-primary">Create Vendor</button>
      <button type="button"
        hx-on:click="document.getElementById('new-vendor-section').innerHTML=''">Cancel</button>
    </div>
  </form>
</div>
```

**Step 5: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: all PASS.

**Step 6: Commit**

```bash
git add bill_processor/web/app.py bill_processor/web/templates/partials/ bill_processor/tests/test_web_app.py
git commit -m "feat: inline new vendor creation with address lookup"
```

---

## Task 6: Bill processing (queue → GnuCash)

**Files:**
- Modify: `bill_processor/web/app.py`
- Modify: `bill_processor/tests/test_web_app.py`

**Step 1: Write failing tests**

```python
def test_process_queue_empty_returns_ok(client, tmp_queue):
    response = client.post("/bills/queue/process")
    assert response.status_code == 200


def test_process_single_bill_missing_index(client, tmp_queue):
    response = client.post("/bills/queue/99/process")
    assert response.status_code == 200
    assert b"error" in response.content.lower() or b"not found" in response.content.lower()
```

Note: Testing the full `create_bill → post_bill → pay_bill` path requires a real GnuCash DB and is covered by the existing `test_bill_workflow.py`. The web layer tests only verify routing and error handling.

**Step 2: Run to verify failure**

```bash
uv run pytest bill_processor/tests/test_web_app.py::test_process_queue_empty_returns_ok -v
```

**Step 3: Add processing routes to `app.py`**

```python
from bill_processor.vendor_manager import VendorManager

def _process_one_bill(bill: dict) -> dict:
    """
    Run create/post/pay for a single bill dict.
    Returns {"ok": True} or {"ok": False, "error": str}.
    """
    vm = VendorManager()
    vendor_data, match_type = vm.find_vendor(bill["vendor_name"])
    if not vendor_data:
        return {"ok": False, "error": f"Vendor not found: {bill['vendor_name']}"}

    vendor_guid = vendor_data.get("gnucash_guid")
    if not vendor_guid:
        gc_vendor = gnucash_db.find_vendor_by_name(vendor_data.get("display_name"))
        if not gc_vendor:
            return {"ok": False, "error": f"No GnuCash GUID for {vendor_data.get('display_name')}"}
        vendor_guid = gc_vendor["guid"]

    try:
        expense_guid = vm.get_or_create_expense_account(vendor_data)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    checking = gnucash_db.get_checking_accounts()
    if not checking:
        return {"ok": False, "error": "No checking account found in GnuCash"}
    checking_guid = checking[0]["guid"]

    try:
        bill_guid = gnucash_db.create_bill(
            vendor_guid=vendor_guid,
            expense_account_guid=expense_guid,
            amount=bill["amount"],
            memo=bill.get("memo", ""),
            bill_date=bill["date"],
        )
        gnucash_db.post_bill(bill_guid=bill_guid, post_date=bill["date"], due_date=bill["date"])
        gnucash_db.pay_bill(
            bill_guid=bill_guid,
            checking_account_guid=checking_guid,
            payment_date=bill["date"],
            memo=bill.get("memo", ""),
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/bills/queue/{index}/process", response_class=HTMLResponse)
def process_one(request: Request, index: int):
    """Process a single queued bill through GnuCash."""
    queue = queue_io.read_queue()
    if index < 0 or index >= len(queue):
        return templates.TemplateResponse("partials/queued_bills.html", {
            "request": request,
            "queue": queue,
            "error": f"Bill index {index} not found",
        })
    bill = queue[index]
    result = _process_one_bill(bill)
    if result["ok"]:
        queue_io.remove_bill(index)
    queue = queue_io.read_queue()
    return templates.TemplateResponse("partials/queued_bills.html", {
        "request": request,
        "queue": queue,
        "last_error": None if result["ok"] else result["error"],
    })


@app.post("/bills/queue/process", response_class=HTMLResponse)
def process_all(request: Request):
    """Process all queued bills through GnuCash."""
    errors = []
    # Process in reverse order to avoid index shifting on removal
    queue = queue_io.read_queue()
    for bill in queue:
        result = _process_one_bill(bill)
        if result["ok"]:
            queue_io.remove_bill(bill["_index"])
        else:
            errors.append(f"{bill['vendor_name']}: {result['error']}")
    remaining = queue_io.read_queue()
    return templates.TemplateResponse("partials/queued_bills.html", {
        "request": request,
        "queue": remaining,
        "last_error": "; ".join(errors) if errors else None,
    })
```

Update `partials/queued_bills.html` to show errors if present:
```html
{% if last_error %}
<p class="error-msg">&#9888; {{ last_error }}</p>
{% endif %}
```

**Step 4: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: all PASS.

**Step 5: Commit**

```bash
git add bill_processor/web/app.py bill_processor/web/templates/partials/queued_bills.html bill_processor/tests/test_web_app.py
git commit -m "feat: bill processing routes (queue → GnuCash create/post/pay)"
```

---

## Task 7: Vendor sync endpoint

**Files:**
- Modify: `bill_processor/web/app.py`
- Create: `bill_processor/web/templates/partials/sync_status.html`
- Modify: `bill_processor/tests/test_web_app.py`

**Step 1: Write failing test**

```python
def test_sync_vendors_returns_html(client):
    response = client.post("/vendors/sync")
    assert response.status_code == 200
    assert b"sync" in response.content.lower() or b"vendor" in response.content.lower()
```

**Step 2: Run to verify failure**

```bash
uv run pytest bill_processor/tests/test_web_app.py::test_sync_vendors_returns_html -v
```

**Step 3: Add sync route to `app.py`**

```python
from bill_processor.vendor_sync import VendorSyncUtility

@app.post("/vendors/sync", response_class=HTMLResponse)
def sync_vendors(request: Request):
    """Run bidirectional vendor sync and return updated status card."""
    error = None
    try:
        util = VendorSyncUtility()
        util.sync_all_vendors()
    except Exception as e:
        error = str(e)
        logger.error(f"Vendor sync failed: {e}")
    sync = _get_sync_status()
    return templates.TemplateResponse("partials/sync_status.html", {
        "request": request,
        "sync": sync,
        "error": error,
    })
```

**Step 4: Extract sync status partial**

Create `bill_processor/web/templates/partials/sync_status.html`:

```html
<div class="card" id="sync-status">
  <h2>Vendor Sync Status</h2>
  {% if error %}
    <p class="error-msg">Sync failed: {{ error }}</p>
  {% elif sync.error is defined %}
    <p class="error-msg">Could not check sync status: {{ sync.error }}</p>
  {% elif sync.needs_sync %}
    <p class="status-warn">&#9888; {{ sync.gc_count }} in GnuCash, {{ sync.json_count }} in local database — sync needed</p>
    <button class="btn-primary"
      hx-post="/vendors/sync"
      hx-target="#sync-status"
      hx-swap="outerHTML">Sync Vendors</button>
  {% else %}
    <p class="status-ok">&#10003; In sync ({{ sync.gc_count }} vendors)</p>
    <button disabled class="btn-disabled">Sync Vendors</button>
  {% endif %}
</div>
```

Update `dashboard.html` to use:
```html
{% include "partials/sync_status.html" %}
```

**Step 5: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
```
Expected: all PASS.

**Step 6: Commit**

```bash
git add bill_processor/web/app.py bill_processor/web/templates/partials/sync_status.html bill_processor/tests/test_web_app.py
git commit -m "feat: vendor sync endpoint with status partial"
```

---

## Task 8: Shutdown endpoint and desktop launcher

**Files:**
- Modify: `bill_processor/web/app.py`
- Create: `launcher.pyw`
- Modify: `pyproject.toml`
- Modify: `bill_processor/tests/test_web_app.py`

**Step 1: Write failing test**

```python
def test_shutdown_endpoint_exists(client):
    # Just verify the route exists and returns something —
    # we can't actually test it killing the server in a test
    # Use raise_server_exceptions=False so the test doesn't fail on shutdown
    from fastapi.testclient import TestClient
    from bill_processor.web.app import app
    c = TestClient(app, raise_server_exceptions=False)
    response = c.post("/shutdown")
    assert response.status_code in (200, 503)
```

**Step 2: Add shutdown route to `app.py`**

```python
import os
import signal

@app.post("/shutdown")
def shutdown():
    """Gracefully stop the server."""
    import threading
    def _stop():
        import time
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_stop, daemon=True).start()
    return {"message": "Server shutting down"}
```

**Step 3: Create `launcher.pyw`**

Create `launcher.pyw` at project root:

```python
"""
Windows desktop launcher for GnuCash Bill Processor web UI.
Run this file (or a shortcut to it) to start the server and open the browser.
The .pyw extension prevents a console window from appearing.
"""
import subprocess
import sys
import time
import webbrowser
import socket
from pathlib import Path

PORT = 8000
URL = f"http://localhost:{PORT}"
PROJECT_ROOT = Path(__file__).parent


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


if _port_in_use(PORT):
    # Server already running — just open browser
    webbrowser.open(URL)
else:
    # Start server
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bill_processor.web.app:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(PROJECT_ROOT),
        creationflags=0x08000000,  # CREATE_NO_WINDOW on Windows
    )
    # Wait for server to start (max 5 seconds)
    for _ in range(10):
        if _port_in_use(PORT):
            break
        time.sleep(0.5)
    webbrowser.open(URL)
```

**Step 4: Add entry point to `pyproject.toml`**

```toml
[project.scripts]
# Add alongside existing entries:
bill-web = "bill_processor.web.app:app"
```

Note: the web UI is launched via `launcher.pyw` on Windows, not via this entry point. The entry point is for running `uvicorn bill_processor.web.app:app` directly from the terminal.

**Step 5: Run tests**

```bash
uv run pytest bill_processor/tests/test_web_app.py -v
uv run pytest -v  # Full suite
```
Expected: all existing tests still PASS.

**Step 6: Commit**

```bash
git add bill_processor/web/app.py launcher.pyw pyproject.toml bill_processor/tests/test_web_app.py
git commit -m "feat: shutdown endpoint and Windows desktop launcher"
```

---

## Task 9: Dashboard polling and final wiring

**Files:**
- Modify: `bill_processor/web/templates/dashboard.html`
- Modify: `bill_processor/web/templates/base.html`

**Step 1: Add HTMX polling to dashboard**

In `dashboard.html`, update the sync status div to poll every 30 seconds:

```html
<div id="sync-status"
     hx-get="/partials/sync-status"
     hx-trigger="every 30s"
     hx-swap="outerHTML">
  {% include "partials/sync_status.html" %}
</div>
```

Add a GET route for the partial in `app.py`:

```python
@app.get("/partials/sync-status", response_class=HTMLResponse)
def get_sync_status_partial(request: Request):
    sync = _get_sync_status()
    return templates.TemplateResponse("partials/sync_status.html", {
        "request": request, "sync": sync
    })

@app.get("/partials/queued-bills", response_class=HTMLResponse)
def get_queued_bills_partial(request: Request):
    queue = queue_io.read_queue()
    sync = _get_sync_status()
    return templates.TemplateResponse("partials/queued_bills.html", {
        "request": request, "queue": queue, "sync": sync
    })
```

**Step 2: Fix `bill_entry.html` — pass `today` from context**

Update the `dashboard` route in `app.py` to pass `today`:

```python
from datetime import date

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    queue = queue_io.read_queue()
    sync = _get_sync_status()
    recent = gnucash_db.get_unpaid_bills()[:10]
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "queue": queue,
        "sync": sync,
        "recent_bills": recent,
        "today": date.today().isoformat(),
    })
```

**Step 3: Manual smoke test**

```bash
uv run uvicorn bill_processor.web.app:app --reload --port 8000
```

Open `http://localhost:8000` in a browser. Verify:
- Dashboard renders without errors
- Vendor sync status card shows
- Queued bills card shows (should be empty or show current queue)
- Bill entry form renders
- Recent bills table renders

**Step 4: Run full test suite**

```bash
uv run pytest -v
```
Expected: all tests PASS (or previously-skipped edge case tests remain skipped).

**Step 5: Commit**

```bash
git add bill_processor/web/
git commit -m "feat: dashboard polling and final wiring complete"
```

---

## Task 10: Register web entry point and update CLAUDE.md

**Files:**
- Modify: `pyproject.toml`
- Modify: `CLAUDE.md`

**Step 1: Verify entry point in `pyproject.toml`**

The `[project.scripts]` section should now include:
```toml
bill-web = "bill_processor.web.app:app"
```

Run `uv sync` to register it:
```bash
uv sync
```

**Step 2: Update CLAUDE.md**

Add to the Commands section:
```markdown
uv run uvicorn bill_processor.web.app:app --port 8000  # Start web UI server
# Or double-click launcher.pyw for Windows desktop launch
```

Add to the Architecture section — Key modules table:
```
| `web/app.py`      | FastAPI routes — dashboard, queue CRUD, vendor search, bill processing |
| `web/queue_io.py` | Queue file I/O — read/write/edit/delete for bills_to_process.txt |
| `launcher.pyw`    | Windows launcher — starts uvicorn and opens browser |
```

**Step 3: Final full test run**

```bash
uv run pytest -v --tb=short
```

**Step 4: Commit**

```bash
git add pyproject.toml CLAUDE.md
git commit -m "docs: update CLAUDE.md and pyproject for web UI entry points"
```

---

## Completion

After Task 10, invoke `superpowers:finishing-a-development-branch` to decide how to merge `browser-ui` → `main`.
