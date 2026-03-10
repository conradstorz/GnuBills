# GnuCash Bill Processor
*** this branch is now depricated *** 3/9/2026
**Simplify vendor bill management in GnuCash** - Automatically create complete vendor records with addresses and streamline the bill/post/pay workflow.

## Why Use This Tool?

### Problem 1: Creating Complete Vendor Records is Tedious
Manually entering vendor names and addresses in GnuCash is time-consuming and error-prone. This tool:
- **Automatically looks up vendor addresses** using Google Places API
- **Creates complete vendor records** with full mailing addresses
- **Saves time** - no more typing addresses manually

### Problem 2: Printing Checks with Addresses Requires the Bill/Post/Pay Process
GnuCash can only print vendor addresses on checks if you use the full bill workflow:
1. Create a vendor bill
2. Post the bill (creates accounts payable entry)
3. Pay the bill (creates the check transaction)

**This tool automates all three steps**, making it easy to:
- ✓ Create bills with proper vendor records
- ✓ Post bills to accounts payable
- ✓ Generate payment transactions ready for check printing
- ✓ Print checks with complete mailing addresses

Without this tool, you'd need to manually execute this multi-step process in GnuCash for every bill.

---

## Quick Start

### Installation

1. **Install uv** (modern Python package manager):
   ```cmd
   # On Windows with PowerShell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Clone this repository** and install dependencies:
   ```cmd
   cd path\to\bill_processor
   uv sync
   ```

3. **Configure the database path** in `src\config.py`:
   ```python
   GNUCASH_DB_PATH = Path(r"C:\path\to\your\database.gnucash")
   ```

4. **(Optional) Set up Google Places API** for automatic address lookup:
   ```cmd
   uv run python setup_google_api.py
   ```
   See `docs/GOOGLE_API_SETUP.md` for detailed instructions.

---

### Running the Bill Entry GUI

```cmd
uv run python src\bill_entry_gui.py
```

The GUI makes it easy to:
- Enter vendor bills with real-time autocomplete
- Preview your bills queue before processing
- Process all bills with one click (create → post → pay)

**Important:** Make sure GnuCash is **closed** before running this tool (database lock protection is enforced).

---

## How It Works

### Simple Workflow

1. **Enter bills** using the GUI or text file
2. **Vendor lookup** - Tool finds or creates vendors with addresses
3. **One-click processing** - Bills are created, posted, and paid in GnuCash
4. **Print checks** - Open GnuCash and print checks with addresses

### Input Format

Bills can be entered as simple text (GUI or `data\bills_to_process.txt`):

```text
Acme Electric, 150.00, January service
Louisville Water, 75.50
Bob's Plumbing, 340.00, Kitchen repair, 2026-01-15
```

Format: `vendor_name, amount, memo, date`
- **vendor_name** - Required (fuzzy matched)
- **amount** - Required
- **memo** - Optional (defaults to "no memo")
- **date** - Optional (defaults to today, format: YYYY-MM-DD)

---

## Configuration

Edit `src\config.py` for:

- **GnuCash database path** - Point to your `.gnucash` SQLite file
- **Your locality** - City/state for address searches (e.g., "Louisville, KY")
- **Google API key** - For automatic address lookups (optional but recommended)

---

## Requirements

- **Python 3.11+**
- **GnuCash 4.x or 5.x** with SQLite backend
- **uv** package manager ([installation](https://github.com/astral-sh/uv))
- Internet connection for address lookups

---

## Additional Documentation

- `docs/GOOGLE_API_SETUP.md` - Setting up address lookup
- `docs/GNUCASH_SQLITE_BILL_WORKFLOW.md` - How the bill/post/pay process works
- `docs/vendor-sync-readme.md` - Syncing vendors between JSON and GnuCash

---

## License

This is personal-use software. Use at your own risk. Always backup your GnuCash database before use.
