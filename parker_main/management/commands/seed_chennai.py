"""Adds realistic parking spots around well-known Chennai localities, each with a local host (PIN 1234)."""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from Authentication.models import Landlord, Parker
from parker_main.illustrations import ensure_photo
from parker_main.models import Booking, ParkingSpot, Review

HOST_PIN = "1234"

# (host name, title, address, lat, lng, ₹/hr, slots, cars, bikes, amenities, instant, description)
SPOTS = [
    ("Lakshmi Narayanan", "Gated driveway near Pondy Bazaar", "14, Thirumalai Pillai Rd, T. Nagar", 13.0418, 80.2337, 60, 2, True, True, "covered cctv", False,
     "Two minutes' walk to Pondy Bazaar. Gate closes at 11 PM."),
    ("Meenakshi Sundaram", "Bike bay off Ranganathan Street", "6, Usman Rd, T. Nagar", 13.0392, 80.2318, 20, 8, False, True, "cctv guard", True,
     "Secure bike parking for shopping trips. Watchman on duty 9 AM to 10 PM."),
    ("Karthikeyan R", "Covered garage near Anna Nagar Tower Park", "21, 2nd Avenue, Anna Nagar", 13.0868, 80.2135, 40, 3, True, True, "covered cctv", True,
     "Opposite the Tower Park gate. Plenty of turning space for SUVs."),
    ("Priya Venkatesh", "Shaded spot near Express Avenue", "9, Whites Rd, Royapettah", 13.0584, 80.2632, 70, 2, True, False, "covered cctv", False,
     "5-minute walk to Express Avenue mall. Cheaper than mall parking on weekends."),
    ("Arun Balaji", "Velachery 100 Ft Road basement", "112, Velachery Main Rd, Velachery", 12.9798, 80.2206, 50, 6, True, True, "covered cctv ev", True,
     "Basement parking near Phoenix MarketCity. One EV charging point (Type 2)."),
    ("Deepa Ramesh", "Walk-in lot near Phoenix MarketCity", "3, Taramani Link Rd, Velachery", 12.9922, 80.2181, 60, 4, True, True, "cctv", False,
     "Right behind the mall's service lane."),
    ("Suresh Kumar", "Chennai Central quick-stop lot", "18, Poonamallee High Rd, Park Town", 13.0818, 80.2739, 80, 5, True, True, "cctv guard", True,
     "Ideal for train pickups and drop-offs at Chennai Central."),
    ("Vijayalakshmi M", "Egmore station side-lane parking", "4, Gandhi Irwin Rd, Egmore", 13.0776, 80.2596, 50, 3, True, True, "guard", False,
     "Walking distance to Egmore railway station and the Government Museum."),
    ("Rajesh Iyer", "Marina Beach evening parking", "27, Kamarajar Salai, Triplicane", 13.0520, 80.2810, 80, 4, True, True, "cctv guard", True,
     "Across the road from Marina Beach. Busy on weekend evenings, so book ahead."),
    ("Anitha Krishnan", "Besant Nagar beach-side driveway", "5th Avenue, Besant Nagar", 12.9996, 80.2705, 60, 2, True, True, "cctv", False,
     "Short walk to Elliot's Beach and the 2nd Avenue cafés."),
    ("Ganesh Subramanian", "Adyar Gandhi Nagar driveway", "8, 1st Main Rd, Gandhi Nagar, Adyar", 13.0065, 80.2571, 40, 1, True, True, "", False,
     "Quiet residential street near Adyar signal."),
    ("Kavitha Rajan", "Kapaleeshwarar Temple parking", "11, North Mada St, Mylapore", 13.0338, 80.2694, 40, 3, True, True, "guard", True,
     "Steps from Kapaleeshwarar Temple and the Mylapore tank."),
    ("Srinivasan P", "Khader Nawaz Khan Road covered bay", "2, Khader Nawaz Khan Rd, Nungambakkam", 13.0612, 80.2465, 90, 2, True, False, "covered cctv", False,
     "Prime spot on KNK Road for cafés and boutiques."),
    ("Harini Sekar", "Greams Road hospital-visit parking", "15, Greams Lane, Thousand Lights", 13.0628, 80.2519, 50, 4, True, True, "covered cctv", True,
     "Close to Apollo Hospitals on Greams Road. Long stays welcome."),
    ("Mohammed Irfan", "Chepauk stadium match-day parking", "7, Bells Rd, Chepauk", 13.0633, 80.2787, 100, 6, True, True, "guard", False,
     "Walk to M. A. Chidambaram Stadium. Fills up fast on IPL match days."),
    ("Ramya Gopal", "Guindy business-district parking", "22, SIDCO Industrial Estate Rd, Guindy", 13.0105, 80.2122, 40, 5, True, True, "covered cctv", True,
     "Close to Olympia Tech Park and Guindy station."),
    ("Venkatesh Babu", "Tidel Park commuter parking", "4, Rajiv Gandhi Salai, Taramani", 12.9893, 80.2475, 30, 6, True, True, "cctv ev", True,
     "Weekday office parking next to Tidel Park. EV charging available."),
    ("Sangeetha N", "Thoraipakkam OMR stilt parking", "88, OMR, Thoraipakkam", 12.9362, 80.2327, 30, 4, True, True, "covered", False,
     "Stilt parking in an apartment on OMR, near the IT parks."),
    ("Prakash Murugan", "Sholinganallur junction lot", "3, Sholinganallur Main Rd, Sholinganallur", 12.9012, 80.2276, 30, 8, True, True, "cctv ev guard", True,
     "Large open lot at the ECR–OMR link. Two EV chargers."),
    ("Divya Sridhar", "Airport long-stay parking", "12, GST Rd, Meenambakkam", 12.9905, 80.1712, 70, 10, True, True, "covered cctv guard", True,
     "Cheaper than the airport multi-level lot. Free drop to the terminal on request."),
    ("Balasubramaniam K", "Tambaram station park & ride", "5, Shanmugam Rd, West Tambaram", 12.9252, 80.1175, 20, 10, True, True, "guard", True,
     "Park here and take the suburban train into the city."),
    ("Nandhini Arumugam", "Porur junction driveway", "31, Arcot Rd, Porur", 13.0385, 80.1572, 30, 2, True, True, "cctv", False,
     "Near Porur junction and Sri Ramachandra hospital."),
    ("Saravanan T", "Forum Vijaya Mall side parking", "9, Arcot Rd, Vadapalani", 13.0497, 80.2094, 50, 3, True, True, "covered", True,
     "Behind Forum Vijaya Mall, near Vadapalani metro."),
    ("Keerthana Mohan", "Koyambedu bus terminus parking", "2, Jawaharlal Nehru Rd, Koyambedu", 13.0694, 80.1946, 40, 8, True, True, "cctv guard", True,
     "Convenient for CMBT long-distance buses and the Koyambedu market."),
    ("Dinesh Kannan", "Ashok Nagar 4th Avenue driveway", "4th Avenue, Ashok Nagar", 13.0367, 80.2123, 30, 1, True, True, "", False,
     "Residential driveway close to Ashok Nagar metro."),
    ("Revathi Selvam", "Kilpauk Garden Road parking", "17, Kilpauk Garden Rd, Kilpauk", 13.0852, 80.2412, 40, 2, True, True, "covered", False,
     "Near Kilpauk Medical College and the Poonamallee High Road shops."),
    ("Ashwin Raghavan", "Spencer Plaza, Anna Salai", "6, Blackers Rd, Anna Salai", 13.0615, 80.2618, 60, 3, True, True, "cctv", True,
     "Walk to Spencer Plaza and the Anna Salai offices."),
    ("Uma Maheswari", "TTK Road Alwarpet parking", "10, TTK Rd, Alwarpet", 13.0335, 80.2545, 60, 2, True, False, "covered cctv", False,
     "Central Alwarpet, close to the music sabhas and restaurants."),
    ("Manikandan S", "Perambur Barracks Road lot", "40, Barracks Rd, Perambur", 13.1178, 80.2331, 20, 6, True, True, "", True,
     "Budget parking near Perambur station and the market."),
    ("Janani Vasudevan", "Thiruvanmiyur beach-road driveway", "3, Valmiki Nagar Main Rd, Thiruvanmiyur", 12.9834, 80.2596, 40, 2, True, True, "cctv", False,
     "Between Thiruvanmiyur beach and the ECR start."),
    ("Selvakumar A", "Chromepet GST Road parking", "55, GST Rd, Chromepet", 12.9518, 80.1460, 20, 5, True, True, "guard", True,
     "Near Chromepet station, handy for the Tambaram–Beach trains."),
    ("Bhavani Chandran", "Saidapet metro-side bay", "8, Jones Rd, Saidapet", 13.0215, 80.2229, 30, 3, True, True, "cctv", True,
     "Right next to Saidapet metro station."),
]
AMENITY_FIELDS = {"covered": "is_covered", "cctv": "has_cctv", "ev": "has_ev_charging", "guard": "has_guard"}
REVIEWS = [
    (5, "Easy to find and the host was very helpful."),
    (5, "Safe and clean. Will book again."),
    (4, "Good spot, a little tight for a big car."),
    (5, "Much cheaper than the mall parking."),
    (4, "Watchman was friendly. Gate timing was a bit strict."),
    (5, ""),
    (3, "Fine, but it took a while to locate the gate."),
]
GUESTS = [("Karthik S", "car"), ("Meera V", "car"), ("Rahul N", "bike"), ("Divya P", "car"), ("Sanjay R", "bike"), ("Aishwarya K", "car")]


