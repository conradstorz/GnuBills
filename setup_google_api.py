#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Places API End-to-End Verification and Setup Tool

This comprehensive tool will:
1. VERIFY existing configuration and detect what's already set up
2. TEST the complete integration chain (API key → config → address lookup)
3. DIAGNOSE any issues with detailed troubleshooting steps
4. GUIDE you through setup only for missing components

The tool performs a full end-to-end verification:
- Check if .env file exists and has API key
- Validate API key format and functionality
- Test actual Google Places API requests
- Verify config.py loads the key correctly
- Test full address lookup integration
- Check Google Cloud project status (if gcloud available)

Run this script with: uv run python setup_google_api.py

Run with --verify-only to skip setup and only run verification:
    uv run python setup_google_api.py --verify-only
"""

import sys
import os
import re
import time
import json
import subprocess
from pathlib import Path
import requests
import webbrowser
from typing import Optional, Dict, Tuple, List

# Fix Unicode encoding on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class VerificationResult:
    """Represents the result of a verification check."""
    def __init__(self, passed: bool, message: str, details: str = None, troubleshooting: List[str] = None):
        self.passed = passed
        self.message = message
        self.details = details
        self.troubleshooting = troubleshooting or []
    
    def __bool__(self):
        return self.passed


class SetupState:
    """Tracks the overall setup/verification state."""
    def __init__(self):
        self.dependencies_installed = False
        self.env_file_exists = False
        self.api_key_in_env = False
        self.api_key_format_valid = False
        self.api_key_works = False
        self.config_loads_key = False
        self.address_lookup_works = False
        self.gcloud_available = False
        self.project_detected = None
        self.api_enabled = None
        
        self.api_key_value = None
        self.error_log = []
        self.missing_dependencies = []
    
    def is_fully_configured(self) -> bool:
        """Check if everything is working end-to-end."""
        return all([
            self.dependencies_installed,
            self.env_file_exists,
            self.api_key_in_env,
            self.api_key_format_valid,
            self.api_key_works,
            self.config_loads_key,
            self.address_lookup_works
        ])
    
    def has_dependency_issues(self) -> bool:
        """Check if the main issue is missing dependencies."""
        return not self.dependencies_installed
    
    def has_google_api_issues(self) -> bool:
        """Check if there are Google API configuration issues (not dependency issues)."""
        if not self.dependencies_installed:
            return False  # Can't tell if we have dependency issues
        
        return not all([
            self.env_file_exists,
            self.api_key_in_env,
            self.api_key_format_valid,
            self.api_key_works
        ])
    
    def get_missing_components(self) -> List[str]:
        """Get list of components that need setup."""
        missing = []
        if not self.dependencies_installed:
            missing.append("Python dependencies")
        if not self.env_file_exists:
            missing.append(".env file")
        if not self.api_key_in_env:
            missing.append("API key in .env")
        if self.api_key_in_env and not self.api_key_format_valid:
            missing.append("valid API key format")
        if self.api_key_format_valid and not self.api_key_works:
            missing.append("working API key")
        if not self.config_loads_key:
            missing.append("config.py integration")
        if not self.address_lookup_works:
            missing.append("address lookup functionality")
        return missing



def print_header(text):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}\n")


def print_step(number, text):
    """Print a step number and description."""
    print(f"{Colors.BOLD}{Colors.CYAN}Step {number}:{Colors.END} {text}\n")


def print_success(text):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text):
    """Print informational message."""
    print(f"{Colors.CYAN}ℹ {text}{Colors.END}")


def print_diagnostic(text):
    """Print diagnostic/debug message."""
    print(f"  {Colors.CYAN}→ {text}{Colors.END}")


def print_troubleshooting(steps: List[str]):
    """Print troubleshooting steps."""
    if not steps:
        return
    print(f"\n{Colors.YELLOW}{Colors.BOLD}Troubleshooting Steps:{Colors.END}")
    for i, step in enumerate(steps, 1):
        print(f"{Colors.YELLOW}  {i}. {step}{Colors.END}")



def wait_for_user():
    """Wait for user to press Enter."""
    input(f"\n{Colors.YELLOW}Press Enter when ready to continue...{Colors.END}")


def get_user_input(prompt, default=None):
    """Get input from user with optional default."""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        return input(f"{prompt}: ").strip()


def validate_api_key(api_key):
    """Validate API key format."""
    # Google API keys are typically 39 characters, alphanumeric with dashes/underscores
    if not api_key:
        return False
    if len(api_key) < 30:
        return False
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        return False
    return True


# =============================================================================
# VERIFICATION FUNCTIONS
# =============================================================================

def verify_env_file() -> VerificationResult:
    """Verify that .env file exists."""
    env_path = Path(__file__).parent / ".env"
    
    if env_path.exists():
        print_diagnostic(f"Found .env file at: {env_path}")
        return VerificationResult(
            True,
            ".env file exists",
            str(env_path)
        )
    else:
        return VerificationResult(
            False,
            ".env file not found",
            "The .env file is used to securely store your API key",
            [
                "The .env file will be created during setup",
                "You can manually create one by copying .env.example",
                f"Expected location: {env_path}"
            ]
        )


def verify_api_key_in_env() -> Tuple[VerificationResult, Optional[str]]:
    """Verify API key exists in .env file. Returns (result, api_key_value)."""
    env_path = Path(__file__).parent / ".env"
    
    if not env_path.exists():
        return VerificationResult(
            False,
            "Cannot check - .env file doesn't exist"
        ), None
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for GOOGLE_PLACES_API_KEY
        pattern = r'^GOOGLE_PLACES_API_KEY=(.+)$'
        match = re.search(pattern, content, re.MULTILINE)
        
        if match:
            api_key = match.group(1).strip().strip('"').strip("'")
            if api_key:
                print_diagnostic(f"Found API key in .env (length: {len(api_key)} chars)")
                return VerificationResult(
                    True,
                    "API key found in .env file",
                    f"Key length: {len(api_key)} characters"
                ), api_key
            else:
                return VerificationResult(
                    False,
                    "API key variable exists but is empty",
                    "GOOGLE_PLACES_API_KEY is defined but has no value",
                    [
                        "Add your API key after the = sign",
                        "Format: GOOGLE_PLACES_API_KEY=your-key-here",
                        "Run this script to get a new API key"
                    ]
                ), None
        else:
            return VerificationResult(
                False,
                "API key not defined in .env file",
                "GOOGLE_PLACES_API_KEY variable not found",
                [
                    "The variable needs to be added to .env",
                    "Run this script to complete setup",
                    f"Or manually add: GOOGLE_PLACES_API_KEY=your-key-here to {env_path}"
                ]
            ), None
            
    except Exception as e:
        return VerificationResult(
            False,
            f"Error reading .env file: {e}",
            troubleshooting=[
                "Check file permissions on .env",
                "Ensure the file is not corrupted",
                f"Try opening {env_path} in a text editor"
            ]
        ), None


def verify_api_key_format(api_key: str) -> VerificationResult:
    """Verify API key has valid format."""
    if not api_key:
        return VerificationResult(False, "No API key provided")
    
    issues = []
    
    # Check length
    if len(api_key) < 30:
        issues.append(f"Too short ({len(api_key)} chars, expected ~39)")
    
    # Check characters
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        issues.append("Contains invalid characters (expected only alphanumeric, dash, underscore)")
    
    # Check typical prefix
    if not api_key.startswith('AIza'):
        issues.append("Doesn't start with 'AIza' (typical for Google API keys)")
    
    if issues:
        return VerificationResult(
            False,
            "API key format appears invalid",
            "; ".join(issues),
            [
                "Verify you copied the complete API key from Google Cloud Console",
                "Check for extra spaces or line breaks",
                "Make sure you copied the API key, not another credential type",
                "Google API keys typically: start with 'AIza', are ~39 chars, no spaces"
            ]
        )
    else:
        print_diagnostic(f"API key format looks valid (length: {len(api_key)}, starts with 'AIza')")
        return VerificationResult(
            True,
            "API key format is valid",
            f"Length: {len(api_key)} characters"
        )


def verify_api_key_works(api_key: str, test_location="Louisville, KY") -> VerificationResult:
    """Test if API key actually works with Google Places API."""
    print_diagnostic(f"Testing API with search: 'Kroger {test_location}'...")
    
    success, message = test_api_key(api_key, test_location)
    
    if success:
        return VerificationResult(
            True,
            "API key successfully authenticated with Google",
            message
        )
    else:
        # Provide detailed troubleshooting based on error type
        troubleshooting = []
        
        if "403" in message or "denied" in message.lower():
            troubleshooting.extend([
                "Verify you enabled 'Places API (New)' not the legacy 'Places API'",
                "Check API key restrictions in Google Cloud Console",
                "Ensure billing is enabled on your Google Cloud project",
                "Wait a few minutes if you just created the API key",
                "Verify the API key isn't restricted to different APIs"
            ])
        elif "429" in message or "quota" in message.lower():
            troubleshooting.extend([
                "You've exceeded your API quota for today",
                "Check usage at: https://console.cloud.google.com/apis/dashboard",
                "Wait until quota resets (usually midnight Pacific Time)",
                "Consider increasing quota limits if needed"
            ])
        elif "network" in message.lower() or "timeout" in message.lower():
            troubleshooting.extend([
                "Check your internet connection",
                "Verify you can access https://places.googleapis.com",
                "Check if a firewall is blocking the request",
                "Try again in a moment"
            ])
        else:
            troubleshooting.extend([
                "Verify you copied the complete API key",
                "Check that 'Places API (New)' is enabled in Google Cloud Console",
                "Ensure billing is enabled (required even for free tier)",
                "Try creating a new API key",
                f"Error details: {message}"
            ])
        
        return VerificationResult(
            False,
            "API key test failed",
            message,
            troubleshooting
        )


def check_dependencies() -> VerificationResult:
    """Check if required Python dependencies are installed."""
    print_diagnostic("Checking Python dependencies...")
    
    required_packages = {
        'requests': 'requests',
        'thefuzz': 'thefuzz',
        'Levenshtein': 'python-Levenshtein',
        'loguru': 'loguru',
        'dotenv': 'python-dotenv'
    }
    
    missing = []
    
    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    
    if missing:
        return VerificationResult(
            False,
            f"Missing {len(missing)} required package(s)",
            f"Missing: {', '.join(missing)}",
            [
                "Install missing packages with uv:",
                f"  uv add {' '.join(missing)}",
                "Or sync all dependencies from pyproject.toml:",
                "  uv sync",
                "Note: pip is deprecated in this project, always use uv"
            ]
        )
    else:
        print_diagnostic("All required packages installed")
        return VerificationResult(
            True,
            "All required dependencies installed",
            f"Checked: {', '.join(required_packages.values())}"
        )


def verify_config_loads_key() -> Tuple[VerificationResult, Optional[str]]:
    """Verify that config.py can load the API key from environment."""
    print_diagnostic("Testing config.py integration...")
    
    try:
        # Import config from package
        from bill_processor import config
        
        # Reload config to ensure fresh .env load
        import importlib
        importlib.reload(config)
        
        api_key = config.GOOGLE_PLACES_API_KEY
        
        if api_key:
            print_diagnostic(f"config.py loaded API key successfully (length: {len(api_key)})")
            return VerificationResult(
                True,
                "config.py successfully loads API key",
                f"Key length: {len(api_key)} characters"
            ), api_key
        else:
            return VerificationResult(
                False,
                "config.py loads but API key is empty",
                "config.GOOGLE_PLACES_API_KEY is empty string",
                [
                    "Verify .env file has GOOGLE_PLACES_API_KEY=your-key",
                    "Check that .env is in the project root directory",
                    "Ensure python-dotenv is installed: uv add python-dotenv",
                    "Try restarting your terminal/IDE to reload environment"
                ]
            ), None
            
    except ImportError as e:
        return VerificationResult(
            False,
            "Cannot import config.py",
            str(e),
            [
                "Verify bill_processor/config.py exists",
                "Check for syntax errors in config.py",
                "Ensure python-dotenv is installed",
                f"Import error: {e}"
            ]
        ), None
    except Exception as e:
        return VerificationResult(
            False,
            f"Error loading config: {e}",
            troubleshooting=[
                "Check config.py for errors",
                "Verify .env file format",
                f"Error details: {e}"
            ]
        ), None


def verify_address_lookup_integration() -> VerificationResult:
    """Test full end-to-end address lookup functionality."""
    print_diagnostic("Testing complete address lookup integration...")
    
    try:
        # Import from package
        from bill_processor.address_lookup import lookup_google_places
        from bill_processor import config
        import importlib
        importlib.reload(config)
        
        # Test actual lookup
        print_diagnostic("Performing test lookup: 'Kroger' in Louisville, KY...")
        
        # Temporarily suppress loguru output to avoid cluttering verification
        from loguru import logger
        logger.disable("address_lookup")
        logger.disable("logging_setup")
        
        result = lookup_google_places("Kroger", "Louisville, KY")
        
        # Re-enable logging
        logger.enable("address_lookup")
        logger.enable("logging_setup")
        
        if result:
            name = result.get('name', 'Unknown')
            address = result.get('formatted_address', 'Unknown')
            
            print_diagnostic(f"Lookup successful! Found: {name}")
            print_diagnostic(f"  Address: {address}")
            
            # Check if it came from Google (it should if API key is working)
            return VerificationResult(
                True,
                "Address lookup working with Google Places API",
                f"Successfully found: {name}"
            )
        else:
            # If we got here, the direct API test passed but integration failed
            # This likely means there's a configuration issue in address_lookup.py
            return VerificationResult(
                False,
                "Address lookup integration issue detected",
                "Direct API test passed, but full integration returned no results",
                [
                    "This indicates a configuration issue in src/address_lookup.py",
                    "Common causes:",
                    "  - Location bias radius too large (check config.SEARCH_RADIUS_MILES)",
                    "  - Invalid lat/lon coordinates (check config.CENTER_LAT/CENTER_LON)",
                    "  - Field mask requesting unavailable fields",
                    "Check logs/bill_processor.log for detailed error messages",
                    "Try running the application directly to see full error details"
                ]
            )
            
    except ImportError as e:
        error_msg = str(e)
        
        # Check if it's a missing dependency issue
        if "No module named" in error_msg:
            missing_module = error_msg.split("'")[1] if "'" in error_msg else "unknown"
            
            return VerificationResult(
                False,
                f"Missing Python dependency: {missing_module}",
                f"Cannot test address lookup without {missing_module}",
                [
                    f"Install the missing package: uv add {missing_module}",
                    "Or sync all dependencies: uv sync",
                    "Note: pip is deprecated, always use uv",
                    "Note: This is a dependency issue, not a Google API configuration issue"
                ]
            )
        else:
            return VerificationResult(
                False,
                "Cannot import address_lookup module",
                str(e),
                [
                    "Verify src/address_lookup.py exists",
                    "Check for missing dependencies",
                    "Sync dependencies: uv sync",
                    f"Import error: {e}"
                ]
            )
    except Exception as e:
        return VerificationResult(
            False,
            f"Address lookup test failed: {e}",
            troubleshooting=[
                "Check logs/bill_processor.log for details",
                "Verify all dependencies are installed",
                "Check config.py settings",
                f"Error: {e}"
            ]
        )


def check_gcloud_cli() -> Tuple[bool, Optional[str]]:
    """Check if gcloud CLI is installed and configured."""
    try:
        result = subprocess.run(
            ['gcloud', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.split('\n')[0] if result.stdout else "unknown"
            return True, version
        return False, None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, None


def check_gcloud_project() -> Optional[str]:
    """Get current gcloud project if available."""
    try:
        result = subprocess.run(
            ['gcloud', 'config', 'get-value', 'project'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            project = result.stdout.strip()
            return project if project else None
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def check_places_api_enabled(project: str) -> Optional[bool]:
    """Check if Places API (New) is enabled for the project."""
    try:
        result = subprocess.run(
            ['gcloud', 'services', 'list', '--enabled', 
             '--filter=name:places', '--format=value(name)'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            services = result.stdout.lower()
            # Look for places.googleapis.com or placesnew
            return 'places' in services
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None



def test_api_key(api_key, test_location="Louisville, KY"):
    """
    Test the API key by making a simple request to Google Places API (New).
    
    Args:
        api_key: The Google Places API key to test
        test_location: Location to use for test search
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    # Use the new Places API (New) - Text Search endpoint
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.id'
    }
    body = {
        'textQuery': f'Kroger {test_location}'
    }
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        data = response.json()
        
        # New API returns different structure - check for places array
        if 'places' in data and len(data['places']) > 0:
            place = data['places'][0]
            name = place.get('displayName', {}).get('text', 'Unknown')
            address = place.get('formattedAddress', 'Unknown')
            return True, f"Found: {name} at {address}"
        elif 'error' in data:
            # New API returns errors differently
            error = data['error']
            error_msg = error.get('message', 'No error message provided')
            status_code = error.get('code', response.status_code)
            return False, f"Error {status_code}: {error_msg}"
        elif response.status_code != 200:
            return False, f"HTTP error {response.status_code}"
        else:
            return True, "API key works but returned no results"
            
    except requests.RequestException as e:
        return False, f"Network error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# COMPREHENSIVE VERIFICATION WORKFLOW
