"""
FastAPI web application for GnuCash Bill Processor.
Serves a state-aware dashboard for managing vendor bills.
"""
from datetime import date
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from bill_processor import gnucash_db
from bill_processor import config
import bill_processor.address_lookup as addr_lookup
from bill_processor.utils import parse_input_line, fuzzy_match_vendor, strip_vendor_name
from bill_processor.vendor_manager import VendorManager
from bill_processor.web import queue_io

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="GnuCash Bill Processor")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

VENDOR_SEARCH_MIN_SCORE = 40  # Lower threshold for dropdown suggestions


def _get_sync_status() -> dict:
    """Return vendor sync status: counts and whether sync is needed."""
    try:
        vm = VendorManager()
        json_guids = {
            v.get("gnucash_guid")
            for v in vm.vendors.get("vendors", {}).values()
            if v.get("gnucash_guid")
        }
        gc_vendors = gnucash_db.get_all_vendors()
        gc_guids = {v["guid"] for v in gc_vendors}
        needs_sync = not json_guids.issubset(gc_guids) or not gc_guids.issubset(json_guids)
        return {
            "json_count": len(vm.vendors.get("vendors", {})),
            "gc_count": len(gc_vendors),
            "needs_sync": needs_sync,
        }
    except Exception as e:
        logger.warning(f"Could not check sync status: {e}")
        return {"json_count": 0, "gc_count": 0, "needs_sync": False, "error": str(e)}


