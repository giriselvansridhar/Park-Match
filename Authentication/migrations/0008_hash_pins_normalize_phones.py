import re

from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def forwards(apps, schema_editor):
    for model_name in ("Parker", "Landlord"):
        Model = apps.get_model("Authentication", model_name)
        taken = set(Model.objects.values_list("phone", flat=True))
        for obj in Model.objects.all():
            fields = []
            phone = normalize_phone(obj.phone)
            if phone and phone != obj.phone and phone not in taken:
                taken.add(phone)
                obj.phone = phone
                fields.append("phone")
            try:
                identify_hasher(obj.pin)
            except ValueError:
                obj.pin = make_password(obj.pin)
                fields.append("pin")
            if fields:
                obj.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("Authentication", "0007_pins_and_optional_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
