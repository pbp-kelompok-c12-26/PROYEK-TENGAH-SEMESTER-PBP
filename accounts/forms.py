import re

from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.db import transaction
from PIL import Image

from .models import (
    UserProfile,
    STYLE_CHOICES,
    CLOTHING_SIZE_CHOICES,
    SHOE_SIZE_CHOICES,
)

INPUT_CLASS = ('w-full rounded-xl bg-[#F8F3FA] border border-swPink/30 px-4 text-sm text-swNavy '
               'placeholder:text-swSlate/60 focus:outline-none focus:bg-white focus:border-swBerry focus:ring-2 focus:ring-swPink/35')
CHIP_INPUT = {'class': 'peer sr-only'}
MAX_PICTURE_MB = 5


def _shoe_sizes_to_int(sizes):
    return [int(size) for size in sizes]


def normalize_phone(raw):
    """Normalisasi nomor HP: hapus spasi/tanda baca, ubah +62 / 62 menjadi 0."""
    phone = re.sub(r'[\s\-().]', '', raw or '')
    if phone.startswith('+62'):
        phone = '0' + phone[3:]
    elif phone.startswith('62'):
        phone = '0' + phone[2:]
    return phone


def validate_phone(raw, exclude_profile=None):
    """Normalisasi + cek format + cek unik. exclude_profile = profil sendiri saat edit."""
    phone = normalize_phone(raw)
    if not re.fullmatch(r'0\d{8,13}', phone):
        raise forms.ValidationError('Masukkan nomor HP yang valid, mis. 081234567890.')
    taken = UserProfile.objects.filter(phone_number=phone)
    if exclude_profile is not None and exclude_profile.pk:
        taken = taken.exclude(pk=exclude_profile.pk)
    if taken.exists():
        raise forms.ValidationError('Nomor HP ini sudah dipakai akun lain.')
    return phone


def validate_profile_picture(picture):
    """Foto baru: maks 5 MB, JPG/PNG, dan isinya benar-benar gambar (Pillow)."""
    if picture and hasattr(picture, 'content_type'):  # file baru diupload
        if picture.size > MAX_PICTURE_MB * 1024 * 1024:
            raise forms.ValidationError(f'Ukuran foto maksimal {MAX_PICTURE_MB} MB.')
        if picture.content_type not in ('image/jpeg', 'image/png'):
            raise forms.ValidationError('Foto harus berformat JPG atau PNG.')
        try:
            image = Image.open(picture)
            image.verify()
            if image.format not in ('JPEG', 'PNG'):
                raise ValueError('Format gambar bukan JPEG/PNG')
        except Exception:
            raise forms.ValidationError('Foto harus berformat JPG atau PNG.')
        finally:
            picture.seek(0)
    return picture


