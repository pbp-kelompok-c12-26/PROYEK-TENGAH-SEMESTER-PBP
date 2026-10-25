
import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import (
    UserProfile,
    STYLE_CHOICES,
    CLOTHING_SIZE_CHOICES,
    SHOE_SIZE_CHOICES,
)

INPUT_CLASS = ('w-full rounded-xl bg-[#F3F1F6] border border-swNavy/10 px-4 text-sm text-swNavy '
               'placeholder:text-swSlate/60 focus:outline-none focus:bg-white focus:border-swPlum focus:ring-2 focus:ring-swPlum/30')
CHIP_INPUT = {'class': 'peer sr-only'}
MAX_PICTURE_MB = 5


def _shoe_sizes_to_int(sizes):
    return [int(size) for size in sizes]


class UserProfileForm(forms.ModelForm):
    """Form profil lengkap (bisa dipakai untuk halaman Pengaturan Profil)."""
    preferred_styles = forms.MultipleChoiceField(
        choices=STYLE_CHOICES,
        required=False,
    )

    preferred_clothing_sizes = forms.MultipleChoiceField(
        choices=CLOTHING_SIZE_CHOICES,
        required=False,
    )

    preferred_shoe_sizes = forms.MultipleChoiceField(
        choices=SHOE_SIZE_CHOICES,
        required=False,
    )

    class Meta:
        model = UserProfile
        fields = [
            "display_name",
            "profile_picture",
            "bio",
            "preferred_styles",
            "preferred_clothing_sizes",
            "preferred_shoe_sizes",
        ]

    def clean_preferred_shoe_sizes(self):
        return _shoe_sizes_to_int(self.cleaned_data["preferred_shoe_sizes"])


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
        picture = self.cleaned_data.get('profile_picture')
        if picture and hasattr(picture, 'content_type'):  # file baru diupload
            if picture.size > MAX_PICTURE_MB * 1024 * 1024:
                raise forms.ValidationError(f'Ukuran foto maksimal {MAX_PICTURE_MB} MB.')
            if picture.content_type not in ('image/jpeg', 'image/png'):
                raise forms.ValidationError('Foto harus berformat JPG atau PNG.')
        return picture


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
        raw = self.cleaned_data['phone_number']
        phone = re.sub(r'[\s\-().]', '', raw)
        if phone.startswith('+62'):
            phone = '0' + phone[3:]
        elif phone.startswith('62'):
            phone = '0' + phone[2:]
        if not re.fullmatch(r'0\d{8,13}', phone):
            raise forms.ValidationError('Masukkan nomor HP yang valid, mis. 081234567890.')
        if UserProfile.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError('Nomor HP ini sudah dipakai akun lain.')
        return phone

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
