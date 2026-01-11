"""
Diagnostic script to find differences between manually-created and automation-created vendors.
This will help identify why GnuCash displays some vendor addresses but not others.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from src import config

DB_PATH = config.GNUCASH_DB_PATH

def get_all_table_names():
    """Get all table names in the database."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [row['name'] for row in cursor.fetchall()]

def get_vendor_guid(vendor_name):
    """Get GUID for a vendor by name."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT guid FROM vendors WHERE name = ?", (vendor_name,))
        row = cursor.fetchone()
        return row['guid'] if row else None

def get_all_rows_for_guid(guid, table_name):
    """Get all rows from a table that reference a specific GUID in any column."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = [col['name'] for col in cursor.fetchall()]
        
        # Build query to search all columns for the GUID
        where_clauses = [f"{col} = ?" for col in columns]
        query = f"SELECT * FROM {table_name} WHERE " + " OR ".join(where_clauses)
        params = [guid] * len(columns)
        
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def compare_vendors(manual_vendor, auto_vendor):
    """Compare two vendors across all database tables."""
    print(f"\n{'='*80}")
    print(f"COMPARING VENDORS:")
    print(f"  Manual (working): {manual_vendor}")
    print(f"  Automated (not working): {auto_vendor}")
    print(f"{'='*80}\n")
    
    manual_guid = get_vendor_guid(manual_vendor)
    auto_guid = get_vendor_guid(auto_vendor)
    
    if not manual_guid:
        print(f"ERROR: Could not find manual vendor '{manual_vendor}'")
        return
    if not auto_guid:
        print(f"ERROR: Could not find automated vendor '{auto_vendor}'")
        return
    
    print(f"Manual vendor GUID: {manual_guid}")
    print(f"Auto vendor GUID:   {auto_guid}\n")
    
    tables = get_all_table_names()
    print(f"Checking {len(tables)} tables...\n")
    
    differences = []
    
    for table in tables:
        try:
            manual_rows = get_all_rows_for_guid(manual_guid, table)
            auto_rows = get_all_rows_for_guid(auto_guid, table)
            
            # Compare row counts
            if len(manual_rows) != len(auto_rows):
                differences.append({
                    'table': table,
                    'issue': 'row_count_mismatch',
                    'manual_count': len(manual_rows),
                    'auto_count': len(auto_rows),
                    'manual_rows': manual_rows,
                    'auto_rows': auto_rows
                })
                print(f"⚠️  {table}: Row count mismatch (manual={len(manual_rows)}, auto={len(auto_rows)})")
                
            # Compare actual data
            elif len(manual_rows) > 0:
                for i, (m_row, a_row) in enumerate(zip(manual_rows, auto_rows)):
                    field_diffs = {}
                    for key in m_row.keys():
                        if m_row.get(key) != a_row.get(key):
                            field_diffs[key] = {
                                'manual': m_row.get(key),
                                'auto': a_row.get(key)
                            }
                    
                    if field_diffs:
                        differences.append({
                            'table': table,
                            'issue': 'field_value_mismatch',
                            'row_index': i,
                            'differences': field_diffs
                        })
                        print(f"⚠️  {table} row {i}: Field differences: {list(field_diffs.keys())}")
                        
        except Exception as e:
            print(f"❌ Error checking table {table}: {e}")
    
    # Print detailed differences
    print(f"\n{'='*80}")
    print(f"DETAILED DIFFERENCES:")
    print(f"{'='*80}\n")
    
    if not differences:
        print("✅ No differences found between vendors!")
    else:
        for diff in differences:
            print(f"\nTable: {diff['table']}")
            print(f"Issue: {diff['issue']}")
            
            if diff['issue'] == 'row_count_mismatch':
                print(f"  Manual has {diff['manual_count']} rows, Auto has {diff['auto_count']} rows")
                print(f"\n  Manual rows:")
                for row in diff['manual_rows']:
                    print(f"    {row}")
                print(f"\n  Auto rows:")
                for row in diff['auto_rows']:
                    print(f"    {row}")
                    
            elif diff['issue'] == 'field_value_mismatch':
                print(f"  Row {diff['row_index']} differences:")
                for field, values in diff['differences'].items():
                    print(f"    {field}:")
                    print(f"      Manual: {values['manual']}")
                    print(f"      Auto:   {values['auto']}")
    
    # Save report
    report_path = Path('data') / f'vendor_comparison_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(report_path, 'w') as f:
        json.dump({
            'manual_vendor': manual_vendor,
            'auto_vendor': auto_vendor,
            'manual_guid': manual_guid,
            'auto_guid': auto_guid,
            'differences': differences
        }, f, indent=2)
    
    print(f"\n{'='*80}")
    print(f"Report saved to: {report_path}")
    print(f"{'='*80}\n")

def main():
    # Compare a working manual vendor with a non-working automated vendor
    # Both should have no bills to eliminate that variable
    manual_vendor = "Vic's Cafe"  # Manual, shows address in GnuCash
    auto_vendor = "Versailles Brewing Company"  # Automated, doesn't show address in GnuCash
    
    compare_vendors(manual_vendor, auto_vendor)

if __name__ == '__main__':
    main()
