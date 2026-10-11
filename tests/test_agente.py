"""Testa o grafo LangGraph de ponta a ponta com um LLM roteirizado (sem chamar API)."""
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bpmn_agent.app.agente.grafo import cortar_historico
from bpmn_agent.app.sessao import Sessao


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

    assert r.texto.startswith("Entendi! E se o valor for alto, o que acontece?")
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


def _sessao_com_passo(tmp_path, *respostas):
    """Sessão com um passo 'Pagar imposto' já desenhado e o LLM roteirizado para o que vem depois."""
    llm = LLMRoteirizado(respostas=[
        AIMessage(content="", tool_calls=[chamada("adicionar_elemento", {
            "tipo": "tarefa_pessoa", "nome": "Pagar imposto", "responsavel": "Financeiro"}, 1)]),
        AIMessage(content="ok"),
        *respostas,
    ])
    s = Sessao(llm, pasta=tmp_path)
    s.enviar("o financeiro paga o imposto")
    return s, llm


DUVIDA = AIMessage(content="", tool_calls=[
    chamada("pedir_confirmacao", {"motivo": "Ninguém aprova o pagamento hoje",
                                  "pedido": "o advogado aprova o pagamento"}, 10),
    chamada("atualizar_elemento", {"id": "Passo_1", "nome": "Aprovar e pagar imposto"}, 11),  # deve ser barrada
])
PERGUNTA = AIMessage(content="Hoje ninguém aprova o pagamento. Você quer criar uma aprovação?")


def test_pedido_incoerente_fica_pendente_e_nao_altera_o_desenho(tmp_path):
    s, _ = _sessao_com_passo(tmp_path, DUVIDA, PERGUNTA)
    r = s.enviar("quem aprova o pagamento é o advogado")

    assert s.pendente == {"motivo": "Ninguém aprova o pagamento hoje", "pedido": "o advogado aprova o pagamento"}
    assert s.modelo.p.elementos["Passo_1"].nome == "Pagar imposto"
    assert any(a.startswith("atualizar_elemento: ERRO") for a in r.acoes)   # trava no código
    assert r.alterados == []
    assert "aprovação" in r.texto


def test_confirmar_aplica_o_pedido_guardado(tmp_path):
    aplica = AIMessage(content="", tool_calls=[chamada("atualizar_elemento", {
        "id": "Passo_1", "nome": "Aprovar e pagar imposto"}, 20)])
    s, llm = _sessao_com_passo(tmp_path, DUVIDA, PERGUNTA, aplica, AIMessage(content="Feito."))
    s.enviar("quem aprova o pagamento é o advogado")
    r = s.enviar("Sim!")

    assert s.pendente is None and s.pedido_liberado == ""
    assert s.modelo.p.elementos["Passo_1"].nome == "Aprovar e pagar imposto"
    assert r.texto.startswith("Feito.")
    # o prompt do turno da confirmação carrega o pedido original; os outros turnos não
    assert "o advogado aprova o pagamento" in llm.vistos[-2][0].content
    assert "Confirmação recebida" not in llm.vistos[0][0].content


def test_cancelar_descarta_sem_chamar_o_llm(tmp_path):
    s, llm = _sessao_com_passo(tmp_path, DUVIDA, PERGUNTA)   # nenhuma resposta sobrando: chamar o LLM falharia
    s.enviar("quem aprova o pagamento é o advogado")
    r = s.enviar("não")

    assert s.pendente is None
    assert s.modelo.p.elementos["Passo_1"].nome == "Pagar imposto"
    assert "não mudei nada" in r.texto


def test_outra_mensagem_descarta_a_pendencia_e_vira_pedido_novo(tmp_path):
    s, _ = _sessao_com_passo(tmp_path, DUVIDA, PERGUNTA, AIMessage(content="Entendi, o gerente aprova."))
    s.enviar("quem aprova o pagamento é o advogado")
    r = s.enviar("na verdade quem aprova é o gerente")

    assert s.pendente is None
    assert r.texto == "Entendi, o gerente aprova."


def test_nao_pede_confirmacao_de_novo_depois_de_confirmado(tmp_path):
    de_novo = AIMessage(content="", tool_calls=[chamada("pedir_confirmacao", {"motivo": "x", "pedido": "y"}, 30)])
    s, _ = _sessao_com_passo(tmp_path, DUVIDA, PERGUNTA, de_novo, AIMessage(content="ok"))
    s.enviar("quem aprova o pagamento é o advogado")
    r = s.enviar("confirmo")

    assert s.pendente is None
    assert any(a.startswith("pedir_confirmacao: ERRO") for a in r.acoes)