# =============================================================================

def run_comprehensive_verification() -> SetupState:
    """
    Run complete end-to-end verification of Google Places API setup.
    Returns SetupState with all verification results.
    """
    print_header("Google Places API - Comprehensive Verification")
    
    state = SetupState()
    
    print(f"\n{Colors.BOLD}Running end-to-end verification checks...{Colors.END}\n")
    
    # Check 0: Python dependencies (NEW - check first!)
    print(f"{Colors.BOLD}[1/9]{Colors.END} Checking Python dependencies...")
    result = check_dependencies()
    state.dependencies_installed = result.passed
    if result:
        print_success(result.message)
    else:
        print_error(result.message)
        if result.details:
            print_info(result.details)
        if result.troubleshooting:
            print_troubleshooting(result.troubleshooting)
        
        # Extract missing dependencies for later use
        if result.details and "Missing:" in result.details:
            deps_str = result.details.split("Missing:")[1].strip()
            state.missing_dependencies = [d.strip() for d in deps_str.split(',')]
    
    # Check 1: .env file exists
    print(f"\n{Colors.BOLD}[2/9]{Colors.END} Checking for .env file...")
    result = verify_env_file()
    state.env_file_exists = result.passed
    if result:
        print_success(result.message)
    else:
        print_error(result.message)
        if result.details:
            print_info(result.details)
        if result.troubleshooting:
            print_troubleshooting(result.troubleshooting)
    
    # Check 2: API key in .env
    print(f"\n{Colors.BOLD}[3/9]{Colors.END} Checking for API key in .env...")
    result, api_key = verify_api_key_in_env()
    state.api_key_in_env = result.passed
    state.api_key_value = api_key
    if result:
        print_success(result.message)
    else:
        print_error(result.message)
        if result.details:
            print_info(result.details)
        if result.troubleshooting:
            print_troubleshooting(result.troubleshooting)
    
    # Check 3: API key format
    if api_key:
        print(f"\n{Colors.BOLD}[4/9]{Colors.END} Validating API key format...")
        result = verify_api_key_format(api_key)
        state.api_key_format_valid = result.passed
        if result:
            print_success(result.message)
        else:
            print_error(result.message)
            if result.details:
                print_info(result.details)
            if result.troubleshooting:
                print_troubleshooting(result.troubleshooting)
    else:
        print(f"\n{Colors.BOLD}[4/9]{Colors.END} Validating API key format...")
        print_warning("Skipped - no API key to validate")
        state.api_key_format_valid = False
    
    # Check 4: API key functionality
    if api_key and state.api_key_format_valid:
        print(f"\n{Colors.BOLD}[5/9]{Colors.END} Testing API key with Google Places API...")
        result = verify_api_key_works(api_key)
        state.api_key_works = result.passed
        if result:
            print_success(result.message)
            if result.details:
                print_info(result.details)
        else:
            print_error(result.message)
            if result.details:
                print_info(result.details)
            if result.troubleshooting:
                print_troubleshooting(result.troubleshooting)
    else:
        print(f"\n{Colors.BOLD}[5/9]{Colors.END} Testing API key with Google Places API...")
        print_warning("Skipped - no valid API key to test")
        state.api_key_works = False
    
    # Check 5: config.py integration
    print(f"\n{Colors.BOLD}[6/9]{Colors.END} Verifying config.py loads API key...")
    result, config_key = verify_config_loads_key()
    state.config_loads_key = result.passed
    if result:
        print_success(result.message)
        # Verify it matches .env
        if config_key and api_key and config_key != api_key:
            print_warning("API key in config.py doesn't match .env file!")
            print_info("This may indicate caching - try restarting your IDE/terminal")
    else:
        print_error(result.message)
        if result.details:
            print_info(result.details)
        if result.troubleshooting:
            print_troubleshooting(result.troubleshooting)
    
    # Check 6: Full address lookup integration (only if dependencies are installed)
    if state.dependencies_installed and state.api_key_works:
        print(f"\n{Colors.BOLD}[7/9]{Colors.END} Testing complete address lookup integration...")
        result = verify_address_lookup_integration()
        state.address_lookup_works = result.passed
        if result:
            print_success(result.message)
            if result.details:
                print_info(result.details)
        else:
            print_error(result.message)
            if result.details:
                print_info(result.details)
            if result.troubleshooting:
                print_troubleshooting(result.troubleshooting)
    else:
        print(f"\n{Colors.BOLD}[7/9]{Colors.END} Testing complete address lookup integration...")
        if not state.dependencies_installed:
            print_warning("Skipped - dependencies not installed")
        else:
            print_warning("Skipped - API key not working")
        state.address_lookup_works = False
    
    # Check 7: gcloud CLI (optional)
    print(f"\n{Colors.BOLD}[8/9]{Colors.END} Checking for gcloud CLI (optional)...")
    gcloud_available, gcloud_version = check_gcloud_cli()
    state.gcloud_available = gcloud_available
    if gcloud_available:
        print_success(f"gcloud CLI found: {gcloud_version}")
        
        # Check project
        project = check_gcloud_project()
        if project:
            state.project_detected = project
            print_info(f"Active project: {project}")
            
            # Check if API enabled
            api_enabled = check_places_api_enabled(project)
            state.api_enabled = api_enabled
            if api_enabled:
                print_success("Places API appears to be enabled")
            elif api_enabled is False:
                print_warning("Places API may not be enabled for this project")
            else:
                print_info("Could not verify API status")
        else:
            print_info("No active gcloud project configured")
    else:
        print_info("gcloud CLI not found (not required)")
    
    # Check 8: Summary
    print(f"\n{Colors.BOLD}[9/9]{Colors.END} Generating verification report...")
    
    return state


