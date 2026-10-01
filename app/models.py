from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class ValorMixin:
    """Valores monetários são guardados em centavos (inteiro) para evitar erros de arredondamento."""

    valor_centavos = db.Column(db.Integer, nullable=False, default=0)

    @property
    def valor(self) -> Decimal:
        return Decimal(self.valor_centavos or 0) / 100

    @valor.setter
    def valor(self, v: Decimal):
        self.valor_centavos = int((Decimal(v) * 100).quantize(Decimal("1")))


class AnexoMixin:
    arquivo = db.Column(db.String(255))  # nome salvo em disco
    arquivo_nome = db.Column(db.String(255))  # nome original enviado

    @property
    def anexo(self):
        """(arquivo_em_disco, nome_original) do anexo a exibir, ou None."""
        return (self.arquivo, self.arquivo_nome) if self.arquivo else None


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    totp_segredo = db.Column(db.String(64))  # verificação em duas etapas (app autenticador)
    totp_ativo = db.Column(db.Boolean, default=False)
    totp_ultimo_passo = db.Column(db.Integer)  # impede reutilizar o mesmo código

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self):
        return self.ativo


class TentativaLogin(db.Model):
    """Usada para bloquear tentativas repetidas de adivinhar a senha."""

    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), index=True)
    email = db.Column(db.String(120), index=True)
    sucesso = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Atividade(db.Model):
    """Registro de quem fez o quê e quando (entradas, alterações, exclusões, backups...)."""

    id = db.Column(db.Integer, primary_key=True)
    criado_em = db.Column(db.DateTime, default=datetime.now, index=True)
    usuario = db.Column(db.String(120), default="")
    ip = db.Column(db.String(64), default="")
    acao = db.Column(db.String(120), default="")
    detalhe = db.Column(db.String(500), default="")


class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(200), default="")
    nome_fantasia = db.Column(db.String(200), default="")
    cnpj = db.Column(db.String(30), default="")
    inscricao_estadual = db.Column(db.String(30), default="")
    endereco = db.Column(db.String(255), default="")
    telefone = db.Column(db.String(40), default="")
    email = db.Column(db.String(120), default="")
    responsavel = db.Column(db.String(120), default="")

    @classmethod
    def get(cls):
        empresa = db.session.get(cls, 1)
        if empresa is None:
            empresa = cls(id=1)
            db.session.add(empresa)
            db.session.commit()
        return empresa


OBRA_STATUS = ["Planejada", "Em andamento", "Pausada", "Concluída", "Cancelada"]


class Obra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    cliente = db.Column(db.String(200), default="")
    endereco = db.Column(db.String(255), default="")
    orcamento_centavos = db.Column(db.Integer, default=0)
    data_inicio = db.Column(db.Date)
    previsao_termino = db.Column(db.Date)
    status = db.Column(db.String(30), default="Em andamento")
    observacoes = db.Column(db.Text, default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    lancamentos = db.relationship("Lancamento", back_populates="obra")

    @property
    def orcamento(self) -> Decimal:
        return Decimal(self.orcamento_centavos or 0) / 100

    @orcamento.setter
    def orcamento(self, v):
        self.orcamento_centavos = int((Decimal(v) * 100).quantize(Decimal("1")))


CATEGORIAS_ENTRADA = [
    "Venda de unidade / Parcela de cliente",
    "Medição / Recebimento de cliente",
    "Adiantamento de cliente",
    "Aporte de sócio",
    "Empréstimo",
    "Venda de material / equipamento",
    "Outras entradas",
]
CATEGORIAS_SAIDA = [
    "Material de construção",
    "Mão de obra / Folha de pagamento",
    "Empreiteiro / Terceirizado",
    "Aluguel de equipamentos",
    "Combustível / Transporte",
    "Impostos e taxas",
    "Projetos e licenças",
    "Despesas administrativas",
    "Alimentação",
    "Outras saídas",
]
FORMAS_PAGAMENTO = ["PIX", "Transferência", "Boleto", "Dinheiro", "Cartão", "Cheque", "Outro"]


class Lancamento(ValorMixin, AnexoMixin, db.Model):
    """Entrada ou saída de dinheiro. Se obra_id for vazio, é um lançamento geral da empresa."""

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False)  # "entrada" | "saida"
    descricao = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(80), default="")
    data = db.Column(db.Date, nullable=False, default=date.today)
    forma_pagamento = db.Column(db.String(40), default="")
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    nota_id = db.Column(db.Integer, db.ForeignKey("nota_fiscal.id", ondelete="CASCADE"))
    pagamento_id = db.Column(db.Integer, db.ForeignKey("pagamento_funcionario.id", ondelete="CASCADE"))
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedor.id"))
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))
    venda_id = db.Column(db.Integer, db.ForeignKey("venda.id"))
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra", back_populates="lancamentos")
    fornecedor = db.relationship("Fornecedor")
    cliente = db.relationship("Cliente")
    venda = db.relationship("Venda", back_populates="recebimentos")
    pedido = db.relationship("Pedido", back_populates="pagamentos")
    nota = db.relationship("NotaFiscal", back_populates="lancamento")
    pagamento = db.relationship("PagamentoFuncionario", back_populates="lancamento")

    @property
    def anexo(self):
        # Lançamentos automáticos mostram o arquivo da nota fiscal / comprovante do pagamento de origem.
        for obj in (self, self.nota, self.pagamento):
            if obj is not None and obj.arquivo:
                return obj.arquivo, obj.arquivo_nome
        return None

    @property
    def origem(self):
        if self.nota_id:
            return "Nota fiscal"
        if self.pagamento_id:
            return "Pagamento de funcionário"
        return "Manual"


