import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Your specific Supabase URL
url: str = "https://kfwtxlswenleozteuzac.supabase.co"

# This pulls from Railway's environment variables
supabase_key = os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtmd3R4bHN3ZW5sZW96dGV1emFjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTA3NzEzNSwiZXhwIjoyMDkwNjUzMTM1fQ.bWut3sXXVJicDqeqJ6-zSdQxo8tk45M4jZOsGeeueLw")

if not supabase_key:
    raise ValueError("SUPABASE_KEY environment variable is not set!")

supabase: Client = create_client(url, supabase_key)
