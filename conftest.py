"""Shared pytest fixtures: users, spots, bookings and logged-in clients."""
from datetime import timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from Authentication.models import Landlord, Parker
from parker_main.models import Booking, ParkingSpot

PIN = "1234"
_seq = count(1)


@pytest.fixture(autouse=True)
def _test_env(settings, tmp_path):
    """Fast hashing, a throwaway media folder and a clean lockout cache for every test."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MEDIA_ROOT = str(tmp_path / "media")
    cache.clear()


@pytest.fixture
def make_parker(db):
    def make(phone=None, vehicle_type="car", pin=PIN, **kw):
        n = next(_seq)
        phone = phone or f"98{n:08d}"
        p = Parker(name=kw.pop("name", f"Driver {n}"), email=f"{phone}@test.in", phone=phone,
                   vehicle_type=vehicle_type, vehicle_number=kw.pop("vehicle_number", f"TN {n:04d}"), **kw)
        p.set_pin(pin)
        p.save()
        return p
    return make


@pytest.fixture
def make_landlord(db):
    def make(phone=None, pin=PIN, **kw):
        n = next(_seq)
        phone = phone or f"91{n:08d}"
        host = Landlord(name=kw.pop("name", f"Host {n}"), email=f"{phone}@host.in", phone=phone, city="Chennai", **kw)
        host.set_pin(pin)
        host.save()
        return host
    return make


@pytest.fixture
def make_spot(db, make_landlord):
    def make(landlord=None, **kw):
        fields = dict(title="Driveway near T. Nagar", address="1 Usman Rd", city="Chennai",
                      latitude=13.0418, longitude=80.2337, hourly_rate=Decimal("40"), capacity=1)
        fields.update(kw)
        return ParkingSpot.objects.create(landlord=landlord or make_landlord(), **fields)
    return make


@pytest.fixture
def make_booking(db):
    def make(parker, spot, start=None, hours=2, status=Booking.CONFIRMED):
        start = start or timezone.now() + timedelta(days=1)
        return Booking.objects.create(parker=parker, spot=spot, start=start, end=start + timedelta(hours=hours),
                                      vehicle_type=parker.vehicle_type, vehicle_number=parker.vehicle_number,
                                      total_price=spot.hourly_rate * hours, status=status)
    return make


def _login(client, role, user):
    resp = client.post(reverse("login"), {"role": role, "phone": user.phone,
                                          **{f"pin{i + 1}": d for i, d in enumerate(PIN)}})
    assert resp.status_code == 302, "login failed"
    return client


@pytest.fixture
def parker(make_parker):
    return make_parker()


@pytest.fixture
def host(make_landlord):
    return make_landlord()


@pytest.fixture
def parker_client(parker):
    return _login(Client(), "parker", parker)


@pytest.fixture
def host_client(host):
    return _login(Client(), "landlord", host)
