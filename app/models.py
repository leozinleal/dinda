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


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self):
        return self.ativo


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
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra", back_populates="lancamentos")
    nota = db.relationship("NotaFiscal", back_populates="lancamento")
    pagamento = db.relationship("PagamentoFuncionario", back_populates="lancamento")

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
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    obra = db.relationship("Obra")
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
