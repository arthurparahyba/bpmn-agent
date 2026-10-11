"""
Agente em LangGraph.

    START -> agente --(pediu ferramentas?)--> ferramentas -> agente -> ... -> END

* O nó `agente` monta o prompt de sistema com o estado ATUAL do diagrama a cada chamada.
  Assim o LLM nunca trabalha com uma visão desatualizada, mesmo depois de muitas edições,
  e o histórico de mensagens pode ser cortado sem perder o diagrama.
* O nó `ferramentas` executa as chamadas em sequência (a ordem importa: criar um passo e
  depois conectá-lo) e transforma erros em mensagens que o LLM consegue corrigir.
* O histórico da conversa fica no checkpointer do LangGraph (por `thread_id`).

`sessao` é quem tem `.modelo` (o processo) e `.salvar()`; ver app/sessao.py.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from bpmn_agent.app.agente.ferramentas import criar_ferramentas
from bpmn_agent.app.agente.prompt import CONFIRMACAO_RECEBIDA, SYSTEM_PROMPT
from bpmn_agent.app.dominio import ErroModelo

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
        texto_sistema = SYSTEM_PROMPT.format(estado=sessao.modelo.resumo())
        if sessao.pedido_liberado:
            texto_sistema += CONFIRMACAO_RECEBIDA.format(pedido=sessao.pedido_liberado)
        sistema = SystemMessage(texto_sistema)
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
                if sessao.pendente and chamada["name"] != "pedir_confirmacao":
                    # a trava é do código, não do prompt: nada muda enquanto a pessoa não decidir
                    raise ErroModelo("Há um pedido aguardando confirmação da pessoa. Não altere o "
                                     "diagrama agora; apenas pergunte se ela confirma.")
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
