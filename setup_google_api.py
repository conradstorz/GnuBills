#!/usr/bin/env python3
"""
Interactive Google Places API Setup Script

This script walks you through setting up Google Places API access for the
Bill Processor application. It will:
1. Guide you through creating a Google Cloud project
2. Help you enable the Places API
3. Create and configure an API key
4. Test the API key
5. Save it to your config file

Run this script with: python setup_google_api.py
"""

import sys
import os
import re
import time
from pathlib import Path
import requests
import webbrowser

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


def test_api_key(api_key, test_location="Louisville, KY"):
    """
    Test the API key by making a simple request to Google Places API.
    
    Args:
        api_key: The Google Places API key to test
        test_location: Location to use for test search
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    print_info(f"Testing API key with a search for 'Kroger' near {test_location}...")
    
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        'query': f'Kroger {test_location}',
        'key': api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        status = data.get('status', 'UNKNOWN')
        
        if status == 'OK':
            results = data.get('results', [])
            if results:
                result = results[0]
                name = result.get('name', 'Unknown')
                address = result.get('formatted_address', 'Unknown')
                print_success(f"API key is working! Found: {name}")
                print(f"  Address: {address}")
                return True, "API key validated successfully"
            else:
                print_warning("API returned OK but no results found")
                return True, "API key works but returned no results"
                
        elif status == 'REQUEST_DENIED':
            error_msg = data.get('error_message', 'No error message provided')
            print_error(f"API key was rejected: {error_msg}")
            return False, f"Request denied: {error_msg}"
            
        elif status == 'INVALID_REQUEST':
            print_error("Invalid request format")
            return False, "Invalid request"
            
        elif status == 'OVER_QUERY_LIMIT':
            print_warning("API quota exceeded")
            return False, "Query limit exceeded"
            
        else:
            print_error(f"Unexpected status: {status}")
            return False, f"Unexpected status: {status}"
            
    except requests.RequestException as e:
        print_error(f"Network error while testing API key: {e}")
        return False, f"Network error: {e}"
    except Exception as e:
        print_error(f"Error testing API key: {e}")
        return False, f"Error: {e}"


def update_config_file(api_key):
    """
    Update the config.py file with the API key.
    
    Args:
        api_key: The Google Places API key to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    config_path = Path(__file__).parent / "src" / "config.py"
    
    if not config_path.exists():
        print_error(f"Config file not found at: {config_path}")
        return False
    
    try:
        # Read the current config
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find and replace the API key line
        pattern = r'GOOGLE_PLACES_API_KEY\s*=\s*["\'][^"\']*["\']'
        replacement = f'GOOGLE_PLACES_API_KEY = "{api_key}"'
        
        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)
            
            # Write back to file
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print_success(f"Updated config file: {config_path}")
            return True
        else:
            print_error("Could not find GOOGLE_PLACES_API_KEY in config file")
            print_info("You may need to manually add the following line to config.py:")
            print(f"  {replacement}")
            return False
            
    except Exception as e:
        print_error(f"Error updating config file: {e}")
        return False


