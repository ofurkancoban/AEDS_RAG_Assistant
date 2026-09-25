"""Metadata filter construction for Chroma queries."""

import pytest

from db.chroma_client import _where


def test_the_approved_scope_is_always_applied():
    # Unapproved chunks must never be reachable by any search, filtered or not.
    assert _where(None) == {"status": "approved"}


def test_a_single_condition_stays_a_plain_mapping():
    assert _where({}) == {"status": "approved"}


def test_extra_conditions_are_wrapped_for_chroma():
    result = _where({"source_id": "catalog"})

    # Chroma rejects a mapping with more than one key ("Expected where to have
    # exactly one operator"), which made every source-filtered chat request
    # fail with a 500. The UI never sends one, so nothing surfaced it.
    # Order inside $and carries no meaning, so it is not asserted.
    assert sorted(result["$and"], key=str) == sorted(
        [{"status": "approved"}, {"source_id": "catalog"}], key=str
    )


def test_the_caller_cannot_widen_the_approved_scope():
    # A caller-supplied status must not be able to pull unapproved or
    # deprecated chunks back into retrieval.
    assert _where({"status": "deprecated"}) == {"status": "approved"}
    assert {"status": "approved"} in _where({"status": "pending", "source_id": "x"})["$and"]
    assert {"status": "pending"} not in _where({"status": "pending", "source_id": "x"})["$and"]


@pytest.mark.parametrize("filter_", [None, {}, {"source_id": "x"}, {"source_id": "x", "page": 2}])
def test_every_shape_is_something_chroma_accepts(filter_):
    result = _where(filter_)
    # Either exactly one key, or the $and operator - the two forms Chroma
    # validates successfully.
    assert len(result) == 1
