"""
Bill Processor - Main entry point.

Process bills from input file and create posted bills in GnuCash.
"""

import sys
import argparse
from pathlib import Path
from datetime import date
from loguru import logger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
import gnucash_db
from vendor_manager import VendorManager
from utils import (
    parse_input_line, 
    format_currency, 
    format_date,
    print_header,
    print_separator,
    confirm_proceed
)
from logging_setup import setup_logging_for_script, log_function_entry, log_function_exit, log_stage, log_error_with_context


def process_bill(
    vendor_manager: VendorManager,
    vendor_name: str,
    amount: float,
    memo: str,
    bill_date: date
) -> bool:
    """
    Process a single bill entry.
    
    Returns True if successful, False otherwise.
    """
    log_function_entry("process_bill", vendor_name=vendor_name, amount=amount, memo=memo[:50], bill_date=bill_date)
    logger.info(f"Processing bill: {vendor_name} - {format_currency(amount)}")
    
    print(f"\n{'-'*60}")
    print(f"Processing: {vendor_name}")
    print(f"  Amount: {format_currency(amount)}")
    print(f"  Memo: {memo}")
    print(f"  Date: {format_date(bill_date)}")
    print(f"{'-'*60}")
    
    # Find or create vendor
    logger.debug(f"Looking up vendor: {vendor_name}")
    vendor_data, match_type = vendor_manager.find_vendor(vendor_name)
    
    if vendor_data:
        logger.info(f"Vendor found: {vendor_data.get('display_name')} ({match_type} match)")
        print(f"\n✓ Found vendor: {vendor_data.get('display_name')} ({match_type} match)")
        
        # Add alias if fuzzy match
        if match_type == 'fuzzy' and vendor_name.lower() != vendor_data.get('display_name', '').lower():
            if confirm_proceed(f"Add '{vendor_name}' as alias?"):
                vendor_key = next(
                    (k for k, v in vendor_manager.vendors['vendors'].items() 
                     if v.get('gnucash_guid') == vendor_data.get('gnucash_guid')),
                    None
                )
                if vendor_key:
                    vendor_manager.add_alias(vendor_name, vendor_key)
    else:
        logger.warning(f"Vendor not found: {vendor_name}")
        print(f"\n? Vendor not found: {vendor_name}")
        if confirm_proceed("Create new vendor?"):
            logger.info(f"User chose to create new vendor: {vendor_name}")
            vendor_data = vendor_manager.create_new_vendor(vendor_name)
            if vendor_data:
                logger.info(f"Successfully created vendor: {vendor_data.get('display_name')}")
            else:
                logger.error(f"Failed to create vendor: {vendor_name}")
                print("  Failed to create vendor.")
                log_function_exit("process_bill", False)
                return False
        else:
            logger.info(f"User chose to skip bill for: {vendor_name}")
            print("  Skipping this bill.")
            log_function_exit("process_bill", False)
            return False
    
    # Get expense account
    logger.debug("Getting or creating expense account")
    try:
        expense_acct_guid = vendor_manager.get_or_create_expense_account(vendor_data)
        logger.debug(f"Expense account GUID: {expense_acct_guid}")
    except ValueError as e:
        log_error_with_context(e, "Failed to get expense account", vendor_name=vendor_name)
        print(f"  ERROR: {e}")
        log_function_exit("process_bill", False)
        return False
    
    # Create the posted bill
    logger.debug("Creating posted bill in GnuCash")
    try:
        vendor_guid = vendor_data.get('gnucash_guid')
        if not vendor_guid:
            logger.debug("No vendor GUID cached, searching in GnuCash by name")
            # Try to find in GnuCash by name
            gc_vendor = gnucash_db.find_vendor_by_name(vendor_data.get('display_name'))
            if gc_vendor:
                vendor_guid = gc_vendor['guid']
                logger.debug(f"Found vendor GUID in GnuCash: {vendor_guid}")
            else:
                logger.error(f"Could not find vendor GUID for: {vendor_data.get('display_name')}")
                print(f"  ERROR: Could not find vendor GUID")
                log_function_exit("process_bill", False)
                return False
        
        bill_guid = gnucash_db.create_posted_bill(
            vendor_guid=vendor_guid,
            expense_account_guid=expense_acct_guid,
            amount=amount,
            memo=memo,
            bill_date=bill_date
        )
        
        logger.info(f"Successfully created bill: GUID={bill_guid}, amount={format_currency(amount)}")
        print(f"\n✓ Created bill for {format_currency(amount)}")
        log_function_exit("process_bill", True)
        return True
        
    except Exception as e:
        log_error_with_context(e, "Error creating posted bill", vendor_name=vendor_name, amount=amount)
        print(f"  ERROR: {e}")
        log_function_exit("process_bill", False)
        return False


