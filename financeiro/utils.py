import json
import os
import time
import uuid
import io
import base64
import pytz
import openai
import plotly.io as pio
import plotly.graph_objects as go

from datetime import datetime, timedelta
from django.utils import timezone
from decouple import config

from dashboard.models import TemporaryLink
from financeiro.models import ConversationContext

openai.api_key = config('APIKEY')


def limpar_base64(data: str):
    return data.replace(' ', '+').replace('\n', '')


def salvar_arquivo_temporario(base64_str, extensao=".jpg"):
    os.makedirs("tmp", exist_ok=True)
    caminho = f"tmp/{uuid.uuid4()}{extensao}"
    base64_str = limpar_base64(base64_str)

    try:
        with open(caminho, "wb") as f:
            f.write(base64.b64decode(base64_str))
    except base64.binascii.Error:
        raise ValueError("Base64 inválido")

    return caminho


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
                    {"role": "system", "content": categorias_financeiras_prompt()},
                    {
                        "role": "user",
                        "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}]
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


def interpretar_mensagem(mensagem_usuario, contexto=None):
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    data_hoje = datetime.now(fuso_brasilia).date().isoformat()

    if any(palavra in mensagem_usuario.lower() for palavra in agradecimentos):
        return json.dumps({
            "tipo": "agradecimento",
            "mensagem": "De nada! Estou sempre aqui para ajudar. 😊"
        })

    # Contexto anterior injetado
    contexto_texto = ""
    if contexto and contexto.last_intent:
        contexto_texto = (
            f"O usuário está em uma conversa contínua. Ele anteriormente fez uma ação do tipo '{contexto.last_intent}'.\n"
            f"A categoria anterior foi '{contexto.last_category or 'todas'}'.\n"
        )
        if contexto.last_date_range_start and contexto.last_date_range_end:
            contexto_texto += (
                f"O intervalo de datas usado anteriormente foi de {contexto.last_date_range_start} até {contexto.last_date_range_end}.\n"
            )

    prompt_sistema = (
            f"Hoje é {data_hoje}. "
            "Você é um assistente financeiro que interpreta mensagens de usuários sobre *registro* ou *consulta* de transações financeiras. "
            "Sua resposta deve ser sempre e somente um JSON estruturado, com as seguintes possibilidades:\n\n"
            "1. Para *registro* de uma transação:\n"
            "{\n"
            '  "tipo": "registro",\n'
            '  "valor": 1200,\n'
            '  "categoria": "IPVA",\n'
            '  "descricao": "Paguei o IPVA",\n'
            '  "data": "2025-04-04",\n'
            '  "tipo_lancamento": "despesa"\n'
            "}\n\n"
            "2. Para *consulta* de transações:\n"
            "{\n"
            '  "tipo": "consulta",\n'
            '  "data_inicial": "2025-04-01",\n'
            '  "data_final": "2025-04-30",\n'
            '  "categoria": "Plano de saúde",\n'
            '  "categoria_principal": null,\n'
            '  "tipo_lancamento": "despesa",\n'
            '  "grafico": false\n'
            "}\n\n"
            "3. Se a mensagem for um agradecimento (ex: obrigado, valeu), retorne:\n"
            '{ "tipo": "agradecimento", "mensagem": "De nada! Estou sempre aqui para ajudar. 😊" }\n\n'
            "4. Se a mensagem não estiver relacionada a finanças, retorne:\n"
            '{ "tipo": "irrelevante" }\n\n'
            "📌 **Regras importantes:**\n"
            "- Todos os campos devem ser passados, por mais que uns tenha  valores nulos para tipo \"consulta\"\n"
            "- Deve sempre passar uma descrição para a transação de registro\n"
            "- Sempre use datas no formato ISO: yyyy-mm-dd\n"
            "- Sempre use o nome exato da subcategoria com acentuação e capitalização corretas (ex: \"IPVA\", \"Plano de saúde\")\n"
            "- Retorne \"categoria\": \"Sem categoria\" apenas se o usuário mencionar isso literalmente\n"
            "- Se não houver categoria mencionada na consulta, omita esse campo ou use null\n"
            "- Se não houver período mencionado na consulta, considerar o período do primeiro dia do ano até hoje\n"
            "- Só deve ser gerado gráfico caso o usuário mencione que quer gráfico\n"
            "- Sempre inclua o campo \"tipo_lancamento\" quando for possível inferir\n\n"
            "✅ Se o usuário mencionar uma *subcategoria específica* (ex: Ifood, IPVA):\n"
            "- Preencha \"categoria\" com a subcategoria mencionada\n"
            "- Defina \"categoria_principal\" como null, obrigatoriamente\n"
            "- A subcategoria sempre tem prioridade sobre qualquer categoria principal\n\n"
            "❌ Se o usuário mencionar apenas uma *categoria principal* (ex: EDUCAÇÃO, TRANSPORTE):\n"
            "- Defina \"categoria_principal\" com o nome da categoria principal corretamente capitalizado\n"
            "- Não preencha o campo \"categoria\"\n"
            "- Se não for possível identificar uma subcategoria, mas for claramente uma categoria principal, continue com \"categoria_principal\"\n"
            "- Caso a mensagem for vaga e contiver apenas uma categoria ampla, considere retornar \"tipo\": \"irrelevante\"\n\n"
            "📚 *Palavras associadas a despesas* (inferir tipo_lancamento = 'despesa'):\n"
            "- gastei, paguei, comprei, adquiri, investi, doei, transferi, saquei, apliquei, pagaram, quitar, desembolsei\n\n"
            "📚 *Palavras associadas a receitas* (inferir tipo_lancamento = 'receita'):\n"
            "- recebi, ganhei, entrou, caiu na conta, depósito, pagaram para mim, crédito, bônus, prêmio, herança, ou sinônimos\n\n"
            "📚 *Palavras associadas a consulta*:\n"
            "- quero ver, me mostre, consultar, quanto gastei, quanto recebi, listar, exibir, mostrar, extrato, relatório, saldo, meu saldo ou sinônimos\n\n"
            + categorias_financeiras_prompt()
    )

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": mensagem_usuario}
        ]
    )

    content = response['choices'][0]['message']['content']
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        resultado = json.loads(cleaned)

        if resultado.get("categoria") and resultado.get("categoria_principal"):
            resultado["categoria_principal"] = None
        elif resultado.get("categoria_principal") and not resultado.get("categoria"):
            resultado["categoria"] = None

        return json.dumps(resultado)
    except Exception as e:
        print("Erro ao interpretar JSON:", content)
        raise e


