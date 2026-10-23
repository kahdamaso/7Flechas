# Testar online (PythonAnywhere)

O sistema fica num endereço na internet, como `https://SEU_USUARIO.pythonanywhere.com`, e qualquer
celular, tablet ou computador acessa de onde estiver. Não é preciso instalar nada na casa.

O plano gratuito do PythonAnywhere basta para testar. Ele guarda o banco de dados entre
reinícios e já vem com HTTPS (cadeado).

## 1. Criar a conta

1. Acesse <https://www.pythonanywhere.com> e clique em **Pricing & signup → Create a Beginner account** (gratuita).
2. Escolha o **nome de usuário** com cuidado: ele vira o endereço do sistema.
   Por exemplo, o usuário `tuc7fj` dá o endereço `https://tuc7fj.pythonanywhere.com`.
3. Confirme o e-mail.

## 2. Criar o web app

1. No painel, abra a aba **Web** e clique em **Add a new web app**.
2. Clique em **Next**, escolha **Manual configuration** e escolha o **Python mais novo** da lista.
3. Clique em **Next**.

## 3. Instalar o sistema (copiar e colar)

1. Abra a aba **Consoles** e clique em **Bash**.
2. Cole os dois comandos abaixo e tecle Enter:

```bash
git clone -b claude/confident-sagan-zykmvc https://github.com/kahdamaso/7Flechas.git ~/tuc7fj
bash ~/tuc7fj/deploy/pythonanywhere.sh
```

O script baixa o sistema, instala os componentes e configura o web app. No fim, ele mostra os
passos que faltam:

1. Volte à aba **Web**.
2. Em **Virtualenv**, informe `/home/SEU_USUARIO/tuc7fj/.venv`.
   - O web app precisa estar na **mesma versão do Python** que o script mostrou. Se não estiver,
     apague o web app e crie de novo com essa versão.
3. Em **Security**, ligue **Force HTTPS**.
4. Clique no botão verde **Reload**.

## 4. Primeiro acesso

1. Abra `https://SEU_USUARIO.pythonanywhere.com`.
2. Defina a **senha da casa**. Use uma senha forte: o sistema fica na internet e guarda CPFs e telefones.
3. Informe seu nome como responsável do dia.

## 5. Importar a planilha

1. No Google Drive, baixe a planilha TUC7FJ como **.xlsx** (Arquivo → Fazer download → Microsoft Excel).
2. No PythonAnywhere, abra a aba **Files**.
3. Entre na pasta `tuc7fj/data/` e clique em **Upload a file**. Envie o arquivo com o nome `TUC7FJ.xlsx`.
4. No console Bash, rode:

```bash
cd ~/tuc7fj && .venv/bin/python -m flask --app run importar data/TUC7FJ.xlsx
```

O relatório aparece no console. Depois de importar, **apague o .xlsx** da pasta `data/`, porque os
dados já estão no sistema.

## 6. Cópias de segurança (recomendado)

1. Na aba **Tasks**, crie uma tarefa diária com o comando:

```bash
cd ~/tuc7fj && SQLITE_WAL=0 .venv/bin/python -m flask --app run backup
```

2. As cópias ficam em `tuc7fj/instance/backups/`, e são guardadas as 30 mais recentes.
3. De vez em quando, baixe uma cópia pela aba **Files**.

## Atualizar o sistema depois de ajustes

1. No console Bash, rode `bash ~/tuc7fj/deploy/pythonanywhere.sh` de novo.
2. Na aba **Web**, clique em **Reload**.

Os dados não são apagados.

## Cuidados

- **Plano gratuito:**
  - O web app pede uma confirmação a cada **3 meses**: o botão "Run until 3 months from today", na aba Web. Sem essa confirmação, o sistema sai do ar, mas os dados continuam guardados.
  - O plano tem um limite diário de processamento. Para testar, ele é suficiente.
- **Dados pessoais (LGPD):** o banco fica nos servidores do PythonAnywhere. Use uma senha da casa forte e troque-a se alguém sair da secretaria (menu do responsável → Senha da casa).
- **Esqueceu a senha?** No console Bash, rode:

```bash
cd ~/tuc7fj && .venv/bin/python -m flask --app run definir-senha
```
