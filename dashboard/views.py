import os
import uuid
import pandas as pd
import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from financeiro.models import User, Transaction, Category, MainCategory
from .models import TemporaryLink


# Middleware para autenticação por token
def token_auth_middleware(get_response):
    def middleware(request):
        # Excluir rotas de validação de token
        if request.path.startswith('/dashboard/temp/'):
            return get_response(request)

        # Verificar token na sessão para todas as rotas do dashboard
        if request.path.startswith('/dashboard/'):
            token = request.session.get('auth_token')
            if not token:
                return redirect('temp_access_error')

            # Verificar validade do token
            is_valid, user = is_valid_token(token)
            if not is_valid:
                # Limpar sessão e redirecionar para erro
                request.session.pop('auth_token', None)
                return redirect('temp_access_error')

            # Adicionar usuário ao request para uso nas views
            request.user = user

        return get_response(request)

    return middleware


# Função para verificar se o token é válido
def is_valid_token(token):
    try:
        temp_link = TemporaryLink.objects.get(token=token)
        return temp_link.is_valid, temp_link.user
    except TemporaryLink.DoesNotExist:
        return False, None


# Decorator para verificar acesso via token
def token_required(view_func):
    def wrapped_view(request, *args, **kwargs):
        token = request.session.get('auth_token')
        if not token:
            return redirect('temp_access_error')

        is_valid, user = is_valid_token(token)
        if not is_valid:
            request.session.pop('auth_token', None)
            return redirect('temp_access_error')

        request.user = user
        return view_func(request, *args, **kwargs)

    return wrapped_view


# View para página principal do dashboard
@token_required
def dashboard_index(request):
    # Obter usuário atual
    user = request.user

    # Obter data atual e data de 30 dias atrás
    today = timezone.now()
    thirty_days_ago = today - timedelta(days=30)

    # Obter transações dos últimos 30 dias
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=thirty_days_ago
    ).order_by('-date')

    # Calcular saldo atual
    receitas = Transaction.objects.filter(
        user=user,
        tipo='receita'
    ).aggregate(total=Sum('amount'))['total'] or 0

    despesas = Transaction.objects.filter(
        user=user,
        tipo='despesa'
    ).aggregate(total=Sum('amount'))['total'] or 0

    saldo = float(receitas) - float(despesas)

    # Obter últimas 10 transações
    ultimas_transacoes = transactions[:10]

    # Obter categorias principais para despesas
    main_categories = MainCategory.objects.all()
    categorias_despesas = {}

    for mc in main_categories:
        total_categoria = Transaction.objects.filter(
            user=user,
            tipo='despesa',
            category__main_category=mc,
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('amount'))['total'] or 0

        if total_categoria > 0:
            categorias_despesas[mc.name] = float(total_categoria)

    # Preparar dados para gráficos
    chart_data = {
        'saldo': float(saldo),
        'receitas': float(receitas),
        'despesas': float(despesas),
        'categorias_despesas': categorias_despesas
    }

    context = {
        'user': user,
        'transactions': ultimas_transacoes,
        'chart_data': json.dumps(chart_data),
        'saldo': saldo,
        'receitas': receitas,
        'despesas': despesas
    }

    return render(request, 'dashboard/index.html', context)


# View para lista de transações
@token_required
def transactions_list(request):
    user = request.user

    # Parâmetros de filtro
    data_inicial = request.GET.get('data_inicial')
    data_final = request.GET.get('data_final')
    categoria = request.GET.get('categoria')
    tipo = request.GET.get('tipo')

    # Filtrar transações
    transactions = Transaction.objects.filter(user=user).order_by('-date')

    if data_inicial:
        data_inicial = datetime.strptime(data_inicial, '%Y-%m-%d')
        transactions = transactions.filter(date__date__gte=data_inicial)

    if data_final:
        data_final = datetime.strptime(data_final, '%Y-%m-%d')
        transactions = transactions.filter(date__date__lte=data_final)

    if categoria and categoria != 'all':
        try:
            cat = Category.objects.get(id=categoria)
            transactions = transactions.filter(category=cat)
        except Category.DoesNotExist:
            pass

    if tipo and tipo != 'all':
        transactions = transactions.filter(tipo=tipo)

    # Obter categorias para filtro
    categories = Category.objects.all()

    context = {
        'user': user,
        'transactions': transactions,
        'categories': categories,
        'data_inicial': data_inicial.strftime('%Y-%m-%d') if data_inicial else '',
        'data_final': data_final.strftime('%Y-%m-%d') if data_final else '',
        'categoria_selecionada': categoria,
        'tipo_selecionado': tipo
    }

    return render(request, 'dashboard/transactions.html', context)


