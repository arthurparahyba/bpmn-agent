"""Catálogo de sistemas: cadastro, uso nos passos, separação de participantes e saídas."""
import xml.etree.ElementTree as ET

import pytest

from bpmn_agent.app.dominio import ErroModelo, ModeloProcesso
from bpmn_agent.app.exportacao.exportar_bpmn import gerar_bpmn_xml
from bpmn_agent.app.persistencia import carregar_modelo, salvar_modelo

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def com_core() -> ModeloProcesso:
    m = ModeloProcesso()
    m.cadastrar_sistema("Core Bancário", "Contas e saldos", "API REST", "POST /contas; GET /saldo")
    m.adicionar_elemento("tarefa_sistema", "Abrir conta", "Backoffice", sistema="core bancario",
                         operacao="POST /contas")
    return m


def test_cadastrar_e_completar_sistema_sem_duplicar():
    m = com_core()
    m.cadastrar_sistema("CORE BANCÁRIO", operacoes="POST /contas; PUT /contas")
    assert [s.nome for s in m.p.sistemas] == ["Core Bancário"]
    s = m.p.sistemas[0]
    assert s.descricao == "Contas e saldos" and s.integracao == "API REST"       # campos vazios não apagam
    assert s.operacoes == ["POST /contas", "GET /saldo", "PUT /contas"]          # sem repetir


def test_passo_usa_o_nome_canonico_e_aprende_a_operacao():
    m = com_core()
    e = m.p.elementos["Passo_1"]
    assert e.sistema == "Core Bancário" and e.operacao == "POST /contas"
    m.adicionar_elemento("tarefa_sistema", "Consultar saldo", "Backoffice", depois_de="Passo_1",
                         sistema="Core Bancário", operacao="GET /extrato")
    assert "GET /extrato" in m.p.sistemas[0].operacoes


def test_sistema_novo_citado_no_passo_e_cadastrado_sozinho():
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa_sistema", "Consultar score", "Crédito", sistema="Serasa")
    assert [s.nome for s in m.p.sistemas] == ["Serasa"]


def test_sistema_nao_pode_ser_responsavel_nem_participante():
    m = com_core()
    with pytest.raises(ErroModelo, match="sistema do catálogo"):
        m.adicionar_elemento("tarefa", "Conferir", "Core Bancário")
    with pytest.raises(ErroModelo, match="sistema do catálogo"):
        m.atualizar_elemento("Passo_1", responsavel="Core Bancário")
    with pytest.raises(ErroModelo, match="sistema do catálogo"):
        m.adicionar_participante("Core Bancário")
    assert "Core Bancário" not in m.p.participantes


def test_participante_nao_pode_virar_sistema():
    m = ModeloProcesso()
    m.adicionar_participante("Financeiro")
    with pytest.raises(ErroModelo, match="já é um participante"):
        m.cadastrar_sistema("Financeiro")
    with pytest.raises(ErroModelo, match="já é um participante"):
        m.adicionar_elemento("tarefa_sistema", "Pagar", sistema="financeiro")


def test_atualizar_e_tirar_sistema_do_passo():
    m = com_core()
    m.atualizar_elemento("Passo_1", sistema="Serasa", operacao="GET /score")
    e = m.p.elementos["Passo_1"]
    assert (e.sistema, e.operacao) == ("Serasa", "GET /score")
    m.atualizar_elemento("Passo_1", sistema="nenhum")
    assert (e.sistema, e.operacao) == ("", "")
    with pytest.raises(ErroModelo, match="Informe o `sistema`"):
        m.atualizar_elemento("Passo_1", operacao="GET /x")


def test_remover_sistema_limpa_os_passos_e_da_para_desfazer():
    m = com_core()
    r = m.remover_sistema("Core Bancário")
    assert "Abrir conta" in r and m.p.sistemas == [] and m.p.elementos["Passo_1"].sistema == ""
    m.desfazer()
    assert m.p.elementos["Passo_1"].sistema == "Core Bancário" and len(m.p.sistemas) == 1


def test_pontos_em_aberto_de_sistemas():
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa_sistema", "Calcular juros", "Crédito")
    m.cadastrar_sistema("SAP")
    probs = " ".join(m.problemas())
    assert "Calcular juros" in probs and "em qual sistema" in probs
    assert "'SAP' está cadastrado, mas nenhum passo o usa" in probs


def test_resumo_narrativa_e_bpmn_mostram_o_sistema():
    m = com_core()
    assert "Sistemas (não são participantes):" in m.resumo() and "sistema: Core Bancário (POST /contas)" in m.resumo()
    assert "**Sistemas:**" in m.narrativa() and "Sistema: Core Bancário — POST /contas" in m.narrativa()
    raiz = ET.fromstring(gerar_bpmn_xml(m))
    no = raiz.find(".//bpmn:serviceTask", NS)
    assert "Sistema: Core Bancário — POST /contas" in no.find("bpmn:documentation", NS).text


