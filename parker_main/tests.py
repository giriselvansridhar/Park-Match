import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Authentication.tests import FAST_HASH, login, make_landlord, make_parker

from .illustrations import ensure_photo, render_spot_svg, scene_for
from .models import Booking, ParkingSpot, Review

TEMP_MEDIA = tempfile.mkdtemp(prefix="parkmatch-test-media-")


def make_spot(landlord, **kw):
    defaults = dict(title="Driveway", address="1 Main Rd", city="Chennai", latitude=13.08, longitude=80.27,
                    hourly_rate=Decimal("40"), capacity=1)
    defaults.update(kw)
    return ParkingSpot.objects.create(landlord=landlord, **defaults)


def local_input(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


@FAST_HASH
class ParkerFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.host = make_landlord()
        self.parker = make_parker()
        self.spot = make_spot(self.host)
        login(self.client, "parker", "9876543210", "1234")
        self.start = (timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)

    def book(self, spot=None, start=None, hours=2):
        return self.client.post(reverse("spot_detail", args=[(spot or self.spot).id]),
                                {"start": local_input(start or self.start), "hours": hours})

    def test_search_finds_nearby_and_filters(self):
        far = make_spot(self.host, title="Far away", latitude=12.0, longitude=79.0)
        bikes_only = make_spot(self.host, title="Bikes", accepts_car=False)
        covered = make_spot(self.host, title="Covered", is_covered=True, hourly_rate=Decimal("90"))
        resp = self.client.get(reverse("Parker_main"), {"lat": 13.08, "lon": 80.27, "radius": 5})
        ids = {s.id for s in resp.context["spots"]}
        self.assertIn(self.spot.id, ids)
        self.assertIn(covered.id, ids)
        self.assertNotIn(far.id, ids)
        self.assertNotIn(bikes_only.id, ids)  # parker drives a car

        resp = self.client.get(reverse("Parker_main"), {"lat": 13.08, "lon": 80.27, "is_covered": 1})
        self.assertEqual([s.id for s in resp.context["spots"]], [covered.id])
        resp = self.client.get(reverse("Parker_main"), {"lat": 13.08, "lon": 80.27, "max_price": 50})
        self.assertNotIn(covered.id, {s.id for s in resp.context["spots"]})

    def test_paused_spots_hidden(self):
        self.spot.is_active = False
        self.spot.save()
        resp = self.client.get(reverse("Parker_main"))
        self.assertEqual(resp.context["spots"], [])

    def test_request_booking_is_pending_with_price(self):
        self.assertRedirects(self.book(hours=3), reverse("parker_bookings"))
        b = Booking.objects.get()
        self.assertEqual(b.status, Booking.PENDING)
        self.assertEqual(b.total_price, Decimal("120"))
        self.assertEqual(b.vehicle_number, self.parker.vehicle_number)

    def test_instant_book_confirms(self):
        self.spot.instant_book = True
        self.spot.save()
        self.book()
        self.assertEqual(Booking.objects.get().status, Booking.CONFIRMED)

    def test_capacity_is_enforced(self):
        other = make_parker(phone="9000011111")
        Booking.objects.create(parker=other, spot=self.spot, start=self.start, end=self.start + timedelta(hours=2),
                               vehicle_type="car", vehicle_number="X", total_price=80, status=Booking.CONFIRMED)
        resp = self.book(start=self.start + timedelta(hours=1))
        self.assertContains(resp, "Fully booked")
        self.assertEqual(self.book(start=self.start + timedelta(hours=2)).status_code, 302)  # back-to-back is fine

    def test_rejects_past_start_and_wrong_vehicle(self):
        self.assertContains(self.book(start=timezone.now() - timedelta(hours=2)), "future")
        bike_spot = make_spot(self.host, accepts_car=False)
        self.assertContains(self.book(spot=bike_spot), "doesn")

    def test_cancel(self):
        self.book()
        b = Booking.objects.get()
        self.client.post(reverse("cancel_booking", args=[b.id]))
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.CANCELLED)

    def test_cannot_touch_someone_elses_booking(self):
        other = make_parker(phone="9000011111")
        b = Booking.objects.create(parker=other, spot=self.spot, start=self.start, end=self.start + timedelta(hours=1),
                                   vehicle_type="car", vehicle_number="X", total_price=40)
        self.assertEqual(self.client.post(reverse("cancel_booking", args=[b.id])).status_code, 404)

    def test_review_only_after_completion(self):
        b = Booking.objects.create(parker=self.parker, spot=self.spot, start=self.start, end=self.start + timedelta(hours=1),
                                   vehicle_type="car", vehicle_number="X", total_price=40, status=Booking.CONFIRMED)
        self.client.post(reverse("review_booking", args=[b.id]), {"rating": 5})
        self.assertFalse(Review.objects.exists())

        past = timezone.now() - timedelta(days=1)
        b.start, b.end = past, past + timedelta(hours=1)
        b.save()
        self.client.post(reverse("review_booking", args=[b.id]), {"rating": 5, "comment": "Great"})
        self.assertEqual(self.spot.rating_summary()["avg"], 5)
        self.client.post(reverse("review_booking", args=[b.id]), {"rating": 1})
        self.assertEqual(Review.objects.count(), 1)

    def test_visitors_can_browse_but_not_book(self):
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("Parker_main")).status_code, 200)
        resp = self.client.get(reverse("spot_detail", args=[self.spot.id]))
        self.assertContains(resp, "Try booking with the demo account")
        resp = self.book()
        self.assertIn(reverse("login"), resp["Location"])
        self.assertFalse(Booking.objects.exists())

    def test_directions_page(self):
        resp = self.client.get(reverse("spot_directions", args=[self.spot.id]))
        self.assertContains(resp, "Directions to")
        self.assertContains(resp, "router.project-osrm.org")
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("spot_directions", args=[self.spot.id])).status_code, 200)  # public

    def test_pages_render(self):
        self.book()
        for url in (reverse("Parker_main"), reverse("spot_detail", args=[self.spot.id]), reverse("parker_bookings")):
            self.assertEqual(self.client.get(url).status_code, 200, url)


