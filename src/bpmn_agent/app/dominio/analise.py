"""
Leituras que avaliam o processo, sem alterá-lo: o que ainda falta (pontos em aberto)
e em que raia cada elemento é desenhado.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bpmn_agent.app.dominio.processo import GATEWAYS, HERDAM_RAIA

if TYPE_CHECKING:
    from bpmn_agent.app.dominio.modelo import ModeloProcesso


def problemas(m: ModeloProcesso) -> list[str]:
    """Pontos em aberto, em linguagem simples, que o agente usa para guiar a entrevista."""
    els = m.p.elementos
    if not els:
        return []
    msgs = []
    inicios = [e for e in els.values() if e.tipo == "startEvent"]
    fins = [e for e in els.values() if e.tipo == "endEvent"]
    if not inicios:
        msgs.append("O processo ainda não tem início.")
    if not fins:
        msgs.append("Ainda não sabemos como o processo termina (nenhum fim).")
    for e in els.values():
        ent, sai = m.entradas(e.id), m.saidas(e.id)
        if e.tipo != "startEvent" and not ent:
            msgs.append(f"{e.id} '{e.nome}' não tem nada levando até ele.")
        if e.tipo != "endEvent" and not sai:
            msgs.append(f"{e.id} '{e.nome}': não sabemos o que acontece depois.")
        if e.tipo == "exclusiveGateway" and len(sai) == 1 and len(ent) <= 1:
            msgs.append(f"Decisão {e.id} '{e.nome}' só tem um caminho; falta a(s) outra(s) resposta(s).")
        if e.tipo == "exclusiveGateway" and len(sai) > 1:
            sem = [els[f.destino].nome for f in sai if not f.rotulo]
            if sem:
                msgs.append(f"Decisão {e.id} '{e.nome}': caminhos sem resposta/condição indicada (para {sem}).")
        if e.tipo not in GATEWAYS and e.tipo != "endEvent" and len(sai) > 1:
            msgs.append(f"{e.id} '{e.nome}' tem várias saídas sem uma decisão; pode faltar uma decisão.")
        if e.tipo not in HERDAM_RAIA and not e.responsavel and m.p.participantes:
            msgs.append(f"{e.id} '{e.nome}' está sem responsável.")
    return msgs


def raia_de(m: ModeloProcesso, elem_id: str) -> str:
    """Participante em cuja raia o elemento é desenhado. Início, fim, decisão, paralelo e espera
    sem responsável herdam o do passo mais próximo: primeiro olhando para trás, depois para frente."""
    e = m.p.elementos[elem_id]
    if e.responsavel or e.tipo not in HERDAM_RAIA:
        return e.responsavel
    para_tras = lambda i: [f.origem for f in m.entradas(i)]   # noqa: E731
    para_frente = lambda i: [f.destino for f in m.saidas(i)]  # noqa: E731
    for vizinhos in (para_tras, para_frente):
        vistos, fila = {elem_id}, [elem_id]
        while fila:
            for v in vizinhos(fila.pop(0)):
                if v in vistos:
                    continue
                if m.p.elementos[v].responsavel:
                    return m.p.elementos[v].responsavel
                vistos.add(v)
                fila.append(v)
    return ""
