"""
Address lookup via Google Places API and OpenStreetMap/Nominatim.
"""

import time
from typing import Optional, Dict, List, Tuple
import requests
from loguru import logger

import config
from utils import calculate_distance_miles


class AddressLookupError(Exception):
    """Raised when address lookup fails."""
    pass


def lookup_google_places(business_name: str, locality: str = None) -> Optional[Dict]:
    """
    Search for a business using Google Places API.
    
    Returns dict with:
        - name: Business name from Google
        - formatted_address: Full address string
        - addr_line1: Street address
        - addr_line2: City, State ZIP
        - phone: Phone number (if available)
        - lat, lng: Coordinates
        - place_id: Google place ID
    
    Returns None if not found or API error.
    """
    if not config.GOOGLE_PLACES_API_KEY:
        logger.warning("Google Places API key not configured")
        return None
    
    if locality is None:
        locality = config.DEFAULT_LOCALITY
    
    # Build search query
    query = f"{business_name} {locality}"
    
    try:
        # Text Search API
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            'query': query,
            'key': config.GOOGLE_PLACES_API_KEY,
            'type': 'establishment'
        }
        
        # Add location bias if configured
        if config.CENTER_LAT and config.CENTER_LON:
            params['location'] = f"{config.CENTER_LAT},{config.CENTER_LON}"
            params['radius'] = config.SEARCH_RADIUS_MILES * 1609  # Convert to meters
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            logger.debug(f"Google Places API status: {data.get('status')}")
            return None
        
        results = data.get('results', [])
        if not results:
            return None
        
        # Filter by distance if we have center coordinates
        if config.CENTER_LAT and config.CENTER_LON:
            filtered = []
            for r in results:
                loc = r.get('geometry', {}).get('location', {})
                if loc:
                    dist = calculate_distance_miles(
                        config.CENTER_LAT, config.CENTER_LON,
                        loc.get('lat', 0), loc.get('lng', 0)
                    )
                    if dist <= config.SEARCH_RADIUS_MILES:
                        r['_distance'] = dist
                        filtered.append(r)
            results = sorted(filtered, key=lambda x: x.get('_distance', 999))
        
        if not results:
            return None
        
        best = results[0]
        
        # Get place details for phone number
        phone = None
        if config.GOOGLE_PLACES_API_KEY:
            phone = _get_google_place_phone(best.get('place_id'))
        
        # Parse address
        formatted_addr = best.get('formatted_address', '')
        addr_parts = _parse_formatted_address(formatted_addr)
        
        return {
            'name': best.get('name'),
            'formatted_address': formatted_addr,
            'addr_line1': addr_parts.get('line1', ''),
            'addr_line2': addr_parts.get('line2', ''),
            'phone': phone,
            'lat': best.get('geometry', {}).get('location', {}).get('lat'),
            'lng': best.get('geometry', {}).get('location', {}).get('lng'),
            'place_id': best.get('place_id'),
            'source': 'google'
        }
        
    except requests.RequestException as e:
        logger.error(f"Google Places API error: {e}")
        return None


def _get_google_place_phone(place_id: str) -> Optional[str]:
    """Get phone number from Google Place Details API."""
    if not place_id or not config.GOOGLE_PLACES_API_KEY:
        return None
    
    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'fields': 'formatted_phone_number',
            'key': config.GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return data.get('result', {}).get('formatted_phone_number')
        
    except requests.RequestException:
        return None


