# Neha Central Action Engine

## What is connected

The central engine is exposed through the local API and the mobile app's **Actions** tab.

- Create a local owner account once with `python -m src.setup_owner`.
- Start the API from the repository root with `python src/app_api.py`.
- The API listens on `127.0.0.1:8765` by default.
- In the mobile app, open **Actions** and sign in with the local Neha owner username/password.
- Review an action and explicitly choose **Approve & Run**. The app displays the action, permission, and risk first.
- The API issues a short-lived, single-use approval token. The execution endpoint consumes it and re-authenticates the owner.
- A process restart revokes owner sessions and pending approvals.

## Enable only the permissions you want

The default is deny-all. Add an explicit comma-separated allowlist to the private root `.env` file under `NEHA_ACTION_PERMISSIONS`.

Example syntax (choose only permissions you intend to enable):

```dotenv
NEHA_ACTION_PERMISSIONS=device.battery,device.volume,app.youtube
```

Available built-in permissions:

- `device.battery`
- `device.volume`
- `device.camera`
- `device.notification`
- `device.speech`
- `app.youtube`
- `app.google`
- `app.gmail`
- `app.maps`
- `app.instagram`

Restart the API after changing the allowlist. Do not use wildcard permissions.

## Test

From the repository root:

```bash
python -m unittest test_action_engine test_action_audit test_action_engine_bridge test_action_authorization test_authorized_action_service test_action_service_factory test_local_owner_auth test_action_registry test_app_api test_app_api_security -v
```

## Important limits

- This is a local-device control API, not a remote cloud action service. Keep it bound to localhost.
- The API uses HTTP, not HTTPS. Do not expose it to a LAN or the public internet.
- Cloud memory/chat authentication remains separate and continues to use Supabase.
- Existing built-in actions currently accept no arguments. Model-generated shell commands and arbitrary code are not executable.
- All built-in actions require owner approval. Permission allowlisting is an additional gate, not a replacement for approval.
- The engine reports `executed_unverified` when a handler returns. It does not independently prove that Android performed the requested effect.
- The current approval UI is in the Expo mobile app. Other clients must implement the same review-and-confirm step before calling the approval endpoint.
