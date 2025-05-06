from .utils import interpretar_mensagem, formatar_resposta_registro, formatar_resposta_consulta, gerar_grafico_base64, \
    salvar_arquivo_temporario, transcrever_audio, interpretar_imagem_gpt4_vision
import json
from datetime import datetime
from django.utils.timezone import make_aware, now
from rest_framework.views import APIView
from rest_framework.response import Response
import unicodedata
import requests
from decouple import config

from .models import User, Category, MainCategory, Transaction


def normalizar(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII').lower()


class InterpretarTransacaoView(APIView):
    def post(self, request):

        data = request.POST

        message_type = data.get("message_type", "text").strip().lower()
        base64_str = data.get('message_body', "")
        extensao = data.get("message_body_extension", ".txt").strip()
        phone_number = data.get("contact_phone_number", "").strip()
        nome_contato = data.get("contact_name", "").strip()

        print(base64_str)

        if len(base64_str) < 5:
            return Response({"error": "Nenhuma mensagem válida foi recebida. Quantidade de caracteres insuficiente."},
                            status=400)
        try:
            if not phone_number:
                return Response({"error": "Campo 'phone_number' obrigatório."}, status=400)

            # Processamento baseado no tipo de mensagem
            if message_type == "audio" and base64_str:
                caminho = salvar_arquivo_temporario(base64_str, extensao)
                description = transcrever_audio(caminho)
            elif message_type == "image" and base64_str:
                description = interpretar_imagem_gpt4_vision(base64_str)
            else:
                # Para texto ou fallback
                description = base64_str.strip()

            if not description:
                return Response({"error": "Nenhuma mensagem válida foi recebida."}, status=400)
            interpretado_raw = interpretar_mensagem(description)
            interpretado = json.loads(interpretado_raw)

            print("INTERPRETADO:", interpretado)

            if interpretado["tipo"] == "irrelevante":
                resposta = {
                    "apiKey": config("APIKEY_WG"),
                    "phone_number": config("BOT_NUMBER"),
                    "contact_phone_number": phone_number,
                    "contact_name": nome_contato or phone_number,
                    "chat_type": "user",
                    "message_type": "text",
                    "message_body": "Não conseguimos processar sua mensagem 🥺. Por favor, tente novamente.",
                }

                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded'
                }

                requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=headers)

                return Response({"error": "Mensagem irrelevante."}, status=400)

            user, created = User.objects.get_or_create(phone_number=phone_number)
            if created and nome_contato:
                user.name = nome_contato
                user.save()

            if interpretado["tipo"] == "registro":
                categoria_nome_normalizada = normalizar(interpretado["categoria"])
                categoria = None

                for cat in Category.objects.all():
                    if normalizar(cat.name) == categoria_nome_normalizada:
                        categoria = cat
                        break

                if not categoria:
                    print("CATEGORIA não encontrada:", interpretado["categoria"])
                    categoria = Category.objects.create(name=interpretado["categoria"])

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
                    categoria_nome_normalizada = normalizar(categoria_nome)
                    encontrada = False

                    for cat in Category.objects.all():
                        if normalizar(cat.name) == categoria_nome_normalizada:
                            transacoes = transacoes.filter(category=cat)
                            encontrada = True
                            break

                    if not encontrada:
                        for mc in MainCategory.objects.all():
                            if normalizar(mc.name) == categoria_nome_normalizada:
                                subcategorias = Category.objects.filter(main_category=mc)
                                transacoes = transacoes.filter(category__in=subcategorias)
                                break

                tipo_lancamento = interpretado.get("tipo_lancamento")
                if tipo_lancamento:
                    transacoes = transacoes.filter(tipo=tipo_lancamento)

                mensagem = formatar_resposta_consulta(transacoes, data_inicial, data_final, categoria_nome,
                                                      tipo_lancamento)

                if interpretado.get("grafico", False):
                    imagem_base64 = gerar_grafico_base64(transacoes)
                    if imagem_base64:
                        resposta_grafico = {
                            "apiKey": config("APIKEY_WG"),
                            "phone_number": config("BOT_NUMBER"),
                            "contact_phone_number": phone_number,
                            "contact_name": nome_contato or phone_number,
                            "chat_type": "user",
                            "message_type": "image",
                            "message_body": imagem_base64,
                            "message_body_filename": "file.png",
                            "message_body_mimetype": "image/png",
                        }
                        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                        requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta_grafico, headers=headers)

                        return Response(data={"message": "Gráfico gerado com sucesso!"}, status=200)

            else:
                return Response({"error": "Tipo de ação não reconhecido."}, status=400)

            resposta = {
                "apiKey": config("APIKEY_WG"),
                "phone_number": config("BOT_NUMBER"),
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

            resposta = {
                "apiKey": config("APIKEY_WG"),
                "phone_number": config("BOT_NUMBER"),
                "contact_phone_number": phone_number,
                "contact_name": nome_contato or phone_number,
                "chat_type": "user",
                "message_type": "text",
                "message_body": "Não conseguimos processar sua mensagem 🥺. Por favor, tente novamente.",
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=headers)
            return Response({"error": f"Erro ao interpretar ou processar mensagem: {str(e)}"}, status=500)
