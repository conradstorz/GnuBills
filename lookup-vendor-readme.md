# Address Lookup GUI

## Overview

The Address Lookup GUI (`address_lookup_gui.py`) is a standalone tool for managing vendor addresses in the Bill Processor system. It provides a split-panel interface for browsing all vendors and editing their address information with automatic saving to the JSON database.

## Features

- **Multi-vendor session management** - Edit multiple vendors without closing the tool
- **Vendor list browser** - See all vendors at a glance with address indicators
- **Filter/search** - Quickly find vendors by name
- **Google Places integration** - Search for addresses using Google Places API
- **Multiple result handling** - Choose from multiple locations when searching
- **Auto-save** - All changes automatically saved to `vendor_database.json`
- **Read-only name protection** - Prevents accidental vendor name changes
- **New vendor creation** - Clean workflow for adding new vendors

## Launching the Tool

### From Bill Entry GUI

1. Select a vendor (bill) from the queue
2. Click the **"Address Lookup"** button in External Functions
3. The tool opens with that vendor pre-loaded

### Standalone

```bash
# Launch empty
uv run python src/address_lookup_gui.py

# Launch with specific vendor
uv run python src/address_lookup_gui.py "Vendor Name"
```

## User Interface

### Left Panel: Vendor List

- **All vendors** displayed alphabetically
- **📍 indicator** shows vendors with addresses
- **Filter box** to narrow down the list (type to search)
- **Click any vendor** to load their details

### Right Panel: Address Editor

**Vendor Name Section:**
- **Name field** - Read-only when editing existing vendors
- **Search Web button** - Look up address via Google Places
- **New Vendor button** - Create a new vendor entry

**Address Details Section:**
- Address Name
- Street Address
- Address Line 2
- City
- State
- ZIP Code
- Phone
- Email

**Search Results Section** (appears after web search):
- List of matching locations
- Shows distance if coordinates configured
- Double-click or click "Use Selected Result"

## Workflows

### Editing Existing Vendor

1. **Find vendor** - Scroll list or use filter box
2. **Click vendor** - Loads address details
3. **Edit fields** - Make any changes (name is read-only)
4. **Changes auto-save** - No need to click Save
5. **Click another vendor** - Continue editing

**Note:** Vendor name is read-only to prevent accidental changes to existing vendors.

### Creating New Vendor

1. **Click "New Vendor"** - Clears all fields
2. **Name field becomes editable** - Enter vendor name
3. **Fill in address** - Enter known details
4. **Search web** (optional) - Look up address if needed
5. **Changes auto-save** - Vendor appears in list
6. **Continue editing** - Click another vendor or create another

### Using Web Search

1. **Enter or load vendor name**
2. **Click "Search Web"** - Queries Google Places API
3. **Review results** - List shows all matching locations with distances
4. **Select correct location** - Click to highlight
5. **Click "Use Selected Result"** or double-click
6. **Fields populate** - Address, city, state, ZIP, phone auto-filled
7. **Auto-saves** - Changes saved to JSON immediately

## Address Indicators

In the vendor list:

- **📍** - Vendor has a street address (addr_line1)
- **Empty space** - Vendor exists but no address on file

## Auto-Save Behavior

All changes are automatically saved to `vendor_database.json` when:

- Any address field is modified
- A web search result is applied
- A new vendor name is entered

**No manual save required!**

## Field Mapping

The tool maps fields to the JSON structure:

| GUI Field | JSON Field |
|-----------|------------|
| Name | `display_name`, `search_name` |
| Address Name | `addr_name` |
| Street Address | `addr_line1` |
| Address Line 2 | `addr_line2` |
| City | `city` |
| State | `state` |
| ZIP Code | `zip` |
| Phone | `phone` |
| Email | `email` |

Additional fields stored from web search:
- `latitude`, `longitude` - GPS coordinates
- `place_id` - Google Place ID
- `address_source` - Set to "google" for web searches

## Google Places Search

### Requirements

- Google Places API key configured in `config.py`
- Internet connection

### Search Behavior

1. Searches for: `"Vendor Name" + "Default Locality"`
2. Filters by configured search radius (if CENTER_LAT/LON set)
3. Returns all matching results sorted by distance
4. Phone number lookup only occurs when result is selected (to save API calls)

### Result Display

