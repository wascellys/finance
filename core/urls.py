
from django.contrib import admin
from django.urls import path

from financeiro.views import InterpretarTransacaoView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/transaction/", InterpretarTransacaoView.as_view(), name="transaction-register")
]
