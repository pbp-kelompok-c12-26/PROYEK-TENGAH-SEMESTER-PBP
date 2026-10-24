from django import forms

from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap
from .models import SwapRequest

INPUT_CLASS = ('w-full h-11 px-3 rounded-xl bg-white border border-swNavy/15 text-sm text-swNavy '
               'focus:outline-none focus:ring-2 focus:ring-swPlum/40 focus:border-swPlum')


def offerable_items(user):
    """Pakaian wardrobe yang tidak sedang dipakai request Pending/Awaiting."""
    active = SwapRequest.objects.filter(status__in=(SwapRequest.PENDING, SwapRequest.AWAITING))
    return (ClothingItem.objects.in_wardrobe(user)
            .exclude(pk__in=active.exclude(requested_item__isnull=True).values('requested_item_id'))
            .exclude(pk__in=active.exclude(offered_item__isnull=True).values('offered_item_id'))
            .order_by('name'))


class SwapRequestForm(forms.ModelForm):
    class Meta:
        model = SwapRequest
        fields = ['offered_item', 'message']
        labels = {'offered_item': 'Pakaian yang kamu tawarkan', 'message': 'Pesan'}
        widgets = {
            'offered_item': forms.Select(attrs={'class': INPUT_CLASS, 'data-offer-select': ''}),
            'message': forms.Textarea(attrs={
                'class': INPUT_CLASS.replace('h-11', 'min-h-[110px] py-2'), 'rows': 4,
                'placeholder': 'Ceritakan kenapa kamu tertarik, kondisi pakaianmu, atau ajak ngobrol soal ukuran...'}),
        }

    def __init__(self, *args, user=None, requested_item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.requested_item = requested_item
        qs = offerable_items(user)
        if self.instance.pk and self.instance.offered_item_id:
            qs = qs | ClothingItem.objects.filter(pk=self.instance.offered_item_id)
        self.fields['offered_item'].queryset = qs.distinct()
        self.fields['offered_item'].required = True
        self.fields['offered_item'].empty_label = 'Pilih pakaian'

    def clean(self):
        cleaned = super().clean()
        item = self.requested_item
        if (item is None or not item.is_listed_for_swap
                or not ItemForSwap.objects.available().filter(
                    clothing_item=item, clothing_item__deleted_at__isnull=True,
                ).exists()):
            raise forms.ValidationError('Pakaian yang kamu minta sudah tidak tersedia untuk ditukar.')
        if item.user_id == self.user.pk:
            raise forms.ValidationError('Kamu tidak bisa mengajukan swap untuk pakaianmu sendiri.')
        if SwapRequest.objects.is_locked(item):
            raise forms.ValidationError('Pakaian ini sedang dalam proses tukar dengan orang lain. Coba lagi nanti.')
        offered = cleaned.get('offered_item')
        if offered and not self.instance.pk:
            duplicate = SwapRequest.objects.filter(
                requester=self.user, requested_item=item, offered_item=offered, status=SwapRequest.PENDING)
            if duplicate.exists():
                raise forms.ValidationError('Kamu sudah mengirim request yang sama dan masih menunggu jawaban.')
        return cleaned

    def save(self, commit=True):
        swap = super().save(commit=False)
        swap.requester = self.user
        swap.owner = self.requested_item.user
        swap.requested_item = self.requested_item
        swap.requested_item_name = self.requested_item.name
        swap.offered_item_name = swap.offered_item.name
        if commit:
            swap.save()
        return swap


class ConfirmForm(forms.Form):
    choice = forms.ChoiceField(choices=SwapRequest.CONFIRM_CHOICES)
