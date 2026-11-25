import datetime as dt
import zoneinfo
from dataclasses import replace

import astral.sun
import pytest
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    _POLAR_SUN_EVENT_OFFSET,
    RampSchedule,
    SunEvent,
    SunEvents,
    SunLightSettings,
    clamp,
)

# Create a mock astral location object (its `.observer` is passed to `SunEvents`)
location = Location(LocationInfo())

LAT_LONG_TZS = [
    (52.379189, 4.899431, "Europe/Amsterdam"),
    (32.87336, -117.22743, "US/Pacific"),
    (60, 50, "GMT"),
    (60, 50, "UTC"),
]


@pytest.fixture(params=LAT_LONG_TZS)
def tzinfo_and_location(request):
    lat, long, timezone = request.param
    tzinfo = zoneinfo.ZoneInfo(timezone)
    location = Location(
        LocationInfo(
            name="name",
            region="region",
            timezone=timezone,
            latitude=lat,
            longitude=long,
        ),
    )
    return tzinfo, location


def test_replace_time(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )

    new_time = dt.time(5, 30)
    datetime = dt.datetime(2022, 1, 1)
    replaced_time_utc = sun_events._replace_time(datetime.date(), new_time)
    assert replaced_time_utc.astimezone(tzinfo).time() == new_time


def test_sunrise_without_offset(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location

    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1).date()
    result = sun_events.sunrise(date)
    assert result == location.sunrise(date)


def test_sun_position_no_fixed_sunset_and_sunrise(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1).date()
    sunset = location.sunset(date)
    position = sun_events.sun_position(sunset)
    assert position == 0
    sunrise = location.sunrise(date)
    position = sun_events.sun_position(sunrise)
    assert position == 0
    noon = location.noon(date)
    position = sun_events.sun_position(noon)
    assert position == 1
    midnight = location.midnight(date)
    position = sun_events.sun_position(midnight)
    assert position == -1


def test_sun_position_fixed_sunset_and_sunrise(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=dt.time(6, 0),
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=dt.time(18, 0),
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1).date()
    sunset = sun_events.sunset(date)
    position = sun_events.sun_position(sunset)
    assert position == 0
    sunrise = sun_events.sunrise(date)
    position = sun_events.sun_position(sunrise)
    assert position == 0
    noon, midnight = sun_events.noon_and_midnight(date)
    position = sun_events.sun_position(noon)
    assert position == 1
    position = sun_events.sun_position(midnight)
    assert position == -1


def test_noon_and_midnight(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1)
    noon, midnight = sun_events.noon_and_midnight(date)
    assert noon == location.noon(date)
    assert midnight == location.midnight(date)


@pytest.mark.parametrize("day", [dt.date(2026, 4, 17), dt.date(2026, 8, 30)])
def test_midnight_falls_in_the_night_it_belongs_to(day):
    """Derived midnight must lie between sunset and the next sunrise (#1599)."""
    location = Location(
        LocationInfo(
            name="name",
            region="region",
            timezone="UTC",
            latitude=51.5,
            longitude=0.0,  # on the prime meridian
        ),
    )
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=dt.time(8, 0),
        sunset_time=None,
        min_sunset_time=dt.time(17, 0),
        max_sunset_time=dt.time(20, 0),
        timezone=zoneinfo.ZoneInfo("UTC"),
    )
    date = dt.datetime.combine(day, dt.time(12), tzinfo=dt.UTC)
    sunset = sun_events.sunset(date)
    next_sunrise = sun_events.sunrise(date + dt.timedelta(days=1))
    _, midnight = sun_events.noon_and_midnight(date)
    assert sunset < midnight < next_sunrise

    just_after_sunset = sunset + dt.timedelta(minutes=40)
    events = sun_events.prev_and_next_events(just_after_sunset)
    assert [event for event, _ in events] == [SunEvent.SUNSET, SunEvent.MIDNIGHT]
    assert sun_events.sun_position(just_after_sunset) > -0.5


