"""
Tests for address lookup functionality in address_lookup.py

Note: API lookup functions are tested with mocking to avoid actual API calls.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, settings

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from address_lookup import (
    AddressLookupError,
    _parse_formatted_address,
    _get_google_place_phone
)
from utils import format_address_for_display


class TestParseFormattedAddress:
    """Test _parse_formatted_address() function"""
    
    def test_full_us_address(self):
        """Test parsing full US address"""
        address = "123 Main St, Springfield, IL 62701, USA"
        result = _parse_formatted_address(address)
        
        assert result['line1'] == "123 Main St"
        assert "Springfield" in result['line2']
        assert "IL 62701" in result['line2']
    
    def test_address_without_country(self):
        """Test parsing address without country suffix"""
        address = "456 Oak Ave, Louisville, KY 40205"
        result = _parse_formatted_address(address)
        
        assert result['line1'] == "456 Oak Ave"
        assert "Louisville" in result['line2']
    
    def test_two_part_address(self):
        """Test parsing simple two-part address"""
        address = "789 Elm St, Chicago"
        result = _parse_formatted_address(address)
        
        assert result['line1'] == "789 Elm St"
        assert result['line2'] == "Chicago"
    
    def test_single_part_address(self):
        """Test parsing single-line address"""
        address = "123 Main Street"
        result = _parse_formatted_address(address)
        
        assert result['line1'] == "123 Main Street"
        assert result['line2'] == ""
    
    def test_empty_address(self):
        """Test parsing empty address"""
        result = _parse_formatted_address("")
        
        assert result['line1'] == ""
        assert result['line2'] == ""
    
    def test_removes_usa_suffix(self):
        """Test that USA suffix is removed"""
        address1 = "123 Main St, City, State, USA"
        result1 = _parse_formatted_address(address1)
        assert "USA" not in result1['line2']
        
        address2 = "123 Main St, City, State, US"
        result2 = _parse_formatted_address(address2)
        assert "US" not in result2['line2']
        
        address3 = "123 Main St, City, State, United States"
        result3 = _parse_formatted_address(address3)
        assert "United States" not in result3['line2']
    
    def test_strips_whitespace(self):
        """Test that whitespace is stripped from parts"""
        address = "  123 Main St  ,  Springfield  ,  IL  "
        result = _parse_formatted_address(address)
        
        assert result['line1'] == "123 Main St"
        assert not result['line2'].startswith(" ")
        assert not result['line2'].endswith(" ")


class TestFormatAddressForDisplay:
    """Test format_address_for_display() function"""
    
    def test_full_address_display(self):
        """Test displaying full address"""
        address = {
            'addr_name': 'Acme Corp',
            'addr_line1': '123 Main St',
            'addr_line2': 'Springfield, IL 62701',
            'phone': '(555) 123-4567'
        }
        result = format_address_for_display(address)
        
        assert 'Acme Corp' in result
        assert '123 Main St' in result
        assert 'Springfield, IL 62701' in result
        assert '(555) 123-4567' in result
    
    def test_partial_address_display(self):
        """Test displaying partial address (no phone)"""
        address = {
            'addr_name': 'Acme Corp',
            'addr_line1': '123 Main St',
            'addr_line2': 'Springfield, IL 62701'
        }
        result = format_address_for_display(address)
        
        assert 'Acme Corp' in result
        assert '123 Main St' in result
        assert 'Phone' not in result
    
    def test_minimal_address_display(self):
        """Test displaying minimal address (just name and line1)"""
        address = {
            'addr_name': 'Acme Corp',
            'addr_line1': '123 Main St'
        }
        result = format_address_for_display(address)
        
        assert 'Acme Corp' in result
        assert '123 Main St' in result
    
    def test_empty_address_display(self):
        """Test displaying empty address"""
        result = format_address_for_display({})
        assert result == "(No address)"
    
    def test_multiline_format(self):
        """Test that output uses newlines"""
        address = {
            'addr_name': 'Test',
            'addr_line1': 'Line 1',
            'addr_line2': 'Line 2'
        }
        result = format_address_for_display(address)
        
        assert '\n' in result
        lines = result.split('\n')
        assert len(lines) == 3


class TestGooglePlacePhone:
    """Test _get_google_place_phone() with mocking"""
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', 'test_key')
    @patch('address_lookup.requests.get')
    def test_successful_phone_retrieval(self, mock_get):
        """Test successful phone number retrieval"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            'result': {
                'formatted_phone_number': '(555) 123-4567'
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        phone = _get_google_place_phone('test_place_id')
        
        assert phone == '(555) 123-4567'
        assert mock_get.called
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', 'test_key')
    @patch('address_lookup.requests.get')
    def test_no_phone_in_response(self, mock_get):
        """Test when API returns no phone number"""
        mock_response = Mock()
        mock_response.json.return_value = {'result': {}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        phone = _get_google_place_phone('test_place_id')
        
        assert phone is None
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', None)
    def test_no_api_key(self):
        """Test behavior when API key is not configured"""
        phone = _get_google_place_phone('test_place_id')
        assert phone is None
    
    def test_empty_place_id(self):
        """Test behavior with empty place_id"""
        phone = _get_google_place_phone('')
        assert phone is None
        
        phone = _get_google_place_phone(None)
        assert phone is None
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', 'test_key')
    @patch('address_lookup.requests.get')
    def test_api_request_exception(self, mock_get):
        """Test handling of API request exceptions"""
        import requests
        mock_get.side_effect = requests.RequestException("API Error")
        
        phone = _get_google_place_phone('test_place_id')
        
        assert phone is None


class TestPropertyBasedAddressLookup:
    """Property-based tests for address lookup functions"""
    
    @settings(max_examples=50)
    @given(st.text())
    def test_parse_formatted_address_never_crashes(self, address):
        """Test that _parse_formatted_address never crashes"""
        try:
            result = _parse_formatted_address(address)
            assert isinstance(result, dict)
            assert 'line1' in result
            assert 'line2' in result
            assert isinstance(result['line1'], str)
            assert isinstance(result['line2'], str)
        except Exception as e:
            pytest.fail(f"_parse_formatted_address crashed on input '{address}': {e}")
    
    @settings(max_examples=50)
    @given(st.dictionaries(
        st.sampled_from(['addr_name', 'addr_line1', 'addr_line2', 'phone', 'email']),
        st.text(max_size=100),
        min_size=0,
        max_size=5
    ))
    def test_format_address_for_display_never_crashes(self, address_dict):
        """Test that format_address_for_display never crashes"""
        try:
            result = format_address_for_display(address_dict)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"format_address_for_display crashed on input {address_dict}: {e}")


