import pytest
import sqlite3
import tempfile
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
import sys

# Add src to path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from config import GNUCASH_DB_PATH
import gnucash_db


class TestBillWorkflow:
    """Test the three-step bill workflow: create_bill -> post_bill -> pay_bill"""

    @pytest.fixture(scope="class")
    def test_db_path(self):
        """Create a temporary copy of the real database for testing"""
        if not GNUCASH_DB_PATH.exists():
            pytest.skip(f"Database not found: {GNUCASH_DB_PATH}")
        
        # Create temp copy
        temp_dir = Path(tempfile.mkdtemp())
        test_db = temp_dir / "test_database.gnucash"
        shutil.copy2(GNUCASH_DB_PATH, test_db)
        
        yield test_db
        
        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture(scope="class") 
    def db_connection(self, test_db_path):
        """Provide database connection to test database"""
        # Monkey patch the database path in gnucash_db module
        original_path = gnucash_db.config.GNUCASH_DB_PATH
        gnucash_db.config.GNUCASH_DB_PATH = test_db_path
        
        yield test_db_path
        
        # Restore original path
        gnucash_db.config.GNUCASH_DB_PATH = original_path

    @pytest.fixture
    def test_vendor_guid(self, db_connection):
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
    def test_accounts(self, db_connection):
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
    def bill_data(self):
        """Sample bill data for testing"""
        return {
            'amount': 12345,  # $123.45
            'memo': 'Test bill for automated testing',
            'date': date.today()
        }

    def test_create_bill_success(self, db_connection, test_vendor_guid, test_accounts, bill_data):
        """Test create_bill() creates unposted bill and entry"""
        
        # Call the function
        bill_guid = gnucash_db.create_bill(
            vendor_guid=test_vendor_guid,
            date=bill_data['date'],
            memo=bill_data['memo'], 
            amount=bill_data['amount'],
            expense_account_guid=test_accounts['expense_account']
        )
        
        # Verify bill was created
        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()
        
        # Check invoice table
        cursor.execute("""
            SELECT id, date_opened, date_posted, notes, active, owner_guid, 
                   post_txn, post_lot, post_acc
            FROM invoices WHERE guid = ?
        """, (bill_guid,))
        
        invoice = cursor.fetchone()
        assert invoice is not None, "Invoice not created"
        assert invoice[1] == bill_data['date'].strftime('%Y-%m-%d %H:%M:%S'), "Wrong date_opened"
        assert invoice[2] == '', "date_posted should be empty (unposted)"
        assert invoice[3] == bill_data['memo'], "Wrong notes/memo"
        assert invoice[4] == 1, "Invoice should be active"
        assert invoice[5] == test_vendor_guid, "Wrong vendor GUID"
        assert invoice[6] is None, "post_txn should be NULL (unposted)"
        assert invoice[7] is None, "post_lot should be NULL (unposted)" 
        assert invoice[8] is None, "post_acc should be NULL (unposted)"
        
        # Check entry table
        cursor.execute("""
            SELECT description, quantity_num, quantity_denom, i_price_num, i_price_denom,
                   i_acct, bill, invoice
            FROM entries WHERE bill = ?
        """, (bill_guid,))
        
        entry = cursor.fetchone()
        assert entry is not None, "Entry not created"
        assert entry[0] == bill_data['memo'], "Wrong entry description"
        assert entry[1] == 1, "Wrong quantity_num"  
        assert entry[2] == 1, "Wrong quantity_denom"
        assert entry[3] == bill_data['amount'], "Wrong i_price_num"
        assert entry[4] == 100, "Wrong i_price_denom"
        assert entry[5] == test_accounts['expense_account'], "Wrong expense account"
        assert entry[6] == bill_guid, "Entry should use 'bill' column"
        assert entry[7] == '', "Entry should NOT use 'invoice' column"
        
        # Check credit-note slot
        cursor.execute("""
            SELECT slot_type, int64_val FROM slots 
            WHERE obj_guid = ? AND name = 'credit-note'
        """, (bill_guid,))
        
        slot = cursor.fetchone()
        assert slot is not None, "credit-note slot missing"
        assert slot[0] == 1, "credit-note should be int64 type"
        assert slot[1] == 0, "credit-note should be 0 for bill"
        
        conn.close()

    def test_post_bill_success(self, db_connection, test_vendor_guid, test_accounts, bill_data):
        """Test post_bill() creates transaction, lot, and splits"""
        
        # First create an unposted bill
        bill_guid = gnucash_db.create_bill(
            vendor_guid=test_vendor_guid,
            date=bill_data['date'],
            memo=bill_data['memo'],
            amount=bill_data['amount'], 
            expense_account_guid=test_accounts['expense_account']
        )
        
        # Now post it
        lot_guid = gnucash_db.post_bill(
            bill_guid=bill_guid,
            date=bill_data['date'],
            ap_account_guid=test_accounts['ap_account']
        )
        
        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()
        
        # Verify invoice was updated with posting info
        cursor.execute("""
            SELECT date_posted, post_txn, post_lot, post_acc
            FROM invoices WHERE guid = ?
        """, (bill_guid,))
        
        invoice = cursor.fetchone()
        assert invoice[0] == bill_data['date'].strftime('%Y-%m-%d %H:%M:%S'), "date_posted not set"
        assert invoice[1] is not None, "post_txn should be set"
        assert invoice[2] == lot_guid, "post_lot should match returned lot_guid"
        assert invoice[3] == test_accounts['ap_account'], "post_acc should be AP account"
        
        post_txn_guid = invoice[1]
        
        # Verify lot was created
        cursor.execute("""
            SELECT account, closed FROM lots WHERE guid = ?
        """, (lot_guid,))
        
        lot = cursor.fetchone()
        assert lot is not None, "Lot not created"
        assert lot[0] == test_accounts['ap_account'], "Lot should be linked to AP account"
        assert lot[1] == 0, "Lot should not be closed yet (unpaid)"
        
        # Verify transaction was created
        cursor.execute("""
            SELECT currency_guid, post_date, description
            FROM transactions WHERE guid = ?
        """, (post_txn_guid,))
        
        txn = cursor.fetchone()
        assert txn is not None, "Transaction not created"
        assert txn[1] == bill_data['date'].strftime('%Y-%m-%d %H:%M:%S'), "Wrong transaction date"
        
        # Verify splits were created
        cursor.execute("""
            SELECT account_guid, value_num, value_denom, lot_guid, memo, action
            FROM splits WHERE tx_guid = ?
            ORDER BY value_num DESC
        """, (post_txn_guid,))
        
        splits = cursor.fetchall()
        assert len(splits) == 2, "Should have exactly 2 splits"
        
        # Expense split (debit, positive)
        expense_split = splits[0]
        assert expense_split[0] == test_accounts['expense_account'], "First split should be expense"
        assert expense_split[1] == bill_data['amount'], "Wrong expense amount"
        assert expense_split[2] == 100, "Wrong denominator"
        assert expense_split[3] == '', "Expense split should not have lot_guid"
        assert expense_split[4] == bill_data['memo'], "Wrong memo"
        assert expense_split[5] == 'Bill', "Wrong action"
        
        # AP split (credit, negative)  
        ap_split = splits[1]
        assert ap_split[0] == test_accounts['ap_account'], "Second split should be AP"
        assert ap_split[1] == -bill_data['amount'], "AP split should be negative"
        assert ap_split[2] == 100, "Wrong denominator"
        assert ap_split[3] == lot_guid, "AP split should have lot_guid"
        assert ap_split[4] == bill_data['memo'], "Wrong memo"
        assert ap_split[5] == 'Bill', "Wrong action"
        
        # Verify transaction slots
        cursor.execute("""
            SELECT name, slot_type, string_val FROM slots 
            WHERE obj_guid = ? AND name IN ('trans-txn-type', 'trans-read-only')
        """, (post_txn_guid,))
        
        txn_slots = cursor.fetchall()
        slot_dict = {slot[0]: slot[2] for slot in txn_slots}
        assert 'trans-txn-type' in slot_dict, "Missing trans-txn-type slot"
        assert slot_dict['trans-txn-type'] == 'I', "trans-txn-type should be 'I' for invoice"
        
        # Verify lot slots
        cursor.execute("""
            SELECT name, slot_type, string_val, guid_val FROM slots 
            WHERE obj_guid = ? AND name IN ('title', 'gncInvoice')
        """, (lot_guid,))
        
        lot_slots = cursor.fetchall()
        lot_slot_dict = {slot[0]: (slot[2], slot[3]) for slot in lot_slots}
        assert 'title' in lot_slot_dict, "Missing lot title slot"
        assert lot_slot_dict['gncInvoice'][1] == bill_guid, "gncInvoice should point to bill"
        
        conn.close()

    def test_pay_bill_success(self, db_connection, test_vendor_guid, test_accounts, bill_data):
        """Test pay_bill() creates payment transaction and closes lot"""
        
        # Create and post a bill first
        bill_guid = gnucash_db.create_bill(
            vendor_guid=test_vendor_guid,
            date=bill_data['date'], 
            memo=bill_data['memo'],
            amount=bill_data['amount'],
            expense_account_guid=test_accounts['expense_account']
        )
        
        lot_guid = gnucash_db.post_bill(
            bill_guid=bill_guid,
            date=bill_data['date'],
            ap_account_guid=test_accounts['ap_account']  
        )
        
        # Now pay it
        payment_txn_guid = gnucash_db.pay_bill(
            bill_guid=bill_guid,
            date=bill_data['date'],
            checking_account_guid=test_accounts['checking_account'],
            memo=bill_data['memo']
        )
        
        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()
        
        # Verify original lot is now closed
        cursor.execute("""
            SELECT closed FROM lots WHERE guid = ?
        """, (lot_guid,))
        
        lot = cursor.fetchone()
        assert lot[0] == -1, "Original lot should be closed (-1)"
        
        # Verify payment transaction was created
        cursor.execute("""
            SELECT currency_guid, post_date, description  
            FROM transactions WHERE guid = ?
        """, (payment_txn_guid,))
        
        payment_txn = cursor.fetchone()
        assert payment_txn is not None, "Payment transaction not created"
        assert payment_txn[1] == bill_data['date'].strftime('%Y-%m-%d %H:%M:%S'), "Wrong payment date"
        
        # Verify payment splits
        cursor.execute("""
            SELECT account_guid, value_num, value_denom, lot_guid, memo
            FROM splits WHERE tx_guid = ?
            ORDER BY value_num DESC  
        """, (payment_txn_guid,))
        
        payment_splits = cursor.fetchall()
        assert len(payment_splits) == 2, "Payment should have exactly 2 splits"
        
        # AP split (debit, positive - reduces AP balance)
        ap_payment_split = payment_splits[0] 
        assert ap_payment_split[0] == test_accounts['ap_account'], "First split should be AP"
        assert ap_payment_split[1] == bill_data['amount'], "Wrong AP payment amount"
        assert ap_payment_split[2] == 100, "Wrong denominator"
        assert ap_payment_split[3] == lot_guid, "AP split should link to original lot"
        assert ap_payment_split[4] == bill_data['memo'], "Wrong memo"
        
        # Checking split (credit, negative - reduces checking balance)
        checking_split = payment_splits[1]
        assert checking_split[0] == test_accounts['checking_account'], "Second split should be checking"
        assert checking_split[1] == -bill_data['amount'], "Checking split should be negative"
        assert checking_split[2] == 100, "Wrong denominator" 
        assert checking_split[3] == '', "Checking split should not have lot_guid"
        assert checking_split[4] == bill_data['memo'], "Wrong memo"
        
        # Verify payment transaction has notes slot with memo
        cursor.execute("""
            SELECT string_val FROM slots 
            WHERE obj_guid = ? AND name = 'notes'
        """, (payment_txn_guid,))
        
        notes_slot = cursor.fetchone()
        assert notes_slot is not None, "Missing notes slot on payment transaction"
        assert notes_slot[0] == bill_data['memo'], "Notes should contain original memo"
        
        # Verify payment transaction type
        cursor.execute("""
            SELECT string_val FROM slots 
            WHERE obj_guid = ? AND name = 'trans-txn-type'
        """, (payment_txn_guid,))
        
        txn_type_slot = cursor.fetchone()
        assert txn_type_slot is not None, "Missing trans-txn-type slot"
        assert txn_type_slot[0] == 'P', "Payment transaction type should be 'P'"
        
        # Verify payment lot was created with gncOwner slots
        cursor.execute("""
            SELECT guid FROM lots WHERE account = ? AND closed = 0 
            ORDER BY rowid DESC LIMIT 1
        """, (test_accounts['checking_account'],))
        
        payment_lot_result = cursor.fetchone()
        if payment_lot_result:  # Payment lot is optional depending on implementation
            payment_lot_guid = payment_lot_result[0]
            
            cursor.execute("""
                SELECT name, slot_type, int64_val, guid_val FROM slots 
                WHERE obj_guid = ? AND name LIKE 'gncOwner%'
            """, (payment_lot_guid,))
            
            owner_slots = cursor.fetchall()
            owner_dict = {slot[0]: (slot[2], slot[3]) for slot in owner_slots}
            
            if 'gncOwner/owner-type' in owner_dict:
                assert owner_dict['gncOwner/owner-type'][0] == 4, "Owner type should be 4 (vendor)"
            if 'gncOwner/owner-guid' in owner_dict:
                assert owner_dict['gncOwner/owner-guid'][1] == test_vendor_guid, "Owner GUID should match vendor"
        
        conn.close()

    def test_full_workflow_integration(self, db_connection, test_vendor_guid, test_accounts, bill_data):
        """Test complete workflow: create -> post -> pay"""
        
        # Step 1: Create bill
        bill_guid = gnucash_db.create_bill(
            vendor_guid=test_vendor_guid,
            date=bill_data['date'],
            memo=bill_data['memo'],
            amount=bill_data['amount'],
            expense_account_guid=test_accounts['expense_account']
        )
        
        assert bill_guid is not None, "create_bill should return bill GUID"
        
        # Step 2: Post bill  
        lot_guid = gnucash_db.post_bill(
            bill_guid=bill_guid,
            date=bill_data['date'],
            ap_account_guid=test_accounts['ap_account']
        )
        
        assert lot_guid is not None, "post_bill should return lot GUID"
        
        # Step 3: Pay bill
        payment_txn_guid = gnucash_db.pay_bill(
            bill_guid=bill_guid,
            date=bill_data['date'],
            checking_account_guid=test_accounts['checking_account'],
            memo=bill_data['memo']
        )
        
        assert payment_txn_guid is not None, "pay_bill should return payment transaction GUID"
        
        # Verify complete workflow in database
        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()
        
        # Check that bill is fully processed
        cursor.execute("""
            SELECT date_posted, post_txn, post_lot, post_acc 
            FROM invoices WHERE guid = ?
        """, (bill_guid,))
        
        invoice = cursor.fetchone()
        assert invoice[0] != '', "Bill should be posted"
        assert invoice[1] is not None, "Bill should have post_txn"
        assert invoice[2] == lot_guid, "Bill should have correct lot"
        assert invoice[3] == test_accounts['ap_account'], "Bill should have correct AP account"
        
        # Check that lot is closed
        cursor.execute("""
            SELECT closed FROM lots WHERE guid = ?
        """, (lot_guid,))
        
        lot = cursor.fetchone()
        assert lot[0] == -1, "Lot should be closed after payment"
        
        # Count transactions (should be 2: posting + payment)
        cursor.execute("""
            SELECT COUNT(*) FROM transactions t
            JOIN splits s ON t.guid = s.tx_guid  
            WHERE s.account_guid = ? AND s.memo = ?
        """, (test_accounts['ap_account'], bill_data['memo']))
        
        txn_count = cursor.fetchone()[0]
        assert txn_count == 2, "Should have 2 AP transactions (post + payment)"
        
        conn.close()

    def test_create_bill_error_cases(self, db_connection, test_accounts, bill_data):
        """Test create_bill() error handling"""
        
        # Test with invalid vendor GUID
        with pytest.raises(Exception):
            gnucash_db.create_bill(
                vendor_guid="invalid-guid-12345",
                date=bill_data['date'],
                memo=bill_data['memo'], 
                amount=bill_data['amount'],
                expense_account_guid=test_accounts['expense_account']
            )
        
        # Test with invalid expense account
        with pytest.raises(Exception):
            gnucash_db.create_bill(
                vendor_guid="valid-but-nonexistent-guid123456789012",
                date=bill_data['date'],
                memo=bill_data['memo'],
                amount=bill_data['amount'],
                expense_account_guid="invalid-expense-account"
            )

    def test_post_bill_error_cases(self, db_connection, test_accounts, bill_data):
        """Test post_bill() error handling"""
        
        # Test with invalid bill GUID
        with pytest.raises(Exception):
            gnucash_db.post_bill(
                bill_guid="invalid-bill-guid",
                date=bill_data['date'],
                ap_account_guid=test_accounts['ap_account']
            )

    def test_pay_bill_error_cases(self, db_connection, test_accounts, bill_data):
        """Test pay_bill() error handling"""
        
        # Test with invalid bill GUID  
        with pytest.raises(Exception):
            gnucash_db.pay_bill(
                bill_guid="invalid-bill-guid",
                date=bill_data['date'],
                checking_account_guid=test_accounts['checking_account'],
                memo=bill_data['memo']
            )

    @pytest.mark.manual
    def test_gnucash_ui_verification(self, db_connection, test_vendor_guid, test_accounts, bill_data):
        """Manual test: Create a bill and verify it appears correctly in GnuCash UI"""
        
        # Create, post, and pay a bill
        bill_guid = gnucash_db.create_bill(
            vendor_guid=test_vendor_guid,
            date=bill_data['date'],
            memo="MANUAL_TEST_BILL - Please verify in GnuCash",
            amount=bill_data['amount'],
            expense_account_guid=test_accounts['expense_account']
        )
        
        lot_guid = gnucash_db.post_bill(
            bill_guid=bill_guid,
            date=bill_data['date'],
            ap_account_guid=test_accounts['ap_account']
        )
        
        payment_txn_guid = gnucash_db.pay_bill(
            bill_guid=bill_guid,
            date=bill_data['date'], 
            checking_account_guid=test_accounts['checking_account'],
            memo="MANUAL_TEST_BILL - Please verify in GnuCash"
        )
        
        # Get vendor name for instructions
        conn = sqlite3.connect(db_connection)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM vendors WHERE guid = ?", (test_vendor_guid,))
        vendor_name = cursor.fetchone()[0]
        
        cursor.execute("SELECT id FROM invoices WHERE guid = ?", (bill_guid,))
        bill_id = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"\n{'='*60}")
        print("MANUAL VERIFICATION REQUIRED")
        print(f"{'='*60}")
        print(f"A test bill has been created in the database copy at:")
        print(f"  {db_connection}")
        print(f"")
        print(f"Bill details:")
        print(f"  Vendor: {vendor_name}")
        print(f"  Bill ID: {bill_id}")
        print(f"  Amount: ${bill_data['amount']/100:.2f}")
        print(f"  Memo: MANUAL_TEST_BILL - Please verify in GnuCash")
        print(f"")
        print(f"To verify:")
        print(f"1. Copy this test database over your real database (BACKUP FIRST!)")
        print(f"2. Open GnuCash")
        print(f"3. Check Business → Vendor → Process Payment")
        print(f"4. Verify the bill appears as PAID")
        print(f"5. Check that vendor address shows on payment")
        print(f"6. Verify memo appears in check register")
        print(f"{'='*60}")
        
        # This test always "passes" - it's just for manual verification
        assert True


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_bill_workflow.py -v
    # Run manual tests: python -m pytest tests/test_bill_workflow.py -v -m manual
    pytest.main([__file__, "-v"])