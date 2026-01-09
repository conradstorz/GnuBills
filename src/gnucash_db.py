"""
GnuCash SQLite database interface.
Read and write vendors, bills, accounts, etc.

Uses schema_discovery module to handle column name variations
between different GnuCash versions.

POST-WRITE VERIFICATION:
Every INSERT or UPDATE operation MUST be followed by verification.
User data is SACRED - we verify writes succeeded before returning.
"""

import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
from contextlib import contextmanager
from loguru import logger

import config


def generate_guid() -> str:
    """Generate a GnuCash-compatible GUID (32 hex chars, no dashes)."""
    return uuid.uuid4().hex


def _get_schema():
    """
    Get schema discovery instance (lazy import to avoid circular deps).
    """
    from schema_discovery import get_schema
    return get_schema()


def _get_column(table: str, expected_name: str) -> str:
    """
    Get actual column name from schema mapping.
    
    Falls back to expected name if schema not available.
    Logs a warning if mapping differs.
    """
    try:
        schema = _get_schema()
        actual = schema.get_column(table, expected_name)
        if actual and actual != expected_name:
            logger.debug(f"Column mapped: {table}.{expected_name} -> {actual}")
        return actual or expected_name
    except Exception as e:
        logger.warning(f"Schema lookup failed for {table}.{expected_name}: {e}")
        return expected_name


# =============================================================================
# POST-WRITE VERIFICATION - Verify all writes succeeded
# =============================================================================

class WriteVerificationError(Exception):
    """Raised when a database write cannot be verified."""
    pass


def verify_record_exists(table: str, guid: str, description: str = "") -> bool:
    """
    Verify a record with the given GUID exists in the table.
    
    Args:
        table: Table name to check
        guid: GUID to look for
        description: Human-readable description for logging
        
    Returns:
        True if record exists, raises WriteVerificationError if not
    """
    with get_connection() as conn:
        cursor = conn.execute(f"SELECT guid FROM {table} WHERE guid = ?", (guid,))
        row = cursor.fetchone()
        
        if row:
            logger.debug(f"POST-WRITE VERIFIED: {description or table} with GUID {guid[:12]}... exists")
            return True
        else:
            error_msg = f"POST-WRITE VERIFICATION FAILED: {description or table} with GUID {guid} NOT FOUND in {table}"
            logger.error(error_msg)
            
            # Record failure in schema verification
            try:
                schema = _get_schema()
                if hasattr(schema, 'verification') and schema.verification.current_run:
                    schema.verification.check(
                        "POST_WRITE_VERIFY", table,
                        f"Record exists after INSERT: {description}",
                        passed=False,
                        details=f"GUID {guid} not found in {table} after write"
                    )
            except Exception:
                pass  # Don't fail on logging failure
            
            raise WriteVerificationError(error_msg)


def verify_vendor_created(guid: str, expected_name: str) -> Dict:
    """
    Verify a vendor was created successfully.
    
    Returns the vendor record if found, raises WriteVerificationError if not.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT guid, id, name FROM vendors WHERE guid = ?",
            (guid,)
        )
        row = cursor.fetchone()
        
        if row:
            actual_name = row['name']
            if actual_name == expected_name:
                logger.info(f"POST-WRITE VERIFIED: Vendor '{expected_name}' created (ID: {row['id']})")
                return dict(row)
            else:
                logger.warning(f"POST-WRITE WARNING: Vendor name mismatch. Expected '{expected_name}', got '{actual_name}'")
                return dict(row)
        else:
            error_msg = f"POST-WRITE VERIFICATION FAILED: Vendor '{expected_name}' with GUID {guid} NOT FOUND"
            logger.error(error_msg)
            raise WriteVerificationError(error_msg)


def verify_account_created(guid: str, expected_name: str, expected_type: str) -> Dict:
    """
    Verify an account was created successfully.
    
    Returns the account record if found, raises WriteVerificationError if not.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT guid, name, account_type FROM accounts WHERE guid = ?",
            (guid,)
        )
        row = cursor.fetchone()
        
        if row:
            actual_name = row['name']
            actual_type = row['account_type']
            
            issues = []
            if actual_name != expected_name:
                issues.append(f"name mismatch (expected '{expected_name}', got '{actual_name}')")
            if actual_type != expected_type:
                issues.append(f"type mismatch (expected '{expected_type}', got '{actual_type}')")
            
            if issues:
                logger.warning(f"POST-WRITE WARNING: Account created with issues: {', '.join(issues)}")
            else:
                logger.info(f"POST-WRITE VERIFIED: Account '{expected_name}' ({expected_type}) created")
            
            return dict(row)
        else:
            error_msg = f"POST-WRITE VERIFICATION FAILED: Account '{expected_name}' with GUID {guid} NOT FOUND"
            logger.error(error_msg)
            raise WriteVerificationError(error_msg)


