import socket

from supabase import create_client, Client
from app.core.config import settings

# Some networks (seen in local/sandboxed dev) hand back NAT64-synthesized
# IPv6 addresses for public hosts like *.supabase.co ahead of the working
# IPv4 ones, but never actually route them. socket.create_connection tries
# addresses sequentially with no Happy-Eyeballs racing, so every cold
# connection (first JWKS fetch, first REST call) stalls ~40s on the dead
# IPv6 entry before falling back to IPv4. Sorting IPv4 first removes the
# stall; real IPv6 connectivity still works exactly the same when reachable.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_first_getaddrinfo(*args, **kwargs):
    return sorted(_orig_getaddrinfo(*args, **kwargs), key=lambda r: r[0] != socket.AF_INET)


socket.getaddrinfo = _ipv4_first_getaddrinfo

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

def get_user_scoped_client(access_token: str) -> Client:
    """A fresh anon-key client whose PostgREST requests carry the caller's own
    JWT, so RLS evaluates auth.uid() as that user instead of bypassing it
    (service_role has BYPASSRLS). Only safe for tables with an authenticated
    RLS policy scoped to auth.uid() = user_id -- see
    backend/migrations/2026-08-02_authenticated_user_rls.sql for which ones.
    A new client per call (not a shared singleton) since the token is
    request-specific and clients aren't meant to swap identity mid-flight.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client
