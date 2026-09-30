from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import ClothingItem
from .forms import ClothingItemForm

# R -> Read: Melihat daftar pakaian pribadi
@login_required
def item_list(request):
    items = ClothingItem.objects.filter(user=request.user)
    return render(request, 'digital_wardrobe/item_list.html', {'items': items})

# R -> Read: Melihat detail 1 pakaian
@login_required
def item_detail(request, pk):
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
    return render(request, 'digital_wardrobe/item_detail.html', {'item': item})

# C -> Create: Menambahkan pakaian baru
@login_required
def item_create(request):
    if request.method == 'POST':
        form = ClothingItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.save()
            return redirect('digital_wardrobe:item_list')
    else:
        form = ClothingItemForm()
    return render(request, 'digital_wardrobe/item_form.html', {'form': form, 'title': 'Tambah Pakaian'})

# U -> Update: Mengubah informasi pakaian
@login_required
def item_update(request, pk):
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ClothingItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return redirect('digital_wardrobe:item_detail', pk=item.pk)
    else:
        form = ClothingItemForm(instance=item)
    return render(request, 'digital_wardrobe/item_form.html', {'form': form, 'title': 'Edit Pakaian'})

# D -> Delete: Menghapus pakaian dari wardrobe
@login_required
def item_delete(request, pk):
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
    if request.method == 'POST':
        item.delete()
        return redirect('digital_wardrobe:item_list')
    return render(request, 'digital_wardrobe/item_confirm_delete.html', {'item': item})

