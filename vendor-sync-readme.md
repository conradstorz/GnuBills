# Vendor Sync Utility

## Overview

The Vendor Sync Utility (`vendor_sync.py`) is a command-line tool that synchronizes vendor data between two databases:

1. **JSON Database** (`data/vendor_database.json`) - Your local vendor repository with addresses, phone numbers, and metadata
2. **GnuCash Database** (`data/CFSIV_Sqlite3_database.gnucash`) - The GnuCash SQLite database

The tool supports **bidirectional synchronization**, ensuring vendor data stays consistent between both systems.

## Key Features

- **Bidirectional Sync**: Sync vendors in both directions (JSON ↔ GnuCash)
- **One-Way Sync**: Sync only from JSON to GnuCash or vice versa
- **Dry Run Mode**: Preview changes without modifying any data
- **Address Preservation**: Maintains complete vendor address information
- **Smart Matching**: Matches vendors by GUID or name to avoid duplicates
- **Account Preservation**: Keeps expense account assignments when syncing from GnuCash

## Installation & Requirements

This tool is part of the Bill Processor project and requires:

- Python 3.11+
- UV package manager (required per project style guide)
- SQLite3 support
- Loguru for logging

All dependencies are managed via `pyproject.toml`.

## Basic Usage

All commands must be run using the `uv run` prefix:

```bash
uv run python src/vendor_sync.py [options]
```

## Command-Line Options

### Sync Modes

| Option | Description |
|--------|-------------|
| `--bidirectional` | Sync in both directions (GnuCash → JSON, then JSON → GnuCash) |
| `--from-gnucash` | Import vendors FROM GnuCash TO JSON database only |
| `--to-gnucash` | Export vendors FROM JSON TO GnuCash database only |
| *(no option)* | Default behavior: bidirectional sync |

### Additional Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview what would happen without making changes |
| `--list` | List all vendors in the JSON database |
| `--force` | Force recreate existing vendors (not fully implemented) |

## Usage Examples

### 1. Bidirectional Sync (Recommended)

Sync vendors in both directions - import new vendors from GnuCash and create missing vendors in GnuCash:

```bash
uv run python src/vendor_sync.py --bidirectional
```

Or simply:

```bash
uv run python src/vendor_sync.py
```

**What happens:**
1. **Step 1**: Imports all vendors from GnuCash into JSON database
   - New vendors in GnuCash are added to JSON
   - Existing vendors in JSON are updated with GnuCash data
   - Expense account assignments are preserved
2. **Step 2**: Creates any missing vendors in GnuCash from JSON
   - Vendors that exist only in JSON are created in GnuCash
   - GnuCash GUIDs and IDs are saved back to JSON

### 2. Import from GnuCash Only

Import vendors from GnuCash database into JSON, but don't create any new vendors in GnuCash:

```bash
uv run python src/vendor_sync.py --from-gnucash
```

**Use case:** You've manually created vendors in GnuCash and want to import them into your JSON database.

### 3. Export to GnuCash Only

Create missing vendors in GnuCash from your JSON database:

```bash
uv run python src/vendor_sync.py --to-gnucash
```

**Use case:** You've added vendors to your JSON database and want to create them in GnuCash.

### 4. Preview Changes (Dry Run)

See what would happen without making any changes:

```bash
uv run python src/vendor_sync.py --bidirectional --dry-run
```

This shows:
- Which vendors would be imported from GnuCash
- Which vendors would be created in GnuCash
- No actual database changes are made

### 5. List Vendors

Display all vendors in your JSON database:

```bash
uv run python src/vendor_sync.py --list
```

Output shows:
- Vendor display name
- GnuCash ID (or "Not synced")
- Address indicator (📍 if address exists, ❌ if not)

Example output:
```
Vendors in database (23):
==================================================
Home Depot                 | 000001     | 📍
Lowes                      | 000002     | 📍
Best Buy                   | Not synced | ❌
```

## How It Works

### JSON Database Structure

The `vendor_database.json` file contains:

```json
{
  "vendors": {
    "homedepot": {
      "display_name": "Home Depot",
      "search_name": "home depot",
      "gnucash_guid": "abc123...",
      "gnucash_id": "000001",
      "addr_name": "Home Depot",
      "addr_line1": "123 Main St",
      "addr_line2": "Suite 100",
      "phone": "(555) 123-4567",
      "email": "contact@homedepot.com",
      "expense_account": "Expenses:Home Improvement",
      "expense_account_guid": "xyz789...",
      "address_source": "google"
    }
  },
  "aliases": {
    "home depot inc": "homedepot",
    "the home depot": "homedepot"
  }
}
```