def print_verification_summary(state: SetupState):
    """Print a comprehensive summary of verification results."""
    print_header("Verification Summary")
    
    if state.is_fully_configured():
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ ALL CHECKS PASSED!{Colors.END}")
        print(f"\n{Colors.GREEN}Your Google Places API integration is fully configured and working!{Colors.END}\n")
        print("Components verified:")
        print(f"  {Colors.GREEN}✓{Colors.END} Python dependencies installed")
        print(f"  {Colors.GREEN}✓{Colors.END} .env file exists")
        print(f"  {Colors.GREEN}✓{Colors.END} API key configured in .env")
        print(f"  {Colors.GREEN}✓{Colors.END} API key format valid")
        print(f"  {Colors.GREEN}✓{Colors.END} API key authenticated with Google")
        print(f"  {Colors.GREEN}✓{Colors.END} config.py loads API key correctly")
        print(f"  {Colors.GREEN}✓{Colors.END} Address lookup working end-to-end")
        
        if state.gcloud_available and state.project_detected:
            print(f"\n{Colors.CYAN}Google Cloud Project:{Colors.END} {state.project_detected}")
            if state.api_enabled:
                print(f"  {Colors.GREEN}✓{Colors.END} Places API enabled")
        
        print(f"\n{Colors.BOLD}You're all set!{Colors.END} The Bill Processor will use Google Places API for address lookups.")
        print(f"\nMonitor usage at: {Colors.CYAN}https://console.cloud.google.com/apis/dashboard{Colors.END}")
        
    elif state.has_dependency_issues():
        # Special handling for dependency issues
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ MISSING PYTHON DEPENDENCIES{Colors.END}\n")
        
        print(f"{Colors.YELLOW}The Google API configuration cannot be fully tested because required")
        print(f"Python packages are missing.{Colors.END}\n")
        
        if state.missing_dependencies:
            print(f"{Colors.BOLD}Missing packages:{Colors.END}")
            for dep in state.missing_dependencies:
                print(f"  {Colors.YELLOW}✗{Colors.END} {dep}")
        
        print(f"\n{Colors.BOLD}Quick Fix:{Colors.END}")
        if state.missing_dependencies:
            print(f"  {Colors.CYAN}uv add {' '.join(state.missing_dependencies)}{Colors.END}")
        else:
            print(f"  {Colors.CYAN}uv sync{Colors.END}")
        
        print(f"\n{Colors.BOLD}Or sync all project dependencies:{Colors.END}")
        print(f"  {Colors.CYAN}uv sync{Colors.END}")
        print(f"\n{Colors.CYAN}Note: pip is deprecated in this project, always use uv{Colors.END}")
        
        # Show what IS working (Google API config might be fine)
        working = []
        if state.env_file_exists:
            working.append(".env file exists")
        if state.api_key_in_env:
            working.append("API key in .env")
        if state.api_key_format_valid:
            working.append("API key format valid")
        if state.api_key_works:
            working.append("API key authenticated")
        
        if working:
            print(f"\n{Colors.GREEN}Google API configuration (looks good!):{Colors.END}")
            for item in working:
                print(f"  {Colors.GREEN}✓{Colors.END} {item}")
        
        print(f"\n{Colors.BOLD}After installing dependencies:{Colors.END}")
        print(f"  Run verification again: {Colors.CYAN}python setup_google_api.py --verify-only{Colors.END}")
        
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ CONFIGURATION INCOMPLETE{Colors.END}\n")
        
        # Show what's working
        working = []
        if state.dependencies_installed:
            working.append("Python dependencies installed")
        if state.env_file_exists:
            working.append(".env file exists")
        if state.api_key_in_env:
            working.append("API key in .env")
        if state.api_key_format_valid:
            working.append("API key format valid")
        if state.api_key_works:
            working.append("API key works")
        if state.config_loads_key:
            working.append("config.py integration")
        if state.address_lookup_works:
            working.append("Address lookup working")
        
        if working:
            print(f"{Colors.GREEN}Working components:{Colors.END}")
            for item in working:
                print(f"  {Colors.GREEN}✓{Colors.END} {item}")
        
        # Show what needs attention
        missing = state.get_missing_components()
        if missing:
            print(f"\n{Colors.YELLOW}Needs attention:{Colors.END}")
            for item in missing:
                print(f"  {Colors.YELLOW}✗{Colors.END} {item}")
        
        print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
        if state.has_dependency_issues():
            print("  1. Install missing Python packages (see above)")
            print("  2. Run verification again to check Google API configuration")
        else:
            print("  Run this script without --verify-only to complete Google API setup")
            print("  Or use the troubleshooting steps above to fix issues manually")