# View para análise por categorias
@token_required
def categories_analysis(request):
    user = request.user

    # Obter data atual e data de 30 dias atrás
    today = timezone.now()
    thirty_days_ago = today - timedelta(days=30)

    # Obter categorias principais
    main_categories = MainCategory.objects.all()

    # Dados para gráfico de categorias principais
    main_category_data = {}
    total_despesas = 0

    for mc in main_categories:
        total = Transaction.objects.filter(
            user=user,
            tipo='despesa',
            category__main_category=mc,
            date__gte=thirty_days_ago
        ).aggregate(total=Sum('amount'))['total'] or 0

        if total > 0:
            main_category_data[mc.name] = float(total)
            total_despesas += float(total)

    # Dados para tabela de subcategorias
    subcategory_data = []
    for mc in main_categories:
        subcategories = Category.objects.filter(main_category=mc)
        for sc in subcategories:
            total = Transaction.objects.filter(
                user=user,
                tipo='despesa',
                category=sc,
                date__gte=thirty_days_ago
            ).aggregate(total=Sum('amount'))['total'] or 0

            if total > 0:
                subcategory_data.append({
                    'main_category': mc.name,
                    'subcategory': sc.name,
                    'total': float(total)
                })

    context = {
        'user': user,
        'main_category_data': json.dumps(main_category_data),
        'subcategory_data': subcategory_data,
        'total_despesas': total_despesas
    }

    return render(request, 'dashboard/categories.html', context)


# View para relatórios financeiros
@token_required
def financial_reports(request):
    user = request.user

    # Obter data atual
    today = timezone.now()

    # Dados para relatório mensal
    monthly_data = {}
    monthly_data_table = {}
    variation_data = {}

    for i in range(6):
        month_start = (today - timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0)
        next_month = month_start.replace(
            month=month_start.month + 1) if month_start.month < 12 else month_start.replace(year=month_start.year + 1,
                                                                                            month=1)

        receitas = Transaction.objects.filter(
            user=user,
            tipo='receita',
            date__gte=month_start,
            date__lt=next_month
        ).aggregate(total=Sum('amount'))['total'] or 0

        despesas = Transaction.objects.filter(
            user=user,
            tipo='despesa',
            date__gte=month_start,
            date__lt=next_month
        ).aggregate(total=Sum('amount'))['total'] or 0

        month_name = month_start.strftime('%b/%Y')
        monthly_data[month_name] = {
            'receitas': float(receitas),
            'despesas': float(despesas),
            'saldo': float(receitas - despesas)
        }

        monthly_data_table[month_name] = {
            'receitas': float(receitas),
            'despesas': float(despesas),
            'saldo': float(receitas - despesas)
        }

        # Calcular variação percentual (exceto para o primeiro mês)
        if i > 0:
            prev_month = (today - timedelta(days=30 * (i - 1))).replace(day=1, hour=0, minute=0, second=0)
            prev_month_name = prev_month.strftime('%b/%Y')

            prev_receitas = monthly_data[prev_month_name]['receitas']
            prev_despesas = monthly_data[prev_month_name]['despesas']

            receitas_var = ((float(receitas) - prev_receitas) / prev_receitas * 100) if prev_receitas > 0 else 0
            despesas_var = ((float(despesas) - prev_despesas) / prev_despesas * 100) if prev_despesas > 0 else 0

            variation_data[month_name] = {
                'receitas_var': receitas_var,
                'despesas_var': despesas_var
            }

    context = {
        'user': user,
        'monthly_data': json.dumps(monthly_data),
        'monthly_data_table': monthly_data_table,
        'variation_data': variation_data
    }

    return render(request, 'dashboard/reports.html', context)


