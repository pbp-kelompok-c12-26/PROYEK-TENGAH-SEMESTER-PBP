
from django import forms
from .models import (
    UserProfile,
    STYLE_CHOICES,
    CLOTHING_SIZE_CHOICES,
    SHOE_SIZE_CHOICES,
)


class UserProfileForm(forms.ModelForm):
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
        return [
            int(size)
            for size in self.cleaned_data["preferred_shoe_sizes"]
        ]

class OnboardingSizesForm(forms.Form):
    preferred_clothing_sizes = forms.MultipleChoiceField(
        choices=CLOTHING_SIZE_CHOICES,
        required=False,
    )

    preferred_shoe_sizes = forms.MultipleChoiceField(
        choices=SHOE_SIZE_CHOICES,
        required=False,
    )

    def clean_preferred_shoe_sizes(self):
        return [
            int(size)
            for size in self.cleaned_data["preferred_shoe_sizes"]
        ]