def update_config_file(api_key):
    """
    Save the API key to .env file (secure storage).
    
    Args:
        api_key: The Google Places API key to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    env_path = Path(__file__).parent / ".env"
    env_example_path = Path(__file__).parent / ".env.example"
    
    try:
        # Read existing .env file if it exists, otherwise start from .env.example
        env_lines = []
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        elif env_example_path.exists():
            with open(env_example_path, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        
        # Update or add the API key
        key_found = False
        new_lines = []
        for line in env_lines:
            if line.strip().startswith('GOOGLE_PLACES_API_KEY=') or line.strip().startswith('#GOOGLE_PLACES_API_KEY='):
                new_lines.append(f'GOOGLE_PLACES_API_KEY={api_key}\n')
                key_found = True
            else:
                new_lines.append(line)
        
        # If key wasn't found, add it
        if not key_found:
            if new_lines and not new_lines[-1].endswith('\n'):
                new_lines.append('\n')
            new_lines.append(f'\n# Google Places API Key (from Google Cloud Console)\n')
            new_lines.append(f'GOOGLE_PLACES_API_KEY={api_key}\n')
        
        # Write back to .env file
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print_success(f"API key saved to: {env_path}")
        print_info("The .env file is in .gitignore and won't be committed to git")
        return True
        
    except Exception as e:
        print_error(f"Error saving to .env file: {e}")
        print_info(f"You can manually create a .env file with:")
        print(f"  GOOGLE_PLACES_API_KEY={api_key}")
        return False


def main():
    """Main setup workflow with hybrid verification/creation approach."""
    
    # Check for --help flag
    if '--help' in sys.argv or '-h' in sys.argv:
        print(f"""
{Colors.BOLD}Google Places API Setup & Verification Tool{Colors.END}

