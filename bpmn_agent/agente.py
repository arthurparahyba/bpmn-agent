"""
Agente em LangGraph.

    START -> agente --(pediu ferramentas?)--> ferramentas -> agente -> ... -> END

* O nó `agente` monta o prompt de sistema com o estado ATUAL do diagrama a cada chamada.
  Assim o LLM nunca trabalha com uma visão desatualizada, mesmo depois de muitas edições,
  e o histórico de mensagens pode ser cortado sem perder o diagrama.
* O nó `ferramentas` executa as chamadas em sequência (a ordem importa: criar um passo e
  depois conectá-lo) e transforma erros em mensagens que o LLM consegue corrigir.
* O histórico da conversa fica no checkpointer do LangGraph (por `thread_id`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from .exportar_bpmn import gerar_bpmn_xml
from .ferramentas import criar_ferramentas
from .modelo import ErroModelo, ModeloProcesso
from .prompt import SAUDACAO, SYSTEM_PROMPT

MAX_TURNOS_HISTORICO = 14   # turnos do usuário mantidos no contexto (o diagrama vai sempre inteiro)
LIMITE_PASSOS_GRAFO = 60    # proteção contra loops de ferramentas


def texto_de(msg: AnyMessage) -> str:
    """Extrai texto de mensagens cujo conteúdo pode vir como string ou lista de blocos."""
    c = msg.content
    if isinstance(c, str):
        return c
    partes = []
    for b in c or []:
        if isinstance(b, str):
            partes.append(b)
        elif isinstance(b, dict) and b.get("type") == "text":
            partes.append(b.get("text", ""))
    return "".join(partes)


def cortar_historico(msgs: list[AnyMessage], max_turnos: int = MAX_TURNOS_HISTORICO) -> list[AnyMessage]:
    """Mantém só os últimos N turnos, sempre começando numa mensagem do usuário
    (nunca separa uma chamada de ferramenta do seu resultado)."""
    idx_humanos = [i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)]
    if len(idx_humanos) <= max_turnos:
        return msgs
    return msgs[idx_humanos[-max_turnos]:]


def construir_grafo(llm: BaseChatModel, sessao, checkpointer=None):
    ferramentas = criar_ferramentas(sessao)
    por_nome = {t.name: t for t in ferramentas}
    llm_com_ferramentas = llm.bind_tools(ferramentas)

    def agente(state: MessagesState):
        sistema = SystemMessage(SYSTEM_PROMPT.format(estado=sessao.modelo.resumo()))
        historico = cortar_historico(state["messages"])
        if historico and not isinstance(historico[0], HumanMessage):
            # alguns provedores (Anthropic, Gemini) exigem que a conversa comece pelo usuário
            historico = [HumanMessage(content="(início da conversa)"), *historico]
        resposta = llm_com_ferramentas.invoke([sistema, *historico])
        return {"messages": [resposta]}

    def executar_ferramentas(state: MessagesState):
        ultima = state["messages"][-1]
        saidas = []
        for chamada in ultima.tool_calls:
            ferramenta = por_nome.get(chamada["name"])
            try:
                if ferramenta is None:
                    raise ErroModelo(f"Ferramenta '{chamada['name']}' não existe.")
                resultado = ferramenta.invoke(chamada["args"])
            except ErroModelo as e:
                resultado = f"ERRO: {e}"
            except Exception as e:  # argumentos inválidos etc.
                resultado = f"ERRO ao chamar {chamada['name']}: {e}"
            saidas.append(ToolMessage(content=str(resultado), tool_call_id=chamada["id"], name=chamada["name"]))
        sessao.salvar()
        return {"messages": saidas}

    def rotear(state: MessagesState):
        ultima = state["messages"][-1]
        return "ferramentas" if getattr(ultima, "tool_calls", None) else END

    g = StateGraph(MessagesState)
    g.add_node("agente", agente)
    g.add_node("ferramentas", executar_ferramentas)
    g.add_edge(START, "agente")
    g.add_conditional_edges("agente", rotear, {"ferramentas": "ferramentas", END: END})
    g.add_edge("ferramentas", "agente")
    return g.compile(checkpointer=checkpointer or MemorySaver())


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

    def trocar_llm(self, llm: BaseChatModel) -> None:
        """Troca o modelo no meio da conversa, mantendo histórico e diagrama."""
        self.grafo = construir_grafo(llm, self, self.checkpointer)

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
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.modelo.salvar(self.pasta / "processo.json")
        (self.pasta / "processo.bpmn").write_text(self.bpmn_xml(), encoding="utf-8")
        (self.pasta / "processo.md").write_text(self.modelo.narrativa(), encoding="utf-8")
