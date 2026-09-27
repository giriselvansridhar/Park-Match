import csv
import os
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction

from Authentication.models import Landlord, normalize_phone
from parker_main.illustrations import ensure_photo
from parker_main.models import ParkingSpot


class Command(BaseCommand):
    help = 'Import landlords from CSV file, giving each one with a location a bookable parking spot'

    def handle(self, *args, **kwargs):
        filepath = os.path.join(settings.BASE_DIR, 'Authentication', 'data', 'landlords.csv')
        existing = set(Landlord.objects.values_list('phone', flat=True)) | set(Landlord.objects.values_list('email', flat=True))

        created = skipped = 0
        with open(filepath, newline='', encoding='utf-8') as csvfile, transaction.atomic():
            for row in csv.DictReader(csvfile):
                if row['name'].strip().lower() == 'name':
                    # The file has an unrelated dataset appended after a second header row; stop there.
                    break
                lat, lng = _coordinate(row['latitude'], 90), _coordinate(row['longitude'], 180)
                if row['latitude'] and lat is None or row['longitude'] and lng is None:
                    skipped += 1
                    continue
                phone = normalize_phone(row['phone'])
                if phone in existing or row['email'] in existing:
                    continue
                existing |= {phone, row['email']}
                landlord = Landlord.objects.create(
                    name=row['name'],
                    email=row['email'],
                    phone=phone,
                    pincode=row['pincode'],
                    address=row['address'],
                    area=row['area'],
                    landmark=row['landmark'],
                    city=row['city'],
                    state=row['state'],
                    country=row['country'],
                    pin=make_password(row['pin']),
                    latitude=lat,
                    longitude=lng,
                )
                if landlord.latitude is not None and landlord.longitude is not None:
                    seed = landlord.id * 7919
                    spot = ParkingSpot.objects.create(
                        landlord=landlord,
                        title=f"{landlord.name.split()[0]}'s parking" + (f" · {landlord.landmark}" if landlord.landmark else ""),
                        address=", ".join(p for p in [landlord.address, landlord.area] if p),
                        city=landlord.city,
                        latitude=float(landlord.latitude),
                        longitude=float(landlord.longitude),
                        hourly_rate=Decimal(20 + (seed % 9) * 10),
                        capacity=1 + seed % 5,
                        is_covered=seed % 2 == 0,
                        has_cctv=seed % 3 != 0,
                        instant_book=seed % 3 == 0,
                    )
                    ensure_photo(spot)
                created += 1

        note = f', skipped {skipped} rows with invalid coordinates' if skipped else ''
        self.stdout.write(self.style.SUCCESS(f'Imported {created} new landlords (existing phones/emails skipped{note}).'))


def _coordinate(value, limit):
    """A latitude/longitude as Decimal, or None if it's blank, not a number or out of range."""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError):
        return None
    return number if abs(number) <= limit else None