def test_resumo_mostra_que_so_a_descricao_mudou_mesmo_se_a_llm_diz_que_detalhou(tmp_path):
    so_descricao = AIMessage(content="", tool_calls=[chamada("atualizar_elemento", {
        "id": "Passo_1", "descricao": "cada fornecedor envia a sua proposta"}, 40)])
    s, _ = _sessao_com_passo(tmp_path, so_descricao, AIMessage(content="Pronto, detalhei a cotação em paralelo."))
    r = s.enviar("detalha a cotação em paralelo")

    assert r.texto.startswith("Pronto, detalhei a cotação em paralelo.")
    assert "O que mudou de fato no desenho: alterado(s): Pagar imposto (a descrição)." in r.texto
    assert "novo(s)" not in r.texto and "ligações" not in r.texto
    assert any("O que mudou de fato" in t for p, t in s.historico_visivel() if p == "assistant")   # a tela mostra


def test_resumo_lista_itens_novos_e_ligacoes(tmp_path):
    novo = AIMessage(content="", tool_calls=[
        chamada("adicionar_elemento", {"tipo": "tarefa", "nome": "Revisar", "depois_de": "Passo_1"}, 41)])
    s, _ = _sessao_com_passo(tmp_path, novo, AIMessage(content="Coloquei."))
    r = s.enviar("coloca revisar depois")

    assert "1 item(ns) novo(s): Revisar" in r.texto and "ligações: +1 / -0" in r.texto


def test_turno_sem_ferramentas_nao_ganha_resumo_e_a_llm_nao_ve_o_resumo(tmp_path):
    novo = AIMessage(content="", tool_calls=[chamada("adicionar_elemento", {"tipo": "tarefa", "nome": "Revisar"}, 42)])
    s, llm = _sessao_com_passo(tmp_path, novo, AIMessage(content="Coloquei."), AIMessage(content="Só uma conversa."))
    s.enviar("coloca revisar")
    r = s.enviar("obrigado")

    assert r.texto == "Só uma conversa." and "O que mudou" not in r.texto
    enviado = " ".join(str(m.content) for m in llm.vistos[-1])
    assert "Coloquei." in enviado and "O que mudou de fato" not in enviado     # a LLM não vê o resumo


def test_pedido_em_duvida_mostra_que_nada_mudou(tmp_path):
    s, _ = _sessao_com_passo(tmp_path, DUVIDA, PERGUNTA)
    r = s.enviar("quem aprova o pagamento é o advogado")

    assert "O que mudou de fato no desenho: nada." in r.texto


def test_estado_no_fim_deixa_o_comeco_estavel_e_manda_o_diagrama_na_ultima_mensagem(tmp_path):
    novo = AIMessage(content="", tool_calls=[chamada("adicionar_elemento", {"tipo": "tarefa", "nome": "Revisar"}, 50)])
    llm = LLMRoteirizado(respostas=[novo, AIMessage(content="Coloquei.")])
    s = Sessao(llm, pasta=tmp_path, estado_no_fim=True)
    s.enviar("coloca revisar")

    primeira, segunda = llm.vistos[0], llm.vistos[1]
    assert "Elementos:" not in primeira[0].content and "Elementos:" not in segunda[0].content   # prompt sem o diagrama
    assert primeira[0].content == segunda[0].content                                              # começo idêntico
    assert primeira[-1].type == "human" and "[ESTADO ATUAL" in primeira[-1].content
    assert "Revisar" in segunda[-1].content and "Revisar" not in primeira[-1].content            # estado fresco a cada chamada
    assert not any("[ESTADO ATUAL" in str(m.content) for m in s.mensagens())                      # não vai para o histórico


def test_cortar_historico_comeca_em_mensagem_do_usuario():
    from langchain_core.messages import HumanMessage
    msgs = []
    for i in range(20):
        msgs += [HumanMessage(content=str(i)),
                 AIMessage(content="", tool_calls=[chamada("desfazer", {}, i)]),
                 ToolMessage(content="ok", tool_call_id=f"c{i}"), AIMessage(content="r")]
    cortado = cortar_historico(msgs, 5)
    assert isinstance(cortado[0], HumanMessage) and cortado[0].content == "15"
