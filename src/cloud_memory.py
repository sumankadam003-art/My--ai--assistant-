"""Server-side Supabase memory access for Neha's single configured identity.

This module uses the Supabase service-role key only on the trusted backend.
Never expose SUPABASE_SERVICE_ROLE_KEY to the mobile app or a public client.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
NEHA_CLOUD_OWNER_ID = os.getenv("NEHA_CLOUD_OWNER_ID", "")


def is_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and NEHA_CLOUD_OWNER_ID)


def _headers():
    if not is_configured():
        return {}
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def find_cloud_memory(user_id, memory):
    """Return True if found, False if absent, or None if lookup fails."""
    if (
        not is_configured()
        or user_id != NEHA_CLOUD_OWNER_ID
        or not isinstance(memory, str)
        or not memory.strip()
    ):
        return None
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/neha_memories",
            headers=_headers(),
            params={
                "select": "id",
                "user_id": f"eq.{NEHA_CLOUD_OWNER_ID}",
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
        return len(data) == 1 and isinstance(data[0], dict) and data[0].get("id") is not None
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def save_cloud_memory(user_id, memory, category="general"):
    if (
        not is_configured()
        or user_id != NEHA_CLOUD_OWNER_ID
        or not isinstance(memory, str)
        or not memory.strip()
        or not isinstance(category, str)
        or len(category) > 100
    ):
        return False

    memory = memory.strip()
    existing = find_cloud_memory(NEHA_CLOUD_OWNER_ID, memory)
    if existing is None:
        return False
    if existing:
        return True
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/rest/v1/neha_memories",
            headers={**_headers(), "Prefer": "return=minimal"},
            json={
                "user_id": NEHA_CLOUD_OWNER_ID,
                "memory": memory,
                "category": category,
            },
            timeout=15,
        )
        return response.status_code in (200, 201, 204)
    except httpx.HTTPError:
        return False


def load_cloud_memories(user_id, limit=100):
    """Return a list on success, or None when loading fails."""
    if not is_configured() or user_id != NEHA_CLOUD_OWNER_ID:
        return None
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/neha_memories",
            headers=_headers(),
            params={
                "select": "id,memory,category,created_at",
                "user_id": f"eq.{NEHA_CLOUD_OWNER_ID}",
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
