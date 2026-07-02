"""One-off backfill: canonicalise evidence-answer casing in stored QA data.

The legacy data used lowercase "Yes w/ evidence" / "Yes w/o evidence" in BOTH
the stored answers and the migrated form definitions' option strings, while
the seeds use capital-E "Yes w/ Evidence" / "Yes w/o Evidence". Scoring is
case-insensitive so scores were never affected, but exact-match rendering and
any future re-seed depend on one canonical casing — this rewrites both sides:

- qa_project_responses: answer values (both {"value": ...} dict cells and raw
  string cells); timestamps and attribution are left untouched.
- qa_form_definitions: option strings and trigger_value in every section,
  question, and subform question.

Idempotent. Run (from projectqa-api/, with the cluster up):

    ./.venv/Scripts/python.exe -m scripts.backfill_answer_casing --dry-run
    ./.venv/Scripts/python.exe -m scripts.backfill_answer_casing
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal
from app.models.form import QaFormDefinition
from app.models.response import QaProjectResponse

_CANONICAL = {
    "yes w/ evidence": "Yes w/ Evidence",
    "yes w/o evidence": "Yes w/o Evidence",
}


def _canonical(value: Any) -> str | None:
    """The canonical replacement for ``value``, or None if no rewrite needed."""
    if not isinstance(value, str):
        return None
    fixed = _CANONICAL.get(value.strip().lower())
    return fixed if fixed is not None and fixed != value else None


def _canon_question(q: dict[str, Any]) -> int:
    """Canonicalise a question's options/trigger in place; return fix count."""
    fixes = 0
    opts = q.get("options")
    if isinstance(opts, list):
        for i, opt in enumerate(opts):
            fixed = _canonical(opt)
            if fixed is not None:
                opts[i] = fixed
                fixes += 1
    fixed = _canonical(q.get("trigger_value"))
    if fixed is not None:
        q["trigger_value"] = fixed
        fixes += 1
    sub = q.get("subform")
    if isinstance(sub, dict):
        for sq in sub.get("questions", []):
            if isinstance(sq, dict):
                fixes += _canon_question(sq)
    return fixes


async def run(dry_run: bool) -> None:
    counts: Counter[str] = Counter()
    rows_touched = 0
    option_fixes = 0
    forms_touched = 0
    async with SessionLocal() as session:
        rows = (await session.scalars(select(QaProjectResponse))).all()
        for row in rows:
            responses = row.responses or {}
            changed = False
            for key, cell in responses.items():
                if isinstance(cell, dict):
                    fixed = _canonical(cell.get("value"))
                    if fixed is not None:
                        cell["value"] = fixed
                        changed = True
                        counts[fixed] += 1
                else:
                    fixed = _canonical(cell)
                    if fixed is not None:
                        responses[key] = fixed
                        changed = True
                        counts[fixed] += 1
            if changed:
                rows_touched += 1
                flag_modified(row, "responses")

        forms = (await session.scalars(select(QaFormDefinition))).all()
        for form in forms:
            structure = form.structure or {}
            fixes = 0
            for section in structure.get("sections", []):
                for q in section.get("questions", []):
                    if isinstance(q, dict):
                        fixes += _canon_question(q)
            if fixes:
                forms_touched += 1
                option_fixes += fixes
                flag_modified(form, "structure")

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    mode = "DRY RUN — would rewrite" if dry_run else "rewrote"
    print(f"{mode} {sum(counts.values())} answers across {rows_touched} response rows")
    for value, n in sorted(counts.items()):
        print(f"  {value!r}: {n}")
    print(
        f"{mode} {option_fixes} option/trigger strings across "
        f"{forms_touched} form definitions"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canonicalise evidence answer casing in qa_project_responses"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change, write nothing"
    )
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
