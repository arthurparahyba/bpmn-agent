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
        if e.tipo not in HERDAM_RAIA and not e.responsavel and not _raia_do_sistema(m, e) and m.p.participantes:
            msgs.append(f"{e.id} '{e.nome}' está sem responsável.")
        if e.tipo == "serviceTask" and not e.sistema and not e.chama:
            msgs.append(f"{e.id} '{e.nome}' é automático, mas não sabemos em qual sistema.")
    usados = {e.sistema for e in els.values()} | {e.chama for e in els.values()}
    vistos: dict[tuple, str] = {}
    for e in els.values():   # a mesma chamada, do mesmo executor e do mesmo responsável, em dois passos
        if e.operacao and (e.chama or e.sistema):
            chave = (e.chama or e.sistema, e.operacao.lower(), e.sistema, e.responsavel)
            if chave in vistos:
                msgs.append(f"'{vistos[chave]}' e '{e.nome}' usam a mesma chamada ({e.operacao}); "
                            "se for o mesmo passo, junte os dois (se forem passos diferentes, pode ignorar).")
            else:
                vistos[chave] = e.nome
    for s in m.p.sistemas:
        if s.nome not in usados:
            msgs.append(f"O sistema '{s.nome}' está cadastrado, mas nenhum passo o usa.")
    return msgs


# Passos que um sistema faz sozinho: automático e envio (e-mail, notificação...).
PASSOS_DE_SISTEMA = {"serviceTask", "sendTask"}


def _raia_do_sistema(m: ModeloProcesso, e) -> str:
    """Passo automático ou de envio, sem responsável, feito num sistema DA EMPRESA: a raia leva o nome do sistema.
    (Sistema de terceiros não vira raia: é desenhado como uma caixa separada, ver exportar_bpmn.)"""
    if e.responsavel or e.tipo not in PASSOS_DE_SISTEMA or not e.sistema:
        return ""
    s = next((x for x in m.p.sistemas if x.nome == e.sistema), None)
    return e.sistema if s and not s.externo else ""


def _raia_propria(m: ModeloProcesso, e) -> str:
    return e.responsavel or _raia_do_sistema(m, e)


def raia_de(m: ModeloProcesso, elem_id: str) -> str:
    """Participante (ou sistema da empresa, em passo automático sem responsável) em cuja raia o elemento é
    desenhado. Início, fim, decisão, paralelo e espera sem responsável herdam o do passo mais próximo:
    primeiro olhando para trás, depois para frente."""
    e = m.p.elementos[elem_id]
    if _raia_propria(m, e) or e.tipo not in HERDAM_RAIA:
        return _raia_propria(m, e)
    para_tras = lambda i: [f.origem for f in m.entradas(i)]   # noqa: E731
    para_frente = lambda i: [f.destino for f in m.saidas(i)]  # noqa: E731
    for vizinhos in (para_tras, para_frente):
        vistos, fila = {elem_id}, [elem_id]
        while fila:
            for v in vizinhos(fila.pop(0)):
                if v in vistos:
                    continue
                if _raia_propria(m, m.p.elementos[v]):
                    return _raia_propria(m, m.p.elementos[v])
                vistos.add(v)
                fila.append(v)
    return ""
