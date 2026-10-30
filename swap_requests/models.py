from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
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

    def has_active_request(self, item):
        """True jika item dipakai request yang masih Pending atau Awaiting."""
        return self.involving_item(item).filter(
            status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
        ).exists()

    def sync_availability(self):
        """Request aktif terkait listing yang dihapus otomatis menjadi Rejected."""
        active = self.filter(status__in=(SwapRequest.PENDING, SwapRequest.AWAITING)).filter(
            Q(requested_item__isnull=True) | Q(offered_item__isnull=True)
            | Q(requested_item__is_listed_for_swap=False)
            | Q(requested_item__deleted_at__isnull=False)
            | Q(offered_item__deleted_at__isnull=False)
        ).select_related('requester', 'owner')
        for swap in active:
            swap.status = SwapRequest.REJECTED
            swap.responded_at = timezone.now()
            swap.record_status_change()
            swap.save(update_fields=['status', 'responded_at', 'updated_at'])
        return active.count()

    def mark_listing_returned(self, listing):
        """Simpan siklus listing pada request lama lalu tandai bahwa listing dikembalikan."""
        related = self.filter(
            owner_id=listing.user_id,
            requested_item_id=listing.clothing_item_id,
            created_at__gte=listing.posted_at,
        )
        related.filter(
            Q(requested_listing_cycle_key__isnull=True)
            | Q(requested_listing_cycle_key=''),
        ).update(requested_listing_cycle_key=listing.cycle_key)
        return related.filter(
            requested_listing_cycle_key=listing.cycle_key,
        ).update(requested_listing_returned_to_wardrobe=True)

    def visible_to(self, user):
        return self.filter(
            Q(requester=user, requester_hidden=False)
            | Q(owner=user, owner_hidden=False)
        )

    def mark_seen_by(self, user):
        """Tandai perubahan status pada daftar request pengguna sebagai sudah dilihat."""
        visible = Q(swap_request__requester=user, swap_request__requester_hidden=False) | Q(
            swap_request__owner=user, swap_request__owner_hidden=False)
        notifications = SwapRequestNotification.objects.filter(
            recipient=user, read_at__isnull=True, swap_request__in=self,
        ).filter(visible)
        return notifications.update(read_at=timezone.now())