{Colors.BOLD}USAGE:{Colors.END}
  uv run python setup_google_api.py [OPTIONS]

{Colors.BOLD}OPTIONS:{Colors.END}
  --verify-only    Run comprehensive verification without setup
                   Returns exit code 0 if fully configured, 1 otherwise

  --help, -h       Show this help message

{Colors.BOLD}MODES:{Colors.END}
  {Colors.CYAN}Interactive Setup (default):{Colors.END}
    uv run python setup_google_api.py
    
    • Runs full end-to-end verification
    • Auto-detects existing configuration
    • Guides you through setup for missing components only
    • Tests complete integration
  
  {Colors.CYAN}Verification Only:{Colors.END}
    uv run python setup_google_api.py --verify-only
    
    • Checks all components without making changes
    • Useful for debugging and CI/CD
    • Provides detailed troubleshooting for failures

{Colors.BOLD}WHAT IT VERIFIES:{Colors.END}
  1. Python dependencies installed
  2. .env file exists
  3. API key present in .env
  4. API key format is valid
  5. API key works with Google Places API
  6. config.py loads the key correctly
  7. Full address lookup integration
  8. Google Cloud project status (if gcloud available)
  9. Places API (New) enabled status (if gcloud available)

{Colors.BOLD}EXAMPLES:{Colors.END}
  # First-time setup
  uv run python setup_google_api.py
  
  # Check if everything is working
  uv run python setup_google_api.py --verify-only
  
  # After updating API key, verify it works
  uv run python setup_google_api.py --verify-only

