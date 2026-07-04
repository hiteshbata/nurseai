"""Apply specialty tags to existing scenarios. Run AFTER the ALTER TABLE migration."""
import sys
sys.path.insert(0, '.')
from app.core.supabase import get_supabase

SPECIALTIES = {
    "Chest Pain in Emergency Department": "Emergency / Acute Care",
    "Pre-operative Anxiety": "Surgical / Post-Op",
    "Diabetes Insulin Education": "General / Internal Medicine",
    "Discharge Instructions - Post Hip Replacement": "Surgical / Post-Op",
    "Chemotherapy Side Effects Discussion": "Oncology",
    "Post-Operative Care After Cholecystectomy": "Surgical / Post-Op",
    "Medication Side Effects Counselling": "Respiratory",
    "Discharge Planning After Stroke": "Geriatrics / Elderly Care",
    "Post-Operative Pain Assessment": "Surgical / Post-Op",
    "Patient Refusing Antibiotic Treatment": "General / Internal Medicine",
}

supabase = get_supabase()

for title, specialty in SPECIALTIES.items():
    result = supabase.table("scenarios").update({"specialty": specialty}).eq("title", title).execute()
    if result.data:
        print(f"  [OK] {title} → {specialty}")
    else:
        print(f"  [ERR] {title} — not found")

print("\nDone. All specialties applied.")