def verify_bill_created(guid: str, expected_amount: float, vendor_guid: str) -> Dict:
    """
    Verify a bill/invoice was created successfully.
    
    Checks:
    1. Invoice record exists
    2. Linked to correct vendor
    3. Transaction and splits exist
    
    Returns bill info if verified, raises WriteVerificationError if not.
    """
    with get_connection() as conn:
        # Check invoice exists and links to vendor
        cursor = conn.execute("""
            SELECT i.guid, i.id, i.owner_guid, i.post_txn, i.post_lot,
                   v.name as vendor_name
            FROM invoices i
            LEFT JOIN vendors v ON i.owner_guid = v.guid
            WHERE i.guid = ?
        """, (guid,))
        row = cursor.fetchone()
        
        if not row:
            error_msg = f"POST-WRITE VERIFICATION FAILED: Invoice with GUID {guid} NOT FOUND"
            logger.error(error_msg)
            raise WriteVerificationError(error_msg)
        
        # Verify vendor link
        if row['owner_guid'] != vendor_guid:
            error_msg = f"POST-WRITE VERIFICATION FAILED: Invoice vendor mismatch. Expected {vendor_guid[:12]}..., got {row['owner_guid'][:12] if row['owner_guid'] else 'None'}..."
            logger.error(error_msg)
            raise WriteVerificationError(error_msg)
        
        # Verify transaction exists
        txn_guid = row['post_txn']
        cursor = conn.execute("SELECT guid FROM transactions WHERE guid = ?", (txn_guid,))
        txn_row = cursor.fetchone()
        if not txn_row:
            error_msg = f"POST-WRITE VERIFICATION FAILED: Transaction {txn_guid} for invoice NOT FOUND"
            logger.error(error_msg)
            raise WriteVerificationError(error_msg)
        
        # Verify splits exist (should be at least 2 - expense and AP)
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM splits WHERE tx_guid = ?", (txn_guid,))
        split_count = cursor.fetchone()['cnt']
        if split_count < 2:
            error_msg = f"POST-WRITE VERIFICATION FAILED: Expected 2+ splits, found {split_count}"
            logger.error(error_msg)
            raise WriteVerificationError(error_msg)
        
        logger.info(f"POST-WRITE VERIFIED: Bill {row['id']} for vendor '{row['vendor_name']}' created successfully")
        return {
            'guid': row['guid'],
            'id': row['id'],
            'vendor_guid': row['owner_guid'],
            'vendor_name': row['vendor_name'],
            'transaction_guid': txn_guid,
            'split_count': split_count
        }


def is_gnucash_locked() -> tuple[bool, str | None, int | None]:
    """
    Check if GnuCash has the database locked.
    
    GnuCash uses a 'gnclock' table inside the SQLite database with hostname
    and PID when the database is open. An empty table means unlocked.
    
    Returns:
        Tuple of (is_locked, hostname, pid)
        - is_locked: True if database is locked
        - hostname: The machine holding the lock (or None)
        - pid: The process ID holding the lock (or None)
    """
    db_path = Path(config.GNUCASH_DB_PATH)
    
    if not db_path.exists():
        return (False, None, None)
    
    try:
        # Open in read-only mode to check lock
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        cursor = conn.cursor()
        
        # Check gnclock table for any records
        cursor.execute("SELECT Hostname, PID FROM gnclock")
        row = cursor.fetchone()
        conn.close()
        
        if row:
            hostname, pid = row
            logger.warning(f"Database LOCKED by: {hostname} (PID {pid})")
            return (True, hostname, pid)
        
        return (False, None, None)
        
    except sqlite3.OperationalError as e:
        # If we can't read the table, assume it might be locked
        logger.error(f"Error checking gnclock table: {e}")
        return (True, "unknown", 0)