{Colors.BOLD}MORE INFO:{Colors.END}
  See GOOGLE_API_SETUP.md for manual setup instructions
""")
        sys.exit(0)
    
    # Check for --verify-only flag
    verify_only = '--verify-only' in sys.argv
    
    if verify_only:
        # Just run verification and exit
        state = run_comprehensive_verification()
        print_verification_summary(state)
        sys.exit(0 if state.is_fully_configured() else 1)
    
    # Regular mode: verify first, then guide through setup for missing components
    print_header("Google Places API - Setup & Verification Tool")
    
    print(f"""
{Colors.BOLD}This tool will:{Colors.END}
  1. Verify your existing Google Places API configuration
  2. Detect which components are already set up
  3. Guide you through setup for only the missing pieces
  4. Test the complete integration end-to-end

{Colors.BOLD}You'll need:{Colors.END}
  • A Google account
  • About 10 minutes (if starting from scratch)
  • A web browser

{Colors.CYAN}Note:{Colors.END} Google provides $200/month in free credits = ~40,000 address lookups
For personal use, you likely won't exceed the free tier.
""")
    
    proceed = get_user_input("Ready to begin verification? (yes/no)", "yes").lower()
    if proceed not in ['yes', 'y']:
        print("\nSetup cancelled.")
        return
    
    # Step 1: Run comprehensive verification
    state = run_comprehensive_verification()
    
    # Step 2: Check if already fully configured
    if state.is_fully_configured():
        print_verification_summary(state)
        print(f"\n{Colors.GREEN}No setup needed - everything is already working!{Colors.END}")
        return
    
    # Step 2.5: Check if it's just a dependency issue
    if state.has_dependency_issues():
        print_verification_summary(state)
        print(f"\n{Colors.YELLOW}This is a Python dependency issue, not a Google API configuration issue.{Colors.END}")
        print(f"\n{Colors.BOLD}Install the missing packages and run verification again:{Colors.END}")
        if state.missing_dependencies:
            print(f"  {Colors.CYAN}uv add {' '.join(state.missing_dependencies)}{Colors.END}")
        else:
            print(f"  {Colors.CYAN}uv sync{Colors.END}")
        print(f"\n{Colors.BOLD}Then verify:{Colors.END}")
        print(f"  {Colors.CYAN}uv run python setup_google_api.py --verify-only{Colors.END}")
        return
    
    # Step 3: Show what needs setup (Google API issues only)
    print(f"\n{Colors.BOLD}{Colors.YELLOW}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.YELLOW}Setup Required{Colors.END}")
    print(f"{Colors.BOLD}{Colors.YELLOW}{'=' * 70}{Colors.END}\n")
    
    missing = state.get_missing_components()
    print(f"The following components need attention:\n")
    for item in missing:
        print(f"  {Colors.YELLOW}→{Colors.END} {item}")
    
    print(f"\n{Colors.BOLD}Let's fix these issues...{Colors.END}\n")
    
    proceed = get_user_input("Continue with guided setup? (yes/no)", "yes").lower()
    if proceed not in ['yes', 'y']:
        print("\nSetup cancelled. Run with --verify-only to check status anytime.")
        return
    
    # Determine what steps we need
    need_new_api_key = not (state.api_key_in_env and state.api_key_format_valid and state.api_key_works)
    need_cloud_setup = need_new_api_key  # Only guide through cloud setup if we need a new key
    
    api_key_to_save = state.api_key_value if state.api_key_value and state.api_key_works else None
    
    # If we need a new API key, guide through Google Cloud setup
    if need_cloud_setup:
        print_header("Google Cloud Console Setup")
        
        # Step 1: Open Google Cloud Console
        print_step(1, "Open Google Cloud Console")
        print("""
