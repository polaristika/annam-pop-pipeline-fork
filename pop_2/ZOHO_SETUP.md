# Zoho API Setup Guide

## 0. Get API Credentials

1. Go to [api-console.zoho.in](https://api-console.zoho.in)
2. Click **Self Client → CREATE NOW**
3. Click **Create** on the confirmation banner
4. Copy the **Client ID** and **Client Secret**

## 1. Generate an Auth Code

1. On the Self Client page, click **Generate Code**
2. In the **Scope** field enter:
   ```
   ZohoSheet.dataAPI.READ,WorkDrive.files.READ.CREATE
   ```
3. Set duration to **10 minutes**, add any description, click **Create**
4. Copy the auth code immediately (expires in 10 min)

## 2. Exchange for Tokens

Create `.pop_2_env` and fill in:
```python
CLIENT_ID     = "your_client_id"
CLIENT_SECRET = "your_client_secret"
AUTH_CODE     = "your_auth_code"
```
Then run:
```bash
python pop_cli.py zoho-auth
```
This saves tokens to `zoho_tokens.json`. Tokens expire in ~1 hour — repeat steps 2–3 to refresh.

## 3. Dedup Zoho Doc links

```bash
python python pop_cli.py dedup
```

## 4. Download PDFs from Zoho Sheet

```bash
python pop_cli.py zoho-download
```
- Downloads all PDFs linked in the Zoho Sheet to `data/raw/POP Bank/{State}/`
- Skips files already downloaded
- 8 parallel threads


## Notes

- Never commit `zoho_tokens.json` or the Zoho scripts — they are gitignored
- Re-run `zoho_token_exchange.py` with a fresh auth code if you get auth errors
- `zoho_sheet_explorer.py` is utility script
