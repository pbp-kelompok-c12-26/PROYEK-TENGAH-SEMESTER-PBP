from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from digital_wardrobe.models import ClothingItem


class SwapRequestQuerySet(models.QuerySet):
    """Query bantu. Modul lain (mis. Items for Swap) boleh memakai ini."""

    def involving_item(self, item):
        return self.filter(Q(requested_item=item) | Q(offered_item=item))

    def is_locked(self, item):
        """True kalau pakaian sedang dalam proses tukar (Awaiting exchange).
        Pakaian yang terkunci tidak boleh dikembalikan ke lemari atau dihapus."""
        return self.involving_item(item).filter(status=SwapRequest.AWAITING).exists()

    def sync_availability(self):
        """Request Pending yang pakaiannya sudah tidak ditawarkan / sudah dihapus
        otomatis jadi 'Item not available'."""
        return self.filter(status=SwapRequest.PENDING).filter(
            Q(requested_item__isnull=True) | Q(offered_item__isnull=True)
            | Q(requested_item__is_listed_for_swap=False) | Q(offered_item__is_listed_for_swap=False)
        ).update(status=SwapRequest.UNAVAILABLE, updated_at=timezone.now())


class SwapRequest(models.Model):
    PENDING = 'pending'
    REJECTED = 'rejected'
    AWAITING = 'awaiting_exchange'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    UNAVAILABLE = 'unavailable'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (REJECTED, 'Rejected'),
        (AWAITING, 'Awaiting exchange'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
        (UNAVAILABLE, 'Item not available'),
    ]
    # warna badge status (class Tailwind)
    STATUS_STYLES = {
        PENDING: 'bg-[#DCEBFF] text-[#2B4C9B]',
        REJECTED: 'bg-[#FBE1EA] text-swBerry',
        AWAITING: 'bg-[#E4F3D5] text-[#3C6E2A]',
        COMPLETED: 'bg-[#3E8E4E] text-white',
        CANCELLED: 'bg-[#ECEAF1] text-swSlate',
        UNAVAILABLE: 'bg-[#FDECC8] text-[#8A5A00]',
    }
    STATUS_NOTES = {
        PENDING: 'Menunggu pemilik pakaian menyetujui atau menolak request ini.',
        REJECTED: 'Request ini ditolak oleh pemilik pakaian.',
        AWAITING: 'Request disetujui. Hubungi satu sama lain untuk mengatur pertukaran, lalu konfirmasi penyelesaian di bawah.',
        COMPLETED: 'Pertukaran selesai. Pakaian sudah pindah ke lemari pemilik barunya.',
        CANCELLED: 'Pertukaran dibatalkan. Kedua pakaian kembali tersedia untuk ditukar.',
        UNAVAILABLE: 'Salah satu pakaian sudah tidak tersedia untuk ditukar.',
    }

    DONE = 'done'
    CANCEL = 'cancel'
    CONFIRM_CHOICES = [(DONE, 'Selesai swap'), (CANCEL, 'Batalkan swap')]

    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swap_requests_sent')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swap_requests_received')
    # Pakaian milik owner yang diminta, dan pakaian milik requester yang ditawarkan.
    # SET_NULL + snapshot nama supaya riwayat tetap ada walau pakaian dihapus.
    requested_item = models.ForeignKey(ClothingItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_swap_requests')
    offered_item = models.ForeignKey(ClothingItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_swap_requests')
    requested_item_name = models.CharField(max_length=100)
    offered_item_name = models.CharField(max_length=100)

    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    requester_confirmation = models.CharField(max_length=10, choices=CONFIRM_CHOICES, blank=True)
    owner_confirmation = models.CharField(max_length=10, choices=CONFIRM_CHOICES, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = SwapRequestQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code}: {self.offered_item_name} ⇄ {self.requested_item_name}'

    # ---------- tampilan ----------
    @property
    def code(self):
        return f'SR-{self.pk:04d}'

    @property
    def status_style(self):
        return self.STATUS_STYLES.get(self.status, '')

    @property
    def status_note(self):
        return self.STATUS_NOTES.get(self.status, '')

    # ---------- hak akses ----------
    def role_of(self, user):
        if user.pk == self.requester_id:
            return 'requester'
        if user.pk == self.owner_id:
            return 'owner'
        return None

    def other_party(self, user):
        return self.owner if user.pk == self.requester_id else self.requester

    @property
    def can_delete(self):
        return self.status != self.AWAITING

    def can_edit(self, user):
        return user.pk == self.requester_id and self.status == self.PENDING

    def can_respond(self, user):
        return user.pk == self.owner_id and self.status == self.PENDING

    # ---------- alur status ----------
    def accept(self):
        """Setujui: request ini jadi Awaiting exchange, request Pending lain yang
        memakai salah satu pakaian ini jadi Item not available."""
        with transaction.atomic():
            self.status = self.AWAITING
            self.responded_at = timezone.now()
            self.save()
            SwapRequest.objects.filter(status=self.PENDING).filter(
                Q(requested_item__in=[self.requested_item_id, self.offered_item_id])
                | Q(offered_item__in=[self.requested_item_id, self.offered_item_id])
            ).exclude(pk=self.pk).update(status=self.UNAVAILABLE, updated_at=timezone.now())

    def reject(self):
        self.status = self.REJECTED
        self.responded_at = timezone.now()
        self.save()

    def confirm(self, user, choice):
        """Konfirmasi penyelesaian dari salah satu pihak (Selesai / Batalkan)."""
        if self.role_of(user) == 'requester':
            self.requester_confirmation = choice
        else:
            self.owner_confirmation = choice
        if self.CANCEL in (self.requester_confirmation, self.owner_confirmation):
            self.status = self.CANCELLED
            self.save()
        elif self.requester_confirmation == self.owner_confirmation == self.DONE:
            self.complete()
        else:
            self.save()

    def complete(self):
        """Kedua pihak sudah konfirmasi: pakaian berpindah pemilik."""
        with transaction.atomic():
            for item, new_owner in ((self.requested_item, self.requester), (self.offered_item, self.owner)):
                if item is None:
                    continue
                item.outfits.clear()  # keluarkan dari outfit milik pemilik lama
                item.user = new_owner
                item.is_listed_for_swap = False
                item.last_worn_date = None
                item.is_idle = False
                item.save()
            self.status = self.COMPLETED
            self.completed_at = timezone.now()
            self.save()
