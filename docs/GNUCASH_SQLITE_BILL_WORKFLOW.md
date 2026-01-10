# GnuCash 4.14 SQLite3 Database Workflow for Bills and Payments

## Overview

This document describes the complete database workflow for creating and paying vendor bills in GnuCash 4.14 using direct SQLite3 database manipulation. All findings are based on empirical observation of GnuCash's native behavior through database snapshots taken at each step of the workflow.

**Important**: GnuCash must be closed when making direct database modifications, or changes may be overwritten when GnuCash saves.

---

## Table of Contents

1. [Database Structure Overview](#database-structure-overview)
2. [Complete Bill Lifecycle](#complete-bill-lifecycle)
3. [Step 1: Create Vendor](#step-1-create-vendor)
4. [Step 2: Create Unposted Bill](#step-2-create-unposted-bill)
5. [Step 3: Add Bill Entry (Line Item)](#step-3-add-bill-entry-line-item)
6. [Step 4: Post the Bill](#step-4-post-the-bill)
7. [Step 5: Pay the Bill](#step-5-pay-the-bill)
8. [Sidebar: Creating a Vendor](#sidebar-creating-a-vendor)
9. [Sidebar: Creating an Accounts Payable Account](#sidebar-creating-an-accounts-payable-account)
10. [Sidebar: Locating or Creating an Expense Account](#sidebar-locating-or-creating-an-expense-account)
11. [Sidebar: Locating a Checking Account](#sidebar-locating-a-checking-account)
12. [Slot Types Reference](#slot-types-reference)
13. [Key Findings Summary](#key-findings-summary)

---

## Database Structure Overview

GnuCash 4.14 SQLite3 databases contain 25 tables. The tables relevant to bill processing are:

| Table | Purpose |
|-------|---------|
| `vendors` | Vendor records (name, address, currency, etc.) |
| `accounts` | Chart of accounts (AP, expenses, checking, etc.) |
| `invoices` | Bill/invoice headers (links vendor to lot/transaction) |
| `entries` | Bill line items (description, amount, account) |
| `lots` | Grouping mechanism for related splits (bills + payments) |
| `transactions` | Transaction headers (date, description, currency) |
| `splits` | Individual debit/credit entries within transactions |
| `slots` | Key-value metadata attached to any object |
| `commodities` | Currency definitions (USD, etc.) |

### GUID Format

All primary keys are 32-character hexadecimal GUIDs (no hyphens). Generate using:
```python
import uuid
guid = uuid.uuid4().hex  # e.g., "086ec14f1ec744a2a3614b699b3e8c1b"
```

### Amount Format

All monetary amounts are stored as ratios: `value_num / value_denom`. For USD with 2 decimal places:
- `$456.54` → `value_num=45654`, `value_denom=100`
- Positive values = debits, Negative values = credits

---

## Complete Bill Lifecycle

```
┌─────────────────┐
│  Create Vendor  │  (if not exists)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Create Bill    │  invoices table: owner_type=4, date_posted=NULL
│  (Unposted)     │  slots: credit-note=0
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Add Entry      │  entries table: uses 'bill' column (NOT 'invoice')
│  (Line Item)    │  links to expense account
└────────┬────────┘
         │
         ▼
┌─────────────────┐     Creates:
│  Post Bill      │  ──► Lot (linked to AP account)
│                 │  ──► Transaction (trans-txn-type=I)
│                 │  ──► 2 Splits (AP credit, Expense debit)
│                 │  ──► Lot slots (title, gncInvoice)
│                 │  ──► Transaction slots (date-posted, trans-read-only, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐     Creates:
│  Pay Bill       │  ──► Payment Lot (with gncOwner slots!)
│                 │  ──► Payment Transaction (trans-txn-type=P)
│                 │  ──► 2 Splits (AP debit, Checking credit)
└─────────────────┘
```

---

## Step 1: Create Vendor

**Table**: `vendors`

| Column | Type | Description |
|--------|------|-------------|
| guid | TEXT PK | Unique identifier |
| name | TEXT | Vendor display name |
| id | TEXT | Vendor ID (e.g., "V-001") |
| notes | TEXT | Optional notes |
| currency | TEXT | GUID of currency (USD) |
| active | INT | 1=active, 0=inactive |
| tax_override | INT | Usually 0 |
| addr_name | TEXT | Contact name |
| addr_addr1 | TEXT | Address line 1 |
| addr_addr2 | TEXT | Address line 2 |
| addr_addr3 | TEXT | City, State ZIP |
| addr_addr4 | TEXT | Country (optional) |
| addr_phone | TEXT | Phone number |
| addr_fax | TEXT | Fax number |
| addr_email | TEXT | Email address |
| terms | TEXT | GUID of payment terms (NULL if none) |
| tax_inc | TEXT | Tax included flag |
| tax_table | TEXT | GUID of tax table (NULL if none) |

**Example**:
```sql
INSERT INTO vendors (guid, name, id, notes, currency, active, tax_override,
                     addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
                     addr_phone, addr_fax, addr_email, terms, tax_inc, tax_table)
VALUES ('4814b58d24cb4c7ab84d27331e7af826', 'Acme Corp', 'V-001', '',
        'c30af8dfe58c47099f57ad2eadf02e43', 1, 0,
        'John Smith', '123 Main St', '', 'Louisville, KY 40202', '',
        '502-555-1234', '', 'john@acme.com', NULL, 'NO', NULL);
```

---

## Step 2: Create Unposted Bill

**Table**: `invoices`

| Column | Type | Description |
|--------|------|-------------|
| guid | TEXT PK | Unique identifier |
| id | TEXT | Bill number (e.g., "B-001") |
| date_opened | TEXT | Date bill created (ISO format) |
| date_posted | TEXT | **NULL for unposted bills** |
| notes | TEXT | Optional notes |
| active | INT | 1=active |
| currency | TEXT | Currency GUID |
| owner_type | INT | **4 = vendor** (2 = customer) |
| owner_guid | TEXT | GUID of the vendor |
| terms | TEXT | Payment terms GUID (NULL if none) |
| billing_id | TEXT | External reference |
| post_txn | TEXT | **NULL until posted** |
| post_lot | TEXT | **NULL until posted** |
| post_acc | TEXT | **NULL until posted** |
| billto_type | INT | Usually 0 for bills |
| billto_guid | TEXT | NULL |
| charge_amt_num | INT | 0 |
| charge_amt_denom | INT | 1 |

**Critical**: `owner_type=4` indicates a vendor bill. `owner_type=2` would be a customer invoice.

**Required Slot** (on the invoice):

| obj_guid | name | slot_type | string_val |
|----------|------|-----------|------------|
| {invoice_guid} | credit-note | 1 | (empty) |

The `credit-note` slot with type=1 (int64) and empty value indicates this is NOT a credit note.

**Example**:
```sql
INSERT INTO invoices (guid, id, date_opened, date_posted, notes, active, currency,
                      owner_type, owner_guid, terms, billing_id, post_txn, post_lot,
                      post_acc, billto_type, billto_guid, charge_amt_num, charge_amt_denom)
VALUES ('63efd2b7b1694f7e8612cdffecb17500', 'B-001', '2026-01-09 10:59:00', NULL, '', 1,
        'c30af8dfe58c47099f57ad2eadf02e43', 4, '4814b58d24cb4c7ab84d27331e7af826',
        NULL, '', NULL, NULL, NULL, 0, NULL, 0, 1);

-- Required slot
INSERT INTO slots (id, obj_guid, name, slot_type, int64_val, string_val, double_val,
                   timespec_val, guid_val, numeric_val_num, numeric_val_denom, gdate_val)
VALUES (NULL, '63efd2b7b1694f7e8612cdffecb17500', 'credit-note', 1, 0, NULL, NULL,
        NULL, NULL, NULL, NULL, NULL);
```

---

## Step 3: Add Bill Entry (Line Item)

**Table**: `entries`

**CRITICAL FINDING**: For vendor bills, entries use the **`bill`** column, NOT the `invoice` column!

| Column | Type | Description |
|--------|------|-------------|
| guid | TEXT PK | Unique identifier |
| date | TEXT | Entry date (ISO format) |
| date_entered | TEXT | When entry was created |
| description | TEXT | Line item description |
| action | TEXT | Usually empty for bills |
| notes | TEXT | Optional notes |
| quantity_num | INT | Quantity numerator (usually same as amount) |
| quantity_denom | INT | Quantity denominator |
| i_acct | TEXT | **NULL for bills** (used for customer invoices) |
| i_price_num | INT | 0 for bills |
| i_price_denom | INT | 1 |
| i_discount_num | INT | 0 |
| i_discount_denom | INT | 1 |
| invoice | TEXT | **NULL for bills** |
| i_disc_type | TEXT | NULL |
| i_disc_how | TEXT | NULL |
| i_taxable | INT | 0 |
| i_taxincluded | INT | 0 |
| i_taxtable | TEXT | NULL |
| b_acct | TEXT | **Expense account GUID** |
| b_price_num | INT | **Amount numerator** |
| b_price_denom | INT | **Amount denominator** (100 for USD) |
| bill | TEXT | **GUID of the invoice/bill** |
| b_taxable | INT | 0 |
| b_taxincluded | INT | 0 |
| b_taxtable | TEXT | NULL |
| b_paytype | INT | 0 |
| billable | INT | 0 |
| billto_type | INT | 0 |
| billto_guid | TEXT | NULL |
| order_guid | TEXT | NULL |

**Example** ($456.54 expense):
```sql
INSERT INTO entries (guid, date, date_entered, description, action, notes,
                     quantity_num, quantity_denom,
                     i_acct, i_price_num, i_price_denom, i_discount_num, i_discount_denom,
                     invoice, i_disc_type, i_disc_how, i_taxable, i_taxincluded, i_taxtable,
                     b_acct, b_price_num, b_price_denom, bill,
                     b_taxable, b_taxincluded, b_taxtable, b_paytype,
                     billable, billto_type, billto_guid, order_guid)
VALUES ('a1b2c3d4e5f6...', '2026-01-09 10:59:00', '2026-01-09 10:59:00',
        'Monthly commission payment', '', '',
        45654, 100,
        NULL, 0, 1, 0, 1,
        NULL, NULL, NULL, 0, 0, NULL,
        '3fd492d92c494b13af6c0c0ef79dfb3b', 45654, 100, '63efd2b7b1694f7e8612cdffecb17500',
        0, 0, NULL, 0,
        0, 0, NULL, NULL);
```

---

## Step 4: Post the Bill

Posting a bill is the most complex step. It creates multiple related records:

### 4.1 Create the Lot

**Table**: `lots`

| Column | Type | Description |
|--------|------|-------------|
| guid | TEXT PK | Unique identifier |
| account_guid | TEXT | **AP account GUID** |
| is_closed | INT | -1 = closed, 0 = open |

```sql
INSERT INTO lots (guid, account_guid, is_closed)
VALUES ('efbfc70251a6439fba5425e2a7caa334', '086ec14f1ec744a2a3614b699b3e8c1b', -1);
```

### 4.2 Create Lot Slots

The lot needs metadata slots:

| obj_guid | name | slot_type | value |
|----------|------|-----------|-------|
| {lot_guid} | title | 4 (string) | "Bill B-001" |
| {frame_guid} | gncInvoice/invoice-guid | 5 (GUID) | {invoice_guid} |
| {lot_guid} | gncInvoice | 9 (frame) | {frame_guid} |

**Note**: Type 9 slots (KVP frames) create a hierarchy. The frame GUID is a new GUID that groups related slots.

### 4.3 Create the Transaction

**Table**: `transactions`

| Column | Type | Description |
|--------|------|-------------|
| guid | TEXT PK | Unique identifier |
| currency_guid | TEXT | Currency GUID |
| num | TEXT | Transaction number (empty for bills) |
| post_date | TEXT | Posting date (ISO format) |
| enter_date | TEXT | Entry date |
| description | TEXT | **Vendor name** |

```sql
INSERT INTO transactions (guid, currency_guid, num, post_date, enter_date, description)
VALUES ('36bf583e026745ffbd68485b1a891722', 'c30af8dfe58c47099f57ad2eadf02e43', '',
        '2026-01-09 10:59:00', '2026-01-09 10:59:00', 'Acme Corp');
```

### 4.4 Create Transaction Slots

| obj_guid | name | slot_type | value |
|----------|------|-----------|-------|
| {txn_guid} | trans-txn-type | 4 (string) | **"I"** (Invoice) |
| {txn_guid} | trans-read-only | 4 (string) | "Generated from an invoice. Try unposting the invoice." |
| {txn_guid} | trans-date-due | 6 (timespec) | Due date |
| {txn_guid} | date-posted | 10 (gdate) | "20260109" (YYYYMMDD format) |
| {frame_guid} | gncInvoice/invoice-guid | 5 (GUID) | {invoice_guid} |
| {txn_guid} | gncInvoice | 9 (frame) | {frame_guid} |

**Critical**: `trans-txn-type = "I"` identifies this as an invoice/bill posting transaction.

### 4.5 Create Splits

Two splits are created:

**AP Split** (Credit to Accounts Payable):
| Column | Value |
|--------|-------|
| guid | (new GUID) |
| tx_guid | {transaction_guid} |
| account_guid | {AP_account_guid} |
| memo | "" |
| action | "Bill" |
| reconcile_state | "n" |
| value_num | **-45654** (negative = credit) |
| value_denom | 100 |
| quantity_num | -45654 |
| quantity_denom | 100 |
| lot_guid | **{lot_guid}** |

**Expense Split** (Debit to Expense Account):
| Column | Value |
|--------|-------|
| guid | (new GUID) |
| tx_guid | {transaction_guid} |
| account_guid | {expense_account_guid} |
| memo | "" |
| action | "Bill" |
| reconcile_state | "n" |
| value_num | **45654** (positive = debit) |
| value_denom | 100 |
| quantity_num | 45654 |
| quantity_denom | 100 |
| lot_guid | **NULL** |

**Important**: Only the AP split is linked to the lot!

### 4.6 Update the Invoice Record

```sql
UPDATE invoices SET
    date_posted = '2026-01-09 10:59:00',
    post_txn = '36bf583e026745ffbd68485b1a891722',
    post_lot = 'efbfc70251a6439fba5425e2a7caa334',
    post_acc = '086ec14f1ec744a2a3614b699b3e8c1b'
WHERE guid = '63efd2b7b1694f7e8612cdffecb17500';
```

---

## Step 5: Pay the Bill

Payment creates a separate transaction that links to the bill's lot.

### 5.1 Create Payment Lot

A new lot is created for the payment:

```sql
INSERT INTO lots (guid, account_guid, is_closed)
VALUES ('b6072f1de7304a5b9c8d...', '086ec14f1ec744a2a3614b699b3e8c1b', -1);
```

### 5.2 Create Payment Lot Slots (CRITICAL!)

The payment lot needs **gncOwner** slots to link back to the vendor:

| obj_guid | name | slot_type | value |
|----------|------|-----------|-------|
| {lot_guid} | title | 4 (string) | "Bill B-001" |
| {frame1_guid} | gncInvoice/invoice-guid | 5 (GUID) | {invoice_guid} |
| {lot_guid} | gncInvoice | 9 (frame) | {frame1_guid} |
| {frame2_guid} | gncOwner/owner-type | 1 (int64) | **4** (vendor) |
| {frame2_guid} | gncOwner/owner-guid | 5 (GUID) | {vendor_guid} |
| {lot_guid} | gncOwner | 9 (frame) | {frame2_guid} |

**This is the key finding**: Payment lots need `gncOwner/owner-type=4` and `gncOwner/owner-guid` slots to properly link to the vendor!

### 5.3 Create Payment Transaction

```sql
INSERT INTO transactions (guid, currency_guid, num, post_date, enter_date, description)
VALUES ('16ed5803cb00...', 'c30af8dfe58c47099f57ad2eadf02e43', '',
        '2026-01-09 10:59:00', '2026-01-09 10:59:00', 'Acme Corp');
```

### 5.4 Create Payment Transaction Slot

| obj_guid | name | slot_type | value |
|----------|------|-----------|-------|
| {txn_guid} | trans-txn-type | 4 (string) | **"P"** (Payment) |

**Critical**: `trans-txn-type = "P"` identifies this as a payment transaction.

### 5.5 Create Payment Splits

**AP Split** (Debit to clear the payable):
| Column | Value |
|--------|-------|
| account_guid | {AP_account_guid} |
| action | "Payment" |
| value_num | **45654** (positive = debit) |
| lot_guid | **{bill_lot_guid}** (links to the BILL's lot!) |

**Checking Split** (Credit from bank account):
| Column | Value |
|--------|-------|
| account_guid | {checking_account_guid} |
| action | "Payment" |
| value_num | **-45654** (negative = credit) |
| lot_guid | NULL |

**Important**: The AP split in the payment links to the **original bill's lot** (not the payment lot). This is how GnuCash knows which bill is being paid.

---

## Sidebar: Creating a Vendor

When a vendor doesn't exist, create one before creating the bill.

### Vendor Table Structure

```sql
INSERT INTO vendors (
    guid,           -- Generate new UUID
    name,           -- Display name (required)
    id,             -- Vendor ID like "V-001" 
    notes,          -- Optional notes
    currency,       -- GUID of USD commodity
    active,         -- 1 = active
    tax_override,   -- 0
    addr_name,      -- Contact name (used on checks!)
    addr_addr1,     -- Street address line 1
    addr_addr2,     -- Street address line 2  
    addr_addr3,     -- City, State ZIP
    addr_addr4,     -- Country (optional)
    addr_phone,     -- Phone
    addr_fax,       -- Fax
    addr_email,     -- Email
    terms,          -- NULL or payment terms GUID
    tax_inc,        -- 'NO'
    tax_table       -- NULL
) VALUES (...);
```

### Finding the USD Currency GUID

```sql
SELECT guid FROM commodities WHERE mnemonic = 'USD';
```

### Vendor ID Counter

GnuCash tracks vendor numbering in slots:

```sql
-- Check current counter
SELECT int64_val FROM slots 
WHERE name = 'counters/gncVendor' AND slot_type = 1;

-- Update counter after creating vendor
UPDATE slots SET int64_val = int64_val + 1 
WHERE name = 'counters/gncVendor';
```

---

## Sidebar: Creating an Accounts Payable Account

An AP account is required for posting bills. It must have `account_type = 'PAYABLE'`.

### Finding Existing AP Account

```sql
SELECT guid, name FROM accounts 
WHERE account_type = 'PAYABLE' AND placeholder = 0;
```

### Creating AP Account if None Exists

```sql
-- First find the Liabilities root account
SELECT guid FROM accounts 
WHERE name = 'Liabilities root' OR (account_type = 'LIABILITY' AND placeholder = 1);

-- Create AP account under Liabilities
INSERT INTO accounts (
    guid,               -- Generate new UUID
    name,               -- 'Accounts Payable'
    account_type,       -- 'PAYABLE' (not 'LIABILITY'!)
    commodity_guid,     -- USD commodity GUID
    commodity_scu,      -- 100 (2 decimal places)
    non_std_scu,        -- 0
    parent_guid,        -- Liabilities root GUID
    code,               -- Optional account code
    description,        -- Optional description
    hidden,             -- 0
    placeholder         -- 0 (must accept transactions!)
) VALUES (...);
```

### Key Points for AP Account

1. **account_type must be 'PAYABLE'** - not 'LIABILITY'
2. **placeholder must be 0** - account must accept transactions
3. **Parent should be under Liabilities** - typically under "Liabilities root"
4. **commodity_scu = 100** for USD (2 decimal places)

---

## Sidebar: Locating or Creating an Expense Account

Bills need an expense account for the debit side of the posting transaction.

### Finding Existing Expense Accounts

```sql
-- Find all expense accounts that can accept transactions
SELECT guid, name, parent_guid FROM accounts 
WHERE account_type = 'EXPENSE' AND placeholder = 0
ORDER BY name;

-- Find by specific name
SELECT guid FROM accounts 
WHERE name = 'SAMUSE_Gameroom_Commissions_Paid' AND account_type = 'EXPENSE';
```

### Creating an Expense Account

```sql
-- First find the Expenses root
SELECT guid FROM accounts 
WHERE name = 'Expenses root' OR (account_type = 'EXPENSE' AND placeholder = 1);

-- Or find a specific parent expense category
SELECT guid FROM accounts 
WHERE name = 'Storz Amusements LLC' AND account_type = 'EXPENSE';

-- Create expense account
INSERT INTO accounts (
    guid,               -- Generate new UUID  
    name,               -- Account name
    account_type,       -- 'EXPENSE'
    commodity_guid,     -- USD commodity GUID
    commodity_scu,      -- 100
    non_std_scu,        -- 0
    parent_guid,        -- Parent account GUID (NOT a placeholder!)
    code,               -- Optional
    description,        -- Optional
    hidden,             -- 0
    placeholder         -- 0
) VALUES (...);
```

### Important: Avoid Placeholder Parents

While GnuCash allows accounts under placeholder parents, our tool should:
1. **Prefer non-placeholder parents** for new expense accounts
2. **Never create expense accounts directly under "Expenses root"** (it's a placeholder)
3. **Use an existing expense account** when possible to avoid proliferation

### Default Expense Account Strategy

For automated bill processing, it's recommended to:
1. Configure a **default expense account GUID** in settings
2. Allow per-vendor expense account overrides
3. Validate the account exists and is not a placeholder before use

---

## Sidebar: Locating a Checking Account

Payment transactions need a checking/bank account for the credit side. **We never create checking accounts** - they must pre-exist.

### Finding Checking Accounts

```sql
-- Find all bank accounts that can accept transactions
SELECT guid, name, description FROM accounts 
WHERE account_type = 'BANK' AND placeholder = 0
ORDER BY name;

-- Find by specific name pattern
SELECT guid, name FROM accounts 
WHERE account_type = 'BANK' AND placeholder = 0 
  AND name LIKE '%Checking%';
```

### Typical Checking Account Names

From observed database:
- `Schwab Checking for Conrad`
- `SAM Business Checking *1301`
- `SCS Billpay Checking *6241`
- `SPM main checking *0608`

### Configuration Requirement

The payment checking account GUID should be:
1. **Configured in application settings**
2. **Validated to exist** before any payment operations
3. **Validated to be type='BANK'** and **placeholder=0**

```sql
-- Validate checking account
SELECT guid, name, account_type, placeholder FROM accounts 
WHERE guid = '{configured_checking_guid}'
  AND account_type = 'BANK' 
  AND placeholder = 0;
```

---

## Slot Types Reference

GnuCash uses typed slots for metadata:

| slot_type | Name | Storage Column | Example |
|-----------|------|----------------|---------|
| 1 | int64 | int64_val | counters, flags |
| 4 | string | string_val | notes, trans-txn-type |
| 5 | GUID | guid_val | references to other objects |
| 6 | timespec | timespec_val | timestamps |
| 9 | KVP frame | guid_val | hierarchical grouping |
| 10 | gdate | gdate_val | dates as "YYYYMMDD" |

### KVP Frame Pattern

Type 9 slots create hierarchical metadata:
```
lot_guid → gncInvoice (type=9) → frame_guid
                                    ↓
frame_guid → gncInvoice/invoice-guid (type=5) → invoice_guid
```

The frame GUID is a new UUID that groups related slots together.

---

## Key Findings Summary

### Critical Discoveries

1. **Entries use `bill` column for vendor bills**, NOT `invoice` column
   - `invoice` column is for customer invoices (owner_type=2)
   - `bill` column is for vendor bills (owner_type=4)

2. **Transaction type slots distinguish bill vs payment**
   - `trans-txn-type = "I"` → Invoice/Bill posting
   - `trans-txn-type = "P"` → Payment

3. **Payment lots need gncOwner slots**
   - `gncOwner/owner-type = 4` (vendor)
   - `gncOwner/owner-guid = {vendor_guid}`
   - Without these, GnuCash can't link payment to vendor

4. **AP account type is PAYABLE, not LIABILITY**
   - Special account type for accounts payable
   - Must have `placeholder = 0`

5. **Lot linkage pattern**
   - Bill posting: AP split links to bill's lot
   - Payment: AP split links to **bill's lot** (not payment lot)
   - This is how GnuCash knows which bill is paid

6. **Amount signs**
   - Credits (AP on bill, Checking on payment) = negative
   - Debits (Expense on bill, AP on payment) = positive

### Database Modification Order

When creating a complete bill with posting:
1. Create/verify vendor exists
2. Create/verify AP account exists  
3. Create/verify expense account exists
4. Insert invoice record
5. Insert invoice slot (credit-note)
6. Insert entry record (uses `bill` column)
7. Insert lot record
8. Insert lot slots (title, gncInvoice frame)
9. Insert transaction record
10. Insert transaction slots (trans-txn-type, trans-read-only, date-posted, gncInvoice frame)
11. Insert AP split (negative value, linked to lot)
12. Insert expense split (positive value, no lot)
13. Update invoice with post_txn, post_lot, post_acc

---

## Appendix: SQL Templates

### Complete Bill Creation Template

```sql
-- Variables to set:
-- $vendor_guid, $invoice_guid, $entry_guid, $lot_guid, $txn_guid
-- $ap_split_guid, $expense_split_guid
-- $frame1_guid, $frame2_guid (for KVP frames)
-- $currency_guid, $ap_acct_guid, $expense_acct_guid
-- $vendor_name, $bill_id, $description, $amount_num, $post_date

-- 1. Invoice
INSERT INTO invoices (guid, id, date_opened, date_posted, notes, active, currency,
    owner_type, owner_guid, terms, billing_id, post_txn, post_lot, post_acc,
    billto_type, billto_guid, charge_amt_num, charge_amt_denom)
VALUES ($invoice_guid, $bill_id, $post_date, $post_date, '', 1, $currency_guid,
    4, $vendor_guid, NULL, '', $txn_guid, $lot_guid, $ap_acct_guid,
    0, NULL, 0, 1);

-- 2. Invoice slot
INSERT INTO slots (obj_guid, name, slot_type, int64_val)
VALUES ($invoice_guid, 'credit-note', 1, 0);

-- 3. Entry
INSERT INTO entries (guid, date, date_entered, description, action, notes,
    quantity_num, quantity_denom, b_acct, b_price_num, b_price_denom, bill,
    i_acct, i_price_num, i_price_denom, invoice,
    b_taxable, b_taxincluded, b_paytype, billable)
VALUES ($entry_guid, $post_date, $post_date, $description, '', '',
    $amount_num, 100, $expense_acct_guid, $amount_num, 100, $invoice_guid,
    NULL, 0, 1, NULL, 0, 0, 0, 0);

-- 4. Lot
INSERT INTO lots (guid, account_guid, is_closed)
VALUES ($lot_guid, $ap_acct_guid, -1);

-- 5. Lot slots
INSERT INTO slots (obj_guid, name, slot_type, string_val)
VALUES ($lot_guid, 'title', 4, 'Bill ' || $bill_id);

INSERT INTO slots (obj_guid, name, slot_type, guid_val)
VALUES ($frame1_guid, 'gncInvoice/invoice-guid', 5, $invoice_guid);

INSERT INTO slots (obj_guid, name, slot_type, guid_val)
VALUES ($lot_guid, 'gncInvoice', 9, $frame1_guid);

-- 6. Transaction
INSERT INTO transactions (guid, currency_guid, num, post_date, enter_date, description)
VALUES ($txn_guid, $currency_guid, '', $post_date, $post_date, $vendor_name);

-- 7. Transaction slots
INSERT INTO slots (obj_guid, name, slot_type, string_val)
VALUES ($txn_guid, 'trans-txn-type', 4, 'I');

INSERT INTO slots (obj_guid, name, slot_type, string_val)
VALUES ($txn_guid, 'trans-read-only', 4, 'Generated from an invoice. Try unposting the invoice.');

INSERT INTO slots (obj_guid, name, slot_type, gdate_val)
VALUES ($txn_guid, 'date-posted', 10, strftime('%Y%m%d', $post_date));

INSERT INTO slots (obj_guid, name, slot_type, guid_val)
VALUES ($frame2_guid, 'gncInvoice/invoice-guid', 5, $invoice_guid);

INSERT INTO slots (obj_guid, name, slot_type, guid_val)
VALUES ($txn_guid, 'gncInvoice', 9, $frame2_guid);

-- 8. Splits
INSERT INTO splits (guid, tx_guid, account_guid, memo, action, reconcile_state,
    reconcile_date, value_num, value_denom, quantity_num, quantity_denom, lot_guid)
VALUES ($ap_split_guid, $txn_guid, $ap_acct_guid, '', 'Bill', 'n',
    NULL, -$amount_num, 100, -$amount_num, 100, $lot_guid);

INSERT INTO splits (guid, tx_guid, account_guid, memo, action, reconcile_state,
    reconcile_date, value_num, value_denom, quantity_num, quantity_denom, lot_guid)
VALUES ($expense_split_guid, $txn_guid, $expense_acct_guid, '', 'Bill', 'n',
    NULL, $amount_num, 100, $amount_num, 100, NULL);
```

---

*Document generated from empirical observation of GnuCash 4.14 SQLite3 database behavior, January 2026*