Each result shows:
```
1. Business Name - Full Address (Distance in miles)
2. Business Name - Full Address (Distance in miles)
...
```

Example:
```
1. Home Depot - 123 Main St, Louisville, KY 40202 (2.3 mi)
2. Home Depot - 456 Oak Ave, Louisville, KY 40204 (5.1 mi)
```

## Tips & Best Practices

### Finding Vendors Quickly

Use the filter box:
- Type "home" to find "Home Depot", "Homemakers", etc.
- Filter is case-insensitive
- Searches display names only

### Creating New Vendors

1. Click "New Vendor" first
2. Enter name, then fill address
3. Or enter name, search web, select result
4. Vendor automatically appears in list

### Editing Multiple Vendors

- The tool is designed for batch editing
- Work through your vendor list systematically
- Filter can help you focus on specific vendors (e.g., missing addresses)

### When Web Search Returns No Results

1. Try a simpler search term (e.g., "Kroger" instead of "Kroger Grocery Store")
2. Try without location qualifier
3. Manually enter the address information

## Integration with Bill Processor

The Address Lookup GUI integrates with the bill processing workflow:

1. **Bill Entry GUI** → Click vendor → Click "Address Lookup" → Edit address
2. **Vendor Manager** → Reads from same `vendor_database.json`
3. **Vendor Sync** → Sync changes to GnuCash database
4. **Bill Processor** → Uses updated vendor data

Changes made in the Address Lookup GUI are immediately available to all other tools.

## Data Storage

All vendor data is stored in:
```
data/vendor_database.json
```

Structure:
```json
{
  "vendors": {
    "vendorkey": {
      "display_name": "Vendor Name",
      "search_name": "vendor name",
      "addr_name": "Vendor Name",
      "addr_line1": "123 Main St",
      "addr_line2": "Louisville, KY 40202",
      "city": "Louisville",
      "state": "KY",
      "zip": "40202",
      "phone": "(555) 123-4567",
      "email": "contact@vendor.com",
      "latitude": 38.2527,
      "longitude": -85.7585,
      "place_id": "ChIJ...",
      "address_source": "google"
    }
  },
  "aliases": {
    "alternate name": "vendorkey"
  }
}
```

## Keyboard Shortcuts

- **Double-click** vendor in list → Load vendor
- **Double-click** search result → Apply result
- **Filter box** → Type to search (updates in real-time)

## Troubleshooting

### "Google Places API key not configured"

**Solution:** Add API key to `config.py`:
```python
GOOGLE_PLACES_API_KEY = "your-api-key-here"
```

### Vendor doesn't appear after creating

**Possible causes:**
- Name field was left empty
- Check the filter box (clear it to see all vendors)
- Scroll to find the new vendor (alphabetically sorted)

### Can't edit vendor name

**This is by design:**
- Existing vendor names are read-only
- Prevents accidental changes to established vendors
- To rename: Create new vendor with correct name, copy address details

### Address fields don't clear

**Solution:**
- Click "New Vendor" button to clear all fields
- Or select a different vendor from the list

### Search returns wrong location

**Solutions:**
1. Select different result from the list
2. Manually edit the auto-populated fields
3. Try more specific search term

## Related Tools

- **Bill Entry GUI** - Main bill processing interface
- **Vendor Sync** - Sync vendors between JSON and GnuCash
- **Vendor Manager** - Programmatic vendor management
- **Address Lookup** - Core address lookup functions (used by this GUI)

## Command-Line Usage

```bash
# Launch standalone
uv run python src/address_lookup_gui.py

# Launch with vendor pre-loaded
uv run python src/address_lookup_gui.py "Home Depot"

# From bill_entry_gui (automatic when button clicked)
# Passes selected vendor as argument
```

## Configuration

Relevant config settings in `config.py`:

```python
# Google Places API
GOOGLE_PLACES_API_KEY = "your-key-here"

# Default search location
DEFAULT_LOCALITY = "Louisville, KY"

# Center coordinates for distance filtering
CENTER_LAT = 38.2527
CENTER_LON = -85.7585

# Search radius
SEARCH_RADIUS_MILES = 25
```

## Logging

Log file: `logs/address_lookup_gui.log`

- Console: INFO level (clean output)
- File: DEBUG level (detailed logging)

Check logs for:
- API call details
- Search results
- Auto-save confirmations
- Error details

---

*Last Updated: January 14, 2026*
