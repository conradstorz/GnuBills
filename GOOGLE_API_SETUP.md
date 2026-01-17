# Google Places API Setup

This directory contains a script to help you set up Google Places API (New) access for automatic vendor address lookups.

**IMPORTANT:** You must enable the **"Places API (New)"** not the legacy "Places API" in Google Cloud Console.

## Quick Start

Run the interactive setup script:

```bash
python setup_google_api.py
```

The script will:
1. ✓ Open Google Cloud Console in your browser
2. ✓ Guide you through creating a project
3. ✓ Help you enable the Places API
4. ✓ Walk you through creating an API key
5. ✓ Test your API key
6. ✓ Automatically save it to your config

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
7. Create a `.env` file in the project root (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```
8. Add your key to `.env`:
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

**"REQUEST_DENIED" error:**
- Make sure Places API is enabled for your project
- Check that billing is enabled (required even for free tier)
- Wait a few minutes after creating the API key

**"OVER_QUERY_LIMIT" error:**
- You've exceeded your quota
- Check usage at [Google Cloud Console > Billing](https://console.cloud.google.com/billing)

**Address lookups still using OpenStreetMap:**
- Check logs at `logs/bill_processor.log`
- Verify your API key is in `src/config.py`
- Make sure the key is not empty string

## Monitoring Usage

Monitor your API usage and costs:
- [API Dashboard](https://console.cloud.google.com/apis/dashboard)
- [Billing](https://console.cloud.google.com/billing)

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
