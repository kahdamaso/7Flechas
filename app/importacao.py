"""Importação dos cadastros a partir da planilha TUC7FJ (Fase 1).

Aceita o .xlsx baixado do Google Drive ou uma pasta com CSVs exportados das
abas (o nome do arquivo identifica a aba, ex.: ``TUC7FJ_CONSULENTE.csv``).

Abas usadas
-----------
- ``PRESENÇA`` / ``RETORNO MEDIUNS`` / ``Página15``: nome e categoria dos
  médiuns (nesta ordem de prioridade quando há divergência).
- ``Cópia de GUIA``: ficha espiritual (médium x linha -> entidades).
- ``GUIA``: listas de seleção da planilha; os apelidos dos médiuns que
  incorporam ("Pai Igor", "Thiago DV") aparecem nelas.
- ``CONSULENTE``: cadastro do público (CPF, cidade, outra casa, como soube,
  parentesco, telefone).

Giras/sessões antigas NÃO são importadas (o sistema começa do zero).

Tratamentos: espaços e células vazias ("-", "NÃO", "0"), nomes em CAIXA ALTA,
nomes com/sem acento e com palavras em outra ordem, CPF/telefone gravados como
número (zero à esquerda perdido), erros de digitação conhecidos. A importação é
idempotente: rodar de novo não duplica nada e não apaga o que foi digitado no
sistema (só preenche campos vazios).
"""

import csv
import difflib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .extensions import db
from .models import (
    Entidade,
    HistoricoCategoria,
    Linha,
    Parentesco,
    Pessoa,
    garantir_linhas_padrao,
)
from .utils import chave, limpar, nome_proprio, normalizar_cpf, normalizar_telefone

ORIGEM = "Importado da planilha"

VAZIOS = {"", "-", "--", ".", "0", "0.0", "n/a", "na", "null", "none", "nan", "#n/d", "#n/a",
          "nao", "não", "x"}

CORRECOES = {
    "sutao da matas": "Sultão das Matas",
    "sutao das matas": "Sultão das Matas",
    "sultao da matas": "Sultão das Matas",
    "ze caveira": "Zé Caveira",
    "mae conga": "Mãe Conga",
}

CIDADES = {
    "bo despacho": "Bom Despacho",
    "nova serana": "Nova Serrana",
    "vespaziano": "Vespasiano",
    "divinopolis": "Divinópolis",
    "abaete": "Abaeté",
    "itauna": "Itaúna",
    "tres marias": "Três Marias",
    "dores do indaia": "Dores do Indaiá",
    "sao goncalo do para": "São Gonçalo do Pará",
    "santo antonio do monte": "Santo Antônio do Monte",
}

# cabeçalho (compacto, sem acento/espaço) -> nome da Linha
_LINHAS = {
    "caboclo": "Caboclo", "caboclos": "Caboclo",
    "pretovelho": "Preto Velho", "pretovelhos": "Preto Velho", "pretosvelhos": "Preto Velho",
    "baiano": "Baiano", "baianos": "Baiano",
    "boiadeiro": "Boiadeiro", "boiadeiros": "Boiadeiro",
    "povodagua": "Povo d'Água",
    "cigano": "Cigano", "ciganos": "Cigano",
    "ere": "Erê", "eres": "Erê",
    "exu": "Exu", "exus": "Exu",
    "exumirim": "Exu Mirim",
    "pombogira": "Pomba Gira", "pombagira": "Pomba Gira",
    "pombogiramirim": "Pomba Gira Mirim", "pombagiramirim": "Pomba Gira Mirim",
    "pombog.mirim": "Pomba Gira Mirim",
    "malandragem": "Malandragem",
    "mestre": "Mestres", "mestres": "Mestres",
    "princesa": "Princesas", "princesas": "Princesas",
    "cangaco": "Cangaço",
}

_CATEGORIAS = {"corrente": "Corrente", "auxiliar": "Auxiliar", "auxiliares": "Auxiliar",
               "colaborador": "Colaborador", "colaboradores": "Colaborador",
               "consulente": "Consulente"}

_COL_NOME_MEDIUM = {"mediuns", "medium", "mediun", "nome", "membro"}
_COL_CATEGORIA = {"categoria", "catogoria", "tipo", "grupo"}

