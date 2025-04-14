from .utils import interpretar_mensagem, formatar_resposta_registro, formatar_resposta_consulta, gerar_grafico_base64
import json
from datetime import datetime
from django.utils.timezone import make_aware, now
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
import requests
from decouple import config

from .models import User, Category, MainCategory, Transaction
from .serializers import TransactionSerializer


class InterpretarTransacaoView(APIView):
    def post(self, request):
        try:
            data = request.POST

            phone_number = data.get("contact_phone_number", "").strip()
            nome_contato = data.get("contact_name", "").strip()
            description = data.get("message_body", "").strip()

            if not phone_number or not description:
                return Response({"error": "Campos 'phone_number' e 'description' são obrigatórios."}, status=400)

            interpretado_raw = interpretar_mensagem(description)
            interpretado = json.loads(interpretado_raw)

            print("INTERPRETADO:", interpretado)

            if interpretado["tipo"] == "irrelevante":
                return Response({"error": "Mensagem irrelevante."}, status=400)

            user, created = User.objects.get_or_create(phone_number=phone_number)
            if created and nome_contato:
                user.name = nome_contato
                user.save()

            if interpretado["tipo"] == "registro":
                categoria_nome = interpretado["categoria"].strip().lower()
                categoria, _ = Category.objects.get_or_create(name=categoria_nome)

                tipo_lancamento = interpretado.get("tipo_lancamento", "despesa")
                data_transacao = interpretado.get("data")
                date = make_aware(datetime.strptime(data_transacao, "%Y-%m-%d")) if data_transacao else None

                transacao = Transaction.objects.create(
                    user=user,
                    category=categoria,
                    amount=interpretado["valor"],
                    description=interpretado["descricao"],
                    tipo=tipo_lancamento,
                    created_at=now(),
                    date=date
                )

                mensagem = formatar_resposta_registro(transacao)

            elif interpretado["tipo"] == "consulta":
                data_inicial = datetime.strptime(interpretado["data_inicial"], "%Y-%m-%d")
                data_final = datetime.strptime(interpretado["data_final"], "%Y-%m-%d")

                transacoes = Transaction.objects.filter(
                    user=user,
                    date__date__gte=data_inicial,
                    date__date__lte=data_final
                )

                categoria_nome = interpretado.get("categoria")
                if categoria_nome:
                    if Category.objects.filter(name__iexact=categoria_nome).exists():
                        transacoes = transacoes.filter(category__name__iexact=categoria_nome)
                    elif MainCategory.objects.filter(name__iexact=categoria_nome).exists():
                        subcategorias = Category.objects.filter(main_category__name__iexact=categoria_nome)
                        transacoes = transacoes.filter(category__in=subcategorias)

                tipo_lancamento = interpretado.get("tipo_lancamento")
                if tipo_lancamento:
                    transacoes = transacoes.filter(tipo=tipo_lancamento)

                mensagem = formatar_resposta_consulta(transacoes, data_inicial, data_final, categoria_nome,
                                                      tipo_lancamento)

                # Se usuário solicitar gráfico
                if interpretado.get("grafico", False):
                    imagem_base64 = gerar_grafico_base64(transacoes)
                    if imagem_base64:
                        resposta_grafico = {
                            "apiKey": config("APIKEY_WG"),
                            "phone_number": data.get("phone_number"),
                            "contact_phone_number": phone_number,
                            "contact_name": nome_contato or phone_number,
                            "chat_type": "user",
                            "message_type": "image",
                            "message_image": imagem_base64,
                        }
                        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                        requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta_grafico, headers=headers)

            else:
                return Response({"error": "Tipo de ação não reconhecido."}, status=400)

            resposta = {
                "apiKey": config("APIKEY_WG"),
                "phone_number": data.get("phone_number"),
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