def categorias_financeiras_prompt():
    return """
Use apenas as seguintes subcategorias com suas respectivas categorias principais (mantenha acentuação e capitalização corretas):

Despesas:

Categoria principal: HABITAÇÃO
- Aluguel, Condomínio, Manutenção residencial, Reforma, Móveis e decoração

Categoria principal: CONTAS RESIDENCIAIS
- Energia, Água, Telefone, Internet, Gás, TV por assinatura

Categoria principal: SUPERMERCADO
- Mercearia, Açougue, Hortifruti, Frios e laticínios, Padaria, Bebidas, Produtos de limpeza, Produtos de higiene, Alimentos industrializados, Congelados, Petiscos e snacks, Produtos infantis, Utensílios domésticos, Produtos para pets, Produtos de papelaria

Categoria principal: ALIMENTAÇÃO
- Refeições e lanches, Ifood, Restaurante, Cafeteria, Alimentos

Categoria principal: LAZER
- Cinema e teatro, Festas e eventos, Hobbies, Viagens, Passeios, Jogos

Categoria principal: ASSINATURAS E SERVIÇOS
- Streamings, Aplicativos, Clube de vantagens, Jornais e revistas

Categoria principal: COMPRAS
- Roupas e acessórios, Compras diversas, Eletrônicos, Acessórios para casa, Acessórios para carro

Categoria principal: CUIDADOS PESSOAIS
- Higiene pessoal, Salão de beleza, Barbearia, Estética, Academia

Categoria principal: DÍVIDAS E EMPRÉSTIMOS
- Financiamentos, Empréstimo, Parcelamentos, Cartão de crédito

Categoria principal: EDUCAÇÃO
- Escola/Faculdade, Material escolar, Cursos extracurriculares, Cursos online, Livros

Categoria principal: FAMÍLIA E FILHOS
- Mesada, Ajuda de custo, Creche, Roupas infantis, Atividades infantis

Categoria principal: IMPOSTOS E TAXAS
- Taxas bancárias, IPTU, IPVA, Anuidade de cartão, Multas

Categoria principal: INVESTIMENTOS
- Reserva de emergência, Aposentadoria, Objetivos, Criptomoedas, Ações

Categoria principal: PRESENTES E DOAÇÕES
- Dízimo, Presentes, Doações, Caridade

Categoria principal: SAÚDE
- Medicamentos, Plano de saúde, Consultas particulares, Exames, Terapias

Categoria principal: SEGUROS
- Seguro de vida, Seguro automotivo, Seguro residencial, Seguro saúde

Categoria principal: DESPESAS DE TRABALHO
- Custos diversos, Despesas operacionais, Material de escritório, Ferramentas, Transporte a trabalho

Categoria principal: TRANSPORTE
- Combustível, Manutenção, Táxi/Transporte por aplicativo, Transporte público, Estacionamento, Pedágio

Categoria principal: PETS
- Ração, Pet shop, Veterinário, Acessórios para pets, Banho e tosa

Categoria principal: OUTROS
- Sem categoria

Receitas:

Categoria principal: RENDAS ATIVAS
- Salário/Pró-labore, Freelas/Bônus / Comissão, 13º Salário/Hora extra, Participação nos lucros

Categoria principal: RENDAS PASSIVAS
- Rendimentos de investimentos (CDBs, Tesouro, Fundos, etc.), Dividendos de ações e FIIs, Aluguéis, Royalties, Juros recebidos

Categoria principal: VENDAS EVENTUAIS
- Bens usados, Marketplace, Venda de milhas, Venda de objetos pessoais

Categoria principal: OUTROS
- Cashback, Prêmios, Presentes, Herança, Restituição de imposto

📌 Regras importantes:
- Sempre preencha o campo "categoria" com a subcategoria mencionada pelo usuário.
- Preencha o campo "categoria_principal" apenas se o usuário mencionar diretamente uma categoria principal, sem indicar uma subcategoria específica.
- Se o usuário mencionar uma subcategoria (ex: Ifood, IPVA), a "categoria_principal" deve ser null.
- A subcategoria sempre tem prioridade sobre a principal.
- A subcategoria só deve ser preenchido com subcategorias.
- A categoria principal sempre deve ser preenchida com categorias principais.
- Se o usuário mencionar apenas uma categoria principal (ex: EDUCAÇÃO), a subcategoria deve ser null .
- Se o usuário fizer um agradecimento, retorne "tipo": "agradecimento".
"""


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
    link = f"\n🔗 Você também pode verificar seu extrato completo em:\n\n {url}"

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
        data=[go.Bar(
            x=labels,
            y=valores,
            marker=dict(color='indigo'),
            text=[f"R$ {v:.2f}".replace('.', ',') for v in valores],
            textposition='auto'
        )]
    )

    fig.update_layout(
        title='Gastos por Categoria',
        xaxis_title='Categoria',
        yaxis_title='Valor (R$)',
        template='plotly_dark',
        height=500,
        margin=dict(l=30, r=30, t=50, b=50),
    )

    buffer = io.BytesIO()
    pio.write_image(fig, buffer, format='png')
    buffer.seek(0)
    imagem_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    return imagem_base64
