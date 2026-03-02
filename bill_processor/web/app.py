"""
FastAPI web application for GnuCash Bill Processor.
Serves a state-aware dashboard for managing vendor bills.
"""
import html
import json
import os
import threading
import time
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
from bill_processor.vendor_sync import VendorSyncUtility
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
        "error": None,
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


def _process_one_bill(bill: dict) -> dict:
    """
    Run create/post/pay for a single queued bill dict.
    Returns {"ok": True} or {"ok": False, "error": str}.
    """
    vm = VendorManager()
    vendor_data, match_type = vm.find_vendor(bill["vendor_name"])
    if not vendor_data:
        return {"ok": False, "error": f"Vendor not found: {bill['vendor_name']}"}

    vendor_guid = vendor_data.get("gnucash_guid")
    if not vendor_guid:
        gc_vendor = gnucash_db.find_vendor_by_name(vendor_data.get("display_name", ""))
        if not gc_vendor:
            return {"ok": False, "error": f"No GnuCash record for vendor: {vendor_data.get('display_name')}"}
        vendor_guid = gc_vendor["guid"]

    # Get expense account GUID — check both possible field names in vendor_data
    expense_guid = vendor_data.get("expense_account_guid") or vendor_data.get("expense_account")
    # expense_account may hold a name string rather than a GUID; treat short strings as names
    if expense_guid and len(str(expense_guid)) != 32:
        expense_guid = None
    if not expense_guid:
        return {"ok": False, "error": f"No expense account GUID for vendor: {vendor_data.get('display_name')}"}

    checking_accounts = gnucash_db.get_checking_accounts()
    if not checking_accounts:
        return {"ok": False, "error": "No checking account found in GnuCash"}
    checking_guid = checking_accounts[0]["guid"]

    bill_date = bill["date"]
    try:
        bill_guid = gnucash_db.create_bill(
            vendor_guid=vendor_guid,
            expense_account_guid=expense_guid,
            amount=bill["amount"],
            memo=bill.get("memo", ""),
            bill_date=bill_date,
        )
        gnucash_db.post_bill(
            bill_guid=bill_guid,
            post_date=bill_date,
            due_date=bill_date,
        )
        gnucash_db.pay_bill(
            bill_guid=bill_guid,
            checking_account_guid=checking_guid,
            payment_date=bill_date,
            memo=bill.get("memo", ""),
        )
        logger.info(f"Processed bill: {bill['vendor_name']} ${bill['amount']:.2f}")
        return {"ok": True}
    except Exception as e:
        logger.error(
            f"Failed to process bill {bill['vendor_name']}: {e}. "
            f"Bill may have been partially created in GnuCash — check for duplicates before retrying."
        )
        return {"ok": False, "error": f"{e} (bill may be partially created in GnuCash — check before retrying)"}


@app.post("/bills/queue/process", response_class=HTMLResponse)
def process_all(request: Request):
    """Process all queued bills through GnuCash."""
    queue = queue_io.read_queue()
    errors = []
    # Sort descending by file-line index so removals don't shift earlier indices
    for bill in sorted(queue, key=lambda b: b["_index"], reverse=True):
        result = _process_one_bill(bill)
        if result["ok"]:
            queue_io.remove_bill(bill["_index"])
        else:
            errors.append(f"{bill['vendor_name']}: {result['error']}")
    remaining = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": remaining,
        "last_error": "; ".join(errors) if errors else None,
    })


@app.post("/bills/queue/{index}/process", response_class=HTMLResponse)
def process_one(request: Request, index: int):
    """Process a single queued bill through GnuCash."""
    queue = queue_io.read_queue()
    # Find the bill with this file-line index
    bill = next((b for b in queue if b["_index"] == index), None)
    if not bill:
        return templates.TemplateResponse(request, "partials/queued_bills.html", {
            "queue": queue,
            "last_error": f"Bill at index {index} not found in queue",
        })
    result = _process_one_bill(bill)
    if result["ok"]:
        queue_io.remove_bill(index)
    remaining = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": remaining,
        "last_error": None if result["ok"] else result["error"],
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
        "addr_line1": addr.get("addr_line1", ""),
        "addr_line2": addr.get("addr_line2", ""),
        "addr_city": "",
        "addr_state": "",
        "addr_zip": "",
        "addr_phone": addr.get("phone") or "",
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
            "addr_phone": addr_phone,
        }
        vm.save()
        logger.info(f"Created vendor '{display_name}' with GUID {guid}")
        # Return JS to update the vendor input field, plus a success message
        return HTMLResponse(
            f'<div class="success-msg">&#10003; Created vendor: {html.escape(display_name)}</div>'
            f'<script>document.getElementById("vendor-input").value = {json.dumps(display_name)};</script>'
        )
    except Exception as e:
        logger.error(f"Failed to create vendor '{display_name}': {e}")
        return HTMLResponse(f'<p class="error-msg">Failed to create vendor: {e}</p>')


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
    return templates.TemplateResponse(request, "partials/sync_status.html", {
        "sync": sync,
        "error": error,
    })


@app.get("/partials/sync-status", response_class=HTMLResponse)
def get_sync_status_partial(request: Request):
    """Return the sync status card (for HTMX polling)."""
    sync = _get_sync_status()
    return templates.TemplateResponse(request, "partials/sync_status.html", {
        "sync": sync,
        "error": None,
    })


@app.get("/partials/queued-bills", response_class=HTMLResponse)
def get_queued_bills_partial(request: Request):
    """Return the queued bills card (for HTMX polling)."""
    queue = queue_io.read_queue()
    return templates.TemplateResponse(request, "partials/queued_bills.html", {
        "queue": queue,
        "last_error": None,
    })


@app.post("/shutdown")
def shutdown():
    """Stop the server. Uses os._exit for reliable cross-platform termination."""
    def _stop():
        time.sleep(1.0)
        os._exit(0)
    threading.Thread(target=_stop, daemon=True).start()
    return {"message": "Server shutting down"}
