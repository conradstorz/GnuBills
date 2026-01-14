"""
GnuCash Database Observer

Captures snapshots of the GnuCash SQLite database for analysis.
Use this to observe what GnuCash writes at each step:
1. Create bill (unposted)
2. Post bill
3. Pay bill

Usage:
    # Take a snapshot with a label
    python db_observer.py snapshot baseline
    python db_observer.py snapshot after_create
    python db_observer.py snapshot after_post
    python db_observer.py snapshot after_pay
    
    # Compare two snapshots
    python db_observer.py diff baseline after_create
    
    # List all snapshots
    python db_observer.py list
    
    # Show current database state (no save)
    python db_observer.py show
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
import config
from logging_setup import setup_logging_for_script, log_function_entry, log_function_exit, log_database_operation, log_stage

SNAPSHOTS_DIR = config.PROJECT_ROOT / "data" / "snapshots"

# Capture ALL tables - we don't want to miss anything!
# Set to None to auto-discover all tables in the database
OBSERVED_TABLES = None  # Will be populated dynamically

# Large tables where we limit rows for performance
# All other tables get ALL rows captured
LARGE_TABLES = {
    'slots': 500,        # Can be huge, but we want recent ones
    'splits': 200,       # Many splits
    'transactions': 100, # Many transactions
}

# Tables to always capture completely (even if large)
ALWAYS_FULL_TABLES = [
    'invoices', 'entries', 'lots', 'vendors', 'customers',
    'billterms', 'taxtables', 'taxtable_entries', 'jobs', 'orders',
    'employees', 'books', 'commodities', 'budgets', 'budget_amounts',
    'schedxactions', 'recurrences', 'prices', 'gnclock', 'versions'
]


def get_connection() -> sqlite3.Connection:
    """Get a read-only connection to the GnuCash database."""
    log_function_entry("get_connection")
    
    db_path = Path(config.GNUCASH_DB_PATH)
    logger.debug(f"Attempting to connect to database: {db_path}")
    
    if not db_path.exists():
        logger.error(f"Database file not found: {db_path}")
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    uri = f"file:{db_path}?mode=ro"
    logger.debug(f"Opening read-only connection with URI: {uri}")
    
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        logger.debug("Database connection established successfully")
        log_function_exit("get_connection", "connection")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def get_table_schema(conn: sqlite3.Connection, table: str) -> List[str]:
    """Get column names for a table."""
    log_function_entry("get_table_schema", table=table)
    
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [row['name'] for row in cursor]
        logger.debug(f"Table {table} has {len(columns)} columns: {', '.join(columns)}")
        log_function_exit("get_table_schema", len(columns))
        return columns
    except Exception as e:
        logger.error(f"Failed to get schema for table {table}: {e}")
        raise


def get_all_tables(conn: sqlite3.Connection) -> List[str]:
    """Get list of all tables in the database."""
    log_function_entry("get_all_tables")
    
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row['name'] for row in cursor]
        logger.debug(f"Found {len(tables)} tables in database: {', '.join(tables)}")
        log_function_exit("get_all_tables", len(tables))
        return tables
    except Exception as e:
        logger.error(f"Failed to get table list: {e}")
        raise


def fetch_table_data(conn: sqlite3.Connection, table: str) -> List[Dict]:
    """Fetch data from a table.
    
    Captures ALL rows for most tables.
    For very large tables (slots, splits, transactions), captures recent rows.
    """
    log_function_entry("fetch_table_data", table=table)
    
    # Skip sqlite internal tables
    if table.startswith('sqlite_'):
        logger.debug(f"Skipping SQLite internal table: {table}")
        return []
    
    # Determine if we should limit rows
    if table in ALWAYS_FULL_TABLES:
        limit = None
        logger.debug(f"Fetching ALL rows from {table} (always full table)")
    elif table in LARGE_TABLES:
        limit = LARGE_TABLES[table]
        logger.debug(f"Limiting {table} to {limit} rows (large table)")
    else:
        limit = None  # Get all rows by default
        logger.debug(f"Fetching ALL rows from {table} (standard table)")
    
    try:
        log_database_operation("SELECT", table, limit=limit)
        
        if limit:
            cursor = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT {limit}")
        else:
            cursor = conn.execute(f"SELECT * FROM {table}")
        
        rows = []
        for row in cursor:
            rows.append({key: row[key] for key in row.keys()})
        
        logger.debug(f"Fetched {len(rows)} rows from {table}")
        log_function_exit("fetch_table_data", len(rows))
        return rows
        
    except Exception as e:
        logger.warning(f"Could not fetch data from {table}: {e}")
        return []


def capture_snapshot() -> Dict[str, Any]:
    """Capture current database state - ALL tables."""
    log_function_entry("capture_snapshot")
    log_stage("Capturing database snapshot")
    
    conn = get_connection()
    
    # Get all tables dynamically
    all_tables = get_all_tables(conn)
    logger.info(f"Capturing snapshot of {len(all_tables)} tables")
    
    snapshot = {
        'timestamp': datetime.now().isoformat(),
        'database': str(config.GNUCASH_DB_PATH),
        'tables': {}
    }
    
    total_rows = 0
    for i, table in enumerate(all_tables, 1):
        try:
            logger.debug(f"Processing table {i}/{len(all_tables)}: {table}")
            data = fetch_table_data(conn, table)
            snapshot['tables'][table] = {
                'count': len(data),
                'rows': data
            }
            total_rows += len(data)
            
        except Exception as e:
            logger.error(f"Error capturing table {table}: {e}")
            snapshot['tables'][table] = {
                'error': str(e),
                'count': 0,
                'rows': []
            }
    
    conn.close()
    logger.info(f"Snapshot captured: {len(all_tables)} tables, {total_rows} total rows")
    log_function_exit("capture_snapshot", f"{len(all_tables)} tables")
    return snapshot


def save_snapshot(snapshot: Dict, label: str) -> Path:
    """Save a snapshot to disk."""
    log_function_entry("save_snapshot", label=label)
    
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Snapshots directory: {SNAPSHOTS_DIR}")
    
    filename = f"{label}.json"
    filepath = SNAPSHOTS_DIR / filename
    logger.debug(f"Saving snapshot to: {filepath}")
    
    try:
        with open(filepath, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
        
        file_size = filepath.stat().st_size / 1024 / 1024  # MB
        logger.info(f"Snapshot saved: {filepath} ({file_size:.1f} MB)")
        log_function_exit("save_snapshot", str(filepath))
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to save snapshot to {filepath}: {e}")
        raise


def load_snapshot(label: str) -> Dict:
    """Load a snapshot from disk."""
    log_function_entry("load_snapshot", label=label)
    
    filepath = SNAPSHOTS_DIR / f"{label}.json"
    logger.debug(f"Loading snapshot from: {filepath}")
    
    if not filepath.exists():
        logger.error(f"Snapshot file not found: {filepath}")
        raise FileNotFoundError(f"Snapshot not found: {filepath}")
    
    try:
        with open(filepath) as f:
            snapshot = json.load(f)
        
        table_count = len(snapshot.get('tables', {}))
        logger.debug(f"Loaded snapshot with {table_count} tables")
        log_function_exit("load_snapshot", f"{table_count} tables")
        return snapshot
        
    except Exception as e:
        logger.error(f"Failed to load snapshot from {filepath}: {e}")
        raise


def list_snapshots() -> List[str]:
    """List all available snapshots."""
    log_function_entry("list_snapshots")
    
    if not SNAPSHOTS_DIR.exists():
        logger.debug(f"Snapshots directory does not exist: {SNAPSHOTS_DIR}")
        return []
    
    snapshots = sorted([f.stem for f in SNAPSHOTS_DIR.glob("*.json")])
    logger.debug(f"Found {len(snapshots)} snapshots: {', '.join(snapshots)}")
    log_function_exit("list_snapshots", len(snapshots))
    return snapshots


def diff_snapshots(label1: str, label2: str) -> Dict[str, Any]:
    """Compare two snapshots and return differences."""
    log_function_entry("diff_snapshots", label1=label1, label2=label2)
    log_stage(f"Comparing snapshots: {label1} vs {label2}")
    
    snap1 = load_snapshot(label1)
    snap2 = load_snapshot(label2)
    
    diff = {
        'from': label1,
        'to': label2,
        'from_timestamp': snap1['timestamp'],
        'to_timestamp': snap2['timestamp'],
        'changes': {}
    }
    
    # Get all tables from both snapshots
    all_tables = set(snap1['tables'].keys()) | set(snap2['tables'].keys())
    logger.debug(f"Comparing {len(all_tables)} tables")
    
    total_changes = 0
    for table in sorted(all_tables):
        logger.debug(f"Analyzing differences in table: {table}")
        
        table_diff = {
            'added': [],
            'removed': [],
            'modified': []
        }
        
        rows1_list = snap1['tables'].get(table, {}).get('rows', [])
        rows2_list = snap2['tables'].get(table, {}).get('rows', [])
        
        # Get rows indexed by guid or id (primary key for most tables)
        def get_key(row, idx):
            return row.get('guid') or row.get('id') or str(idx)
        
        rows1 = {get_key(row, i): row for i, row in enumerate(rows1_list)}
        rows2 = {get_key(row, i): row for i, row in enumerate(rows2_list)}
        
        # Find added rows
        for key, row in rows2.items():
            if key not in rows1:
                table_diff['added'].append(row)
        
        # Find removed rows
        for key, row in rows1.items():
            if key not in rows2:
                table_diff['removed'].append(row)
        
        # Find modified rows
        for key in set(rows1.keys()) & set(rows2.keys()):
            if rows1[key] != rows2[key]:
                table_diff['modified'].append({
                    'key': key,
                    'before': rows1[key],
                    'after': rows2[key],
                    'changed_fields': [
                        k for k in rows2[key].keys()
                        if rows1[key].get(k) != rows2[key].get(k)
                    ]
                })
        
        # Only include if there are changes
        if table_diff['added'] or table_diff['removed'] or table_diff['modified']:
            diff['changes'][table] = table_diff
            table_change_count = len(table_diff['added']) + len(table_diff['removed']) + len(table_diff['modified'])
            total_changes += table_change_count
            logger.debug(f"Table {table}: {table_change_count} changes (added: {len(table_diff['added'])}, removed: {len(table_diff['removed'])}, modified: {len(table_diff['modified'])})")
    
    logger.info(f"Comparison complete: {len(diff['changes'])} tables with changes, {total_changes} total changes")
    log_function_exit("diff_snapshots", f"{len(diff['changes'])} tables changed")
    return diff


def print_snapshot_summary(snapshot: Dict):
    """Print a summary of a snapshot."""
    log_function_entry("print_snapshot_summary")
    
    logger.debug("Printing snapshot summary")
    print(f"\n{'='*60}")
    print(f"Snapshot: {snapshot.get('timestamp', 'unknown')}")
    print(f"Database: {snapshot.get('database', 'unknown')}")
    print(f"{'='*60}")
    
    total_rows = 0
    for table, data in snapshot['tables'].items():
        if 'error' in data:
            print(f"\n{table}: ERROR - {data['error']}")
            logger.warning(f"Table {table} had error: {data['error']}")
        else:
            row_count = data['count']
            total_rows += row_count
            print(f"\n{table}: {row_count} rows")
            
            # Show key info for certain tables
            if table == 'invoices' and data['rows']:
                print("  Bills/Invoices:")
                for row in data['rows'][:10]:
                    posted = "POSTED" if row.get('date_posted') else "UNPOSTED"
                    print(f"    {row.get('id', '?'):12} | {posted:10} | lot={str(row.get('post_lot', ''))[:12]}")
            
            elif table == 'lots' and data['rows']:
                print("  Lots:")
                for row in data['rows'][:10]:
                    closed = "CLOSED" if row.get('is_closed') else "OPEN"
                    print(f"    {row.get('guid', '?')[:12]}... | {closed}")
            
            elif table == 'slots' and data['rows']:
                print(f"  Slots (showing first 10):")
                for row in data['rows'][:10]:
                    val = row.get('string_val') or row.get('guid_val', '')[:12] if row.get('guid_val') else row.get('int64_val', '')
                    print(f"    {row.get('name', '?'):20} | type={row.get('slot_type')} | val={val}")


def print_diff(diff: Dict):
    """Print a diff in a readable format."""
    log_function_entry("print_diff", from_snapshot=diff['from'], to_snapshot=diff['to'])
    
    logger.debug("Printing diff summary")
    print(f"\n{'='*60}")
    print(f"DIFF: {diff['from']} -> {diff['to']}")
    print(f"From: {diff['from_timestamp']}")
    print(f"To:   {diff['to_timestamp']}")
    print(f"{'='*60}")
    
    if not diff['changes']:
        logger.info("No changes detected between snapshots")
        print("\nNo changes detected.")
        return
    
    total_changes = sum(len(changes['added']) + len(changes['removed']) + len(changes['modified']) 
                       for changes in diff['changes'].values())
    logger.info(f"Displaying {len(diff['changes'])} tables with {total_changes} total changes")
    
    for table, changes in sorted(diff['changes'].items()):
        print(f"\n{'─'*60}")
        print(f"TABLE: {table}")
        print(f"{'─'*60}")
        
        if changes['added']:
            print(f"\n  ADDED ({len(changes['added'])} rows):")
            for row in changes['added']:
                # Smart display based on table type
                if table == 'invoices':
                    print(f"    + Invoice {row.get('id')}: owner_type={row.get('owner_type')}, posted={row.get('date_posted')}")
                elif table == 'lots':
                    print(f"    + Lot {str(row.get('guid', ''))[:12]}...: account={str(row.get('account_guid', ''))[:12]}... closed={row.get('is_closed')}")
                elif table == 'slots':
                    val = row.get('string_val') or (str(row.get('guid_val', ''))[:16] if row.get('guid_val') else None) or row.get('int64_val') or row.get('gdate_val') or ''
                    print(f"    + Slot: obj={str(row.get('obj_guid', ''))[:12]}... name={row.get('name')} type={row.get('slot_type')} val={val}")
                elif table == 'transactions':
                    print(f"    + Txn {str(row.get('guid', ''))[:12]}...: {str(row.get('description', ''))[:40]} | {row.get('post_date')}")
                elif table == 'splits':
                    print(f"    + Split: acct={str(row.get('account_guid', ''))[:12]}... val={row.get('value_num')}/{row.get('value_denom')} action={row.get('action')} lot={str(row.get('lot_guid') or '')[:12]}")
                elif table == 'entries':
                    print(f"    + Entry: {str(row.get('description', ''))[:30]} bill={str(row.get('bill') or '')[:12]} invoice={str(row.get('invoice') or '')[:12]}")
                else:
                    # Generic display - show first few meaningful fields
                    key = row.get('guid') or row.get('id') or row.get('name') or str(list(row.values())[0])
                    print(f"    + {key}")
        
        if changes['removed']:
            print(f"\n  REMOVED ({len(changes['removed'])} rows):")
            for row in changes['removed']:
                key = row.get('guid') or row.get('id') or row.get('name') or str(list(row.values())[0])
                print(f"    - {str(key)[:40]}")
        
        if changes['modified']:
            print(f"\n  MODIFIED ({len(changes['modified'])} rows):")
            for mod in changes['modified']:
                print(f"    ~ {str(mod['key'])[:30]}...")
                print(f"      Changed: {', '.join(mod['changed_fields'])}")
                for field in mod['changed_fields'][:5]:  # Show first 5 changed fields
                    before = mod['before'].get(field)
                    after = mod['after'].get(field)
                    print(f"        {field}: {before} -> {after}")


def show_current_state():
    """Show the current database state without saving."""
    log_function_entry("show_current_state")
    log_stage("Displaying current database state")
    
    snapshot = capture_snapshot()
    print_snapshot_summary(snapshot)
    
    # Also show some detailed info
    conn = get_connection()
    
    print(f"\n{'='*60}")
    print("DETAILED VIEW - VENDOR BILLS")
    print(f"{'='*60}")
    
    logger.debug("Querying detailed bill information")
    
    cursor = conn.execute("""
        SELECT i.*, v.name as vendor_name
        FROM invoices i
        LEFT JOIN vendors v ON i.owner_guid = v.guid
        WHERE i.owner_type = 4
        ORDER BY i.rowid DESC
    """)
    
    for row in cursor:
        print(f"\n--- Bill: {row['id']} ---")
        print(f"  GUID: {row['guid']}")
        print(f"  Vendor: {row['vendor_name']}")
        print(f"  Date Opened: {row['date_opened']}")
        print(f"  Date Posted: {row['date_posted']}")
        print(f"  Post Txn: {row['post_txn']}")
        print(f"  Post Lot: {row['post_lot']}")
        print(f"  Post Acc: {row['post_acc']}")
        
        # Show lot slots if posted
        if row['post_lot']:
            cursor2 = conn.execute("""
                SELECT name, slot_type, string_val, guid_val, int64_val
                FROM slots WHERE obj_guid = ?
            """, (row['post_lot'],))
            slots = list(cursor2)
            if slots:
                print(f"  Lot Slots:")
                for s in slots:
                    val = s['string_val'] or s['guid_val'] or s['int64_val']
                    print(f"    {s['name']}: type={s['slot_type']} val={val}")
            else:
                print(f"  Lot Slots: NONE!")
        
        # Show transaction slots if posted
        if row['post_txn']:
            cursor2 = conn.execute("""
                SELECT name, slot_type, string_val, guid_val, int64_val
                FROM slots WHERE obj_guid = ?
            """, (row['post_txn'],))
            slots = list(cursor2)
            if slots:
                print(f"  Transaction Slots:")
                for s in slots:
                    val = s['string_val'] or s['guid_val'] or s['int64_val']
                    print(f"    {s['name']}: type={s['slot_type']} val={val}")
            else:
                print(f"  Transaction Slots: NONE!")
    
    conn.close()


def main():
    # Set up logging first
    setup_logging_for_script("db_observer")
    
    if len(sys.argv) < 2:
        logger.warning("No command provided")
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    logger.info(f"Running command: {command}")
    
    try:
        if command == 'snapshot':
            if len(sys.argv) < 3:
                logger.error("Missing snapshot label argument")
                print("Usage: python db_observer.py snapshot <label>")
                return
            label = sys.argv[2]
            logger.info(f"Creating snapshot with label: {label}")
            print(f"Capturing snapshot '{label}'...")
            snapshot = capture_snapshot()
            filepath = save_snapshot(snapshot, label)
            print(f"Saved to: {filepath}")
            print_snapshot_summary(snapshot)
        
        elif command == 'diff':
            if len(sys.argv) < 4:
                logger.error("Missing snapshot labels for diff")
                print("Usage: python db_observer.py diff <label1> <label2>")
                return
            label1 = sys.argv[2]
            label2 = sys.argv[3]
            logger.info(f"Comparing snapshots: {label1} -> {label2}")
            print(f"Comparing '{label1}' to '{label2}'...")
            diff = diff_snapshots(label1, label2)
            print_diff(diff)
            
            # Also save the diff
            diff_path = SNAPSHOTS_DIR / f"diff_{label1}_to_{label2}.json"
            with open(diff_path, 'w') as f:
                json.dump(diff, f, indent=2, default=str)
            logger.info(f"Diff saved to: {diff_path}")
            print(f"\nDiff saved to: {diff_path}")
        
        elif command == 'list':
            logger.info("Listing available snapshots")
            snapshots = list_snapshots()
            if snapshots:
                print("Available snapshots:")
                for s in snapshots:
                    if not s.startswith('diff_'):
                        print(f"  {s}")
            else:
                print("No snapshots found.")
        
        elif command == 'show':
            logger.info("Showing current database state")
            show_current_state()
        
        else:
            logger.error(f"Unknown command: {command}")
            print(f"Unknown command: {command}")
            print(__doc__)
            
    except Exception as e:
        logger.error(f"Command '{command}' failed: {e}")
        raise


if __name__ == '__main__':
    main()
