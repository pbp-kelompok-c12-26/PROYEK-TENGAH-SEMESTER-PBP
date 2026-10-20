from django import forms

from digital_wardrobe.models import ClothingItem

from .models import ItemForSwap


class ItemForSwapForm(forms.Form):
    """Create: pilih baju dari lemari + lokasi (wajib) + deskripsi (opsional)."""
    clothing_item = forms.ModelChoiceField(
        queryset=ClothingItem.objects.none(),
        label='Tambahkan pakaian', empty_label='Pilih pakaian',
    )
    meeting_location = forms.CharField(
        label='Lokasi bertemu', max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Berikan rencana lokasi bertemu'}),
    )
    reason = forms.CharField(
        label='Deskripsi', required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Ceritakan tentang pakaian ini, apa keinginan penukaranmu, dan lainnya...',
        }),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['clothing_item']
        field.queryset = ClothingItem.objects.available_for_swap(user)
        field.label_from_instance = lambda obj: f'{obj.name} · {obj.size_label}'

    def clean_meeting_location(self):
        return self.cleaned_data['meeting_location'].strip()


class ItemForSwapEditForm(forms.ModelForm):
    """Update: hanya lokasi & deskripsi. Bajunya tidak bisa diganti."""
    class Meta:
        model = ItemForSwap
        fields = ['meeting_location', 'reason']
        widgets = {
            'meeting_location': forms.TextInput(attrs={'placeholder': 'Berikan rencana lokasi bertemu'}),
            'reason': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Ceritakan tentang pakaian ini, apa keinginan penukaranmu, dan lainnya...',
            }),
        }