"""The management commands that build the demo data (and the Vercel bundle)."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from Authentication.demo import DEMO_HOST_PHONE, DEMO_PARKER_PHONE, demo_accounts
from Authentication.models import Landlord, Parker, is_hashed
from parker_main.models import Booking, ParkingSpot, Review

pytestmark = pytest.mark.django_db


def run(*args, **kwargs):
    out = StringIO()
    call_command(*args, stdout=out, **kwargs)
    return out.getvalue()


def test_seed_chennai_is_idempotent():
    assert "Added 32" in run("seed_chennai")
    assert "Added 0" in run("seed_chennai")
    spots = ParkingSpot.objects.all()
    assert spots.count() == 32
    assert all(s.photo.name.endswith(".svg") for s in spots)
    assert all(12.8 < s.latitude < 13.2 and 80.0 < s.longitude < 80.35 for s in spots)   # all inside Chennai
    assert Review.objects.exists()


def test_seed_demo_and_reset():
    run("seed_demo")
    host = Landlord.objects.get(phone=DEMO_HOST_PHONE)
    parker = Parker.objects.get(phone=DEMO_PARKER_PHONE)
    assert host.spots.count() == 3 and host.check_pin("1234") and parker.check_pin("1234")

    parker.bookings.update(status=Booking.CANCELLED)          # a visitor clicks around...
    run("seed_demo", reset=True)
    assert parker.bookings.filter(status=Booking.CONFIRMED, start__gt=timezone.now()).exists()
    assert host.spots.count() == 3


def test_demo_accounts_refresh_when_stale():
    accounts = demo_accounts()                                  # seeds on first use
    Booking.objects.filter(spot__landlord=accounts["landlord"]).update(start=timezone.now() - timezone.timedelta(days=30))
    demo_accounts()                                             # all in the past -> re-seeded
    assert Booking.objects.filter(spot__landlord=accounts["landlord"], start__gt=timezone.now()).exists()


def test_generate_spot_images_keeps_real_photos(make_spot):
    spot = make_spot()
    assert "for 1 spot" in run("generate_spot_images")
    assert "for 0 spot" in run("generate_spot_images")          # nothing left to do
    spot.refresh_from_db()
    assert spot.photo.name.endswith(".svg")


def test_import_landlords_from_csv():
    output = run("import_landlords")
    assert "Imported" in output
    host = Landlord.objects.first()
    assert host is not None and is_hashed(host.pin)
    assert ParkingSpot.objects.count() == Landlord.objects.exclude(latitude=None).count()
    assert "Imported 0" in run("import_landlords")               # re-running skips existing hosts
