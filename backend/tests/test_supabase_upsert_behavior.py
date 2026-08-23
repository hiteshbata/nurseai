"""Pins the actual behavior of postgrest-py 0.16.11 (pulled in by
supabase==2.5.3, see requirements.txt) for composite-key upsert, since
skill_graph._record_sync relies on it and the wrong assumption here silently
breaks every module's write path. Verified against source at
venv/Lib/site-packages/postgrest/base_request_builder.py -- do not assume,
this asserts the real request the client builds."""
from postgrest.base_request_builder import pre_upsert
from postgrest.types import ReturnMethod


def test_on_conflict_is_passed_through_verbatim_as_column_list():
    # PostgREST matches this comma-joined list against a table's unique/
    # exclusion constraint by column set (order-independent) -- a composite
    # target like "user_id,product,skill_tag" is not special-cased, it's
    # just a string.
    method, params, headers, json = pre_upsert(
        [{"user_id": "u1", "product": "OET", "skill_tag": "reading:B", "attempts": 1, "ema_score": 4.5}],
        count=None,
        returning=ReturnMethod.representation,
        ignore_duplicates=False,
        on_conflict="user_id,product,skill_tag",
    )
    assert params["on_conflict"] == "user_id,product,skill_tag"


def test_upsert_resolution_header_is_merge_not_ignore():
    # ignore_duplicates=False (the default skill_graph relies on) must
    # produce "merge-duplicates" -- an existing row's non-key columns get
    # updated, not skipped.
    _, _, headers, _ = pre_upsert(
        [{"user_id": "u1", "product": "OET", "skill_tag": "reading:B"}],
        count=None,
        returning=ReturnMethod.representation,
        ignore_duplicates=False,
        on_conflict="user_id,product,skill_tag",
    )
    assert "resolution=merge-duplicates" in headers["Prefer"]


def test_batch_columns_param_is_the_union_of_row_keys():
    # A column absent from a row's dict is absent from the "columns" query
    # param -- and therefore NOT part of the INSERT or the ON CONFLICT DO
    # UPDATE SET. If a row omitted "product", PostgREST would fall back to
    # the column default on insert and leave it untouched on update. This is
    # why _record_sync must set "product" on every row explicitly.
    _, params, _, _ = pre_upsert(
        [
            {"user_id": "u1", "product": "OET", "skill_tag": "reading:B", "attempts": 1, "ema_score": 4.5},
            {"user_id": "u1", "product": "OET", "skill_tag": "reading:C", "attempts": 1, "ema_score": 3.0},
        ],
        count=None,
        returning=ReturnMethod.representation,
        ignore_duplicates=False,
        on_conflict="user_id,product,skill_tag",
    )
    columns = set(c.strip('"') for c in params["columns"].split(","))
    assert columns == {"user_id", "product", "skill_tag", "attempts", "ema_score"}