We'll start by opening the Google Cloud Console where you can create a new
project and enable the Places API. After that webpage opens return here to continue.
""")

        open_browser = get_user_input("Open Google Cloud Console in browser? (yes/no)", "yes").lower()
        if open_browser in ['yes', 'y']:
            print_info("Opening https://console.cloud.google.com/")
            webbrowser.open("https://console.cloud.google.com/")
            time.sleep(2)
        else:
            print_info("Please navigate to: https://console.cloud.google.com/")
        
        wait_for_user()
        
        # Step 2: Create or Select Project
        print_step(2, "Create or Select a Google Cloud Project")
        print("""
In the Google Cloud Console:

1. Click the project dropdown at the top of the page (next to "Google Cloud")
2. Click "NEW PROJECT" button in the dialog that appears
3. Enter a project name (e.g., "Bill Processor" or "GnuCash Tools")
4. Click "CREATE" and wait for the project to be created
5. Make sure the new project is selected in the dropdown

If you already have a project you want to use, simply select it from the
dropdown instead.
""")
        
        wait_for_user()
        
        # Step 3: Enable Places API and Create API Key
        print_step(3, "Enable the Places API (New) and Create API Key")
        print(f"""
{Colors.BOLD}{Colors.YELLOW}IMPORTANT: Enable "Places API (New)" not the legacy "Places API"{Colors.END}

