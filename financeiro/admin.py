from django.contrib import admin
from .models import User, Category, Transaction


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'phone_number', 'name')
    search_fields = ('phone_number', 'name')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)
    search_fields = ('name',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'category', 'amount', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('user__phone_number', 'description')
    date_hierarchy = 'created_at'
