from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import make_aware, now
from datetime import datetime
import unicodedata
import json
import requests

from decouple import config

from .models import User, Category, MainCategory, Transaction, ConversationContext
from .utils import (
    interpretar_mensagem,
    formatar_resposta_registro,
    formatar_resposta_consulta,
    gerar_grafico_base64,
    salvar_arquivo_temporario,
    transcrever_audio,
    interpretar_imagem_gpt4_vision
)


HEADERS = {
    'Content-Type': 'application/x-www-form-urlencoded'
}


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

        if len(base64_str) < 5:
            return Response({"error": "Mensagem vazia ou inválida."}, status=200)

        if not phone_number:
            return Response({"error": "Campo 'phone_number' obrigatório."}, status=200)

        try:
            # Determina o conteúdo da mensagem
            if message_type == "audio":
                caminho = salvar_arquivo_temporario(base64_str, extensao)
                description = transcrever_audio(caminho)
            elif message_type == "image":
                description = interpretar_imagem_gpt4_vision(base64_str)
            else:
                description = base64_str.strip()

            if not description:
                return Response({"error": "Não foi possível interpretar a mensagem."}, status=200)

            # Busca ou cria o usuário
            user, _ = User.objects.get_or_create(phone_number=phone_number)
            if nome_contato and not user.name:
                user.name = nome_contato
                user.save()

            # Busca ou cria o contexto
            contexto, _ = ConversationContext.objects.get_or_create(user=user)
            if contexto.contexto_expirado():
                contexto.limpar()

            # Chama o interpretador com o contexto
            interpretado_raw = interpretar_mensagem(description, contexto)
            interpretado = json.loads(interpretado_raw)

            # Mensagem irrelevante
            if interpretado["tipo"] == "irrelevante":
                mensagem = (
                    "Não conseguimos processar sua mensagem 🥺.\n\n"
                    "Para registrar um gasto, use frases como *gastei 50 reais em supermercado*.\n"
                    "Para consultar, diga algo como *quanto recebi em abril*.\n\n"
                    "Tente novamente! 😊"
                )
                resposta = responder_bot(phone_number, nome_contato, mensagem)
                requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=HEADERS)
                return Response({"error": "Mensagem irrelevante."}, status=200)

            # Agradecimento
            if interpretado["tipo"] == "agradecimento":
                resposta = responder_bot(phone_number, nome_contato, interpretado["mensagem"])
                requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=HEADERS)
                return Response({"message": interpretado["mensagem"]}, status=200)

            # Registro de transação
            if interpretado["tipo"] == "registro":
                categoria_nome = interpretado.get("categoria")
                categoria = Category.objects.filter(name__iexact=categoria_nome).first()

                if not categoria:
                    categoria = Category.objects.filter(name__icontains="Sem categoria").first()

                data_transacao = interpretado.get("data")
                data_formatada = make_aware(datetime.strptime(data_transacao, "%Y-%m-%d")) if data_transacao else None

                transacao = Transaction.objects.create(
                    user=user,
                    category=categoria,
                    amount=interpretado["valor"],
                    description=interpretado["descricao"],
                    tipo=interpretado["tipo_lancamento"],
                    date=data_formatada,
                    created_at=now()
                )

                # Atualiza contexto
                contexto.last_message = description
                contexto.last_intent = "registro"
                contexto.last_category = categoria.name if categoria else None
                contexto.last_date_range_start = data_formatada.date() if data_formatada else None
                contexto.last_date_range_end = data_formatada.date() if data_formatada else None
                contexto.save()

                mensagem = formatar_resposta_registro(transacao)

            # Consulta de transações
            elif interpretado["tipo"] == "consulta":
                # Datas (fallback via contexto se necessário)
                data_inicial = datetime.strptime(
                    interpretado.get("data_inicial") or contexto.last_date_range_start.isoformat(),
                    "%Y-%m-%d"
                )
                data_final = datetime.strptime(
                    interpretado.get("data_final") or contexto.last_date_range_end.isoformat(),
                    "%Y-%m-%d"
                )

                transacoes = Transaction.objects.filter(
                    user=user,
                    date__date__gte=data_inicial,
                    date__date__lte=data_final
                )

                categoria_principal = interpretado.get("categoria_principal")
                categoria_nome = interpretado.get("categoria")

                if categoria_principal:
                    main = MainCategory.objects.filter(name__iexact=categoria_principal).first()
                    if main:
                        transacoes = transacoes.filter(category__main_category=main)
                elif categoria_nome:
                    categoria = Category.objects.filter(name__iexact=categoria_nome).first()
                    if categoria:
                        transacoes = transacoes.filter(category=categoria)

                if interpretado.get("tipo_lancamento"):
                    transacoes = transacoes.filter(tipo=interpretado["tipo_lancamento"])

                mensagem = formatar_resposta_consulta(
                    transacoes,
                    data_inicial,
                    data_final,
                    categoria_principal or categoria_nome,
                    interpretado.get("tipo_lancamento")
                )

                # Atualiza contexto
                contexto.last_message = description
                contexto.last_intent = "consulta"
                contexto.last_category = categoria_nome or categoria_principal
                contexto.last_date_range_start = data_inicial.date()
                contexto.last_date_range_end = data_final.date()
                contexto.save()

                # Gráfico (se solicitado)
                if interpretado.get("grafico", False):
                    imagem_base64 = gerar_grafico_base64(transacoes)
                    if imagem_base64:
                        resposta_img = {
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
                        requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta_img, headers=HEADERS)
                        return Response({"message": "Gráfico enviado com sucesso"}, status=200)

            else:
                return Response({"error": "Tipo de ação não reconhecido."}, status=200)

            # Envia mensagem final
            resposta = responder_bot(phone_number, nome_contato, mensagem)
            requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=HEADERS)
            return Response({"message": mensagem}, status=200)

        except Exception as e:
            print("Erro:", str(e))
            mensagem = "Não conseguimos processar sua mensagem 🥺. Tente novamente."
            resposta = responder_bot(phone_number, nome_contato, mensagem)
            requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=HEADERS)
            return Response({"error": str(e)}, status=500)


def responder_bot(phone_number, nome_contato, mensagem):
    return {
        "apiKey": config("APIKEY_WG"),
        "phone_number": config("BOT_NUMBER"),
        "contact_phone_number": phone_number,
        "contact_name": nome_contato or phone_number,
        "chat_type": "user",
        "message_type": "text",
        "message_body": mensagem,
    }
