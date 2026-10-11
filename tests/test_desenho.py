"""Desenho do BPMN: setas que desviam de elementos, rótulos sem sobreposição e cores dos sistemas de terceiros."""
import xml.etree.ElementTree as ET

from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.exportacao.exportar_bpmn import _cruza, calcular_layout, gerar_bpmn_xml

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL", "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
      "dc": "http://www.omg.org/spec/DD/20100524/DC", "di": "http://www.omg.org/spec/DD/20100524/DI"}
BIOC = "{http://bpmn.io/schema/bpmn/biocolor/1.0}stroke"


def decisoes_encadeadas() -> ModeloProcesso:
    """Três decisões em sequência, duas saídas da mesma decisão para o mesmo lado e dois elementos na mesma linha
    com um terceiro no meio (os casos em que as setas atravessavam elementos e os rótulos se sobrepunham)."""
    m = ModeloProcesso()
    m.definir_processo("Desvio")
    for p in ("Família", "Advogado"):
        m.adicionar_participante(p)
    m.adicionar_elemento("tarefa_pessoa", "Levantar bens", "Advogado")
    m.adicionar_elemento("decisao", "Foi descoberta dívida?", "Advogado", depois_de="Levantar bens")
    m.adicionar_elemento("tarefa_pessoa", "Incluir dívida no inventário", "Advogado",
                         depois_de="Foi descoberta dívida?", rotulo_conexao="Sim")
    m.adicionar_elemento("decisao", "Faltam documentos?", "Advogado", depois_de="Foi descoberta dívida?",
                         rotulo_conexao="Não")
    m.adicionar_elemento("envio", "Pedir documentos à família", "Família", depois_de="Faltam documentos?",
                         rotulo_conexao="Sim")
    m.adicionar_elemento("decisao", "Valor acima de 1 milhão?", "Advogado", depois_de="Incluir dívida no inventário")
    m.conectar("Faltam documentos?", "Valor acima de 1 milhão?", "Não")
    m.conectar("Pedir documentos à família", "Levantar bens")
    m.adicionar_elemento("tarefa_pessoa", "Avaliar bens", "Advogado", depois_de="Valor acima de 1 milhão?",
                         rotulo_conexao="Sim")
    m.adicionar_elemento("tarefa_pessoa", "Calcular imposto", "Advogado", depois_de="Valor acima de 1 milhão?",
                         rotulo_conexao="Não")
    m.conectar("Avaliar bens", "Calcular imposto")
    m.adicionar_elemento("fim", "Fim", depois_de="Calcular imposto")
    return m


def test_nenhuma_seta_atravessa_um_elemento():
    m = decisoes_encadeadas()
    lay = calcular_layout(m)
    ids = list(m.p.elementos)
    ruins = [(f.origem, f.destino) for f in m.p.fluxos
             if _cruza(lay["rotas"][f.id], [lay["pos"][i] for i in ids if i not in (f.origem, f.destino)])]
    assert ruins == []


def test_duas_saidas_da_mesma_decisao_para_o_mesmo_lado_usam_corredores_diferentes():
    m = decisoes_encadeadas()
    lay = calcular_layout(m)
    saidas = [f for f in m.p.fluxos if f.origem == "Decisao_2"]      # "Faltam documentos?": as duas sobem
    xs = [tuple(round(x) for x, _ in lay["rotas"][f.id]) for f in saidas]
    assert len(set(xs)) == 2          # caminhos diferentes: as duas setas não seguem pela mesma linha


def _segmentos_e_rotulos(xml: str, m: ModeloProcesso):
    raiz = ET.fromstring(xml)
    nomes = {f.id: f.rotulo for f in m.p.fluxos}
    segmentos, rotulos = [], []
    for ed in raiz.iter("{%s}BPMNEdge" % NS["bpmndi"]):
        pts = [(float(w.get("x")), float(w.get("y"))) for w in ed.findall("di:waypoint", NS)]
        segmentos += [(ed.get("bpmnElement"), a, b) for a, b in zip(pts, pts[1:])]
        lb = ed.find("bpmndi:BPMNLabel/dc:Bounds", NS)
        if lb is not None and nomes.get(ed.get("bpmnElement")):
            largura, texto_w = float(lb.get("width")), min(float(lb.get("width")), 5.6 * len(nomes[ed.get("bpmnElement")]) + 4)
            x = float(lb.get("x")) + (largura - texto_w) / 2
            rotulos.append((ed.get("bpmnElement"), (x, float(lb.get("y")), texto_w, float(lb.get("height")) - 1)))
    return segmentos, rotulos


def test_rotulos_nao_se_sobrepoem_nem_tocam_nenhuma_linha_nem_elemento():
    m = decisoes_encadeadas()
    segmentos, rotulos = _segmentos_e_rotulos(gerar_bpmn_xml(m), m)
    assert len(rotulos) == 6                                              # Sim/Não de cada uma das 3 decisões
    lay = calcular_layout(m)
    for fid, caixa in rotulos:
        assert not any(_cruza([a, b], [caixa], 0) for _, a, b in segmentos), f"rótulo de {fid} toca uma linha"
        assert not _cruza([(caixa[0], caixa[1]), (caixa[0] + caixa[2], caixa[1] + caixa[3])], list(lay["pos"].values()), 0), \
            f"rótulo de {fid} está em cima de um elemento"
    for i, (_, a) in enumerate(rotulos):
        for _, b in rotulos[i + 1:]:
            assert not (a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1])


def test_cada_sistema_de_terceiros_tem_uma_cor_na_caixa_e_nas_setas_dele():
    m = ModeloProcesso()
    m.adicionar_participante("Advogado")
    m.cadastrar_sistema("Sefaz", externo="sim")
    m.cadastrar_sistema("PJe", externo="sim")
    m.adicionar_elemento("tarefa_pessoa", "Calcular", "Advogado", sistema="Sefaz")
    m.adicionar_elemento("tarefa_pessoa", "Protocolar", "Advogado", depois_de="Calcular", sistema="PJe")
    m.adicionar_elemento("tarefa_pessoa", "Pagar", "Advogado", depois_de="Protocolar", sistema="Sefaz")
    raiz = ET.fromstring(gerar_bpmn_xml(m))
    cor_caixa = {}
    for p in raiz.findall(".//bpmn:participant", NS):
        if p.get("name") in ("Sefaz", "PJe"):
            shape = [s for s in raiz.iter("{%s}BPMNShape" % NS["bpmndi"]) if s.get("bpmnElement") == p.get("id")][0]
            cor_caixa[p.get("id")] = shape.get(BIOC)
    assert len(set(cor_caixa.values())) == 2 and None not in cor_caixa.values()
    for mf in raiz.findall(".//bpmn:messageFlow", NS):
        edge = [e for e in raiz.iter("{%s}BPMNEdge" % NS["bpmndi"]) if e.get("bpmnElement") == mf.get("id")][0]
        assert edge.get(BIOC) == cor_caixa[mf.get("targetRef")]
