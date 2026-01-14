"""
Standalone Vendor Sync Utility
Syncs vendors from vendor_database.json to GnuCash database.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
from gnucash_db import get_connection, generate_guid, get_usd_guid
from schema_discovery import SchemaDiscovery


class VendorSyncUtility:
    """Utility to sync vendors from JSON database to GnuCash."""
    
    def __init__(self):
        # Fix: Use the correct path structure from your project
        project_root = Path(__file__).parent.parent  # Go up from src/ to project root
        data_dir = project_root / "data"
        self.vendor_db_path = data_dir / "vendor_database.json"
        
        self.vendors_data = {}
        self.schema = None
        self.stats = {
            'total': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }
        
        # Ensure data directory exists
        data_dir.mkdir(exist_ok=True)
    
    def load_vendor_database(self) -> bool:
        """Load vendor database from JSON file."""
        try:
            if not self.vendor_db_path.exists():
                print(f"❌ Vendor database not found: {self.vendor_db_path}")
                print(f"Expected location: {self.vendor_db_path.absolute()}")
                return False
            
            with open(self.vendor_db_path, 'r') as f:
                data = json.load(f)
                self.vendors_data = data.get('vendors', {})
            
            self.stats['total'] = len(self.vendors_data)
            print(f"✅ Loaded {self.stats['total']} vendors from database")
            
            if self.stats['total'] == 0:
                print("⚠️  No vendors found in database")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ Failed to load vendor database: {e}")
            return False
    
    def discover_schema(self) -> bool:
        """Discover GnuCash database schema."""
        try:
            print("🔍 Discovering GnuCash database schema...")
            
            # Check if GnuCash database path is configured
            if not hasattr(config, 'GNUCASH_DB_PATH'):
                print("❌ GNUCASH_DB_PATH not configured in config.py")
                return False
            
            gnucash_path = Path(config.GNUCASH_DB_PATH)
            if not gnucash_path.exists():
                print(f"❌ GnuCash database not found: {gnucash_path}")
                return False
            
            print(f"📍 Using GnuCash database: {gnucash_path}")
            
            # Create fresh schema discovery instance
            self.schema = SchemaDiscovery()
            
            # Ensure schema is discovered/loaded
            if not hasattr(self.schema, 'schema') or not self.schema.schema:
                print("🔄 Running schema discovery...")
                result = self.schema.discover()
                if not result.passed:
                    print(f"❌ Schema discovery failed: {result.summary}")
                    return False
            
            # Check if vendors table exists and get structure
            if not self.schema.has_table('vendors'):
                print("❌ Vendors table not found in GnuCash database")
                return False
                
            vendor_columns = self.schema.get_columns('vendors')
            print(f"✅ Found vendors table with {len(vendor_columns)} columns")
            
            # Log available address columns
            addr_columns = [col for col in vendor_columns if col.startswith('addr_')]
            print(f"📍 Address columns available: {addr_columns}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to discover schema: {e}")
            logger.error(f"Schema discovery failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def build_vendor_insert(self) -> Tuple[str, List[str]]:
        """Build INSERT statement based on discovered schema."""
        try:
            sql, columns = self.schema.build_vendor_insert_statement()
            print(f"✅ Built INSERT statement with {len(columns)} columns")
            
            # Show which address columns will be populated
            addr_columns = [col for col in columns if col.startswith('addr_')]
            for col in addr_columns:
                print(f"  📍 Will populate address field: {col}")
            
            return sql, columns
        except Exception as e:
            print(f"❌ Failed to build INSERT statement: {e}")
            raise
    
    def vendor_exists_in_gnucash(self, display_name: str) -> Optional[Dict]:
        """Check if vendor already exists in GnuCash."""
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    "SELECT guid, id, name FROM vendors WHERE name = ?",
                    (display_name,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'guid': row['guid'],
                        'id': row['id'],
                        'name': row['name']
                    }
                return None
        except Exception as e:
            logger.error(f"Error checking vendor existence: {e}")
            return None
    
    def get_next_vendor_id(self) -> str:
        """Get next available vendor ID."""
        with get_connection() as conn:
            cursor = conn.execute("SELECT MAX(CAST(id AS INTEGER)) FROM vendors")
            max_id = cursor.fetchone()[0] or 0
            return f"{max_id + 1:06d}"
    
    def create_vendor_in_gnucash(self, vendor_key: str, vendor_data: Dict) -> bool:
        """Create a single vendor in GnuCash."""
        display_name = vendor_data.get('display_name', vendor_key)
        
        try:
            # Build INSERT statement
            insert_sql, column_names = self.build_vendor_insert()
            
            # Prepare values
            vendor_guid = generate_guid()
            vendor_id = self.get_next_vendor_id()
            usd_guid = get_usd_guid()
            
            # Map JSON data to database columns with detailed logging
            values_map = {
                'guid': vendor_guid,
                'id': vendor_id,
                'name': display_name,
                'currency': usd_guid,
                'active': 1,
                'notes': '',
                'addr_name': vendor_data.get('addr_name', ''),
                'addr_addr1': vendor_data.get('addr_line1', ''),
                'addr_addr2': vendor_data.get('addr_line2', ''),
                'addr_phone': vendor_data.get('phone', ''),
                'addr_email': vendor_data.get('addr_email', ''),
                'tax_override': 0,
                'tax_inc': '',
                'tax_table': ''
            }
            
            # Log address data being inserted
            print(f"    📍 Address data:")
            print(f"      addr_name: '{values_map.get('addr_name', '')}'")
            print(f"      addr_addr1: '{values_map.get('addr_addr1', '')}'")
            print(f"      addr_addr2: '{values_map.get('addr_addr2', '')}'")
            print(f"      addr_phone: '{values_map.get('addr_phone', '')}'")
            
            # Build ordered values list
            insert_values = [values_map.get(col, '') for col in column_names]
            
            # Execute INSERT
            with get_connection(readonly=False) as conn:
                conn.execute(insert_sql, insert_values)
                conn.commit()
                
                # Verify the insert worked
                cursor = conn.execute(
                    "SELECT addr_name, addr_addr1, addr_addr2, addr_phone FROM vendors WHERE guid = ?",
                    (vendor_guid,)
                )
                row = cursor.fetchone()
                if row:
                    print(f"    ✅ Verified address saved:")
                    print(f"      addr_name: '{row['addr_name'] or '(empty)'}'")
                    print(f"      addr_addr1: '{row['addr_addr1'] or '(empty)'}'")
                    print(f"      addr_addr2: '{row['addr_addr2'] or '(empty)'}'")
                    print(f"      addr_phone: '{row['addr_phone'] or '(empty)'}'")
            
            # Update JSON database with GnuCash IDs
            vendor_data['gnucash_guid'] = vendor_guid
            vendor_data['gnucash_id'] = vendor_id
            
            print(f"  ✅ Created: {display_name} (ID: {vendor_id})")
            self.stats['created'] += 1
            return True
            
        except Exception as e:
            print(f"  ❌ Failed to create {display_name}: {e}")
            logger.error(f"Failed to create vendor {display_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
            return False
    
    def update_vendor_ids(self, vendor_key: str, gnucash_data: Dict) -> bool:
        """Update JSON database with existing GnuCash IDs."""
        try:
            self.vendors_data[vendor_key]['gnucash_guid'] = gnucash_data['guid']
            self.vendors_data[vendor_key]['gnucash_id'] = gnucash_data['id']
            self.stats['updated'] += 1
            return True
        except Exception as e:
            logger.error(f"Failed to update vendor IDs: {e}")
            return False
    
    def save_vendor_database(self) -> bool:
        """Save updated vendor database to JSON file."""
        try:
            # Preserve existing aliases
            existing_data = {}
            if self.vendor_db_path.exists():
                with open(self.vendor_db_path, 'r') as f:
                    existing_data = json.load(f)
            
            data = {
                'vendors': self.vendors_data, 
                'aliases': existing_data.get('aliases', {})
            }
            
            with open(self.vendor_db_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"💾 Updated vendor database saved to: {self.vendor_db_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to save vendor database: {e}")
            return False
    
    def sync_all_vendors(self, force_recreate: bool = False, dry_run: bool = False) -> bool:
        """Sync all vendors from JSON to GnuCash."""
        print(f"\n{'='*60}")
        print(f"VENDOR SYNC UTILITY")
        print(f"{'='*60}")
        print(f"Source: {self.vendor_db_path}")
        print(f"Target: {getattr(config, 'GNUCASH_DB_PATH', 'Not configured')}")
        print(f"Force recreate: {force_recreate}")
        print(f"Dry run: {dry_run}")
        print(f"{'='*60}\n")
        
        if not self.load_vendor_database():
            return False
        
        if not self.discover_schema():
            return False
        
        if dry_run:
            print(f"🔍 DRY RUN - Would sync {self.stats['total']} vendors")
            for vendor_key, vendor_data in self.vendors_data.items():
                display_name = vendor_data.get('display_name', vendor_key)
                existing = self.vendor_exists_in_gnucash(display_name)
                status = "EXISTS" if existing else "CREATE"
                print(f"  {display_name} -> {status}")
            return True
        
        print(f"🚀 Starting sync of {self.stats['total']} vendors...\n")
        
        for vendor_key, vendor_data in self.vendors_data.items():
            display_name = vendor_data.get('display_name', vendor_key)
            print(f"Processing: {display_name}")
            
            # Check if vendor already exists
            existing = self.vendor_exists_in_gnucash(display_name)
            
            if existing and not force_recreate:
                print(f"  📍 Already exists (ID: {existing['id']})")
                # Update JSON with GnuCash IDs if missing
                if not vendor_data.get('gnucash_guid'):
                    self.update_vendor_ids(vendor_key, existing)
                    print(f"  📝 Updated JSON with GnuCash IDs")
                else:
                    self.stats['skipped'] += 1
            elif existing and force_recreate:
                print(f"  🔄 Force recreate not implemented (would delete existing)")
                self.stats['skipped'] += 1
            else:
                # Create new vendor
                self.create_vendor_in_gnucash(vendor_key, vendor_data)
        
        print(f"\n{'='*60}")
        print(f"SYNC COMPLETE")
        print(f"{'='*60}")
        print(f"Total vendors: {self.stats['total']}")
        print(f"Created: {self.stats['created']}")
        print(f"Updated: {self.stats['updated']}")
        print(f"Skipped: {self.stats['skipped']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"{'='*60}\n")
        
        # Save updated JSON database
        if self.stats['created'] > 0 or self.stats['updated'] > 0:
            self.save_vendor_database()
        
        return self.stats['errors'] == 0


def main():
    """Command-line interface for vendor sync."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync vendors from JSON to GnuCash')
    parser.add_argument('--force', action='store_true', 
                       help='Force recreate existing vendors')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--list', action='store_true',
                       help='List vendors in JSON database')
    
    args = parser.parse_args()
    
    sync_util = VendorSyncUtility()
    
    if args.list:
        if sync_util.load_vendor_database():
            print(f"\nVendors in database ({len(sync_util.vendors_data)}):")
            print("="*50)
            for key, data in sync_util.vendors_data.items():
                name = data.get('display_name', key)
                has_addr = bool(data.get('addr_line1'))
                gnucash_id = data.get('gnucash_id') or 'Not synced'
                print(f"{name:<30} | {gnucash_id:<10} | {'📍' if has_addr else '❌'}")
        return
    
    # Configure logging
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(log_dir / "vendor_sync.log", rotation="5 MB", retention="30 days")
    
    try:
        success = sync_util.sync_all_vendors(
            force_recreate=args.force, 
            dry_run=args.dry_run
        )
        
        if success:
            print("🎉 Vendor sync completed successfully!")
            sys.exit(0)
        else:
            print("💥 Vendor sync completed with errors")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️  Vendor sync cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Fatal error during sync: {e}")
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()