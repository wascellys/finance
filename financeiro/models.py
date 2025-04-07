from django.db import models


class User(models.Model):
    phone_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.phone_number


class Category(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TIPOS = (
        ("receita", "Receita"),
        ("despesa", "Despesa"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    tipo = models.CharField(max_length=10, choices=TIPOS)  # <-- novo campo
    created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tipo.upper()}: {self.description} - R${self.amount}"
