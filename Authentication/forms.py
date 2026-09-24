from django import forms

from .models import Landlord, Parker, normalize_phone

INPUT = "pm-input"


class PinSignUpMixin(forms.Form):
    """Adds a 4-digit PIN + confirmation, and normalizes/validates the phone number."""

    pin = forms.CharField(
        label="4-digit PIN", min_length=4, max_length=4,
        widget=forms.PasswordInput(attrs={"class": INPUT, "inputmode": "numeric", "placeholder": "••••", "autocomplete": "new-password"}),
    )
    confirm_pin = forms.CharField(
        label="Confirm PIN", min_length=4, max_length=4,
        widget=forms.PasswordInput(attrs={"class": INPUT, "inputmode": "numeric", "placeholder": "••••", "autocomplete": "new-password"}),
    )

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not pin.isdigit():
            raise forms.ValidationError("PIN must be 4 digits.")
        return pin

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get("phone"))
        if len(phone) != 10:
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        if self._meta.model.objects.filter(phone=phone).exists():
            raise forms.ValidationError("This number is already registered. Try logging in.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("pin") and cleaned.get("confirm_pin") and cleaned["pin"] != cleaned["confirm_pin"]:
            self.add_error("confirm_pin", "PINs don't match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_pin(self.cleaned_data["pin"])
        if commit:
            user.save()
        return user


class ParkerSignUpForm(PinSignUpMixin, forms.ModelForm):
    class Meta:
        model = Parker
        fields = ["name", "email", "phone", "vehicle_type", "vehicle_number"]
        labels = {"name": "Full name", "vehicle_number": "Vehicle number"}
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT, "placeholder": "Priya Raman", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": INPUT, "placeholder": "you@example.com", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"class": INPUT, "placeholder": "98765 43210", "inputmode": "tel", "autocomplete": "tel"}),
            "vehicle_type": forms.RadioSelect,
            "vehicle_number": forms.TextInput(attrs={"class": INPUT + " uppercase", "placeholder": "TN 01 AB 1234"}),
        }

    def clean_vehicle_number(self):
        return " ".join(self.cleaned_data["vehicle_number"].upper().split())


class LandlordSignUpForm(PinSignUpMixin, forms.ModelForm):
    class Meta:
        model = Landlord
        fields = ["name", "email", "phone", "city", "profile_image"]
        labels = {"name": "Full name", "profile_image": "Profile photo (optional)"}
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT, "placeholder": "Arjun Kumar", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": INPUT, "placeholder": "you@example.com", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"class": INPUT, "placeholder": "98765 43210", "inputmode": "tel", "autocomplete": "tel"}),
            "city": forms.TextInput(attrs={"class": INPUT, "placeholder": "Chennai"}),
            "profile_image": forms.ClearableFileInput(attrs={"class": "pm-file", "accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["city"].required = True
