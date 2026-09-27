"""The booking rules: overlap, capacity, pricing and a booking's lifecycle."""
from datetime import timedelta

from decimal import Decimal

import pytest
from django.utils import timezone

from parker_main.forms import BookingForm
from parker_main.models import Booking

pytestmark = pytest.mark.django_db

H = timedelta(hours=1)


def errors_text(form):
    return " ".join(e for errs in form.errors.values() for e in errs)


@pytest.fixture
def base():
    """A fixed reference time, tomorrow at 10:00, so the windows below read like a timetable."""
    return (timezone.localtime() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)


# Existing booking: 10:00-12:00. Can a second car fit in a one-slot spot?
@pytest.mark.parametrize("start_h, hours, fits", [
    (8, 2, True),     # 08-10 ends exactly when it starts
    (12, 2, True),    # 12-14 starts exactly when it ends
    (9, 2, False),    # 09-11 overlaps the start
    (11, 2, False),   # 11-13 overlaps the end
    (10, 2, False),   # identical window
    (9, 4, False),    # 09-13 covers it entirely
    (10.5, 1, False), # 10:30-11:30 inside it
])
def test_overlap_edges(make_spot, make_parker, make_booking, base, start_h, hours, fits):
    spot = make_spot(capacity=1)
    make_booking(make_parker(), spot, start=base, hours=2)
    start = base + (start_h - 10) * H
    assert (spot.free_slots(start, start + hours * H) > 0) == fits


@pytest.mark.parametrize("capacity, existing, free", [(1, 1, 0), (2, 1, 1), (3, 2, 1), (3, 3, 0)])
def test_capacity(make_spot, make_parker, make_booking, base, capacity, existing, free):
    spot = make_spot(capacity=capacity)
    for _ in range(existing):
        make_booking(make_parker(), spot, start=base)
    assert spot.free_slots(base, base + 2 * H) == free


@pytest.mark.parametrize("status, counts", [
    (Booking.PENDING, True), (Booking.CONFIRMED, True),
    (Booking.REJECTED, False), (Booking.CANCELLED, False),
])
def test_only_live_bookings_take_a_slot(make_spot, make_parker, make_booking, base, status, counts):
    spot = make_spot(capacity=1)
    make_booking(make_parker(), spot, start=base, status=status)
    assert (spot.free_slots(base, base + H) == 0) == counts


@pytest.mark.parametrize("rate, hours, total", [("40", 1, 40), ("40", 3, 120), ("55.50", 2, 111), ("100", 24, 2400)])
def test_price(make_spot, parker, base, rate, hours, total):
    spot = make_spot(hourly_rate=Decimal(rate))
    form = BookingForm({"start": base.strftime("%Y-%m-%dT%H:%M"), "hours": hours}, spot=spot, parker=parker)
    assert form.is_valid(), form.errors
    assert form.save().total_price == total


@pytest.mark.parametrize("instant, status", [(True, Booking.CONFIRMED), (False, Booking.PENDING)])
def test_instant_book_decides_initial_status(make_spot, parker, base, instant, status):
    spot = make_spot(instant_book=instant)
    form = BookingForm({"start": base.strftime("%Y-%m-%dT%H:%M"), "hours": 1}, spot=spot, parker=parker)
    assert form.is_valid()
    assert form.save().status == status


@pytest.mark.parametrize("change, message", [
    ({"start_offset": timedelta(hours=-3)}, "future"),
    ({"start_offset": timedelta(days=90)}, "60 days"),
    ({"is_active": False}, "isn't taking bookings"),
    ({"accepts_car": False}, "doesn't accept cars"),
])
def test_booking_form_rejections(make_spot, parker, change, message):
    spot = make_spot(is_active=change.get("is_active", True), accepts_car=change.get("accepts_car", True))
    start = timezone.localtime() + change.get("start_offset", timedelta(days=1))
    form = BookingForm({"start": start.strftime("%Y-%m-%dT%H:%M"), "hours": 1}, spot=spot, parker=parker)
    assert not form.is_valid()
    assert message in errors_text(form)


def test_a_driver_cannot_double_book_themselves(make_spot, parker, make_booking, base):
    make_booking(parker, make_spot(), start=base)
    other_spot = make_spot()
    form = BookingForm({"start": base.strftime("%Y-%m-%dT%H:%M"), "hours": 1}, spot=other_spot, parker=parker)
    assert not form.is_valid()
    assert "already have a booking" in errors_text(form)


@pytest.mark.parametrize("start_offset, status, phase, can_cancel, can_review", [
    (timedelta(hours=5), Booking.CONFIRMED, "upcoming", True, False),
    (timedelta(hours=-1), Booking.CONFIRMED, "active", False, False),
    (timedelta(hours=-5), Booking.CONFIRMED, "completed", False, True),
    (timedelta(hours=5), Booking.PENDING, "pending", True, False),
    (timedelta(hours=5), Booking.REJECTED, "rejected", False, False),
    (timedelta(hours=-5), Booking.CANCELLED, "cancelled", False, False),
])
def test_booking_lifecycle(make_spot, parker, make_booking, start_offset, status, phase, can_cancel, can_review):
    b = make_booking(parker, make_spot(), start=timezone.now() + start_offset, hours=2, status=status)
    assert (b.phase, b.can_cancel, b.can_review) == (phase, can_cancel, can_review)


def test_booking_code_format(make_spot, parker, make_booking):
    b = make_booking(parker, make_spot())
    assert b.code == f"PM-{b.pk:05d}"
