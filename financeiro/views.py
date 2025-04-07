import json
from datetime import datetime

import requests
from decouple import config
from django.db.models import Sum
from django.shortcuts import render
from django.utils.timezone import make_aware

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import User, Category, Transaction
from .serializers import TransactionSerializer
from .utils import interpretar_mensagem, formatar_resposta_registro, formatar_resposta_consulta
from django.db.models import Sum


class InterpretarTransacaoView(APIView):
    def post(self, request):
        try:
            body = request.data

            # Extrair telefone
            raw_phone = body.get("key", {}).get("remoteJid", "")
            phone_number = raw_phone.replace("@s.whatsapp.net", "")

            # Extrair nome do contato (opcional)
            nome_contato = body.get("pushName", "")

            # Extrair mensagem enviada
            description = body.get("message", {}).get("conversation", "").strip()

            if not phone_number or not description:
                return Response({"error": "Campos 'phone_number' e 'description' são obrigatórios."}, status=400)

            # Interpretar a mensagem
            interpretado_raw = interpretar_mensagem(description)
            interpretado = json.loads(interpretado_raw)

            if interpretado["tipo"] == "irrelevante":
                return Response({"error": "Mensagem irrelevante."}, status=400)

            # Buscar ou criar o usuário
            user, created = User.objects.get_or_create(phone_number=phone_number)
            if created and nome_contato:
                user.name = nome_contato
                user.save()

            # REGISTRO DE TRANSAÇÃO
            if interpretado["tipo"] == "registro":
                categoria, _ = Category.objects.get_or_create(name=interpretado["categoria"].strip().lower())
                tipo_lancamento = interpretado.get("tipo_lancamento", "despesa")
                data_transacao = interpretado.get("data")
                created_at = make_aware(datetime.strptime(data_transacao, "%Y-%m-%d")) if data_transacao else None

                transacao = Transaction.objects.create(
                    user=user,
                    category=categoria,
                    amount=interpretado["valor"],
                    description=interpretado["descricao"],
                    tipo=tipo_lancamento,
                    created_at=created_at
                )

                mensagem = formatar_resposta_registro(transacao)

            # CONSULTA DE TRANSAÇÕES
            elif interpretado["tipo"] == "consulta":
                data_inicial = datetime.strptime(interpretado["data_inicial"], "%Y-%m-%d")
                data_final = datetime.strptime(interpretado["data_final"], "%Y-%m-%d")

                transacoes = Transaction.objects.filter(
                    user=user,
                    created_at__date__gte=data_inicial,
                    created_at__date__lte=data_final
                )

                categoria_nome = interpretado.get("categoria")
                if categoria_nome:
                    transacoes = transacoes.filter(category__name__iexact=categoria_nome)

                tipo_lancamento = interpretado.get("tipo_lancamento")
                if tipo_lancamento:
                    transacoes = transacoes.filter(tipo=tipo_lancamento)

                total = transacoes.aggregate(total_gasto=Sum("amount"))["total_gasto"] or 0
                lista = TransactionSerializer(transacoes, many=True).data

                mensagem = formatar_resposta_consulta(transacoes, data_inicial, data_final, categoria_nome,
                                                      tipo_lancamento)

            else:
                return Response({"error": "Tipo de ação não reconhecido."}, status=400)

            # Enviar resposta via WhatsGw
            data = {
                "apiKey": config('APIKEY_WG'),
                "phone_number": "5588988287586",  # Seu número de envio (fixo)
                "contact_phone_number": phone_number,
                "contact_name": nome_contato or phone_number,
                "chat_type": "user",
                "message_type": "text",
                "message_body": mensagem,
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            requests.post(f"{config('APIKEY')}/Send", data=data, headers=headers)

            return Response({"status": "mensagem enviada com sucesso"})

        except Exception as e:
            return Response({"error": f"Erro ao interpretar ou processar mensagem: {str(e)}"}, status=500)
