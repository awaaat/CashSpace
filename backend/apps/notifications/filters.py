from django_filters import rest_framework as filters
from .models import Notification


class NotificationFilter(filters.FilterSet):
    is_read = filters.BooleanFilter()
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    type = filters.ChoiceFilter(choices=Notification.Type.choices)

    class Meta:
        model = Notification
        fields = ["is_read", "type", "level"]