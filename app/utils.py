"""Funções utilitárias de normalização de texto, usadas pelo app e pela importação."""

import re
import unicodedata

_PARTICULAS = {"da", "das", "de", "do", "dos", "e", "d'"}


def limpar(valor):
    """Remove espaços extras; devolve None para células vazias."""
    if valor is None:
        return None
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return texto or None


def chave(valor):
    """Chave de comparação: sem acentos, minúscula, espaços colapsados.

    'Canindé ' e 'CANINDE' produzem a mesma chave.
    """
    texto = limpar(valor)
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.casefold()


def nome_proprio(valor):
    """Formata nomes digitados em CAIXA ALTA ('MARIA JOSE DA SILVA' -> 'Maria Jose da Silva').

    Nomes já em caixa mista são mantidos como foram digitados.
    """
    texto = limpar(valor)
    if not texto:
        return None
    if texto != texto.upper():
        return texto
    palavras = []
    for i, palavra in enumerate(texto.lower().split(" ")):
        if i > 0 and palavra in _PARTICULAS:
            palavras.append(palavra)
        else:
            palavras.append(palavra[:1].upper() + palavra[1:])
    return " ".join(palavras)


def somente_digitos(valor):
    texto = limpar(valor)
    if not texto:
        return None
    digitos = re.sub(r"\D", "", texto)
    return digitos or None


def normalizar_cpf(valor):
    """Devolve o CPF com 11 dígitos (sem máscara) ou None se inválido/ausente.

    Planilhas costumam perder o zero à esquerda (CPF tratado como número),
    por isso completamos com zeros quando há entre 9 e 10 dígitos.
    """
    digitos = somente_digitos(valor)
    if not digitos:
        return None
    if 9 <= len(digitos) < 11:
        digitos = digitos.zfill(11)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return None
    return digitos


def formatar_cpf(cpf):
    if not cpf or len(cpf) != 11:
        return cpf or ""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def normalizar_telefone(valor):
    digitos = somente_digitos(valor)
    if not digitos:
        return None
    # remove DDI 55 quando presente
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        digitos = digitos[2:]
    return digitos if len(digitos) >= 8 else None


def formatar_telefone(tel):
    if not tel:
        return ""
    if len(tel) == 11:
        return f"({tel[:2]}) {tel[2:7]}-{tel[7:]}"
    if len(tel) == 10:
        return f"({tel[:2]}) {tel[2:6]}-{tel[6:]}"
    return tel
