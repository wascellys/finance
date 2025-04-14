from django.contrib import admin
from .models import User, Category, Transaction, MainCategory


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'phone_number', 'name')
    search_fields = ('phone_number', 'name')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'main_category')
    search_fields = ('name',)
    list_filter = ('main_category',)


@admin.register(MainCategory)
class MainCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'category', 'amount', 'tipo', 'date', 'created_at')
    list_filter = ('category', 'tipo', 'date')
    search_fields = ('user__phone_number', 'description')
    date_hierarchy = 'date'  # agora usa a data real da transação
