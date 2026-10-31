from datetime import date

import pytest
from fastapi import HTTPException

from app.api.routes.analytics import date_window


def test_analytics_date_window_defaults_to_thirty_days():
    start, end = date_window(None, date(2026, 10, 31))
    assert start == date(2026, 10, 2)
    assert end == date(2026, 10, 31)


def test_analytics_date_window_allows_maximum_range_and_rejects_larger():
    assert date_window(date(2025, 10, 31), date(2026, 10, 31))[0] == date(2025, 10, 31)
    with pytest.raises(HTTPException) as too_wide:
        date_window(date(2025, 10, 30), date(2026, 10, 31))
    assert too_wide.value.status_code == 422
    with pytest.raises(HTTPException) as reversed_window:
        date_window(date(2026, 11, 1), date(2026, 10, 31))
    assert reversed_window.value.status_code == 422
