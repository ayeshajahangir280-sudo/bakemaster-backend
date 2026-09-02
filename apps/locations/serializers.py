from rest_framework.serializers import ModelSerializer
from .models import Location
class LocationSerializer(ModelSerializer):
 class Meta: model=Location; fields="__all__"; read_only_fields=("created_by","updated_by")
