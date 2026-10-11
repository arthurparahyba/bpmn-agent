"""
Os dados do processo: tipos de elemento, as três estruturas (Elemento, Fluxo, Processo)
e o erro de uso. Aqui não há operações; elas ficam em modelo.py.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

# Tipos amigáveis (usados pelo agente) -> tipo BPMN
TIPOS: dict[str, str] = {
    "inicio": "startEvent",
    "fim": "endEvent",
    "tarefa": "task",
    "tarefa_pessoa": "userTask",        # alguém faz usando um sistema/tela
    "tarefa_sistema": "serviceTask",    # o sistema faz sozinho
    "tarefa_manual": "manualTask",      # feita à mão, fora de sistema
    "envio": "sendTask",                # enviar e-mail, mensagem, documento
    "decisao": "exclusiveGateway",      # um caminho OU outro
    "paralelo": "parallelGateway",      # vários caminhos ao mesmo tempo / junção
    "espera": "intermediateCatchEvent", # aguardar prazo / data
}
TIPO_AMIGAVEL = {v: k for k, v in TIPOS.items()}
ROTULO_LEGIVEL = {
    "startEvent": "início", "endEvent": "fim", "task": "passo", "userTask": "feito por pessoa",
    "serviceTask": "automático", "manualTask": "manual", "sendTask": "envio", "exclusiveGateway": "decisão",
    "parallelGateway": "ao mesmo tempo", "intermediateCatchEvent": "espera",
}
GATEWAYS = {"exclusiveGateway", "parallelGateway"}
# Não são trabalho de alguém: sem responsável próprio, ficam na raia de quem vem antes (ou depois).
HERDAM_RAIA = GATEWAYS | {"startEvent", "endEvent", "intermediateCatchEvent"}

PREFIXO = {
    "startEvent": "Inicio", "endEvent": "Fim", "intermediateCatchEvent": "Espera",
    "exclusiveGateway": "Decisao", "parallelGateway": "Paralelo",
}


class ErroModelo(ValueError):
    """Erro com mensagem amigável, devolvida ao agente como resultado da ferramenta."""


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


@dataclass
class Elemento:
    id: str
    tipo: str                  # tipo BPMN (startEvent, task, ...)
    nome: str
    responsavel: str = ""      # nome do participante (raia); "" = sem raia
    descricao: str = ""
    regras: list[str] = field(default_factory=list)
    sistema: str = ""          # sistema do catálogo (Processo.sistemas) em que o passo é executado
    operacao: str = ""         # tela/chamada usada; vale para `chama` se houver, senão para `sistema`
    chama: str = ""            # outro sistema que o passo aciona (em geral de terceiros), ex.: o Gateway


@dataclass
class Sistema:
    """Um sistema que o processo usa ou integra. Não é quem trabalha (isso é participante)."""
    nome: str
    descricao: str = ""
    integracao: str = ""       # como se acessa: tela, API REST, arquivo, fila...
    operacoes: list[str] = field(default_factory=list)   # telas/endpoints conhecidos
    externo: bool = False      # True: sistema de terceiros (fora da empresa); aparece como caixa separada no desenho


@dataclass
class Fluxo:
    id: str
    origem: str
    destino: str
    rotulo: str = ""


@dataclass
class Processo:
    nome: str = "Novo processo"
    descricao: str = ""
    participantes: list[str] = field(default_factory=list)
    sistemas: list[Sistema] = field(default_factory=list)
    elementos: dict[str, Elemento] = field(default_factory=dict)
    fluxos: list[Fluxo] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    contadores: dict[str, int] = field(default_factory=dict)
