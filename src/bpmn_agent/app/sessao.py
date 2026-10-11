"""
Sessao: a porta de entrada do backend para as interfaces.

Uma conversa = um processo + um thread no LangGraph + arquivos salvos em disco.
A API conversa só com esta classe: envia o texto do usuário e recebe um RespostaTurno.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from bpmn_agent.app.agente.grafo import LIMITE_PASSOS_GRAFO, construir_grafo, texto_de
from bpmn_agent.app.agente.prompt import SAUDACAO
from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.dominio.processo import _normalizar
from bpmn_agent.app.dominio.textos import MARCADOR_MUDANCAS, assinatura, resumo_mudancas
from bpmn_agent.app.exportacao.exportar_bpmn import gerar_bpmn_xml
from bpmn_agent.app.persistencia import salvar_artefatos

# Respostas que valem como comando quando há uma alteração aguardando confirmação.
# Qualquer outra mensagem descarta a pendência e é tratada como um pedido novo.
CONFIRMACOES = {"sim", "s", "confirmo", "confirmar", "confirmado", "pode", "pode sim", "pode aplicar",
                "aplica", "aplicar", "isso", "isso mesmo", "ok", "claro"}
CANCELAMENTOS = {"nao", "n", "cancelar", "cancela", "cancelado", "deixa", "deixa pra la", "esquece",
                 "ignora", "nao precisa", "nao quero"}


def _comando(texto: str) -> str:
    return _normalizar(re.sub(r"[^\w\s]", "", texto or ""))


@dataclass
class RespostaTurno:
    texto: str
    acoes: list[str] = field(default_factory=list)        # resultados das ferramentas (para depuração/UI)
    alterados: list[str] = field(default_factory=list)    # ids criados/alterados (destaque no desenho)


class Sessao:
    """Uma conversa = um processo + um thread no LangGraph + arquivos salvos em disco."""

    def __init__(self, llm: BaseChatModel, pasta: str | Path = "sessoes",
                 modelo: ModeloProcesso | None = None, id: str | None = None, estado_no_fim: bool = False):
        self.id = id or uuid.uuid4().hex[:8]
        self.pasta = Path(pasta) / self.id
        self.modelo = modelo or ModeloProcesso()
        self.checkpointer = MemorySaver()
        # Alteração que o agente achou incoerente com o desenho: fica guardada, sem ser aplicada,
        # até a pessoa confirmar ou cancelar. `pedido_liberado` vale só durante o turno da confirmação.
        self.pendente: dict[str, str] | None = None
        self.pedido_liberado: str = ""
        self.grafo = construir_grafo(llm, self, self.checkpointer, estado_no_fim)
        self.config = {"configurable": {"thread_id": self.id}, "recursion_limit": LIMITE_PASSOS_GRAFO}
        saudacao = SAUDACAO if not self.modelo.p.elementos else (
            f"Oi de novo! Carreguei o processo **{self.modelo.p.nome}**. "
            "Quer continuar de onde paramos ou mudar alguma coisa?")
        self.grafo.update_state(self.config, {"messages": [AIMessage(content=saudacao)]}, as_node="agente")

    # ----------------------------------------------------------------- conversa
    def pedir_confirmacao(self, motivo: str, pedido: str) -> str:
        """Guarda um pedido incoerente sem aplicá-lo. Chamada pela ferramenta `pedir_confirmacao`."""
        if self.pedido_liberado:
            return "ERRO: a pessoa já confirmou este pedido. Aplique-o agora com as ferramentas de edição."
        if not motivo.strip() or not pedido.strip():
            return "ERRO: informe o motivo da dúvida e o pedido original da pessoa."
        self.pendente = {"motivo": motivo.strip(), "pedido": pedido.strip()}
        return ("Nada foi alterado. Explique à pessoa, em uma frase simples, o que não bateu com o desenho "
                "e pergunte se é isso mesmo que ela quer. Não use mais ferramentas neste turno.")

    def enviar(self, texto_usuario: str) -> RespostaTurno:
        if self.pendente:
            pend, self.pendente = self.pendente, None
            comando = _comando(texto_usuario)
            if comando in CANCELAMENTOS:
                return RespostaTurno(texto="Tudo bem, não mudei nada. O que acontece em seguida?")
            if comando in CONFIRMACOES:
                self.pedido_liberado = pend["pedido"]
        try:
            return self._enviar(texto_usuario)
        finally:
            self.pedido_liberado = ""

    def _enviar(self, texto_usuario: str) -> RespostaTurno:
        antes = {i: assinatura(e) for i, e in self.modelo.p.elementos.items()}
        fluxos_antes = {(f.origem, f.destino, f.rotulo) for f in self.modelo.p.fluxos}
        n_antes = len(self.mensagens())

        estado = self.grafo.invoke({"messages": [HumanMessage(content=texto_usuario)]}, self.config)
        novas = estado["messages"][n_antes + 1:]

        acoes = [f"{m.name}: {texto_de(m)}" for m in novas if isinstance(m, ToolMessage)]
        falas = [texto_de(m).strip() for m in novas if isinstance(m, AIMessage) and texto_de(m).strip()]
        texto = falas[-1] if falas else "Pronto, atualizei o desenho. O que acontece em seguida?"
        if acoes:   # houve ferramentas: o código confere e mostra o que mudou de fato, sem confiar na fala da LLM
            texto = self._anexar_mudancas(estado["messages"], texto,
                                          resumo_mudancas(antes, fluxos_antes, self.modelo, texto_usuario=texto_usuario))

        depois = self.modelo.p.elementos
        alterados = [i for i, e in depois.items()
                     if antes.get(i) != assinatura(e)]
        for f in self.modelo.p.fluxos:  # pontas de conexões novas/alteradas também
            if (f.origem, f.destino, f.rotulo) not in fluxos_antes:
                alterados += [f.id]
        return RespostaTurno(texto=texto, acoes=acoes, alterados=alterados)

    def _anexar_mudancas(self, mensagens: list[AnyMessage], texto: str, resumo: str) -> str:
        """Grava o resumo no fim da última fala do agente (é o que a tela mostra no histórico)."""
        completo = texto + MARCADOR_MUDANCAS + resumo
        ultima = mensagens[-1]
        if isinstance(ultima, AIMessage) and texto_de(ultima).strip():
            nova = AIMessage(id=ultima.id, content=texto_de(ultima).rstrip() + MARCADOR_MUDANCAS + resumo)
        else:   # a LLM só chamou ferramentas e não falou: o resumo vira a própria fala
            nova = AIMessage(content=completo)
        self.grafo.update_state(self.config, {"messages": [nova]}, as_node="agente")
        return completo

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
