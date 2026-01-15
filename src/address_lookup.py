"""
Address lookup via Google Places API and OpenStreetMap/Nominatim.
"""

import time
from typing import Optional, Dict, List, Tuple
import requests
from loguru import logger

import config
from utils import calculate_distance_miles
from logging_setup import log_function_entry, log_function_exit, log_api_call, log_error_with_context


class AddressLookupError(Exception):
    """Raised when address lookup fails."""
    pass


def lookup_google_places(business_name: str, locality: str = None, return_all: bool = False) -> Optional[Dict]:
    """
    Search for a business using Google Places API.
    
    Args:
        business_name: Business name to search for
        locality: Location/city to search in (defaults to config.DEFAULT_LOCALITY)
        return_all: If True, returns a list of all results instead of just the best match
    
    Returns dict with:
        - name: Business name from Google
        - formatted_address: Full address string
        - addr_line1: Street address
        - addr_line2: City, State ZIP
        - phone: Phone number (if available)
        - lat, lng: Coordinates
        - place_id: Google place ID
        - distance: Distance in miles (if CENTER_LAT/LON configured)
    
    If return_all=True, returns a list of dicts instead.
    Returns None (or empty list) if not found or API error.
    """
    log_function_entry("lookup_google_places", business_name=business_name, locality=locality)
    
    if not config.GOOGLE_PLACES_API_KEY:
        logger.warning("Google Places API key not configured - skipping Google search")
        log_function_exit("lookup_google_places", None)
        return None
    
    if locality is None:
        locality = config.DEFAULT_LOCALITY
        logger.debug(f"Using default locality: {locality}")
    
    # Build search query
    query = f"{business_name} {locality}"
    logger.debug(f"Google Places search query: '{query}'")
    
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
            radius_meters = config.SEARCH_RADIUS_MILES * 1609  # Convert to meters
            params['radius'] = radius_meters
            logger.debug(f"Adding location bias: {params['location']}, radius: {radius_meters}m")
        
        log_api_call("Google Places", "textsearch", query=query[:50])
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        status = data.get('status')
        logger.debug(f"Google Places API response status: {status}")
        
        if status != 'OK':
            logger.info(f"Google Places search unsuccessful: {status}")
            log_function_exit("lookup_google_places", None)
            return None
        
        results = data.get('results', [])
        logger.debug(f"Google Places found {len(results)} results")
        
        if not results:
            logger.info("No results from Google Places")
            log_function_exit("lookup_google_places", None)
            return None
        
        # Filter by distance if we have center coordinates
        if config.CENTER_LAT and config.CENTER_LON:
            logger.debug("Filtering results by distance")
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
                        logger.debug(f"Including result '{r.get('name')}' at {dist:.1f} miles")
                    else:
                        logger.debug(f"Excluding result '{r.get('name')}' at {dist:.1f} miles (too far)")
            results = sorted(filtered, key=lambda x: x.get('_distance', 999))
            logger.debug(f"After distance filtering: {len(results)} results")
        
        if not results:
            logger.info("No results within search radius")
            log_function_exit("lookup_google_places", None)
            return [] if return_all else None
        
        # If return_all is True, process all results and return them
        if return_all:
            all_results = []
            for r in results:
                formatted_addr = r.get('formatted_address', '')
                addr_parts = _parse_formatted_address(formatted_addr)
                
                result = {
                    'name': r.get('name'),
                    'formatted_address': formatted_addr,
                    'addr_line1': addr_parts.get('line1', ''),
                    'addr_line2': addr_parts.get('line2', ''),
                    'phone': None,  # Phone lookup is expensive, only do it when selected
                    'lat': r.get('geometry', {}).get('location', {}).get('lat'),
                    'lng': r.get('geometry', {}).get('location', {}).get('lng'),
                    'place_id': r.get('place_id'),
                    'distance': r.get('_distance'),
                    'source': 'google'
                }
                all_results.append(result)
            
            logger.info(f"Google Places lookup returned {len(all_results)} results for '{business_name}'")
            log_function_exit("lookup_google_places", f"{len(all_results)} results")
            return all_results
        
        # Original behavior: return only the best result
        best = results[0]
        logger.debug(f"Selected best result: '{best.get('name')}' at {best.get('formatted_address')}")
        
        # Get place details for phone number
        phone = None
        if config.GOOGLE_PLACES_API_KEY:
            logger.debug(f"Getting phone number for place_id: {best.get('place_id')}")
            phone = _get_google_place_phone(best.get('place_id'))
            if phone:
                logger.debug(f"Found phone number: {phone}")
            else:
                logger.debug("No phone number found")
        
        # Parse address
        formatted_addr = best.get('formatted_address', '')
        logger.debug(f"Parsing formatted address: {formatted_addr}")
        addr_parts = _parse_formatted_address(formatted_addr)
        
        result = {
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
        
        logger.info(f"Google Places lookup successful for '{business_name}': {result['name']}")
        log_function_exit("lookup_google_places", "success")
        return result
        
    except requests.RequestException as e:
        log_error_with_context(e, "Google Places API request failed", business_name=business_name, query=query)
        log_function_exit("lookup_google_places", None)
        return None


def _get_google_place_phone(place_id: str) -> Optional[str]:
    """Get phone number from Google Place Details API."""
    log_function_entry("_get_google_place_phone", place_id=str(place_id)[:20] if place_id else None)
    
    if not place_id or not config.GOOGLE_PLACES_API_KEY:
        logger.debug("Missing place_id or API key for phone lookup")
        log_function_exit("_get_google_place_phone", None)
        return None
    
    # OpenStreetMap returns integer place_id, Google expects string
    # Only Google place IDs work with the Google Places Details API
    if isinstance(place_id, int):
        logger.debug("place_id is from OpenStreetMap (integer), cannot query Google for phone")
        log_function_exit("_get_google_place_phone", None)
        return None
    
    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'fields': 'formatted_phone_number',
            'key': config.GOOGLE_PLACES_API_KEY
        }
        
        log_api_call("Google Places", "details", place_id=place_id[:20])
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        phone = data.get('result', {}).get('formatted_phone_number')
        if phone:
            logger.debug(f"Retrieved phone number from Google Places")
            log_function_exit("_get_google_place_phone", "found")
        else:
            logger.debug("No phone number available from Google Places")
            log_function_exit("_get_google_place_phone", None)
        
        return phone
        
    except requests.RequestException as e:
        log_error_with_context(e, "Google Places Details API error", place_id=place_id)
        log_function_exit("_get_google_place_phone", None)
        return None


