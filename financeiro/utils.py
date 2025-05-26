import json
import os
from django.utils import timezone
import time
import uuid
from datetime import datetime
import plotly.io as pio
import io
import base64
import pytz
from decouple import config
import openai
import plotly.graph_objects as go
from datetime import timedelta


from dashboard.models import TemporaryLink

openai.api_key = config('APIKEY')


def limpar_base64(data: str):
    # Remove espaços, quebras de linha e caracteres inválidos
    clean_str = data.replace(' ', '+').replace('\n', '')

    return clean_str


def salvar_arquivo_temporario(base64_str, extensao=".jpg"):
    os.makedirs("tmp", exist_ok=True)  # garante a pasta tmp
    caminho = f"tmp/{uuid.uuid4()}{extensao}"

    base64_str = limpar_base64(base64_str)

    try:
        with open(caminho, "wb") as f:
            f.write(base64.b64decode(base64_str))
    except base64.binascii.Error:
        raise ValueError("Base64 inválido")

    return caminho


def categorias_financeiras_prompt():
    return """
Use apenas as seguintes subcategorias (com acentuação e capitalização corretas):

Despesas:
- Aluguel, Condomínio, Manutenção residencial, Reforma, Móveis e decoração
- Energia, Água, Telefone, Internet, Gás, TV por assinatura
- Mercearia, Açougue, Hortifruti, Frios e laticínios, Padaria, Bebidas, Produtos de limpeza, Produtos de higiene, Alimentos industrializados, Congelados, Petiscos e snacks, Produtos infantis, Utensílios domésticos, Produtos para pets, Produtos de papelaria
- Refeições e lanches, Ifood, Restaurante, Cafeteria, Alimentos
- Cinema e teatro, Festas e eventos, Hobbies, Viagens, Passeios, Jogos
- Streamings, Aplicativos, Clube de vantagens, Jornais e revistas
- Roupas e acessórios, Compras diversas, Eletrônicos, Acessórios para casa, Acessórios para carro
- Higiene pessoal, Salão de beleza, Barbearia, Estética, Academia
- Financiamentos, Empréstimo, Parcelamentos, Cartão de crédito
- Escola/Faculdade, Material escolar, Cursos extracurriculares, Cursos online, Livros
- Mesada, Ajuda de custo, Creche, Roupas infantis, Atividades infantis
- Taxas bancárias, IPTU, IPVA, Anuidade de cartão, Multas
- Reserva de emergência, Aposentadoria, Objetivos, Criptomoedas, Ações
- Dízimo, Presentes, Doações, Caridade
- Medicamentos, Plano de saúde, Consultas particulares, Exames, Terapias
- Seguro de vida, Seguro automotivo, Seguro residencial, Seguro saúde
- Custos diversos, Despesas operacionais, Material de escritório, Ferramentas, Transporte a trabalho
- Combustível, Manutenção, Táxi/Transporte por aplicativo, Transporte público, Estacionamento, Pedágio
- Ração, Pet shop, Veterinário, Acessórios para pets, Banho e tosa
- Sem categoria

Receitas:
- Salário/Pró-labore, Freelas/Bônus / Comissão, 13º Salário/Hora extra, Participação nos lucros
- Rendimentos de investimentos (CDBs, Tesouro, Fundos, etc.), Dividendos de ações e FIIs, Aluguéis, Royalties, Juros recebidos
- Bens usados, Marketplace, Venda de milhas, Venda de objetos pessoais
- Cashback, Prêmios, Presentes, Herança, Restituição de imposto

📌 Apenas subcategorias são válidas. Se o usuário mencionar apenas a categoria principal, retorne "irrelevante". 
   Caso o usuário faça algum agradeicmento, retorne "agradecimento".
"""


def transcrever_audio(caminho):
    with open(caminho, "rb") as f:
        result = openai.Audio.transcribe("whisper-1", f)
        return result["text"]


