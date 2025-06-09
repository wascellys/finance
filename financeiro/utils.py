import json
import os
from django.utils import timezone
import time
import uuid
from datetime import datetime, timedelta
import plotly.io as pio
import io
import base64
import pytz
from decouple import config
import openai
import plotly.graph_objects as go

from dashboard.models import TemporaryLink

openai.api_key = config('APIKEY')


def limpar_base64(data: str):
    clean_str = data.replace(' ', '+').replace('\n', '')
    return clean_str


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


def categorias_financeiras_prompt():
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    data_hoje = datetime.now(fuso_brasilia).date().isoformat()

    return f"""
Hoje é {data_hoje}.
Você é um assistente financeiro amigável que conversa com o usuário sobre suas finanças.

📌 Regras obrigatórias:
- Sempre que possível, retorne um JSON estruturado de forma correta.
- Se o usuário não mencionar uma data explícita para o registro, assuma que a transação é para hoje.
- A data deve sempre estar no formato ISO: yyyy-mm-dd.
- A descrição deve ser preenchida com base na mensagem, mesmo que resumida.
- A categoria deve usar exatamente a subcategoria informada no catálogo, com acentuação e capitalização correta.
- Se o usuário mencionar uma categoria principal sem uma subcategoria específica, preencha \"categoria_principal\" e deixe \"categoria\" como null.
- Se o usuário mencionar uma subcategoria (ex: Ifood, IPVA), a \"categoria_principal\" deve ser null.
- Nunca peça ao usuário mais informações. Faça o melhor possível com o que foi fornecido.
- Para mensagens genéricas ou cumprimentos, responda com uma mensagem textual simpática — não JSON.


Você pode responder com mensagens livres para cumprimentos e dúvidas.

Quando o usuário quiser registrar, consultar, atualizar ou remover uma transação, responda obrigatoriamente com um JSON estruturado. Isso vale para mensagens de texto, audio e imagens.

Exemplos:

Registro:
{{
  "tipo": "registro",
  "valor": 80.5,
  "categoria": "IPVA",
  "descricao": "Paguei o IPVA",
  "data": "2025-04-04",
  "tipo_lancamento": "despesa"
}}

Consulta:
{{
  "tipo": "consulta",
  "data_inicial": "2025-04-01",
  "data_final": "2025-04-30",
  "categoria": "Plano de saúde",
  "categoria_principal": null,
  "tipo_lancamento": "despesa",
  "grafico": false
}}

Atualizar:
{{
  "tipo": "atualizar",
  "campo": "categoria",
  "valor": "Supermercado",
  "codigo": "ABC123"  # opcional
}}

Remover:
{{
  "tipo": "remover",
  "codigo": "ABC123"  # opcional
}}

Se a mensagem for apenas uma saudação ou dúvida, responda com uma mensagem textual simpática.
Use apenas as seguintes subcategorias com suas respectivas categorias principais (mantenha acentuação e capitalização corretas):
Se o usuário não especificar data, considere que a transação seja para hoje.
Se na consulta ele não especificar o periodo, considere o primeiro dia do ano atual ate o dia de hoje.
Despesas:

Categoria principal: HABITAÇÃO
- Aluguel, Condomínio, Manutenção residencial, Reforma, Móveis e decoração

Categoria principal: CONTAS RESIDENCIAIS
- Energia, Água, Telefone, Internet, Gás, TV por assinatura

Categoria principal: SUPERMERCADO
- Mercearia, Açougue, Hortifruti, Frios e laticínios, Padaria, Bebidas, Produtos de limpeza, Produtos de higiene, Alimentos industrializados, Congelados, Petiscos e snacks, Produtos infantis, Utensílios domésticos, Produtos para pets, Produtos de papelaria, Compras no supermercado 

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
"""


def transcrever_audio(caminho):
    with open(caminho, "rb") as f:
        result = openai.Audio.transcribe("whisper-1", f)
        return result["text"]


def interpretar_imagem_gpt4_vision(image, retries=3):

    image = limpar_base64(image)
    for attempt in range(retries):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": categorias_financeiras_prompt()},
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
            content = response["choices"][0]["message"]["content"]

            if content.startswith("```"):
                content = content.strip("`")
                if content.lower().startswith("json"):
                    content = content[4:].strip()

            try:
                return json.loads(content)
            except Exception:
                return content
        except Exception as e:
            print(f"Tentativa {attempt + 1} falhou. Erro: {e}")
            time.sleep(2)
    return None


def interpretar_mensagem(mensagem_usuario):
    prompt_sistema = categorias_financeiras_prompt()

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        temperature=0.3,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": mensagem_usuario}
        ]
    )

    content = response['choices'][0]['message']['content'].strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    try:
        return json.loads(content)
    except Exception:
        return content


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

    link = (
        f"\n🔗 Você também pode verificar seu extrato completo em:\n\n {url}"
    )

    return header + "\n" + "".join(linhas) + "\n" + link
