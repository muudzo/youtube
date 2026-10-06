"""A video below the mid-roll threshold must not be published.

Mid-rolls unlock past 8 minutes and they are the entire revenue case for this
channel -- Shorts RPM is ~$0.02-0.12/1k. Publishing a 7:50 video spends an
upload slot, a cadence slot, and a topic on something that cannot earn. The
render is kept so it can be salvaged; only the upload is refused.
"""

import pytest

import scripts.nl.produce as produce_mod
from scripts.nl.produce import TooShortToMonetizeError


def test_threshold_is_the_eight_minute_midroll_line():
    # Arrange / Act / Assert
    assert produce_mod.MIN_MIDROLL_SECONDS == 8 * 60


@pytest.mark.parametrize("seconds", [0, 60, 479, 479.9])
def test_rejects_anything_under_eight_minutes(seconds):
    # Arrange / Act / Assert
    with pytest.raises(TooShortToMonetizeError, match="midroll"):
        produce_mod.assert_monetizable(seconds)


@pytest.mark.parametrize("seconds", [480, 481, 600, 1500])
def test_accepts_eight_minutes_and_over(seconds):
    # Arrange / Act
    result = produce_mod.assert_monetizable(seconds)

    # Assert
    assert result is None


def test_error_names_the_actual_duration_so_the_shortfall_is_visible():
    # Arrange / Act
    with pytest.raises(TooShortToMonetizeError) as excinfo:
        produce_mod.assert_monetizable(420)

    # Assert
    assert "7.0" in str(excinfo.value)
