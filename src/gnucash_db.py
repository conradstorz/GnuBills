"""
GnuCash SQLite database interface.
Read and write vendors, bills, accounts, etc.
"""

import sqlite3
import uuid
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from contextlib import contextmanager

import config

logger = logging.getLogger(__name__)


def generate_guid() -> str:
    """Generate a GnuCash-compatible GUID (32 hex chars, no dashes)."""
    return uuid.uuid4().hex


@contextmanager
def get_connection(readonly: bool = True):
    """
    Context manager for database connections.
    
    Args:
        readonly: If True, open in read-only mode (default for safety)
    """
    db_path = Path(config.GNUCASH_DB_PATH)
    
    if not db_path.exists():
        raise FileNotFoundError(f"GnuCash database not found: {db_path}")
    
    # SQLite URI format for read-only
    if readonly:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
    
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# =============================================================================
# VENDOR OPERATIONS
# =============================================================================

def get_all_vendors() -> List[Dict]:
    """
    Retrieve all vendors from GnuCash.
    
    Returns list of dicts with: guid, id, name, addr_name, addr_addr1-4,
    addr_phone, addr_email, notes
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                guid, id, name, currency,
                addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
                addr_phone, addr_email, notes, active
            FROM vendors
            ORDER BY name
        """)
        
        vendors = []
        for row in cursor:
            vendors.append({
                'guid': row['guid'],
                'id': row['id'],
                'name': row['name'],
                'currency': row['currency'],
                'addr_name': row['addr_name'],
                'addr_addr1': row['addr_addr1'],
                'addr_addr2': row['addr_addr2'],
                'addr_addr3': row['addr_addr3'],
                'addr_addr4': row['addr_addr4'],
                'addr_phone': row['addr_phone'],
                'addr_email': row['addr_email'],
                'notes': row['notes'],
                'active': row['active']
            })
        
        return vendors


