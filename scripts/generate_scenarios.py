"""
Batch-generate additional speaking scenarios to grow the library toward
100+. Uses your configured OPENROUTER_API_KEY/GEMINI_API_KEY (real, cheap
AI calls) and writes real rows to your Supabase `scenarios` table.

Usage (from the backend/ directory, with your venv active):
    python ../scripts/generate_scenarios.py --specialties general --per-cell 1 --dry-run
    python ../scripts/generate_scenarios.py --per-cell 3

Idempotent by title -- safe to re-run if it's interrupted partway.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.generate_scenario_library import (  # noqa: E402
    generate_speaking_library,
    SPECIALTIES,
    DIFFICULTIES,
)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--per-cell", type=int, default=3,
        help="How many scenarios to generate per specialty/difficulty combination",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate and validate but don't write to Supabase",
    )
    parser.add_argument(
        "--specialties", type=str, default=None,
        help=f"Comma-separated subset of specialties (default: all {len(SPECIALTIES)})",
    )
    args = parser.parse_args()

    specialties = args.specialties.split(",") if args.specialties else SPECIALTIES

    print(
        f"Generating {args.per_cell} scenario(s) per specialty x difficulty "
        f"({len(specialties)} specialties x {len(DIFFICULTIES)} difficulties = "
        f"up to {len(specialties) * len(DIFFICULTIES) * args.per_cell} scenarios)"
        f"{' [DRY RUN -- nothing will be saved]' if args.dry_run else ''}...\n"
    )

    result = await generate_speaking_library(
        specialties=specialties,
        difficulties=DIFFICULTIES,
        per_cell=args.per_cell,
        dry_run=args.dry_run,
    )

    print(f"\nCreated: {result['created']}, Failed/skipped: {result['failed']}")
    if result["titles"]:
        print("\nTitles:")
        for t in result["titles"]:
            print(f"  - {t}")


if __name__ == "__main__":
    asyncio.run(main())
