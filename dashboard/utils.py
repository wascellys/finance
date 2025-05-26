import os

from django.contrib.auth.models import User
from django.utils import timezone
import uuid

from dashboard.models import TemporaryLink

BASE_URL = "http://localhost:8000"


def create_temp_link(user_id, expiry_days=1):
    try:
        user = User.objects.get(id=user_id)
        token = uuid.uuid4().hex
        expires_at = timezone.now() + timezone.timedelta(days=expiry_days)

        # Remover links antigos do mesmo usuário
        TemporaryLink.objects.filter(user=user).delete()

        # Criar novo link
        temp_link = TemporaryLink.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )

        url = f"{BASE_URL}/dashboard/temp/{token}/"

        return url
    except User.DoesNotExist:
        return None
