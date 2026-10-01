# Como publicar o sistema na internet (passo a passo)

Este guia coloca o sistema num endereço como **https://sistema.suaconstrutora.com.br**, com cadeado (HTTPS),
backup diário e todas as proteções ligadas. É feito **uma vez só**. Tempo estimado: 1 a 2 horas,
incluindo a espera do domínio.

Você vai precisar de:
- um computador (o Mac serve) com o aplicativo **Terminal**;
- um cartão para pagar o domínio e o servidor;
- o celular de quem vai usar o sistema, para a verificação em duas etapas.

---

## Etapa 1 – Registrar um domínio (o "nome" do site)

1. Acesse **https://registro.br** e crie uma conta (pode ser com o CNPJ da construtora).
2. Pesquise e registre um domínio, por exemplo `suaconstrutora.com.br`. Se a construtora já tem site,
   use o domínio que já existe: não precisa registrar outro.
3. O sistema vai ficar num subdomínio, por exemplo `sistema.suaconstrutora.com.br`. Ele é configurado na Etapa 3.

> Se a construtora já tem domínio registrado em outro lugar (GoDaddy, Hostinger etc.), a Etapa 3 é
> feita no painel desse lugar.

## Etapa 2 – Contratar o servidor (VPS)

Contrate uma **VPS** (servidor virtual) com:

| Item | Escolha |
|---|---|
| Sistema operacional | **Ubuntu 24.04** (ou 22.04) |
| Local / região | **Brasil (São Paulo)**, que é melhor para a LGPD e mais rápido |
| Tamanho | 1 vCPU, **2 GB de RAM** e **pelo menos 40 GB de disco** (os documentos ocupam espaço) |
| Backup do provedor | Se houver a opção de "backup/snapshot automático", **ative** (é uma segunda cópia de segurança) |

Alguns provedores com servidores no Brasil: Hostinger, Locaweb, Magalu Cloud, AWS (região São Paulo).
Compare os preços na hora de contratar.

Depois de criar a VPS, anote:
- o **endereço IP** do servidor (algo como `203.0.113.45`);
- a **senha do usuário root**, definida na criação. Use uma senha forte e guarde num lugar seguro.

## Etapa 3 – Apontar o endereço para o servidor (DNS)

No painel onde o domínio está (registro.br → seu domínio → **DNS** → **Editar zona**), crie um registro:

| Tipo | Nome | Valor |
|---|---|---|
| **A** | `sistema` | o IP do servidor (da Etapa 2) |

Salve. A mudança pode levar de alguns minutos até algumas horas para valer.
Para conferir no Terminal do Mac:

```bash
ping -c 1 sistema.suaconstrutora.com.br
```

Quando a resposta mostrar o IP do servidor, pode seguir.

## Etapa 4 – Enviar o sistema para o servidor

1. No GitHub, baixe a versão mais nova: **Code → Download ZIP**. O arquivo vai para a pasta Downloads.
2. Abra o **Terminal** no Mac e envie o arquivo (troque `203.0.113.45` pelo IP do seu servidor):

```bash
scp ~/Downloads/dinda-*.zip root@203.0.113.45:/root/
```

Na primeira vez, o Terminal pergunta se confia no servidor: digite `yes` e Enter. Depois, digite a
senha do root. Ela não aparece enquanto você digita, isso é normal.

## Etapa 5 – Instalar (um comando só)

Ainda no Terminal do Mac, entre no servidor:

```bash
ssh root@203.0.113.45
```

Já dentro do servidor, rode os três comandos abaixo, trocando o endereço pelo seu:

```bash
apt-get update && apt-get install -y unzip
unzip -o dinda-*.zip && cd dinda-*/
bash deploy/instalar.sh sistema.suaconstrutora.com.br
```

A instalação leva de 5 a 10 minutos. No final aparece:

```
 Endereço:  https://sistema.suaconstrutora.com.br
 Código de instalação (pedido no primeiro acesso):  A1B2C3D4
```

**Anote o código de instalação.** Ele protege a tela de primeiro acesso, para que só você consiga criar o login.

O instalador já faz tudo isto:
- coloca o HTTPS (cadeado) e o renova sozinho;
- liga o firewall (só ficam abertas as portas do site e do acesso SSH);
- instala o fail2ban, que bloqueia quem tenta adivinhar a senha do servidor;
- liga as atualizações de segurança automáticas do Ubuntu;
- agenda o backup diário às 3h da manhã, guardando os últimos 30 dias;
- faz o sistema ligar sozinho se o servidor reiniciar.

## Etapa 6 – Primeiro acesso

Escolha **uma** das opções:

