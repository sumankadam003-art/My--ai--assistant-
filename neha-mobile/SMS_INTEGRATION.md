# Neha SMS integration

## Safety model

Neha does not send SMS silently and does not request Android's `SEND_SMS` permission.

After the owner enters a phone number and message, the app shows an exact-content confirmation. The authenticated backend validates both values and consumes a short-lived, single-use approval token. Only then does the app open Android's SMS application with the approved recipient and message prefilled. The owner must review the native composer and press **Send**.

The Android SMS API does not provide Neha with delivery confirmation. The app must not report an SMS as delivered merely because the composer opened.

The `send_sms` action is disabled in Termux. It is exposed by the authenticated mobile API only and still requires the existing `device.sms` owner permission.

## Backend permission

Add `device.sms` to the existing comma-separated `NEHA_ACTION_PERMISSIONS` allowlist in the private Termux environment file. Preserve all existing permissions; do not replace the allowlist with only this value. Restart the API after changing the environment.

Do not commit the private environment file or put Supabase service-role credentials in the mobile app.

## Mobile dependency and build

The app uses the Expo SDK 58-compatible `expo-sms` module. Expo SMS opens the system composer; it does not send messages in the background. No Android SMS runtime permission or config plugin is required for this composer-based workflow.

A development build profile already exists in `eas.json`. From `neha-mobile`, install the locked dependencies and create an Android development build with EAS:

```bash
npm ci
npx eas-cli build --platform android --profile development
```

Install the generated development APK on the Android phone, then start the project with the development-client option:

```bash
npx expo start --dev-client
```

Expo Go also includes Expo SMS, but the development build is the intended app-testing path.

## Required device test

1. Sign in as the owner.
2. Confirm `send_sms` is listed and enabled only after the backend owner permission is configured.
3. Enter a test phone number and a harmless test message.
4. Verify the in-app confirmation shows the exact recipient and message.
5. Cancel once and verify no message is sent.
6. Repeat and press **Send** in the native SMS app.
7. Verify the phone's Messages app shows the outgoing message; do not treat the app's Android callback as proof of delivery.
