# TUC7FJ — Sistema de gestão do terreiro

Aplicação web para a secretaria do terreiro, que substitui as planilhas. Funciona no celular, no
tablet e no computador, e vários aparelhos podem usá-la ao mesmo tempo.

**Stack:** Python 3.11+ · Flask · SQLAlchemy · SQLite · Bootstrap 5, servido localmente (funciona sem internet).

## Fases

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 | Pessoas e trajetória (Consulente → Colaborador → Auxiliar → Corrente), funções (Cambone, Ogã), parentescos, ficha espiritual, importação dos cadastros | **pronta** |
| 2 | Gira: chamada (SIM/NÃO), inscrição, atendimento puxado pelo cambone por entidade, retornos e prontuário | próxima |
| 3 | Relatórios: frequência dos médiuns, retornos, histórico | depois |
| Futuro | Inscrição online e perfis de acesso | — |

## Regras de negócio da Fase 1

- **A mesma pessoa evolui na casa:** Consulente → Colaborador → Auxiliar → Corrente. Toda mudança
  de categoria fica no histórico, com data, observação e quem registrou.
- Auxiliares e membros da Corrente podem ter **funções**: Cambone e Ogã.
- **Incorpora:** indica quem incorpora. Na Corrente, nem todos incorporam.
- **Ficha espiritual:** é a lista de entidades que o médium trabalha, cada uma pertencendo a uma
  linha. Enquanto a entidade não der o nome, ela aparece pelo médium, por exemplo "Exu de Jessica".
- **Linhas:** Caboclo, Preto Velho, Baiano, Boiadeiro, Povo d'Água, Cigano, Erê, Exu, Exu Mirim,
  Pomba Gira, Pomba Gira Mirim, Malandragem, Mestres, Princesas e Cangaço.
- **Parentesco:** parentes não conversam com as entidades uns dos outros. Quando há parentesco, o
  prontuário mostra um aviso. Na Fase 2 ele também vai bloquear o chamado.

## Acesso

- Há **uma senha única da casa**. Ela é definida na primeira vez que o sistema é aberto.
- Cada aparelho fica conectado por 30 dias.
- Todo dia, o sistema pergunta **quem é o responsável**. Esse nome fica gravado em tudo o que for lançado.
- Esqueceu a senha? Rode `flask --app run definir-senha` no computador onde o sistema está instalado.
- Depois de 5 senhas erradas seguidas, o acesso daquele aparelho fica bloqueado por 5 minutos.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Importar os cadastros da planilha

1. No Google Drive, abra a planilha TUC7FJ.
2. Vá em **Arquivo → Fazer download → Microsoft Excel (.xlsx)**.
3. Salve o arquivo na pasta `data/`. Essa pasta não vai para o git, porque guarda dados pessoais.

```bash
flask --app run importar data/TUC7FJ.xlsx
```

| Aba | O que vira |
|---|---|
| `PRESENÇA`, `RETORNO MEDIUNS`, `Página15` | Médiuns e sua categoria. Se houver divergência, vale a primeira aba |
| `Cópia de GUIA` | Ficha espiritual (médium × linha → entidades) |
| `GUIA` | Apelidos de quem incorpora ("Pai Igor", "Thiago DV") |
| `CONSULENTE` | Consulentes: CPF, cidade, outra casa, como soube, telefone, parentesco |

As giras antigas **não** são importadas: o sistema começa do zero.

Sobre a importação:
- Pode ser repetida sem duplicar nada. Ela só preenche campos vazios, então não apaga o que foi digitado no sistema.
- No fim, o relatório lista o que precisa ser conferido à mão:
  - apelidos ambíguos (por exemplo, dois Thiagos);
  - parentescos não identificados;
  - parentescos vinculados por grafia parecida;
  - categorias divergentes entre as abas.

## Uso no dia a dia (vários aparelhos)

### Opção A — um computador da casa como servidor

```bash
python servidor.py
```

O programa mostra um endereço como `http://192.168.0.10:8000`. Abra esse endereço no navegador
dos celulares e tablets conectados ao **mesmo Wi-Fi**. Para ter o sistema como um aplicativo,
use "Adicionar à tela inicial".

- O computador precisa ficar ligado durante a gira.
- No Windows, permita o Python no firewall quando o aviso aparecer.

### Opção B — hospedagem na internet

O sistema funciona em qualquer serviço que rode Python com disco persistente (PythonAnywhere,
Render, Railway, uma VPS…). Configure:
- `SECRET_KEY`: uma chave aleatória longa;
- `COOKIE_SEGURO=1`: obrigatório com HTTPS;
- `DATABASE_URL`: opcional, para usar outro caminho de banco.

O banco é o arquivo `instance/tuc7fj.db`. **Faça cópia de segurança dele.**

### Uso simultâneo

- **Edição:** o SQLite fica em modo WAL, para que as leituras não esperem as gravações. Cada
  cadastro tem um número de versão. Se dois aparelhos editarem a mesma pessoa, o segundo a salvar
  recebe um aviso e não apaga, sem perceber, o que o primeiro fez.
- **CPF:** é único. Duas pessoas cadastrando o mesmo CPF ao mesmo tempo não geram duplicata.

## Modelo de dados

```
Pessoa ─┬─< PessoaFuncao            (Cambone, Ogã)
        ├─< HistoricoCategoria      (de → para, data, observação, quem registrou)
        ├─< Entidade >── Linha      (ficha espiritual; nome pode ficar vazio)
        └─< Parentesco >── Pessoa   (laço guardado uma vez, vale nos dois sentidos)
Configuracao                        (senha da casa)
```

## Testes

```bash
pytest
```

Os testes usam apenas dados **fictícios**. A planilha de teste é gerada dentro do próprio teste.