def lookup_openstreetmap(business_name: str, locality: str = None) -> Optional[Dict]:
    """
    Search for a business using OpenStreetMap Nominatim API.
    
    This is the free fallback option.
    
    Returns same structure as lookup_google_places.
    """
    log_function_entry("lookup_openstreetmap", business_name=business_name, locality=locality)
    
    if locality is None:
        locality = config.DEFAULT_LOCALITY
        logger.debug(f"Using default locality: {locality}")
    
    query = f"{business_name} {locality}"
    logger.debug(f"OpenStreetMap search query: '{query}'")
    
    try:
        # Nominatim requires a User-Agent
        headers = {
            'User-Agent': config.OSM_USER_AGENT
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
            logger.debug("Adding bounding box for location bias")
            # Create bounding box (rough approximation)
            # 1 degree lat ≈ 69 miles, 1 degree lon varies
            lat_delta = config.SEARCH_RADIUS_MILES / 69
            lon_delta = config.SEARCH_RADIUS_MILES / 54  # Approximate for ~38° latitude
            
            params['bounded'] = 1
            params['viewbox'] = (
                f"{config.CENTER_LON - lon_delta},{config.CENTER_LAT + lat_delta},"
                f"{config.CENTER_LON + lon_delta},{config.CENTER_LAT - lat_delta}"
            )
            logger.debug(f"Bounding box: {params['viewbox']}")
        
        # Rate limiting - Nominatim requires max 1 request/second
        logger.debug("Rate limiting: waiting 1.1 seconds for Nominatim")
        time.sleep(1.1)
        
        log_api_call("OpenStreetMap Nominatim", "search", query=query[:50])
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json()
        
        logger.debug(f"OpenStreetMap found {len(results)} results")
        
        if not results:
            logger.info("No results from OpenStreetMap")
            log_function_exit("lookup_openstreetmap", None)
            return None
        
        # Filter by distance
        if config.CENTER_LAT and config.CENTER_LON:
            logger.debug("Filtering results by distance")
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
                    logger.debug(f"Including result at {dist:.1f} miles")
                else:
                    logger.debug(f"Excluding result at {dist:.1f} miles (too far)")
            results = sorted(filtered, key=lambda x: x.get('_distance', 999))
            logger.debug(f"After distance filtering: {len(results)} results")
        
        if not results:
            logger.info("No results within search radius")
            log_function_exit("lookup_openstreetmap", None)
            return None
        
        best = results[0]
        logger.debug(f"Selected best result: '{best.get('display_name', '')}'")
        address = best.get('address', {})
        
        # Build address lines
        house_number = address.get('house_number', '')
        road = address.get('road', '')
        line1 = f"{house_number} {road}".strip()
        
        city = address.get('city') or address.get('town') or address.get('village', '')
        state = address.get('state', '')
        postcode = address.get('postcode', '')
        
        line2 = f"{city}, {state} {postcode}".strip()
        logger.debug(f"Parsed address: line1='{line1}', line2='{line2}'")
        
        result = {
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
        
        logger.info(f"OpenStreetMap lookup successful for '{business_name}': {result['name']}")
        log_function_exit("lookup_openstreetmap", "success")
        return result
        
    except requests.RequestException as e:
        log_error_with_context(e, "OpenStreetMap API request failed", business_name=business_name, query=query)
        log_function_exit("lookup_openstreetmap", None)
        return None


def _parse_formatted_address(address: str) -> Dict[str, str]:
    """
    Parse a formatted address string into granular components.
    
    "123 Main St, Louisville, KY 40201, USA" ->
    {
        'street': '123 Main St',
        'city': 'Louisville',
        'state': 'KY',
        'zip': '40201',
        'line1': '123 Main St',
        'line2': 'Louisville, KY 40201'
    }
    
    Returns both granular components (street, city, state, zip) and
    traditional line1/line2 format for compatibility.
    """
    log_function_entry("_parse_formatted_address", address=address[:50] if address else None)
    
    result = {'street': '', 'city': '', 'state': '', 'zip': '', 'line1': '', 'line2': ''}
    
    if not address:
        logger.debug("Empty address provided")
        log_function_exit("_parse_formatted_address", "empty")
        return result
    
    # Remove country suffix if present
    parts = [p.strip() for p in address.split(',')]
    
    # Remove "USA", "US", "United States" from end
    if parts and parts[-1].lower() in ('usa', 'us', 'united states'):
        parts = parts[:-1]
    
    if len(parts) >= 3:
        # Format: "123 Main St, City, State ZIP"
        street = parts[0]
        city = parts[1]
        
        # Parse state and ZIP from last part ("KY 40201" or "Kentucky 40201")
        last_part = parts[2].strip()
        state = ''
        zip_code = ''
        
        # Split on whitespace to separate state from ZIP
        last_parts = last_part.split()
        if len(last_parts) >= 2:
            state = last_parts[0]
            zip_code = last_parts[1]
        elif len(last_parts) == 1:
            # Could be just state or just ZIP
            if last_parts[0].isdigit() or '-' in last_parts[0]:
                zip_code = last_parts[0]
            else:
                state = last_parts[0]
        
        result = {
            'street': street,
            'city': city,
            'state': state,
            'zip': zip_code,
            'line1': street,
            'line2': f"{city}, {state} {zip_code}".strip()
        }
        
    elif len(parts) == 2:
        # Format: "123 Main St, Louisville"
        result = {
            'street': parts[0],
            'city': parts[1],
            'state': '',
            'zip': '',
            'line1': parts[0],
            'line2': parts[1]
        }
    else:
        # Just one part - treat as street
        result = {
            'street': address,
            'city': '',
            'state': '',
            'zip': '',
            'line1': address,
            'line2': ''
        }
    
    logger.debug(f"Parsed address: street='{result['street']}', city='{result['city']}', state='{result['state']}', zip='{result['zip']}'")
    log_function_exit("_parse_formatted_address", "success")
    return result



