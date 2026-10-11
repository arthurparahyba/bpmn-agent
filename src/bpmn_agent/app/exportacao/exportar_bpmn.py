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

from bpmn_agent.app.dominio import GATEWAYS, ModeloProcesso
from bpmn_agent.app.dominio.textos import _cond

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "bioc": "http://bpmn.io/schema/bpmn/biocolor/1.0",
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
CAIXA_W, CAIXA_H = 200, 40   # sistemas de terceiros
ESPACO_CORREDOR = 16         # distância entre as linhas horizontais das setas de cada sistema de terceiros
# Uma cor por sistema de terceiros (caixa + setas), para dar para seguir cada seta até a sua caixa.
CORES_SISTEMAS = ["#d6336c", "#1c7ed6", "#2f9e44", "#e8590c", "#7048e8", "#0b7285", "#a61e4d", "#5c940d"]


def _cruza(pts: list[tuple[float, float]], retangulos: list[tuple[float, float, float, float]], folga: float = 5) -> bool:
    """O caminho (segmentos retos) passa por dentro de algum retângulo (x, y, w, h)?"""
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        x0, x1, y0, y1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
        for rx, ry, rw, rh in retangulos:
            if x1 > rx - folga and x0 < rx + rw + folga and y1 > ry - folga and y0 < ry + rh + folga:
                return True
    return False


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
    raia_de = {i: m.raia_de(i) for i in ids}
    raias = list(p.participantes)
    raias += [r for r in dict.fromkeys(raia_de.values()) if r and r not in raias]   # sistemas da empresa
    usar_raias = bool(raias)
    if usar_raias and any(not r for r in raia_de.values()):
        raias.append("")  # raia "sem responsável"
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
    # Uma decisão com 2+ saídas para o mesmo lado (cima ou baixo): a 1ª sai pelo vértice, as outras pela direita,
    # para as linhas e os rótulos não ficarem um em cima do outro.
    indice_saida: dict[str, int] = {}
    for i in ids:
        if p.elementos[i].tipo not in GATEWAYS:
            continue
        sx, sy, sw, sh = pos[i]
        contagem = {"cima": 0, "baixo": 0}
        for f in p.fluxos:
            if f.origem != i or (i, f.destino) in voltas:
                continue
            tx, ty, tw, th = pos[f.destino]
            if tx + tw / 2 <= sx + sw / 2 or abs((sy + sh / 2) - (ty + th / 2)) < 1:
                continue
            lado = "cima" if ty + th / 2 < sy + sh / 2 else "baixo"
            indice_saida[f.id] = contagem[lado]
            contagem[lado] += 1
    rotas = {}
    usado_mx: dict[str, set[float]] = {}   # origem -> corredores verticais já ocupados por setas dela
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
            k = indice_saida.get(f.id, 0)
            if k == 0:
                sai_y = sy if tcy < scy else sy + sh  # sai por cima/baixo do losango
                pts = [(scx, sai_y), (scx, tcy), (tx, tcy)]
            else:   # 2ª saída para o mesmo lado: pela direita do losango, num corredor próprio
                mx = sx + sw + 16 + 22 * (k - 1)
                pts = [(sx + sw, scy), (mx, scy), (mx, tcy), (tx, tcy)]
                usado_mx.setdefault(f.origem, set()).add(mx)
        else:
            mx = (sx + sw + tx) / 2
            pts = [(sx + sw, scy), (mx, scy), (mx, tcy), (tx, tcy)]
        # a seta não pode passar por dentro de outro elemento: se passar, tenta descer/subir num corredor entre colunas
        if not ((f.origem, f.destino) in voltas or tcx <= scx):
            outros = [pos[i] for i in ids if i not in (f.origem, f.destino)]
            base_x = POOL_X + POOL_HEADER + LANE_HEADER + MARGEM_X
            if _cruza(pts, outros) and abs(scy - tcy) >= 1:
                for c in range(col[f.origem] + 1, col[f.destino] + 1):
                    mx = base_x + c * COL_W            # centro do vão entre duas colunas: nunca tem elemento
                    while mx in usado_mx.get(f.origem, ()):
                        mx += 22                        # outra seta da mesma origem já usa este corredor
                    if mx > tx - 8:
                        continue
                    alt = [(sx + sw, scy), (mx, scy), (mx, tcy), (tx, tcy)]
                    if not _cruza(alt, outros):
                        pts = alt
                        usado_mx.setdefault(f.origem, set()).add(mx)
                        break
            elif _cruza(pts, outros):   # mesma linha, com um elemento no meio: contorna por baixo (ou por cima)
                g1 = base_x + (col[f.origem] + 1) * COL_W
                g2 = base_x + col[f.destino] * COL_W
                for faixa in (scy + 52, scy - 52):
                    alt = [(sx + sw, scy), (g1, scy), (g1, faixa), (g2, faixa), (g2, tcy), (tx, tcy)]
                    if not _cruza(alt, outros):
                        pts = alt
                        break
        rotas[f.id] = pts

    # 8) sistemas de terceiros: uma caixa (piscina recolhida) para cada um, abaixo do processo, ligada por
    #    seta de mensagem aos passos que o usam
    def alvo(e) -> str:   # o sistema de terceiros que o passo aciona (o `chama`, ou o `sistema` se não houver `chama`)
        s = next((x for x in p.sistemas if x.nome == (e.chama or e.sistema)), None)
        return s.nome if s and s.externo else ""

    externos = [s.nome for s in p.sistemas if s.externo and any(alvo(e) == s.nome for e in p.elementos.values())]
    caixas, mensagens = {}, {}
    topo_caixas = pool[1] + pool[3] + 34 + ESPACO_CORREDOR * len(externos)
    for k, nome in enumerate(externos):
        cx0 = POOL_X + POOL_HEADER + k * (CAIXA_W + 30)
        caixas[nome] = (cx0, topo_caixas, CAIXA_W, CAIXA_H)
    for n, nome in enumerate(externos):
        bx, by, bw, bh = caixas[nome]
        for e in p.elementos.values():
            if alvo(e) != nome:
                continue
            x, y, w, h = pos[e.id]
            tcx = x + w / 2
            corredor = pool[1] + pool[3] + 14 + ESPACO_CORREDOR * n   # desvio horizontal, um corredor por sistema
            mensagens[(e.id, nome)] = [(tcx, y + h), (tcx, corredor), (bx + bw / 2, corredor), (bx + bw / 2, by)]
    return {"pos": pos, "rotas": rotas, "lanes": lanes_geo, "pool": pool,
            "raia_de": raia_de, "usar_raias": usar_raias, "caixas": caixas, "mensagens": mensagens}


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

    caixa_ids = {nome: f"Participant_{n}" for n, nome in enumerate(lay["caixas"], 2)}
    for nome, pid in caixa_ids.items():
        ET.SubElement(collab, _q("bpmn", "participant"), {"id": pid, "name": nome})
    mensagem_ids = {}
    for n, (elem_id, nome) in enumerate(lay["mensagens"], 1):
        mensagem_ids[(elem_id, nome)] = f"MessageFlow_{n}"
        ET.SubElement(collab, _q("bpmn", "messageFlow"), {"id": mensagem_ids[(elem_id, nome)], "name": "",
                                                          "sourceRef": elem_id, "targetRef": caixa_ids[nome]})

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
        # o sistema aparece dentro do próprio passo (2ª linha), para dar para ler no desenho
        tag = " → ".join(x for x in (e.sistema, e.chama) if x) if not (e.chama and not e.sistema) else f"→ {e.chama}"
        rotulo = e.nome + (f"\n[{tag}]" if tag and e.tipo.endswith("Task") else "")
        no = ET.SubElement(proc, _q("bpmn", e.tipo), {"id": e.id, "name": rotulo})
        doc = "\n".join(([e.descricao] if e.descricao else [])
                        + ([f"Sistema: {e.sistema}" + (f" — {e.operacao}" if e.operacao and not e.chama else "")]
                           if e.sistema else [])
                        + ([f"Chama: {e.chama}" + (f" — {e.operacao}" if e.operacao else "")] if e.chama else [])
                        + [f"Regra: {r}" + _cond(e, r, " (", ")") for r in e.regras])
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

    cor_de = {nome: CORES_SISTEMAS[n % len(CORES_SISTEMAS)] for n, nome in enumerate(lay["caixas"])}
    for nome, geo in lay["caixas"].items():
        shape(caixa_ids[nome], *geo, isHorizontal="true", **{_q("bioc", "stroke"): cor_de[nome]})
    for chave, pts in lay["mensagens"].items():
        ed = ET.SubElement(plano, _q("bpmndi", "BPMNEdge"),
                           {"id": f"{mensagem_ids[chave]}_di", "bpmnElement": mensagem_ids[chave],
                            _q("bioc", "stroke"): cor_de[chave[1]]})
        for (x, y) in pts:
            ET.SubElement(ed, _q("di", "waypoint"), {"x": _n(x), "y": _n(y)})

    # Rótulos das setas: cada um procura um lugar encostado na SUA linha que não toque em nenhuma outra
    # linha, elemento ou rótulo (senão fica ilegível). Caixas de texto: (x, y, largura, altura).
    segmentos = [s for pts in list(lay["rotas"].values()) + list(lay["mensagens"].values()) for s in zip(pts, pts[1:])]
    retangulos = list(lay["pos"].values()) + list(lay["caixas"].values())
    rotulos_usados: list[tuple[float, float, float, float]] = []
    ALT = 13

    def livre(caixa) -> bool:
        if any(_cruza([a, b], [caixa], 0) for a, b in segmentos):
            return False
        if _cruza([(caixa[0], caixa[1]), (caixa[0] + caixa[2], caixa[1])], retangulos, 1) or \
                _cruza([(caixa[0], caixa[1] + caixa[3]), (caixa[0] + caixa[2], caixa[1] + caixa[3])], retangulos, 1):
            return False
        return not any(caixa[0] < ux + uw + 2 and caixa[0] + caixa[2] + 2 > ux and caixa[1] < uy + uh and caixa[1] + caixa[3] > uy
                       for ux, uy, uw, uh in rotulos_usados)

    def lugar_do_rotulo(pts, texto_w):
        trechos = sorted(zip(pts, pts[1:]), key=lambda s: -(abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1])))
        for (ax, ay), (bx, by) in trechos:
            comprimento = abs(ax - bx) + abs(ay - by)
            vertical = abs(ax - bx) < 1
            if comprimento < (20 if vertical else texto_w + 8):
                continue
            for frac in (0.5, 0.35, 0.65, 0.2, 0.8, 0.12, 0.88):
                px, py = ax + (bx - ax) * frac, ay + (by - ay) * frac
                if vertical:
                    opcoes = [(px + 4, py - ALT / 2), (px - 4 - texto_w, py - ALT / 2)]
                else:
                    opcoes = [(px - texto_w / 2, py - 3 - ALT), (px - texto_w / 2, py + 3)]
                for ox, oy in opcoes:
                    if livre((ox, oy, texto_w, ALT)):
                        return ox, oy
        return None

    for f in p.fluxos:
        pts = lay["rotas"][f.id]
        ed = ET.SubElement(plano, _q("bpmndi", "BPMNEdge"), {"id": f"{f.id}_di", "bpmnElement": f.id})
        for (x, y) in pts:
            ET.SubElement(ed, _q("di", "waypoint"), {"x": _n(x), "y": _n(y)})
        if f.rotulo:
            larg = int(min(130, max(24, 6.4 * len(f.rotulo))))   # largura da caixa do rótulo (o texto fica centrado nela)
            texto_w = min(larg, 5.6 * len(f.rotulo) + 4)          # largura real do texto
            lugar = lugar_do_rotulo(pts, texto_w)
            if lugar is None:   # sem lugar livre: o mais perto do começo da seta, acima da linha
                (x1, y1) = pts[0]
                lugar = (x1 + 6, y1 - 3 - ALT)
            lx, ly = lugar[0] - (larg - texto_w) / 2, lugar[1]
            rotulos_usados.append((lugar[0], lugar[1], texto_w, ALT))
            lbl = ET.SubElement(ed, _q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, _q("dc", "Bounds"), {"x": _n(lx), "y": _n(ly), "width": str(larg), "height": str(ALT + 1)})

    ET.indent(defs, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(defs, encoding="unicode")


def _n(v: float) -> str:
    return str(int(round(v)))
