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
    Test the API key by making a simple request to Google Places API (New).
    
    Args:
        api_key: The Google Places API key to test
        test_location: Location to use for test search
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    print_info(f"Testing API key with a search for 'Kroger' near {test_location}...")
    
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
            print_success(f"API key is working! Found: {name}")
            print(f"  Address: {address}")
            return True, "API key validated successfully"
        elif 'error' in data:
            # New API returns errors differently
            error = data['error']
            error_msg = error.get('message', 'No error message provided')
            status_code = error.get('code', response.status_code)
            
            if status_code == 403:
                print_error(f"API key was rejected: {error_msg}")
                return False, f"Request denied: {error_msg}"
            elif status_code == 429:
                print_warning("API quota exceeded")
                return False, "Query limit exceeded"
            else:
                print_error(f"API error ({status_code}): {error_msg}")
                return False, f"Error {status_code}: {error_msg}"
        elif response.status_code != 200:
            print_error(f"HTTP {response.status_code}: {response.text}")
            return False, f"HTTP error {response.status_code}"
        else:
            print_warning("API returned success but no results found")
            return True, "API key works but returned no results"
            
    except requests.RequestException as e:
        print_error(f"Network error while testing API key: {e}")
        return False, f"Network error: {e}"
    except Exception as e:
        print_error(f"Error testing API key: {e}")
        return False, f"Error: {e}"


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
    
    # Step 5: Test API Key
    print_step(5, "Test Your API Key")
    print("""
Let's verify that your API key works by making a test request to the
Google Places API (New).
""")
    
    test_now = get_user_input("Test the API key now? (yes/no)", "yes").lower()
    if test_now in ['yes', 'y']:
        success, message = test_api_key(api_key)
        
        if not success:
            print_error(f"API key test failed: {message}")
            print_info("""
Common issues:
  • API key not yet active (can take a few minutes after creation)
  • Wrong API enabled - make sure you enabled "Places API (New)" not legacy version
  • API key restrictions are too strict
  • Billing not enabled (required even for free tier)

Would you like to save the API key anyway and test it later?
""")
            save_anyway = get_user_input("Save API key? (yes/no)", "no").lower()
            if save_anyway not in ['yes', 'y']:
                print("\nSetup cancelled. You can run this script again later.")
                return
    
    # Step 6: Save to Config
    print_step(6, "Save API Key to Configuration")
    print("""
Now we'll save your API key to a secure .env file so the Bill Processor
can use it automatically. The .env file is NOT committed to git.
""")
    
    if update_config_file(api_key):
        print_success("Configuration updated successfully!")
    else:
        print_warning("Automatic config update failed")
        print_info(f"Please manually create a .env file with:")
        print(f'\n  GOOGLE_PLACES_API_KEY={api_key}\n')
    
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

  Remove or comment out the line in .env file:
    # GOOGLE_PLACES_API_KEY=your-key-here

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