class SwapRequest(models.Model):
    PENDING = 'pending'
    REJECTED = 'rejected'
    AWAITING = 'awaiting_exchange'
    COMPLETED = 'completed'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (REJECTED, 'Rejected'),
        (AWAITING, 'Awaiting exchange'),
        (COMPLETED, 'Completed'),
    ]
    # class CSS warna badge status (lihat .sr-status--... di static/swap_requests/css/swap_requests.css)
    STATUS_STYLES = {
        PENDING: 'sr-status--pending',
        REJECTED: 'sr-status--rejected',
        AWAITING: 'sr-status--awaiting',
        COMPLETED: 'sr-status--completed',
    }
    STATUS_NOTES = {
        PENDING: 'Menunggu pemilik pakaian menyetujui atau menolak request ini.',
        REJECTED: 'Request ditolak, salah satu pihak membatalkan pertukaran, atau item telah dibatalkan untuk ditawarkan.',
        AWAITING: 'Request disetujui. Hubungi satu sama lain untuk mengatur pertukaran, lalu konfirmasi penyelesaian di bawah.',
        COMPLETED: 'Pertukaran selesai. Pakaian sudah pindah ke lemari pemilik barunya.',
    }

    DONE = 'done'
    CANCEL = 'cancel'
    CONFIRM_CHOICES = [(DONE, 'Selesai swap'), (CANCEL, 'Batalkan swap')]

    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swap_requests_sent')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swap_requests_received')
    # Pakaian milik owner yang diminta, dan pakaian milik requester yang ditawarkan.
    # SET_NULL + snapshot nama supaya riwayat tetap ada walau pakaian dihapus.
    requested_item = models.ForeignKey(ClothingItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_swap_requests')
    # Snapshot identitas listing; tidak memakai FK agar siklus tetap tersimpan setelah listing dihapus.
    requested_listing_cycle_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    requested_listing_returned_to_wardrobe = models.BooleanField(default=False)
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
    requester_hidden = models.BooleanField(default=False)
    owner_hidden = models.BooleanField(default=False)
    objects = SwapRequestQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code}: {self.offered_item_name} ⇄ {self.requested_item_name}'

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        actor = getattr(self, '_status_change_actor', None)
        if is_new:
            # Pengaju mengetahui request yang baru ia kirim; pemilik listing
            # mendapat notifikasi request baru.
            SwapRequestNotification.objects.create(
                swap_request=self, recipient=self.owner, status=self.status,
            )
        elif hasattr(self, '_status_change_actor'):
            recipients = [self.requester, self.owner]
            for recipient in recipients:
                if actor and recipient.pk == actor.pk:
                    continue
                SwapRequestNotification.objects.create(
                    swap_request=self, recipient=recipient, status=self.status,
                )
            del self._status_change_actor

    def record_status_change(self, actor=None):
        self._status_change_actor = actor

    def mark_seen_by(self, user):
        SwapRequest.objects.filter(pk=self.pk).mark_seen_by(user)

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
        """Setujui request ini jika kedua pakaian belum dipakai swap Awaiting lain."""
        with transaction.atomic():
            item_ids = [self.requested_item_id, self.offered_item_id]
            conflict = SwapRequest.objects.filter(status=self.AWAITING).exclude(pk=self.pk).filter(
                Q(requested_item_id__in=item_ids) | Q(offered_item_id__in=item_ids)
            ).exists()
            if conflict:
                raise ValidationError('Salah satu pakaian sedang menunggu pertukaran lain. Batalkan pertukaran itu bersama-sama terlebih dahulu.')
            self.status = self.AWAITING
            self.responded_at = timezone.now()
            self.record_status_change(actor=self.owner)
            self.save()

    def reject(self, actor=None):
        self.status = self.REJECTED
        self.responded_at = timezone.now()
        self.record_status_change(actor=actor or self.owner)
        self.save()

    def confirm(self, user, choice):
        """Konfirmasi penyelesaian dari salah satu pihak (Selesai / Batalkan)."""
        if self.role_of(user) == 'requester':
            self.requester_confirmation = choice
        else:
            self.owner_confirmation = choice
        if self.CANCEL in (self.requester_confirmation, self.owner_confirmation):
            # Swap butuh persetujuan kedua pihak. Kalau salah satu membatalkan,
            # pertukaran batal supaya kedua pakaian tidak terkunci selamanya.
            self.status = self.REJECTED
            self.responded_at = timezone.now()
            self.record_status_change(actor=user)
            self.save()
        elif self.requester_confirmation == self.owner_confirmation == self.DONE:
            self.complete(actor=user)
        else:
            self.save()

    def complete(self, actor=None):
        """Kedua pihak sudah konfirmasi: pakaian berpindah pemilik."""
        with transaction.atomic():
            # Tutup kedua listing publik sebelum pakaian berpindah pemilik.
            from items_for_swap.models import ItemForSwap
            ItemForSwap.objects.filter(
                clothing_item_id__in=[self.requested_item_id, self.offered_item_id],
                status=ItemForSwap.AVAILABLE,
            ).update(status=ItemForSwap.SWAPPED)
            pending = SwapRequest.objects.filter(status=self.PENDING).exclude(pk=self.pk).filter(
                Q(requested_item_id__in=[self.requested_item_id, self.offered_item_id])
                | Q(offered_item_id__in=[self.requested_item_id, self.offered_item_id])
            ).select_related('requester', 'owner')
            for other in pending:
                other.status = self.REJECTED
                other.responded_at = timezone.now()
                other.record_status_change()
                other.save(update_fields=['status', 'responded_at', 'updated_at'])
            for item, new_owner in ((self.requested_item, self.requester), (self.offered_item, self.owner)):
                if item is None:
                    continue
                item.user = new_owner
                item.is_listed_for_swap = False
                item.last_worn_date = None
                item.is_idle = False
                item.save()
            self.status = self.COMPLETED
            self.completed_at = timezone.now()
            self.record_status_change(actor=actor)
            self.save()


class SwapRequestNotification(models.Model):
    """Satu notifikasi untuk satu perubahan status yang perlu dilihat user."""

    swap_request = models.ForeignKey(
        SwapRequest, on_delete=models.CASCADE, related_name='notifications',
    )
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='swap_request_notifications',
    )
    status = models.CharField(max_length=20, choices=SwapRequest.STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'read_at'], name='swap_notif_rec_read_idx')]

    def __str__(self):
        return f'{self.swap_request.code}: {self.status} → {self.recipient}'