def interpretar_imagem_gpt4_vision(image, retries=3):
    for attempt in range(retries):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": categorias_financeiras_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Tentativa {attempt + 1} falhou. Erro: {e}")
            time.sleep(2)
    return None


agradecimentos = ["obrigado", "obrigada", "valeu", "agradeço", "muito obrigado", "grato", "grata"]


def interpretar_mensagem(mensagem_usuario):
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    data_hoje = datetime.now(fuso_brasilia).date().isoformat()

    if any(palavra in mensagem_usuario.lower() for palavra in agradecimentos):
        data = {
            "tipo": "agradecimento",
            "mensagem": "De nada! Estou sempre aqui para ajudar. 😊"
        }

        return json.dumps(data)

    prompt_sistema = (
            f"Hoje é {data_hoje}. "
            "Você é um assistente financeiro que interpreta mensagens de usuários sobre *registro* ou *consulta* de transações financeiras. "
            "Sua resposta deve ser sempre e somente um JSON estruturado, com as seguintes possibilidades:\n\n"
            "1. Para *registro* de uma transação:\n"
            "{\n"
            '  "tipo": "registro",\n'
            '  "valor": 1200,\n'
            '  "categoria": "IPVA",\n'
            '  "descricao": "paguei o IPVA",\n'
            '  "data": "2025-04-04",\n'
            '  "tipo_lancamento": "despesa"\n'
            "}\n\n"
            "2. Para *consulta* de transações:\n"
            "{\n"
            '  "tipo": "consulta",\n'
            '  "data_inicial": "2025-04-01",\n'
            '  "data_final": "2025-04-30",\n'
            '  "categoria": "Plano de saúde",\n'
            '  "tipo_lancamento": "despesa",\n'
            '  "grafico": false\n'
            "}\n\n"
            "3. Se a mensagem for um agradecimento (ex: obrigado, valeu), retorne:\n"
            '{ "tipo": "agradecimento", "mensagem": "De nada! Estou sempre aqui para ajudar. 😊" }\n\n'
            "4. Se a mensagem não estiver relacionada a finanças, retorne:\n"
            '{ "tipo": "irrelevante" }\n\n'
            "📌 **Regras importantes:**\n"
            "- Sempre use datas no formato ISO: yyyy-mm-dd\n"
            "- Sempre use o nome exato da subcategoria com acentuação e capitalização corretas (ex: \"IPVA\", \"Plano de saúde\")\n"
            "- Retorne \"categoria\": \"Sem categoria\" apenas se o usuário mencionar isso literalmente\n"
            "- Se não houver categoria mencionada na consulta, omita esse campo ou use null\n"
            "- Se não periodo mensinado na consulta, considerar o periodo do primeiro dia do ano até o dia de hoje\n"
            "- Só deve ser gerado gráfico caso o usuário mencione que quer gráfico\n"
            "- Sempre inclua o campo \"tipo_lancamento\" quando for possível inferir\n\n"
            "📚 *Palavras associadas a despesas* (inferir tipo_lancamento = 'despesa'):\n"
            "- gastei, paguei, comprei, adquiri, investi, doei, transferi, saquei, apliquei, pagaram, quitar, desembolsei\n\n"
            "📚 *Palavras associadas a receitas* (inferir tipo_lancamento = 'receita'):\n"
            "- recebi, ganhei, entrou, caiu na conta, depósito, pagaram para mim, crédito, bônus, prêmio, herança, ou sinonimos\n\n"
            "📚 *Palavras associadas a consulta*:\n"
            "- quero ver, me mostre, consultar, quanto gastei, quanto recebi, listar, exibir, mostrar, extrato, relatório, saldo, meu saldo ou sinonimos\n\n"
            + categorias_financeiras_prompt()
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": mensagem_usuario}
        ]
    )

    return response['choices'][0]['message']['content']


