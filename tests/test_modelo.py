import xml.etree.ElementTree as ET

import pytest

from bpmn_agent.exportar_bpmn import gerar_bpmn_xml
from bpmn_agent.modelo import ErroModelo, ModeloProcesso

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def fluxo_basico() -> ModeloProcesso:
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa_pessoa", "Enviar pedido", "Funcionário")
    m.adicionar_elemento("tarefa_pessoa", "Analisar pedido", "Gestor", depois_de="Enviar pedido")
    m.adicionar_elemento("fim", "Pedido concluído", "Gestor", depois_de="Analisar pedido")
    return m


def arestas(m):
    return {(f.origem, f.destino) for f in m.p.fluxos}


def test_primeiro_passo_cria_inicio_automaticamente():
    m = fluxo_basico()
    assert m.p.elementos["Inicio_1"].tipo == "startEvent"
    assert ("Inicio_1", "Passo_1") in arestas(m)
    assert m.p.participantes == ["Funcionário", "Gestor"]
    assert m.problemas() == []


def test_inserir_no_meio_religa_o_fluxo():
    m = fluxo_basico()
    m.adicionar_elemento("tarefa_sistema", "Conferir limite", "Financeiro", depois_de="Passo_1")
    assert ("Passo_1", "Passo_3") in arestas(m)
    assert ("Passo_3", "Passo_2") in arestas(m)
    assert ("Passo_1", "Passo_2") not in arestas(m)


def test_decisao_com_caminhos_rotulados_e_volta():
    m = fluxo_basico()
    m.remover_elemento("Fim_1")
    m.adicionar_elemento("decisao", "Aprovado?", "Gestor", depois_de="Analisar pedido")
    m.adicionar_elemento("fim", "Pago", "Gestor", depois_de="Aprovado?", rotulo_conexao="Sim")
    m.adicionar_elemento("tarefa_pessoa", "Corrigir", "Funcionário", depois_de="Aprovado?", rotulo_conexao="Não")
    m.conectar("Corrigir", "Analisar pedido")
    rotulos = {(f.origem, f.destino): f.rotulo for f in m.p.fluxos}
    assert rotulos[("Decisao_1", "Fim_2")] == "Sim"
    assert rotulos[("Decisao_1", "Passo_3")] == "Não"
    assert m.problemas() == []


def test_remover_reconecta_e_desfazer_restaura():
    m = fluxo_basico()
    m.remover_elemento("Analisar pedido")
    assert ("Passo_1", "Fim_1") in arestas(m)
    assert "Passo_2" not in m.p.elementos
    m.desfazer()
    assert "Passo_2" in m.p.elementos
    assert ("Passo_1", "Passo_2") in arestas(m)


def test_mover_elemento_troca_ordem():
    m = fluxo_basico()
    m.adicionar_elemento("tarefa", "Arquivar", "Gestor", depois_de="Passo_2")  # Passo_2 -> Passo_3 -> Fim
    m.mover_elemento("Arquivar", "Passo_1")                                     # Passo_1 -> Passo_3 -> Passo_2
    assert ("Passo_1", "Passo_3") in arestas(m)
    assert ("Passo_3", "Passo_2") in arestas(m)
    assert ("Passo_2", "Fim_1") in arestas(m)


def test_resolver_por_nome_sem_acento_e_ambiguidade():
    m = fluxo_basico()
    assert m.resolver("analisar PEDIDO").id == "Passo_2"
    with pytest.raises(ErroModelo):
        m.resolver("pedido")  # ambíguo: 3 elementos contêm "pedido"


def test_fim_nao_tem_saida():
    m = fluxo_basico()
    with pytest.raises(ErroModelo):
        m.conectar("Fim_1", "Passo_1")


def test_renomear_participante_atualiza_passos():
    m = fluxo_basico()
    m.renomear_participante("gestor", "Coordenação")
    assert m.p.elementos["Passo_2"].responsavel == "Coordenação"


def test_problemas_apontam_pontas_soltas():
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa", "Receber", "A")
    m.adicionar_elemento("decisao", "Ok?", "A", depois_de="Receber")
    probs = " ".join(m.problemas())
    assert "como o processo termina" in probs
    assert "só tem um caminho" not in probs  # decisão ainda sem nenhuma saída
    assert "não sabemos o que acontece depois" in probs


def test_xml_estrutura_e_persistencia(tmp_path):
    m = fluxo_basico()
    m.adicionar_regra("Analisar pedido", "Prazo de 2 dias")
    raiz = ET.fromstring(gerar_bpmn_xml(m))
    proc = raiz.find("bpmn:process", NS)
    assert len(proc.findall("bpmn:userTask", NS)) == 2
    assert len(proc.findall("bpmn:sequenceFlow", NS)) == 3
    assert len(proc.findall("bpmn:laneSet/bpmn:lane", NS)) == 2
    doc = proc.find("bpmn:userTask[@id='Passo_2']/bpmn:documentation", NS).text
    assert "Prazo de 2 dias" in doc
    m.salvar(tmp_path / "p.json")
    m2 = ModeloProcesso.carregar(tmp_path / "p.json")
    assert gerar_bpmn_xml(m2) == gerar_bpmn_xml(m)


def test_xml_sem_participantes_nao_cria_raias():
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa", "Fazer algo")
    raiz = ET.fromstring(gerar_bpmn_xml(m))
    assert raiz.find("bpmn:process/bpmn:laneSet", NS) is None


def test_decisao_inicio_e_fim_sem_responsavel_herdam_a_raia():
    m = ModeloProcesso()
    m.adicionar_elemento("inicio", "Pedido recebido")
    m.adicionar_elemento("tarefa_pessoa", "Analisar pedido", "Gestor", depois_de="Inicio_1")
    m.adicionar_elemento("decisao", "Aprovado?", depois_de="Passo_1")
    m.adicionar_elemento("tarefa_pessoa", "Pagar", "Financeiro", depois_de="Decisao_1", rotulo_conexao="Sim")
    m.adicionar_elemento("fim", "Pago", depois_de="Passo_2")
    m.adicionar_elemento("fim", "Recusado", depois_de="Decisao_1", rotulo_conexao="Não")
    assert m.raia_de("Inicio_1") == "Gestor"       # sem ninguém antes: olha para frente
    assert m.raia_de("Decisao_1") == "Gestor"
    assert m.raia_de("Fim_1") == "Financeiro"
    assert m.raia_de("Fim_2") == "Gestor"
    assert m.problemas() == []
    assert "(sem responsável)" not in gerar_bpmn_xml(m)

    m.adicionar_elemento("tarefa", "Arquivar", depois_de="Passo_2")  # passo comum continua sendo cobrado
    assert m.raia_de("Passo_3") == ""
    assert any("sem responsável" in p for p in m.problemas())
    assert "(sem responsável)" in gerar_bpmn_xml(m)