def main():
    """Main setup workflow."""
    print_header("Google Places API Setup for Bill Processor")
    
    print("""
This interactive script will help you set up Google Places API access.
The Google Places API is used to look up vendor addresses and phone numbers
automatically when processing bills.

You'll need:
  • A Google account
  • About 10 minutes to complete setup
  • A web browser

Note: Google provides $200/month in free credits, which covers thousands of
address lookups. For personal use, you likely won't exceed the free tier.
""")
    
    proceed = get_user_input("Ready to begin? (yes/no)", "yes").lower()
    if proceed not in ['yes', 'y']:
        print("\nSetup cancelled.")
        return
    
    # Step 1: Open Google Cloud Console
    print_step(1, "Open Google Cloud Console")
    print("""
We'll start by opening the Google Cloud Console where you can create a new
project and enable the Places API.
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
    
    # Step 3: Enable Places API
    print_step(3, "Enable the Places API")
    print("""
Now we need to enable the Places API for your project:

1. In the Google Cloud Console, use the search bar at the top
2. Type "Places API" and press Enter
3. Click on "Places API" in the search results
4. Click the "ENABLE" button
5. Wait for the API to be enabled (usually takes a few seconds)
""")
    
    open_places = get_user_input("Open Places API page in browser? (yes/no)", "yes").lower()
    if open_places in ['yes', 'y']:
        print_info("Opening Places API page...")
        webbrowser.open("https://console.cloud.google.com/marketplace/product/google/places-backend.googleapis.com")
        time.sleep(2)
    
    wait_for_user()
    
    # Step 4: Create API Key
    print_step(4, "Create an API Key")
    print("""
Now let's create an API key for authentication:

1. In the Google Cloud Console, go to "APIs & Services" > "Credentials"
   (use the navigation menu ☰ on the left)
2. Click "+ CREATE CREDENTIALS" at the top
3. Select "API key" from the dropdown
4. A dialog will appear with your new API key - COPY IT NOW!
5. (Optional but recommended) Click "RESTRICT KEY" to secure it

To restrict your key (recommended):
  a. Under "API restrictions", select "Restrict key"
  b. In the dropdown, select "Places API"
  c. Click "Save"
""")
    
    open_credentials = get_user_input("Open Credentials page in browser? (yes/no)", "yes").lower()
    if open_credentials in ['yes', 'y']:
        print_info("Opening Credentials page...")
        webbrowser.open("https://console.cloud.google.com/apis/credentials")
        time.sleep(2)
    
    wait_for_user()
    
    # Step 5: Enter API Key
    print_step(5, "Enter Your API Key")
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
    
    # Step 6: Test API Key
    print_step(6, "Test Your API Key")
    print("""
Let's verify that your API key works by making a test request to the
Google Places API.
""")
    
    test_now = get_user_input("Test the API key now? (yes/no)", "yes").lower()
    if test_now in ['yes', 'y']:
        success, message = test_api_key(api_key)
        
        if not success:
            print_error(f"API key test failed: {message}")
            print_info("""
Common issues:
  • API key not yet active (can take a few minutes after creation)
  • Places API not enabled for your project
  • API key restrictions are too strict
  • Billing not enabled (required even for free tier)

Would you like to save the API key anyway and test it later?
""")
            save_anyway = get_user_input("Save API key? (yes/no)", "no").lower()
            if save_anyway not in ['yes', 'y']:
                print("\nSetup cancelled. You can run this script again later.")
                return
    
    # Step 7: Save to Config
    print_step(7, "Save API Key to Configuration")
    print("""
Now we'll save your API key to the config file so the Bill Processor
can use it automatically.
""")
    
    if update_config_file(api_key):
        print_success("Configuration updated successfully!")
    else:
        print_warning("Automatic config update failed")
        print_info(f"Please manually add this line to src/config.py:")
        print(f'\n  GOOGLE_PLACES_API_KEY = "{api_key}"\n')
    
    # Final Summary
    print_header("Setup Complete!")
    print(f"""
{Colors.GREEN}✓ Google Places API is now configured!{Colors.END}

Your Bill Processor will now use Google Places API to look up vendor
addresses and phone numbers automatically.

{Colors.BOLD}Important Notes:{Colors.END}

  • Free Tier: $200/month credit = ~40,000 requests/month
  • For personal use, you likely won't exceed the free tier
  • Monitor usage at: https://console.cloud.google.com/billing

  • If address lookups fail, the system will fall back to OpenStreetMap
  • You can check logs at: logs/bill_processor.log

{Colors.BOLD}Next Steps:{Colors.END}

  1. Test the integration by running the Bill Processor
  2. Try looking up a vendor address
  3. Check that Google Places API is being used (see logs)

{Colors.BOLD}To disable Google Places API later:{Colors.END}

  Edit src/config.py and set:
    GOOGLE_PLACES_API_KEY = ""

{Colors.CYAN}Happy billing!{Colors.END}
""")


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
