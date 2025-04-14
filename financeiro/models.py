from django.db import models
from django.utils.crypto import get_random_string


class User(models.Model):
    phone_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.phone_number


class MainCategory(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=50)
    main_category = models.ForeignKey(MainCategory, on_delete=models.CASCADE, related_name="subcategories")

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TIPOS = (
        ("receita", "Receita"),
        ("despesa", "Despesa"),
    )
    code = models.CharField(max_length=5, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    created_at = models.DateTimeField(null=True, blank=True)
    date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tipo.upper()}: {self.description} - R${self.amount}"

    def generate_code(self):
        return get_random_string(5, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')

    def save(self, *args, **kwargs):
        if not self.code:
            new_code = self.generate_code()

            # Garante unicidade
            while Transaction.objects.filter(code=new_code).exists():
                new_code = self.generate_code()
            self.code = new_code
        super().save(*args, **kwargs)