### Opção A: começar do zero
1. Abra **https://sistema.suaconstrutora.com.br** no navegador.
2. Preencha o **código de instalação**, o nome da construtora, o seu nome, o e-mail e uma senha forte.
   A senha precisa ter no mínimo 10 caracteres, com letras e números. Uma frase curta funciona bem, por exemplo
   `obra-azul-2026-sol`.

### Opção B: levar os dados que já estão no Mac
1. No sistema que roda no Mac (atualizado para esta versão), vá em **seu nome (canto superior direito) →
   Backup → Gerar e baixar backup**. Isso gera um `.zip` com todos os dados e documentos.
   Na versão antiga, que ainda não tem o botão: feche o sistema, clique com o botão direito na pasta
   **instance** → **Comprimir "instance"**. Use o `instance.zip` gerado.
2. No Terminal do Mac, envie o arquivo para o servidor. Se usou o `instance.zip`, troque o nome no comando:
   ```bash
   scp ~/Downloads/backup-*.zip root@203.0.113.45:/root/
   ```
3. No servidor (`ssh root@203.0.113.45`), restaure:
   ```bash
   bash /opt/construtora/app/deploy/restaurar.sh /root/backup-*.zip
   ```
4. Abra o endereço e entre com o **mesmo e-mail e senha** que usava no Mac. Em seguida, vá em
   **seu nome → Alterar senha** e troque por uma senha forte (mínimo de 10 caracteres).

## Etapa 7 – Ativar a verificação em duas etapas (muito recomendado)

1. No celular, instale **Google Authenticator** ou **Microsoft Authenticator**.
2. No sistema: **seu nome → Verificação em duas etapas**.
3. Leia o QR code com o app e digite o código de 6 dígitos para ativar.

A partir daí, o login pede a senha **e** o código do celular. Mesmo que alguém descubra a senha, não entra.

> Se trocar de celular: antes, entre no sistema, desative a verificação e ative de novo no celular novo.
> Se perder o celular, a verificação pode ser desligada direto no servidor. Veja "Problemas comuns" abaixo.

## Etapa 8 – Rotina de segurança (depois de publicado)

| Quando | O quê |
|---|---|
| **Toda semana** | **Seu nome → Backup → Gerar e baixar backup**. Guarde o `.zip` fora do servidor (HD externo, Google Drive). Essa cópia protege mesmo se o servidor inteiro for perdido. |
| Todo mês | Dê uma olhada em **seu nome → Registro de atividades** para conferir que só você entrou. |
| Automático | Backup diário no servidor (últimos 30 dias), atualizações de segurança do Ubuntu e renovação do HTTPS. |

Mais algumas regras simples:
- Use a senha do sistema **só nele** e não a compartilhe.
- A senha do root do servidor é diferente da senha do sistema. Guarde-a com segurança, porque só é necessária para instalar e atualizar.
- Por segurança, depois de 60 minutos sem uso o sistema sai sozinho.

---

## Como atualizar para uma versão nova

1. No servidor (`ssh root@IP`), apague a versão baixada anteriormente:
   ```bash
   rm -rf /root/dinda-*
   ```
2. Baixe o ZIP novo no GitHub e envie para o servidor, como na Etapa 4 (`scp ...`).
3. No servidor:
   ```bash
   cd /root && unzip -o dinda-*.zip && cd dinda-*/
   bash deploy/atualizar.sh
   ```
   O script faz um backup antes de atualizar, e os dados continuam lá.

## Problemas comuns

| Problema | Solução |
|---|---|
| O endereço não abre logo depois da instalação | Aguarde: o DNS (Etapa 3) e o certificado HTTPS podem demorar. Confira com `ping`. |
| Quero ver se o sistema está rodando | No servidor: `systemctl status construtora` |
| Ver os erros do sistema | No servidor: `journalctl -u construtora -n 50` |
| "Muitas tentativas erradas" no login | Aguarde 15 minutos. É a proteção contra quem tenta adivinhar a senha. |
| Perdi o celular da verificação em duas etapas | No servidor: `sqlite3 /var/lib/construtora/construtora.db "update usuario set totp_ativo=0, totp_segredo=null;"` (instale antes com `apt-get install -y sqlite3`) e depois ative de novo com o celular novo. |
| Restaurar um backup do servidor | Os backups ficam em `/var/backups/construtora/`. Rode `bash /opt/construtora/app/deploy/restaurar.sh /var/backups/construtora/backup-AAAA-MM-DD_HHMMSS.zip` |

## Onde ficam as coisas no servidor

| O quê | Onde |
|---|---|
| Programa | `/opt/construtora/app` |
| Banco de dados e documentos | `/var/lib/construtora` (acesso só do sistema) |
| Backups diários | `/var/backups/construtora` |
| Configuração e chaves secretas | `/etc/construtora.env` (não compartilhe) |
