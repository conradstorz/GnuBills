# Google Places API Setup

This directory contains an **end-to-end verification and setup tool** for Google Places API (New) access, which enables automatic vendor address lookups.

**IMPORTANT:** You must enable the **"Places API (New)"** not the legacy "Places API" in Google Cloud Console.

## Features

🔍 **Intelligent Verification** - Auto-detects what's already configured  
🎯 **Hybrid Approach** - Only sets up what's missing  
🧪 **Full Integration Testing** - Tests the complete chain from .env → config → API  
🔧 **Detailed Diagnostics** - Pinpoints exact failure points with troubleshooting steps  
✅ **Exit Codes** - Perfect for CI/CD pipelines  
📊 **Comprehensive Reporting** - 8-step verification with clear status

## Quick Start

Run the interactive setup and verification tool:

```bash
uv run python setup_google_api.py
```

The tool will:
1. ✓ **Verify** your existing configuration automatically
2. ✓ **Detect** which components are already set up  
3. ✓ **Guide** you through setup for only the missing pieces
4. ✓ **Test** the complete integration end-to-end
5. ✓ **Troubleshoot** with detailed diagnostic steps

### Verification Only Mode

To check your current configuration without making changes:

```bash
uv run python setup_google_api.py --verify-only
```

This runs comprehensive checks on:
- .env file existence and API key presence
- API key format and validity
- Google Places API connectivity
- config.py integration
- Full address lookup functionality
- Google Cloud project and API status (if gcloud CLI available)

Exit code: 0 if fully configured, 1 if issues found

## What Gets Verified

The tool performs **9 comprehensive checks**:

1. **✓ Python dependencies** - Checks all required packages are installed
2. **✓ .env file exists** - Checks for secure credential storage
3. **✓ API key in .env** - Verifies GOOGLE_PLACES_API_KEY is set
4. **✓ API key format** - Validates key structure and format
5. **✓ API key works** - Tests authentication with Google Places API
6. **✓ config.py integration** - Ensures config loads the key correctly
7. **✓ Address lookup** - Tests full end-to-end functionality
8. **✓ gcloud CLI** (optional) - Detects Google Cloud CLI if installed
9. **✓ Places API enabled** (optional) - Verifies API status in project

**Smart Detection**: The tool distinguishes between dependency issues and Google API configuration issues, providing appropriate guidance for each.


## Why Google Places API?

The Bill Processor can look up vendor addresses and phone numbers automatically when you enter bills. It uses two services:

- **Google Places API** - More accurate, requires setup, $200/month free credit
- **OpenStreetMap** - Free fallback, no setup needed, less accurate

For personal use, Google's free tier ($200/month) provides ~40,000 address lookups per month, which is more than enough for typical bill processing.

## Manual Setup

If you prefer to set up manually:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the **"Places API (New)"** for your project (NOT the legacy "Places API")
   - Search for "Places API (New)" in the API Library
   - Make sure it says "(New)" - there are two different APIs!
4. Create an API key in "Credentials"
5. (Recommended) Restrict the key to only "Places API (New)"
6. Copy your API key
7. Create a `.env` file in the project root:
   ```bash
   # Create .env file and add your key
   echo "GOOGLE_PLACES_API_KEY=your-api-key-here" > .env
   ```
8. Or manually add your key to `.env`:
   ```
   GOOGLE_PLACES_API_KEY=your-api-key-here
   ```

**Note:** 
- The legacy "Places API" will not work. You must use "Places API (New)".
- The `.env` file is in `.gitignore` and will NOT be committed to git (secure!)
- Never commit API keys to version control!

## Testing Your Setup

After setup, test that it works:

```python
from src.address_lookup import lookup_address

result = lookup_address("Kroger", "Louisville, KY")
print(result)
```

You should see address details returned from Google Places API.

## Troubleshooting

The tool provides **detailed troubleshooting steps** for each failure. Common issues:

**"REQUEST_DENIED" or 403 error:**
- Verify you enabled "Places API (New)" not the legacy "Places API"
- Check API key restrictions in Google Cloud Console
- Ensure billing is enabled (required even for free tier)
- Wait a few minutes if you just created the API key
- Verify the API key isn't restricted to different APIs

**"API key expired" error:**
- Create a new API key in Google Cloud Console
- Update the .env file with the new key
- Run verification to confirm: `uv run python setup_google_api.py --verify-only`

**"OVER_QUERY_LIMIT" error:**
- You've exceeded your quota
- Check usage at [Google Cloud Console > Billing](https://console.cloud.google.com/billing)
- Quota resets at midnight Pacific Time

**Address lookups still using OpenStreetMap:**
- Check logs at `logs/bill_processor.log`
- Run verification: `uv run python setup_google_api.py --verify-only`
- Look for specific failure point in the 9-step check
- Follow the troubleshooting steps provided by the tool

**Config.py doesn't load the API key:**
- Ensure .env is in the project root directory
- Verify python-dotenv is installed: `uv add python-dotenv` or `uv sync`
- Try restarting your terminal/IDE to reload environment
- Check for syntax errors in .env (no quotes needed around key)


## Monitoring Usage

Monitor your API usage and costs:
- [API Dashboard](https://console.cloud.google.com/apis/dashboard)
- [Billing](https://console.cloud.google.com/billing)

**Quick health check:**
```bash
uv run python setup_google_api.py --verify-only
```

This will report the complete status in seconds.

## Advanced Usage

### CI/CD Integration

Use verification mode in continuous integration:

```bash
# In your CI script
uv run python setup_google_api.py --verify-only
if [ $? -eq 0 ]; then
    echo "Google Places API configured correctly"
else
    echo "Google Places API configuration issues detected"
    exit 1
fi
```

### Debugging Integration Issues

The tool tests the complete chain:
1. .env file → 2. config.py → 3. address_lookup.py → 4. Google API

Run with verification to pinpoint where the chain breaks.

## Disabling Google Places API

To disable and use only OpenStreetMap:

1. Edit `.env` file
2. Comment out or remove the API key line:
   ```
   # GOOGLE_PLACES_API_KEY=
   ```

Or simply delete the `.env` file.

## Privacy & Security

- Your API key is stored in `.env` file (NOT in config.py)
- `.env` is in `.gitignore` and will never be committed to version control
- Keep your `.env` file secure and never share it
- Consider restricting your API key to only Places API (New)
- Consider adding application restrictions (HTTP referrer, IP address)

## Cost Estimates

With $200/month free credit:
- Text Search (address lookup): ~$32/1000 requests = ~6,250 free/month
- Place Details (phone lookup): ~$17/1000 requests = ~11,750 free/month

For personal bill processing, you'll likely never exceed the free tier.
