"""Formato do que entra e do que sai pela API. É o contrato entre a visão e o backend."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bpmn_agent.app.sessao import Sessao

TAMANHO_MAX_TEXTO = 8000


class Saude(BaseModel):
    status: Literal["ok"] = "ok"
    provedor: str    # qual LLM o servidor está configurado para usar (definido no .env)
    modelo: str


class CriarSessao(BaseModel):
    processo: dict | None = None    # conteúdo de um processo.json salvo antes, para continuar


class EnviarMensagem(BaseModel):
    texto: str = Field(min_length=1, max_length=TAMANHO_MAX_TEXTO)


class Mensagem(BaseModel):
    papel: Literal["user", "assistant"]
    texto: str


class EstadoSessao(BaseModel):
    """Tudo o que a tela precisa para se desenhar, em uma resposta só."""
    id: str
    nome: str
    vazio: bool                 # ainda não há nenhum elemento no desenho
    narrativa: str              # descrição em texto, para pessoas
    em_aberto: list[str]        # o que o próprio diagrama acusa como faltando
    pendencias: list[str]       # lembretes anotados pelo agente
    historico: list[Mensagem]   # só as falas (sem chamadas de ferramentas)
    bpmn_xml: str
    processo: dict              # o processo.json, para baixar e continuar depois
    pasta: str                  # onde o servidor gravou os arquivos (informativo)


class RespostaTurno(BaseModel):
    texto: str
    acoes: list[str]
    alterados: list[str]


class Desfeito(BaseModel):
    mensagem: str


class Erro(BaseModel):
    codigo: str
    mensagem: str               # frase para a pessoa leiga
    detalhe: str = ""           # informação técnica, para quem desenvolve


def estado_de(sessao: Sessao) -> EstadoSessao:
    modelo = sessao.modelo
    return EstadoSessao(
        id=sessao.id,
        nome=modelo.p.nome,
        vazio=not modelo.p.elementos,
        narrativa=modelo.narrativa(),
        em_aberto=modelo.problemas(),
        pendencias=list(modelo.p.pendencias),
        historico=[Mensagem(papel=papel, texto=texto) for papel, texto in sessao.historico_visivel()],
        bpmn_xml=sessao.bpmn_xml(),
        processo=modelo.para_dict(),
        pasta=str(sessao.pasta),
    )