### GnuCash Vendor Fields

The tool synchronizes these GnuCash vendor table fields:

| Field | Description |
|-------|-------------|
| `guid` | Unique identifier (generated) |
| `id` | Sequential vendor ID |
| `name` | Vendor display name |
| `currency` | USD GUID (default) |
| `active` | Active status (1 = active) |
| `notes` | Vendor notes |
| `addr_name` | Address name |
| `addr_addr1` | Address line 1 |
| `addr_addr2` | Address line 2 |
| `addr_phone` | Phone number |
| `addr_email` | Email address |

### Matching Logic

When syncing, vendors are matched by:

1. **GnuCash GUID** (most reliable) - if the JSON vendor has a `gnucash_guid`, it's matched to the GnuCash vendor with that GUID
2. **Vendor name** (fallback) - if no GUID match, vendors are matched by exact name comparison

This prevents duplicate vendors from being created.

### Data Preservation

#### When syncing FROM GnuCash TO JSON:
- Preserves `expense_account` and `expense_account_guid` if they exist in JSON
- Updates all other fields with GnuCash data
- Sets `address_source` to "gnucash"

#### When syncing FROM JSON TO GnuCash:
- Only creates vendors that don't already exist
- Updates JSON with the generated GnuCash GUID and ID
- Skips vendors that already exist (unless `--force` is used)

## Workflow Examples

### Scenario 1: First-Time Setup

You have vendors in GnuCash and want to start using the JSON database:

```bash
# Import all vendors from GnuCash to JSON
uv run python src/vendor_sync.py --from-gnucash

# Review the JSON file
cat data/vendor_database.json
```

### Scenario 2: Adding Vendors via JSON

You've manually added vendor entries to `vendor_database.json` with addresses:

```bash
# Create these vendors in GnuCash
uv run python src/vendor_sync.py --to-gnucash
```

### Scenario 3: Regular Maintenance

Keep both databases in sync:

```bash
# Run bidirectional sync periodically
uv run python src/vendor_sync.py --bidirectional
```

### Scenario 4: Safe Testing

Test changes before applying them:

```bash
# See what would change
uv run python src/vendor_sync.py --bidirectional --dry-run

# If it looks good, run without dry-run
uv run python src/vendor_sync.py --bidirectional
```

## Output & Logging

### Console Output

The tool provides detailed console output:

- Progress indicators (✅, ❌, 📍, 🔄, etc.)
- Step-by-step sync operations
- Summary statistics
- Clear section dividers

Example output:
```
============================================================
BIDIRECTIONAL VENDOR SYNC
============================================================
JSON Database: D:\...\data\vendor_database.json
GnuCash Database: D:\...\data\CFSIV_Sqlite3_database.gnucash
Dry run: False
============================================================

Step 1: GnuCash → JSON (import from database)
------------------------------------------------------------
📥 Found 23 vendors in GnuCash database
  ✏️  Updated: Home Depot
  ✨ New: Ace Hardware

📊 Summary:
  New vendors added: 1
  Existing vendors updated: 22
  Total: 23

✅ JSON database updated successfully

Step 2: JSON → GnuCash (create missing vendors)
------------------------------------------------------------
🔍 Discovering GnuCash database schema...
📍 Using GnuCash database: D:\...\CFSIV_Sqlite3_database.gnucash
✅ Found vendors table with 15 columns
📍 Address columns available: ['addr_name', 'addr_addr1', 'addr_addr2', ...]
✅ Built INSERT statement with 15 columns
✅ Loaded 23 vendors from database
🚀 Starting sync of 23 vendors...

Processing: Home Depot
  📍 Already exists (ID: 000001)
  
============================================================
BIDIRECTIONAL SYNC COMPLETE
============================================================
Synced from GnuCash: 23
Synced to GnuCash: 0
Updated in JSON: 0
Skipped: 23
Errors: 0
============================================================

🎉 Vendor sync completed successfully!
```

### Log Files