# View para acesso via token temporário
def temp_access(request, token):
    try:
        temp_link = TemporaryLink.objects.get(token=token)

        # Verificar se o link expirou
        if temp_link.expires_at < timezone.now():
            return render(request, 'dashboard/access_error.html')

        # Armazenar token na sessão
        request.session['auth_token'] = token
        request.session['user_id'] = temp_link.user.id

        # Redirecionar para o dashboard
        return redirect('dashboard_index')
    except TemporaryLink.DoesNotExist:
        return render(request, 'dashboard/access_error.html')


# View para erro de acesso
def temp_access_error(request):
    return render(request, 'dashboard/access_error.html')


# API para dados de gráficos
@token_required
def chart_data_api(request):
    user = request.user

    # Obter período solicitado
    period = request.GET.get('period', '30')  # Padrão: 30 dias

    try:
        days = int(period)
    except ValueError:
        days = 30

    # Obter data atual e data inicial do período
    today = timezone.now()
    start_date = today - timedelta(days=days)

    # Dados para gráfico de fluxo de caixa
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date
    ).order_by('date')

    # Converter para DataFrame para facilitar a análise
    df = pd.DataFrame(list(transactions.values('date', 'amount', 'tipo')))

    if not df.empty:
        # Converter para datetime
        df['date'] = pd.to_datetime(df['date']).dt.date

        # Agrupar por data e tipo
        grouped = df.groupby(['date', 'tipo'])['amount'].sum().unstack(fill_value=0)

        # Garantir que temos colunas para receita e despesa
        if 'receita' not in grouped.columns:
            grouped['receita'] = 0
        if 'despesa' not in grouped.columns:
            grouped['despesa'] = 0

        # Calcular saldo acumulado
        grouped['saldo'] = grouped['receita'].cumsum() - grouped['despesa'].cumsum()

        # Converter para formato de lista para o gráfico
        dates = [d.strftime('%Y-%m-%d') for d in grouped.index]
        receitas = grouped['receita'].tolist()
        despesas = grouped['despesa'].tolist()
        saldos = grouped['saldo'].tolist()

        data = {
            'dates': dates,
            'receitas': receitas,
            'despesas': despesas,
            'saldos': saldos
        }
    else:
        data = {
            'dates': [],
            'receitas': [],
            'despesas': [],
            'saldos': []
        }

    return JsonResponse(data)


# API para dados de transações
@token_required
def transaction_data_api(request):
    user = request.user

    # Parâmetros de filtro
    data_inicial = request.GET.get('data_inicial')
    data_final = request.GET.get('data_final')
    categoria = request.GET.get('categoria')
    tipo = request.GET.get('tipo')

    # Filtrar transações
    transactions = Transaction.objects.filter(user=user).order_by('-date')

    if data_inicial:
        data_inicial = datetime.strptime(data_inicial, '%Y-%m-%d')
        transactions = transactions.filter(date__date__gte=data_inicial)

    if data_final:
        data_final = datetime.strptime(data_final, '%Y-%m-%d')
        transactions = transactions.filter(date__date__lte=data_final)

    if categoria and categoria != 'all':
        try:
            cat = Category.objects.get(id=categoria)
            transactions = transactions.filter(category=cat)
        except Category.DoesNotExist:
            pass

    if tipo and tipo != 'all':
        transactions = transactions.filter(tipo=tipo)

    # Converter para lista de dicionários
    data = []
    for t in transactions:
        data.append({
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d') if t.date else '',
            'description': t.description,
            'category': t.category.name if t.category else '',
            'amount': float(t.amount),
            'tipo': t.tipo
        })

    return JsonResponse({'data': data})
