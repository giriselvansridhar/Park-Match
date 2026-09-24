from django.core.management.base import BaseCommand

from parker_main.illustrations import ensure_photo
from parker_main.models import ParkingSpot


class Command(BaseCommand):
    help = "Give every parking spot without a photo generated cover art. Host-uploaded photos are never touched."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Regenerate art that was generated before (still keeps real photos).")

    def handle(self, *args, force=False, **options):
        made = sum(ensure_photo(spot, force=force) for spot in ParkingSpot.objects.all())
        self.stdout.write(self.style.SUCCESS(f"Generated cover art for {made} spot(s)."))
