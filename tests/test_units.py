"""Pure logic: no requests, and mostly no database."""
import pytest

from Authentication.models import Parker, is_hashed, normalize_phone
from parker_main.illustrations import render_spot_svg, scene_for
from parker_main.models import ParkingSpot, haversine


@pytest.mark.parametrize("raw, expected", [
    ("9876543210", "9876543210"),
    ("+91 98765 43210", "9876543210"),
    ("919876543210", "9876543210"),
    ("98765-43210", "9876543210"),
    ("(+91) 98765.43210", "9876543210"),
    ("", ""),
    (None, ""),
    ("12345", "12345"),                     # too short: left for the form to reject
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


CHENNAI_CENTRAL = (13.0827, 80.2757)
T_NAGAR = (13.0418, 80.2337)


@pytest.mark.parametrize("a, b, km", [
    (CHENNAI_CENTRAL, CHENNAI_CENTRAL, 0),
    ((13.0, 80.0), (14.0, 80.0), 111.2),     # one degree of latitude
    (CHENNAI_CENTRAL, T_NAGAR, 6.4),
])
def test_haversine(a, b, km):
    assert haversine(*a, *b) == pytest.approx(km, abs=0.2)


def test_haversine_is_symmetric():
    assert haversine(*CHENNAI_CENTRAL, *T_NAGAR) == pytest.approx(haversine(*T_NAGAR, *CHENNAI_CENTRAL))


def test_pin_is_hashed_and_checked():
    p = Parker(phone="9000000000")
    p.set_pin("4321")
    assert is_hashed(p.pin) and "4321" not in p.pin
    assert p.check_pin("4321")
    assert not p.check_pin("1234")


@pytest.mark.parametrize("title, covered, scene", [
    ("Marina Beach evening parking", False, "beach"),
    ("Velachery 100 Ft Road basement", True, "basement"),
    ("Covered garage near Anna Nagar", True, "garage"),
    ("Thoraipakkam OMR stilt parking", False, "garage"),
    ("Ashok Nagar 4th Avenue driveway", False, "driveway"),
    ("Chennai Central quick-stop lot", False, "lot"),
    ("Some spot", True, "garage"),            # covered spots default to a garage scene
])
def test_scene_for(title, covered, scene):
    assert scene_for(ParkingSpot(title=title, description="", is_covered=covered)) == scene


def test_cover_art_is_deterministic_per_spot():
    a, b = ParkingSpot(pk=7, title="Lot"), ParkingSpot(pk=8, title="Lot")
    assert render_spot_svg(a) == render_spot_svg(a)
    assert render_spot_svg(a) != render_spot_svg(b)
    assert render_spot_svg(a).startswith("<svg") and render_spot_svg(a).endswith("</svg>")


@pytest.mark.parametrize("value, limit, expected", [
    ("13.0827", 90, "13.0827"),
    ("-62.88", 90, "-62.88"),
    ("", 90, None),
    ("Latitude", 90, None),        # a stray header row
    ("95.1", 90, None),            # out of range
    ("200", 180, None),
    ("179.9", 180, "179.9"),
])
def test_csv_coordinate_parsing(value, limit, expected):
    from Authentication.management.commands.import_landlords import _coordinate
    result = _coordinate(value, limit)
    assert (str(result) if result is not None else None) == expected