def test_sun_events(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )

    date = dt.datetime(2022, 1, 1)
    events = sun_events.sun_events(date)
    assert len(events) == 4
    assert (SunEvent.SUNRISE, location.sunrise(date).timestamp()) in events


def test_prev_and_next_events(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    datetime = dt.datetime(2022, 1, 1, 10, 0)
    after_sunrise = sun_events.sunrise(datetime.date()) + dt.timedelta(hours=1)
    prev_event, next_event = sun_events.prev_and_next_events(after_sunrise)
    assert prev_event[0] == SunEvent.SUNRISE
    assert next_event[0] == SunEvent.NOON


def test_closest_event(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    datetime = dt.datetime(2022, 1, 1, 6, 0)
    sunrise = sun_events.sunrise(datetime.date())
    event_name, ts = sun_events.closest_event(sunrise)
    assert event_name == SunEvent.SUNRISE
    assert ts == location.sunrise(sunrise.date()).timestamp()


def _make_brightness_settings(
    tzinfo,
    location,
    *,
    min_brightness,
    max_brightness,
    brightness_mode,
):
    """Build a SunLightSettings with only the fields brightness_pct() needs."""
    return SunLightSettings(
        name="test",
        astral_observer=location.observer,
        adapt_until_sleep=False,
        max_brightness=max_brightness,
        max_color_temp=6500,
        min_brightness=min_brightness,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=2000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode=brightness_mode,
        timezone=tzinfo,
    )


def test_clamp_handles_inverted_bounds():
    """A user can intentionally set min_brightness > max_brightness for an
    inverted timescale (#1421, e.g. a porch light that should be brighter at
    night than during the day). clamp() must still bound the value between
    whichever of the two is actually smaller/larger, not silently collapse
    to `minimum` for every input the way `max(minimum, min(value, maximum))`
    does when minimum > maximum.
    """
    assert clamp(50, 100, 15) == 50
    assert clamp(0, 100, 15) == 15
    assert clamp(200, 100, 15) == 100


def test_clamp_normal_bounds_unaffected():
    """The ordinary min <= max case must keep behaving exactly as before."""
    assert clamp(50, 0, 100) == 50
    assert clamp(-10, 0, 100) == 0
    assert clamp(150, 0, 100) == 100


@pytest.mark.parametrize("brightness_mode", ["linear", "tanh"])
def test_brightness_pct_varies_with_inverted_brightness_bounds(
    tzinfo_and_location,
    brightness_mode,
):
    """#1421: with min_brightness > max_brightness, linear/tanh modes got
    stuck returning min_brightness for every sample, because the final
    `clamp(brightness, self.min_brightness, self.max_brightness)` call
    collapsed to `minimum` regardless of the computed value. Sampling a few
    points around sunrise must show the brightness actually move instead of
    being pinned to one value.
    """
    tzinfo, location = tzinfo_and_location
    settings = _make_brightness_settings(
        tzinfo,
        location,
        min_brightness=100,
        max_brightness=15,
        brightness_mode=brightness_mode,
    )

    sunrise = location.sunrise(dt.datetime(2022, 6, 1).date())
    samples = [
        settings.brightness_pct(
            sunrise + dt.timedelta(minutes=offset),
            is_sleep=False,
        )
        for offset in (-20, -10, 0, 10, 20)
    ]

    assert len({round(value) for value in samples}) > 1, samples
    assert all(15 <= value <= 100 for value in samples), samples


@pytest.mark.parametrize("mode", ["linear", "tanh"])
@pytest.mark.parametrize("event", ["sunrise", "sunset"])
def test_temperature_ramp(tzinfo_and_location, mode, event):
    tzinfo, location = tzinfo_and_location
    settings = replace(
        _make_brightness_settings(
            tzinfo,
            location,
            min_brightness=10,
            max_brightness=90,
            brightness_mode="default",
        ),
        temperature_mode=mode,
    )
    event_time = getattr(settings.sun, event)(dt.date(2022, 6, 1))
    offsets = (-20, 40) if event == "sunrise" else (-40, 20)
    if event == "sunrise":
        schedule = replace(
            settings.temperature_schedule,
            sunrise_before=dt.timedelta(minutes=20),
            sunrise_end_time=(event_time + dt.timedelta(minutes=40))
            .astimezone(tzinfo)
            .time(),
        )
    else:
        schedule = replace(
            settings.temperature_schedule,
            sunset_before=dt.timedelta(minutes=40),
            sunset_end_time=(event_time + dt.timedelta(minutes=20))
            .astimezone(tzinfo)
            .time(),
        )
    settings = replace(settings, temperature_schedule=schedule)
    fractions = (0, 1)
    if event == "sunset":
        fractions = fractions[::-1]
    for offset, fraction in zip(offsets, fractions, strict=True):
        result = settings.brightness_and_color(
            event_time + dt.timedelta(minutes=offset),
            False,
        )
        assert result["color_temp_kelvin"] == 2000 + fraction * 4500


@pytest.mark.parametrize("mode", ["linear", "tanh", "brightness"])
def test_temperature_curve_with_inverted_bounds(tzinfo_and_location, mode):
    tzinfo, location = tzinfo_and_location
    settings = replace(
        _make_brightness_settings(
            tzinfo,
            location,
            min_brightness=10,
            max_brightness=90,
            brightness_mode="linear",
        ),
        temperature_mode=mode,
        min_color_temp=6500,
        max_color_temp=2000,
    )
    sunrise = settings.sun.sunrise(dt.date(2022, 6, 1))
    before = settings.brightness_and_color(sunrise - dt.timedelta(minutes=10), False)
    after = settings.brightness_and_color(sunrise + dt.timedelta(minutes=10), False)
    assert 2000 <= after["color_temp_kelvin"] < before["color_temp_kelvin"] <= 6500


@pytest.mark.parametrize("mode", ["default", "linear", "tanh"])
@pytest.mark.parametrize(("minimum", "maximum"), [(10, 90), (90, 10), (50, 50)])
def test_temperature_follows_brightness_curve(
    tzinfo_and_location,
    mode,
    minimum,
    maximum,
):
    tzinfo, location = tzinfo_and_location
    settings = replace(
        _make_brightness_settings(
            tzinfo,
            location,
            min_brightness=minimum,
            max_brightness=maximum,
            brightness_mode=mode,
        ),
        temperature_mode="brightness",
        temperature_schedule=RampSchedule(
            sunrise_before=dt.timedelta(hours=3),
            sunset_before=dt.timedelta(hours=4),
        ),
    )
    reference = replace(settings, min_brightness=0, max_brightness=100)
    for event in ("sunrise", "sunset"):
        event_time = getattr(settings.sun, event)(dt.date(2022, 6, 1))
        for offset in (-60, -15, 0, 15, 60):
            now = event_time + dt.timedelta(minutes=offset)
            fraction = reference.brightness_pct(now, False) / 100
            if minimum > maximum:
                fraction = 1 - fraction
            result = settings.brightness_and_color(now, False)
            assert result["color_temp_kelvin"] == 5 * round(
                (2000 + fraction * 4500) / 5,
            )


@pytest.mark.parametrize("mode", ["linear", "tanh", "brightness"])
def test_temperature_curve_overrides_until_sleep_not_sleep_mode(
    tzinfo_and_location,
    mode,
):
    tzinfo, location = tzinfo_and_location
    settings = replace(
        _make_brightness_settings(
            tzinfo,
            location,
            min_brightness=10,
            max_brightness=90,
            brightness_mode="linear",
        ),
        temperature_mode=mode,
        adapt_until_sleep=True,
        sleep_rgb_or_color_temp="rgb_color",
        sleep_color_temp=1000,
    )
    now = settings.sun.sunset(dt.date(2022, 6, 1)) + dt.timedelta(hours=2)
    result = settings.brightness_and_color(now, False)
    assert result["color_temp_kelvin"] >= settings.min_color_temp
    assert not result["force_rgb_color"]
    sleep = settings.brightness_and_color(now, True)
    assert sleep["color_temp_kelvin"] == 1000
    assert sleep["rgb_color"] == settings.sleep_rgb_color


@pytest.mark.parametrize("mode", ["linear", "tanh"])
def test_zero_duration_temperature_ramp(tzinfo_and_location, mode):
    tzinfo, location = tzinfo_and_location
    settings = replace(
        _make_brightness_settings(
            tzinfo,
            location,
            min_brightness=10,
            max_brightness=90,
            brightness_mode="default",
        ),
        temperature_mode=mode,
    )
    sunrise = settings.sun.sunrise(dt.date(2022, 6, 1))
    settings = replace(
        settings,
        temperature_schedule=replace(
            settings.temperature_schedule,
            sunrise_before=dt.timedelta(),
            sunrise_end_time=sunrise.astimezone(tzinfo).time(),
        ),
    )
    assert (
        settings.brightness_and_color(sunrise - dt.timedelta(seconds=1), False)[
            "color_temp_kelvin"
        ]
        == 2000
    )
    assert settings.brightness_and_color(sunrise, False)["color_temp_kelvin"] == 6500


def _fixed_ramp_settings(mode):
    settings = _make_brightness_settings(
        dt.UTC,
        location,
        min_brightness=10,
        max_brightness=90,
        brightness_mode=mode,
    )
    return replace(
        settings,
        sunrise_time=dt.time(6),
        sunset_time=dt.time(18),
        brightness_schedule=RampSchedule(),
    )


@pytest.mark.parametrize("mode", ["linear", "tanh"])
@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [(5, 0, 10), (7, 15, 50), (9, 30, 90), (17, 30, 90), (20, 15, 50), (23, 0, 10)],
)
def test_fixed_clock_brightness_ramp(mode, hour, minute, expected):
    settings = _fixed_ramp_settings(mode)
    now = dt.datetime(2022, 6, 1, hour, minute, tzinfo=dt.UTC)
    assert settings.brightness_pct(now, False) == pytest.approx(expected)


def test_tanh_uses_a_smooth_curve_between_exact_endpoints():
    now = dt.datetime(2022, 6, 1, 6, 7, 30, tzinfo=dt.UTC)
    linear = _fixed_ramp_settings("linear").brightness_pct(now, False)
    tanh = _fixed_ramp_settings("tanh").brightness_pct(now, False)
    assert 10 < tanh < linear


@pytest.mark.parametrize("mode", ["linear", "tanh"])
@pytest.mark.parametrize(
    ("end_field", "end_time", "hour", "minute", "expected"),
    [
        ("sunrise_end_time", dt.time(5, 30), 5, 30, 50),
        ("sunrise_end_time", dt.time(5, 30), 6, 0, 90),
        ("sunset_end_time", dt.time(17), 17, 45, 50),
        ("sunset_end_time", dt.time(17), 18, 0, 10),
    ],
)
def test_ramp_end_clamped_to_later_sun_event(
    mode, end_field, end_time, hour, minute, expected,
):
    settings = _fixed_ramp_settings(mode)
    settings = replace(
        settings,
        brightness_schedule=replace(
            settings.brightness_schedule, **{end_field: end_time},
        ),
    )
    now = dt.datetime(2022, 6, 1, hour, minute, tzinfo=dt.UTC)
    assert settings.brightness_pct(now, False) == pytest.approx(expected)


@pytest.mark.parametrize("mode", ["linear", "tanh"])
def test_sunset_ramp_completes_after_midnight(mode):
    settings = _fixed_ramp_settings(mode)
    settings = replace(
        settings,
        brightness_schedule=replace(
            settings.brightness_schedule,
            sunset_end_time=dt.time(1),
        ),
    )
    assert (
        settings.brightness_pct(dt.datetime(2022, 6, 2, 0, 30, tzinfo=dt.UTC), False)
        > 10
    )
    assert (
        settings.brightness_pct(dt.datetime(2022, 6, 2, 1, tzinfo=dt.UTC), False) == 10
    )


def test_brightness_and_temperature_have_independent_schedules():
    settings = replace(
        _fixed_ramp_settings("linear"),
        temperature_mode="linear",
        temperature_schedule=RampSchedule(
            sunrise_before=dt.timedelta(hours=2),
            sunrise_end_time=dt.time(8),
            sunset_before=dt.timedelta(hours=1),
            sunset_end_time=dt.time(20),
        ),
    )
    now = dt.datetime(2022, 6, 1, 7, tzinfo=dt.UTC)
    values = settings.brightness_and_color(now, False)
    assert values["brightness_pct"] == pytest.approx(10 + 80 * 2 / 4.5)
    assert values["color_temp_kelvin"] == 5375


def test_ramp_clock_time_uses_local_timezone_across_dst():
    zone = zoneinfo.ZoneInfo("America/New_York")
    settings = replace(
        _fixed_ramp_settings("linear"),
        timezone=zone,
        sunrise_time=dt.time(3),
        brightness_schedule=RampSchedule(
            sunrise_before=dt.timedelta(hours=2),
            sunrise_end_time=dt.time(4),
        ),
    )
    assert settings.brightness_pct(
        dt.datetime(2022, 3, 13, 1, 30, tzinfo=zone),
        False,
    ) == pytest.approx(50)
    assert (
        settings.brightness_pct(dt.datetime(2022, 3, 13, 4, tzinfo=zone), False) == 90
    )


def test_virtual_sunset_after_midnight_uses_same_day_end():
    settings = replace(
        _fixed_ramp_settings("linear"),
        sunrise_time=dt.time(16),
        sunset_time=dt.time(4),
        brightness_schedule=RampSchedule(
            sunrise_before=dt.timedelta(),
            sunrise_end_time=dt.time(22),
            sunset_before=dt.timedelta(hours=6),
            sunset_end_time=dt.time(4),
        ),
    )
    assert (
        settings.brightness_pct(dt.datetime(2022, 6, 1, 16, tzinfo=dt.UTC), False) == 10
    )
    assert (
        settings.brightness_pct(dt.datetime(2022, 6, 1, 22, tzinfo=dt.UTC), False) == 90
    )
    assert (
        settings.brightness_pct(dt.datetime(2022, 6, 2, 4, tzinfo=dt.UTC), False) == 10
    )


# Tromsø, Norway (69.6°N) has polar night (Nov-Jan) and midnight sun (May-Jul).
TROMSO = Location(
    LocationInfo(
        name="Tromsø",
        region="Norway",
        timezone="Europe/Oslo",
        latitude=69.6489,
        longitude=18.9551,
    ),
)
POLAR_NIGHT_DATE = dt.date(2026, 1, 7)
MIDNIGHT_SUN_DATE = dt.date(2026, 7, 7)
MCMURDO = Location(
    LocationInfo(
        name="McMurdo Station",
        region="Antarctica",
        timezone="Antarctica/McMurdo",
        latitude=-77.8419,
        longitude=166.6863,
    ),
)


def _polar_sun_events(location=TROMSO, **kwargs):
    defaults = {
        "name": "test",
        "astral_observer": location.observer,
        "sunrise_time": None,
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": None,
        "min_sunset_time": None,
        "max_sunset_time": None,
        "timezone": zoneinfo.ZoneInfo(location.timezone),
    }
    return SunEvents(**{**defaults, **kwargs})


def test_polar_night_synthesizes_short_day():
    # `astral` cannot compute sunrise/sunset (the sun never rises), see #1485
    with pytest.raises(ValueError):  # noqa: PT011
        astral.sun.sunrise(TROMSO.observer, POLAR_NIGHT_DATE)
    sun_events = _polar_sun_events()
    noon = astral.sun.noon(TROMSO.observer, POLAR_NIGHT_DATE)
    assert sun_events.sunrise(POLAR_NIGHT_DATE) == noon - _POLAR_SUN_EVENT_OFFSET
    assert sun_events.sunset(POLAR_NIGHT_DATE) == noon + _POLAR_SUN_EVENT_OFFSET


def test_midnight_sun_synthesizes_short_night():
    # `astral` cannot compute sunrise/sunset (the sun never sets), see #1485
    with pytest.raises(ValueError):  # noqa: PT011
        astral.sun.sunset(TROMSO.observer, MIDNIGHT_SUN_DATE)
    sun_events = _polar_sun_events()
    midnight = astral.sun.midnight(TROMSO.observer, MIDNIGHT_SUN_DATE)
    next_midnight = astral.sun.midnight(
        TROMSO.observer,
        MIDNIGHT_SUN_DATE + dt.timedelta(days=1),
    )
    assert sun_events.sunrise(MIDNIGHT_SUN_DATE) == midnight + _POLAR_SUN_EVENT_OFFSET
    assert (
        sun_events.sunset(MIDNIGHT_SUN_DATE) == next_midnight - _POLAR_SUN_EVENT_OFFSET
    )


@pytest.mark.parametrize(
    ("date", "midnight_sun"),
    [(dt.date(2026, 1, 7), True), (dt.date(2026, 7, 7), False)],
)
def test_polar_fallback_handles_southern_hemisphere(date, midnight_sun):
    sun_events = _polar_sun_events(MCMURDO)
    noon = astral.sun.noon(MCMURDO.observer, date)
    midnight = astral.sun.midnight(MCMURDO.observer, date)
    next_midnight = astral.sun.midnight(MCMURDO.observer, date + dt.timedelta(days=1))

    if midnight_sun:
        assert sun_events.sunrise(date) == midnight + _POLAR_SUN_EVENT_OFFSET
        assert sun_events.sunset(date) == next_midnight - _POLAR_SUN_EVENT_OFFSET
    else:
        assert sun_events.sunrise(date) == noon - _POLAR_SUN_EVENT_OFFSET
        assert sun_events.sunset(date) == noon + _POLAR_SUN_EVENT_OFFSET


def test_boundary_day_with_real_sunrise_and_synthetic_sunset():
    # At the start of the midnight sun period, `astral` computes a real
    # sunrise for this date but raises for sunset (this exact date depends on
    # astral's numerics). The synthetic sunset must stay consistent with the
    # nearly 24-hour day instead of collapsing into a polar-night day.
    date = dt.date(2026, 5, 18)
    astral.sun.sunrise(TROMSO.observer, date)  # does not raise
    with pytest.raises(ValueError):  # noqa: PT011
        astral.sun.sunset(TROMSO.observer, date)
    sun_events = _polar_sun_events()
    day_length = sun_events.sunset(date) - sun_events.sunrise(date)
    assert day_length > dt.timedelta(hours=22)


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
def test_sun_position_on_polar_days(date):
    sun_events = _polar_sun_events()
    datetime = dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc)
    noon, midnight = sun_events.noon_and_midnight(datetime)
    assert sun_events.sun_position(noon) == 1
    assert sun_events.sun_position(midnight) == -1
    assert sun_events.sun_position(sun_events.sunrise(date)) == 0
    assert sun_events.sun_position(sun_events.sunset(date)) == 0


