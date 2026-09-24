"""Creates a demo parker and a demo host with spots, bookings and reviews, so both sides of the app have something to show."""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from Authentication.models import Landlord, Parker
from parker_main.illustrations import ensure_photo
from parker_main.models import Booking, ParkingSpot, Review

DEMO_PARKER = {"name": "Demo Parker", "email": "demo.parker@parkmatch.test", "phone": "9000000001", "vehicle_number": "TN 09 DM 0001"}
DEMO_HOST = {"name": "Demo Host", "email": "demo.host@parkmatch.test", "phone": "9000000002", "city": "Chennai"}
DEMO_PIN = "1234"

SPOTS = [
    ("Covered garage near Anna Nagar Tower", "Anna Nagar 2nd Ave", 13.0850, 80.2101, 40, 3, dict(is_covered=True, has_cctv=True, instant_book=True)),
    ("T. Nagar shopping-district driveway", "Usman Rd, T. Nagar", 13.0418, 80.2341, 60, 2, dict(has_guard=True)),
    ("Marina-side EV bay", "Kamarajar Salai, Triplicane", 13.0569, 80.2791, 80, 1, dict(has_ev_charging=True, has_cctv=True, instant_book=True)),
]
REVIEWS = [
    (5, "Easy to find, host was super helpful."),
    (5, "Covered and secure, will book again."),
    (4, "Good spot, a bit tight for an SUV."),
    (5, ""),
]
GUESTS = ["Karthik S", "Meera V", "Rahul N", "Divya P", "Sanjay R"]


class Command(BaseCommand):
    help = "Seed a demo parker + demo host (PIN 1234) with spots, bookings and reviews. --reset restores it after visitors."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe the demo host's spots and the demo parker's bookings, then re-seed.")

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        rng = random.Random(7)
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        host, _ = Landlord.objects.get_or_create(phone=DEMO_HOST["phone"], defaults=DEMO_HOST)
        host.set_pin(DEMO_PIN)
        host.save()
        parker, _ = Parker.objects.get_or_create(phone=DEMO_PARKER["phone"], defaults=DEMO_PARKER)
        parker.set_pin(DEMO_PIN)
        parker.save()

        if reset:
            for spot in host.spots.all():
                spot.photo.delete(save=False)
            host.spots.all().delete()  # cascades to their bookings and reviews
            parker.bookings.all().delete()
            host.name, parker.name = DEMO_HOST["name"], DEMO_PARKER["name"]
            host.save()
            parker.save()

        if host.spots.exists():
            self.stdout.write("Demo data already exists; PINs reset to 1234.")
            return

        spots = [
            ParkingSpot.objects.create(landlord=host, title=t, address=a, city="Chennai", latitude=lat, longitude=lng,
                                       hourly_rate=Decimal(price), capacity=cap, **extra)
            for t, a, lat, lng, price, cap, extra in SPOTS
        ]

        for spot in spots:
            ensure_photo(spot)

        guests = []
        for i, name in enumerate(GUESTS):
            g, _ = Parker.objects.get_or_create(
                phone=f"90000001{i:02d}",
                defaults={"name": name, "email": f"guest{i}@parkmatch.test", "vehicle_number": f"TN 0{i} GX {1000 + i}"},
            )
            if not g.pin:
                g.set_pin(DEMO_PIN)
                g.save()
            guests.append(g)

        def book(who, spot, start, hours, status):
            return Booking.objects.create(parker=who, spot=spot, start=start, end=start + timedelta(hours=hours),
                                          vehicle_type=who.vehicle_type, vehicle_number=who.vehicle_number,
                                          total_price=spot.hourly_rate * hours, status=status)

        # Two weeks of completed guest bookings, some reviewed.
        reviews = iter(REVIEWS * 3)
        for day in range(1, 14):
            for _ in range(rng.randint(0, 2)):
                spot = rng.choice(spots)
                b = book(rng.choice(guests), spot, now - timedelta(days=day, hours=rng.randint(0, 8)), rng.choice([1, 2, 3, 4]), Booking.CONFIRMED)
                if rng.random() < 0.5:
                    rating, comment = next(reviews)
                    Review.objects.create(booking=b, rating=rating, comment=comment)

        # Something happening now, soon, and waiting for approval.
        book(guests[0], spots[0], now - timedelta(hours=1), 3, Booking.CONFIRMED)
        book(guests[1], spots[1], now + timedelta(hours=5), 2, Booking.CONFIRMED)
        book(guests[2], spots[1], now + timedelta(days=1, hours=2), 4, Booking.PENDING)
        book(guests[3], spots[2], now + timedelta(days=2), 2, Booking.PENDING)

        # The demo parker's own history: an upcoming pass, a request, and a past trip to review.
        book(parker, spots[0], now + timedelta(hours=3), 2, Booking.CONFIRMED)
        book(parker, spots[1], now + timedelta(days=3), 3, Booking.PENDING)
        book(parker, spots[2], now - timedelta(days=2), 2, Booking.CONFIRMED)

        self.stdout.write(self.style.SUCCESS(
            f"Demo ready. Parker: {DEMO_PARKER['phone']} / {DEMO_PIN}   Host: {DEMO_HOST['phone']} / {DEMO_PIN}"
        ))
