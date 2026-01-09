# GnuCash Bill Processor

Automate vendor bill entry with address lookup for GnuCash.

## Quick Start

### Option 1: GUI Entry (Recommended)

```cmd
cd D:\Users\Conrad\Documents\GnuCash\bill_processor
python src\bill_entry_gui.py
```

The GUI provides:

- **Real-time fuzzy matching** as you type vendor names
- **Tab completion** from known vendors
- **Live preview** of bills queue
- **Edit/remove** entries before processing

### Option 2: Manual Entry

1. **Edit your bills file**: `data\bills_to_process.txt`

   ```text
   Acme Electric, 150.00, January service
   Louisville Water, 75.50
   Bob's Plumbing, 340.00, Kitchen repair, 2026-01-15
   ```

2. **Run the processor**:

   ```cmd
   python src\bill_processor.py
   ```

3. **Review and confirm** the proposed bills

4. **Open GnuCash** to process payments and print checks

## Input Format

```text
vendor_name, amount, memo, date
```

- `vendor_name` - Required. Business name (fuzzy matched)
- `amount` - Required. Bill amount
- `memo` - Optional. Defaults to "no memo"
- `date` - Optional. Defaults to today. Format: YYYY-MM-DD

## Configuration

Edit `src\config.py` to change:

- GnuCash database path
- Your locality for address searches
- API keys for address lookup

## First Run

On first run, the system will:

1. Create `data\vendor_database.json`
2. Prompt you to confirm settings
3. Guide you through any missing configuration

## Project Documentation

See `docs\PROJECT_HISTORY.md` for full design history and specifications.

## Requirements

- Python 3.11+
- GnuCash with SQLite backend
- Internet connection (for address lookups)

Install dependencies:

```cmd
pip install -r requirements.txt
```