def test_polar_night_min_max_times_shape_the_synthetic_day():
    # The (min/max)_(sunrise/sunset)_time options apply on top of the
    # synthetic sun events, so users can still shape their schedule.
    sun_events = _polar_sun_events(
        max_sunrise_time=dt.time(9, 0),
        min_sunset_time=dt.time(17, 0),
        timezone=dt.timezone.utc,
    )
    expected_sunrise = dt.datetime(2026, 1, 7, 9, 0, tzinfo=dt.timezone.utc)
    expected_sunset = dt.datetime(2026, 1, 7, 17, 0, tzinfo=dt.timezone.utc)
    assert sun_events.sunrise(POLAR_NIGHT_DATE) == expected_sunrise
    assert sun_events.sunset(POLAR_NIGHT_DATE) == expected_sunset


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
@pytest.mark.parametrize(
    ("sunrise_offset", "sunset_offset"),
    [
        (dt.timedelta(hours=-20), dt.timedelta(hours=-20)),
        (dt.timedelta(hours=-20), dt.timedelta(hours=20)),
        (dt.timedelta(hours=20), dt.timedelta(hours=-20)),
        (dt.timedelta(hours=20), dt.timedelta(hours=20)),
    ],
)
def test_polar_offsets_cannot_invert_event_order(
    date,
    sunrise_offset,
    sunset_offset,
):
    sun_events = _polar_sun_events(
        sunrise_offset=sunrise_offset,
        sunset_offset=sunset_offset,
    )

    events = dict(
        sun_events.sun_events(dt.datetime.combine(date, dt.time(), tzinfo=dt.UTC)),
    )
    midnight = dt.datetime.fromtimestamp(events[SunEvent.MIDNIGHT], tz=dt.UTC)
    next_midnight = astral.sun.midnight(TROMSO.observer, date + dt.timedelta(days=1))
    noon = dt.datetime.fromtimestamp(events[SunEvent.NOON], tz=dt.UTC)
    sunrise = dt.datetime.fromtimestamp(events[SunEvent.SUNRISE], tz=dt.UTC)
    sunset = dt.datetime.fromtimestamp(events[SunEvent.SUNSET], tz=dt.UTC)

    assert midnight < sunrise < noon < sunset < next_midnight