def get_lock_info() -> dict | None:
    """
    Get detailed lock information for display purposes.
    
    Returns:
        Dict with 'hostname' and 'pid' if locked, None if not locked.
    """
    is_locked, hostname, pid = is_gnucash_locked()
    if is_locked:
        return {'hostname': hostname, 'pid': pid}
    return None


def is_locked_by_others() -> tuple[bool, str | None, int | None]:
    """
    Check if database is locked by someone OTHER than our own process.
    
    This is used for operations within our GUI that need to verify
    no external process (GnuCash, another instance) has the lock.
    Our own lock is fine - we already have access.
    
    Returns:
        Tuple of (is_locked_by_others, hostname, pid)
        - is_locked_by_others: True if locked by external process
        - hostname: Lock holder's hostname (or None)
        - pid: Lock holder's PID (or None)
    """
    import os
    
    is_locked, hostname, pid = is_gnucash_locked()
    
    if not is_locked:
        return (False, None, None)
    
    # Check if it's our own lock
    my_hostname = _get_lock_hostname()
    my_pid = os.getpid()
    
    if hostname == my_hostname and pid == my_pid:
        # It's our own lock - not locked by others
        logger.debug(f"Database locked by our own process (PID {my_pid})")
        return (False, None, None)
    
    # Locked by someone else
    return (True, hostname, pid)


def _is_process_running(pid: int) -> bool:
    """
    Check if a process with the given PID is currently running.
    
    Args:
        pid: Process ID to check
        
    Returns:
        True if process is running, False otherwise
    """
    import os
    
    if pid <= 0:
        return False
    
    try:
        # On Windows and Unix, sending signal 0 checks if process exists
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        # If we can't check, assume it might be running
        return True


def _get_lock_hostname() -> str:
    """Get the hostname to use for our lock entries.
    
    Uses 'BillProcessor@hostname' format to distinguish from GnuCash locks.
    """
    import socket
    return f"BillProcessor@{socket.gethostname()}"


def clean_stale_lock() -> bool:
    """
    Clean up stale locks from crashed BillProcessor processes on this machine.
    
    A lock is considered stale if:
    - The hostname matches our BillProcessor hostname format
    - The PID is no longer running
    
    For locks from GnuCash or other machines, we leave them alone.
    
    Returns:
        True if a stale lock was cleaned, False otherwise
    """
    is_locked, hostname, pid = is_gnucash_locked()
    
    if not is_locked:
        return False  # No lock to clean
    
    my_hostname = _get_lock_hostname()
    
    # Only clean locks from our own tool on this machine
    if hostname != my_hostname:
        if hostname and hostname.startswith('BillProcessor@'):
            logger.info(f"Lock held by BillProcessor on different machine ({hostname}), cannot verify if stale")
        else:
            logger.info(f"Lock held by GnuCash or other application ({hostname}), not cleaning")
        return False
    
    # Check if the process is still running
    if _is_process_running(pid):
        logger.debug(f"Lock holder PID {pid} is still running")
        return False
    
    # Process is not running - this is a stale lock, clean it up
    logger.warning(f"Cleaning stale lock from crashed process (PID {pid})")
    
    db_path = Path(config.GNUCASH_DB_PATH)
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gnclock WHERE Hostname = ? AND PID = ?",
                      (hostname, pid))
        conn.commit()
        conn.close()
        logger.info(f"Stale lock cleaned: {hostname} (PID {pid})")
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to clean stale lock: {e}")
        return False