def slug(name):
    return "".join(ch for ch in name.lower() if ch.isalnum() or ch == " ").replace(" ", ".")


class Command(BaseCommand):
    help = "Add realistic Chennai parking spots (hosts use PIN 1234). Safe to run more than once."

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(600001)
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        guests = []
        for i, (name, vehicle) in enumerate(GUESTS):
            g, created = Parker.objects.get_or_create(
                phone=f"90000001{i:02d}",
                defaults={"name": name, "email": f"guest{i}@parkmatch.test", "vehicle_type": vehicle,
                          "vehicle_number": f"TN 0{i} GX {1000 + i}"},
            )
            if created:
                g.set_pin(HOST_PIN)
                g.save()
            guests.append(g)
        if not any(g.vehicle_type == "bike" for g in guests):
            rider, created = Parker.objects.get_or_create(
                phone="9000000199",
                defaults={"name": "Vignesh B", "email": "guest.bike@parkmatch.test", "vehicle_type": "bike", "vehicle_number": "TN 22 BK 4242"},
            )
            if created:
                rider.set_pin(HOST_PIN)
                rider.save()
            guests.append(rider)

        added = 0
        for i, (host_name, title, address, lat, lng, price, slots, cars, bikes, amen, instant, desc) in enumerate(SPOTS):
            phone = f"91000{i:05d}"
            host, created = Landlord.objects.get_or_create(
                phone=phone,
                defaults={"name": host_name, "email": f"{slug(host_name)}@parkmatch.test", "city": "Chennai",
                          "state": "Tamil Nadu", "country": "India", "address": address},
            )
            if created:
                host.set_pin(HOST_PIN)
                host.save()
            if host.spots.filter(title=title).exists():
                continue

            spot = ParkingSpot.objects.create(
                landlord=host, title=title, description=desc, address=address, city="Chennai",
                latitude=lat, longitude=lng, hourly_rate=Decimal(price), capacity=slots,
                accepts_car=cars, accepts_bike=bikes, instant_book=instant,
                **{AMENITY_FIELDS[a]: True for a in amen.split()},
            )
            ensure_photo(spot)
            added += 1

            # A little booking history so ratings and host dashboards have something in them.
            for _ in range(rng.randint(1, 4)):
                guest = rng.choice([g for g in guests if spot.accepts(g.vehicle_type)])
                start = now - timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 10))
                hours = rng.choice([1, 2, 3, 4])
                b = Booking.objects.create(parker=guest, spot=spot, start=start, end=start + timedelta(hours=hours),
                                           vehicle_type=guest.vehicle_type, vehicle_number=guest.vehicle_number,
                                           total_price=spot.hourly_rate * hours, status=Booking.CONFIRMED)
                if rng.random() < 0.7:
                    rating, comment = rng.choice(REVIEWS)
                    Review.objects.create(booking=b, rating=rating, comment=comment)

        self.stdout.write(self.style.SUCCESS(
            f"Added {added} Chennai spots ({len(SPOTS) - added} already existed). "
            f"Hosts log in with phones 9100000000 to 91000{len(SPOTS) - 1:05d}, PIN {HOST_PIN}."
        ))
