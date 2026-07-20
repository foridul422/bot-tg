# Telegram Config Bot on Cloudflare Workers

This bot receives Telegram files, detects the format, sends a short preview, and attaches full details as a TXT file. It supports these decryptors:

- HTTP Custom
- SSC Custom
- HTTP Injector
- Dark Tunnel

## Deploy

1. Install `uv` and Wrangler.

   ```bash
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   npm install -g wrangler@latest
   ```

   Close and reopen your terminal after installing `uv`.

2. Login:

   ```bash
   npx wrangler login
   ```

3. Add secrets:

   ```bash
   uv run pywrangler secret put BOT_TOKEN
   uv run pywrangler secret put WEBHOOK_SECRET
   uv run pywrangler secret put SETUP_SECRET
   ```

   `BOT_TOKEN` comes from BotFather. `WEBHOOK_SECRET` and `SETUP_SECRET` can be any random strong text.

4. Optional: lock the bot to your Telegram user ID only.

   Add this to `wrangler.toml` under `[vars]`:

   ```toml
   ALLOWED_USER_IDS = "123456789"
   ```

   Optional admin failure logs and anti-spam window:

   ```toml
   ADMIN_USER_IDS = "123456789"
   SPAM_WINDOW_SECONDS = "8"
   ```

5. Deploy:

   ```bash
   uv run pywrangler deploy
   ```

6. Register Telegram webhook:

   Open this URL in a browser:

   ```text
   https://telegram-config-bot.<your-cloudflare-subdomain>.workers.dev/register?key=YOUR_SETUP_SECRET
   ```

7. Send `/start` to your bot, then upload a config file.

## Notes

Cloudflare Workers Free has daily request limits and a small CPU budget. Simple files should be fine, but heavy HTTP Injector files can need more CPU because Argon2 is expensive.
