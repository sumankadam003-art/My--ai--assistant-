# Security notes

- The API binds to `127.0.0.1` by default. Do not expose it to a LAN or public internet; it uses plain HTTP and has no TLS layer.
- `/chat`, `/memory/save`, and `/memory/load` require a valid Supabase access token. This remains separate from the local Neha owner account.
- Run `python -m src.setup_owner` once to create the local owner account. The password is Neha-specific, hashed on disk, and is not your Gmail or Supabase password.
- `/owner/login` issues a process-memory bearer session. Sessions expire after one hour by default and are revoked when the API process restarts. Login attempts are throttled in memory.
- `/actions`, `/actions/approve`, and `/actions/execute` require the local owner bearer token. The client must display the selected action and obtain explicit owner confirmation before calling `/actions/approve`. Approval receipts are single-use and expire after two minutes by default.
- Action permissions are deny-by-default. Add only the permissions you intend to allow to `NEHA_ACTION_PERMISSIONS` in the private `.env` file. Example: `device.battery,device.volume,app.youtube`. Do not use wildcards.
- Existing built-in actions currently accept no arguments. Never pass model-generated shell commands or arbitrary code to an action handler.
- An action result is reported as `executed_unverified`; this means the handler returned, not that the physical effect was independently verified.
- Never commit `.env`, Supabase keys, access tokens, owner credential files, or private credentials.
