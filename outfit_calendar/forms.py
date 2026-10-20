from django import forms

from digital_wardrobe.models import Outfit
from .models import OutfitSchedule

INPUT_CLASS = ('w-full h-11 px-3 rounded-xl bg-white border border-swNavy/15 text-sm text-swNavy '
               'focus:outline-none focus:ring-2 focus:ring-swPlum/40 focus:border-swPlum')


class OutfitScheduleForm(forms.ModelForm):
    class Meta:
        model = OutfitSchedule
        fields = ['date', 'outfit', 'note']
        labels = {'date': 'Tanggal', 'outfit': 'Outfit', 'note': 'Catatan (opsional)'}
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': INPUT_CLASS}, format='%Y-%m-%d'),
            'outfit': forms.Select(attrs={'class': INPUT_CLASS}),
            'note': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'mis. Kuliah, kondangan, nongkrong'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['outfit'].queryset = Outfit.objects.filter(user=user).order_by('name')
        self.fields['outfit'].empty_label = 'Pilih outfit'

    def clean_date(self):
        tanggal = self.cleaned_data['date']
        sudah_ada = OutfitSchedule.objects.filter(user=self.user, date=tanggal).exclude(pk=self.instance.pk)
        if sudah_ada.exists():
            raise forms.ValidationError('Tanggal ini sudah punya jadwal outfit. Edit jadwalnya saja.')
        return tanggal