def process_input_file(input_path: Path) -> dict:
    """
    Process all bills from input file.
    
    Returns dict with counts: total, success, failed, skipped
    """
    log_function_entry("process_input_file", input_path=str(input_path))
    logger.info(f"Processing input file: {input_path}")
    
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Read and parse input
    logger.debug("Reading and parsing input file")
    bills = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            parsed = parse_input_line(line)
            if parsed:
                parsed['line_num'] = line_num
                bills.append(parsed)
    
    if not bills:
        print("No bills to process.")
        return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
    
    # Show summary
    print_header("BILLS TO PROCESS")
    total_amount = sum(b['amount'] for b in bills)
    
    print(f"\nFound {len(bills)} bill(s) totaling {format_currency(total_amount)}:\n")
    
    for i, bill in enumerate(bills, 1):
        print(f"  {i}. {bill['vendor_name']}: {format_currency(bill['amount'])}")
        if bill['memo'] != config.DEFAULT_MEMO:
            print(f"     Memo: {bill['memo']}")
    
    print()
    if not confirm_proceed("Process these bills?"):
        return {'total': len(bills), 'success': 0, 'failed': 0, 'skipped': len(bills)}
    
    # Process each bill
    vendor_manager = VendorManager()
    
    results = {'total': len(bills), 'success': 0, 'failed': 0, 'skipped': 0}
    
    for bill in bills:
        try:
            success = process_bill(
                vendor_manager,
                bill['vendor_name'],
                bill['amount'],
                bill['memo'],
                bill['date']
            )
            
            if success:
                results['success'] += 1
            else:
                results['skipped'] += 1
                
        except KeyboardInterrupt:
            print("\n\nInterrupted by user.")
            break
        except Exception as e:
            logger.exception(f"Error processing bill: {e}")
            results['failed'] += 1
    
    return results


def show_status():
    """Show current database status."""
    print_header("DATABASE STATUS")
    
    # Test connection
    print("\nTesting GnuCash database connection...")
    if gnucash_db.test_connection():
        print("  ✓ Connection OK")
    else:
        print("  ✗ Connection FAILED")
        return
    
    # Count vendors
    vendors = gnucash_db.get_all_vendors()
    print(f"\n  Vendors in GnuCash: {len(vendors)}")
    
    # Count unpaid bills
    unpaid = gnucash_db.get_unpaid_bills()
    print(f"  Unpaid bills: {len(unpaid)}")
    
    # JSON database
    vm = VendorManager()
    json_vendors = vm.list_vendors()
    print(f"  Vendors in local database: {len(json_vendors)}")
    print(f"  Aliases defined: {len(vm.vendors.get('aliases', {}))}")


def list_vendors():
    """List all known vendors."""
    print_header("KNOWN VENDORS")
    
    vm = VendorManager()
    vendors = vm.list_vendors()
    
    if not vendors:
        print("\nNo vendors in local database.")
        print("Vendors will be added as you process bills.")
        return
    
    print(f"\n{'Name':<30} {'GnuCash ID':<12} {'Has Address':<12}")
    print("-" * 54)
    
    for v in vendors:
        name = v.get('display_name', v['key'])[:29]
        gc_id = v.get('gnucash_id', 'N/A')
        has_addr = 'Yes' if v.get('addr_line1') else 'No'
        print(f"{name:<30} {gc_id:<12} {has_addr:<12}")


def main():
    # Set up logging first
    setup_logging_for_script("bill_processor")
    
    parser = argparse.ArgumentParser(
        description="Process bills and create them in GnuCash"
    )
    
    parser.add_argument(
        'input_file',
        nargs='?',
        default=config.DEFAULT_INPUT_FILE,
        help=f"Input file with bills (default: {config.DEFAULT_INPUT_FILE})"
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help="Show database status"
    )
    
    parser.add_argument(
        '--list-vendors',
        action='store_true',
        help="List all known vendors"
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Parse input without creating bills"
    )
    
    args = parser.parse_args()
    logger.info(f"Bill processor started with args: {args}")
    
    # Handle status command
    if args.status:
        logger.info("Running status check")
        show_status()
        return 0
    
    # Handle list vendors
    if args.list_vendors:
        logger.info("Listing vendors")
        list_vendors()
        return 0
    
    # Process bills
    logger.info("Starting bill processing")
    print_header("GNUCASH BILL PROCESSOR")
    print(f"\nGnuCash DB: {config.GNUCASH_DB_PATH}")
    print(f"Input file: {args.input_file}")
    
    # Verify database
    logger.debug("Testing database connection")
    if not gnucash_db.test_connection():
        logger.error("Cannot connect to GnuCash database")
        print("\nERROR: Cannot connect to GnuCash database.")
        print(f"Check path in config.py: {config.GNUCASH_DB_PATH}")
        return 1
    
    input_path = Path(args.input_file)
    logger.debug(f"Input file path: {input_path}")
    
    if args.dry_run:
        logger.info("Running in dry-run mode")
        print("\n[DRY RUN - No changes will be made]")
        # Just parse and show
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                parsed = parse_input_line(line)
                if parsed:
                    print(f"  {parsed['vendor_name']}: {format_currency(parsed['amount'])}")
        return 0
    
    try:
        log_stage("Processing Bills")
        results = process_input_file(input_path)
        
        # Show summary
        logger.info(f"Processing complete - Total: {results['total']}, Success: {results['success']}, Failed: {results['failed']}, Skipped: {results['skipped']}")
        print_header("PROCESSING COMPLETE")
        print(f"\n  Total bills: {results['total']}")
        print(f"  Successful:  {results['success']}")
        print(f"  Failed:      {results['failed']}")
        print(f"  Skipped:     {results['skipped']}")
        
        if results['success'] > 0:
            logger.info("Bills ready for payment in GnuCash")
            print(f"\n  ✓ Bills are ready in GnuCash for payment!")
            print(f"    Open GnuCash -> Business -> Vendor -> Pay Bill")
        
        exit_code = 0 if results['failed'] == 0 else 1
        logger.info(f"Bill processor exiting with code: {exit_code}")
        return exit_code
        
    except FileNotFoundError as e:
        log_error_with_context(e, "Input file not found")
        print(f"\nERROR: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Processing cancelled by user")
        print("\n\nCancelled.")
        return 1
    except Exception as e:
        log_error_with_context(e, "Unexpected error during bill processing")
        raise


if __name__ == '__main__':
    sys.exit(main())
