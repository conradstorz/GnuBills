"""
Schema Discovery Module - Discovers and validates GnuCash database schema.

This module:
1. Discovers actual column names in GnuCash tables
2. Maps them to our expected names
3. Discovers required accounts (A/P, Expenses parent, etc.)
4. Validates setup and offers to fix issues
5. Persists schema info to gnucash_schema.json

All database operations should use this module to get correct column names.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from loguru import logger

import config


# Path to schema cache file
SCHEMA_FILE = config.PROJECT_ROOT / "data" / "gnucash_schema.json"


class SchemaDiscovery:
    """
    Discovers and caches GnuCash database schema information.
    
    Usage:
        schema = SchemaDiscovery()
        schema.discover()  # Reads database and updates cache
        
        # Get actual column name for our expected name
        actual_col = schema.get_column('entries', 'i_discount_num')
        
        # Check if database is properly set up
        if schema.is_valid():
            # proceed
    """
    
    def __init__(self, db_path: Path = None):
        """
        Initialize schema discovery.
        
        Args:
            db_path: Path to GnuCash database. Defaults to config.GNUCASH_DB_PATH
        """
        self.db_path = db_path or config.GNUCASH_DB_PATH
        self.schema = self._load_schema()
        logger.debug(f"SchemaDiscovery initialized for {self.db_path}")
    
    def _load_schema(self) -> Dict:
        """Load schema from JSON file or create default."""
        if SCHEMA_FILE.exists():
            try:
                with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                    logger.debug(f"Loaded schema from {SCHEMA_FILE}")
                    return schema
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load schema file: {e}. Creating new.")
        
        return self._create_default_schema()
    
    def _create_default_schema(self) -> Dict:
        """Create default schema structure."""
        return {
            "schema_version": 1,
            "last_validated": None,
            "database_path": None,
            "tables": {},
            "required_accounts": {
                "accounts_payable": {
                    "guid": None,
                    "name": None,
                    "account_type": "PAYABLE",
                    "can_create": True
                },
                "expense_parent": {
                    "guid": None,
                    "name": None,
                    "account_type": "EXPENSE",
                    "can_create": False
                },
                "liabilities_parent": {
                    "guid": None,
                    "name": None,
                    "account_type": "LIABILITY",
                    "can_create": False
                }
            },
            "required_commodities": {
                "usd": {
                    "guid": None,
                    "mnemonic": "USD",
                    "namespace": "CURRENCY"
                }
            },
            "validation_errors": [],
            "validation_warnings": []
        }
    
    def save(self):
        """Save schema to JSON file."""
        SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEMA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.schema, f, indent=2)
        logger.debug(f"Schema saved to {SCHEMA_FILE}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get read-only database connection."""
        db_path = Path(self.db_path)
        if not db_path.exists():
            raise FileNotFoundError(f"GnuCash database not found: {db_path}")
        
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    
    def discover(self) -> Dict:
        """
        Discover all schema information from the database.
        
        This is the main method that:
        1. Reads all table schemas
        2. Finds required accounts
        3. Validates setup
        4. Saves results
        
        Returns:
            Dict with discovery results including errors and warnings
        """
        logger.info(f"Starting schema discovery for {self.db_path}")
        
        self.schema['database_path'] = str(self.db_path)
        self.schema['last_validated'] = datetime.now().isoformat()
        self.schema['validation_errors'] = []
        self.schema['validation_warnings'] = []
        
        try:
            conn = self._get_connection()
            
            # Discover table schemas
            self._discover_tables(conn)
            
            # Discover required accounts
            self._discover_accounts(conn)
            
            # Discover required commodities
            self._discover_commodities(conn)
            
            conn.close()
            
        except FileNotFoundError as e:
            self.schema['validation_errors'].append(str(e))
            logger.error(f"Database not found: {e}")
        except sqlite3.Error as e:
            self.schema['validation_errors'].append(f"Database error: {e}")
            logger.error(f"Database error: {e}")
        
        # Save results
        self.save()
        
        # Log summary
        error_count = len(self.schema['validation_errors'])
        warning_count = len(self.schema['validation_warnings'])
        logger.info(f"Schema discovery complete: {error_count} errors, {warning_count} warnings")
        
        return {
            'valid': error_count == 0,
            'errors': self.schema['validation_errors'],
            'warnings': self.schema['validation_warnings'],
            'tables_found': list(self.schema.get('tables', {}).keys())
        }
    
    def _discover_tables(self, conn: sqlite3.Connection):
        """Discover schema for all tables we need."""
        tables_to_discover = [
            'vendors', 'accounts', 'invoices', 'entries',
            'transactions', 'splits', 'lots', 'commodities'
        ]
        
        for table_name in tables_to_discover:
            self._discover_table(conn, table_name)
    
    def _discover_table(self, conn: sqlite3.Connection, table_name: str):
        """Discover schema for a single table."""
        logger.debug(f"Discovering table: {table_name}")
        
        try:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = {}
            for row in cursor.fetchall():
                col_name = row['name']
                col_type = row['type']
                columns[col_name] = {
                    'type': col_type,
                    'nullable': not row['notnull'],
                    'primary_key': bool(row['pk'])
                }
            
            if columns:
                if 'tables' not in self.schema:
                    self.schema['tables'] = {}
                
                self.schema['tables'][table_name] = {
                    'columns': columns,
                    'column_count': len(columns)
                }
                logger.debug(f"  Found {len(columns)} columns in {table_name}")
            else:
                self.schema['validation_warnings'].append(
                    f"Table '{table_name}' not found or empty"
                )
                logger.warning(f"Table '{table_name}' not found or empty")
                
        except sqlite3.Error as e:
            self.schema['validation_warnings'].append(
                f"Error reading table '{table_name}': {e}"
            )
            logger.error(f"Error reading table '{table_name}': {e}")
    
    def _discover_accounts(self, conn: sqlite3.Connection):
        """Discover required accounts."""
        logger.debug("Discovering required accounts")
        
        # Find Accounts Payable
        cursor = conn.execute("""
            SELECT guid, name, account_type 
            FROM accounts 
            WHERE account_type = 'PAYABLE'
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.schema['required_accounts']['accounts_payable'] = {
                'guid': row['guid'],
                'name': row['name'],
                'account_type': row['account_type'],
                'can_create': True
            }
            logger.info(f"Found A/P account: {row['name']}")
        else:
            self.schema['required_accounts']['accounts_payable'] = {
                'guid': None,
                'name': None,
                'account_type': 'PAYABLE',
                'can_create': True
            }
            self.schema['validation_errors'].append(
                "No Accounts Payable account found (type: PAYABLE). "
                "This can be created automatically."
            )
            logger.warning("No A/P account found")
        
        # Find Expense parent (top-level EXPENSE account)
        cursor = conn.execute("""
            SELECT a.guid, a.name, a.account_type 
            FROM accounts a
            WHERE a.account_type = 'EXPENSE' 
            AND a.parent_guid IN (SELECT guid FROM accounts WHERE account_type = 'ROOT')
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.schema['required_accounts']['expense_parent'] = {
                'guid': row['guid'],
                'name': row['name'],
                'account_type': row['account_type'],
                'can_create': False
            }
            logger.info(f"Found Expense parent: {row['name']}")
        else:
            self.schema['validation_warnings'].append(
                "No top-level Expense account found. "
                "New expense accounts may not be created correctly."
            )
            logger.warning("No expense parent found")
        
        # Find Liabilities parent
        cursor = conn.execute("""
            SELECT a.guid, a.name, a.account_type 
            FROM accounts a
            WHERE a.account_type = 'LIABILITY' 
            AND a.parent_guid IN (SELECT guid FROM accounts WHERE account_type = 'ROOT')
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.schema['required_accounts']['liabilities_parent'] = {
                'guid': row['guid'],
                'name': row['name'],
                'account_type': row['account_type'],
                'can_create': False
            }
            logger.info(f"Found Liabilities parent: {row['name']}")
        else:
            self.schema['validation_errors'].append(
                "No top-level Liabilities account found. "
                "Cannot create A/P account without this."
            )
            logger.warning("No liabilities parent found")
    
    def _discover_commodities(self, conn: sqlite3.Connection):
        """Discover required commodities (currencies)."""
        logger.debug("Discovering required commodities")
        
        cursor = conn.execute("""
            SELECT guid, mnemonic, namespace 
            FROM commodities 
            WHERE mnemonic = 'USD' AND namespace = 'CURRENCY'
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            self.schema['required_commodities']['usd'] = {
                'guid': row['guid'],
                'mnemonic': row['mnemonic'],
                'namespace': row['namespace']
            }
            logger.info(f"Found USD currency: {row['guid']}")
        else:
            self.schema['validation_errors'].append(
                "USD currency not found in commodities table"
            )
            logger.error("USD currency not found")
    
    # =========================================================================
    # PUBLIC API - Use these methods for schema access
    # =========================================================================
    
    def is_valid(self) -> bool:
        """Check if schema is valid (no critical errors)."""
        return len(self.schema.get('validation_errors', [])) == 0
    
    def get_errors(self) -> List[str]:
        """Get list of validation errors."""
        return self.schema.get('validation_errors', [])
    
    def get_warnings(self) -> List[str]:
        """Get list of validation warnings."""
        return self.schema.get('validation_warnings', [])
    
    def has_column(self, table: str, column: str) -> bool:
        """Check if a table has a specific column."""
        tables = self.schema.get('tables', {})
        if table not in tables:
            return False
        columns = tables[table].get('columns', {})
        return column in columns
    
    def get_columns(self, table: str) -> List[str]:
        """Get list of columns for a table."""
        tables = self.schema.get('tables', {})
        if table not in tables:
            return []
        return list(tables[table].get('columns', {}).keys())
    
    def get_column(self, table: str, expected_name: str) -> Optional[str]:
        """
        Get actual column name for an expected name.
        
        Handles variations like i_disc_num vs i_discount_num by looking
        for close matches.
        
        Returns the actual column name or None if not found.
        """
        columns = self.get_columns(table)
        
        # Exact match
        if expected_name in columns:
            return expected_name
        
        # Try common variations
        variations = self._get_column_variations(expected_name)
        for var in variations:
            if var in columns:
                logger.debug(f"Column mapping: {expected_name} -> {var}")
                return var
        
        logger.warning(f"Column not found: {table}.{expected_name}")
        return None
    
    def _get_column_variations(self, name: str) -> List[str]:
        """Generate possible variations of a column name."""
        variations = [name]
        
        # Common GnuCash abbreviation patterns
        replacements = [
            ('_disc_', '_discount_'),
            ('_discount_', '_disc_'),
            ('_num', '_number'),
            ('_number', '_num'),
            ('_denom', '_denominator'),
            ('_denominator', '_denom'),
        ]
        
        for old, new in replacements:
            if old in name:
                variations.append(name.replace(old, new))
        
        return variations
    
    def get_account_guid(self, account_key: str) -> Optional[str]:
        """
        Get GUID for a required account.
        
        Args:
            account_key: One of 'accounts_payable', 'expense_parent', 'liabilities_parent'
        """
        accounts = self.schema.get('required_accounts', {})
        if account_key in accounts:
            return accounts[account_key].get('guid')
        return None
    
    def get_account_name(self, account_key: str) -> Optional[str]:
        """Get name for a required account."""
        accounts = self.schema.get('required_accounts', {})
        if account_key in accounts:
            return accounts[account_key].get('name')
        return None
    
    def get_usd_guid(self) -> Optional[str]:
        """Get GUID for USD currency."""
        commodities = self.schema.get('required_commodities', {})
        if 'usd' in commodities:
            return commodities['usd'].get('guid')
        return None
    
    def needs_ap_account(self) -> bool:
        """Check if A/P account needs to be created."""
        ap = self.schema.get('required_accounts', {}).get('accounts_payable', {})
        return ap.get('guid') is None
    
    def update_ap_account(self, guid: str, name: str):
        """Update A/P account info after creation."""
        self.schema['required_accounts']['accounts_payable']['guid'] = guid
        self.schema['required_accounts']['accounts_payable']['name'] = name
        
        # Remove error about missing A/P
        self.schema['validation_errors'] = [
            e for e in self.schema['validation_errors']
            if 'Accounts Payable' not in e
        ]
        
        self.save()
        logger.info(f"Updated A/P account: {name} ({guid})")
    
    def get_last_validated(self) -> Optional[str]:
        """Get timestamp of last validation."""
        return self.schema.get('last_validated')
    
    def needs_rediscovery(self) -> bool:
        """
        Check if schema needs to be rediscovered.
        
        Returns True if:
        - Never validated
        - Database path changed
        - Schema file is missing tables
        """
        if not self.schema.get('last_validated'):
            return True
        
        if str(self.db_path) != self.schema.get('database_path'):
            logger.info("Database path changed - rediscovery needed")
            return True
        
        if not self.schema.get('tables'):
            return True
        
        return False


# Global schema instance (lazy-loaded)
_schema_instance: Optional[SchemaDiscovery] = None


def get_schema() -> SchemaDiscovery:
    """Get the global schema discovery instance."""
    global _schema_instance
    if _schema_instance is None:
        _schema_instance = SchemaDiscovery()
    return _schema_instance


def discover_schema() -> Dict:
    """Discover schema and return results."""
    schema = get_schema()
    return schema.discover()


def validate_and_fix() -> Tuple[bool, List[str], List[str]]:
    """
    Validate schema and attempt to fix issues.
    
    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    schema = get_schema()
    
    # Always rediscover on startup
    result = schema.discover()
    
    return (
        result['valid'],
        result['errors'],
        result['warnings']
    )
