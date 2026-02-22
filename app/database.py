from supabase import create_client, Client
from app.config import get_settings

settings = get_settings()

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Return a singleton Supabase client using the service role key."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url.strip(),
            settings.supabase_service_role_key.strip(),
        )
    return _supabase_client
