from django import forms
from .models import ClothingItem

class ClothingItemForm(forms.ModelForm):
    class Meta:
        model = ClothingItem
        fields = ['name', 'category', 'color', 'brand', 'size', 'description', 'image_url']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Pakaian'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Warna'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Merek'}),
            'size': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ukuran (S/M/L/XL)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'image_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
        }