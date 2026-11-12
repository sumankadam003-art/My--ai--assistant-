# Security notes

- The API binds to `127.0.0.1` by default. Set `NEHA_API_HOST=0.0.0.0` only when LAN access is intentionally required on a trusted network.
- `/chat`, `/memory/save`, and `/memory/load` require a valid Supabase access token.
- Never commit `.env`, Supabase keys, access tokens, or private credentials.
- The API uses plain HTTP. Do not expose it to an untrusted network or the public internet; use HTTPS and an authenticated reverse proxy for remote access.
