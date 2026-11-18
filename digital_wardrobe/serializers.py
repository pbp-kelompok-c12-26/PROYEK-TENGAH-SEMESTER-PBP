from pathlib import Path

from rest_framework import serializers

from .models import ClothingItem, Outfit

MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = ('image/jpeg', 'image/png')
ALLOWED_IMAGE_EXTS = ('.jpg', '.jpeg', '.png')


class ClothingItemSerializer(serializers.ModelSerializer):
    """Representasi pakaian pribadi; flag lintas-modul hanya untuk dibaca."""

    size_label = serializers.CharField(read_only=True)
    is_footwear = serializers.BooleanField(read_only=True)
    is_idle = serializers.BooleanField(read_only=True)
    is_listed_for_swap = serializers.BooleanField(read_only=True)
    deleted_at = serializers.DateTimeField(read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ClothingItem
        fields = [
            'id', 'user', 'name', 'category', 'size', 'shoe_size', 'gender',
            'condition', 'color', 'description', 'image', 'size_label',
            'is_footwear', 'is_idle', 'is_listed_for_swap', 'last_worn_date',
            'deleted_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'user', 'is_idle', 'is_listed_for_swap', 'last_worn_date',
            'deleted_at', 'created_at', 'updated_at',
        ]
        extra_kwargs = {'image': {'required': True}}

    def validate(self, attrs):
        category = attrs.get('category', getattr(self.instance, 'category', None))
        size = attrs.get('size', getattr(self.instance, 'size', ''))
        shoe_size = attrs.get('shoe_size', getattr(self.instance, 'shoe_size', None))
        if category == 'footwear':
            if not shoe_size:
                raise serializers.ValidationError({'shoe_size': 'Wajib diisi untuk sepatu.'})
            attrs['size'] = ''
        elif category:
            if not size:
                raise serializers.ValidationError({'size': 'Wajib diisi.'})
            attrs['shoe_size'] = None
        return attrs

    def validate_image(self, image):
        if image.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError('Ukuran foto maksimal 5 MB.')
        content_type = getattr(image, 'content_type', '')
        if content_type not in ALLOWED_IMAGE_TYPES or Path(image.name).suffix.lower() not in ALLOWED_IMAGE_EXTS:
            raise serializers.ValidationError('Format foto harus JPG atau PNG.')
        return image


class ClothingItemSummarySerializer(serializers.ModelSerializer):
    size_label = serializers.CharField(read_only=True)

    class Meta:
        model = ClothingItem
        fields = ['id', 'name', 'category', 'size_label', 'image', 'condition', 'color']


class OutfitSerializer(serializers.ModelSerializer):
    items = ClothingItemSummarySerializer(many=True, read_only=True)
    item_ids = serializers.PrimaryKeyRelatedField(
        source='items', queryset=ClothingItem.objects.all(), many=True, write_only=True,
    )

    class Meta:
        model = Outfit
        fields = ['id', 'name', 'description', 'items', 'item_ids', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_item_ids(self, items):
        user = self.context['request'].user
        items = list(items)
        if not items:
            raise serializers.ValidationError('Pilih minimal 1 pakaian.')
        if len(items) > Outfit.MAX_ITEMS:
            raise serializers.ValidationError(f'Satu outfit maksimal {Outfit.MAX_ITEMS} pakaian.')
        existing_ids = set(self.instance.items.values_list('pk', flat=True)) if self.instance else set()
        if any(item.user_id != user.id and item.pk not in existing_ids for item in items):
            raise serializers.ValidationError('Pakaian baru harus berasal dari lemarimu sendiri.')
        return items

    def create(self, validated_data):
        items = validated_data.pop('items')
        outfit = Outfit.objects.create(user=self.context['request'].user, **validated_data)
        outfit.items.set(items)
        return outfit

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if items is not None:
            instance.items.set(items)
        return instance