@app.get("/status")
def get_status():
    """Return current system state as JSON (used by HTMX polling)."""
    queue = queue_io.read_queue()
    sync = _get_sync_status()
    return {
        "vendor_sync": sync,
        "queued_bills": len(queue),
        "db_ok": gnucash_db.test_connection(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Render the main dashboard."""
    queue = queue_io.read_queue()
    sync = _get_sync_status()
    try:
        recent = gnucash_db.get_unpaid_bills()[:10]
    except Exception as e:
        logger.warning(f"Could not load recent bills: {e}")
        recent = []
    return templates.TemplateResponse(request, "dashboard.html", {
        "queue": queue,
        "sync": sync,
        "recent_bills": recent,
        "today": date.today().isoformat(),
        "last_error": None,
    })


@app.post("/bills/queue", response_class=HTMLResponse)
def add_to_queue(
    request: Request,
    vendor_name: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
    bill_date: str = Form(""),
):
    """Add a bill to the queue and return refreshed bill entry form."""
    if not vendor_name.strip():
        return HTMLResponse('<p class="error-msg">Vendor name is required.</p>', status_code=200)
    if amount <= 0:
        return HTMLResponse('<p class="error-msg">Amount must be greater than zero.</p>', status_code=200)
    try:
        parsed_date = date.fromisoformat(bill_date) if bill_date else date.today()
    except ValueError:
        parsed_date = date.today()
    queue_io.add_bill(vendor_name, amount, memo, parsed_date)
    return templates.TemplateResponse(request, "bill_entry.html", {
        "today": date.today().isoformat(),
        "success": f"Added {vendor_name} ${amount:.2f} to queue",
    })


@app.delete("/bills/queue/{index}", response_class=HTMLResponse)
def remove_from_queue(request: Request, index: int):
    """Remove a bill from the queue by file-line index."""
    ok = queue_io.remove_bill(index)
    queue = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": queue,
        "last_error": None if ok else f"Could not remove bill at index {index}",
    })


@app.post("/bills/queue/process", response_class=HTMLResponse)
def process_all_stub(request: Request):
    """Stub — will be implemented in a later task."""
    queue = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": queue,
        "last_error": "Bill processing not yet implemented. Check back soon.",
    })


@app.post("/bills/queue/{index}/process", response_class=HTMLResponse)
def process_one_stub(request: Request, index: int):
    """Stub — will be implemented in a later task."""
    queue = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": queue,
        "last_error": "Bill processing not yet implemented. Check back soon.",
    })


@app.patch("/bills/queue/{index}", response_class=HTMLResponse)
def edit_queue_item(
    request: Request,
    index: int,
    vendor_name: str = Form(...),
    amount: float = Form(...),
    memo: str = Form(""),
    bill_date: str = Form(""),
):
    """Update a queued bill and return refreshed queue card."""
    if not vendor_name.strip():
        return HTMLResponse('<p class="error-msg">Vendor name is required.</p>', status_code=200)
    if amount <= 0:
        return HTMLResponse('<p class="error-msg">Amount must be greater than zero.</p>', status_code=200)
    try:
        parsed_date = date.fromisoformat(bill_date) if bill_date else date.today()
    except ValueError:
        parsed_date = date.today()
    ok = queue_io.update_bill(index, vendor_name, amount, memo, parsed_date)
    queue = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": queue,
        "last_error": None if ok else f"Could not update bill at index {index}",
    })


@app.get("/vendors/search", response_class=HTMLResponse)
def vendor_search(request: Request, vendor_name: str = ""):
    """Return HTML dropdown fragment of fuzzy-matched vendors."""
    if not vendor_name or len(vendor_name.strip()) < 2:
        return HTMLResponse("")

    try:
        vm = VendorManager()
        _, _, candidates = fuzzy_match_vendor(
            vendor_name.strip(), vm.vendors.get("vendors", {})
        )
    except Exception as e:
        logger.warning(f"Vendor search failed for '{vendor_name}': {e}")
        return HTMLResponse("")

    seen = set()
    results = []
    for key, score in candidates:
        if score >= VENDOR_SEARCH_MIN_SCORE and key not in seen:
            seen.add(key)
            vdata = vm.vendors["vendors"].get(key, {})
            results.append({
                "key": key,
                "display_name": vdata.get("display_name", key),
                "score": score,
            })

    return templates.TemplateResponse(request, "partials/vendor_dropdown.html", {
        "results": results[:6],
        "query": vendor_name.strip(),
    })


@app.get("/vendors/new-form", response_class=HTMLResponse)
def new_vendor_form(request: Request, name: str = ""):
    """Return the new vendor inline creation form."""
    return templates.TemplateResponse(request, "partials/new_vendor_form.html", {
        "vendor_name": name,
        "display_name": name,
        "addr_line1": "",
        "addr_line2": "",
        "addr_city": "",
        "addr_state": "",
        "addr_zip": "",
        "addr_phone": "",
        "message": "",
    })


@app.post("/vendors/lookup-address", response_class=HTMLResponse)
def lookup_address(request: Request, vendor_name: str = Form("")):
    """Look up address for vendor name, return pre-filled form fragment."""
    addr = {}
    message = ""
    try:
        result = addr_lookup.lookup_google_places(vendor_name)
        if not result:
            result = addr_lookup.lookup_openstreetmap(vendor_name)
        if result:
            addr = result
        else:
            message = "Address not found — enter manually"
    except Exception as e:
        logger.warning(f"Address lookup failed for '{vendor_name}': {e}")
        message = "Address lookup unavailable — enter manually"

    return templates.TemplateResponse(request, "partials/new_vendor_form.html", {
        "vendor_name": vendor_name,
        "display_name": vendor_name,
        "addr_line1": addr.get("addr1", ""),
        "addr_line2": addr.get("addr2", ""),
        "addr_city": addr.get("city", ""),
        "addr_state": addr.get("state", ""),
        "addr_zip": addr.get("zip", ""),
        "addr_phone": addr.get("phone", ""),
        "message": message,
    })


@app.post("/vendors/create", response_class=HTMLResponse)
def create_vendor_route(
    request: Request,
    vendor_name: str = Form(""),
    display_name: str = Form(""),
    addr_line1: str = Form(""),
    addr_line2: str = Form(""),
    addr_city: str = Form(""),
    addr_state: str = Form(""),
    addr_zip: str = Form(""),
    addr_phone: str = Form(""),
):
    """Create vendor in GnuCash + JSON cache, return confirmation fragment."""
    display_name = display_name.strip() or vendor_name.strip()
    if not display_name:
        return HTMLResponse('<p class="error-msg">Vendor name is required.</p>')

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
        # Cache in JSON vendor database
        vm = VendorManager()
        key = strip_vendor_name(display_name)
        vm.vendors["vendors"][key] = {
            "display_name": display_name,
            "gnucash_guid": guid,
            "addr_line1": addr_line1,
            "addr_line2": addr_line2,
            "addr_city": addr_city,
            "addr_state": addr_state,
            "addr_zip": addr_zip,
        }
        vm.save()
        logger.info(f"Created vendor '{display_name}' with GUID {guid}")
        # Return JS to update the vendor input field, plus a success message
        safe_name = display_name.replace('"', '\\"').replace("'", "\\'")
        return HTMLResponse(
            f'<div class="success-msg">&#10003; Created vendor: {display_name}</div>'
            f'<script>document.getElementById("vendor-input").value = "{safe_name}";</script>'
        )
    except Exception as e:
        logger.error(f"Failed to create vendor '{display_name}': {e}")
        return HTMLResponse(f'<p class="error-msg">Failed to create vendor: {e}</p>')
