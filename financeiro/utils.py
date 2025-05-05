import os
import re
import uuid
from datetime import datetime
import plotly.io as pio
import io
import base64
import pytz
from decouple import config
import openai
import plotly.graph_objects as go

openai.api_key = config('APIKEY')


def limpar_base64(data: str):
    # Remove espaços, quebras de linha e caracteres inválidos
    clean_str = data.replace(' ', '').replace('\n', '')

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
Use apenas as seguintes categorias e subcategorias (com acentuação e capitalização corretas):

➡️ Despesas:
- Habitação > Aluguel, Condomínio
- Contas residenciais > Energia, Água, Telefone, Internet
- Supermercado > mercearia, açougue, hortifruti, frios e laticínios, padaria, bebidas e produtos de limpeza
- Alimentação > Refeições e lanches, ifood
- Lazer > Cinema e teatro, Festas e eventos, Hobbies
- Assinaturas e serviços > Streamings, Aplicativos
- Compras > Roupas e acessórios, Compras diversas, Eletrônicos
- Cuidados pessoais > Higiene pessoal, Salão de beleza, Barbearia
- Dívidas e empréstimos > Financiamentos, Empréstimo
- Educação > Escola/Faculdade, Material escolar, Cursos extracurriculares
- Família e filhos > Mesada, Ajuda de custo
- Impostos e taxas > Taxas bancárias, IPTU, IPVA, Anuidade de cartão
- Investimentos > Reserva de emergência, Aposentadoria, Objetivos
- Presentes e doações > Dízimo, Presentes, Doações
- Saúde > Medicamentos, Plano de saúde, Consultas particulares
- Seguros > Seguro de vida, Seguro automotivo, Seguro residencial
- Despesas de trabalho > Custos diversos, Despesas operacionais, Material de escritório
- Transporte > Combustível, Manutenção, Táxi/Transporte por aplicativo, Transporte público, Estacionamento

➡️ Receitas:
- Rendas Ativas > Salário/Pró-labore, Freelas/Bônus / Comissão, 13º Salário/Hora extra
- Rendas Passivas > Rendimentos de investimentos (CDBs, Tesouro, Fundos, etc.), Dividendos de ações e FIIs, Aluguéis, Royalties
- Vendas Eventuais > Bens usados, Marketplace
- Outros > Cashback, Prêmios, Presentes

📌 Sempre retorne a subcategoria como o valor da chave \"categoria\".
Se o usuário mencionar apenas a categoria principal (ex: Transporte ou Rendas passivas), use exatamente esse nome.
Caso o usuário mencione que deseja um gráfico, adicione \"grafico\": true na resposta JSON.
"""


def transcrever_audio(caminho):
    with open(caminho, "rb") as f:
        result = openai.Audio.transcribe("whisper-1", f)
        return result["text"]


def interpretar_imagem_gpt4_vision(image):
    image = limpar_base64(image)

    prompt_sistema = (
            "Você é um assistente financeiro..."  # sua mensagem original
            + categorias_financeiras_prompt()
    )

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt_sistema},
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


def interpretar_mensagem(mensagem_usuario):
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    data_hoje = datetime.now(fuso_brasilia).date().isoformat()

    prompt_sistema = (
            f"Hoje é {data_hoje}. "
            "Você é um assistente financeiro. Sua função é interpretar mensagens de um usuário sobre registros ou consultas financeiras. "
            "Sempre responda em JSON com as seguintes possibilidades:\n\n"
            "1. Quando for um *registro* de gasto ou receita, responda com:\n"
            "{\"tipo\": \"registro\", \"valor\": 1200, \"categoria\": \"IPVA\", \"descricao\": \"paguei o IPVA\", \"data\": \"2025-04-04\", \"tipo_lancamento\": \"despesa\"}\n\n"
            "2. Quando for uma *consulta*, responda com:\n"
            "{\"tipo\": \"consulta\", \"data_inicial\": \"2025-04-01\", \"data_final\": \"2025-04-05\", \"categoria\": \"Plano de saúde\", \"tipo_lancamento\": \"despesa\", \"grafico\": true (caso solicitado)}\n\n"
            "3. Se a mensagem não for sobre finanças, retorne:\n"
            "{\"tipo\": \"irrelevante\"}\n\n"
            "*Regras importantes:*\n"
            "- Se o usuário usar palavras como *gastos*, *despesas*, *gastei*, associe a \"tipo_lancamento\": \"despesa\"\n"
            "- Se o usuário usar palavras como *recebi*, *entrada*, *ganhei*, associe a \"tipo_lancamento\": \"receita\"\n"
            "- Sempre retorne datas no formato yyyy-mm-dd\n"
            "- Sempre use o nome exato da categoria ou subcategoria, com acentuação e capitalização corretas\n"
            "- Sempre retorne a subcategoria como valor da chave \"categoria\"\n"
            "- Use \"tipo_lancamento\" mesmo nas consultas, se for possível inferir pelo contexto\n"
            f"- A data de hoje deve ser considerada como sendo {data_hoje}\n\n"
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
    data = transacao.created_at.strftime("%d/%m/%Y")

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
    total = sum([t.amount for t in transacoes])
    inicio = data_inicial.strftime("%d/%m/%Y")
    fim = data_final.strftime("%d/%m/%Y")
    total_str = f"R$ {total:.2f}".replace('.', ',')

    header = (
        "📊 *Resumo de transações*\n"
        f"_Período:_ *{inicio}* até *{fim}*\n"
        f"_Categoria:_ *{categoria if categoria else 'TODAS'}*\n"
        f"_Total:_ *{total_str.upper()}*\n\n"
        "*Transações:* \n"
    )

    linhas = []
    for i, t in enumerate(transacoes, 1):
        valor = f"R$ {t.amount:.2f}".replace('.', ',')
        desc = t.description
        data = t.created_at.strftime("%d/%m/%Y")
        linhas.append(f"{i}. *{valor}* - `{desc}` _({data})_ \n")

    return header + "\n" + "\n".join(linhas)


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
