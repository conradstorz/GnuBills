"""
Bill Processor Configuration
Edit these settings for your environment.
"""

import os
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

# Project root directory
PROJECT_ROOT = Path(r"D:\Users\Conrad\Documents\GnuCash\bill_processor")

# GnuCash database file (SQLite format)
# Change this to your actual .gnucash file
GNUCASH_DB_PATH = Path(r"D:\Users\Conrad\Documents\GnuCash\gnuCash414\CFSIV_Sqlite3_database.gnucash")

# Vendor database JSON file
VENDOR_DB_PATH = PROJECT_ROOT / "data" / "vendor_database.json"
VENDOR_DATABASE_PATH = VENDOR_DB_PATH  # Alias for compatibility

# Input file for bills to process
BILLS_INPUT_PATH = PROJECT_ROOT / "data" / "bills_to_process.txt"
DEFAULT_INPUT_FILE = BILLS_INPUT_PATH  # Alias for compatibility

# =============================================================================
# LOCALITY SETTINGS (for address lookup)
# =============================================================================

# Your city and state - used to narrow address searches
LOCALITY_CITY = "Louisville"
LOCALITY_STATE = "KY"
LOCALITY_COUNTRY = "US"

# Search radius in miles for address lookups
SEARCH_RADIUS_MILES = 100

# Your approximate coordinates (Louisville, KY downtown)
# Used for distance calculations and "pick closest" logic
HOME_LATITUDE = 38.2527
HOME_LONGITUDE = -85.7585
CENTER_LAT = HOME_LATITUDE  # Alias for address_lookup
CENTER_LON = HOME_LONGITUDE  # Alias for address_lookup

# Default locality string for searches
DEFAULT_LOCALITY = f"{LOCALITY_CITY}, {LOCALITY_STATE}"

# =============================================================================
# GNUCASH SETTINGS
# =============================================================================

# Parent account for new expense accounts (created under this)
# New accounts will be named: cmsnpd_<vendor_name>
DEFAULT_EXPENSE_PARENT = "Expenses root"

# Expense account prefix
EXPENSE_ACCOUNT_PREFIX = "cmsnpd_"

# Accounts Payable account path
ACCOUNTS_PAYABLE_PATH = "Liabilities:Accounts Payable"

# Vendor ID prefix and format
VENDOR_ID_PREFIX = "V"
VENDOR_ID_FORMAT = "{prefix}{num:04d}"  # V0001, V0002, etc.

# Bill ID prefix and format  
BILL_ID_PREFIX = "B-"
BILL_ID_FORMAT = "{prefix}{num:04d}"  # B-0001, B-0002, etc.

# Default memo when none provided
DEFAULT_MEMO = "no memo"

# Currency
DEFAULT_CURRENCY = "USD"

# =============================================================================
# ADDRESS LOOKUP API SETTINGS
# =============================================================================

# Google Places API (most accurate, requires API key)
# Get a key at: https://console.cloud.google.com/
GOOGLE_PLACES_API_KEY = ""  # Leave empty to skip Google

# OpenStreetMap Nominatim (free, no key needed)
# Be respectful of usage limits: max 1 request per second
USE_OPENSTREETMAP = True

# User agent for OSM requests (required by their terms)
OSM_USER_AGENT = "GnuCashBillProcessor/1.0 (personal use)"

# =============================================================================
# FUZZY MATCHING SETTINGS
# =============================================================================

# Minimum score (0-100) to consider a fuzzy match valid
FUZZY_MATCH_THRESHOLD = 70

# If two vendors both score above this, flag as ambiguous
FUZZY_AMBIGUOUS_THRESHOLD = 85

# =============================================================================
# DISPLAY SETTINGS
# =============================================================================

# Terminal width for formatting
TERMINAL_WIDTH = 80

# =============================================================================
# LOGGING
# =============================================================================

# Log file path (None to disable file logging)
LOG_FILE_PATH = PROJECT_ROOT / "logs" / "bill_processor.log"
LOG_FILE = LOG_FILE_PATH  # Alias for compatibility

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL = "INFO"