def formatar_resposta_registro(transacao):
    tipo = transacao.tipo
    valor = f"R$ {transacao.amount:.2f}".replace('.', ',')
    categoria = transacao.category.name
    descricao = transacao.description
    data = transacao.date.strftime("%d/%m/%Y")

    return (
        "✅ *Transação registrada!*\n\n"
        f"_Tipo:_ *{tipo.upper()}*\n"
        f"_Valor:_ *{valor}*\n"
        f"_Categoria:_ *{categoria.upper()}*\n"
        f"_Descrição:_ `{descricao.capitalize()}`\n"
        f"_Data:_ *{data}*\n\n"
        f"_Código:_ *#{transacao.code.upper()}*\n"
    )


def formatar_resposta_consulta(transacoes, data_inicial, data_final, categoria=None, tipo=None):
    if not transacoes:
        return "❌ *Nenhum Registro Encontrado Para Este Período*"

    inicio = data_inicial.strftime("%d/%m/%Y")
    fim = data_final.strftime("%d/%m/%Y")

    receitas = [t.amount for t in transacoes if t.tipo == 'receita']
    despesas = [t.amount for t in transacoes if t.tipo == 'despesa']

    total_receita = sum(receitas)
    total_despesa = sum(despesas)
    saldo = total_receita - total_despesa

    total_receita_str = f"R$ {total_receita:.2f}".replace('.', ',')
    total_despesa_str = f"R$ {total_despesa:.2f}".replace('.', ',')
    saldo_str = f"R$ {saldo:.2f}".replace('.', ',')

    header = (
        "📊 *Resumo de transações*\n"
        f"_Período:_ *{inicio}* até *{fim}*\n"
        f"_Categoria:_ *{categoria if categoria else 'TODAS'}*\n"
        f"_Receitas:_ *{total_receita_str}*\n"
        f"_Despesas:_ *{total_despesa_str}*\n"
        f"_Saldo:_ *{saldo_str}*\n\n"
        "*Transações:* \n"
    )

    linhas = []
    for i, t in enumerate(transacoes, 1):
        valor = f"R$ {t.amount:.2f}".replace('.', ',')
        desc = t.description
        data = t.created_at.strftime("%d/%m/%Y")
        tipo_str = "⬆️ Receita" if t.tipo == "receita" else "⬇️ Despesa"
        linhas.append(f"{i}. *{valor}* - `{desc}` _({data})_ {tipo_str}\n")

    # Geração de link temporário
    token_obj, created = TemporaryLink.objects.get_or_create(
        user=transacoes[0].user,
        defaults={
            'token': uuid.uuid4().hex,
            'expires_at': timezone.now() + timedelta(days=1)
        }
    )

    if not created and token_obj.expires_at < timezone.now():
        token_obj.token = uuid.uuid4().hex
        token_obj.expires_at = timezone.now() + timedelta(days=1)
        token_obj.save()

    url = f"{config('BASE_URL_SITE')}/dashboard/temp/{token_obj.token}"

    link = (
        f"\n🔗 Você também pode verificar seu extrato completo em:\n\n {url}"
    )

    return header + "\n" + "".join(linhas) + "\n" + link


def gerar_grafico_base64(transacoes):
    categorias = {}
    for t in transacoes:
        cat = t.category.name
        categorias[cat] = categorias.get(cat, 0) + float(t.amount)

    if not categorias:
        return None

    labels = list(categorias.keys())
    valores = list(categorias.values())

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=valores,
                marker=dict(color='indigo'),
                text=[f"R$ {v:.2f}".replace('.', ',') for v in valores],
                textposition='auto'
            )
        ]
    )

    fig.update_layout(
        title='Gastos por Categoria',
        xaxis_title='Categoria',
        yaxis_title='Valor (R$)',
        template='plotly_dark',
        height=500,
        margin=dict(l=30, r=30, t=50, b=50),
    )

    # Salvar como imagem base64
    buffer = io.BytesIO()
    pio.write_image(fig, buffer, format='png')  # Requer instalação do kaleido
    buffer.seek(0)
    imagem_base64 = base64.b64encode(buffer.read()).decode('utf-8')

    return imagem_base64