# abas: chave normalizada do nome -> papel
ABAS = {
    "presenca": "categorias",
    "retorno mediuns": "categorias",
    "pagina15": "categorias",
    "copia de guia": "ficha",
    "ficha espiritual": "ficha",
    "guia": "apelidos",
    "consulente": "consulentes",
    "consulentes": "consulentes",
}
ORDEM_CATEGORIAS = ["presenca", "retorno mediuns", "pagina15"]


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def texto(valor):
    """Converte uma célula (str, número, data) em texto limpo ou None."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor.isoformat()
    return limpar(str(valor))


def util(valor):
    """Texto da célula, ou None se for um marcador de vazio ('-', 'NÃO', '0')."""
    t = texto(valor)
    if t is None or chave(t) in VAZIOS:
        return None
    return t


def _nome_aba(nome):
    nome = re.sub(r"^\w{0,12}?TUC7FJ[_\s-]*", "", nome, flags=re.I)  # tira prefixo do arquivo
    return chave(nome.replace("_", " ")).strip()


def ler_planilha(caminho):
    """Devolve {nome_normalizado_da_aba: [linhas]} para .xlsx, .csv ou pasta de CSVs."""
    caminho = Path(caminho)
    if caminho.is_dir():
        abas = {}
        for arq in sorted(caminho.glob("*.csv")):
            abas[_nome_aba(arq.stem)] = _ler_csv(arq)
        for arq in sorted(caminho.glob("*.xlsx")):
            abas.update(ler_planilha(arq))
        return abas
    if caminho.suffix.lower() == ".csv":
        return {_nome_aba(caminho.stem): _ler_csv(caminho)}
    import openpyxl

    livro = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        return {_nome_aba(ws.title): [list(r) for r in ws.iter_rows(values_only=True)]
                for ws in livro.worksheets}
    finally:
        livro.close()


def _ler_csv(caminho):
    bruto = Path(caminho).read_bytes()
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            conteudo = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    amostra = conteudo[:4096]
    separador = ";" if amostra.count(";") > amostra.count(",") else ","
    return list(csv.reader(io.StringIO(conteudo), delimiter=separador))


def _celula(linha, i):
    return linha[i] if i is not None and i < len(linha) else None


def _compacto(valor):
    return re.sub(r"[\s'´`’]", "", chave(texto(valor) or ""))


def corrigir(valor):
    t = util(valor)
    if t is None:
        return None
    return CORRECOES.get(chave(t), nome_proprio(t))


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


@dataclass
class Relatorio:
    contagens: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)
    pendencias: dict = field(default_factory=dict)  # título -> itens para conferir à mão

    def conta(self, item, n=1):
        self.contagens[item] = self.contagens.get(item, 0) + n

    def aviso(self, mensagem):
        self.avisos.append(mensagem)

    def pendencia(self, titulo, item):
        itens = self.pendencias.setdefault(titulo, [])
        if item not in itens:
            itens.append(item)

    def texto(self):
        linhas = ["Resumo da importação:"]
        linhas += [f"  {k}: {v}" for k, v in sorted(self.contagens.items())]
        for titulo, itens in self.pendencias.items():
            linhas.append(f"\n{titulo} ({len(itens)}):")
            linhas += [f"  - {i}" for i in itens]
        if self.avisos:
            linhas.append(f"\nAvisos ({len(self.avisos)}):")
            linhas += [f"  - {a}" for a in self.avisos]
        return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Busca de pessoas
# ---------------------------------------------------------------------------


def _tokens(nome):
    return chave(nome).split()


def encontrar_pessoa(nome):
    """Mesma pessoa = mesmo nome sem acento/caixa, ou as mesmas palavras em outra
    ordem ('Thiago Costa Soares' == 'Thiago Soares Costa')."""
    k = chave(nome)
    pessoa = Pessoa.query.filter_by(nome_chave=k).first()
    if pessoa:
        return pessoa
    if not k:
        return None
    alvo = sorted(k.split())
    mesmo_primeiro = Pessoa.query.filter(Pessoa.nome_chave.like(f"{k.split()[0]}%")).all()
    candidatos = [p for p in mesmo_primeiro if sorted(p.nome_chave.split()) == alvo]
    return candidatos[0] if len(candidatos) == 1 else None


def _criar_pessoa(nome, categoria, rel):
    p = Pessoa(nome=nome_proprio(nome), categoria=categoria, atualizado_por=ORIGEM)
    p.historico.append(HistoricoCategoria(de=None, para=categoria, observacao=ORIGEM,
                                          registrado_por=ORIGEM))
    db.session.add(p)
    db.session.flush()
    rel.conta(f"pessoas criadas ({categoria})")
    return p


def _parecido(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _referencia_medium(ref, mediuns):
    """Identifica um médium citado de forma abreviada ('Pai Káh', 'Maria Nunes',
    'Natalia R', 'Mileny').

    Devolve (pessoa, ambiguo, aproximado). Só aceita correspondência única;
    ``aproximado`` indica que foi por grafia parecida e merece conferência.
    """
    k = chave(ref)
    base = re.sub(r"^(pai|mae|vo|vovo|tio|tia)\s+", "", k)
    if not base:
        return None, False, False
    exatos = [m for m in mediuns if m.apelido and chave(m.apelido) in (k, base)]
    if len(exatos) == 1:
        return exatos[0], False, False
    tokens = base.split()

    def contem(m):
        # as palavras citadas aparecem no nome, na mesma ordem; uma letra só vale
        # como inicial ('Natalia R' -> 'Natália Rodrigues')
        nome = m.nome_chave.split()
        if nome[0] != tokens[0]:
            return False
        pos = 1
        for t in tokens[1:]:
            achou = next((i for i in range(pos, len(nome))
                          if nome[i] == t or (len(t) == 1 and nome[i].startswith(t))), None)
            if achou is None:
                return False
            pos = achou + 1
        return True

    candidatos = [m for m in mediuns if contem(m)]
    if len(candidatos) == 1:
        return candidatos[0], False, False
    if candidatos:
        return None, True, False
    # grafia parecida do primeiro nome ('Mileny' ~ 'Mylene', 'Raylaine' ~ 'Railany')
    if len(tokens[0]) >= 4:
        parecidos = [m for m in mediuns if _parecido(tokens[0], m.nome_chave.split()[0])]
        if len(tokens) > 1:
            parecidos = [m for m in parecidos
                         if all(any(_parecido(t, n) for n in m.nome_chave.split()[1:])
                                for t in tokens[1:])]
        if len(parecidos) == 1:
            return parecidos[0], False, True
        if parecidos:
            return None, True, False
    return None, False, False


# ---------------------------------------------------------------------------
# Etapas
# ---------------------------------------------------------------------------


def _achar_cabecalho(linhas, testar, limite=15):
    for i, linha in enumerate(linhas[:limite]):
        mapa = testar([chave(texto(c) or "") for c in linha])
        if mapa:
            return i, mapa
    return None, None


def importar_categorias(abas, rel):
    """Cria/atualiza os médiuns com a categoria. A primeira aba (PRESENÇA) prevalece."""
    definidas = {}  # pessoa_id -> (categoria, aba)
    for nome_aba in ORDEM_CATEGORIAS:
        linhas = abas.get(nome_aba)
        if not linhas:
            continue

        def testar(cab):
            col_nome = next((i for i, c in enumerate(cab) if c in _COL_NOME_MEDIUM), None)
            col_cat = next((i for i, c in enumerate(cab) if c in _COL_CATEGORIA), None)
            return (col_nome, col_cat) if col_nome is not None and col_cat is not None else None

        inicio, cols = _achar_cabecalho(linhas, testar)
        if cols is None:
            rel.aviso(f"Aba '{nome_aba}': cabeçalho com nome e categoria não encontrado.")
            continue
        col_nome, col_cat = cols
        for linha in linhas[inicio + 1:]:
            nome = util(_celula(linha, col_nome))
            categoria = _CATEGORIAS.get(chave(texto(_celula(linha, col_cat)) or ""))
            if not nome or not categoria:
                continue
            pessoa = encontrar_pessoa(nome)
            if pessoa is None:
                pessoa = _criar_pessoa(nome, categoria, rel)
            anterior = definidas.get(pessoa.id)
            if anterior is None:
                definidas[pessoa.id] = (categoria, nome_aba)
                if pessoa.atualizado_por == ORIGEM and pessoa.categoria != categoria:
                    pessoa.categoria = categoria
            elif anterior[0] != categoria:
                rel.pendencia("Categorias divergentes entre abas (mantida a primeira)",
                              f"{pessoa.nome}: {anterior[0]} ({anterior[1]}) x {categoria} ({nome_aba})")
    db.session.flush()


def importar_ficha(abas, rel, linhas_db):
    linhas = abas.get("copia de guia") or abas.get("ficha espiritual")
    if not linhas:
        rel.aviso("Aba da ficha espiritual ('Cópia de GUIA') não encontrada.")
        return

    def testar(cab):
        col_nome = next((i for i, c in enumerate(cab) if c in _COL_NOME_MEDIUM), None)
        colunas = {i: _LINHAS[re.sub(r"[\s']", "", c)] for i, c in enumerate(cab)
                   if re.sub(r"[\s']", "", c) in _LINHAS}
        return (col_nome, colunas) if col_nome is not None and len(colunas) >= 3 else None

    inicio, cols = _achar_cabecalho(linhas, testar)
    if cols is None:
        rel.aviso("Ficha espiritual: cabeçalho não reconhecido.")
        return
    col_nome, colunas = cols
    for linha in linhas[inicio + 1:]:
        nome = util(_celula(linha, col_nome))
        if not nome:
            continue
        medium = encontrar_pessoa(nome)
        if medium is None:
            medium = _criar_pessoa(nome, "Corrente", rel)
            rel.pendencia("Médiuns da ficha sem categoria em outra aba (cadastrados como Corrente)",
                          medium.nome)
        existentes = {(e.linha_id, e.nome_chave) for e in medium.entidades}
        for i, nome_linha in colunas.items():
            conteudo = util(_celula(linha, i))
            if not conteudo:
                continue
            linha_db = linhas_db[nome_linha]
            for parte in re.split(r"[,/;]", conteudo):
                nome_ent = corrigir(parte)
                if not nome_ent or chave(nome_ent) == "geral":
                    continue
                if (linha_db.id, chave(nome_ent)) in existentes:
                    continue
                medium.entidades.append(Entidade(linha=linha_db, nome=nome_ent))
                existentes.add((linha_db.id, chave(nome_ent)))
                rel.conta("entidades na ficha espiritual")
        if medium.entidades and not medium.incorpora:
            medium.incorpora = True
    db.session.flush()


def importar_apelidos(abas, rel):
    """Na aba GUIA, além dos nomes das entidades, aparecem os médiuns que
    incorporam, pelo apelido: "Pai Igor", "Mãe Layla", "Thiago DV", "Jessica".

    - com Pai/Mãe ou com sigla ("Thiago DV") -> vira o apelido do médium;
    - só o primeiro nome ("Jessica") -> apenas marca que o médium incorpora;
    - se mais de um médium tem aquele primeiro nome -> fica para conferir à mão.
    """
    linhas = abas.get("guia")
    if not linhas:
        return
    mediuns = Pessoa.query.filter(Pessoa.categoria != "Consulente").all()
    valores = {}
    for linha in linhas:
        for celula in linha:
            valor = util(celula)
            if valor:
                valores.setdefault(chave(valor), valor)
    for k, valor in valores.items():
        base = re.sub(r"^(pai|mae)\s+", "", k)
        tokens = base.split()
        com_titulo = base != k
        com_sigla = len(tokens) == 2 and len(tokens[1]) <= 3
        if not tokens or not (len(tokens) == 1 or com_sigla):
            continue  # nome de entidade ("Pedra Preta", "Rosa Caveira")
        mesmos = [m for m in mediuns if m.nome_chave.split()[0] == tokens[0]]
        if not mesmos and com_titulo:
            # 'Mãe Ralainy' ~ 'Railany'; se nada parecer, é entidade ('Pai Jacó')
            mesmos = [m for m in mediuns if _parecido(tokens[0], m.nome_chave.split()[0])]
        if not mesmos:
            continue  # nome de entidade ("Tiriri", "Pai Joaquim")
        if len(mesmos) != 1:
            rel.pendencia("Apelidos não identificados (preencha o apelido no cadastro do médium)",
                          valor)
            continue
        medium = mesmos[0]
        medium.incorpora = True
        if (com_titulo or com_sigla) and not medium.apelido:
            medium.apelido = valor
            rel.conta("apelidos definidos")
    db.session.flush()


def importar_consulentes(abas, rel):
    linhas = abas.get("consulente") or abas.get("consulentes")
    if not linhas:
        rel.aviso("Aba CONSULENTE não encontrada.")
        return

    def testar(cab):
        col_nome = next((i for i, c in enumerate(cab) if c in {"consulente", "nome", "nome completo"}), None)
        if col_nome is None:
            return None
        mapa = {"nome": col_nome}
        for i, c in enumerate(cab):
            if c == "cpf":
                mapa["cpf"] = i
            elif c.startswith("parentesco"):
                mapa["parentesco"] = i
            elif c in ("cidade", "municipio"):
                mapa["cidade"] = i
            elif "casa" in c:
                mapa["outra_casa"] = i
            elif "sabendo" in c or "soube" in c:
                mapa["como_soube"] = i
            elif c in ("telefone", "celular", "whatsapp", "fone"):
                mapa["telefone"] = i
            elif "nascimento" in c:
                mapa["nascimento"] = i
        return mapa

    inicio, mapa = _achar_cabecalho(linhas, testar)
    if mapa is None:
        rel.aviso("Aba CONSULENTE: cabeçalho não reconhecido.")
        return

    mediuns = Pessoa.query.filter(Pessoa.categoria != "Consulente").all()
    for n, linha in enumerate(linhas[inicio + 1:], start=inicio + 2):
        nome = util(_celula(linha, mapa["nome"]))
        if not nome:
            continue
        cpf_bruto = util(_celula(linha, mapa.get("cpf")))
        cpf = normalizar_cpf(cpf_bruto)
        nota_cpf = None
        if cpf_bruto and not cpf:
            if re.search(r"\d{5}", cpf_bruto):
                rel.aviso(f"CONSULENTE linha {n}: CPF inválido '{cpf_bruto}' de {nome_proprio(nome)}.")
            # 'CRIANÇA', '14 ANOS', 'NÃO SABE': guarda como observação
            nota_cpf = f"CPF na planilha: {cpf_bruto}"

        pessoa = Pessoa.query.filter_by(cpf=cpf).first() if cpf else None
        if pessoa and pessoa.nome_chave != chave(nome):
            # mesmo CPF com outro nome: pode ser erro de digitação ou CPF de um parente
            rel.aviso(f"CONSULENTE linha {n}: CPF de {nome_proprio(nome)} já pertence a "
                      f"{pessoa.nome}; cadastrado(a) sem CPF para conferência.")
            pessoa, cpf = None, None
        pessoa = pessoa or encontrar_pessoa(nome)
        if pessoa is None:
            pessoa = _criar_pessoa(nome, "Consulente", rel)
        else:
            rel.conta("consulentes já existentes (completados)")

        cidade = util(_celula(linha, mapa.get("cidade")))
        outra_casa = util(_celula(linha, mapa.get("outra_casa")))
        if outra_casa and re.fullmatch(r"[\d.]+", outra_casa):
            outra_casa = None
        if outra_casa and chave(outra_casa) == "sim":
            outra_casa = "Sim (não informou qual)"
        dados = {
            "cpf": cpf,
            "telefone": normalizar_telefone(texto(_celula(linha, mapa.get("telefone")))),
            "cidade": CIDADES.get(chave(cidade), nome_proprio(cidade)) if cidade else None,
            "outra_casa": outra_casa,
            "como_soube": util(_celula(linha, mapa.get("como_soube"))),
            "observacoes": nota_cpf,
        }
        # só preenche o que está vazio: não apaga o que foi digitado no sistema
        for campo_nome, novo in dados.items():
            if novo and not getattr(pessoa, campo_nome):
                setattr(pessoa, campo_nome, novo)
        db.session.flush()

        parentesco = util(_celula(linha, mapa.get("parentesco")))
        if parentesco and chave(parentesco) not in {"sim"}:
            pessoa.parentesco_informado = pessoa.parentesco_informado or parentesco
            _vincular_parentes(pessoa, parentesco, mediuns, rel)
    db.session.flush()


def _vincular_parentes(pessoa, textual, mediuns, rel):
    partes = re.split(r"\s*(?:,|/|;|-|\be\b|\+)\s*", chave(textual))
    for parte in filter(None, (p.strip() for p in partes)):
        medium, ambiguo, aproximado = _referencia_medium(parte, mediuns)
        if medium is None or medium.id == pessoa.id:
            motivo = "mais de um médium possível" if ambiguo else "nenhum médium com esse nome"
            rel.pendencia("Parentescos não identificados (cadastre no prontuário)",
                          f"{pessoa.nome}: '{parte}' ({motivo})")
            continue
        if not Parentesco.entre(pessoa.id, medium.id):
            Parentesco.criar(pessoa, medium, "Parente", observacao=f"{ORIGEM}: {textual}",
                             responsavel=ORIGEM)
            db.session.flush()
            rel.conta("parentescos vinculados")
            if aproximado:
                rel.pendencia("Parentescos vinculados por grafia parecida (confira)",
                              f"{pessoa.nome}: '{parte}' -> {medium.nome}")


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def importar(caminho):
    """Importa os cadastros. Tudo numa transação: em caso de erro nada é gravado."""
    garantir_linhas_padrao()
    abas = ler_planilha(caminho)
    rel = Relatorio()
    reconhecidas = [a for a in abas if a in ABAS]
    rel.conta("abas usadas", len(reconhecidas))
    linhas_db = {l.nome: l for l in Linha.query.all()}
    try:
        importar_categorias(abas, rel)
        importar_ficha(abas, rel, linhas_db)
        importar_apelidos(abas, rel)
        importar_consulentes(abas, rel)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return rel
