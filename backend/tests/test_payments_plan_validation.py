"""Defense-in-depth: payments.validate_plan_id must keep rejecting "free" as
a purchasable plan_id, independent of whatever the /upgrade frontend does or
doesn't render. See backend/app/routers/plans.py get_my_plan for the
frontend-facing half of this contract (Free is never is_purchasable)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.routers.payments import validate_plan_id  # noqa: E402


def test_validate_plan_id_rejects_free():
    with pytest.raises(HTTPException) as exc_info:
        validate_plan_id("free")
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize("plan_id", ["basic", "pro", "elite"])
def test_validate_plan_id_accepts_paid_plans(plan_id):
    assert validate_plan_id(plan_id) == plan_id


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [f for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
