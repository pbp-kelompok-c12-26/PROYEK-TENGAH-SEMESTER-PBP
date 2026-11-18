from rest_framework import serializers

from digital_wardrobe.models import Outfit

from .models import OutfitSchedule, ScheduledItem, recompute_last_worn


class ScheduledItemSerializer(serializers.ModelSerializer):
    clothing_item_id = serializers.IntegerField(read_only=True)
    is_deleted = serializers.BooleanField(read_only=True)

    class Meta:
        model = ScheduledItem
        fields = ['id', 'clothing_item_id', 'name', 'is_deleted']


class OutfitScheduleSerializer(serializers.ModelSerializer):
    outfit_id = serializers.PrimaryKeyRelatedField(source='outfit', queryset=Outfit.objects.all())
    outfit_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    worn_items = ScheduledItemSerializer(many=True, read_only=True)

    class Meta:
        model = OutfitSchedule
        fields = [
            'id', 'date', 'outfit_id', 'outfit_name', 'display_name', 'note',
            'worn_items', 'created_at', 'updated_at',
        ]
        read_only_fields = ['outfit_name', 'display_name', 'worn_items', 'created_at', 'updated_at']

    def validate(self, attrs):
        user = self.context['request'].user
        outfit = attrs.get('outfit', getattr(self.instance, 'outfit', None))
        day = attrs.get('date', getattr(self.instance, 'date', None))
        if outfit is None or outfit.user_id != user.id:
            raise serializers.ValidationError({'outfit_id': 'Outfit yang dipilih tidak valid.'})
        duplicate = OutfitSchedule.objects.filter(user=user, date=day)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({'date': 'Tanggal ini sudah punya jadwal outfit. Edit jadwalnya saja.'})
        return attrs

    def create(self, validated_data):
        schedule = OutfitSchedule.objects.create(user=self.context['request'].user, **validated_data)
        schedule.save_snapshot()
        schedule.update_last_worn()
        return schedule

    def update(self, instance, validated_data):
        old_item_ids = list(instance.worn_items.values_list('clothing_item_id', flat=True))
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        instance.save_snapshot()
        recompute_last_worn(old_item_ids + list(instance.worn_items.values_list('clothing_item_id', flat=True)))
        return instance
