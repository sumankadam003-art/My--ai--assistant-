# Neha Central Action Engine

## What is connected

The central engine is exposed through the local API and the mobile app's **Actions** tab.

- Create a local owner account once with `python -m src.setup_owner`.
- Start the API from the repository root with `python src/app_api.py`.
- The API listens on `127.0.0.1:8765` by default.
- In the mobile app, open **Actions** and sign in with the local Neha owner username/password.
- While signed in, choose **Enable Biometric Password Reset** once. Android protects a randomly generated recovery secret using Expo SecureStore and its biometric authentication prompt. The API stores only a hash of the secret.
- To reset a forgotten owner password, open the Actions tab while signed out, enter a new password twice, and choose **Verify Biometric & Reset**. Android verifies the fingerprint/biometric locally before releasing the protected secret to the app. The fingerprint itself is never sent to Neha.
- A successful reset preserves the owner ID and account data, updates the password hash, and revokes active owner sessions.
- Keep the existing password until biometric enrollment and a test reset have both succeeded. Biometric recovery is tied to this Android app installation; uninstalling/clearing app data, losing the device, or changing enrolled biometrics may invalidate the recovery secret.
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
- Biometric recovery is not a cloud backup and cannot recover the secret if the Android app's protected storage is lost or invalidated.
- Existing built-in actions currently accept no arguments. Model-generated shell commands and arbitrary code are not executable.
- All built-in actions require owner approval. Permission allowlisting is an additional gate, not a replacement for approval.
- The engine reports `executed_unverified` when a handler returns. It does not independently prove that Android performed the requested effect.
- The current approval UI is in the Expo mobile app. Other clients must implement the same review-and-confirm step before calling the approval endpoint.