class UserProfileForm(forms.ModelForm):
    """Form profil lengkap (dipakai untuk halaman Edit Profil)."""
    BIO_MAX = 300

    preferred_styles = forms.MultipleChoiceField(
        label='Style favorit',
        choices=STYLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs=CHIP_INPUT),
    )

    preferred_clothing_sizes = forms.MultipleChoiceField(
        label='Ukuran pakaian',
        choices=CLOTHING_SIZE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs=CHIP_INPUT),
    )

    preferred_shoe_sizes = forms.MultipleChoiceField(
        label='Ukuran sepatu (standar EU)',
        choices=SHOE_SIZE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs=CHIP_INPUT),
    )

    class Meta:
        model = UserProfile
        fields = [
            "display_name",
            "profile_picture",
            "bio",
            "phone_number",
            "domicile",
            "preferred_styles",
            "preferred_clothing_sizes",
            "preferred_shoe_sizes",
        ]
        widgets = {
            "display_name": forms.TextInput(attrs={
                "class": INPUT_CLASS + " h-11",
                "placeholder": "Contoh: Fanny",
                "maxlength": "15",
            }),
            "profile_picture": forms.FileInput(attrs={
                "accept": "image/jpeg,image/png",
                "class": "sr-only",
                "data-avatar-input": "",
            }),
            "bio": forms.Textarea(attrs={
                "class": INPUT_CLASS + " py-3 min-h-[96px]",
                "rows": 3,
                "maxlength": "300",
                "data-bio-input": "",
                "placeholder": "Ceritakan sedikit tentang gaya berpakaianmu...",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": INPUT_CLASS + " h-11",
                "placeholder": "Contoh: 081234567890",
                "inputmode": "tel",
                "autocomplete": "tel",
            }),
            "domicile": forms.TextInput(attrs={
                "class": INPUT_CLASS + " h-11",
                "placeholder": "Contoh: Depok",
                "autocomplete": "address-level2",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].required = True
        self.fields["domicile"].required = True

    def clean_bio(self):
        bio = (self.cleaned_data.get("bio") or "").strip()
        if len(bio) > self.BIO_MAX:
            raise forms.ValidationError(f"Biografi maksimal {self.BIO_MAX} karakter.")
        return bio

    def clean_profile_picture(self):
        return validate_profile_picture(self.cleaned_data.get("profile_picture"))

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data.get("phone_number", ""), exclude_profile=self.instance)

    def clean_domicile(self):
        domicile = (self.cleaned_data.get("domicile") or "").strip()
        if not domicile:
            raise forms.ValidationError("Wajib diisi.")
        return domicile

    def clean_preferred_shoe_sizes(self):
        return _shoe_sizes_to_int(self.cleaned_data["preferred_shoe_sizes"])


# Alias eksplisit jika dipanggil sebagai ProfileEditForm
ProfileEditForm = UserProfileForm


class ProfileSetupForm(forms.ModelForm):
    """Onboarding langkah 2: Set Up Profil."""
    preferred_styles = forms.MultipleChoiceField(
        label='Style favorit', choices=STYLE_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs=CHIP_INPUT))

    class Meta:
        model = UserProfile
        fields = ['display_name', 'profile_picture', 'bio', 'preferred_styles']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': INPUT_CLASS + ' h-11', 'placeholder': 'Contoh: Fanny'}),
            'profile_picture': forms.FileInput(attrs={'accept': 'image/jpeg,image/png', 'class': 'sr-only', 'data-avatar-input': ''}),
            'bio': forms.Textarea(attrs={'class': INPUT_CLASS + ' py-3 min-h-[96px]', 'rows': 3,
                                         'placeholder': 'Ceritakan sedikit tentang gaya berpakaianmu...'}),
        }

    def clean_profile_picture(self):
        return validate_profile_picture(self.cleaned_data.get('profile_picture'))


class SizePreferenceForm(forms.ModelForm):
    """Onboarding langkah 3: Preferensi Ukuran."""
    preferred_clothing_sizes = forms.MultipleChoiceField(
        label='Ukuran pakaian', choices=CLOTHING_SIZE_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs=CHIP_INPUT))
    preferred_shoe_sizes = forms.MultipleChoiceField(
        label='Ukuran sepatu (standar EU)', choices=SHOE_SIZE_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs=CHIP_INPUT))

    class Meta:
        model = UserProfile
        fields = ['preferred_clothing_sizes', 'preferred_shoe_sizes']

    def clean_preferred_shoe_sizes(self):
        return _shoe_sizes_to_int(self.cleaned_data["preferred_shoe_sizes"])


# Nama lama dari versi onboarding sebelumnya
OnboardingSizesForm = SizePreferenceForm


class RegisterForm(UserCreationForm):
    """Register: username + password, ditambah nomor HP & domisili untuk profil."""
    phone_number = forms.CharField(
        label='Nomor HP', max_length=20,
        widget=forms.TextInput(attrs={'placeholder': 'Contoh: 081234567890', 'inputmode': 'tel', 'autocomplete': 'tel'}),
    )
    domicile = forms.CharField(
        label='Domisili', max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Contoh: Depok', 'autocomplete': 'address-level2'}),
    )

    class Meta(UserCreationForm.Meta):
        fields = ('username', 'phone_number', 'domicile')

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data['phone_number'])

    def clean_domicile(self):
        domicile = self.cleaned_data['domicile'].strip()
        if not domicile:
            raise forms.ValidationError('Wajib diisi.')
        return domicile

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=commit)
            if commit:
                profile = UserProfile.for_user(user)
                profile.phone_number = self.cleaned_data['phone_number']
                profile.domicile = self.cleaned_data['domicile']
                profile.save(update_fields=['phone_number', 'domicile'])
        return user


class StyledPasswordChangeForm(PasswordChangeForm):
    """Form ganti password dengan styling input Swapdrobe."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "old_password": "Password lama",
            "new_password1": "Password baru",
            "new_password2": "Konfirmasi password baru",
        }
        for name, field in self.fields.items():
            field.widget.attrs.update({
                "class": INPUT_CLASS + " h-11",
                "placeholder": placeholders.get(name, ""),
            })
