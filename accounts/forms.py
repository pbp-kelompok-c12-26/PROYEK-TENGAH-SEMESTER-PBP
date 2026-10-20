from django import forms

from .models import Profile

INPUT_CLASS = ('w-full rounded-xl bg-[#F3F1F6] border border-swNavy/10 px-4 text-sm text-swNavy '
               'placeholder:text-swSlate/60 focus:outline-none focus:bg-white focus:border-swPlum focus:ring-2 focus:ring-swPlum/30')
MAX_AVATAR_MB = 5


class ProfileSetupForm(forms.ModelForm):
    """Onboarding langkah 2: Set Up Profil."""
    favorite_styles = forms.MultipleChoiceField(
        label='Style favorit', choices=Profile.STYLE_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'peer sr-only'}))

    class Meta:
        model = Profile
        fields = ['display_name', 'avatar', 'bio', 'favorite_styles']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': INPUT_CLASS + ' h-11', 'placeholder': 'Contoh: Fanny'}),
            'avatar': forms.FileInput(attrs={'accept': 'image/jpeg,image/png', 'class': 'sr-only', 'data-avatar-input': ''}),
            'bio': forms.Textarea(attrs={'class': INPUT_CLASS + ' py-3 min-h-[96px]', 'rows': 3,
                                         'placeholder': 'Ceritakan sedikit tentang gaya berpakaianmu...'}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and hasattr(avatar, 'size'):
            if avatar.size > MAX_AVATAR_MB * 1024 * 1024:
                raise forms.ValidationError(f'Ukuran foto maksimal {MAX_AVATAR_MB} MB.')
            if getattr(avatar, 'content_type', 'image/jpeg') not in ('image/jpeg', 'image/png'):
                raise forms.ValidationError('Foto harus berformat JPG atau PNG.')
        return avatar


class SizePreferenceForm(forms.ModelForm):
    """Onboarding langkah 3: Preferensi Ukuran."""
    clothing_sizes = forms.MultipleChoiceField(
        label='Ukuran pakaian', choices=Profile.CLOTHING_SIZE_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'peer sr-only'}))
    shoe_sizes = forms.MultipleChoiceField(
        label='Ukuran sepatu (standar EU)', choices=Profile.SHOE_SIZE_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'peer sr-only'}))

    class Meta:
        model = Profile
        fields = ['clothing_sizes', 'shoe_sizes']
