import tempfile

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Landlord, Parker, is_hashed, normalize_phone

FAST_HASH = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def make_parker(phone="9876543210", pin="1234", **kw):
    p = Parker(name=kw.pop("name", "Priya Raman"), email=kw.pop("email", f"{phone}@x.com"), phone=phone,
               vehicle_type=kw.pop("vehicle_type", "car"), vehicle_number=kw.pop("vehicle_number", f"TN {phone[-4:]}"), **kw)
    p.set_pin(pin)
    p.save()
    return p


def make_landlord(phone="9123456780", pin="4321", **kw):
    l = Landlord(name=kw.pop("name", "Arjun Kumar"), email=kw.pop("email", f"{phone}@host.com"), phone=phone, city="Chennai", **kw)
    l.set_pin(pin)
    l.save()
    return l


def login(client, role, phone, pin):
    data = {"role": role, "phone": phone, **{f"pin{i + 1}": d for i, d in enumerate(pin)}}
    return client.post(reverse("login"), data)


class PhoneTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_phone("+91 98765-43210"), "9876543210")
        self.assertEqual(normalize_phone("919876543210"), "9876543210")
        self.assertEqual(normalize_phone("98765 43210"), "9876543210")


@FAST_HASH
class SignUpTests(TestCase):
    def test_parker_signup_hashes_pin_and_logs_in(self):
        resp = self.client.post(reverse("Parker_Register"), {
            "name": "Priya", "email": "p@x.com", "phone": "+91 98765 43210", "vehicle_type": "car",
            "vehicle_number": "tn 01  ab 1234", "pin": "1234", "confirm_pin": "1234",
        })
        self.assertRedirects(resp, reverse("Parker_main"))
        p = Parker.objects.get()
        self.assertEqual(p.phone, "9876543210")
        self.assertEqual(p.vehicle_number, "TN 01 AB 1234")
        self.assertTrue(is_hashed(p.pin))
        self.assertTrue(p.check_pin("1234"))

    def test_signup_rejects_mismatched_pin_and_duplicate_phone(self):
        make_parker()
        resp = self.client.post(reverse("Parker_Register"), {
            "name": "X", "email": "y@x.com", "phone": "9876543210", "vehicle_type": "car",
            "vehicle_number": "KA 1", "pin": "1234", "confirm_pin": "9999",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("phone", resp.context["form"].errors)
        self.assertIn("confirm_pin", resp.context["form"].errors)

    def test_landlord_signup_goes_to_dashboard(self):
        resp = self.client.post(reverse("LandLord_Register"), {
            "name": "Arjun", "email": "a@x.com", "phone": "9123456780", "city": "Chennai", "pin": "4321", "confirm_pin": "4321",
        })
        self.assertRedirects(resp, reverse("landlord_dashboard"))
        self.assertTrue(Landlord.objects.get().check_pin("4321"))


@FAST_HASH
class LoginTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_parker_login_and_logout(self):
        make_parker()
        self.assertRedirects(login(self.client, "parker", "+919876543210", "1234"), reverse("Parker_main"))
        self.assertEqual(self.client.get(reverse("Parker_main")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("parker_bookings")).status_code, 302)

    def test_landlord_login(self):
        make_landlord()
        self.assertRedirects(login(self.client, "landlord", "9123456780", "4321"), reverse("landlord_dashboard"))

    def test_role_mismatch_fails(self):
        make_parker(phone="9123456780")
        resp = login(self.client, "landlord", "9123456780", "1234")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("role", self.client.session)

    def test_legacy_plaintext_pin_upgraded_on_login(self):
        p = Parker.objects.create(name="Old", email="o@x.com", phone="9000000000", vehicle_number="OLD 1", pin="5555")
        login(self.client, "parker", "9000000000", "5555")
        p.refresh_from_db()
        self.assertTrue(is_hashed(p.pin))

    def test_lockout_after_repeated_failures(self):
        make_parker()
        for _ in range(5):
            login(self.client, "parker", "9876543210", "0000")
        resp = login(self.client, "parker", "9876543210", "1234")
        self.assertContains(resp, "Too many wrong attempts")
        self.assertNotIn("user_id", self.client.session)

    def test_next_redirect_is_safe(self):
        make_parker()
        resp = self.client.post(reverse("login"), {"role": "parker", "phone": "9876543210", "pin1": "1", "pin2": "2", "pin3": "3", "pin4": "4", "next": "https://evil.example/"})
        self.assertRedirects(resp, reverse("Parker_main"))

    def test_role_guard(self):
        make_landlord()
        login(self.client, "landlord", "9123456780", "4321")
        resp = self.client.get(reverse("parker_bookings"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_overview_requires_staff(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_public_pages_render(self):
        for name in ("home", "login", "Parker_Register", "LandLord_Register", "Parker_main"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


@FAST_HASH
@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="parkmatch-test-media-"))
class DemoTests(TestCase):
    def test_one_click_demo_logins_seed_and_switch(self):
        resp = self.client.post(reverse("demo_login", args=["parker"]))
        self.assertRedirects(resp, reverse("Parker_main"))
        self.assertEqual(self.client.session["role"], "parker")
        self.assertContains(self.client.get(reverse("parker_bookings")), "Demo mode")

        resp = self.client.post(reverse("demo_login", args=["landlord"]))
        self.assertRedirects(resp, reverse("landlord_dashboard"))
        self.assertEqual(self.client.session["role"], "landlord")

    def test_demo_login_requires_post_and_valid_role(self):
        self.assertEqual(self.client.get(reverse("demo_login", args=["parker"])).status_code, 405)
        self.assertEqual(self.client.post(reverse("demo_login", args=["admin"])).status_code, 404)

    @override_settings(DEMO_MODE=False)
    def test_demo_can_be_switched_off(self):
        self.assertEqual(self.client.post(reverse("demo_login", args=["parker"])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("home")), "Try as a driver")

    def test_demo_next_redirect(self):
        resp = self.client.post(reverse("demo_login", args=["parker"]), {"next": "/parker/bookings/"})
        self.assertRedirects(resp, "/parker/bookings/")