def test_json_guarda_e_carrega_sistemas_e_aceita_arquivo_antigo(tmp_path):
    m = com_core()
    salvar_modelo(m, tmp_path / "p.json")
    c = carregar_modelo(tmp_path / "p.json")
    assert c.p.sistemas[0].operacoes == ["POST /contas", "GET /saldo"] and c.p.elementos["Passo_1"].sistema == "Core Bancário"
    antigo = m.para_dict()
    antigo.pop("sistemas")
    for e in antigo["elementos"].values():
        e.pop("sistema"), e.pop("operacao")
    assert ModeloProcesso.de_dict(antigo).p.sistemas == []


def test_renomear_sistema_atualiza_os_passos_e_recusa_conflitos():
    m = com_core()
    m.cadastrar_sistema("Serasa")
    m.renomear_sistema("core bancario", "Core Banking")
    assert m.p.elementos["Passo_1"].sistema == "Core Banking" and [s.nome for s in m.p.sistemas][0] == "Core Banking"
    with pytest.raises(ErroModelo, match="Já existe um sistema"):
        m.renomear_sistema("Core Banking", "serasa")
    m.adicionar_participante("Backoffice")
    with pytest.raises(ErroModelo, match="já é um participante"):
        m.renomear_sistema("Serasa", "Backoffice")
    assert [s.nome for s in m.p.sistemas] == ["Core Banking", "Serasa"]   # as tentativas recusadas não mudaram nada
    m.renomear_sistema("Serasa", "Bureau")
    m.desfazer()
    assert [s.nome for s in m.p.sistemas] == ["Core Banking", "Serasa"]


def test_resumo_avisa_sistema_deduzido_que_a_pessoa_nao_citou():
    from bpmn_agent.app.dominio.textos import assinatura, resumo_mudancas
    m = com_core()
    antes = {i: assinatura(e) for i, e in m.p.elementos.items()}
    m.adicionar_elemento("tarefa_sistema", "Enviar confirmação", "Backoffice", depois_de="Passo_1",
                         sistema="Core Bancário")
    dito = resumo_mudancas(antes, set(), m, texto_usuario="depois o core bancário envia a confirmação")
    deduzido = resumo_mudancas(antes, set(), m, texto_usuario="depois o sistema envia a confirmação")
    sem_texto = resumo_mudancas(antes, set(), m)
    assert "deduzido" not in dito and "deduzido" not in sem_texto
    assert "sistema deduzido, não dito por você (confirme): Core Bancário em Enviar confirmação" in deduzido


def test_bpmn_mostra_o_sistema_na_segunda_linha_do_passo_mas_so_em_tarefas():
    m = com_core()
    m.adicionar_elemento("fim", "Fim", depois_de="Passo_1")
    raiz = ET.fromstring(gerar_bpmn_xml(m))
    assert raiz.find(".//bpmn:serviceTask", NS).get("name") == "Abrir conta\n[Core Bancário]"
    assert raiz.find(".//bpmn:endEvent", NS).get("name") == "Fim"
    assert m.p.elementos["Passo_1"].nome == "Abrir conta"      # o nome no modelo não é alterado


def _lanes(m):
    raiz = ET.fromstring(gerar_bpmn_xml(m))
    return [l.get("name") for l in raiz.findall(".//bpmn:lane", NS)], raiz


def test_passo_automatico_sem_responsavel_num_sistema_da_empresa_vai_para_a_raia_do_sistema():
    m = ModeloProcesso()
    m.adicionar_participante("Cliente")
    m.cadastrar_sistema("CAOS REGISTER")
    m.adicionar_elemento("tarefa_pessoa", "Registrar", "Cliente")
    m.adicionar_elemento("tarefa_sistema", "Gerar resumo", "", depois_de="Registrar", sistema="CAOS REGISTER")
    m.adicionar_elemento("fim", "Pronto", depois_de="Gerar resumo")
    assert m.raia_de("Passo_2") == "CAOS REGISTER" and m.raia_de("Fim_1") == "CAOS REGISTER"   # o fim herda
    assert not any("sem responsável" in x for x in m.problemas())
    assert "CAOS REGISTER" not in m.p.participantes                                           # não vira participante
    nomes, _ = _lanes(m)
    assert nomes == ["Cliente", "CAOS REGISTER"]


def test_sistema_de_terceiros_vira_caixa_separada_com_seta_de_mensagem():
    m = ModeloProcesso()
    m.adicionar_participante("Cliente")
    m.cadastrar_sistema("OpenAI", externo="sim")
    m.adicionar_elemento("tarefa_sistema", "Priorizar", "Cliente", sistema="OpenAI")
    nomes, raiz = _lanes(m)
    assert nomes == ["Cliente"]                                                  # nenhuma raia nova
    partes = {p.get("name") for p in raiz.findall(".//bpmn:participant", NS)}
    assert "OpenAI" in partes
    msg = raiz.find(".//bpmn:messageFlow", NS)
    assert msg.get("sourceRef") == "Passo_1" and msg.get("targetRef").startswith("Participant_")
    assert "OpenAI" in m.resumo() and "externo" in m.resumo()


