import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import OutfitScheduleForm
from .models import OutfitSchedule, ScheduledItem, recompute_last_worn

BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
         'Agustus', 'September', 'Oktober', 'November', 'Desember']
HARI = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']
HARI_PANJANG = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']


def format_tanggal(d, with_day=False):
    teks = f'{d.day} {BULAN[d.month]} {d.year}'
    return f'{HARI_PANJANG[d.weekday()]}, {teks}' if with_day else teks


def _schedules_for(user):
    return (OutfitSchedule.objects.filter(user=user)
            .select_related('outfit')
            .prefetch_related(Prefetch('worn_items', queryset=ScheduledItem.objects.select_related('clothing_item'))))


def _read_month(request):
    """?month=2026-10 -> (2026, 10). Default: bulan ini."""
    today = date.today()
    try:
        year, month = map(int, request.GET.get('month', '').split('-'))
        date(year, month, 1)
        return year, month
    except ValueError:
        return today.year, today.month


def _month_url(d):
    return f"{reverse('outfit_calendar:index')}?month={d.year}-{d.month:02d}"


@login_required(login_url='accounts:login')
def index(request):
    year, month = _read_month(request)
    today = date.today()

    month_schedules = _schedules_for(request.user).filter(date__year=year, date__month=month)
    by_date = {}
    for s in month_schedules:
        # maks 4 foto baju (yang masih ada di lemari & punya gambar) untuk kolase di kalender
        s.thumbs = [w.clothing_item for w in s.worn_items.all()
                    if w.clothing_item and w.clothing_item.image][:4]
        by_date[s.date] = s

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        weeks.append([{
            'date': d,
            'in_month': d.month == month,
            'is_today': d == today,
            'schedule': by_date.get(d),
        } for d in week])

    prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    upcoming = list(_schedules_for(request.user).filter(date__gte=today)[:5])
    for s in upcoming:
        s.tanggal = format_tanggal(s.date, with_day=True)

    return render(request, 'outfit_calendar/index.html', {
        'weeks': weeks,
        'day_names': HARI,
        'month_label': f'{BULAN[month]} {year}',
        'prev_month': f'{prev_month[0]}-{prev_month[1]:02d}',
        'next_month': f'{next_month[0]}-{next_month[1]:02d}',
        'this_month': f'{today.year}-{today.month:02d}',
        'upcoming': upcoming,
        'has_outfits': request.user.outfits.exists(),
    })


@login_required(login_url='accounts:login')
def schedule_create(request):
    initial = {}
    if request.GET.get('date'):
        initial['date'] = request.GET['date']
    if request.GET.get('outfit'):
        initial['outfit'] = request.GET['outfit']

    form = OutfitScheduleForm(request.POST or None, user=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        schedule = form.save(commit=False)
        schedule.user = request.user
        schedule.save()
        schedule.save_snapshot()
        schedule.update_last_worn()
        messages.success(request, f'Outfit "{schedule.outfit.name}" dijadwalkan untuk {format_tanggal(schedule.date)}.')
        return redirect(_month_url(schedule.date))
    return render(request, 'outfit_calendar/schedule_form.html', {
        'form': form, 'title': 'Jadwalkan Outfit', 'submit_label': 'Simpan jadwal',
    })


@login_required(login_url='accounts:login')
def schedule_detail(request, pk):
    schedule = get_object_or_404(_schedules_for(request.user), pk=pk)
    for entry in schedule.worn_items.all():
        if entry.clothing_item:
            entry.clothing_item.seen_by(schedule.user_id)  # pakaian yang sudah ditukar -> "tidak tersedia"
    return render(request, 'outfit_calendar/schedule_detail.html', {
        'schedule': schedule,
        'tanggal': format_tanggal(schedule.date, with_day=True),
    })


@login_required(login_url='accounts:login')
def schedule_update(request, pk):
    schedule = get_object_or_404(OutfitSchedule, pk=pk, user=request.user)
    old_item_ids = list(schedule.worn_items.values_list('clothing_item_id', flat=True))
    form = OutfitScheduleForm(request.POST or None, instance=schedule, user=request.user)
    if request.method == 'POST' and form.is_valid():
        schedule = form.save()
        schedule.save_snapshot()
        # Tanggal/outfit bisa berubah: hitung ulang pakaian lama dan baru
        recompute_last_worn(old_item_ids + list(schedule.worn_items.values_list('clothing_item_id', flat=True)))
        messages.success(request, 'Jadwal outfit diperbarui.')
        return redirect('outfit_calendar:schedule_detail', pk=schedule.pk)
    return render(request, 'outfit_calendar/schedule_form.html', {
        'form': form, 'title': 'Edit Jadwal Outfit', 'submit_label': 'Simpan perubahan', 'schedule': schedule,
    })


@login_required(login_url='accounts:login')
@require_POST
def schedule_delete(request, pk):
    schedule = get_object_or_404(OutfitSchedule, pk=pk, user=request.user)
    tanggal = schedule.date
    item_ids = list(schedule.worn_items.values_list('clothing_item_id', flat=True))
    schedule.delete()
    recompute_last_worn(item_ids)  # last_worn_date kembali ke jadwal terakhir sebelumnya
    messages.success(request, f'Jadwal {format_tanggal(tanggal)} dihapus.')
    return redirect(_month_url(tanggal))