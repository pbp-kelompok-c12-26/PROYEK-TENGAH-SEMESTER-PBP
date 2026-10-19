from django import forms

from .models import ClothingItem

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
        fields = ['image', 'name', 'category', 'size', 'gender', 'condition', 'color', 'description']
        labels = {
            'image': 'Foto pakaian',
            'name': 'Nama pakaian',
            'category': 'Kategori',
            'size': 'Ukuran',
            'gender': 'Gender pakaian',
            'condition': 'Kondisi',
            'color': 'Warna',
            'description': 'Deskripsi',
        }
        widgets = {
            'image': forms.FileInput(attrs={'accept': 'image/jpeg,image/png', 'class': 'sr-only'}),
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Contoh: Kemeja linen krem'}),
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
        self.fields['image'].error_messages.update({
            'required': 'Foto pakaian wajib diunggah.',
            'invalid_image': 'File harus berupa foto JPG atau PNG.',
        })
        for name, placeholder in self.PLACEHOLDERS.items():
            field = self.fields[name]
            choices = [c for c in field.choices if c[0] != '']
            field.choices = [('', placeholder)] + choices
            field.widget.attrs['class'] = INPUT_CLASS

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
