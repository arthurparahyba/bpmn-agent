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