class TestAddressLookupError:
    """Test AddressLookupError exception"""
    
    def test_can_raise_error(self):
        """Test that AddressLookupError can be raised and caught"""
        with pytest.raises(AddressLookupError):
            raise AddressLookupError("Test error")
    
    def test_error_message(self):
        """Test that error message is preserved"""
        try:
            raise AddressLookupError("Custom error message")
        except AddressLookupError as e:
            assert str(e) == "Custom error message"


class TestMockedAPILookups:
    """Test API lookup functions with comprehensive mocking"""
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', 'test_key')
    @patch('address_lookup.config.DEFAULT_LOCALITY', 'Springfield, IL')
    @patch('address_lookup.config.CENTER_LAT', None)
    @patch('address_lookup.config.CENTER_LON', None)
    @patch('address_lookup.requests.get')
    def test_google_places_lookup_success(self, mock_get):
        """Test successful Google Places lookup"""
        from address_lookup import lookup_google_places
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [{
                'name': 'Acme Electric',
                'formatted_address': '123 Main St, Springfield, IL 62701',
                'geometry': {
                    'location': {
                        'lat': 39.8,
                        'lng': -89.6
                    }
                },
                'place_id': 'test_place_id_123'
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = lookup_google_places("Acme Electric")
        
        assert result is not None
        assert result['name'] == 'Acme Electric'
        assert result['source'] == 'google'
        assert result['place_id'] == 'test_place_id_123'
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', 'test_key')
    @patch('address_lookup.config.DEFAULT_LOCALITY', 'Springfield, IL')
    @patch('address_lookup.requests.get')
    def test_google_places_no_results(self, mock_get):
        """Test Google Places when no results found"""
        from address_lookup import lookup_google_places
        
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': 'ZERO_RESULTS',
            'results': []
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = lookup_google_places("Nonexistent Business")
        
        assert result is None
    
    @patch('address_lookup.config.GOOGLE_PLACES_API_KEY', None)
    def test_google_places_no_api_key(self):
        """Test Google Places when API key not configured"""
        from address_lookup import lookup_google_places
        
        result = lookup_google_places("Test Business")
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
