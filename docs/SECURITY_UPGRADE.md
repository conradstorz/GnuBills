# Security Improvements - API Key Storage

## Important Security Change

**The Google Places API key is now stored securely in a `.env` file, NOT in `config.py`.**

### Why This Matters

- **Before:** API keys were in `config.py` which could accidentally be committed to git
- **Now:** API keys are in `.env` which is explicitly ignored by git
- **Result:** Your credentials are safe and won't be exposed in version control

### What You Need to Do

If you're upgrading from an older version:

1. **Create a `.env` file:**
   ```bash
   cp .env.example .env
   ```

2. **Move your API key to `.env`:**
   ```
   GOOGLE_PLACES_API_KEY=your-api-key-here
   ```

3. **Remove the API key from `src/config.py`** (if it's there)
   - The code now automatically loads from environment variables
   - You don't need to edit `config.py` anymore for API keys

### For New Users

Just run the setup script:
```bash
python setup_google_api.py
```

It will automatically:
- Guide you through getting an API key
- Save it securely to `.env`
- Make sure it's never committed to git

### Verifying It Works

```bash
python -c "from src import config; print('API key loaded:', 'Yes' if config.GOOGLE_PLACES_API_KEY else 'No')"
```

Should print: `API key loaded: Yes`

### File Structure

- `.env` - Your actual API key (NEVER commit this!)
- `.env.example` - Template showing what variables are needed (safe to commit)
- `src/config.py` - Loads variables from `.env` automatically

### Security Best Practices

✓ `.env` is in `.gitignore`  
✓ API keys are never in source code  
✓ Each developer/environment has their own `.env`  
✓ `.env.example` documents what's needed without exposing secrets  

---

**Note:** This follows industry-standard security practices used by frameworks like Django, Flask, Node.js, etc.