def acquire_lock() -> bool:
    """
    Acquire a lock on the GnuCash database by inserting into gnclock table.
    
    This prevents GnuCash and other instances of this tool from accessing
    the database while we have it locked.
    
    First attempts to clean any stale locks from crashed processes on this machine.
    
    Returns:
        True if lock acquired successfully, False if already locked.
    """
    import os
    
    # First try to clean any stale locks from this machine
    clean_stale_lock()
    
    # Now check if still locked
    is_locked, hostname, pid = is_gnucash_locked()
    if is_locked:
        logger.error(f"Cannot acquire lock - already locked by {hostname} (PID {pid})")
        return False
    
    db_path = Path(config.GNUCASH_DB_PATH)
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Insert our lock record with BillProcessor@ prefix
        my_hostname = _get_lock_hostname()
        my_pid = os.getpid()
        
        cursor.execute("INSERT INTO gnclock (Hostname, PID) VALUES (?, ?)", 
                      (my_hostname, my_pid))
        conn.commit()
        conn.close()
        
        logger.info(f"Database lock ACQUIRED: {my_hostname} (PID {my_pid})")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Failed to acquire database lock: {e}")
        return False


def release_lock() -> bool:
    """
    Release our lock on the GnuCash database by clearing the gnclock table.
    
    Returns:
        True if lock released successfully, False on error.
    """
    import os
    
    db_path = Path(config.GNUCASH_DB_PATH)
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Only delete our own lock (matching our BillProcessor hostname and PID)
        my_hostname = _get_lock_hostname()
        my_pid = os.getpid()
        
        cursor.execute("DELETE FROM gnclock WHERE Hostname = ? AND PID = ?",
                      (my_hostname, my_pid))
        rows_deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows_deleted > 0:
            logger.info(f"Database lock RELEASED: {my_hostname} (PID {my_pid})")
            return True
        else:
            logger.warning("No lock to release (may have been released already)")
            return True
            
    except sqlite3.Error as e:
        logger.error(f"Failed to release database lock: {e}")
        return False


@contextmanager
def database_lock():
    """
    Context manager for safely acquiring and releasing the database lock.
    
    Usage:
        with database_lock():
            # Do database operations
            pass
    
    Raises:
        RuntimeError: If lock cannot be acquired (database already locked)
    """
    if not acquire_lock():
        raise RuntimeError("Cannot acquire database lock - database is in use")
    
    try:
        yield
    finally:
        release_lock()


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


