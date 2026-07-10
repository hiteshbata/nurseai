from supabase import create_client, Client
from app.core.config import settings

# postgrest-py 0.16.x hardcodes http2=True with no override in ClientOptions.
# Supabase/Render idle-close the HTTP/2 connection before httpx's keepalive
# expiry, so a reused pooled connection raises httpx.RemoteProtocolError:
# "Server disconnected" (seen on sessions/usage, onboarding/status,
# progress/stats, progress/history). Force http2=False at the session
# factory so a fresh HTTP/1.1 connection is used instead.
from postgrest._sync.client import SyncPostgrestClient
from postgrest.utils import SyncClient as _SyncClient

def _create_session_no_http2(self, base_url, headers, timeout, verify=True):
    return _SyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        verify=verify,
        follow_redirects=True,
        http2=False,
    )

SyncPostgrestClient.create_session = _create_session_no_http2

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
