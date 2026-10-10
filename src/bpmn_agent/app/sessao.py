"""
Sessao: a porta de entrada do backend para as interfaces.

Uma conversa = um processo + um thread no LangGraph + arquivos salvos em disco.
A API conversa só com esta classe: envia o texto do usuário e recebe um RespostaTurno.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from bpmn_agent.app.agente.grafo import LIMITE_PASSOS_GRAFO, construir_grafo, texto_de
from bpmn_agent.app.agente.prompt import SAUDACAO
from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.exportacao.exportar_bpmn import gerar_bpmn_xml
from bpmn_agent.app.persistencia import salvar_artefatos


@dataclass
class RespostaTurno:
    texto: str
    acoes: list[str] = field(default_factory=list)        # resultados das ferramentas (para depuração/UI)
    alterados: list[str] = field(default_factory=list)    # ids criados/alterados (destaque no desenho)


class Sessao:
    """Uma conversa = um processo + um thread no LangGraph + arquivos salvos em disco."""

    def __init__(self, llm: BaseChatModel, pasta: str | Path = "sessoes",
                 modelo: ModeloProcesso | None = None, id: str | None = None):
        self.id = id or uuid.uuid4().hex[:8]
        self.pasta = Path(pasta) / self.id
        self.modelo = modelo or ModeloProcesso()
        self.checkpointer = MemorySaver()
        self.grafo = construir_grafo(llm, self, self.checkpointer)
        self.config = {"configurable": {"thread_id": self.id}, "recursion_limit": LIMITE_PASSOS_GRAFO}
        saudacao = SAUDACAO if not self.modelo.p.elementos else (
            f"Oi de novo! Carreguei o processo **{self.modelo.p.nome}**. "
            "Quer continuar de onde paramos ou mudar alguma coisa?")
        self.grafo.update_state(self.config, {"messages": [AIMessage(content=saudacao)]}, as_node="agente")

    # ----------------------------------------------------------------- conversa
    def enviar(self, texto_usuario: str) -> RespostaTurno:
        antes = {i: (e.nome, e.tipo, e.responsavel, tuple(e.regras), e.descricao)
                 for i, e in self.modelo.p.elementos.items()}
        fluxos_antes = {(f.origem, f.destino, f.rotulo) for f in self.modelo.p.fluxos}
        n_antes = len(self.mensagens())

        estado = self.grafo.invoke({"messages": [HumanMessage(content=texto_usuario)]}, self.config)
        novas = estado["messages"][n_antes + 1:]

        acoes = [f"{m.name}: {texto_de(m)}" for m in novas if isinstance(m, ToolMessage)]
        falas = [texto_de(m).strip() for m in novas if isinstance(m, AIMessage) and texto_de(m).strip()]
        texto = falas[-1] if falas else "Pronto, atualizei o desenho. O que acontece em seguida?"

        depois = self.modelo.p.elementos
        alterados = [i for i, e in depois.items()
                     if antes.get(i) != (e.nome, e.tipo, e.responsavel, tuple(e.regras), e.descricao)]
        for f in self.modelo.p.fluxos:  # pontas de conexões novas/alteradas também
            if (f.origem, f.destino, f.rotulo) not in fluxos_antes:
                alterados += [f.id]
        return RespostaTurno(texto=texto, acoes=acoes, alterados=alterados)

    def desfazer(self) -> str:
        """Desfaz a última alteração do diagrama (sem passar pelo LLM) e regrava os arquivos."""
        resultado = self.modelo.desfazer()
        self.salvar()
        return resultado

    def mensagens(self) -> list[AnyMessage]:
        return self.grafo.get_state(self.config).values.get("messages", [])

    def historico_visivel(self) -> list[tuple[str, str]]:
        """(papel, texto) só das falas: esconde chamadas e resultados de ferramentas."""
        saida = []
        for m in self.mensagens():
            if isinstance(m, HumanMessage):
                saida.append(("user", texto_de(m)))
            elif isinstance(m, AIMessage) and texto_de(m).strip():
                saida.append(("assistant", texto_de(m)))
        return saida

    # ----------------------------------------------------------------- arquivos
    def bpmn_xml(self) -> str:
        return gerar_bpmn_xml(self.modelo)

    def salvar(self) -> None:
        salvar_artefatos(self.modelo, self.pasta)
