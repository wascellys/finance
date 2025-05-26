from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_index, name='dashboard_index'),
    path('transactions/', views.transactions_list, name='transactions_list'),
    path('categories/', views.categories_analysis, name='categories_analysis'),
    path('reports/', views.financial_reports, name='financial_reports'),
    path('temp/<str:token>/', views.temp_access, name='temp_access'),
    path('access-error/', views.temp_access_error, name='temp_access_error'),
    path('api/chart-data/', views.chart_data_api, name='chart_data_api'),
    path('api/transaction-data/', views.transaction_data_api, name='transaction_data_api'),
]