def find_vendor_by_guid(guid: str) -> Optional[Dict]:
    """
    Find a vendor by GUID.
    
    Use this to verify a GUID from JSON actually exists in GnuCash.
    """
    if not guid:
        return None
    
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM vendors WHERE guid = ?",
            (guid,)
        )
        row = cursor.fetchone()
        if row:
            logger.debug(f"Found vendor by GUID: {row['name']}")
            return dict(row)
        else:
            logger.warning(f"Vendor GUID not found in GnuCash: {guid[:12]}...")
            return None


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
                return config.VENDOR_ID_FORMAT.format(prefix=config.VENDOR_ID_PREFIX, num=num + 1)
        
        # First vendor
        return config.VENDOR_ID_FORMAT.format(prefix=config.VENDOR_ID_PREFIX, num=1)


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
    currency_guid: str = None,
    verify: bool = True
) -> str:
    """
    Create a new vendor in GnuCash.
    
    Args:
        name: Vendor name (required)
        addr_*: Address fields (optional)
        notes: Notes (optional)
        currency_guid: Currency GUID (defaults to USD)
        verify: If True, verify the vendor was created (default True)
    
    Returns the new vendor's GUID.
    Raises WriteVerificationError if verification fails.
    """
    vendor_guid = generate_guid()
    vendor_id = get_next_vendor_id()
    
    if currency_guid is None:
        currency_guid = get_usd_guid()
    
    with get_connection(readonly=False) as conn:
        # First, check what columns exist in the vendors table
        cursor = conn.execute("PRAGMA table_info(vendors)")
        columns = {row['name'] for row in cursor.fetchall()}
        
        # Build INSERT based on available columns
        base_columns = [
            'guid', 'id', 'name', 'currency',
            'addr_name', 'addr_addr1', 'addr_addr2', 'addr_addr3', 'addr_addr4',
            'addr_phone', 'addr_email', 'notes', 'active'
        ]
        base_values = [
            vendor_guid, vendor_id, name, currency_guid,
            addr_name, addr_addr1, addr_addr2, addr_addr3, addr_addr4,
            addr_phone, addr_email, notes, 1  # active=1
        ]
        
        # Add optional columns if they exist
        if 'tax_override' in columns:
            base_columns.append('tax_override')
            base_values.append(0)
        if 'tax_included' in columns:
            base_columns.append('tax_included')
            base_values.append(1)
        
        placeholders = ', '.join(['?'] * len(base_columns))
        column_names = ', '.join(base_columns)
        
        conn.execute(f"""
            INSERT INTO vendors ({column_names})
            VALUES ({placeholders})
        """, base_values)
        conn.commit()
    
    logger.info(f"Created vendor: {name} (ID: {vendor_id}, GUID: {vendor_guid})")
    
    # POST-WRITE VERIFICATION - User data is SACRED
    if verify:
        verify_vendor_created(vendor_guid, name)
    
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
        # Try exact match first
        cursor = conn.execute("""
            SELECT guid FROM accounts 
            WHERE name = ? AND account_type = 'EXPENSE'
            LIMIT 1
        """, (config.DEFAULT_EXPENSE_PARENT,))
        row = cursor.fetchone()
        if row:
            return row['guid']
        
        # Try case-insensitive match
        cursor = conn.execute("""
            SELECT guid FROM accounts 
            WHERE LOWER(name) = LOWER(?) AND account_type = 'EXPENSE'
            LIMIT 1
        """, (config.DEFAULT_EXPENSE_PARENT,))
        row = cursor.fetchone()
        if row:
            return row['guid']
        
        # Try to find any top-level EXPENSE account (parent_guid is root)
        cursor = conn.execute("""
            SELECT a.guid, a.name FROM accounts a
            WHERE a.account_type = 'EXPENSE' 
            AND a.parent_guid IN (SELECT guid FROM accounts WHERE account_type = 'ROOT')
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            logger.warning(f"Using expense parent: {row['name']} (expected: {config.DEFAULT_EXPENSE_PARENT})")
            return row['guid']
        
        # Last resort: any EXPENSE account that could be a parent
        cursor = conn.execute("""
            SELECT guid, name FROM accounts 
            WHERE account_type = 'EXPENSE'
            ORDER BY name
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            logger.warning(f"Using expense parent: {row['name']} (fallback)")
            return row['guid']
        
        return None


def get_ap_account_guid() -> Optional[str]:
    """
    Get the GUID of the Accounts Payable account.
    
    Searches by:
    1. Account type = 'PAYABLE' (correct way)
    2. Account name containing 'payable' (fallback)
    """
    with get_connection() as conn:
        # First try: find by account_type = PAYABLE (the correct way)
        cursor = conn.execute("""
            SELECT guid, name FROM accounts 
            WHERE account_type = 'PAYABLE'
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            logger.debug(f"Found A/P account by type: {row['name']}")
            return row['guid']
        
        # Fallback: search by name containing 'payable'
        cursor = conn.execute("""
            SELECT guid, name, account_type FROM accounts 
            WHERE LOWER(name) LIKE '%payable%'
            ORDER BY 
                CASE WHEN account_type = 'LIABILITY' THEN 1
                     WHEN account_type = 'ASSET' THEN 2
                     ELSE 3 END
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            logger.warning(f"No PAYABLE type account found. Using '{row['name']}' ({row['account_type']}) as fallback")
            return row['guid']
        
        return None


def validate_gnucash_setup() -> Dict[str, any]:
    """
    Validate that GnuCash has the required setup for bill processing.
    
    Returns a dict with:
        - valid: bool - True if all requirements met
        - errors: list - Critical issues that prevent processing
        - warnings: list - Non-critical issues
        - info: dict - Information about found accounts
    """
    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'info': {}
    }
    
    with get_connection() as conn:
        # Check 1: USD currency exists
        cursor = conn.execute("""
            SELECT guid FROM commodities 
            WHERE mnemonic = 'USD' AND namespace = 'CURRENCY'
        """)
        row = cursor.fetchone()
        if row:
            result['info']['usd_guid'] = row['guid']
        else:
            result['errors'].append("USD currency not found in GnuCash")
            result['valid'] = False
        
        # Check 2: Accounts Payable account (CRITICAL)
        cursor = conn.execute("""
            SELECT guid, name FROM accounts WHERE account_type = 'PAYABLE'
        """)
        row = cursor.fetchone()
        if row:
            result['info']['ap_account'] = row['name']
            result['info']['ap_guid'] = row['guid']
        else:
            # Check if there's one with a similar name but wrong type
            cursor = conn.execute("""
                SELECT name, account_type FROM accounts 
                WHERE LOWER(name) LIKE '%payable%'
            """)
            similar = cursor.fetchone()
            if similar:
                result['errors'].append(
                    f"No account with type 'PAYABLE' found. "
                    f"Found '{similar['name']}' but it has type '{similar['account_type']}'. "
                    f"In GnuCash, edit this account and change its type to 'A/Payable'."
                )
            else:
                result['errors'].append(
                    "No Accounts Payable account found. "
                    "In GnuCash: Actions → New Account → "
                    "Name: 'Accounts Payable', Type: 'A/Payable', Parent: 'Liabilities'"
                )
            result['valid'] = False
        
        # Check 3: Expense parent account
        cursor = conn.execute("""
            SELECT guid, name FROM accounts 
            WHERE account_type = 'EXPENSE' 
            AND parent_guid IN (SELECT guid FROM accounts WHERE account_type = 'ROOT')
        """)
        row = cursor.fetchone()
        if row:
            result['info']['expense_parent'] = row['name']
            result['info']['expense_parent_guid'] = row['guid']
        else:
            result['warnings'].append(
                f"No top-level Expense account found. "
                f"Expected '{config.DEFAULT_EXPENSE_PARENT}'. "
                f"New expense accounts may not be created correctly."
            )
        
        # Check 4: Count existing expense accounts (informational)
        cursor = conn.execute("""
            SELECT COUNT(*) as cnt FROM accounts WHERE account_type = 'EXPENSE'
        """)
        result['info']['expense_account_count'] = cursor.fetchone()['cnt']
        
        # Check 5: Count vendors
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM vendors")
        result['info']['vendor_count'] = cursor.fetchone()['cnt']
        
        # Check 6: List available account types (informational)
        cursor = conn.execute("""
            SELECT DISTINCT account_type, COUNT(*) as cnt 
            FROM accounts 
            GROUP BY account_type 
            ORDER BY cnt DESC
        """)
        result['info']['account_types'] = {row['account_type']: row['cnt'] for row in cursor}
    
    return result


def create_expense_account(name: str, parent_guid: str = None, verify: bool = True) -> str:
    """
    Create a new expense account.
    
    Args:
        name: Account name
        parent_guid: Parent account GUID (defaults to Expenses parent)
        verify: If True, verify the account was created (default True)
    
    Returns the new account's GUID.
    Raises WriteVerificationError if verification fails.
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
    
    # POST-WRITE VERIFICATION
    if verify:
        verify_account_created(account_guid, name, 'EXPENSE')
    
    return account_guid


def get_liabilities_parent_guid() -> Optional[str]:
    """Get the GUID of the top-level Liabilities account."""
    with get_connection() as conn:
        # Find top-level LIABILITY account (parent is ROOT)
        cursor = conn.execute("""
            SELECT a.guid, a.name FROM accounts a
            WHERE a.account_type = 'LIABILITY' 
            AND a.parent_guid IN (SELECT guid FROM accounts WHERE account_type = 'ROOT')
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return row['guid']
        
        # Fallback: any LIABILITY account with 'root' or 'liabilities' in name
        cursor = conn.execute("""
            SELECT guid, name FROM accounts 
            WHERE account_type = 'LIABILITY'
            AND (LOWER(name) LIKE '%root%' OR LOWER(name) = 'liabilities')
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return row['guid']
        
        return None


def create_ap_account(name: str = "Accounts Payable", verify: bool = True) -> str:
    """
    Create an Accounts Payable account under Liabilities.
    
    Args:
        name: Account name (default "Accounts Payable")
        verify: If True, verify the account was created (default True)
    
    Returns the new account's GUID.
    Raises WriteVerificationError if verification fails.
    """
    parent_guid = get_liabilities_parent_guid()
    if not parent_guid:
        raise ValueError("Could not find Liabilities parent account")
    
    account_guid = generate_guid()
    usd_guid = get_usd_guid()
    
    with get_connection(readonly=False) as conn:
        conn.execute("""
            INSERT INTO accounts (
                guid, name, account_type, commodity_guid, commodity_scu, 
                non_std_scu, parent_guid, hidden, placeholder
            ) VALUES (?, ?, 'PAYABLE', ?, 100, 0, ?, 0, 0)
        """, (account_guid, name, usd_guid, parent_guid))
        conn.commit()
    
    logger.info(f"Created A/P account: {name} (GUID: {account_guid})")
    
    # POST-WRITE VERIFICATION
    if verify:
        verify_account_created(account_guid, name, 'PAYABLE')
    
    return account_guid


def ensure_ap_account_exists() -> str:
    """
    Ensure an Accounts Payable account exists, creating one if needed.
    
    Returns the A/P account GUID.
    """
    ap_guid = get_ap_account_guid()
    if ap_guid:
        return ap_guid
    
    logger.info("No A/P account found - creating one")
    return create_ap_account()


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
                return config.BILL_ID_FORMAT.format(prefix=config.BILL_ID_PREFIX, num=num + 1)
        
        return config.BILL_ID_FORMAT.format(prefix=config.BILL_ID_PREFIX, num=1)


def create_posted_bill(
    vendor_guid: str,
    expense_account_guid: str,
    amount: float,
    memo: str = "",
    bill_date: date = None,
    due_date: date = None,
    verify: bool = True
) -> str:
    """
    Create a posted bill (vendor invoice) in GnuCash.
    
    This creates:
    1. An invoice record
    2. A billterm lot for tracking
    3. Transaction entries (debit expense, credit AP)
    
    Args:
        vendor_guid: GUID of the vendor
        expense_account_guid: GUID of expense account to debit
        amount: Bill amount
        memo: Bill description/memo
        bill_date: Date of bill (defaults to today)
        due_date: Due date (defaults to bill_date)
        verify: If True, verify the bill was created (default True)
    
    Returns the bill GUID.
    Raises WriteVerificationError if verification fails.
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
        # Use schema discovery for column names that may vary between versions
        discount_num_col = _get_column('entries', 'i_discount_num')
        discount_denom_col = _get_column('entries', 'i_discount_denom')
        
        logger.debug(f"Using entry columns: {discount_num_col}, {discount_denom_col}")
        
        entry_sql = f"""
            INSERT INTO entries (
                guid, date, date_entered, description, action,
                quantity_num, quantity_denom,
                i_acct, i_price_num, i_price_denom,
                {discount_num_col}, {discount_denom_col}, i_disc_type, i_disc_how,
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
        """
        
        conn.execute(entry_sql, (
            entry_guid, date_posted, date_posted, memo,
            expense_account_guid, amount_num, amount_denom,
            expense_account_guid, amount_num, amount_denom,
            bill_guid
        ))
        
        conn.commit()
    
    logger.info(f"Created posted bill: {bill_id} for ${amount:.2f} (GUID: {bill_guid})")
    
    # POST-WRITE VERIFICATION - User data is SACRED
    if verify:
        verify_bill_created(bill_guid, amount, vendor_guid)
    
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
