from django import forms

from digital_wardrobe.models import ClothingItem
from home.wilayah import LocationField
from swap_requests.models import SwapRequest

from .models import ItemForSwap


PLACE_ATTRS = {'placeholder': 'Opsional, mis. Stasiun UI atau Margo City'}


class MeetingLocationMixin:
    """Kab/kota bertemu (autocomplete API Wilayah Indonesia, dicek di server) + detail tempat."""

    @property
    def meeting_city_label(self):
        """Teks yang tampil di input kab/kota (pilihan tersimpan atau yang baru dikirim)."""
        location = self.cleaned_data.get('meeting_city_code') if hasattr(self, 'cleaned_data') else None
        if location:
            return location['label']
        listing = getattr(self, 'instance', None)
        if listing is not None and listing.meeting_city_code:
            return f'{listing.meeting_city}, {listing.meeting_province}'
        return ''


class ItemForSwapForm(MeetingLocationMixin, forms.Form):
    """Create: pilih baju dari lemari + lokasi (wajib) + deskripsi (opsional)."""
    clothing_item = forms.ModelChoiceField(
        queryset=ClothingItem.objects.none(),
        label='Tambahkan pakaian', empty_label='Pilih pakaian',
    )
    meeting_city_code = LocationField(label='Kota/kabupaten bertemu')
    meeting_place = forms.CharField(
        label='Detail tempat', max_length=150, required=False,
        widget=forms.TextInput(attrs=PLACE_ATTRS),
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
        active = SwapRequest.objects.filter(status__in=(SwapRequest.PENDING, SwapRequest.AWAITING))
        field.queryset = (ClothingItem.objects.available_for_swap(user)
                          .exclude(pk__in=active.exclude(requested_item__isnull=True).values('requested_item_id'))
                          .exclude(pk__in=active.exclude(offered_item__isnull=True).values('offered_item_id')))
        field.label_from_instance = lambda obj: f'{obj.name} · {obj.size_label}'

    def clean_meeting_place(self):
        return self.cleaned_data['meeting_place'].strip()


class ItemForSwapEditForm(MeetingLocationMixin, forms.ModelForm):
    """Update: hanya lokasi & deskripsi. Bajunya tidak bisa diganti."""
    meeting_city_code = LocationField(label='Kota/kabupaten bertemu')

    class Meta:
        model = ItemForSwap
        fields = ['meeting_place', 'reason']
        widgets = {
            'meeting_place': forms.TextInput(attrs=PLACE_ATTRS),
            'reason': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Ceritakan tentang pakaian ini, apa keinginan penukaranmu, dan lainnya...',
            }),
        }
        labels = {'meeting_place': 'Detail tempat'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listing = self.instance
        self.fields['meeting_city_code'].initial = listing.meeting_city_code
        if not listing.meeting_city_code and not listing.meeting_place:
            # Listing lama (lokasi masih teks bebas): tampilkan teks lamanya sebagai detail tempat
            # supaya tidak hilang; pemilik cukup memilih kab/kota dari daftar.
            self.initial['meeting_place'] = listing.meeting_location[:150]

    def clean_meeting_place(self):
        return (self.cleaned_data.get('meeting_place') or '').strip()

    def save(self, commit=True):
        self.instance.set_meeting_location(self.cleaned_data['meeting_city_code'],
                                           self.cleaned_data['meeting_place'])
        return super().save(commit=commit)
