from django.conf import settings
from django.db import models

from items_for_swap.models import ItemForSwap


class LikedSwapItem(models.Model):
    """Pakaian Items for Swap yang disimpan sebagai favorit pengguna."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='liked_swap_items',
    )
    listing = models.ForeignKey(
        ItemForSwap,
        on_delete=models.CASCADE,
        related_name='likes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'listing'], name='unique_user_liked_swap_item'),
        ]

    def __str__(self):
        return f'{self.user} menyukai {self.listing}'
