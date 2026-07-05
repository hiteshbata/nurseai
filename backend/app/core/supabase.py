from supabase import create_client, Client
from app.core.config import settings

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)

# Separate client, scoped to the anon key, used ONLY for auth.* calls
# (get_user / sign_up / sign_in_with_password). These methods mutate the
# calling client's internal session state as a side effect. Since `supabase`
# above is a single process-wide singleton used for service-role table
# operations, letting any auth.* call run on it would silently switch its
# identity to whichever end user (or anon session) most recently
# authenticated -- causing RLS to reject subsequent service-role writes
# (e.g. new row violates row-level security policy for table "user_roles").
# Isolating auth.* calls to this client means its session state can mutate
# freely without ever affecting the client actually used for DB writes.
_auth_client: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY,
)

def get_supabase() -> Client:
    return supabase

def get_auth_client() -> Client:
    return _auth_client
