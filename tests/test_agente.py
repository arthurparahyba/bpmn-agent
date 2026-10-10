"""Testa o grafo LangGraph de ponta a ponta com um LLM roteirizado (sem chamar API)."""
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bpmn_agent.agente import Sessao, cortar_historico


class LLMRoteirizado(BaseChatModel):
    respostas: list
    vistos: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.vistos.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.respostas.pop(0))])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "roteirizado"


def chamada(nome, args, i):
    return {"name": nome, "args": args, "id": f"c{i}", "type": "tool_call"}


def test_turno_com_ferramentas_atualiza_diagrama(tmp_path):
    llm = LLMRoteirizado(respostas=[
        AIMessage(content="", tool_calls=[
            chamada("definir_processo", {"nome": "Compras"}, 1),
            chamada("adicionar_elemento", {"tipo": "tarefa_pessoa", "nome": "Solicitar compra",
                                           "responsavel": "Solicitante"}, 2),
            chamada("adicionar_elemento", {"tipo": "decisao", "nome": "Valor alto?",
                                           "responsavel": "Gestor", "depois_de": "Passo_1"}, 3),
            chamada("conectar", {"origem": "Nao_existe", "destino": "Passo_1"}, 4),  # erro proposital
        ]),
        AIMessage(content="Entendi! E se o valor for alto, o que acontece?"),
    ])
    s = Sessao(llm, pasta=tmp_path)
    r = s.enviar("Quero documentar o processo de compras. Começa com a solicitação.")

    assert r.texto == "Entendi! E se o valor for alto, o que acontece?"
    assert s.modelo.p.nome == "Compras"
    assert {"Inicio_1", "Passo_1", "Decisao_1"} <= set(s.modelo.p.elementos)
    assert any(a.startswith("conectar: ERRO") for a in r.acoes)
    assert "Decisao_1" in r.alterados
    assert (tmp_path / s.id / "processo.bpmn").exists()

    # a 2ª chamada ao LLM recebe o estado ATUALIZADO no prompt de sistema
    sistema = llm.vistos[1][0]
    assert isinstance(sistema, SystemMessage) and "Valor alto?" in sistema.content
    # a conversa enviada ao LLM sempre começa pelo usuário
    assert llm.vistos[0][1].type == "human"

    papeis = [p for p, _ in s.historico_visivel()]
    assert papeis == ["assistant", "user", "assistant"]


def test_desfazer_pelo_agente(tmp_path):
    llm = LLMRoteirizado(respostas=[
        AIMessage(content="", tool_calls=[chamada("adicionar_elemento", {"tipo": "tarefa", "nome": "A"}, 1)]),
        AIMessage(content="ok"),
        AIMessage(content="", tool_calls=[chamada("desfazer", {}, 2)]),
        AIMessage(content="Desfeito."),
    ])
    s = Sessao(llm, pasta=tmp_path)
    s.enviar("adiciona A")
    assert "Passo_1" in s.modelo.p.elementos
    s.enviar("desfaz")
    assert "Passo_1" not in s.modelo.p.elementos


def test_cortar_historico_comeca_em_mensagem_do_usuario():
    from langchain_core.messages import HumanMessage
    msgs = []
    for i in range(20):
        msgs += [HumanMessage(content=str(i)),
                 AIMessage(content="", tool_calls=[chamada("desfazer", {}, i)]),
                 ToolMessage(content="ok", tool_call_id=f"c{i}"), AIMessage(content="r")]
    cortado = cortar_historico(msgs, 5)
    assert isinstance(cortado[0], HumanMessage) and cortado[0].content == "15"