We'll now enable the API and create credentials in one workflow:

1. In the Google Cloud Console, use the search bar at the top
2. Type "Places API (New)" and press Enter
3. Look for {Colors.BOLD}"Places API (New)"{Colors.END} - make sure it says "(New)"!
4. Click on "Places API (New)" in the search results
5. Click the {Colors.BOLD}"ENABLE"{Colors.END} button
6. After enabling, you'll see the API page with an "CREATE CREDENTIALS" button
7. Click {Colors.BOLD}"CREATE CREDENTIALS"{Colors.END}
8. Select "API key" from the options
9. A dialog will appear with your new API key - {Colors.BOLD}COPY IT NOW!{Colors.END}

{Colors.YELLOW}Note: There are TWO different APIs:{Colors.END}
  • {Colors.GREEN}"Places API (New)"{Colors.END} ← Use this one! (newer, better)
  • "Places API" ← Legacy version, will NOT work with this app

{Colors.BOLD}Optional but recommended:{Colors.END} After copying your key, click "RESTRICT KEY"
  • Under "API restrictions", select "Restrict key"
  • Search for and select "Places API (New)"
  • Click "Save"
""")
        
        open_console = get_user_input("Open Google Cloud Console in browser? (yes/no)", "yes").lower()
        if open_console in ['yes', 'y']:
            print_info("Opening Google Cloud Console API Library...")
            webbrowser.open("https://console.cloud.google.com/apis/library")
            time.sleep(2)
        
        wait_for_user()
        
        # Step 4: Enter API Key
        print_step(4, "Enter Your API Key")
        print("""
Please paste your Google Places API key below.

The API key should look something like:
  AIzaSyBXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

It's typically 39 characters long and starts with "AIza".
""")
        
        api_key = None
        while not api_key:
            key_input = get_user_input("Paste your API key here").strip()
            
            if not key_input:
                print_error("API key cannot be empty")
                retry = get_user_input("Try again? (yes/no)", "yes").lower()
                if retry not in ['yes', 'y']:
                    print("\nSetup cancelled.")
                    return
                continue
            
            if not validate_api_key(key_input):
                print_warning("That doesn't look like a valid Google API key")
                print_info("Google API keys are usually 39 characters, alphanumeric with dashes/underscores")
                use_anyway = get_user_input("Use this key anyway? (yes/no)", "no").lower()
                if use_anyway not in ['yes', 'y']:
                    continue
            
            api_key = key_input
            break
        
        api_key_to_save = api_key
        
        # Step 5: Test the new API Key
        print_step(5, "Test Your API Key")
        print("""
Let's verify that your API key works by making a test request to the
Google Places API (New).
""")
        
        test_now = get_user_input("Test the API key now? (yes/no)", "yes").lower()
        if test_now in ['yes', 'y']:
            print_info("Testing API key...")
            result = verify_api_key_works(api_key)
            
            if not result:
                print_error(f"API key test failed: {result.message}")
                if result.details:
                    print_info(result.details)
                if result.troubleshooting:
                    print_troubleshooting(result.troubleshooting)
                
                save_anyway = get_user_input("\nSave API key anyway and test later? (yes/no)", "no").lower()
                if save_anyway not in ['yes', 'y']:
                    print("\nSetup cancelled. You can run this script again later.")
                    return
            else:
                print_success(result.message)
    
    # Save API key to .env
    if api_key_to_save:
        print_step("Final", "Save API Key to Configuration")
        print("""
Now we'll save your API key to a secure .env file so the Bill Processor
can use it automatically. The .env file is NOT committed to git.
""")
        
        if update_config_file(api_key_to_save):
            print_success("Configuration updated successfully!")
        else:
            print_warning("Automatic config update failed")
            print_info(f"Please manually create a .env file with:")
            print(f'\n  GOOGLE_PLACES_API_KEY={api_key_to_save}\n')
        
        # Run final verification
        print(f"\n{Colors.BOLD}Running final verification...{Colors.END}\n")
        time.sleep(1)
        
        final_state = run_comprehensive_verification()
        print_verification_summary(final_state)
        
        if final_state.is_fully_configured():
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Setup completed successfully!{Colors.END}")
        else:
            print(f"\n{Colors.YELLOW}Setup completed but some issues remain.{Colors.END}")
            print("Review the troubleshooting steps above or run this script again.")
    else:
        # No new API key but may have had other issues
        print_warning("No API key to save - setup incomplete")
        print_info("Run this script again to complete setup")
    
    # Final tips
    print(f"\n{Colors.BOLD}Useful Commands:{Colors.END}")
    print(f"  • Verify setup: {Colors.CYAN}uv run python setup_google_api.py --verify-only{Colors.END}")
    print(f"  • Monitor usage: {Colors.CYAN}https://console.cloud.google.com/apis/dashboard{Colors.END}")
    print(f"  • View logs: {Colors.CYAN}logs/bill_processor.log{Colors.END}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled by user.{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
