# Gestão da Construtora

Sistema web para a administração de uma construtora. Ele reúne em um só lugar:

| Módulo | O que faz |
|---|---|
| **Painel** | Entradas, saídas e resultado do mês, saldo acumulado, situação de cada obra (quanto do orçamento já foi usado), contratos vencendo e últimos lançamentos. |
| **Obras** | Cadastro de cada obra (cliente, endereço, orçamento, datas e status). A página da obra mostra quanto foi recebido e gasto, os gastos por categoria, as notas, os contratos, a equipe e os pagamentos daquela obra. |
| **Entradas e Saídas** | Livro-caixa com todas as movimentações, ligadas a uma obra ou à empresa (despesas gerais). Tem filtros por obra, tipo, categoria, período e busca, permite anexar comprovante e exportar para Excel (CSV). |
| **Notas Fiscais** | Guarda as notas recebidas (compras) e emitidas (vendas/serviços) com o arquivo PDF, XML ou foto. Opcionalmente já lança o valor no financeiro. |
| **Contratos** | Guarda os contratos com clientes, fornecedores, empreiteiros e funcionários, com o arquivo assinado, a vigência e o status. Mostra um alerta no painel quando o vencimento está a 30 dias ou menos. |
| **Funcionários** | Cadastro da equipe (cargo, tipo de contratação, salário ou diária, PIX, dados bancários e obra onde trabalha), com o histórico de pagamentos de cada um. |
| **Pagamentos** | Registra salários, vales, diárias, férias, 13º etc., com o comprovante. **Cada pagamento vira uma saída no financeiro automaticamente** e soma no custo da obra. |
| **Relatórios** | Fluxo de caixa mês a mês do ano e totais por obra e por categoria. Pode ser impresso ou salvo em PDF pelo navegador. |
| **Empresa / Usuários** | Dados da construtora e cadastro de outros usuários (por exemplo, o contador ou um sócio), cada um com o seu login. |

## Como rodar

Pré-requisito: [Python 3.10 ou mais novo](https://www.python.org/downloads/). No Windows, marque a opção
"Add Python to PATH" durante a instalação.

- **Windows**: dê dois cliques em `iniciar.bat`.
- **Linux/macOS**: execute `./iniciar.sh`.

Na primeira vez, o script instala o que for preciso. Depois, abra **http://localhost:5000** no navegador.
No primeiro acesso, o sistema pede para criar o usuário administrador.

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
  acesse `http://IP-DO-COMPUTADOR:5000` pelos outros aparelhos.
- **Pela internet**: publique em um servidor (VPS, Render, Railway, PythonAnywhere etc.) atrás de HTTPS.
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
