import os
from supabase import create_client, Client

# DEBUG: Let's see what Railway is actually providing
print("--- ENVIRONMENT DEBUG ---")
env_keys = list(os.environ.keys())
print(f"Available environment keys: {env_keys}")
print(f"Is SUPABASE_KEY in env? {'SUPABASE_KEY' in os.environ}")
print("-------------------------")

url: str = "https://kfwtxlswenleozteuzac.supabase.co"
supabase_key = os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtmd3R4bHN3ZW5sZW96dGV1emFjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTA3NzEzNSwiZXhwIjoyMDkwNjUzMTM1fQ.bWut3sXXVJicDqeqJ6-zSdQxo8tk45M4jZOsGeeueLw")

if not supabase_key:
    # If this fails, we will see the print statements above in the logs
    raise ValueError(f"SUPABASE_KEY is missing. Detected keys: {env_keys}")

supabase: Client = create_client(url, supabase_key)
