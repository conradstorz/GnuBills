import pytest
import sqlite3
import tempfile
import shutil
from datetime import date
from pathlib import Path
import sys

# Add src to path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from config import GNUCASH_DB_PATH
import gnucash_db


@pytest.fixture(scope="class")
def test_db_path():
    """Create a temporary copy of the real database for testing"""
    if not GNUCASH_DB_PATH.exists():
        pytest.skip(f"Database not found: {GNUCASH_DB_PATH}")
    
    # Create temp copy
    temp_dir = Path(tempfile.mkdtemp())
    test_db = temp_dir / "test_database.gnucash"
    shutil.copy2(GNUCASH_DB_PATH, test_db)
    
    yield test_db
    
    # Cleanup with Windows-safe approach
    try:
        # Close any potential open connections first
        import gc
        gc.collect()
        
        # Try to remove with error handling
        if test_db.exists():
            test_db.unlink()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        # On Windows, sometimes files are locked - ignore cleanup errors in tests
        pass

@pytest.fixture(scope="class") 
def db_connection(test_db_path):
    """Provide database connection to test database"""
    # Monkey patch the database path in gnucash_db module
    original_path = gnucash_db.config.GNUCASH_DB_PATH
    gnucash_db.config.GNUCASH_DB_PATH = test_db_path
    
    yield test_db_path
    
    # Restore original path
    gnucash_db.config.GNUCASH_DB_PATH = original_path

@pytest.fixture
def test_vendor_guid(db_connection):
    """Get an existing vendor GUID for testing"""
    conn = sqlite3.connect(db_connection)
    cursor = conn.cursor()
    cursor.execute("SELECT guid, name FROM vendors LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        pytest.skip("No vendors found in test database")
    
    return result[0]  # Return GUID

@pytest.fixture
def test_accounts(db_connection):
    """Get required account GUIDs for testing"""
    conn = sqlite3.connect(db_connection)
    cursor = conn.cursor()
    
    # Get AP account
    cursor.execute("""
        SELECT guid FROM accounts 
        WHERE name = 'Accounts Payable' AND account_type = 'PAYABLE'
        LIMIT 1
    """)
    ap_result = cursor.fetchone()
    
    # Get expense account (non-placeholder)
    cursor.execute("""
        SELECT guid FROM accounts 
        WHERE account_type = 'EXPENSE' AND placeholder = 0
        LIMIT 1
    """)
    expense_result = cursor.fetchone()
    
    # Get checking account
    cursor.execute("""
        SELECT guid FROM accounts 
        WHERE account_type = 'BANK' 
        LIMIT 1
    """)
    checking_result = cursor.fetchone()
    
    conn.close()
    
    if not all([ap_result, expense_result, checking_result]):
        pytest.skip("Required accounts not found in test database")
    
    return {
        'ap_account': ap_result[0],
        'expense_account': expense_result[0], 
        'checking_account': checking_result[0]
    }

@pytest.fixture
def bill_data():
    """Sample bill data for testing"""
    return {
        'amount': 12345,  # $123.45
        'memo': 'Test bill for automated testing',
        'date': date.today()
    }