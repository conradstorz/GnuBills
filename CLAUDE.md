# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**All Python execution MUST use `uv run`. Never use `pip` or call `python` directly.**

```bash
uv sync                              # Install/update dependencies
uv run python -m bill_processor.main # Run CLI bill processor
uv run bill-entry                    # Launch bill entry GUI (tkinter)
uv run vendor-manager-gui            # Launch vendor manager GUI
uv run vendor-sync                   # Sync vendors between JSON and GnuCash
uv run uvicorn bill_processor.web.app:app --port 8000  # Start web UI server (dev mode)
# Or double-click launcher.pyw for Windows desktop launch (no console window)

# Testing
uv run pytest                        # Run all tests
uv run pytest bill_processor/tests/test_utils.py  # Run a single test file
uv run pytest -k "test_fuzzy"        # Run tests matching a pattern
uv run pytest --cov=bill_processor   # Run with coverage

# Add dependencies
uv add <package>
uv add --dev <package>
```

**GnuCash must be closed** before running any tool that writes to the database.

## Architecture

This tool automates the GnuCash vendor bill workflow (create → post → pay) by writing directly to the GnuCash SQLite database. There is no GnuCash Python API used — all GnuCash interactions go through raw SQL.

### Data flow

1. **Input**: Bills entered via GUI (`bill_entry_gui.py`) or as text in `data/bills_to_process.txt` (`vendor, amount, memo, date`)
2. **Vendor resolution**: `VendorManager` checks local JSON database (`data/vendor_database.json`) first, then GnuCash DB, then offers to create a new vendor with address lookup
3. **Address lookup**: `address_lookup.py` queries Google Places API (preferred) or OpenStreetMap Nominatim (free fallback) using locality settings from `config.py`
4. **Bill processing**: `gnucash_db.py` executes the 3-step workflow directly on the SQLite file:
   - `create_bill()` → inserts into `invoices` + `entries` tables
   - `post_bill()` → creates `lots`, `transactions`, `splits` entries + `slots` metadata
   - `pay_bill()` → creates payment transaction with splits linking AP lot to checking account
5. **Output**: Bills visible in GnuCash; checks can be printed with vendor addresses

### Key modules

| Module | Role |
|--------|------|
| `gnucash_db.py` | All database I/O — the only place that touches the `.gnucash` SQLite file. Every write is verified immediately after execution. |
| `schema_discovery.py` | Handles column name variations across GnuCash versions (e.g., `addr_addr1` vs `addr1`). Always use `_get_column()` helper instead of hardcoding column names. |
| `vendor_manager.py` | `VendorManager` class — two-layer vendor lookup (JSON cache → GnuCash DB). Handles fuzzy matching, alias management, and vendor creation. |
| `config.py` | All configurable paths, GnuCash account structure, API keys, fuzzy match thresholds. The single source of truth for environment-specific values. |
| `utils.py` | Shared utilities: `parse_input_line()`, `fuzzy_match_vendor()`, display helpers. |
| `address_lookup.py` | Google Places / OSM address lookup, returns structured address dict. |
| `bill_entry_gui.py` | Tkinter GUI — writes to `bills_to_process.txt`, launches processing subprocess, shows live output. |
| `vendor_manager_gui.py` | Tkinter GUI for browsing/editing the vendor JSON database. |
| `vendor_sync.py` | Bidirectional sync between `vendor_database.json` and the GnuCash vendors table. |
| `logging_setup.py` | Loguru configuration. Always use `from loguru import logger` — never `import logging`. |
| `web/app.py`      | FastAPI routes — dashboard, queue CRUD, vendor search/create, bill processing, vendor sync |
| `web/queue_io.py` | Queue file I/O — read/write/edit/delete for `data/bills_to_process.txt` |
| `launcher.pyw`    | Windows launcher — starts uvicorn and opens browser at `localhost:8000` |

### GnuCash database schema notes

The GnuCash SQLite schema (documented in `docs/GNUCASH_SQLITE_BILL_WORKFLOW.md`) uses these tables for bill processing: `vendors`, `accounts`, `invoices`, `entries`, `lots`, `transactions`, `splits`, `slots`.

- All primary keys are 32-char hex GUIDs (no hyphens): `uuid.uuid4().hex`
- Amounts are stored as integers in hundredths of a cent (multiply by 100 for `value_num`; `value_denom = 100`)
- Lot/split linkage is critical for posting: the `ap_guid` split must reference the lot, and slots on the invoice and lot must be set correctly
- The `slots` table stores key-value metadata — bill posting state is stored here (`invoice-posted`, `invoice-postlot`, etc.)

### Vendor database (JSON)

`data/vendor_database.json` structure:
```json
{
  "vendors": {
    "vendor_key": {
      "display_name": "Acme Electric",
      "gnucash_guid": "...",
      "gnucash_id": "000001",
      "addr_line1": "123 Main St",
      ...
    }
  },
  "aliases": {
    "acme": "vendor_key",
    "acme elec": "vendor_key"
  }
}
```

This JSON is the authoritative local cache. `vendor_sync.py` reconciles it with GnuCash.

## Testing

Tests use a temporary copy of the real GnuCash database (see `conftest.py`). The `db_connection` fixture monkey-patches `gnucash_db.config.GNUCASH_DB_PATH` to point at the temp copy. Tests that require the real database are skipped if it doesn't exist.

Mark tests requiring manual verification: `@pytest.mark.manual`

Property-based tests use Hypothesis. When a property test discovers a failing edge case, suspend it with `@pytest.mark.skip(reason="Edge case: ...")` rather than fixing immediately.

## Style conventions

- **Logging**: `from loguru import logger` everywhere. Configured in `logging_setup.py`.
- **Paths**: Always use `Path` objects; hardcoded paths belong in `config.py` only.
- **DB writes**: Every INSERT/UPDATE in `gnucash_db.py` must be followed by a verification read. The principle: "User data is SACRED - we verify writes succeeded before returning."
- **Schema access**: Use `_get_column(table, expected_name)` for all column references in `gnucash_db.py` to handle cross-version compatibility.
- **Why raw SQL, not piecash**: The `piecash` ORM library was evaluated and rejected. See `docs/WHY_NOT_PIECASH.md`. Do not introduce piecash abstractions.
