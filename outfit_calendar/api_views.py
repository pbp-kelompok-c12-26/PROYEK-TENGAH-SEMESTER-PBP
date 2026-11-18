from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OutfitSchedule, recompute_last_worn
from .serializers import OutfitScheduleSerializer


class SessionAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]


class OutfitScheduleListAPIView(SessionAPIView):
    def get(self, request):
        schedules = OutfitSchedule.objects.filter(user=request.user).select_related('outfit').prefetch_related('worn_items')
        return Response(OutfitScheduleSerializer(schedules, many=True, context={'request': request}).data)

    def post(self, request):
        serializer = OutfitScheduleSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(OutfitScheduleSerializer(serializer.save(), context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class OutfitScheduleDetailAPIView(SessionAPIView):
    def get_object(self, pk):
        try:
            return OutfitSchedule.objects.select_related('outfit').prefetch_related('worn_items').get(
                pk=pk, user=self.request.user,
            )
        except OutfitSchedule.DoesNotExist:
            raise NotFound('Jadwal outfit tidak ditemukan.')

    def get(self, request, pk):
        return Response(OutfitScheduleSerializer(self.get_object(pk), context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk, False)

    def patch(self, request, pk):
        return self._update(request, pk, True)

    def _update(self, request, pk, partial):
        serializer = OutfitScheduleSerializer(self.get_object(pk), data=request.data, partial=partial,
                                              context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(OutfitScheduleSerializer(serializer.save(), context={'request': request}).data)

    def delete(self, request, pk):
        schedule = self.get_object(pk)
        item_ids = list(schedule.worn_items.values_list('clothing_item_id', flat=True))
        schedule.delete()
        recompute_last_worn(item_ids)
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def schedule_list(request):
    return OutfitScheduleListAPIView.as_view()(request._request)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def schedule_detail(request, pk):
    return OutfitScheduleDetailAPIView.as_view()(request._request, pk=pk)