@FAST_HASH
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class LandlordFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.host = make_landlord()
        self.parker = make_parker()
        login(self.client, "landlord", "9123456780", "4321")

    def test_create_edit_toggle_spot(self):
        resp = self.client.post(reverse("spot_create"), {
            "title": "Garage", "address": "2 Lake Rd", "city": "Chennai", "latitude": "13.05", "longitude": "80.25",
            "hourly_rate": "50", "capacity": "2", "accepts_car": "on", "instant_book": "on",
        })
        self.assertRedirects(resp, reverse("landlord_dashboard"))
        spot = self.host.spots.get()
        self.assertTrue(spot.photo.name.endswith(".svg"))  # listed without a photo, so it got cover art
        self.assertTrue(spot.instant_book)
        self.assertFalse(spot.accepts_bike)

        self.client.post(reverse("spot_toggle", args=[spot.id]))
        spot.refresh_from_db()
        self.assertFalse(spot.is_active)
        self.assertEqual(self.client.get(reverse("spot_edit", args=[spot.id])).status_code, 200)

    def test_spot_needs_location_and_a_vehicle_type(self):
        resp = self.client.post(reverse("spot_create"), {"title": "X", "address": "Y", "hourly_rate": "10", "capacity": "1"})
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertIn("latitude", form.errors)
        self.assertTrue(form.non_field_errors())

    def test_cannot_edit_other_hosts_spot(self):
        other = make_landlord(phone="9111111111")
        spot = make_spot(other)
        self.assertEqual(self.client.get(reverse("spot_edit", args=[spot.id])).status_code, 404)

    def test_accept_and_decline(self):
        spot = make_spot(self.host)
        start = timezone.now() + timedelta(days=1)
        mk = lambda s: Booking.objects.create(parker=self.parker, spot=spot, start=s, end=s + timedelta(hours=1),
                                              vehicle_type="car", vehicle_number="X", total_price=40)
        a, b = mk(start), mk(start)
        self.client.post(reverse("booking_respond", args=[a.id, "accept"]))
        a.refresh_from_db()
        self.assertEqual(a.status, Booking.CONFIRMED)
        # Capacity is 1, so the overlapping request can't also be accepted.
        self.client.post(reverse("booking_respond", args=[b.id, "accept"]))
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.PENDING)
        self.client.post(reverse("booking_respond", args=[b.id, "decline"]))
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.REJECTED)

    def test_dashboard_shows_revenue(self):
        spot = make_spot(self.host)
        now = timezone.now()
        Booking.objects.create(parker=self.parker, spot=spot, start=now - timedelta(hours=1), end=now + timedelta(hours=1),
                               vehicle_type="car", vehicle_number="X", total_price=80, status=Booking.CONFIRMED)
        resp = self.client.get(reverse("landlord_dashboard"))
        self.assertEqual(resp.context["stats"]["active_now"], 1)
        self.assertEqual(resp.context["chart_total"], 80)
        self.assertEqual(self.client.get(reverse("landlord_bookings")).status_code, 200)

    def test_empty_dashboard_onboarding(self):
        self.assertContains(self.client.get(reverse("landlord_dashboard")), "first spot")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class IllustrationTests(TestCase):
    def setUp(self):
        self.host = make_landlord()

    def test_scene_matches_spot_type(self):
        self.assertEqual(scene_for(make_spot(self.host, title="Marina Beach evening parking")), "beach")
        self.assertEqual(scene_for(make_spot(self.host, title="Velachery basement")), "basement")
        self.assertEqual(scene_for(make_spot(self.host, title="Covered garage")), "garage")
        self.assertEqual(scene_for(make_spot(self.host, title="Quiet driveway")), "driveway")
        self.assertEqual(scene_for(make_spot(self.host, title="Station lot")), "lot")

    def test_svg_is_stable_and_valid(self):
        spot = make_spot(self.host)
        svg = render_spot_svg(spot)
        self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"))
        self.assertEqual(svg, render_spot_svg(spot))

    def test_never_replaces_real_photo(self):
        spot = make_spot(self.host)
        spot.photo.save("real.jpg", ContentFile(b"jpeg-bytes"))
        self.assertFalse(ensure_photo(spot, force=True))
        self.assertTrue(spot.photo.name.endswith(".jpg"))

    def test_force_regenerates_generated_art(self):
        spot = make_spot(self.host)
        self.assertTrue(ensure_photo(spot))
        self.assertFalse(ensure_photo(spot))
        self.assertTrue(ensure_photo(spot, force=True))
