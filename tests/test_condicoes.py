"""Condição estruturada (campo, op, valor, ação), catálogo de dados e aviso de volta para dentro de paralelo."""
import pytest

from bpmn_agent.app.dominio import ErroModelo, ModeloProcesso
from bpmn_agent.app.dominio.textos import resumo_mudancas  # noqa: F401  (garante o import do módulo de textos)


def com_passo() -> ModeloProcesso:
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa_pessoa", "Calcular imposto", "Financeiro")
    return m


@pytest.mark.parametrize("texto, esperado", [
    ("60 dias", (60, "dias")), ("R$ 1 milhão", (1_000_000, "BRL")), ("R$ 500 mil", (500_000, "BRL")),
    ("4%", (4, "%")), ("18", (18, "")), ("2,5 mil", (2500, "")), ("1.500.000", (1_500_000, "")),
    ("1 milhão de reais", (1_000_000, "BRL")), ("3 dias úteis", (3, "dias úteis")), ("aprovado", ("aprovado", "")),
])
def test_valor_e_separado_em_numero_e_unidade(texto, esperado):
    assert ModeloProcesso._valor_unidade(texto) == esperado


def test_regra_com_condicao_guarda_texto_condicao_e_dado_no_catalogo():
    m = com_passo()
    r = m.adicionar_regra("Passo_1", "Se passar de 60 dias, multa de 10%", campo="tempo desde a abertura",
                          op=">", valor="60 dias", acao="aplicar multa de 10%")
    e = m.p.elementos["Passo_1"]
    assert "quando tempo desde a abertura > 60 dias" in r
    c = e.condicoes[0]
    assert (c.campo, c.op, c.valor, c.unidade, c.regra) == ("tempo desde a abertura", ">", 60, "dias",
                                                           "Se passar de 60 dias, multa de 10%")
    assert [d.nome for d in m.p.dados] == ["tempo desde a abertura"]
    assert "regra 1: Se passar de 60 dias, multa de 10% [quando tempo desde a abertura > 60 dias → aplicar multa de 10%]" in m.resumo()
    assert "Dados usados nas condições" in m.resumo()


def test_campo_com_outra_grafia_reaproveita_o_dado_do_catalogo_e_aceita_alias_de_operador():
    m = com_passo()
    m.adicionar_regra("Passo_1", "a", campo="Valor total dos bens", op="≥", valor="R$ 1 milhão")
    m.adicionar_regra("Passo_1", "b", campo="valor total dos bens", op="<", valor="R$ 1 milhão")
    assert [d.nome for d in m.p.dados] == ["Valor total dos bens"]
    assert [c.op for c in m.p.elementos["Passo_1"].condicoes] == [">=", "<"]
    assert m.p.elementos["Passo_1"].condicoes[0].unidade == "BRL"


def test_condicao_incompleta_ou_operador_invalido_e_recusada_sem_alterar_nada():
    m = com_passo()
    with pytest.raises(ErroModelo, match="juntos"):
        m.adicionar_regra("Passo_1", "x", campo="idade", op="<")
    with pytest.raises(ErroModelo, match="Operador"):
        m.adicionar_regra("Passo_1", "x", campo="idade", op="parecido", valor="3")
    assert m.p.elementos["Passo_1"].regras == [] and m.p.dados == []


def test_regra_sem_condicao_continua_so_em_texto_e_remover_regra_remove_a_condicao():
    m = com_passo()
    m.adicionar_regra("Passo_1", "O contrato precisa ser revisado")
    m.adicionar_regra("Passo_1", "Menor de 18 exige assinatura", campo="idade", op="<", valor="18", acao="exigir")
    e = m.p.elementos["Passo_1"]
    assert len(e.regras) == 2 and len(e.condicoes) == 1
    m.remover_regra("Passo_1", 2)
    assert e.condicoes == [] and len(e.regras) == 1


def test_condicoes_vao_para_json_bpmn_e_arquivo_antigo_continua_abrindo():
    import xml.etree.ElementTree as ET

    from bpmn_agent.app.exportacao.exportar_bpmn import gerar_bpmn_xml
    m = com_passo()
    m.adicionar_regra("Passo_1", "Alíquota de 4%", campo="alíquota do ITCMD", op="=", valor="4%", acao="calcular")
    d = m.para_dict()
    assert d["elementos"]["Passo_1"]["condicoes"][0]["unidade"] == "%" and d["dados"][0]["nome"] == "alíquota do ITCMD"
    c = ModeloProcesso.de_dict(d).p.elementos["Passo_1"].condicoes[0]
    assert (c.valor, c.unidade) == (4, "%")
    ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
    doc = ET.fromstring(gerar_bpmn_xml(m)).find(".//bpmn:userTask/bpmn:documentation", ns).text
    assert "Regra: Alíquota de 4% (quando alíquota do ITCMD = 4 % → calcular)" in doc
    for e in d["elementos"].values():
        e.pop("condicoes")
    d.pop("dados")
    assert ModeloProcesso.de_dict(d).p.elementos["Passo_1"].condicoes == []


def _levantamento(volta_para: str) -> ModeloProcesso:
    m = ModeloProcesso()
    m.adicionar_elemento("tarefa", "Abrir", "A")
    m.adicionar_elemento("paralelo", "Iniciar levantamentos", depois_de="Abrir")
    m.adicionar_elemento("tarefa", "Consultar saldos", "A", depois_de="Iniciar levantamentos")
    m.adicionar_elemento("tarefa", "Entregar documentos", "B", depois_de="Iniciar levantamentos")
    m.adicionar_elemento("paralelo", "Aguardar levantamentos", depois_de="Consultar saldos")
    m.conectar("Entregar documentos", "Aguardar levantamentos")
    m.adicionar_elemento("tarefa", "Consolidar", "A", depois_de="Aguardar levantamentos")
    m.adicionar_elemento("decisao", "Falta documento?", "A", depois_de="Consolidar")
    m.adicionar_elemento("tarefa", "Pedir documentos", "A", depois_de="Falta documento?", rotulo_conexao="Sim")
    m.conectar("Pedir documentos", volta_para)
    m.adicionar_elemento("fim", "Fim", depois_de="Falta documento?", rotulo_conexao="Não")
    return m


def test_volta_para_dentro_de_um_ramo_paralelo_vira_ponto_em_aberto_e_para_o_inicio_do_bloco_nao():
    avisos = [x for x in _levantamento("Entregar documentos").problemas() if "ao mesmo tempo" in x]
    assert len(avisos) == 1 and "'Pedir documentos' volta para dentro" in avisos[0] and "'Iniciar levantamentos'" in avisos[0]
    assert not [x for x in _levantamento("Iniciar levantamentos").problemas() if "ao mesmo tempo" in x]
