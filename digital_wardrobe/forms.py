from django import forms
from django.db.models import Q

from .models import ClothingItem, Outfit

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = ('image/jpeg', 'image/png')
ALLOWED_IMAGE_EXTS = ('.jpg', '.jpeg', '.png')

INPUT_CLASS = (
    'w-full h-10 px-3 rounded-lg border border-swNavy/15 bg-white text-sm text-swNavy '
    'placeholder:text-swSlate/70 focus:outline-none focus:ring-2 focus:ring-swPlum/40 focus:border-swPlum'
)
TEXTAREA_CLASS = (
    'w-full px-3 py-2.5 rounded-lg border border-swNavy/15 bg-white text-sm text-swNavy '
    'placeholder:text-swSlate/70 focus:outline-none focus:ring-2 focus:ring-swPlum/40 focus:border-swPlum'
)


class ClothingItemForm(forms.ModelForm):
    class Meta:
        model = ClothingItem
        fields = ['image', 'name', 'category', 'size', 'shoe_size', 'gender', 'condition', 'color', 'description']
        labels = {
            'image': 'Foto pakaian',
            'name': 'Nama pakaian',
            'category': 'Kategori',
            'size': 'Ukuran',
            'shoe_size': 'Ukuran sepatu (EU)',
            'gender': 'Gender pakaian',
            'condition': 'Kondisi',
            'color': 'Warna',
            'description': 'Deskripsi',
        }
        widgets = {
            'image': forms.FileInput(attrs={'accept': 'image/jpeg,image/png', 'class': 'sr-only'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Contoh: Kemeja linen krem'}),
            'shoe_size': forms.NumberInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Contoh: 38',
                'min': ClothingItem.SHOE_SIZE_MIN,
                'max': ClothingItem.SHOE_SIZE_MAX,
                'inputmode': 'numeric',
            }),
            'description': forms.Textarea(attrs={
                'class': TEXTAREA_CLASS,
                'rows': 4,
                'placeholder': 'Ceritakan catatan, bahan, ukuran detail, dan tanda pemakaian...',
            }),
        }

    PLACEHOLDERS = {
        'category': 'Pilih kategori',
        'size': 'Pilih ukuran',
        'gender': 'Pilih gender',
        'condition': 'Pilih kondisi',
        'color': 'Pilih warna',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages['required'] = 'Wajib diisi.'
            field.error_messages['invalid_choice'] = 'Pilihan tidak valid.'
        self.fields['shoe_size'].error_messages.update({
            'min_value': f'Ukuran sepatu minimal {ClothingItem.SHOE_SIZE_MIN}.',
            'max_value': f'Ukuran sepatu maksimal {ClothingItem.SHOE_SIZE_MAX}.',
            'invalid': 'Ukuran sepatu harus berupa angka.',
        })
        self.fields['image'].error_messages.update({
            'required': 'Foto pakaian wajib diunggah.',
            'invalid_image': 'File harus berupa foto JPG atau PNG.',
        })
        for name, placeholder in self.PLACEHOLDERS.items():
            field = self.fields[name]
            choices = [c for c in field.choices if c[0] != '']
            field.choices = [('', placeholder)] + choices
            field.widget.attrs['class'] = INPUT_CLASS

    @property
    def is_footwear(self):
        return self['category'].value() == 'footwear'

    def clean(self):
        cleaned = super().clean()
        # Sepatu pakai ukuran angka (EU), pakaian lain pakai XS–XXL.
        if cleaned.get('category') == 'footwear':
            if not cleaned.get('shoe_size'):
                self.add_error('shoe_size', 'Wajib diisi untuk sepatu.')
            cleaned['size'] = ''
        elif cleaned.get('category'):
            if not cleaned.get('size'):
                self.add_error('size', 'Wajib diisi.')
            cleaned['shoe_size'] = None
        return cleaned

    def clean_image(self):
        image = self.cleaned_data.get('image')
        # File baru saja yang dicek; saat edit tanpa ganti foto, foto lama dipakai.
        if image and hasattr(image, 'content_type'):
            if image.size > MAX_IMAGE_SIZE:
                raise forms.ValidationError('Ukuran foto maksimal 5 MB.')
            name = image.name.lower()
            if image.content_type not in ALLOWED_IMAGE_TYPES or not name.endswith(ALLOWED_IMAGE_EXTS):
                raise forms.ValidationError('Format foto harus JPG atau PNG.')
        return image


class OutfitForm(forms.ModelForm):
    """
    Form outfit: nama, deskripsi, dan 1–5 pakaian dari lemari user sendiri.
    """

    items = forms.ModelMultipleChoiceField(
        queryset=ClothingItem.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label='Pilih pakaian',
        error_messages={
            'required': 'Pilih minimal 1 pakaian.',
            'invalid_choice': 'Pakaian yang dipilih tidak valid.',
            'invalid_pk_value': 'Pakaian yang dipilih tidak valid.',
        },
    )

    class Meta:
        model = Outfit
        fields = ['name', 'description', 'items']
        labels = {
            'name': 'Nama outfit',
            'description': 'Deskripsi',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Contoh: Casual Kampus'}),
            'description': forms.Textarea(attrs={
                'class': TEXTAREA_CLASS,
                'rows': 3,
                'placeholder': 'Cocok dipakai ke mana? Ceritakan sedikit tentang outfit ini...',
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Yang bisa dipilih: pakaian di lemari, ditambah pakaian yang sudah ada di outfit ini
        # (meski sedang ditawarkan / sudah dihapus) supaya tidak hilang saat outfit diedit.
        allowed = Q(is_listed_for_swap=False, deleted_at__isnull=True)
        if self.instance.pk:
            allowed |= Q(pk__in=self.instance.items.values('pk'))
        eligible = ClothingItem.objects.filter(user=user).filter(allowed)
        if self.instance.pk:
            # Outfit tetap dapat mempertahankan dan melepas pakaian lama yang
            # sudah berpindah ke pengguna lain setelah swap.
            eligible = eligible | ClothingItem.objects.filter(pk__in=self.instance.items.values('pk'))
        self.fields['items'].queryset = eligible.order_by('category', '-created_at')
        self.fields['name'].error_messages['required'] = 'Wajib diisi.'

    def clean_items(self):
        items = self.cleaned_data.get('items')
        items = list(items)
        if not items:
            raise forms.ValidationError('Pilih minimal 1 pakaian.')
        if len(items) > Outfit.MAX_ITEMS:
            raise forms.ValidationError(f'Satu outfit maksimal {Outfit.MAX_ITEMS} pakaian.')
        existing_ids = set(self.instance.items.values_list('pk', flat=True)) if self.instance.pk else set()
        if any(item.user_id != self.user.id and item.pk not in existing_ids for item in items):
            raise forms.ValidationError('Pakaian baru harus berasal dari lemarimu sendiri.')
        return items