Detailed logs are written to:
- **File**: `logs/vendor_sync.log` (DEBUG level - full details)
- **Console**: INFO level only (clean output, no DEBUG spam)

The log file includes:
- Full stack traces for errors
- Variable values for debugging
- Database operation details
- API call information

## Troubleshooting

### Issue: "Vendor database not found"

**Problem**: The `vendor_database.json` file doesn't exist.

**Solution**: Create an empty JSON database:

```json
{
  "vendors": {},
  "aliases": {}
}
```

Save this to `data/vendor_database.json`.

### Issue: "GnuCash database not found"

**Problem**: The path in `config.py` is incorrect.

**Solution**: Check `src/config.py` and verify `GNUCASH_DB_PATH` points to your GnuCash SQLite file.

### Issue: "Schema discovery failed"

**Problem**: Cannot read the GnuCash database structure.

**Solution**: 
1. Ensure the GnuCash file is not open in GnuCash (close it first)
2. Verify the file is a valid SQLite database
3. Check file permissions

### Issue: Duplicate vendors created

**Problem**: Vendors appear twice in GnuCash.

**Solution**: This happens if vendor names don't match exactly. The tool matches by:
1. GUID (most reliable)
2. Exact name match

Ensure vendor names in JSON match GnuCash exactly, or ensure `gnucash_guid` is populated in JSON.

### Issue: Address data not syncing

**Problem**: Addresses aren't being copied to GnuCash.

**Solution**: 
1. Check that JSON has fields: `addr_name`, `addr_line1`, `addr_line2`, `phone`
2. Verify console output shows "Address data:" section
3. Check log file for errors during INSERT

## Database Backup Recommendations

**Before running sync operations**, especially the first time:

1. **Backup GnuCash database**:
   ```bash
   cp data/CFSIV_Sqlite3_database.gnucash data/CFSIV_Sqlite3_database.gnucash.backup
   ```

2. **Backup JSON database**:
   ```bash
   cp data/vendor_database.json data/vendor_database.json.backup
   ```

3. **Use dry-run first**:
   ```bash
   uv run python src/vendor_sync.py --bidirectional --dry-run
   ```

## Integration with Bill Processor

The vendor sync tool is designed to work with the Bill Processor workflow:

1. **Vendor Discovery**: Bill Processor uses `vendor_manager.py` to look up vendors in JSON
2. **Address Lookup**: If vendor not found, uses Google Places API to find address
3. **Vendor Creation**: Adds new vendor to JSON database
4. **Sync to GnuCash**: Run vendor_sync.py to create the vendor in GnuCash
5. **Bill Entry**: Now the vendor exists in both databases for bill entry

This keeps your vendor data synchronized and addresses readily available.

## Advanced Usage

### Programmatic Usage

You can also import and use the VendorSyncUtility class in your own scripts:

```python
from vendor_sync import VendorSyncUtility

sync_util = VendorSyncUtility()

# Load and discover schema
if sync_util.load_vendor_database() and sync_util.discover_schema():
    # Perform sync
    success = sync_util.sync_bidirectional(dry_run=False)
    
    # Check stats
    print(f"Created: {sync_util.stats['created']}")
    print(f"Updated: {sync_util.stats['updated']}")
    print(f"Errors: {sync_util.stats['errors']}")
```

## Exit Codes

The tool returns standard exit codes:

- `0`: Success (no errors)
- `1`: Failure (errors occurred or user cancelled)

This allows integration with shell scripts and automation.

## Future Enhancements

Potential improvements (not yet implemented):

- `--force` option to recreate/update existing vendors
- Conflict resolution strategies
- Vendor deduplication tools
- Export to CSV for review
- Interactive mode for resolving conflicts

## Related Files

- `src/vendor_manager.py` - Vendor management and lookup
- `src/address_lookup.py` - Google Places API integration
- `data/vendor_database.json` - JSON vendor database
- `data/CFSIV_Sqlite3_database.gnucash` - GnuCash SQLite database
- `docs/GNUCASH_SQLITE_BILL_WORKFLOW.md` - Bill workflow documentation

## Support

For issues or questions:

1. Check the log file: `logs/vendor_sync.log`
2. Run with `--dry-run` to preview changes
3. Review the console output for specific error messages
4. Check `PROGRAMMING_STYLE_GUIDE.md` for project conventions

---

*Last Updated: January 14, 2026*
