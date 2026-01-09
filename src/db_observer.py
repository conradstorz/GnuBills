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

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
import config

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
    db_path = Path(config.GNUCASH_DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_table_schema(conn: sqlite3.Connection, table: str) -> List[str]:
    """Get column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return [row['name'] for row in cursor]


def get_all_tables(conn: sqlite3.Connection) -> List[str]:
    """Get list of all tables in the database."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row['name'] for row in cursor]


def fetch_table_data(conn: sqlite3.Connection, table: str) -> List[Dict]:
    """Fetch data from a table.
    
    Captures ALL rows for most tables.
    For very large tables (slots, splits, transactions), captures recent rows.
    """
    # Skip sqlite internal tables
    if table.startswith('sqlite_'):
        return []
    
    # Determine if we should limit rows
    if table in ALWAYS_FULL_TABLES:
        limit = None
    elif table in LARGE_TABLES:
        limit = LARGE_TABLES[table]
    else:
        limit = None  # Get all rows by default
    
    try:
        if limit:
            cursor = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT {limit}")
        else:
            cursor = conn.execute(f"SELECT * FROM {table}")
        
        rows = []
        for row in cursor:
            rows.append({key: row[key] for key in row.keys()})
        return rows
    except Exception as e:
        print(f"Warning: Could not fetch {table}: {e}")
        return []


def capture_snapshot() -> Dict[str, Any]:
    """Capture current database state - ALL tables."""
    conn = get_connection()
    
    # Get all tables dynamically
    all_tables = get_all_tables(conn)
    
    snapshot = {
        'timestamp': datetime.now().isoformat(),
        'database': str(config.GNUCASH_DB_PATH),
        'tables': {}
    }
    
    for table in all_tables:
        try:
            data = fetch_table_data(conn, table)
            snapshot['tables'][table] = {
                'count': len(data),
                'rows': data
            }
        except Exception as e:
            snapshot['tables'][table] = {
                'error': str(e),
                'count': 0,
                'rows': []
            }
    
    conn.close()
    return snapshot


def save_snapshot(snapshot: Dict, label: str) -> Path:
    """Save a snapshot to disk."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    filename = f"{label}.json"
    filepath = SNAPSHOTS_DIR / filename
    
    with open(filepath, 'w') as f:
        json.dump(snapshot, f, indent=2, default=str)
    
    return filepath


def load_snapshot(label: str) -> Dict:
    """Load a snapshot from disk."""
    filepath = SNAPSHOTS_DIR / f"{label}.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Snapshot not found: {filepath}")
    
    with open(filepath) as f:
        return json.load(f)


def list_snapshots() -> List[str]:
    """List all available snapshots."""
    if not SNAPSHOTS_DIR.exists():
        return []
    return sorted([f.stem for f in SNAPSHOTS_DIR.glob("*.json")])


def diff_snapshots(label1: str, label2: str) -> Dict[str, Any]:
    """Compare two snapshots and return differences."""
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
    
    for table in sorted(all_tables):
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
    
    return diff


def print_snapshot_summary(snapshot: Dict):
    """Print a summary of a snapshot."""
    print(f"\n{'='*60}")
    print(f"Snapshot: {snapshot.get('timestamp', 'unknown')}")
    print(f"Database: {snapshot.get('database', 'unknown')}")
    print(f"{'='*60}")
    
    for table, data in snapshot['tables'].items():
        if 'error' in data:
            print(f"\n{table}: ERROR - {data['error']}")
        else:
            print(f"\n{table}: {data['count']} rows")
            
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
    print(f"\n{'='*60}")
    print(f"DIFF: {diff['from']} -> {diff['to']}")
    print(f"From: {diff['from_timestamp']}")
    print(f"To:   {diff['to_timestamp']}")
    print(f"{'='*60}")
    
    if not diff['changes']:
        print("\nNo changes detected.")
        return
    
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
    snapshot = capture_snapshot()
    print_snapshot_summary(snapshot)
    
    # Also show some detailed info
    conn = get_connection()
    
    print(f"\n{'='*60}")
    print("DETAILED VIEW - VENDOR BILLS")
    print(f"{'='*60}")
    
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
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == 'snapshot':
        if len(sys.argv) < 3:
            print("Usage: python db_observer.py snapshot <label>")
            return
        label = sys.argv[2]
        print(f"Capturing snapshot '{label}'...")
        snapshot = capture_snapshot()
        filepath = save_snapshot(snapshot, label)
        print(f"Saved to: {filepath}")
        print_snapshot_summary(snapshot)
    
    elif command == 'diff':
        if len(sys.argv) < 4:
            print("Usage: python db_observer.py diff <label1> <label2>")
            return
        label1 = sys.argv[2]
        label2 = sys.argv[3]
        print(f"Comparing '{label1}' to '{label2}'...")
        diff = diff_snapshots(label1, label2)
        print_diff(diff)
        
        # Also save the diff
        diff_path = SNAPSHOTS_DIR / f"diff_{label1}_to_{label2}.json"
        with open(diff_path, 'w') as f:
            json.dump(diff, f, indent=2, default=str)
        print(f"\nDiff saved to: {diff_path}")
    
    elif command == 'list':
        snapshots = list_snapshots()
        if snapshots:
            print("Available snapshots:")
            for s in snapshots:
                if not s.startswith('diff_'):
                    print(f"  {s}")
        else:
            print("No snapshots found.")
    
    elif command == 'show':
        show_current_state()
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == '__main__':
    main()
