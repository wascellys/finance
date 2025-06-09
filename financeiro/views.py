from .utils import interpretar_mensagem, formatar_resposta_registro, formatar_resposta_consulta, \
    salvar_arquivo_temporario, transcrever_audio, interpretar_imagem_gpt4_vision
from datetime import datetime
from django.utils.timezone import make_aware, now
from rest_framework.views import APIView
from rest_framework.response import Response
import unicodedata
import requests
from decouple import config

from .models import User, Category, MainCategory, Transaction

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


        print(base64_str)

        if len(base64_str) < 5:
            return Response({"error": "Nenhuma mensagem válida foi recebida."}, status=200)

        try:
            if not phone_number:
                return Response({"error": "Campo 'phone_number' obrigatório."}, status=200)

            if message_type == "audio" and base64_str:
                caminho = salvar_arquivo_temporario(base64_str, extensao)
                description = transcrever_audio(caminho)
                interpretado = interpretar_mensagem(description)
            elif message_type == "image" and base64_str:
                description = interpretar_imagem_gpt4_vision(base64_str)
                interpretado = description
            elif message_type == "text":
                interpretado = interpretar_mensagem(base64_str)
            else:
                description = base64_str.strip()

            if not description:
                return Response({"error": "Mensagem válida não recebida."}, status=200)

            print("INTERPRETADO:", interpretado)

            if isinstance(interpretado, str):
                resposta = self._resposta_simples(phone_number, nome_contato, interpretado)
                return Response({"message": interpretado}, status=200)

            tipo = interpretado.get("tipo")

            if tipo == "irrelevante":
                mensagem = (
                    "Não conseguimos processar sua mensagem 🥺.\n"
                    "Tente usar frases como:\n"
                    "*Gastei 50 reais em mercado* ou *Consultar despesas de abril*."
                )
                self._enviar_resposta(phone_number, nome_contato, mensagem)
                return Response({"error": "Mensagem irrelevante."}, status=200)

            if tipo == "agradecimento":
                self._enviar_resposta(phone_number, nome_contato, interpretado.get("mensagem"))
                return Response({"message": interpretado.get("mensagem")}, status=200)

            user, _ = User.objects.get_or_create(phone_number=phone_number)
            if nome_contato:
                user.name = nome_contato
                user.save()

            if tipo == "registro":
                categoria = self._obter_categoria(interpretado.get("categoria"))
                if not categoria:
                    categoria = Category.objects.get(name__icontains="Sem categoria")

                transacao = Transaction.objects.create(
                    user=user,
                    category=categoria,
                    amount=interpretado["valor"],
                    description=interpretado["descricao"],
                    tipo=interpretado.get("tipo_lancamento", "despesa"),
                    created_at=now(),
                    date=make_aware(datetime.strptime(interpretado["data"], "%Y-%m-%d"))
                )
                mensagem = formatar_resposta_registro(transacao)

            elif tipo == "consulta":
                data_inicial = datetime.strptime(interpretado["data_inicial"], "%Y-%m-%d")
                data_final = datetime.strptime(interpretado["data_final"], "%Y-%m-%d")
                transacoes = Transaction.objects.filter(user=user, date__date__range=(data_inicial, data_final))

                categoria_nome = interpretado.get("categoria")
                categoria_principal = interpretado.get("categoria_principal")

                if categoria_principal:
                    main_cat = MainCategory.objects.filter(name__icontains=categoria_principal).first()
                    if main_cat:
                        transacoes = transacoes.filter(category__main_category=main_cat)
                elif categoria_nome:
                    if normalizar(categoria_nome) not in ["todas", "tudo", "geral"]:
                        categoria = Category.objects.filter(name__icontains=categoria_nome).first()
                        if categoria:
                            transacoes = transacoes.filter(category=categoria)

                tipo_lancamento = interpretado.get("tipo_lancamento")
                if tipo_lancamento:
                    transacoes = transacoes.filter(tipo=tipo_lancamento)

                mensagem = formatar_resposta_consulta(transacoes, data_inicial, data_final,
                                                      categoria_nome or categoria_principal, tipo_lancamento)


            elif tipo == "remover":
                codigo = interpretado.get("codigo")
                filtro = {"user": user}
                if codigo:
                    filtro["code__iexact"] = codigo
                transacao = Transaction.objects.filter(**filtro).order_by("-created_at").first()
                if transacao:
                    transacao.delete()
                    mensagem = "🗑️ Transação removida com sucesso."
                else:
                    mensagem = "❌ Nenhuma transação encontrada para remover."

            elif tipo == "atualizar":
                campo = interpretado.get("campo")
                valor = interpretado.get("valor")
                codigo = interpretado.get("codigo")
                transacao = Transaction.objects.filter(user=user)
                if codigo:
                    transacao = transacao.filter(code__iexact=codigo)
                transacao = transacao.order_by("-created_at").first()

                if not transacao:
                    mensagem = "❌ Nenhuma transação encontrada para atualizar."
                elif campo == "categoria":
                    nova_categoria = Category.objects.filter(name__iexact=valor).first()
                    if nova_categoria:
                        transacao.category = nova_categoria
                        transacao.save()
                        mensagem = f"✅ Categoria atualizada para *{valor}*."
                    else:
                        mensagem = f"❌ Categoria '{valor}' não encontrada."
                else:
                    mensagem = "❌ Campo de atualização não suportado."

            else:
                mensagem = "❌ Tipo de ação não reconhecido."

            self._enviar_resposta(phone_number, nome_contato, mensagem)
            return Response({"message": mensagem}, status=200)

        except Exception as e:
            erro = "Não conseguimos processar sua mensagem 🥺. Por favor, tente novamente."
            self._enviar_resposta(phone_number, nome_contato, erro)
            return Response({"error": str(e)}, status=200)

    def _resposta_simples(self, phone, nome, body):
        resposta = {
            "apiKey": config("APIKEY_WG"),
            "phone_number": config("BOT_NUMBER"),
            "contact_phone_number": phone,
            "contact_name": nome or phone,
            "chat_type": "user",
            "message_type": "text",
            "message_body": body,
        }
        requests.post(f"{config('URL_WHATSGW')}/Send", data=resposta, headers=HEADERS)
        return resposta

    def _enviar_resposta(self, phone, nome, mensagem):
        return self._resposta_simples(phone, nome, mensagem)

    def _resposta_imagem(self, phone, nome, imagem):
        return {
            "apiKey": config("APIKEY_WG"),
            "phone_number": config("BOT_NUMBER"),
            "contact_phone_number": phone,
            "contact_name": nome or phone,
            "chat_type": "user",
            "message_type": "image",
            "message_body": imagem,
            "message_body_filename": "grafico.png",
            "message_body_mimetype": "image/png",
        }

    def _obter_categoria(self, nome_categoria):
        nome_normalizado = normalizar(nome_categoria or "")
        for cat in Category.objects.all():
            if normalizar(cat.name) == nome_normalizado:
                return cat
        return None