class NotaFiscal(ValorMixin, AnexoMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # "entrada" = nota recebida de fornecedor (despesa); "saida" = nota emitida pela empresa (receita)
    tipo = db.Column(db.String(10), nullable=False, default="entrada")
    numero = db.Column(db.String(60), nullable=False)
    serie = db.Column(db.String(20), default="")
    parceiro = db.Column(db.String(200), default="")  # fornecedor ou cliente
    cpf_cnpj = db.Column(db.String(30), default="")
    data_emissao = db.Column(db.Date, nullable=False, default=date.today)
    descricao = db.Column(db.String(255), default="")
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedor.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra")
    fornecedor = db.relationship("Fornecedor")
    lancamento = db.relationship(
        "Lancamento", back_populates="nota", uselist=False, cascade="all, delete-orphan"
    )


CONTRATO_TIPOS = ["Cliente", "Fornecedor", "Empreiteiro / Prestador", "Funcionário", "Locação", "Outro"]
CONTRATO_STATUS = ["Vigente", "Encerrado", "Cancelado"]


class Contrato(ValorMixin, AnexoMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(40), default="Cliente")
    parte = db.Column(db.String(200), default="")  # outra parte do contrato
    cpf_cnpj = db.Column(db.String(30), default="")
    data_inicio = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    status = db.Column(db.String(20), default="Vigente")
    descricao = db.Column(db.Text, default="")
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra")


class Funcionario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    cpf = db.Column(db.String(20), default="")
    cargo = db.Column(db.String(80), default="")
    telefone = db.Column(db.String(40), default="")
    tipo_contratacao = db.Column(db.String(40), default="CLT")
    salario_centavos = db.Column(db.Integer, default=0)
    chave_pix = db.Column(db.String(120), default="")
    dados_bancarios = db.Column(db.String(255), default="")
    data_admissao = db.Column(db.Date)
    data_demissao = db.Column(db.Date)
    ativo = db.Column(db.Boolean, default=True)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))  # obra onde está alocado
    observacoes = db.Column(db.Text, default="")

    obra = db.relationship("Obra")
    pagamentos = db.relationship(
        "PagamentoFuncionario", back_populates="funcionario", cascade="all, delete-orphan"
    )

    @property
    def salario(self) -> Decimal:
        return Decimal(self.salario_centavos or 0) / 100

    @salario.setter
    def salario(self, v):
        self.salario_centavos = int((Decimal(v) * 100).quantize(Decimal("1")))


TIPOS_CONTRATACAO = ["CLT", "Diarista", "Autônomo / MEI", "Empreiteiro", "Estagiário", "Outro"]
TIPOS_PAGAMENTO = [
    "Salário",
    "Adiantamento / Vale",
    "Diárias",
    "Hora extra",
    "Empreitada",
    "Férias",
    "13º salário",
    "Rescisão",
    "Outro",
]