def test_polar_fallback_applies_offsets_within_solar_anchors():
    offset = dt.timedelta(minutes=15)
    plain = _polar_sun_events()
    shifted = _polar_sun_events(
        sunrise_offset=offset,
        sunset_offset=offset,
    )

    assert (
        shifted.sunrise(MIDNIGHT_SUN_DATE) - plain.sunrise(MIDNIGHT_SUN_DATE) == offset
    )
    assert shifted.sunset(MIDNIGHT_SUN_DATE) - plain.sunset(MIDNIGHT_SUN_DATE) == offset


def test_sun_position_all_year_in_polar_region():
    # Covers the transitions into and out of polar night and midnight sun;
    # `sun_position` internally validates the order of the sun events.
    sun_events = _polar_sun_events()
    datetime = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    while datetime < end:
        position = sun_events.sun_position(datetime)
        assert -1 <= position <= 1
        datetime += dt.timedelta(hours=8)


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
def test_brightness_and_color_on_polar_days(date):
    settings = SunLightSettings(
        name="test",
        astral_observer=TROMSO.observer,
        adapt_until_sleep=False,
        max_brightness=100,
        max_color_temp=5500,
        min_brightness=30,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=zoneinfo.ZoneInfo("Europe/Oslo"),
    )
    datetime = dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc)
    noon, midnight = settings.sun.noon_and_midnight(datetime)
    at_noon = settings.brightness_and_color(noon, is_sleep=False)
    assert at_noon["brightness_pct"] == 100
    assert at_noon["color_temp_kelvin"] == 5500
    at_midnight = settings.brightness_and_color(midnight, is_sleep=False)
    assert at_midnight["brightness_pct"] == 30
    assert at_midnight["color_temp_kelvin"] == 2000
