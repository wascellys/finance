from django.contrib import admin
from .models import TemporaryLink

@admin.register(TemporaryLink)
class TemporaryLinkAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'expires_at', 'created_at', 'is_valid')
    search_fields = ('user__phone_number', 'token')
    list_filter = ('created_at', 'expires_at')
    readonly_fields = ('created_at',)
