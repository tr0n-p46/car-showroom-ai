import os
from supabase import create_client, Client

# The URL is public, so hardcoding is fine for MVP
url: str = "https://kfwtxlswenleozteuzac.supabase.co"

# Use .get and fallback to empty string, then strip invisible spaces/newlines
supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

# Remove literal quotes if they were accidentally pasted into Railway
if supabase_key.startswith('"') and supabase_key.endswith('"'):
    supabase_key = supabase_key[1:-1]

# Final check
if len(supabase_key) < 10:
    # We print the length so we can see in the logs if it's 0 or 1
    raise ValueError(f"CRITICAL: SUPABASE_KEY is too short ({len(supabase_key)} chars). Check Railway variables.")

print(f"--- SUCCESS: Supabase Key Loaded ({len(supabase_key)} chars) ---")

supabase: Client = create_client(url, supabase_key)
