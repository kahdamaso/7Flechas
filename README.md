# TUC7FJ — Sistema de gestão do terreiro

Sistema web que substitui as planilhas do TUC7FJ: cadastro de médiuns e consulentes,
entidades por linha, sessões/giras, presença e atendimentos.

**Stack:** Python 3.11+ · Flask · SQLAlchemy · SQLite · Jinja2 + Bootstrap 5 (servido localmente, funciona sem internet).

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

flask --app run init-db            # cria instance/tuc7fj.db
flask --app run importar data/     # importa os CSVs (veja abaixo)
flask --app run run                # abre em http://127.0.0.1:5000
```

Em produção, defina `SECRET_KEY` (e opcionalmente `DATABASE_URL`) como variáveis de ambiente.

## Importação das planilhas

Coloque os CSVs em `data/`. A pasta não vai para o git porque guarda dados pessoais.

```bash
flask --app run importar data/                    # ou: python scripts/importar_csv.py data/
flask --app run importar data/TUC7FJ_02_08_2026.csv --substituir   # reimporta uma sessão
flask --app run importar data/TUC7FJ_PRESENÇA.csv --ano 2026        # datas sem ano
```

| Arquivo (pelo nome) | O que vira |
|---|---|
| `*CONSULENTE*.csv` | Consulentes (Nome, CPF, Telefone, Cidade, UF, Bairro, Endereço, E-mail, Nascimento, Obs) |
| `*RETORNO_MEDIUNS*.csv` | Médiuns + entidades que cada um trabalha (colunas Caboclo, Exu, …; várias separadas por `/`) |
| `*DD_MM_AAAA*.csv` | Uma sessão: blocos Corrente / Auxiliares / Colaborador / Consulentes → atendimentos e manifestações |
| `*PRESEN*.csv` | Presença: formato largo (uma coluna por data com P/F/J) ou longo (Nome, Data, Presente) |

Os arquivos são processados nesta ordem: consulentes → retorno dos médiuns → sessões → presença.
Toda a importação roda numa única transação, então um erro não deixa dados pela metade.

O que a importação trata:
- Codificação UTF-8 ou Windows-1252 e separador `,` ou `;`.
- Cabeçalhos em qualquer linha do arquivo, inclusive vários blocos com ordem de colunas diferente.
- Células vazias, `-`, `N/A` e `#N/D`.
- Nomes em CAIXA ALTA convertidos para "Nome Próprio".
- Comparação de nomes sem acento e sem diferença de maiúsculas (`Canindé ` = `CANINDE`).
- CPF sem máscara e com o zero à esquerda perdido pelo Excel. CPFs inválidos são descartados com aviso.
- Erros de digitação conhecidos, como `ORIENTEÇÃO` e `Sutão da Matas`. Ficam no dicionário `CORRECOES` em `app/importacao.py`.
- Reimportação idempotente: pessoas e entidades são reaproveitadas, e sessões que já têm atendimentos são puladas (a menos que você use `--substituir`).

### Como as células das colunas de linha são interpretadas

Nas planilhas de sessão, uma célula como `Exu = Jessica` ou `Exu = 7 Garfos` pode citar a
**entidade** ou o **médium** que atendeu. O importador guarda sempre o texto original e tenta resolver:

1. `GERAL` → marcado como "Geral".
2. Entidade já cadastrada naquela linha → entidade. Se só um médium trabalha essa entidade, ele também é registrado.
3. Nome curto que identifica um único médium (`Pablo`, `Jessica`) → médium. A entidade dele naquela linha é preenchida se o RETORNO_MEDIUNS tiver só uma.
4. Nome que pode ser de mais de um médium (`Thiago DV`, com dois Thiagos) → fica só o texto, com aviso.
5. Qualquer outro valor → nova entidade naquela linha.

No fim, o relatório lista as **entidades criadas**. Confira essa lista: um nome de pessoa pode ter
virado entidade. Para corrigir, preencha o **apelido** do médium (por exemplo, "Thiago DV") e
reimporte com `--substituir`, ou ajuste na tela de Entidades.

## Telas

- **Sessões:** criar gira → marcar presença (presente/falta/justificativa) → registrar atendimentos.
  O formulário de atendimento tem uma linha por linha de trabalho (entidade + médium + anotação).
  Um consulente novo pode ser cadastrado direto pelo nome, e o botão "Salvar e registrar outro" agiliza o lançamento em sequência.
- **Médiuns:** CRUD, grupo (Corrente/Auxiliar/Colaborador), ativo/inativo, entidades que trabalha, histórico e % de frequência.
- **Consulentes:** CRUD com busca por nome, CPF ou telefone, filtro por cidade e histórico de atendimentos.
- **Entidades:** CRUD por linha, com os médiuns de cada entidade e o número de atendimentos.

## Modelo de dados

```
Medium ─┬─< MediumEntidade >── Entidade >── Linha
        ├─< Presenca >── Sessao
        └─< Atendimento (quando o atendido é médium)
Consulente ──< Atendimento >── Sessao
Atendimento ──< Manifestacao >── Linha
                     ├── Entidade (opcional)
                     └── Medium responsável (opcional)
```

- `Linha` inclui as linhas de trabalho (Caboclo, Exu, Pombo Gira…) e os "serviços" 7 Flechas e Maca,
  cujo conteúdo é o tipo de trabalho (Orientação Espiritual, Consagrar Pano…).
- `Atendimento` = uma linha da planilha de sessão (categoria, parentesco, retorno).
- `Manifestacao` = cada célula preenchida das colunas de linha.

## Testes

```bash
pytest
```

Os testes usam planilhas **fictícias** em `tests/fixtures/`.
