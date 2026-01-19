# Fuzzy Search Implementation

## Overview
Implemented automatic fuzzy matching for address lookups when initial searches return zero results.

## How It Works

When a business search returns no results, the system now automatically tries variations of the search term:

1. **Remove business suffixes**: Inc, LLC, Ltd, Corp, Store #123, etc.
2. **Try first two words**: For multi-word names (e.g., "Wendy's Old Fashioned" → "Wendy's Old")
3. **Try first word only**: The brand name (e.g., "Walmart Supercenter #1234" → "Walmart")

## Implementation Details

### New Function: `_generate_fuzzy_search_terms()`
- Located in `src/address_lookup.py`
- Generates search variations in order from most to least specific
- Uses regex to strip common suffixes:
  - Inc, LLC, Ltd, Corp, Corporation, Company, Co
  - Store #123, #123, trailing numbers
  - Supercenter, Center, Market

### Modified Functions
1. **`lookup_google_places()`**
   - When initial search returns 0 results, tries fuzzy terms
   - Stops at first successful match
   - Logs which fuzzy term succeeded

2. **`lookup_openstreetmap()`**
   - Same fuzzy fallback as Google
   - Respects rate limiting (1.1 second delay per request)
   - Logs which fuzzy term succeeded

## Examples

### Example 1: Store Number Suffix
- **Original**: "Kroger Store #567"
- **Fuzzy terms**: ["Kroger", "Kroger"]
- **Result**: Finds all Kroger locations in the area

### Example 2: Corporate Suffix
- **Original**: "McDonald's Corporation"
- **Fuzzy terms**: ["McDonald's"]
- **Result**: Finds McDonald's locations

### Example 3: Complex Name
- **Original**: "Wendy's Old Fashioned Hamburgers Inc"
- **Fuzzy terms**: ["Wendy's Old Fashioned Hamburgers", "Wendy's Old", "Wendy's"]
- **Result**: Tries progressively shorter forms until match found

## Benefits

1. **More forgiving searches**: Users don't need exact business names
2. **Better coverage**: Finds locations even with store numbers or corporate suffixes
3. **No user intervention**: Automatic fallback is transparent
4. **Maintains accuracy**: Only triggers when initial search fails
5. **Ordered attempts**: Most specific variations tried first

## Logging

The fuzzy search process is fully logged:
- "No results from Google Places, trying fuzzy matching"
- "Trying fuzzy search term: 'Walmart'"
- "Fuzzy search successful with term 'Walmart', found 15 results"

## Integration with GUI

Works seamlessly with `address_lookup_gui.py`:
- User enters full business name with suffixes
- If not found, fuzzy search activates automatically
- Results appear in the dropdown list
- User selects the correct location from expanded results
