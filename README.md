# Gestão da Construtora

Sistema web para a administração de uma construtora, organizado em 6 áreas:

| Área | O que tem |
|---|---|
| **1. Empresa** | Dados da empresa (razão social, CNPJ, endereço etc.) e **documentos da empresa**, como contrato social, cartão CNPJ, alvarás, certidões e certificado digital, com data de validade. Também fica aqui o cadastro de funcionários, cada um com a **ficha e os documentos** dele (RG/CPF, comprovante de residência, CTPS, ASO, NRs...). |
| **2. Obras** | Cada obra tem **documentos** (projetos, condomínio, alvarás, ART, matrícula, fotos...), entradas e saídas, gastos por categoria, vendas das unidades, notas, contratos, equipe e pagamentos. Também mostra o orçamento usado e o saldo da obra. |
| **3. Clientes / Vendas** | Cadastro de clientes com documentos pessoais. Registra a venda de apartamentos, casas e lotes (unidade, valor, condições, status, corretor), com os recebimentos e o saldo **a receber**, além dos documentos da venda (contrato, comprovantes, financiamento). |
| **4. Financeiro** | Painel de entradas e saídas com filtros por data, obra, tipo, categoria, fornecedor e cliente. Aceita comprovante anexado e exporta para Excel (CSV). Inclui notas fiscais, pagamentos de funcionários e relatórios (fluxo de caixa mês a mês, por obra e por categoria). |
| **5. Fornecedores** | Lista com os dados de cada fornecedor (CNPJ, ramo, contato, PIX, banco), os **documentos** dele (contratos, orçamentos, certidões), o total pago, os pagamentos e as notas fiscais. Também tem os **pedidos** feitos a cada fornecedor, com status (pendente, aprovado, em trânsito, entregue...), previsão de entrega, aviso de atraso, histórico de acompanhamento, documentos e pagamentos do pedido. |
| **6. Jurídico** | Documentos jurídicos (processos, notificações, procurações, acordos...) com situação, partes ou número do processo, prazo e obra relacionada, além dos contratos com vencimento. |

Outros recursos:

- **Painel**: mostra o resultado do mês, o saldo, o valor a receber de vendas, as obras, os **documentos vencendo ou vencidos** e os contratos a vencer.
- **Arquivos nos lançamentos automáticos**: os lançamentos gerados por nota fiscal ou por pagamento de funcionário mostram o arquivo de origem para abrir.
- **Busca de documentos**: o campo no topo procura em todos os documentos de todas as áreas.
- **Envio de vários arquivos de uma vez**: é possível anexar vários arquivos de uma só vez em qualquer área.
- **Usuários**: cada pessoa tem o seu próprio login.
- **Segurança**:
  - verificação em duas etapas com app autenticador;
  - bloqueio depois de várias tentativas de senha erradas;
  - senha forte obrigatória;
  - saída automática depois de 60 minutos sem uso;
  - registro de atividades (quem fez o quê e quando);
  - backup completo com um clique;
  - proteções do navegador (CSP, cookies seguros, HSTS).
- **Atualização**: quando o sistema é atualizado, o banco de dados é ajustado sozinho e os dados antigos continuam lá.

## Como rodar

Pré-requisito: [Python 3.10 ou mais novo](https://www.python.org/downloads/). No Windows, marque a opção
"Add Python to PATH" durante a instalação.

- **Windows**: dê dois cliques em `iniciar.bat`.
- **Mac**: clique com o botão direito em `iniciar.command` e escolha **Abrir**. Na primeira vez, o Mac
  pergunta se quer mesmo abrir; confirme. Nas próximas vezes, basta dar dois cliques.
- **Linux**: execute `./iniciar.sh`.

Na primeira vez, o script instala o que for preciso (demora 1 ou 2 minutos). Depois, abra **http://localhost:8000** no navegador.
No primeiro acesso, o sistema pede para criar o usuário administrador.

Para desligar o sistema, feche a janela do Terminal (ou do Prompt de Comando).

### Manualmente

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip ...
.venv/bin/python run.py
```

## Onde ficam os dados (faça backup!)

Tudo fica na pasta `instance/`:

- `instance/construtora.db`: banco de dados (obras, lançamentos, cadastros).
- `instance/uploads/`: arquivos anexados (notas, contratos e comprovantes).
- `instance/secret_key`: chave de segurança das sessões.

**Para fazer backup, basta copiar a pasta `instance/` inteira** para um pen drive ou para a nuvem
(Google Drive, OneDrive etc.), de preferência toda semana.

## Acessar de outros computadores ou do celular

- **Na mesma rede (escritório)**: inicie com `HOST=0.0.0.0` (Windows: `set HOST=0.0.0.0` antes de rodar) e
  acesse `http://IP-DO-COMPUTADOR:8000` pelos outros aparelhos.
- **Pela internet**: siga o guia **[PUBLICAR.md](PUBLICAR.md)**. Ele usa um instalador automático para um servidor Ubuntu, com HTTPS, firewall e backup diário. Se preferir instalar à mão, use HTTPS.
  Variáveis de ambiente aceitas:
  - `SECRET_KEY`: chave secreta das sessões.
  - `DATABASE_URL`: por exemplo, um PostgreSQL. O padrão é SQLite em `instance/`.
  - `UPLOAD_FOLDER`: pasta dos anexos.
  - `HOST` e `PORT`: endereço e porta do servidor.

  Use um disco persistente para o banco e para os anexos.

## Detalhes técnicos

- Python com Flask, SQLAlchemy (SQLite) e Flask-Login. Telas em Bootstrap 5, servido localmente, então funciona sem internet.
- Os valores são guardados em centavos, para não haver erros de arredondamento. Os campos aceitam `1.234,56`.
- Senhas são guardadas com hash, e há proteção contra CSRF em todos os formulários.
- Anexos aceitos: PDF, XML, imagens, documentos do Office e LibreOffice, CSV, TXT e ZIP, com até 25 MB por envio.
- Testes: `.venv/bin/pip install pytest && .venv/bin/python -m pytest`.