def test_passo_em_sistema_de_terceiros_sem_responsavel_continua_pedindo_responsavel():
    m = ModeloProcesso()
    m.adicionar_participante("Cliente")
    m.cadastrar_sistema("OpenAI", externo="sim")
    m.adicionar_elemento("tarefa_sistema", "Priorizar", "", sistema="OpenAI")
    assert any("sem responsável" in x for x in m.problemas())


def test_externo_pode_ser_mudado_e_arquivo_antigo_abre_como_interno():
    m = com_core()
    assert m.p.sistemas[0].externo is False
    m.cadastrar_sistema("Core Bancário", externo="sim")
    assert m.p.sistemas[0].externo is True
    m.cadastrar_sistema("Core Bancário", externo="nao")
    assert m.p.sistemas[0].externo is False
    d = m.para_dict()
    d["sistemas"][0].pop("externo")
    assert ModeloProcesso.de_dict(d).p.sistemas[0].externo is False


def _delivery():
    m = ModeloProcesso()
    m.adicionar_participante("Cliente")
    m.cadastrar_sistema("App Delivery")
    m.cadastrar_sistema("Gateway de Pagamento", externo="sim")
    m.adicionar_elemento("tarefa_pessoa", "Fazer pedido", "Cliente", sistema="App Delivery")
    m.adicionar_elemento("tarefa_sistema", "Cobrar cartão", "", depois_de="Fazer pedido",
                         sistema="App Delivery", chama="Gateway de Pagamento", operacao="POST /cobrancas")
    return m


def test_passo_executado_no_app_chamando_o_gateway_fica_na_raia_do_app_com_seta_para_o_gateway():
    m = _delivery()
    e = m.p.elementos["Passo_2"]
    assert (e.sistema, e.chama, e.operacao) == ("App Delivery", "Gateway de Pagamento", "POST /cobrancas")
    assert m.raia_de("Passo_2") == "App Delivery"
    assert not any("sem responsável" in x for x in m.problemas())            # o falso aviso some
    assert m.p.sistemas[1].operacoes == ["POST /cobrancas"]                    # a operação é do sistema chamado
    nomes, raiz = _lanes(m)
    assert nomes == ["Cliente", "App Delivery"]
    msg = raiz.find(".//bpmn:messageFlow", NS)
    assert msg.get("sourceRef") == "Passo_2"
    alvo = [p for p in raiz.findall(".//bpmn:participant", NS) if p.get("id") == msg.get("targetRef")][0]
    assert alvo.get("name") == "Gateway de Pagamento"
    assert raiz.find(".//bpmn:serviceTask", NS).get("name") == "Cobrar cartão\n[App Delivery → Gateway de Pagamento]"


def test_chama_aparece_no_resumo_e_no_resumo_de_mudancas_e_acompanha_renomear_e_remover():
    from bpmn_agent.app.dominio.textos import assinatura, resumo_mudancas
    m = _delivery()
    assert "sistema: App Delivery | chama: Gateway de Pagamento (POST /cobrancas)" in m.resumo()
    antes = {i: assinatura(e) for i, e in m.p.elementos.items()}
    m.atualizar_elemento("Passo_2", chama="nenhum")
    assert "o sistema chamado" in resumo_mudancas(antes, set(), m)
    m.atualizar_elemento("Passo_2", chama="Gateway de Pagamento")
    m.renomear_sistema("Gateway de Pagamento", "Pagar.me")
    assert m.p.elementos["Passo_2"].chama == "Pagar.me"
    m.remover_sistema("Pagar.me")
    assert m.p.elementos["Passo_2"].chama == ""


def test_dois_passos_com_a_mesma_chamada_viram_ponto_em_aberto():
    m = _delivery()
    m.adicionar_elemento("tarefa_sistema", "Reembolsar", "", depois_de="Cobrar cartão",
                         sistema="App Delivery", chama="Gateway de Pagamento", operacao="POST /reembolsos")
    assert not any("mesma chamada" in x for x in m.problemas())
    m.adicionar_elemento("tarefa_sistema", "Reembolsar por prazo", "", depois_de="Reembolsar",
                         sistema="App Delivery", chama="Gateway de Pagamento", operacao="post /reembolsos")
    achados = [x for x in m.problemas() if "mesma chamada" in x]
    assert len(achados) == 1 and "'Reembolsar' e 'Reembolsar por prazo'" in achados[0]


def test_aviso_de_conclusao_tambem_vale_quando_a_fala_so_pergunta_se_esta_correto():
    from bpmn_agent.app.dominio.textos import aviso_de_conclusao
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa", "A")
    m.adicionar_elemento("tarefa", "B", depois_de="A")
    assert aviso_de_conclusao(m, "Fechei o fluxo. Está correto ou quer mudar algum passo?") != ""
    assert aviso_de_conclusao(m, "Quem faz o passo B?") == ""
