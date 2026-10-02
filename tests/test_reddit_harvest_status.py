"""Arctic Shift harvest status: a down archive is blocked, and it must not wipe a prior harvest."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from fetch_reddit_arctic import decide_reddit_status  # noqa: E402


def test_five_failures_with_no_rows_is_blocked_and_keeps_previous():
    status, preserve = decide_reddit_status(
        status_page="up",
        rows_this_run=0,
        previous_rows=1777,
        error_count=5,
        stopped=True,
    )
    assert status == "blocked"
    assert preserve is True


def test_status_page_down_with_no_rows_is_blocked():
    status, preserve = decide_reddit_status(
        status_page="down",
        rows_this_run=0,
        previous_rows=0,
        error_count=0,
        stopped=False,
    )
    assert status == "blocked"
    assert preserve is False


def test_down_status_page_with_rows_still_ok():
    status, preserve = decide_reddit_status(
        status_page="down",
        rows_this_run=20,
        previous_rows=0,
        error_count=0,
        stopped=False,
    )
    assert status == "ok"
    assert preserve is False


def test_clean_empty_does_not_replace_a_larger_file():
    status, preserve = decide_reddit_status(
        status_page="up",
        rows_this_run=0,
        previous_rows=4000,
        error_count=0,
        stopped=False,
    )
    assert status == "empty"
    assert preserve is True


def test_partial_stop_does_not_shrink_the_harvest():
    status, preserve = decide_reddit_status(
        status_page="up",
        rows_this_run=3,
        previous_rows=4577,
        error_count=5,
        stopped=True,
    )
    assert status == "error"
    assert preserve is True
