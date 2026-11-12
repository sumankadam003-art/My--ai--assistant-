import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def is_configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(access_token):
    if not access_token:
        return {}
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }



def find_cloud_memory(user_id, memory, access_token):
    """Return True if found, False if absent, or None if lookup fails."""
    if (
        not is_configured()
        or not user_id
        or not access_token
        or not isinstance(memory, str)
        or not memory.strip()
    ):
        return None

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/neha_memories",
            headers=_headers(access_token),
            params={
                "select": "id",
                "user_id": f"eq.{user_id}",
                "memory": f"eq.{memory.strip()}",
                "limit": 1,
            },
            timeout=15,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        if not isinstance(data, list):
            return None
        if not data:
            return False
        if len(data) != 1 or not isinstance(data[0], dict):
            return None

        record_id = data[0].get("id")
        if (
            isinstance(record_id, bool)
            or not isinstance(record_id, (str, int))
            or not str(record_id).strip()
        ):
            return None

        return True
    except (httpx.HTTPError, ValueError, TypeError):
        return None

def save_cloud_memory(user_id, memory, access_token, category="general"):
    if (
        not is_configured()
        or not user_id
        or not access_token
        or not isinstance(memory, str)
        or not memory.strip()
    ):
        return False

    memory = memory.strip()

    # Never insert if we cannot confirm whether the memory already exists.
    existing = find_cloud_memory(user_id, memory, access_token)
    if existing is None:
        return False
    if existing:
        return True

    try:
        response = httpx.post(
            f"{SUPABASE_URL}/rest/v1/neha_memories",
            headers={**_headers(access_token), "Prefer": "return=minimal"},
            json={
                "user_id": user_id,
                "memory": memory,
                "category": category,
            },
            timeout=15,
        )
        return response.status_code in (200, 201, 204)
    except httpx.HTTPError:
        return False


def load_cloud_memories(user_id, access_token, limit=100):
    """Return a list on success, or None when loading fails."""
    if not is_configured() or not user_id or not access_token:
        return None

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/neha_memories",
            headers=_headers(access_token),
            params={
                "select": "id,memory,category,created_at",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": max(1, min(int(limit), 500)),
            },
            timeout=15,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return data if isinstance(data, list) else None
    except (httpx.HTTPError, ValueError, TypeError):
        return None