def lookup_openstreetmap(business_name: str, locality: str = None) -> Optional[Dict]:
    """
    Search for a business using OpenStreetMap Nominatim API.
    
    This is the free fallback option.
    
    Returns same structure as lookup_google_places.
    """
    if locality is None:
        locality = config.DEFAULT_LOCALITY
    
    query = f"{business_name} {locality}"
    
    try:
        # Nominatim requires a User-Agent
        headers = {
            'User-Agent': 'GnuCash-Bill-Processor/1.0'
        }
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'addressdetails': 1,
            'limit': 5
        }
        
        # Add bounding box if configured
        if config.CENTER_LAT and config.CENTER_LON:
            # Create bounding box (rough approximation)
            # 1 degree lat ≈ 69 miles, 1 degree lon varies
            lat_delta = config.SEARCH_RADIUS_MILES / 69
            lon_delta = config.SEARCH_RADIUS_MILES / 54  # Approximate for ~38° latitude
            
            params['bounded'] = 1
            params['viewbox'] = (
                f"{config.CENTER_LON - lon_delta},{config.CENTER_LAT + lat_delta},"
                f"{config.CENTER_LON + lon_delta},{config.CENTER_LAT - lat_delta}"
            )
        
        # Rate limiting - Nominatim requires max 1 request/second
        time.sleep(1.1)
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json()
        
        if not results:
            return None
        
        # Filter by distance
        if config.CENTER_LAT and config.CENTER_LON:
            filtered = []
            for r in results:
                lat = float(r.get('lat', 0))
                lon = float(r.get('lon', 0))
                dist = calculate_distance_miles(
                    config.CENTER_LAT, config.CENTER_LON, lat, lon
                )
                if dist <= config.SEARCH_RADIUS_MILES:
                    r['_distance'] = dist
                    filtered.append(r)
            results = sorted(filtered, key=lambda x: x.get('_distance', 999))
        
        if not results:
            return None
        
        best = results[0]
        address = best.get('address', {})
        
        # Build address lines
        house_number = address.get('house_number', '')
        road = address.get('road', '')
        line1 = f"{house_number} {road}".strip()
        
        city = address.get('city') or address.get('town') or address.get('village', '')
        state = address.get('state', '')
        postcode = address.get('postcode', '')
        
        line2 = f"{city}, {state} {postcode}".strip()
        
        return {
            'name': best.get('display_name', '').split(',')[0],
            'formatted_address': best.get('display_name', ''),
            'addr_line1': line1,
            'addr_line2': line2,
            'phone': None,  # Nominatim doesn't provide phone
            'lat': float(best.get('lat', 0)),
            'lng': float(best.get('lon', 0)),
            'place_id': best.get('place_id'),
            'source': 'openstreetmap'
        }
        
    except requests.RequestException as e:
        logger.error(f"OpenStreetMap API error: {e}")
        return None


def lookup_address(business_name: str, locality: str = None) -> Optional[Dict]:
    """
    Look up business address using configured sources.
    
    Tries Google Places first (if API key configured), falls back to OpenStreetMap.
    
    Returns address dict or None if not found.
    """
    # Try Google first if configured
    if config.GOOGLE_PLACES_API_KEY:
        result = lookup_google_places(business_name, locality)
        if result:
            logger.info(f"Found address via Google Places: {result.get('formatted_address')}")
            return result
    
    # Fall back to OpenStreetMap
    result = lookup_openstreetmap(business_name, locality)
    if result:
        logger.info(f"Found address via OpenStreetMap: {result.get('formatted_address')}")
        return result
    
    logger.warning(f"No address found for: {business_name}")
    return None


def _parse_formatted_address(address: str) -> Dict[str, str]:
    """
    Parse a formatted address string into lines.
    
    "123 Main St, Louisville, KY 40201, USA" ->
    {
        'line1': '123 Main St',
        'line2': 'Louisville, KY 40201'
    }
    """
    if not address:
        return {'line1': '', 'line2': ''}
    
    # Remove country suffix if present
    parts = [p.strip() for p in address.split(',')]
    
    # Remove "USA", "US", "United States" from end
    if parts and parts[-1].lower() in ('usa', 'us', 'united states'):
        parts = parts[:-1]
    
    if len(parts) >= 3:
        # Format: "123 Main St, City, State ZIP"
        line1 = parts[0]
        line2 = ', '.join(parts[1:])
    elif len(parts) == 2:
        line1 = parts[0]
        line2 = parts[1]
    else:
        line1 = address
        line2 = ''
    
    return {'line1': line1, 'line2': line2}


def prompt_manual_address() -> Dict[str, str]:
    """
    Prompt user to enter address manually.
    
    Returns dict with addr_name, addr_line1, addr_line2, phone.
    """
    print("\n--- Manual Address Entry ---")
    print("Enter address details (press Enter to skip a field):\n")
    
    addr_name = input("Business Name for Address: ").strip()
    addr_line1 = input("Address Line 1 (street): ").strip()
    addr_line2 = input("Address Line 2 (city, state zip): ").strip()
    phone = input("Phone (optional): ").strip()
    
    return {
        'addr_name': addr_name,
        'addr_line1': addr_line1,
        'addr_line2': addr_line2,
        'phone': phone,
        'source': 'manual'
    }


def format_address_for_display(address: Dict) -> str:
    """Format address dict for display."""
    lines = []
    
    if address.get('addr_name'):
        lines.append(address['addr_name'])
    if address.get('addr_line1'):
        lines.append(address['addr_line1'])
    if address.get('addr_line2'):
        lines.append(address['addr_line2'])
    if address.get('phone'):
        lines.append(f"Phone: {address['phone']}")
    
    return '\n'.join(lines) if lines else "(No address)"
