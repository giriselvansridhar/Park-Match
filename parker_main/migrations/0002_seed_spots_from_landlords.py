from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    """Give every existing landlord with a location one bookable spot, so the map isn't empty."""
    Landlord = apps.get_model("Authentication", "Landlord")
    ParkingSpot = apps.get_model("parker_main", "ParkingSpot")
    spots = []
    for l in Landlord.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True):
        seed = l.id * 7919
        address = ", ".join(p for p in [l.address, l.area] if p)
        spots.append(ParkingSpot(
            landlord_id=l.id,
            title=f"{l.name.split()[0]}'s parking" + (f" · {l.landmark}" if l.landmark else ""),
            address=address or l.city or "Address on request",
            city=l.city,
            latitude=float(l.latitude),
            longitude=float(l.longitude),
            hourly_rate=Decimal(20 + (seed % 9) * 10),
            capacity=1 + seed % 5,
            accepts_car=seed % 6 != 0,
            accepts_bike=True,
            is_covered=seed % 2 == 0,
            has_cctv=seed % 3 != 0,
            has_ev_charging=seed % 7 == 0,
            has_guard=seed % 4 == 0,
            instant_book=seed % 3 == 0,
        ))
    ParkingSpot.objects.bulk_create(spots)


class Migration(migrations.Migration):

    dependencies = [
        ("Authentication", "0008_hash_pins_normalize_phones"),
        ("parker_main", "0001_spots_bookings_reviews"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
