from rest_framework import serializers

from digital_wardrobe.models import ClothingItem
from digital_wardrobe.serializers import ClothingItemSummarySerializer
from home.wilayah import resolve_location

from .models import ItemForSwap


class ItemForSwapSerializer(serializers.ModelSerializer):
    """Listing hanya dapat dibuat dari pakaian milik user yang sedang login."""

    clothing_item = ClothingItemSummarySerializer(read_only=True)
    clothing_item_id = serializers.PrimaryKeyRelatedField(
        source='clothing_item', queryset=ClothingItem.objects.all(), write_only=True,
    )
    owner = serializers.CharField(source='user.username', read_only=True)
    photo_url = serializers.CharField(read_only=True)
    meeting_area = serializers.CharField(read_only=True)
    request_count = serializers.IntegerField(read_only=True)

    def get_fields(self):
        """Pakaian hanya wajib saat membuat listing; tidak boleh diganti saat update."""
        fields = super().get_fields()
        fields['clothing_item_id'].required = self.instance is None
        return fields

    class Meta:
        model = ItemForSwap
        fields = [
            'id', 'clothing_item', 'clothing_item_id', 'owner', 'meeting_location',
            'meeting_city_code', 'meeting_city', 'meeting_province', 'meeting_place',
            'reason', 'status', 'photo_url', 'meeting_area', 'request_count', 'posted_at',
        ]
        read_only_fields = [
            'meeting_location', 'meeting_city', 'meeting_province', 'status',
            'photo_url', 'meeting_area', 'request_count', 'posted_at',
        ]
        extra_kwargs = {
            'meeting_city_code': {'write_only': True},
            'meeting_place': {'required': True},
        }

    def validate(self, attrs):
        if self.instance is None:
            item = attrs['clothing_item']
            if item.user_id != self.context['request'].user.id:
                raise serializers.ValidationError({'clothing_item_id': 'Pakaian ini bukan milikmu.'})
        code = attrs.get('meeting_city_code')
        if code:
            try:
                attrs['location'] = resolve_location(code)
            except Exception as error:  # forms.ValidationError from existing location validator
                raise serializers.ValidationError({'meeting_city_code': list(getattr(error, 'messages', [str(error)]) )})
        elif self.instance is None:
            raise serializers.ValidationError({'meeting_city_code': 'Pilih lokasi dari daftar rekomendasi.'})
        return attrs

    def validate_meeting_place(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Detail tempat wajib diisi.')
        return value

    def create(self, validated_data):
        location = validated_data.pop('location')
        item = validated_data.pop('clothing_item')
        validated_data.pop('meeting_city_code', None)
        return ItemForSwap.list_item(
            clothing_item=item,
            user=self.context['request'].user,
            location=location,
            meeting_place=validated_data.get('meeting_place', ''),
            reason=validated_data.get('reason', ''),
        )

    def update(self, instance, validated_data):
        if not instance.is_available:
            raise serializers.ValidationError({'detail': 'Item yang sudah swapped tidak bisa diedit.'})
        location = validated_data.pop('location', None)
        validated_data.pop('meeting_city_code', None)
        if location:
            instance.set_meeting_location(location, validated_data.get('meeting_place', instance.meeting_place))
        elif 'meeting_place' in validated_data:
            # PATCH lokasi detail saja tetap harus memperbarui label lokasi yang
            # ditampilkan, tanpa bergantung pada panggilan ulang API wilayah.
            place = validated_data['meeting_place']
            label = ', '.join(part for part in (instance.meeting_city, instance.meeting_province) if part)
            if label:
                instance.meeting_location = f'{place}, {label}'
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
