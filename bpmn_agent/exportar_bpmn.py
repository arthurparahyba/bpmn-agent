"""
Gera BPMN 2.0 XML (com diagrama/posições - BPMN DI) a partir do ModeloProcesso.

O arquivo abre no bpmn.io, Camunda Modeler, Bizagi, Signavio etc.

Layout automático, simples e previsível:
  * cada participante vira uma raia (lane) horizontal dentro de uma piscina (pool);
  * colunas = "etapa" do elemento (maior distância a partir do início, ignorando voltas);
  * dentro de uma raia, elementos da mesma coluna são empilhados em linhas;
  * conexões ortogonais; voltas (retrabalho) passam por baixo dos elementos.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .modelo import GATEWAYS, ModeloProcesso

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
for _p, _u in NS.items():
    ET.register_namespace(_p, _u)


def _q(prefixo: str, tag: str) -> str:
    return f"{{{NS[prefixo]}}}{tag}"


# dimensões
TAM = {"task": (110, 80), "event": (36, 36), "gateway": (50, 50)}
COL_W, ROW_H = 170, 130
POOL_X, POOL_Y = 100, 60
POOL_HEADER, LANE_HEADER = 30, 30
MARGEM_X = 40


def _tam(tipo: str) -> tuple[int, int]:
    if tipo in GATEWAYS:
        return TAM["gateway"]
    if tipo.endswith("Event"):
        return TAM["event"]
    return TAM["task"]


# ---------------------------------------------------------------------- layout
def calcular_layout(m: ModeloProcesso) -> dict:
    p = m.p
    ids = list(p.elementos)
    succ = {i: [f.destino for f in p.fluxos if f.origem == i] for i in ids}

    # 1) arestas de volta (ciclos) via DFS a partir dos inícios
    inicios = [i for i in ids if p.elementos[i].tipo == "startEvent"]
    inicios += [i for i in ids if not any(f.destino == i for f in p.fluxos) and i not in inicios]
    voltas: set[tuple[str, str]] = set()
    estado: dict[str, int] = {}  # 1=na pilha, 2=concluído

    def dfs(raiz: str) -> None:
        pilha = [(raiz, iter(succ[raiz]))]
        estado[raiz] = 1
        while pilha:
            no, it = pilha[-1]
            prox = next(it, None)
            if prox is None:
                estado[no] = 2
                pilha.pop()
            elif estado.get(prox) == 1:
                voltas.add((no, prox))
            elif prox not in estado:
                estado[prox] = 1
                pilha.append((prox, iter(succ[prox])))

    for i in inicios + ids:
        if i not in estado:
            dfs(i)

    # 2) coluna = caminho mais longo no grafo sem as voltas (ordem topológica de Kahn)
    frente = {i: [d for d in succ[i] if (i, d) not in voltas] for i in ids}
    grau = {i: 0 for i in ids}
    for i in ids:
        for d in frente[i]:
            grau[d] += 1
    fila = [i for i in ids if grau[i] == 0]
    topo, col = [], {i: 0 for i in ids}
    while fila:
        i = fila.pop(0)
        topo.append(i)
        for d in frente[i]:
            col[d] = max(col[d], col[i] + 1)
            grau[d] -= 1
            if grau[d] == 0:
                fila.append(d)
    topo += [i for i in ids if i not in topo]

    # 3) raias
    raias = list(p.participantes)
    if raias and any(not p.elementos[i].responsavel for i in ids):
        raias.append("")  # raia "sem responsável"
    usar_raias = bool(raias)
    raia_de = {i: (p.elementos[i].responsavel if usar_raias else "") for i in ids}
    if not usar_raias:
        raias = [""]

    # 4) linha dentro da raia: tenta herdar a linha do predecessor (caminho principal reto)
    ocupado: dict[tuple[str, int], set[int]] = {}
    linha: dict[str, int] = {}
    pred = {i: [f.origem for f in p.fluxos if f.destino == i and (f.origem, i) not in voltas] for i in ids}
    for i in topo:
        preferida = 0
        for o in pred[i]:
            if raia_de.get(o) == raia_de[i] and o in linha:
                preferida = linha[o]
                break
        usadas = ocupado.setdefault((raia_de[i], col[i]), set())
        r = preferida
        while r in usadas:
            r += 1
        usadas.add(r)
        linha[i] = r

    # 5) geometria das raias
    linhas_por_raia = {r: 1 for r in raias}
    for i in ids:
        linhas_por_raia[raia_de[i]] = max(linhas_por_raia.get(raia_de[i], 1), linha[i] + 1)
    n_cols = (max(col.values()) + 1) if ids else 1
    largura = LANE_HEADER + MARGEM_X * 2 + n_cols * COL_W
    lanes_geo, y = {}, POOL_Y
    for r in raias:
        h = linhas_por_raia[r] * ROW_H
        lanes_geo[r] = (POOL_X + POOL_HEADER, y, largura, h)
        y += h
    pool = (POOL_X, POOL_Y, POOL_HEADER + largura, y - POOL_Y)

    # 6) posição de cada elemento (x, y, w, h)
    pos = {}
    for i in ids:
        lx, ly, _, _ = lanes_geo[raia_de[i]]
        w, h = _tam(p.elementos[i].tipo)
        cx = lx + LANE_HEADER + MARGEM_X + col[i] * COL_W + COL_W / 2
        cy = ly + linha[i] * ROW_H + ROW_H / 2
        pos[i] = (cx - w / 2, cy - h / 2, w, h)

    # 7) rotas das conexões
    rotas = {}
    for f in p.fluxos:
        sx, sy, sw, sh = pos[f.origem]
        tx, ty, tw, th = pos[f.destino]
        scx, scy, tcx, tcy = sx + sw / 2, sy + sh / 2, tx + tw / 2, ty + th / 2
        if (f.origem, f.destino) in voltas or tcx <= scx:
            if abs(scy - tcy) < 1:      # mesma linha: contorna por baixo dos dois
                base = max(sy + sh, ty + th) + 22
                pts = [(scx, sy + sh), (scx, base), (tcx, base), (tcx, ty + th)]
            elif tcy > scy:             # destino abaixo: corredor logo abaixo da origem
                canal = sy + sh + (ROW_H - sh) / 2 - 8
                pts = [(scx, sy + sh), (scx, canal), (tcx, canal), (tcx, ty)]
            else:                       # destino acima: corredor logo acima da origem
                canal = sy - (ROW_H - sh) / 2 + 8
                pts = [(scx, sy), (scx, canal), (tcx, canal), (tcx, ty + th)]
        elif abs(scy - tcy) < 1:
            pts = [(sx + sw, scy), (tx, tcy)]
        elif p.elementos[f.origem].tipo in GATEWAYS:
            sai_y = sy if tcy < scy else sy + sh  # sai por cima/baixo do losango
            pts = [(scx, sai_y), (scx, tcy), (tx, tcy)]
        else:
            mx = (sx + sw + tx) / 2
            pts = [(sx + sw, scy), (mx, scy), (mx, tcy), (tx, tcy)]
        rotas[f.id] = pts

    return {"pos": pos, "rotas": rotas, "lanes": lanes_geo, "pool": pool,
            "raia_de": raia_de, "usar_raias": usar_raias}


# ---------------------------------------------------------------------- XML
def gerar_bpmn_xml(m: ModeloProcesso) -> str:
    p = m.p
    lay = calcular_layout(m)

    defs = ET.Element(_q("bpmn", "definitions"), {
        "id": "Definitions_1",
        "targetNamespace": "http://bpmn.io/schema/bpmn",
        "exporter": "bpmn-agent (LangGraph)",
        "exporterVersion": "0.1",
    })
    collab = ET.SubElement(defs, _q("bpmn", "collaboration"), {"id": "Collaboration_1"})
    ET.SubElement(collab, _q("bpmn", "participant"),
                  {"id": "Participant_1", "name": p.nome, "processRef": "Process_1"})

    proc = ET.SubElement(defs, _q("bpmn", "process"), {"id": "Process_1", "name": p.nome, "isExecutable": "false"})
    if p.descricao:
        ET.SubElement(proc, _q("bpmn", "documentation")).text = p.descricao

    lane_ids = {}
    if lay["usar_raias"]:
        lane_set = ET.SubElement(proc, _q("bpmn", "laneSet"), {"id": "LaneSet_1"})
        for n, r in enumerate(lay["lanes"], 1):
            lane_ids[r] = f"Lane_{n}"
            lane = ET.SubElement(lane_set, _q("bpmn", "lane"), {"id": lane_ids[r], "name": r or "(sem responsável)"})
            for i, raia in lay["raia_de"].items():
                if raia == r:
                    ET.SubElement(lane, _q("bpmn", "flowNodeRef")).text = i

    for e in p.elementos.values():
        no = ET.SubElement(proc, _q("bpmn", e.tipo), {"id": e.id, "name": e.nome})
        doc = "\n".join(([e.descricao] if e.descricao else []) + [f"Regra: {r}" for r in e.regras])
        if doc:
            ET.SubElement(no, _q("bpmn", "documentation")).text = doc
        for f in m.entradas(e.id):
            ET.SubElement(no, _q("bpmn", "incoming")).text = f.id
        for f in m.saidas(e.id):
            ET.SubElement(no, _q("bpmn", "outgoing")).text = f.id
        if e.tipo == "intermediateCatchEvent":
            ET.SubElement(no, _q("bpmn", "timerEventDefinition"), {"id": f"Timer_{e.id}"})

    for f in p.fluxos:
        attrs = {"id": f.id, "sourceRef": f.origem, "targetRef": f.destino}
        if f.rotulo:
            attrs["name"] = f.rotulo
        ET.SubElement(proc, _q("bpmn", "sequenceFlow"), attrs)

    # ---- diagrama (DI)
    diag = ET.SubElement(defs, _q("bpmndi", "BPMNDiagram"), {"id": "BPMNDiagram_1"})
    plano = ET.SubElement(diag, _q("bpmndi", "BPMNPlane"), {"id": "BPMNPlane_1", "bpmnElement": "Collaboration_1"})

    def shape(elem_id: str, x, y, w, h, **extra):
        s = ET.SubElement(plano, _q("bpmndi", "BPMNShape"), {"id": f"{elem_id}_di", "bpmnElement": elem_id, **extra})
        ET.SubElement(s, _q("dc", "Bounds"), {"x": _n(x), "y": _n(y), "width": _n(w), "height": _n(h)})
        return s

    shape("Participant_1", *lay["pool"], isHorizontal="true")
    for r, geo in lay["lanes"].items():
        if r in lane_ids:
            shape(lane_ids[r], *geo, isHorizontal="true")

    for i, (x, y, w, h) in lay["pos"].items():
        tipo = p.elementos[i].tipo
        extra = {"isMarkerVisible": "true"} if tipo == "exclusiveGateway" else {}
        s = shape(i, x, y, w, h, **extra)
        if tipo in GATEWAYS:  # rótulo acima/à esquerda: não colide com saídas por cima/baixo
            lbl = ET.SubElement(s, _q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, _q("dc", "Bounds"), {"x": _n(x - 85), "y": _n(y - 30),
                                                     "width": "100", "height": "27"})
        elif tipo.endswith("Event"):  # rótulo abaixo do símbolo
            lbl = ET.SubElement(s, _q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, _q("dc", "Bounds"), {"x": _n(x + w / 2 - 50), "y": _n(y + h + 5),
                                                     "width": "100", "height": "27"})

    for f in p.fluxos:
        pts = lay["rotas"][f.id]
        ed = ET.SubElement(plano, _q("bpmndi", "BPMNEdge"), {"id": f"{f.id}_di", "bpmnElement": f.id})
        for (x, y) in pts:
            ET.SubElement(ed, _q("di", "waypoint"), {"x": _n(x), "y": _n(y)})
        if f.rotulo:
            # rótulo colado no início da conexão (logo na saída da decisão)
            (x1, y1), (x2, y2) = pts[0], pts[1]
            if abs(x1 - x2) < 1:   # primeiro trecho vertical
                lx, ly = x1 + 6, (y1 + 4 if y2 > y1 else y1 - 18)
            else:                  # primeiro trecho horizontal
                lx, ly = x1 + 6, y1 - 18
            lbl = ET.SubElement(ed, _q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, _q("dc", "Bounds"), {"x": _n(lx), "y": _n(ly), "width": "70", "height": "14"})

    ET.indent(defs, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(defs, encoding="unicode")


def _n(v: float) -> str:
    return str(int(round(v)))
