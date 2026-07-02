from django.contrib.auth.models import User
from rest_framework import serializers
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['is_suspended', 'suspension_reason', 'phone', 'created_at']
        read_only_fields = ['created_at']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    # Flat, top-level mirror of profile.is_suspended so consumers (rentals-
    # service's bootstrap sync) don't have to dig into a nested object.
    is_suspended = serializers.BooleanField(source='profile.is_suspended', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'profile', 'is_suspended', 'date_joined']
        read_only_fields = ['date_joined']