class PagamentoFuncionario(ValorMixin, AnexoMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey("funcionario.id"), nullable=False)
    tipo = db.Column(db.String(40), default="Salário")
    competencia = db.Column(db.String(7), default="")  # AAAA-MM
    data_pagamento = db.Column(db.Date, nullable=False, default=date.today)
    forma_pagamento = db.Column(db.String(40), default="PIX")
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    observacao = db.Column(db.String(255), default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    funcionario = db.relationship("Funcionario", back_populates="pagamentos")
    obra = db.relationship("Obra")
    lancamento = db.relationship(
        "Lancamento", back_populates="pagamento", uselist=False, cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------- Clientes e vendas

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    tipo_pessoa = db.Column(db.String(2), default="PF")  # PF | PJ
    cpf_cnpj = db.Column(db.String(30), default="")
    rg = db.Column(db.String(30), default="")
    data_nascimento = db.Column(db.Date)
    estado_civil = db.Column(db.String(40), default="")
    profissao = db.Column(db.String(80), default="")
    telefone = db.Column(db.String(40), default="")
    email = db.Column(db.String(120), default="")
    endereco = db.Column(db.String(255), default="")
    observacoes = db.Column(db.Text, default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    vendas = db.relationship("Venda", back_populates="cliente")


VENDA_STATUS = ["Reserva / Proposta", "Contrato assinado", "Em pagamento", "Quitada", "Escriturada", "Distratada"]


class Venda(ValorMixin, db.Model):
    """Venda de unidade (apartamento, casa, lote, sala...) de uma obra para um cliente."""

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"), nullable=False)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    unidade = db.Column(db.String(120), default="")  # ex.: Apto 101 - Bloco A
    data_venda = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(40), default="Contrato assinado")
    condicoes = db.Column(db.Text, default="")  # entrada, parcelas, financiamento...
    corretor = db.Column(db.String(120), default="")
    observacoes = db.Column(db.Text, default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    cliente = db.relationship("Cliente", back_populates="vendas")
    obra = db.relationship("Obra")
    recebimentos = db.relationship("Lancamento", back_populates="venda")

    @property
    def recebido(self) -> Decimal:
        return Decimal(sum(l.valor_centavos for l in self.recebimentos if l.tipo == "entrada")) / 100

    @property
    def a_receber(self) -> Decimal:
        return self.valor - self.recebido


# ---------------------------------------------------------------- Fornecedores

CATEGORIAS_FORNECEDOR = [
    "Material de construção", "Concreto / Aço", "Elétrica", "Hidráulica", "Acabamento",
    "Madeira / Esquadrias", "Locação de equipamentos", "Mão de obra / Empreiteiro",
    "Projetos / Engenharia", "Transporte / Frete", "Serviços", "Outros",
]


class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)  # razão social ou nome
    nome_fantasia = db.Column(db.String(200), default="")
    cpf_cnpj = db.Column(db.String(30), default="")
    categoria = db.Column(db.String(80), default="")
    contato = db.Column(db.String(120), default="")  # pessoa de contato
    telefone = db.Column(db.String(40), default="")
    email = db.Column(db.String(120), default="")
    endereco = db.Column(db.String(255), default="")
    chave_pix = db.Column(db.String(120), default="")
    dados_bancarios = db.Column(db.String(255), default="")
    ativo = db.Column(db.Boolean, default=True)
    observacoes = db.Column(db.Text, default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def nome_exibicao(self):
        return self.nome_fantasia or self.nome


# ---------------------------------------------------------------- Documentos (anexos em qualquer área)

CATEGORIAS_DOCUMENTO = {
    "empresa": [
        "Contrato social / alterações", "Cartão CNPJ", "Inscrição estadual / municipal", "Alvará",
        "Certidões negativas", "Certificado digital", "Documentos dos sócios", "Registro CREA / CAU",
        "Seguros", "Contabilidade", "Outros",
    ],
    "obra": [
        "Projetos e plantas", "Alvará / licenças", "Matrícula / escritura do terreno", "Condomínio",
        "Incorporação / memorial", "ART / RRT", "Habite-se", "Atas e reuniões", "Fotos", "Outros",
    ],
    "cliente": [
        "RG / CPF / CNH", "Comprovante de residência", "Comprovante de renda", "Certidão de casamento / nascimento",
        "Ficha cadastral", "Outros",
    ],
    "venda": [
        "Proposta / reserva", "Contrato de compra e venda", "Comprovantes de pagamento", "Financiamento",
        "Escritura / registro", "Distrato", "Outros",
    ],
    "fornecedor": [
        "Cartão CNPJ", "Contrato", "Orçamento / proposta", "Certidões", "Dados bancários", "Outros",
    ],
    "funcionario": [
        "RG / CPF / CNH", "Comprovante de residência", "Carteira de trabalho (CTPS)", "Contrato de trabalho",
        "ASO / exames", "Certificados / NRs", "EPI (fichas)", "Atestados", "Férias / rescisão", "Outros",
    ],
    "pedido": [
        "Pedido / ordem de compra", "Orçamento", "Nota fiscal", "Boleto", "Comprovante de pagamento",
        "Canhoto / comprovante de entrega", "Fotos", "Outros",
    ],
    "juridico": [
        "Processo judicial", "Notificação", "Procuração", "Parecer", "Acordo", "Contrato",
        "Certidão", "Trabalhista", "Outros",
    ],
}
ENTIDADES_DOCUMENTO = {
    "empresa": "Empresa", "obra": "Obra", "cliente": "Cliente", "venda": "Venda",
    "fornecedor": "Fornecedor", "funcionario": "Funcionário", "pedido": "Pedido",
    "juridico": "Jurídico",
}


class Documento(AnexoMixin, db.Model):
    """Arquivo anexado a qualquer área do sistema (entidade + entidade_id)."""

    id = db.Column(db.Integer, primary_key=True)
    entidade = db.Column(db.String(20), nullable=False, index=True)
    entidade_id = db.Column(db.Integer, index=True)  # vazio para empresa / jurídico geral
    titulo = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(80), default="")
    descricao = db.Column(db.Text, default="")
    data_documento = db.Column(db.Date)
    validade = db.Column(db.Date)
    # Jurídico: pode ser ligado a uma obra, cliente ou fornecedor
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    parte = db.Column(db.String(200), default="")  # parte envolvida / nº do processo
    status = db.Column(db.String(40), default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra")

# ---------------------------------------------------------------- Pedidos a fornecedores

PEDIDO_STATUS = [
    "Pendente", "Orçamento / cotação", "Aprovado", "Confirmado pelo fornecedor", "Em trânsito",
    "Entregue parcialmente", "Entregue", "Cancelado",
]
PEDIDO_STATUS_FINAIS = ("Entregue", "Cancelado")


class Pedido(ValorMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedor.id"), nullable=False)
    obra_id = db.Column(db.Integer, db.ForeignKey("obra.id"))
    numero = db.Column(db.String(60), default="")  # nº do pedido / ordem de compra
    descricao = db.Column(db.String(255), nullable=False)  # ex.: 200 sacos de cimento CP-II
    itens = db.Column(db.Text, default="")
    data_pedido = db.Column(db.Date, nullable=False, default=date.today)
    previsao_entrega = db.Column(db.Date)
    data_entrega = db.Column(db.Date)
    status = db.Column(db.String(40), default="Pendente")
    condicoes = db.Column(db.String(255), default="")  # forma / prazo de pagamento
    observacoes = db.Column(db.Text, default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    fornecedor = db.relationship("Fornecedor")
    obra = db.relationship("Obra")
    pagamentos = db.relationship("Lancamento", back_populates="pedido")
    historico = db.relationship(
        "PedidoHistorico", back_populates="pedido", cascade="all, delete-orphan",
        order_by="PedidoHistorico.criado_em.desc()",
    )

    @property
    def pago(self) -> Decimal:
        return Decimal(sum(l.valor_centavos for l in self.pagamentos if l.tipo == "saida")) / 100

    @property
    def atrasado(self):
        return (self.status not in PEDIDO_STATUS_FINAIS and self.previsao_entrega is not None
                and self.previsao_entrega < date.today())


class PedidoHistorico(db.Model):
    """Registro de cada mudança de status / anotação do pedido, para acompanhamento."""

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False)
    status = db.Column(db.String(40), default="")
    observacao = db.Column(db.Text, default="")
    usuario = db.Column(db.String(120), default="")
    criado_em = db.Column(db.DateTime, default=datetime.now)

    pedido = db.relationship("Pedido", back_populates="historico")


JURIDICO_STATUS = ["", "Em andamento", "Aguardando", "Concluído", "Arquivado"]


def atualizar_banco():
    """Cria tabelas novas e adiciona colunas que faltam em bancos criados por versões anteriores."""
    from sqlalchemy import inspect, text

    db.create_all()
    insp = inspect(db.engine)
    for tabela in db.metadata.sorted_tables:
        existentes = {c["name"] for c in insp.get_columns(tabela.name)}
        for coluna in tabela.columns:
            if coluna.name not in existentes:
                tipo = coluna.type.compile(dialect=db.engine.dialect)
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN "{coluna.name}" {tipo}'))
