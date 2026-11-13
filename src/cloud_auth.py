import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def is_configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _auth_request(endpoint, payload):
    if not is_configured():
        return {
            "success": False,
            "error": "Supabase configuration is missing."
        }

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/{endpoint}",
            json=payload,
            headers=headers,
            timeout=20.0,
        )

        try:
            data = response.json()
        except ValueError:
            data = {}

        if not isinstance(data, dict):
            data = {}

        if not response.is_success:
            message = (
                data.get("msg")
                or data.get("message")
                or data.get("error_description")
                or data.get("error")
                or "Authentication request failed."
            )

            return {
                "success": False,
                "error": str(message)[:300],
                "status_code": response.status_code,
            }

        user = data.get("user") or data
        session = data.get("session") or data

        access_token = session.get("access_token")
        user_id = user.get("id")

        if not user_id and access_token:
            return {
                "success": False,
                "error": "Login response did not contain a user ID."
            }

        if not user_id:
            return {
                "success": False,
                "error": "No user ID returned. Check email confirmation."
            }

        return {
            "success": True,
            "user_id": user_id,
            "access_token": access_token,
            "email_confirmation_required": not bool(access_token),
        }

    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timed out. Check your connection."
        }

    except httpx.RequestError:
        return {
            "success": False,
            "error": "Could not connect to Supabase."
        }


def sign_up(email, password):
    return _auth_request(
        "signup",
        {
            "email": email.strip(),
            "password": password,
        },
    )


def sign_in(email, password):
    return _auth_request(
        "token?grant_type=password",
        {
            "email": email.strip(),
            "password": password,
        },
    )


def get_authenticated_user(access_token):
    """Return the Supabase user only when the access token is valid."""
    if not is_configured() or not access_token:
        return None

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers=headers,
            timeout=15,
        )
        if response.status_code != 200:
            return None

        user = response.json()
        return user if isinstance(user, dict) and user.get("id") else None

    except (httpx.HTTPError, ValueError):
        return None
