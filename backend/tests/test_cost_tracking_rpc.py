"""
Verifies _increment_session_cost_sync calls the atomic increment_session_cost
RPC with correctly-mapped params instead of doing a read-modify-write.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import cost_tracking


class FakeRpc:
    def __init__(self, calls):
        self.calls = calls

    def execute(self):
        return None


class FakeSupabase:
    def __init__(self):
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return FakeRpc(self.calls)


def test_increment_session_cost_sync_calls_rpc_with_mapped_params(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(cost_tracking, "get_supabase", lambda: fake)

    cost_tracking._increment_session_cost_sync(
        42, "openai", realtime_cost_usd=0.001, tts_cost_usd=0.002
    )

    assert len(fake.calls) == 1
    name, params = fake.calls[0]
    assert name == "increment_session_cost"
    assert params == {
        "p_session_id": 42,
        "p_provider": "openai",
        "p_realtime_delta": 0.001,
        "p_tts_delta": 0.002,
    }


def test_increment_session_cost_sync_rejects_unknown_column(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(cost_tracking, "get_supabase", lambda: fake)

    try:
        cost_tracking._increment_session_cost_sync(42, None, bogus_cost_usd=1.0)
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert fake.calls == []
