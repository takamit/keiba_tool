from core import collector


def test_should_treat_as_no_race_day_when_primary_is_no_race() -> None:
    assert collector._should_treat_as_no_race_day("no_race", []) is True


def test_should_treat_as_no_race_day_when_primary_is_not_found_and_subs_are_safe() -> None:
    assert collector._should_treat_as_no_race_day(
        "not_found",
        ["not_found", "no_race", "unexpected", "empty"],
    ) is True


def test_should_not_treat_as_no_race_day_when_webdriver_error_exists() -> None:
    assert collector._should_treat_as_no_race_day(
        "not_found",
        ["not_found", "webdriver_error"],
    ) is False
