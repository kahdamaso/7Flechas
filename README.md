# TUC7FJ — Sistema de gestão do terreiro

Aplicação web para a secretaria do terreiro, que substitui as planilhas. Funciona no celular, no
tablet e no computador, e vários aparelhos podem usá-la ao mesmo tempo.

> **Para testar online, sem instalar nada, veja o [ONLINE.md](ONLINE.md).**
> **Para instalar num computador da casa, veja o [INSTALAR.md](INSTALAR.md).**
> Os dois guias são passo a passo e não exigem programação.

**Stack:** Python 3.11+ · Flask · SQLAlchemy · SQLite · Bootstrap 5, servido localmente (funciona sem internet).

## Fases

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 | Pessoas e trajetória (Consulente → Colaborador → Auxiliar → Corrente), funções (Cambone, Ogã), parentescos, ficha espiritual, importação dos cadastros | **pronta** |
| 2 | Gira: chamada (SIM/NÃO), inscrição, atendimento puxado pelo cambone por entidade, retornos e prontuário | **pronta** |
| 3 | Relatórios: frequência dos médiuns, retornos, giras e atendimentos (com planilha CSV); cópias de segurança | **pronta** |
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

## A gira (Fase 2)

Menu **Giras → Nova gira**. O tipo é sugerido pelo dia da semana:
- **Sexta:** pública, atende consulentes e membros da casa.
- **Quarta:** interna, atende só Auxiliares e Corrente.
- **Especial:** festas e giras extras.

1. **Chamada:** a lista mostra os médiuns ativos.
   - Toque em **SIM** ou **NÃO**. Salva na hora e aparece nos outros aparelhos.
   - As entidades da ficha espiritual de quem está SIM ficam **em terra**.
2. **Inscrição:** digite o nome de quem chegou. O sistema mostra:
   - os **retornos pendentes**, avisando se o médium da entidade não veio;
   - os **parentes** na casa.

   Consulentes e Colaboradores passam em **todas as linhas**. Auxiliares e Corrente escolhem as
   linhas (GERAL). Aqui também se registram os pedidos ao **Sete Flechas**: orientação espiritual,
   consagrar pano, consagrar guiada e autorização para conversar com uma entidade específica.
3. **Atendimento:**
   1. O cambone diz o nome da entidade e a pessoa do sistema toca nela.
   2. Se havia uma conversa em andamento, ela é encerrada: **Atendido**, **Não quis passar** ou
      **Não estava**. Se a entidade pediu retorno, informa-se a data (já vem preenchida com +7 dias) e uma observação.
   3. O sistema sugere quem chamar, nesta ordem:
      1. quem tem **retorno** com aquela entidade;
      2. **pedidos ao Sete Flechas**, quando a entidade é o Sete Flechas;
      3. quem foi **autorizado** pelo Sete Flechas a falar com aquela entidade;
      4. a **fila da linha**: primeiro quem incorpora, depois por ordem de chegada.

   Quem é **parente** do médium fica bloqueado. A liberação manual existe e fica registrada. O
   próprio médium e quem já está conversando com outra entidade também ficam fora da fila.
4. **Mapa:** grade pessoa × linha, como a planilha antiga. Também serve para registrar que a pessoa
   não quer passar numa linha. Pode ser impresso.

Os **retornos** ficam pendentes até a pessoa voltar e conversar com a mesma entidade. Nessa
conversa, o retorno é concluído automaticamente. Se o médium faltar, o retorno continua pendente.
O menu **Retornos** lista os pendentes, os atrasados, os concluídos e os cancelados. O prontuário
de cada pessoa mostra todas as giras, conversas e retornos dela.

**Vários aparelhos ao mesmo tempo:** as telas de chamada, inscrição, atendimento e mapa se
atualizam sozinhas a cada poucos segundos. O banco garante que:
- uma entidade atende uma pessoa por vez;
- uma pessoa conversa com uma entidade por vez.

Se dois aparelhos chamarem ao mesmo tempo, o segundo recebe um aviso.

## Relatórios (Fase 3)

O menu **Relatórios** tem três relatórios. Cada um tem filtro de período (o padrão são os últimos
90 dias) e o botão **Planilha (CSV)**, que abre direto no Excel e no Google Planilhas.

- **Frequência dos médiuns:**
  - presenças e faltas na chamada;
  - percentual calculado só sobre as giras em que a pessoa foi marcada;
  - quantas pessoas as entidades de cada médium atenderam;
  - quantas vezes cada um foi cambone.

  Colaboradores só contam nas giras públicas. A lista começa por quem tem a menor frequência.
- **Retornos:**
  - pedidos, concluídos e cancelados, com a taxa de conclusão;
  - pendentes e atrasados hoje;
  - ranking das entidades que mais pedem retorno.
- **Giras e atendimentos:**
  - movimento de cada gira;
  - conversas por entidade e por linha;
  - inscrições por categoria;
  - quem veio pela primeira vez.

## Cópias de segurança

- `python servidor.py` faz uma cópia do banco ao iniciar e a cada 6 horas, em `instance/backups/`.
  São guardadas as 30 mais recentes.
- Para fazer uma cópia na hora: `flask --app run backup`.
- Para restaurar, pare o sistema e copie o arquivo desejado por cima de `instance/tuc7fj.db`.
- **Guarde cópias também fora do computador.** Por exemplo, copie periodicamente a pasta
  `instance/backups/` para um pendrive ou para o Google Drive.

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

Gira ─┬─< Presenca >── Pessoa            (chamada SIM/NÃO)
      ├─< CamboneGira >── Entidade         (quem camboneia cada entidade)
      └─< Inscricao >── Pessoa
             ├─< InscricaoLinha >── Linha  (linhas escolhidas: GERAL)
             ├─< PedidoSeteFlechas         (orientação, consagração, autorização)
             └─< Conversa >── Entidade     (situação, cambone, retorno cumprido)
Retorno >── Pessoa, Entidade, Conversa de origem   (pendente → concluído/cancelado)
```

## Testes

```bash
pytest
```

Os testes usam apenas dados **fictícios**. A planilha de teste é gerada dentro do próprio teste.
