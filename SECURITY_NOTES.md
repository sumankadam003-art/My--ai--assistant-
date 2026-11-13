# Security notes

## API network exposure

- The API listens on `127.0.0.1:8765` by default. `NEHA_API_HOST` can override the bind address; keep it on loopback unless a separately secured deployment is designed and reviewed.
- The API uses plain HTTP and does not provide TLS. Do not expose it directly to a LAN or the public internet.
- CORS currently allows the configured local Expo development origin `http://localhost:8081`. CORS is not authentication and does not protect the API from non-browser clients.
- The `/health` endpoint is public and reports service/cloud-memory configuration status. The challenge and login endpoints are also reachable without an existing session because they establish authentication.

## Local owner authentication and sessions

- Create the local owner account with `python -m src.setup_owner`. This creates `data/owner_auth.json`; keep the `data/` directory private and out of version control.
- The owner credential record stores a PBKDF2-HMAC-SHA256 password hash and salt, not the plaintext password.
- Current API login uses `POST /auth/challenge` followed by `POST /auth/login`. Challenges expire after 120 seconds and are invalidated after a successful answer or five attempts. The challenge answer is checked using the private `NEHA_LOGIN_OFFSET` configuration.
- The API does not expose the older `/owner/login` route. Do not assume that the setup password is submitted to the current challenge-login endpoint.
- Successful login returns a bearer token. The API stores only the SHA-256 digest of each token in `data/owner_sessions.json`, associated with the local owner ID.
- `src/app_api.py` configures `LocalOwnerAuth(session_ttl_seconds=None)`. Therefore sessions have no time-based expiry and survive API process restarts. This is intentional current behaviour; do not document a one-hour expiry or restart-based revocation.
- `POST /auth/logout` revokes the presented session. The password-recovery helper also clears active sessions when it resets the password. Protect the session file and owner account file as credentials.

## Endpoint access

- Public endpoints: `GET /health`, `POST /auth/challenge`, and `POST /auth/login`.
- `POST /auth/logout` requires the bearer token it is revoking.
- The following endpoints require a valid local owner bearer session: `GET /actions`, `POST /chat`, `POST /memory/save`, `POST /memory/load`, `POST /actions/approve`, and `POST /actions/execute`.
- The chat and cloud-memory routes do not authenticate the client with a Supabase access token. Cloud-memory operations use the server-configured `NEHA_CLOUD_OWNER_ID` and server-side Supabase configuration. Never put a Supabase service-role key in the mobile app.
- Request bodies are limited to 100,000 bytes by the API. Chat messages are limited to 10,000 characters; saved memories are limited to 5,000 characters.

## Biometric recovery

- `LocalOwnerAuth` contains backend helper methods for recovery enrollment, password reset, and recovery-secret rotation. These helpers are not exposed as HTTP routes by the current `src/app_api.py`.
- Do not assume that a complete, end-to-end biometric enrollment or password-reset workflow is available through the current API until the required routes and client flow are implemented and tested.
- Recovery secrets are represented in the owner record by SHA-256 digests. Any future mobile recovery flow must keep the raw recovery secret in secure device storage and must not transmit biometric images or templates.

## Action execution safeguards

- `/actions`, `/actions/approve`, and `/actions/execute` require the local owner bearer token.
- The client must present the selected action details and obtain explicit owner confirmation before requesting approval. The API checks `owner_confirmed: true` on `/actions/approve`.
- Approval receipts are single-use, owner-bound, and expire after two minutes by default.
- Action permissions are deny-by-default. Add only intended permissions to `NEHA_ACTION_PERMISSIONS` in the private `.env` file. Example: `device.battery,device.volume,app.youtube`. Do not use wildcards.
- Existing built-in actions currently accept no arguments. Never pass model-generated shell commands or arbitrary code to an action handler.
- An action result reported as `executed_unverified` means the handler returned; it does not mean the physical effect was independently verified.

## Secret handling

- Never commit `.env`, Supabase keys, access tokens, owner credential files, owner session files, recovery secrets, or other private credentials.
- Keep backups of private owner data secure. Anyone who obtains valid session tokens or can alter local owner/session files may compromise the local owner account.
