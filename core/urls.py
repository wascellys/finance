from django.contrib import admin
from django.urls import path, include

from financeiro.views import InterpretarTransacaoView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/transaction/", InterpretarTransacaoView.as_view(), name="transaction-register"),
    path('dashboard/', include('dashboard.urls')),

]
