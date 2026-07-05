"""
One-time setup: create the Razorpay Plan objects that back auto-renew
subscriptions (Basic/Pro/Elite, monthly, INR).

This is NOT run automatically by the app -- it's a manual, one-time step
you run yourself against your own Razorpay account, since it requires a
business decision (which plans, what pricing) and creates live objects
in your account.

Prerequisites:
  - Your Razorpay account must have the Subscriptions feature enabled
    (Dashboard -> Subscriptions; if you don't see it, contact Razorpay
    support to have it turned on for your account -- this can require
    additional business verification beyond basic payment acceptance).
  - RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET must already be set in
    backend/.env (the same credentials used for one-off orders work
    here too).

Usage (from the backend/ directory, with your venv active):
    python ../scripts/create_razorpay_plans.py

Idempotent: checks existing plans (via notes.plan_id) before creating a
new one, so re-running after a partial failure won't create duplicates.

After running, paste the printed ids into backend/.env:
    RAZORPAY_PLAN_ID_BASIC=plan_xxxxxxxxxxxxx
    RAZORPAY_PLAN_ID_PRO=plan_xxxxxxxxxxxxx
    RAZORPAY_PLAN_ID_ELITE=plan_xxxxxxxxxxxxx
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import razorpay  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.plans import PLANS  # noqa: E402

PLANS_TO_CREATE = ["basic", "pro", "elite"]


def find_existing_plan(client, plan_id: str):
    """Page through existing plans looking for one already tagged with
    notes.plan_id == plan_id, so re-running this script is safe."""
    skip = 0
    page_size = 100
    while True:
        page = client.plan.all({"count": page_size, "skip": skip})
        items = page.get("items", [])
        if not items:
            return None
        for item in items:
            if (item.get("notes") or {}).get("plan_id") == plan_id:
                return item
        if len(items) < page_size:
            return None
        skip += page_size


def main():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        print("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set in backend/.env -- aborting.")
        sys.exit(1)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    plans_by_id = {p["id"]: p for p in PLANS}

    print(f"Creating Razorpay plans against key {settings.RAZORPAY_KEY_ID[:12]}...\n")

    results = {}
    for plan_id in PLANS_TO_CREATE:
        plan = plans_by_id[plan_id]

        existing = find_existing_plan(client, plan_id)
        if existing:
            print(f"[SKIP] {plan_id} already exists -> {existing['id']}")
            results[plan_id] = existing["id"]
            continue

        try:
            created = client.plan.create({
                "period": "monthly",
                "interval": 1,
                "item": {
                    "name": f"NurseAI {plan['name']}",
                    "amount": plan["price"] * 100,
                    "currency": "INR",
                    "description": plan["description"],
                },
                "notes": {"plan_id": plan_id},
            })
        except Exception as e:
            print(f"[FAILED] {plan_id}: {e}")
            continue

        print(f"[OK] {plan_id} (Rs.{plan['price']}/month) -> {created['id']}")
        results[plan_id] = created["id"]

    print("\nPaste these into backend/.env:")
    for plan_id in PLANS_TO_CREATE:
        env_var = f"RAZORPAY_PLAN_ID_{plan_id.upper()}"
        print(f"  {env_var}={results.get(plan_id, '<FAILED - see above>')}")


if __name__ == "__main__":
    main()
