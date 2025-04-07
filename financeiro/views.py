from .utils import interpretar_mensagem, formatar_resposta_registro, formatar_resposta_consulta
import json
from datetime import datetime
from django.utils.timezone import make_aware
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
import requests
from decouple import config

from .models import User, Category, Transaction
from .serializers import TransactionSerializer
from .utils import formatar_resposta_registro, formatar_resposta_consulta


class InterpretarTransacaoView(APIView):
    def post(self, request):
        try:
            data = request.POST  # application/x-www-form-urlencoded

            phone_number = data.get("contact_phone_number", "").strip()
            nome_contato = data.get("contact_name", "").strip()
            description = data.get("message_body", "").strip()

            if not phone_number or not description:
                return Response({"error": "Campos 'phone_number' e 'description' são obrigatórios."}, status=400)

            # Interpreta a mensagem
            interpretado_raw = interpretar_mensagem(description)
            interpretado = json.loads(interpretado_raw)

            print("INTERPRETADO:", interpretado)

            if interpretado["tipo"] == "irrelevante":
                return Response({"error": "Mensagem irrelevante."}, status=400)

            # Busca ou cria o usuário
            user, created = User.objects.get_or_create(phone_number=phone_number)
            if created and nome_contato:
                user.name = nome_contato
                user.save()

            # REGISTRO
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

            # CONSULTA
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

            # Envia mensagem de resposta via WhatsGw
            resposta = {
                "apiKey": config("APIKEY_WG"),
                "phone_number": data.get("phone_number"),  # número da instância (seu número)
                "contact_phone_number": phone_number,
                "contact_name": nome_contato or phone_number,
                "chat_type": "user",
                "message_type": "text",
                "message_body": mensagem,
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=headers)

            return Response(data=mensagem, status=200)

        except Exception as e:
            return Response({"error": f"Erro ao interpretar ou processar mensagem: {str(e)}"}, status=500)