def find_vendor_by_name(name: str) -> Optional[Dict]:
    """Find a vendor by exact name match."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM vendors WHERE name = ?",
            (name,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def find_vendor_by_id(vendor_id: str) -> Optional[Dict]:
    """Find a vendor by ID (like V0001)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM vendors WHERE id = ?",
            (vendor_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_next_vendor_id() -> str:
    """
    Get the next available vendor ID.
    Queries MAX(id) and increments.
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT id FROM vendors ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        
        if row and row['id']:
            # Parse existing ID format (e.g., "000001" or "V0001")
            current_id = row['id']
            # Extract numeric portion
            import re
            match = re.search(r'(\d+)', current_id)
            if match:
                num = int(match.group(1))
                # Use same format as config
                return config.VENDOR_ID_FORMAT.format(num + 1)
        
        # First vendor
        return config.VENDOR_ID_FORMAT.format(1)


def create_vendor(
    name: str,
    addr_name: str = "",
    addr_addr1: str = "",
    addr_addr2: str = "",
    addr_addr3: str = "",
    addr_addr4: str = "",
    addr_phone: str = "",
    addr_email: str = "",
    notes: str = "",
    currency_guid: str = None
) -> str:
    """
    Create a new vendor in GnuCash.
    
    Returns the new vendor's GUID.
    """
    vendor_guid = generate_guid()
    vendor_id = get_next_vendor_id()
    
    if currency_guid is None:
        currency_guid = get_usd_guid()
    
    with get_connection(readonly=False) as conn:
        conn.execute("""
            INSERT INTO vendors (
                guid, id, name, currency,
                addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
                addr_phone, addr_email, notes, active,
                tax_override, tax_included
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 1)
        """, (
            vendor_guid, vendor_id, name, currency_guid,
            addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
            addr_phone, addr_email, notes
        ))
        conn.commit()
        
    logger.info(f"Created vendor: {name} (ID: {vendor_id}, GUID: {vendor_guid})")
    return vendor_guid


def update_vendor_address(
    vendor_guid: str,
    addr_name: str = None,
    addr_addr1: str = None,
    addr_addr2: str = None,
    addr_addr3: str = None,
    addr_addr4: str = None,
    addr_phone: str = None,
    addr_email: str = None
):
    """Update vendor address fields. Only updates non-None values."""
    updates = []
    params = []
    
    if addr_name is not None:
        updates.append("addr_name = ?")
        params.append(addr_name)
    if addr_addr1 is not None:
        updates.append("addr_addr1 = ?")
        params.append(addr_addr1)
    if addr_addr2 is not None:
        updates.append("addr_addr2 = ?")
        params.append(addr_addr2)
    if addr_addr3 is not None:
        updates.append("addr_addr3 = ?")
        params.append(addr_addr3)
    if addr_addr4 is not None:
        updates.append("addr_addr4 = ?")
        params.append(addr_addr4)
    if addr_phone is not None:
        updates.append("addr_phone = ?")
        params.append(addr_phone)
    if addr_email is not None:
        updates.append("addr_email = ?")
        params.append(addr_email)
    
    if not updates:
        return
    
    params.append(vendor_guid)
    
    with get_connection(readonly=False) as conn:
        conn.execute(
            f"UPDATE vendors SET {', '.join(updates)} WHERE guid = ?",
            params
        )
        conn.commit()


# =============================================================================
# ACCOUNT OPERATIONS
# =============================================================================

def get_account_by_name(name: str) -> Optional[Dict]:
    """
    Find an account by name (searches anywhere in hierarchy).
    Note: GnuCash stores accounts with parent references, not full paths.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT guid, name, account_type, parent_guid, commodity_guid FROM accounts WHERE name = ?",
            (name,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_account_by_guid(guid: str) -> Optional[Dict]:
    """Get an account by GUID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT guid, name, account_type, parent_guid, commodity_guid FROM accounts WHERE guid = ?",
            (guid,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def find_expense_accounts_like(pattern: str) -> List[Dict]:
    """
    Find expense accounts matching a pattern.
    Searches for accounts starting with the pattern.
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT guid, name, account_type, parent_guid
            FROM accounts 
            WHERE name LIKE ? AND account_type = 'EXPENSE'
            ORDER BY name
        """, (f"{pattern}%",))
        
        return [dict(row) for row in cursor]


def get_expenses_parent_guid() -> Optional[str]:
    """Get the GUID of the Expenses parent account."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT guid FROM accounts 
            WHERE name = 'Expenses' AND account_type = 'EXPENSE'
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row['guid'] if row else None


def get_ap_account_guid() -> Optional[str]:
    """Get the GUID of the Accounts Payable account."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT guid FROM accounts 
            WHERE account_type = 'PAYABLE'
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row['guid'] if row else None


def create_expense_account(name: str, parent_guid: str = None) -> str:
    """
    Create a new expense account.
    
    Returns the new account's GUID.
    """
    if parent_guid is None:
        parent_guid = get_expenses_parent_guid()
        if not parent_guid:
            raise ValueError("Could not find Expenses parent account")
    
    account_guid = generate_guid()
    usd_guid = get_usd_guid()
    
    with get_connection(readonly=False) as conn:
        conn.execute("""
            INSERT INTO accounts (
                guid, name, account_type, commodity_guid, commodity_scu, 
                non_std_scu, parent_guid, hidden, placeholder
            ) VALUES (?, ?, 'EXPENSE', ?, 100, 0, ?, 0, 0)
        """, (account_guid, name, usd_guid, parent_guid))
        conn.commit()
    
    logger.info(f"Created expense account: {name} (GUID: {account_guid})")
    return account_guid


def get_usd_guid() -> str:
    """Get the GUID for USD commodity."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT guid FROM commodities 
            WHERE mnemonic = 'USD' AND namespace = 'CURRENCY'
            LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            raise ValueError("USD currency not found in database")
        return row['guid']


# =============================================================================
# BILL/INVOICE OPERATIONS
# =============================================================================

def get_next_bill_id() -> str:
    """Get the next available bill ID."""
    with get_connection() as conn:
        # Bills are stored in the invoices table
        cursor = conn.execute("""
            SELECT id FROM invoices 
            WHERE id LIKE 'B-%' OR id LIKE 'B%'
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        
        if row and row['id']:
            import re
            match = re.search(r'(\d+)', row['id'])
            if match:
                num = int(match.group(1))
                return config.BILL_ID_FORMAT.format(num + 1)
        
        return config.BILL_ID_FORMAT.format(1)


def create_posted_bill(
    vendor_guid: str,
    expense_account_guid: str,
    amount: float,
    memo: str = "",
    bill_date: date = None,
    due_date: date = None
) -> str:
    """
    Create a posted bill (vendor invoice) in GnuCash.
    
    This creates:
    1. An invoice record
    2. A billterm lot for tracking
    3. Transaction entries (debit expense, credit AP)
    
    Returns the bill GUID.
    """
    if bill_date is None:
        bill_date = date.today()
    if due_date is None:
        due_date = bill_date
    
    bill_guid = generate_guid()
    bill_id = get_next_bill_id()
    lot_guid = generate_guid()
    txn_guid = generate_guid()
    split1_guid = generate_guid()  # Expense debit
    split2_guid = generate_guid()  # AP credit
    entry_guid = generate_guid()
    
    usd_guid = get_usd_guid()
    ap_guid = get_ap_account_guid()
    
    if not ap_guid:
        raise ValueError("Accounts Payable account not found")
    
    # Convert amount to GnuCash format (integer with denominator)
    # GnuCash stores values as value_num/value_denom
    amount_num = int(amount * 100)
    amount_denom = 100
    
    # Date formatting for GnuCash
    date_str = bill_date.strftime("%Y%m%d")
    date_posted = f"{date_str}000000"
    
    with get_connection(readonly=False) as conn:
        # Create the lot (tracks amounts owed)
        conn.execute("""
            INSERT INTO lots (guid, account_guid, is_closed)
            VALUES (?, ?, 0)
        """, (lot_guid, ap_guid))
        
        # Create the invoice/bill record
        conn.execute("""
            INSERT INTO invoices (
                guid, id, date_opened, date_posted, notes, active,
                currency, owner_type, owner_guid, 
                post_lot, post_txn, post_acc,
                billto_type, billto_guid
            ) VALUES (?, ?, ?, ?, ?, 1, ?, 4, ?, ?, ?, ?, 0, ?)
        """, (
            bill_guid, bill_id, date_posted, date_posted, memo,
            usd_guid, vendor_guid,
            lot_guid, txn_guid, ap_guid,
            generate_guid()  # Empty billto
        ))
        
        # Create the transaction
        conn.execute("""
            INSERT INTO transactions (
                guid, currency_guid, num, post_date, enter_date, description
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            txn_guid, usd_guid, bill_id, date_posted, date_posted, memo
        ))
        
        # Create expense split (debit - positive)
        conn.execute("""
            INSERT INTO splits (
                guid, tx_guid, account_guid, memo, action,
                reconcile_state, reconcile_date,
                value_num, value_denom, quantity_num, quantity_denom,
                lot_guid
            ) VALUES (?, ?, ?, ?, 'Expense', 'n', '', ?, ?, ?, ?, NULL)
        """, (
            split1_guid, txn_guid, expense_account_guid, memo,
            amount_num, amount_denom, amount_num, amount_denom
        ))
        
        # Create AP split (credit - negative)
        conn.execute("""
            INSERT INTO splits (
                guid, tx_guid, account_guid, memo, action,
                reconcile_state, reconcile_date,
                value_num, value_denom, quantity_num, quantity_denom,
                lot_guid
            ) VALUES (?, ?, ?, ?, 'Bill', 'n', '', ?, ?, ?, ?, ?)
        """, (
            split2_guid, txn_guid, ap_guid, memo,
            -amount_num, amount_denom, -amount_num, amount_denom,
            lot_guid
        ))
        
        # Create the invoice entry
        conn.execute("""
            INSERT INTO entries (
                guid, date, date_entered, description, action,
                quantity_num, quantity_denom,
                i_acct, i_price_num, i_price_denom,
                i_disc_num, i_disc_denom, i_disc_type, i_disc_how,
                i_taxable, i_taxincluded, i_taxtable,
                b_acct, b_price_num, b_price_denom,
                b_taxable, b_taxincluded, b_taxtable,
                b_paytype, billable, billto_type, billto_guid,
                order_guid, invoice
            ) VALUES (
                ?, ?, ?, ?, '',
                1, 1,
                ?, ?, ?, 0, 1, '', '',
                0, 0, NULL,
                ?, ?, ?,
                0, 0, NULL,
                0, 0, 0, NULL,
                NULL, ?
            )
        """, (
            entry_guid, date_posted, date_posted, memo,
            expense_account_guid, amount_num, amount_denom,
            expense_account_guid, amount_num, amount_denom,
            bill_guid
        ))
        
        conn.commit()
    
    logger.info(f"Created posted bill: {bill_id} for ${amount:.2f} (GUID: {bill_guid})")
    return bill_guid


def get_unpaid_bills(vendor_guid: str = None) -> List[Dict]:
    """
    Get all unpaid bills, optionally filtered by vendor.
    """
    with get_connection() as conn:
        query = """
            SELECT 
                i.guid, i.id, i.date_opened, i.date_posted, i.notes,
                i.owner_guid as vendor_guid, v.name as vendor_name,
                l.is_closed as lot_closed
            FROM invoices i
            JOIN vendors v ON i.owner_guid = v.guid
            LEFT JOIN lots l ON i.post_lot = l.guid
            WHERE i.owner_type = 4  -- Vendor type
            AND (l.is_closed = 0 OR l.is_closed IS NULL)
        """
        
        params = []
        if vendor_guid:
            query += " AND i.owner_guid = ?"
            params.append(vendor_guid)
        
        query += " ORDER BY i.date_posted"
        
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor]


# =============================================================================
# VERIFICATION
# =============================================================================

def verify_database_structure() -> Dict[str, bool]:
    """
    Verify that expected tables exist in the database.
    Returns dict of {table_name: exists}
    """
    required_tables = [
        'vendors', 'accounts', 'invoices', 'entries', 
        'transactions', 'splits', 'lots', 'commodities'
    ]
    
    results = {}
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row['name'] for row in cursor}
        
        for table in required_tables:
            results[table] = table in existing_tables
    
    return results


def test_connection() -> bool:
    """Test database connection and basic structure."""
    try:
        results = verify_database_structure()
        all_present = all(results.values())
        
        if not all_present:
            missing = [t for t, exists in results.items() if not exists]
            logger.error(f"Missing tables: {missing}")
        
        return all_present
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
