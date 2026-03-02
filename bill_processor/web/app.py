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
from bill_processor.utils import parse_input_line
from bill_processor.vendor_manager import VendorManager

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
    })
