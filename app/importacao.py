"""Importação das planilhas CSV do TUC7FJ para o banco SQLite.

Arquivos reconhecidos (pelo nome, sem diferenciar maiúsculas/acentos):

- ``*CONSULENTE*.csv``        cadastro de consulentes
- ``*RETORNO_MEDIUNS*.csv``   entidades que cada médium trabalha
- ``*PRESEN*.csv``            presença dos médiuns (formato largo ou longo)
- ``*DD_MM_AAAA*.csv``        planilha de uma sessão/gira com os atendimentos

A ordem de processamento é sempre: consulentes -> retorno dos médiuns ->
sessões -> presença, para que as sessões consigam identificar médiuns e
entidades já cadastrados.

Tratamentos aplicados às planilhas:
- detecção de codificação (UTF-8, UTF-8 com BOM, Windows-1252) e separador (, ou ;);
- cabeçalhos localizados em qualquer linha (blocos Corrente/Auxiliares/...);
- espaços extras, células "-", "N/A", "#N/D" etc. tratadas como vazias;
- nomes em CAIXA ALTA convertidos para nome próprio;
- comparação de nomes sem acentos/caixa ('Canindé ' == 'CANINDE');
- CPF sem máscara e com zeros à esquerda recompostos; CPFs inválidos descartados com aviso;
- reimportação idempotente: pessoas, entidades e sessões já existentes são reaproveitadas.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .extensions import db
from .models import (
    Atendimento,
    Consulente,
    Entidade,
    Linha,
    Manifestacao,
    Medium,
    MediumEntidade,
    Presenca,
    Sessao,
    garantir_linhas_padrao,
)
from .utils import chave, limpar, nome_proprio, normalizar_cpf, normalizar_telefone

# ---------------------------------------------------------------------------
# Vocabulário das planilhas
# ---------------------------------------------------------------------------

VAZIOS = {"", "-", "--", "---", ".", "n/a", "na", "null", "none", "nan", "#n/d", "#n/a"}

# cabeçalho da coluna (chave compacta) -> nome da Linha no banco
_LINHAS_CABECALHO = {
    "7flechas": "7 Flechas",
    "seteflechas": "7 Flechas",
    "maca": "Maca",
    "caboclo": "Caboclo",
    "caboclos": "Caboclo",
    "boiadeiro": "Boiadeiro",
    "boiadeiros": "Boiadeiro",
    "baiano": "Baiano",
    "baianos": "Baiano",
    "povodagua": "Povo d'Água",
    "povod'agua": "Povo d'Água",
    "marinheiro": "Povo d'Água",
    "marinheiros": "Povo d'Água",
    "pretovelho": "Preto Velho",
    "pretovelhos": "Preto Velho",
    "pretosvelhos": "Preto Velho",
    "ere": "Erê",
    "eres": "Erê",
    "crianca": "Erê",
    "criancas": "Erê",
    "cigano": "Cigano",
    "ciganos": "Cigano",
    "cigana": "Cigano",
    "exu": "Exu",
    "exus": "Exu",
    "pombogira": "Pombo Gira",
    "pombagira": "Pombo Gira",
    "pombasgiras": "Pombo Gira",
    "malandragem": "Malandragem",
    "malandro": "Malandragem",
    "malandros": "Malandragem",
    "mestre": "Mestres",
    "mestres": "Mestres",
}

# título do bloco na planilha de sessão -> categoria do atendimento
_BLOCOS = {
    "corrente": "Corrente",
    "auxiliar": "Auxiliar",
    "auxiliares": "Auxiliar",
    "colaborador": "Colaborador",
    "colaboradores": "Colaborador",
    "consulente": "Consulente",
    "consulentes": "Consulente",
}

# Correções de digitação recorrentes (chave normalizada -> forma correta).
CORRECOES = {
    "orientecao espiritual": "Orientação Espiritual",
    "orientacao espiritual": "Orientação Espiritual",
    "sutao da matas": "Sultão das Matas",
    "sutao das matas": "Sultão das Matas",
    "sultao da matas": "Sultão das Matas",
    "ze caveira": "Zé Caveira",
}

PRESENTE = {"p", "x", "presente", "sim", "s", "1", "ok", "✓", "✔", "v"}
FALTA = {"f", "falta", "faltou", "nao", "n", "0", "ausente", "a"}
JUSTIFICADA = {"j", "fj", "justificada", "justificado", "falta justificada"}


def _compacto(texto):
    return re.sub(r"[\s'´`’]", "", chave(texto))


def linha_do_cabecalho(texto):
    return _LINHAS_CABECALHO.get(_compacto(texto))


def valor(texto):
    """Limpa uma célula; devolve None para valores vazios/marcadores de nulo."""
    texto = limpar(texto)
    if texto is None or chave(texto) in VAZIOS:
        return None
    return texto


def corrigir(texto):
    texto = valor(texto)
    if texto is None:
        return None
    return CORRECOES.get(chave(texto), nome_proprio(texto))


def ler_data(texto, ano_padrao=None):
    texto = valor(texto)
    if not texto:
        return None
    texto = texto.split(" ")[0]
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d_%m_%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    if ano_padrao:
        m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})", texto)
        if m:
            try:
                return date(ano_padrao, int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None
    return None


def data_do_arquivo(caminho):
    m = re.search(r"(\d{2})[_\-.](\d{2})[_\-.](\d{4})", Path(caminho).stem)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def ler_csv(caminho):
    """Lê um CSV tolerando codificação e separador diferentes."""
    bruto = Path(caminho).read_bytes()
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    amostra = texto[:4096]
    separador = ";" if amostra.count(";") > amostra.count(",") else ","
    return [linha for linha in csv.reader(io.StringIO(texto), delimiter=separador)]


def _celula(linha, indice):
    return linha[indice] if indice is not None and indice < len(linha) else None


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


@dataclass
class Relatorio:
    contagens: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)
    entidades_criadas: list = field(default_factory=list)

    def conta(self, item, n=1):
        self.contagens[item] = self.contagens.get(item, 0) + n

    def aviso(self, arquivo, mensagem):
        self.avisos.append(f"[{Path(arquivo).name}] {mensagem}")

    def texto(self):
        linhas = ["Resumo da importação:"]
        linhas += [f"  {k}: {v}" for k, v in sorted(self.contagens.items())]
        if self.entidades_criadas:
            linhas.append("\nEntidades criadas (confira se algum nome é na verdade um médium):")
            linhas += [f"  - {e}" for e in self.entidades_criadas]
        if self.avisos:
            linhas.append(f"\nAvisos ({len(self.avisos)}):")
            linhas += [f"  - {a}" for a in self.avisos]
        return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Repositório em memória para buscas por nome durante a importação
# ---------------------------------------------------------------------------


class Cadastros:
    def __init__(self, relatorio):
        self.rel = relatorio
        self.linhas = {l.nome: l for l in Linha.query.all()}

    # -- médiuns -----------------------------------------------------------
    def medium(self, nome, grupo=None):
        nome = nome_proprio(nome)
        medium = Medium.query.filter_by(nome_chave=chave(nome)).first()
        if medium is None:
            medium = Medium.query.filter(Medium.apelido.isnot(None)).filter(
                db.func.lower(Medium.apelido) == nome.lower()
            ).first()
        if medium is None:
            medium = Medium(nome=nome, grupo=grupo or "Corrente")
            db.session.add(medium)
            db.session.flush()
            self.rel.conta("médiuns criados")
        return medium

    def medium_por_referencia(self, texto):
        """Identifica um médium citado numa célula ('Pablo', 'Thiago DV').

        Devolve (medium, ambiguo). Só aceita correspondência única. Pelo
        primeiro nome, só considera textos curtos ('Pablo', 'Thiago DV'), para
        não confundir entidades como 'Maria Quitéria' com a médium 'Maria ...'.
        """
        k = chave(texto)
        todos = Medium.query.all()
        exatos = [m for m in todos if m.nome_chave == k or (m.apelido and chave(m.apelido) == k)]
        if len(exatos) == 1:
            return exatos[0], False
        if len(exatos) > 1:
            return None, True
        tokens = k.split(" ")
        referencia_curta = len(tokens) == 1 or (len(tokens) == 2 and len(tokens[1]) <= 3)
        if not referencia_curta:
            return None, False
        mesmo_nome = [m for m in todos if m.nome_chave.split(" ")[0] == tokens[0]]
        if len(mesmo_nome) == 1:
            return mesmo_nome[0], False
        return None, len(mesmo_nome) > 1

    # -- consulentes ---------------------------------------------------------
    def consulente(self, nome, arquivo):
        nome = nome_proprio(nome)
        encontrados = Consulente.query.filter_by(nome_chave=chave(nome)).all()
        if len(encontrados) > 1:
            self.rel.aviso(arquivo, f"'{nome}' tem {len(encontrados)} cadastros homônimos; usado o primeiro.")
        if encontrados:
            return encontrados[0]
        consulente = Consulente(nome=nome)
        db.session.add(consulente)
        db.session.flush()
        self.rel.conta("consulentes criados")
        return consulente

    # -- entidades -----------------------------------------------------------
    def entidade(self, nome, linha, criar=True):
        nome = corrigir(nome)
        if not nome:
            return None
        ent = Entidade.query.filter_by(linha_id=linha.id, nome_chave=chave(nome)).first()
        if ent is None and criar:
            ent = Entidade(nome=nome, linha=linha)
            db.session.add(ent)
            db.session.flush()
            self.rel.conta("entidades criadas")
            self.rel.entidades_criadas.append(f"{linha.nome}: {nome}")
        return ent

    def vincular(self, medium, entidade):
        existe = MediumEntidade.query.filter_by(medium_id=medium.id, entidade_id=entidade.id).first()
        if not existe:
            db.session.add(MediumEntidade(medium=medium, entidade=entidade))
            db.session.flush()
            self.rel.conta("vínculos médium-entidade")

    def presenca(self, sessao, medium, presente=True, justificativa=None, sobrescrever=False):
        p = Presenca.query.filter_by(sessao_id=sessao.id, medium_id=medium.id).first()
        if p is None:
            p = Presenca(sessao=sessao, medium=medium, presente=presente, justificativa=justificativa)
            db.session.add(p)
            db.session.flush()
            self.rel.conta("presenças registradas")
        elif sobrescrever:
            p.presente, p.justificativa = presente, justificativa
        return p


def _sessao(data_sessao):
    sessao = Sessao.query.filter_by(data=data_sessao).order_by(Sessao.id).first()
    if sessao is None:
        sessao = Sessao(data=data_sessao, tipo="Gira")
        db.session.add(sessao)
        db.session.flush()
    return sessao


# ---------------------------------------------------------------------------
# Cabeçalhos
# ---------------------------------------------------------------------------

_ALIASES_CONSULENTE = {
    "nome": {"nome", "nome completo", "consulente", "consulentes", "nome do consulente"},
    "cpf": {"cpf", "cpf/cnpj", "documento"},
    "telefone": {"telefone", "tel", "celular", "fone", "whatsapp", "contato", "telefone/whatsapp"},
    "email": {"email", "e-mail", "e mail"},
    "cidade": {"cidade", "municipio"},
    "uf": {"uf", "estado"},
    "bairro": {"bairro"},
    "endereco": {"endereco", "rua", "logradouro"},
    "data_nascimento": {
        "data de nascimento", "data nascimento", "nascimento", "dt nasc", "dt. nasc.", "data nasc",
        "aniversario",
    },
    "observacoes": {"observacoes", "observacao", "obs", "obs.", "anotacoes"},
}

_NOME_MEDIUM = {"nome", "medium", "mediuns", "nome do medium", "membro"} | set(_BLOCOS)


def _mapear(cabecalho, aliases):
    mapa = {}
    for i, celula in enumerate(cabecalho):
        k = chave(celula)
        for campo, nomes in aliases.items():
            if k in nomes and campo not in mapa:
                mapa[campo] = i
    return mapa


# ---------------------------------------------------------------------------
# Importadores
# ---------------------------------------------------------------------------


def importar_consulentes(caminho, cad, rel):
    linhas = ler_csv(caminho)
    inicio, mapa = None, {}
    for i, linha in enumerate(linhas[:20]):
        mapa = _mapear(linha, _ALIASES_CONSULENTE)
        if "nome" in mapa:
            inicio = i + 1
            break
    if inicio is None:
        rel.aviso(caminho, "cabeçalho com coluna 'Nome' não encontrado; arquivo ignorado.")
        return

    for n, linha in enumerate(linhas[inicio:], start=inicio + 1):
        nome = valor(_celula(linha, mapa["nome"]))
        if not nome:
            continue
        nome = nome_proprio(nome)
        cpf_bruto = valor(_celula(linha, mapa.get("cpf")))
        cpf = normalizar_cpf(cpf_bruto)
        if cpf_bruto and not cpf:
            rel.aviso(caminho, f"linha {n}: CPF inválido '{cpf_bruto}' de {nome} descartado.")

        consulente = Consulente.query.filter_by(cpf=cpf).first() if cpf else None
        if consulente and consulente.nome_chave != chave(nome):
            rel.aviso(caminho, f"linha {n}: CPF de {nome} já pertence a {consulente.nome}; dados mesclados.")
        if consulente is None:
            candidatos = Consulente.query.filter_by(nome_chave=chave(nome)).all()
            # homônimo com CPF diferente é outra pessoa
            candidatos = [c for c in candidatos if not (cpf and c.cpf and c.cpf != cpf)]
            consulente = candidatos[0] if candidatos else None
        if consulente is None:
            consulente = Consulente(nome=nome)
            db.session.add(consulente)
            rel.conta("consulentes criados")
        else:
            rel.conta("consulentes atualizados")

        dados = {
            "cpf": cpf,
            "telefone": normalizar_telefone(_celula(linha, mapa.get("telefone"))),
            "email": (valor(_celula(linha, mapa.get("email"))) or "").lower() or None,
            "cidade": nome_proprio(valor(_celula(linha, mapa.get("cidade")))),
            "uf": (valor(_celula(linha, mapa.get("uf"))) or "").upper()[:2] or None,
            "bairro": nome_proprio(valor(_celula(linha, mapa.get("bairro")))),
            "endereco": valor(_celula(linha, mapa.get("endereco"))),
            "data_nascimento": ler_data(_celula(linha, mapa.get("data_nascimento"))),
            "observacoes": valor(_celula(linha, mapa.get("observacoes"))),
        }
        nasc_bruto = valor(_celula(linha, mapa.get("data_nascimento")))
        if nasc_bruto and not dados["data_nascimento"]:
            rel.aviso(caminho, f"linha {n}: data de nascimento '{nasc_bruto}' não reconhecida.")
        # só preenche o que está vazio: não apaga dados digitados no sistema
        for campo, novo in dados.items():
            if novo and not getattr(consulente, campo):
                setattr(consulente, campo, novo)
        db.session.flush()


def _cabecalho_de_linhas(linha):
    """Se a linha for um cabeçalho com colunas de linhas de trabalho, devolve o mapa."""
    colunas = {}
    for i, celula in enumerate(linha):
        nome_linha = linha_do_cabecalho(celula)
        if nome_linha and nome_linha not in colunas.values():
            colunas[i] = nome_linha
    return colunas


def _dividir(texto):
    return [p.strip() for p in re.split(r"[/;,]", texto) if p.strip()]


def importar_retorno_mediuns(caminho, cad, rel):
    linhas = ler_csv(caminho)
    colunas, col_nome, grupo = None, None, "Corrente"
    for n, linha in enumerate(linhas, start=1):
        possivel = _cabecalho_de_linhas(linha)
        if len(possivel) >= 2:
            colunas = possivel
            col_nome = next(
                (i for i, c in enumerate(linha) if chave(c) in _NOME_MEDIUM),
                next((i for i, c in enumerate(linha) if valor(c)), 0),
            )
            grupo = _BLOCOS.get(chave(linha[col_nome]), grupo)
            if grupo == "Consulente":
                grupo = "Corrente"
            continue
        if colunas is None:
            continue
        nome = valor(_celula(linha, col_nome))
        if not nome:
            continue
        medium = cad.medium(nome, grupo)
        for i, nome_linha in colunas.items():
            conteudo = valor(_celula(linha, i))
            if not conteudo or cad.linhas[nome_linha].servico:
                continue
            for parte in _dividir(conteudo):
                if chave(parte) in {"x", "geral", "sim", "ok"}:
                    continue
                cad.vincular(medium, cad.entidade(parte, cad.linhas[nome_linha]))
    if colunas is None:
        rel.aviso(caminho, "nenhum cabeçalho com linhas de trabalho (Caboclo, Exu...) encontrado.")


def _resolver_manifestacao(texto, linha, cad, rel, caminho):
    """Transforma o texto de uma célula numa Manifestacao (sem salvar)."""
    m = Manifestacao(linha=linha)
    if linha.servico:
        m.descricao = corrigir(texto)
        return m
    m.descricao = limpar(texto)
    if chave(texto) == "geral":
        m.geral = True
        return m

    # entidade já cadastrada nesta linha tem prioridade sobre nomes de médiuns
    m.entidade = cad.entidade(texto, linha, criar=False)
    if m.entidade:
        quem = [v.medium for v in m.entidade.mediuns]
        if len(quem) == 1:
            m.medium_responsavel = quem[0]
        return m

    medium, ambiguo = cad.medium_por_referencia(texto)
    if medium:
        m.medium_responsavel = medium
        do_medium = [v.entidade for v in medium.entidades if v.entidade.linha_id == linha.id]
        if len(do_medium) == 1:
            m.entidade = do_medium[0]
        return m
    if ambiguo:
        rel.aviso(caminho, f"'{texto.strip()}' ({linha.nome}) pode ser mais de um médium; mantido só o texto.")
        return m

    m.entidade = cad.entidade(texto, linha)
    quem = [v.medium for v in m.entidade.mediuns]
    if len(quem) == 1:
        m.medium_responsavel = quem[0]
    return m


def importar_sessao(caminho, cad, rel, substituir=False):
    data_sessao = data_do_arquivo(caminho)
    if data_sessao is None:
        rel.aviso(caminho, "data não encontrada no nome do arquivo (esperado DD_MM_AAAA).")
        return
    sessao = _sessao(data_sessao)
    if sessao.atendimentos:
        if not substituir:
            rel.aviso(caminho, f"sessão de {data_sessao:%d/%m/%Y} já tem atendimentos; ignorada "
                               "(use --substituir para reimportar).")
            return
        for at in list(sessao.atendimentos):
            db.session.delete(at)
        db.session.flush()
    rel.conta("sessões importadas")

    linhas = ler_csv(caminho)
    # 1ª passada: cadastra todas as pessoas, para que referências a médiuns
    # nas colunas de linha (ex.: 'Pablo') encontrem quem está nesta mesma gira.
    registros = []
    bloco = None
    for n, linha in enumerate(linhas, start=1):
        titulo = next(((i, _BLOCOS[chave(c)]) for i, c in enumerate(linha) if chave(c) in _BLOCOS), None)
        colunas = _cabecalho_de_linhas(linha)
        if titulo and colunas:
            mapa = {chave(c): i for i, c in enumerate(linha)}
            bloco = {
                "categoria": titulo[1],
                "col_nome": titulo[0],
                "col_parentesco": mapa.get("parentesco"),
                "col_retorno": mapa.get("retorno"),
                "colunas": colunas,
            }
            continue
        if bloco is None:
            continue
        nome = valor(_celula(linha, bloco["col_nome"]))
        if not nome:
            continue
        if bloco["categoria"] == "Consulente":
            pessoa = cad.consulente(nome, caminho)
        else:
            pessoa = cad.medium(nome, bloco["categoria"])
        registros.append((n, linha, bloco, pessoa))

    # 2ª passada: atendimentos e manifestações
    for n, linha, bloco, pessoa in registros:
        pessoa_kw = {"consulente": pessoa} if isinstance(pessoa, Consulente) else {"medium": pessoa}
        at = Atendimento(
            sessao=sessao,
            categoria=bloco["categoria"],
            parentesco=valor(_celula(linha, bloco["col_parentesco"])),  # texto livre: mantido
            retorno=corrigir(_celula(linha, bloco["col_retorno"])),
            **pessoa_kw,
        )
        db.session.add(at)
        if isinstance(pessoa, Medium):
            cad.presenca(sessao, pessoa)
        for i, nome_linha in bloco["colunas"].items():
            texto = valor(_celula(linha, i))
            if texto:
                manif = _resolver_manifestacao(texto, cad.linhas[nome_linha], cad, rel, caminho)
                at.manifestacoes.append(manif)
                rel.conta("manifestações")
                if manif.medium_responsavel:
                    cad.presenca(sessao, manif.medium_responsavel)
        db.session.flush()
        rel.conta("atendimentos")


def importar_presenca(caminho, cad, rel, ano_padrao=None):
    linhas = ler_csv(caminho)
    ano_padrao = ano_padrao or date.today().year
    for i, cab in enumerate(linhas[:20]):
        col_nome = next((j for j, c in enumerate(cab) if chave(c) in _NOME_MEDIUM), None)
        if col_nome is None:
            continue
        mapa = {chave(c): j for j, c in enumerate(cab)}
        col_data = mapa.get("data")
        col_status = next((mapa[k] for k in ("presente", "presenca", "status", "situacao") if k in mapa), None)
        col_grupo = mapa.get("grupo")
        if col_data is not None and col_status is not None:
            _presenca_longa(linhas[i + 1:], col_nome, col_data, col_status, col_grupo, cad, rel, caminho, ano_padrao)
        else:
            datas = {j: ler_data(c, ano_padrao) for j, c in enumerate(cab) if j != col_nome}
            datas = {j: d for j, d in datas.items() if d}
            if not datas:
                rel.aviso(caminho, "nenhuma coluna de data encontrada no cabeçalho.")
                return
            if any(not re.search(r"\d{4}|\d{1,2}/\d{1,2}/\d{2}$", cab[j]) for j in datas):
                rel.aviso(caminho, f"datas sem ano no cabeçalho; assumido {ano_padrao} (use --ano).")
            for n, linha in enumerate(linhas[i + 1:], start=i + 2):
                nome = valor(_celula(linha, col_nome))
                if not nome:
                    continue
                grupo = _BLOCOS.get(chave(_celula(linha, col_grupo)))
                medium = cad.medium(nome, grupo if grupo != "Consulente" else None)
                for j, d in datas.items():
                    _registrar_status(_celula(linha, j), d, medium, cad, rel, caminho, n)
        return
    rel.aviso(caminho, "cabeçalho com coluna de nome do médium não encontrado; arquivo ignorado.")


def _presenca_longa(linhas, col_nome, col_data, col_status, col_grupo, cad, rel, caminho, ano_padrao):
    for n, linha in enumerate(linhas, start=2):
        nome = valor(_celula(linha, col_nome))
        d = ler_data(_celula(linha, col_data), ano_padrao)
        if not nome:
            continue
        if not d:
            rel.aviso(caminho, f"linha {n}: data inválida para {nome}.")
            continue
        grupo = _BLOCOS.get(chave(_celula(linha, col_grupo)))
        medium = cad.medium(nome, grupo if grupo != "Consulente" else None)
        _registrar_status(_celula(linha, col_status), d, medium, cad, rel, caminho, n)


def _registrar_status(texto, d, medium, cad, rel, caminho, n):
    texto = valor(texto)
    if not texto:
        return
    k = chave(texto)
    if k in PRESENTE:
        presente, justificativa = True, None
    elif k in JUSTIFICADA:
        presente, justificativa = False, "Falta justificada"
    elif k in FALTA:
        presente, justificativa = False, None
    else:
        rel.aviso(caminho, f"linha {n}: marcação de presença '{texto}' não reconhecida ({medium.nome}).")
        return
    cad.presenca(_sessao(d), medium, presente, justificativa, sobrescrever=True)


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def classificar(caminho):
    k = chave(Path(caminho).stem).replace(" ", "_")
    if "consulente" in k:
        return "consulentes"
    if "retorno" in k and "medi" in k:
        return "retorno"
    if "presen" in k:
        return "presenca"
    if data_do_arquivo(caminho):
        return "sessao"
    return None


def importar(caminhos, substituir=False, ano=None):
    """Importa arquivos/pastas. Tudo numa transação: em caso de erro nada é gravado."""
    garantir_linhas_padrao()
    arquivos = []
    for c in caminhos:
        c = Path(c)
        arquivos += sorted(c.glob("*.csv")) if c.is_dir() else [c]

    rel = Relatorio()
    grupos = {"consulentes": [], "retorno": [], "sessao": [], "presenca": []}
    for arq in arquivos:
        tipo = classificar(arq)
        if tipo is None:
            rel.aviso(arq, "nome de arquivo não reconhecido; ignorado.")
        else:
            grupos[tipo].append(arq)
    grupos["sessao"].sort(key=data_do_arquivo)

    cad = Cadastros(rel)
    try:
        for arq in grupos["consulentes"]:
            importar_consulentes(arq, cad, rel)
        for arq in grupos["retorno"]:
            importar_retorno_mediuns(arq, cad, rel)
        for arq in grupos["sessao"]:
            importar_sessao(arq, cad, rel, substituir=substituir)
        for arq in grupos["presenca"]:
            importar_presenca(arq, cad, rel, ano_padrao=ano)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return rel
