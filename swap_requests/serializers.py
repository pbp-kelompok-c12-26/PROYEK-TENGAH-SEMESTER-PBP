from rest_framework import serializers

from digital_wardrobe.models import ClothingItem
from digital_wardrobe.serializers import ClothingItemSummarySerializer
from items_for_swap.models import ItemForSwap

from .forms import offerable_items
from .models import SwapRequest


class SwapRequestSerializer(serializers.ModelSerializer):
    requester = serializers.CharField(source='requester.username', read_only=True)
    owner = serializers.CharField(source='owner.username', read_only=True)
    requested_item = ClothingItemSummarySerializer(read_only=True)
    offered_item = ClothingItemSummarySerializer(read_only=True)
    code = serializers.CharField(read_only=True)
    status_note = serializers.CharField(read_only=True)
    role = serializers.SerializerMethodField()

    class Meta:
        model = SwapRequest
        fields = [
            'id', 'code', 'requester', 'owner', 'requested_item', 'offered_item',
            'requested_item_name', 'offered_item_name', 'message', 'status',
            'status_note', 'requester_confirmation', 'owner_confirmation', 'role',
            'created_at', 'updated_at', 'responded_at', 'completed_at',
        ]
        read_only_fields = fields

    def get_role(self, obj):
        request = self.context.get('request')
        return obj.role_of(request.user) if request else None


class SwapRequestCreateSerializer(serializers.ModelSerializer):
    requested_item_id = serializers.PrimaryKeyRelatedField(
        source='requested_item', queryset=ClothingItem.objects.all(), write_only=True,
    )
    offered_item_id = serializers.PrimaryKeyRelatedField(
        source='offered_item', queryset=ClothingItem.objects.all(), write_only=True,
    )

    class Meta:
        model = SwapRequest
        fields = ['requested_item_id', 'offered_item_id', 'message']

    def validate(self, attrs):
        user = self.context['request'].user
        requested = attrs['requested_item']
        offered = attrs['offered_item']
        listing = ItemForSwap.objects.available().filter(
            clothing_item=requested, clothing_item__deleted_at__isnull=True,
            clothing_item__is_listed_for_swap=True,
        ).first()
        if listing is None:
            raise serializers.ValidationError({'requested_item_id': 'Pakaian yang diminta sudah tidak tersedia untuk ditukar.'})
        if requested.user_id == user.id:
            raise serializers.ValidationError({'requested_item_id': 'Kamu tidak bisa mengajukan swap untuk pakaianmu sendiri.'})
        if offered not in offerable_items(user):
            raise serializers.ValidationError({'offered_item_id': 'Pakaian yang ditawarkan tidak valid atau sedang dipakai request aktif.'})
        if SwapRequest.objects.filter(
            requester=user, requested_item=requested, offered_item=offered,
            status=SwapRequest.PENDING,
        ).exists():
            raise serializers.ValidationError('Kamu sudah mengirim request yang sama dan masih menunggu jawaban.')
        attrs['listing'] = listing
        return attrs

    def create(self, validated_data):
        listing = validated_data.pop('listing')
        requested = validated_data['requested_item']
        offered = validated_data['offered_item']
        return SwapRequest.objects.create(
            requester=self.context['request'].user,
            owner=requested.user,
            requested_item=requested,
            offered_item=offered,
            requested_item_name=requested.name,
            offered_item_name=offered.name,
            requested_listing_cycle_key=listing.cycle_key,
            **{key: value for key, value in validated_data.items()
               if key not in ('requested_item', 'offered_item')},
        )


class SwapRequestUpdateSerializer(serializers.ModelSerializer):
    offered_item_id = serializers.PrimaryKeyRelatedField(
        source='offered_item', queryset=ClothingItem.objects.all(), required=False,
    )

    class Meta:
        model = SwapRequest
        fields = ['offered_item_id', 'message']

    def validate_offered_item_id(self, item):
        user = self.context['request'].user
        if item.pk != self.instance.offered_item_id and item not in offerable_items(user):
            raise serializers.ValidationError('Pakaian yang ditawarkan tidak valid atau sedang dipakai request aktif.')
        return item

    def validate(self, attrs):
        offered = attrs.get('offered_item', self.instance.offered_item)
        if not ItemForSwap.objects.available().filter(
            clothing_item=self.instance.requested_item,
            clothing_item__deleted_at__isnull=True,
            clothing_item__is_listed_for_swap=True,
        ).exists():
            raise serializers.ValidationError('Pakaian yang diminta sudah tidak tersedia untuk ditukar.')
        duplicate = SwapRequest.objects.filter(
            requester=self.context['request'].user,
            requested_item=self.instance.requested_item,
            offered_item=offered,
            status=SwapRequest.PENDING,
        ).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError('Kamu sudah mengirim request yang sama dan masih menunggu jawaban.')
        return attrs

    def update(self, instance, validated_data):
        offered = validated_data.get('offered_item')
        if offered:
            instance.offered_item_name = offered.name
        return super().update(instance, validated_data)
