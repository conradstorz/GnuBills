# Bill Processor Project History

## Project Genesis: January 7-8, 2026

This document captures the complete design discussion and requirements gathering for the GnuCash Bill Processor system.

---

## Original Problem

**Goal**: Print checks from GnuCash with vendor addresses automatically filled in for transactions that are NOT part of the AR/AP cycle.

**Challenge**: GnuCash only auto-populates address fields when a transaction is linked to a business owner (Customer, Vendor, Employee). Regular transactions don't have this capability.

---

## Initial Exploration: GnuCash Check Format Files (.chk)

### What We Learned About .chk Files

GnuCash 4.x uses key-value text format files (not XML) for check printing. Location:
- Windows: `%APPDATA%\gnucash\checks\`
- Custom user checks can be placed there

### Valid Check Item Keywords

| Keyword | Description |
|---------|-------------|
| PAYEE | Payee/Description from transaction |
| DATE | Transaction date |
| NOTES | Transaction notes field |
| CHECK_NUMBER | Check number (from Num field) |
| MEMO | Split memo field |
| ACTION | Action field |
| AMOUNT_NUMBER | Numeric amount |
| AMOUNT_WORDS | Amount in words |
| TEXT | Custom static text |
| ADDRESS | Address block (5 lines) |
| DATE_FORMAT | Prints date format string under date |
| SPLITS_AMOUNT | Each split's amount on separate lines |
| SPLITS_MEMO | Each split's memo on separate lines |
| SPLITS_ACCOUNT | Each split's account name on separate lines |
| PICTURE | Image file |

### Attempted Workarounds

1. **Using NOTES field for address**: Works but GnuCash GUI doesn't allow entering newlines in the Notes field
2. **Multi-line via SPLITS_MEMO**: Would require creating fake splits just for address lines
3. **Manually editing XML**: Could insert `&#10;` for newlines but tedious

### Conclusion

The check format system has limitations. Better solution: Use proper AP workflow with vendors that have addresses.

---

## Solution: Bill Processor System

Rather than fight the check printing limitations, create a system that:
1. Makes it easy to enter bills for vendors
2. Automatically looks up and stores vendor addresses
3. Creates proper AP transactions in GnuCash
4. Leverages GnuCash's built-in check printing with address support

---

## Requirements Gathering Q&A

### 1. Input & Workflow

**Q1.1**: How to provide vendor name + amount?
**A**: `name, amount, memo, date` format (memo and date optional)

**Q1.2**: One-time batch or queue over time?
**A**: Parallel database - system shows status of all transactions and asks how to proceed each run

**Q1.3**: Expense accounts per vendor or single default?
**A**: Specific expense account per vendor with unique name: `cmsnpd_<stripped_vendor_name>`

### 2. Address Lookup

**Q2.1**: Locality?
**A**: Louisville, KY area

**Q2.2**: Address lookup services?
**A**: Yes to all - Google Places API, OpenStreetMap/Nominatim, manual fallback

**Q2.3**: Ambiguous results handling?
**A**: Pick closest to location and flag for review

### 3. GnuCash Integration

**Q3.1**: File format?
**A**: SQLite (recommended for easier Python integration)

**Q3.2**: Concurrent access?
**A**: No - GnuCash will be closed when running

**Q3.3**: Account paths?
**A**: New expense accounts created under `Expenses` placeholder, may be moved later by user

**Q3.4**: Payment terms?
**A**: Due on receipt (these are bills to be paid)

### 4. Vendor Matching

**Q4.1**: Matching strategy?
**A**: Fuzzy match as long as no two vendors match to the same transaction

**Q4.2**: Vendor ID format?
**A**: Sequential (`V0001`, `V0002`, etc.)

### 5. Data Persistence

**Q5.1**: What to store per vendor?
**A**: Everything reasonable - data storage is cheap. Keep every detail including all past bills and status.

**Q5.2**: JSON file location?
**A**: Same place as GnuCash files with a good name

### 6. Output & Review

**Q6.1**: Review step before creating bills?
**A**: Yes, a Y/N confirmation step

**Q6.2**: Generate report?
**A**: No separate report needed, logging is part of all code

### 7. Technical Environment

**Q7.1**: OS?
**A**: Windows

**Q7.2**: Python version?
**A**: Greater than 3.11

**Q7.3**: Scripts or executable?
**A**: Scripts are fine

