# GnuBills v1.0.0-MVP Release Notes

**Release Date:** January 16, 2026

## Overview

GnuBills is a bill processing system for GnuCash that automates vendor bill entry, posting, and payment directly into the GnuCash SQLite database.

## Features

### 🎯 Core Functionality
- **3-Step Bill Workflow**: Automatically creates, posts, and pays vendor bills
  - Step 1: Create unposted bill with invoice entry
  - Step 2: Post bill with AP transaction
  - Step 3: Pay bill with check transaction (includes memo in register)
- **Database Verification**: Validates each step before proceeding
- **Smart Error Handling**: Aborts on failures, preserves failed bills in queue

### 🖥️ User Interfaces
- **GUI Application** (`bill_entry_gui.py`): User-friendly interface for bill entry
  - Real-time vendor name autocomplete with fuzzy matching
  - Keyboard navigation (↓↑ arrows, Enter, Escape)
  - Account selection dialogs
  - Progress tracking with visual feedback
  - Vendor management integration
  
- **Command-Line Tool** (`bill_processor.py`): Batch bill processing
  - Process multiple bills from text file
  - Interactive account selection
  - Detailed progress indicators
  - Comprehensive logging

### 🔍 Vendor Management
- **Fuzzy Matching**: Uses thefuzz library for intelligent vendor lookup
  - 50% threshold for autocomplete suggestions
  - Token set ratio algorithm for flexible matching
  - Searches both local JSON database and GnuCash database
- **Dual Database**: Maintains vendor data in both JSON and GnuCash
  - Automatic synchronization
  - Handles vendor creation and updates

### 📊 Data Integrity
- **Transaction Verification**: Confirms all database writes
- **Proper GnuCash Schema**: Follows GnuCash 4.14 native behavior
  - Uses trans-txn-type="I" for bills
  - Uses trans-txn-type="P" for payments
  - Proper lot management for owner tracking
  - Correct slot assignments
- **Smart File Cleanup**: Removes only successfully processed bills from queue

### 📝 Documentation
- Comprehensive workflow documentation from database snapshots
- Programming style guide
- Detailed README files for each component
- Schema discovery and analysis tools

## Technical Details

### Database Operations
- Direct SQLite3 manipulation of GnuCash database
- GUID generation following GnuCash format (32-char hex)
- Amount storage using numerator/denominator pairs
- Proper timestamp handling (ISO 8601 with timezone)

### Key Functions
- `create_bill()`: Creates unposted vendor bill with entry
- `post_bill()`: Posts bill with lot and AP transaction
- `pay_bill()`: Pays bill with payment lot and check transaction
- `ensure_ap_account_exists()`: Manages Accounts Payable account
- `fuzzy_match_vendor()`: Intelligent vendor name matching

### File Structure
```
src/
  ├── bill_entry_gui.py         # GUI application
  ├── bill_processor.py          # Command-line processor
  ├── gnucash_db.py              # Database operations
  ├── vendor_manager.py          # Vendor management
  ├── address_lookup.py          # Address validation
  └── utils.py                   # Shared utilities

data/
  ├── vendor_database.json       # Local vendor data
  ├── bills_to_process.txt       # Bill queue (auto-created)
  └── snapshots/                 # GnuCash behavior documentation

docs/
  ├── GNUCASH_SQLITE_BILL_WORKFLOW.md
  └── PROJECT_HISTORY.md
```

## Known Limitations

- Requires GnuCash SQLite3 format database (not XML)
- Tested with GnuCash 4.14
- Single currency support (USD)
- Requires manual closing of GnuCash during bill processing

## Installation

```bash
# Clone repository
git clone https://github.com/conradstorz/GnuBills.git
cd GnuBills

# Install with uv (recommended)
uv sync

# Run GUI
uv run ./src/bill_entry_gui.py

# Or run command-line tool
uv run ./src/bill_processor.py
```

## Usage

### GUI Workflow
1. Launch `bill_entry_gui.py`
2. Enter vendor name (autocomplete will suggest matches)
3. Enter amount, date, and memo
4. Click "Add Bill to Queue"
5. Click "Process Bills" when ready
6. Select expense and checking accounts
7. Bills are automatically created, posted, and paid

### Command-Line Workflow
1. Add bills to `data/bills_to_process.txt`:
   ```
   Vendor Name | 123.45 | 2026-01-16 | Memo text
   ```
2. Run: `uv run ./src/bill_processor.py`
3. Select checking account from list
4. Watch progress as bills are processed

## Breaking Changes from Previous Versions

- **Deprecated**: `create_posted_bill()` → Use 3-step workflow instead
- **New Requirement**: Checking account must be selected for payment
- **Behavior Change**: Bills are now automatically paid (not just posted)

## Contributors

- Conrad Storz (@conradstorz)

## License

See LICENSE file for details.

---

**Note**: This is an MVP release. Features and APIs may change in future versions.
