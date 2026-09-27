"""End-to-end behaviour through HTTP: access rules, the marketplace flow, search and login security."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from parker_main.models import Booking, Review

pytestmark = pytest.mark.django_db


def when(days=1, hour=10):
    return (timezone.localtime() + timedelta(days=days)).replace(hour=hour, minute=0).strftime("%Y-%m-%dT%H:%M")


# ------------------------------------------------------------------ access rules

@pytest.mark.parametrize("name", ["home", "login", "Parker_Register", "LandLord_Register", "Parker_main"])
def test_public_pages(client, name):
    assert client.get(reverse(name)).status_code == 200


def test_spot_and_directions_pages_are_public(client, make_spot):
    spot = make_spot()
    assert client.get(reverse("spot_detail", args=[spot.id])).status_code == 200
    assert client.get(reverse("spot_directions", args=[spot.id])).status_code == 200


@pytest.mark.parametrize("name", ["parker_bookings", "landlord_dashboard", "landlord_bookings", "spot_create"])
def test_private_pages_send_visitors_to_login(client, name):
    resp = client.get(reverse(name))
    assert resp.status_code == 302 and resp["Location"].startswith(reverse("login"))


@pytest.mark.parametrize("who, name", [
    ("parker_client", "landlord_dashboard"),
    ("parker_client", "spot_create"),
    ("host_client", "parker_bookings"),
])
def test_roles_are_separate(request, who, name):
    c = request.getfixturevalue(who)
    assert c.get(reverse(name)).status_code == 302


def test_staff_overview_needs_staff(parker_client):
    assert parker_client.get(reverse("dashboard")).status_code == 302


# ------------------------------------------------------------------ ownership (changing an id in the URL must not work)

def test_host_cannot_edit_someone_elses_spot(host_client, make_spot):
    other = make_spot()
    assert host_client.get(reverse("spot_edit", args=[other.id])).status_code == 404
    assert host_client.post(reverse("spot_toggle", args=[other.id])).status_code == 404


def test_driver_cannot_cancel_someone_elses_booking(parker_client, make_parker, make_spot, make_booking):
    theirs = make_booking(make_parker(), make_spot())
    assert parker_client.post(reverse("cancel_booking", args=[theirs.id])).status_code == 404
    theirs.refresh_from_db()
    assert theirs.status == Booking.CONFIRMED


def test_host_cannot_answer_requests_for_other_spots(host_client, make_parker, make_spot, make_booking):
    theirs = make_booking(make_parker(), make_spot(), status=Booking.PENDING)
    assert host_client.post(reverse("booking_respond", args=[theirs.id, "accept"])).status_code == 404


# ------------------------------------------------------------------ the marketplace, start to finish

def test_request_accept_and_capacity_flow(parker_client, host_client, host, parker, make_parker, make_spot):
    spot = make_spot(landlord=host, capacity=1, instant_book=False, hourly_rate=Decimal("50"))

    # driver requests 3 hours
    resp = parker_client.post(reverse("spot_detail", args=[spot.id]), {"start": when(), "hours": 3})
    assert resp.status_code == 302
    booking = Booking.objects.get()
    assert (booking.status, booking.total_price) == (Booking.PENDING, 150)

    # host sees it and accepts
    assert parker.name in host_client.get(reverse("landlord_dashboard")).content.decode()
    host_client.post(reverse("booking_respond", args=[booking.id, "accept"]))
    booking.refresh_from_db()
    assert booking.status == Booking.CONFIRMED
    assert "Confirmed" in parker_client.get(reverse("parker_bookings")).content.decode()

    # the only slot is now taken for that window
    other = Client()
    other.post(reverse("login"), {"role": "parker", "phone": make_parker().phone, "pin1": "1", "pin2": "2", "pin3": "3", "pin4": "4"})
    resp = other.post(reverse("spot_detail", args=[spot.id]), {"start": when(), "hours": 1})
    assert "Fully booked" in resp.content.decode()


def test_accept_rechecks_capacity(host_client, host, make_parker, make_spot, make_booking):
    spot = make_spot(landlord=host, capacity=1)
    start = timezone.now() + timedelta(days=2)
    first = make_booking(make_parker(), spot, start=start, status=Booking.PENDING)
    second = make_booking(make_parker(), spot, start=start, status=Booking.PENDING)
    host_client.post(reverse("booking_respond", args=[first.id, "accept"]))
    host_client.post(reverse("booking_respond", args=[second.id, "accept"]))
    first.refresh_from_db(); second.refresh_from_db()
    assert (first.status, second.status) == (Booking.CONFIRMED, Booking.PENDING)


def test_review_after_stay(parker_client, parker, make_spot, make_booking):
    spot = make_spot()
    stay = make_booking(parker, spot, start=timezone.now() - timedelta(days=1))
    parker_client.post(reverse("review_booking", args=[stay.id]), {"rating": 4, "comment": "Easy to find"})
    assert spot.rating_summary() == {"avg": 4.0, "count": 1}


def test_new_listing_gets_cover_art(host_client, host):
    resp = host_client.post(reverse("spot_create"), {
        "title": "Basement near Phoenix", "address": "Velachery", "city": "Chennai",
        "latitude": "12.99", "longitude": "80.21", "hourly_rate": "50", "capacity": "4", "accepts_car": "on",
    })
    assert resp.status_code == 302
    assert host.spots.get().photo.name.endswith(".svg")


# ------------------------------------------------------------------ search

@pytest.mark.parametrize("params, included", [
    ({}, True),
    ({"max_price": 30}, False),             # spot costs 40
    ({"max_price": 40}, True),
    ({"is_covered": 1}, True),
    ({"has_ev_charging": 1}, False),
    ({"instant_book": 1}, False),
    ({"vehicle": "bike"}, False),           # spot is cars-only
    ({"radius": 1, "lat": 13.0827, "lon": 80.2757}, False),   # Chennai Central is ~6 km away
    ({"radius": 10, "lat": 13.0827, "lon": 80.2757}, True),
])
def test_search_filters(client, make_spot, params, included):
    spot = make_spot(hourly_rate=Decimal("40"), is_covered=True, accepts_bike=False)
    query = {"lat": 13.0418, "lon": 80.2337, **params}
    ids = [s.id for s in client.get(reverse("Parker_main"), query).context["spots"]]
    assert (spot.id in ids) == included


@pytest.mark.parametrize("sort, expected_first", [("price", "cheap"), ("distance", "near"), ("rating", "loved")])
def test_search_sorting(client, make_spot, make_parker, make_booking, sort, expected_first):
    make_spot(title="cheap", hourly_rate=Decimal("20"), latitude=13.060, longitude=80.2337)
    make_spot(title="near", hourly_rate=Decimal("90"), latitude=13.0419, longitude=80.2337)
    loved = make_spot(title="loved", hourly_rate=Decimal("60"), latitude=13.050, longitude=80.2337)
    stay = make_booking(make_parker(), loved, start=timezone.now() - timedelta(days=2))
    Review.objects.create(booking=stay, rating=5)
    spots = client.get(reverse("Parker_main"), {"lat": 13.0418, "lon": 80.2337, "sort": sort}).context["spots"]
    assert spots[0].title == expected_first


def test_paused_spots_are_hidden(client, make_spot):
    make_spot(is_active=False)
    assert client.get(reverse("Parker_main"), {"lat": 13.0418, "lon": 80.2337}).context["spots"] == []


# ------------------------------------------------------------------ login security

def test_lockout_after_five_wrong_pins(client, parker):
    wrong = {"role": "parker", "phone": parker.phone, "pin1": "0", "pin2": "0", "pin3": "0", "pin4": "0"}
    for _ in range(5):
        client.post(reverse("login"), wrong)
    right = {**wrong, "pin1": "1", "pin2": "2", "pin3": "3", "pin4": "4"}
    assert "Too many wrong attempts" in client.post(reverse("login"), right).content.decode()
    assert "user_id" not in client.session


@pytest.mark.parametrize("next_url, lands_on", [
    ("/parker/bookings/", "/parker/bookings/"),
    ("https://evil.example/steal", "/parker/"),
    ("//evil.example", "/parker/"),
])
def test_next_redirect_only_stays_on_site(client, parker, next_url, lands_on):
    resp = client.post(reverse("login"), {"role": "parker", "phone": parker.phone, "next": next_url,
                                          "pin1": "1", "pin2": "2", "pin3": "3", "pin4": "4"})
    assert resp["Location"] == lands_on


@pytest.mark.parametrize("role, home", [("parker", "/parker/"), ("landlord", "/landlord/")])
def test_one_click_demo(client, role, home):
    resp = client.post(reverse("demo_login", args=[role]))
    assert resp["Location"] == home
    assert client.session["role"] == role
