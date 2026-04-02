from database import supabase

def search_cars(budget=None, model=None, fuel_type=None):
    query = supabase.table("inventory").select("*").eq("status", 
"available")
    
    if budget:
        query = query.lte("price", budget)
    if model:
        query = query.ilike("model", f"%{model}%")
    if fuel_type:
        query = query.eq("fuel_type", fuel_type)
        
    res = query.execute()
    return res.data if res.data else "No cars found matching those 
criteria."

def create_lead(phone, intent, summary):
    data = {
        "phone_number": phone,
        "intent": intent,
        "requirement_summary": summary
    }
    res = supabase.table("leads").insert(data).execute()
    return "Lead recorded successfully."
