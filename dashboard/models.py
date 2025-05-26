from django.db import models
from django.utils import timezone
from financeiro.models import User

class TemporaryLink(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='temp_links')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"Link para {self.user.name} - expira em {self.expires_at.strftime('%d/%m/%Y %H:%M')}"
    
    @property
    def is_valid(self):
        return self.expires_at > timezone.now()
