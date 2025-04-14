from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64
import pytz
from decouple import config
import openai

openai.api_key = config('APIKEY')


def interpretar_mensagem(mensagem_usuario):
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    data_hoje = datetime.now(fuso_brasilia).date().isoformat()

    categorias_financeiras = """
    Use apenas as seguintes categorias e subcategorias:

    - habitacao > aluguel, condominio
    - contas_residenciais > energia, agua, telefone, internet
    - supermercado
    - alimentacao > refeicoes e lanches
    - lazer > cinema e teatro, festas e eventos, hobbies
    - assinaturas_e_servicos > streamings, aplicativos
    - compras > roupas e acessorios, compras diversas, eletronicos
    - cuidados_pessoais > higiene pessoal, salao de beleza, barbearia
    - dividas_e_emprestimos > financiamentos, emprestimo
    - educacao > escola/faculdade, material escolar, cursos extracurriculares
    - familia_e_filhos > mesada, ajuda de custo
    - impostos_e_taxas > taxas bancarias, iptu, ipva, anuidade de cartao
    - investimentos > reserva de emergencia, aposentadoria, objetivos
    - presentes_e_doacoes > dizimo, presentes, doacoes
    - saude > medicamentos, plano de saude, consultas particulares
    - seguros > seguro de vida, seguro automotivo, seguro residencial
    - despesas_de_trabalho > custos diversos, despesas operacionais, material de escritorio
    - transporte > combustivel, manutencao, taxi/transporte por aplicativo, transporte publico, estacionamento

    Sempre retorne a subcategoria como o valor da chave "categoria".
    Se o usuario mencionar uma categoria geral (ex: transporte, saude), use o nome da categoria principal.
    """

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    f"Hoje é {data_hoje}. "
                    "Você é um assistente financeiro. Sua função é interpretar mensagens de um usuário sobre registros ou consultas financeiras. "
                    "Sempre responda em JSON com as seguintes possibilidades:\n\n"

                    "1. Quando for um *registro* de gasto ou receita, responda com:\n"
                    "{\"tipo\": \"registro\", \"valor\": 1200, \"categoria\": \"salario\", \"descricao\": \"recebi meu salário\", \"data\": \"2025-04-04\", \"tipo_lancamento\": \"receita\"}\n\n"

                    "2. Quando for uma *consulta*, responda com:\n"
                    "{\"tipo\": \"consulta\", \"data_inicial\": \"2025-04-01\", \"data_final\": \"2025-04-05\", \"categoria\": \"alimentacao\", \"tipo_lancamento\": \"despesa\" (opcional)}\n\n"

                    "3. Se a mensagem não for sobre finanças, retorne:\n"
                    "{\"tipo\": \"irrelevante\"}\n\n"

                    "*Regras importantes:*\n"
                    "- Se o usuário usar palavras como *gastos*, *despesas*, *gastei*, associe a \"tipo_lancamento\": \"despesa\"\n"
                    "- Se o usuário usar palavras como *recebi*, *entrada*, *ganhei*, associe a \"tipo_lancamento\": \"receita\"\n"
                    "- Sempre retorne datas no formato yyyy-mm-dd\n"
                    "- Sempre use letras minúsculas nas categorias\n"
                    "- Sempre retorne a subcategoria como valor da chave \"categoria\"\n"
                    "- Use \"tipo_lancamento\" mesmo nas consultas, se for possível inferir pelo contexto\n"
                    f"- A data de hoje deve ser considerada como sendo {data_hoje}\n\n"
                    f"{categorias_financeiras}"
                )
            },
            {"role": "user", "content": mensagem_usuario}
        ]
    )

    return response['choices'][0]['message']['content']


def formatar_resposta_registro(transacao):
    tipo = transacao.tipo  # receita ou despesa
    valor = f"R$ {transacao.amount:.2f}".replace('.', ',')
    categoria = transacao.category.name
    descricao = transacao.description
    data = transacao.created_at.strftime("%d/%m/%Y")

    return (
        "✅ *Transação registrada!*\n\n"
        f"_Código:_ *#{transacao.code}*\n"
        f"_Tipo:_ *{tipo.upper()}*\n"
        f"_Valor:_ *{valor}*\n"
        f"_Categoria:_ *{categoria.upper()}*\n"
        f"_Descrição:_ `{descricao.capitalize()}`\n"
        f"_Data:_ *{data}*"
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
        f"_Categoria:_ *{categoria if categoria else 'todas'}*\n"
        f"_Tipo:_ *{tipo if tipo else 'todas'}*\n"
        f"_Total:_ *{total_str}*\n\n"
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

    fig, ax = plt.subplots()
    ax.bar(labels, valores)
    ax.set_title('Gastos por Categoria')
    ax.set_ylabel('Valor (R$)')
    plt.xticks(rotation=45)
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)

    imagem_base64 = base64.b64encode(buffer.read()).decode('utf-8')

    plt.close()

    return imagem_base64