### 8. Edge Cases

**Q8.1**: Vendor address changes?
**A**: User's problem to handle manually

**Q8.2**: Duplicate bills for same vendor?
**A**: Both go into JSON and are handled separately

---

## Key Design Decisions

### Sequential ID Conflict Prevention

**Problem**: If user manually creates vendors/bills in GnuCash, stored "next_id" in JSON would conflict.

**Solution**: Query GnuCash for max ID each time, don't store next ID in JSON.

```python
def get_next_vendor_id(conn):
    cursor = conn.execute("""
        SELECT id FROM vendors 
        WHERE id LIKE 'V%' 
        ORDER BY CAST(SUBSTR(id, 2) AS INTEGER) DESC 
        LIMIT 1
    """)
    # Returns V0043 if max is V0042
```

### Expense Account Search Strategy

**Problem**: User will move expense accounts after creation, breaking path-based lookups.

**Solution**: Search entire account tree by name (`cmsnpd_*`), not by path.

### Bill Status on Creation

**Decision**: Create POSTED bills (not drafts) so they're immediately visible in "Process Payment" and ready for check printing.

---

## Final Specifications

| Setting | Value |
|---------|-------|
| GnuCash format | SQLite |
| Bill status on create | Posted (ready for payment) |
| Input format | `name, amount, memo, date` (memo/date optional) |
| Default memo | "no memo" |
| Default date | Today |
| Expense account naming | `cmsnpd_<stripped_vendor_name>` |
| Expense account parent | `Expenses` (initially, user may move) |
| Account search method | By name anywhere in tree |
| Vendor ID format | `V0001`, `V0002`, etc. |
| Bill ID format | `B-0001`, `B-0002`, etc. |
| ID generation | Query GnuCash for max each time |
| Locality | Louisville, KY |
| Address lookup | Google Places → OSM → Manual fallback |
| Ambiguous results | Pick closest + flag for review |
| Duplicate detection | Check existing unpaid bills |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT FILE                              │
│  bills_to_process.txt                                           │
│  ─────────────────────                                          │
│  Acme Electric, 150.00, January service                         │
│  Louisville Water, 75.50                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BILL PROCESSOR                             │
│                      bill_processor.py                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Load vendor_database.json                                   │
│  2. Load GnuCash SQLite                                         │
│  3. For each input line:                                        │
│     ├── Fuzzy match to known vendor                             │
│     ├── If new: web lookup address → add to JSON                │
│     ├── If not in GnuCash: create vendor                        │
│     ├── Check for duplicate/existing bills                      │
│     └── Queue bill for creation                                 │
│  4. Display summary + status of all pending                     │
│  5. Prompt: "Create these bills? [Y/N]"                         │
│  6. Create bills in GnuCash                                     │
│  7. Update JSON with new bill records                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    vendor_database.json                         │
│  • Vendor metadata and addresses                                │
│  • Bill history and status cache                                │
│  • Aliases for fuzzy matching                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GnuCash SQLite Database                      │
│  • Vendors with full addresses                                  │
│  • Posted bills ready for payment                               │
│  • User manually: Process Payment → Print Checks                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Manual Steps (User Responsibility)

After running the bill processor, user must manually in GnuCash:

1. **Process Payment**: Business → Vendor → Process Payment
2. **Print Checks**: File → Print Checks (addresses auto-filled from vendor)
3. **Reconcile**: Normal bank reconciliation

---

## File Structure

```
D:\Users\Conrad\Documents\GnuCash\bill_processor\
├── docs/
│   └── PROJECT_HISTORY.md        # This file
├── src/
│   ├── bill_processor.py         # Main entry point
│   ├── config.py                 # Settings & paths
│   ├── gnucash_db.py             # SQLite interface
│   ├── vendor_manager.py         # Vendor operations
│   ├── address_lookup.py         # Web address lookup
│   └── utils.py                  # Utilities
├── data/
│   ├── vendor_database.json      # Vendor data (created on first run)
│   └── bills_to_process.txt      # Input file
├── README.md                     # Quick start guide
└── requirements.txt              # Python dependencies
```

---

## Future Enhancements (Not Implemented)

- GUI interface for bill entry
- Automatic bill import from email/PDF
- Payment scheduling
- Recurring bill templates
- Report generation

---

*Document created: January 8, 2026*
*Project initiated by: Conrad*
*Technical design by: GitHub Copilot*
