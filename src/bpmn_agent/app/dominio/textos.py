"""
Descrições do processo em texto, sem alterá-lo: o resumo compacto que vai para o LLM
e a narrativa em markdown para pessoas.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bpmn_agent.app.dominio.analise import problemas
from bpmn_agent.app.dominio.processo import ROTULO_LEGIVEL, TIPO_AMIGAVEL, Elemento

if TYPE_CHECKING:
    from bpmn_agent.app.dominio.modelo import ModeloProcesso


def resumo(m: ModeloProcesso) -> str:
    """Representação textual compacta do diagrama, injetada no prompt a cada turno."""
    p = m.p
    if not p.elementos:
        return (f"Processo: {p.nome}\n" + (f"Descrição: {p.descricao}\n" if p.descricao else "")
                + (f"Participantes: {', '.join(p.participantes)}\n" if p.participantes else "")
                + "Diagrama vazio.")
    linhas = [f"Processo: {p.nome}"]
    if p.descricao:
        linhas.append(f"Descrição: {p.descricao}")
    linhas.append(f"Participantes: {', '.join(p.participantes) or '(nenhum)'}")
    linhas.append("Elementos:")
    for e in p.elementos.values():
        info = f"- {e.id} [{TIPO_AMIGAVEL.get(e.tipo, e.tipo)}] '{e.nome}'"
        if e.responsavel:
            info += f" | quem: {e.responsavel}"
        if e.descricao:
            info += f" | obs: {e.descricao}"
        for i, r in enumerate(e.regras, 1):
            info += f"\n    regra {i}: {r}"
        linhas.append(info)
    linhas.append("Conexões:")
    for f in p.fluxos:
        linhas.append(f"- {f.origem} -> {f.destino}" + (f" [{f.rotulo}]" if f.rotulo else ""))
    probs = problemas(m)
    if probs:
        linhas.append("Pontos em aberto no diagrama:")
        linhas += [f"- {m}" for m in probs]
    if p.pendencias:
        linhas.append("Pendências anotadas para perguntar depois:")
        linhas += [f"{i}. {t}" for i, t in enumerate(p.pendencias, 1)]
    return "\n".join(linhas)


def narrativa(m: ModeloProcesso) -> str:
    """Descrição do fluxo em linguagem natural (para revisão com o usuário / documentação)."""
    p = m.p
    if not p.elementos:
        return "O diagrama ainda está vazio."
    nome = lambda i: p.elementos[i].nome  # noqa: E731
    cab = [f"# {p.nome}"]
    if p.descricao:
        cab.append(p.descricao)
    if p.participantes:
        cab.append("**Participantes:** " + ", ".join(p.participantes))
    partes = ["\n\n".join(cab), ""]
    for n, e in enumerate(_ordem_visita(m), 1):
        quem = f" — {e.responsavel}" if e.responsavel else ""
        partes.append(f"{n}. **{e.nome}**{quem} _({ROTULO_LEGIVEL.get(e.tipo, e.tipo)})_")
        if e.descricao:
            partes.append(f"   - {e.descricao}")
        for r in e.regras:
            partes.append(f"   - Regra: {r}")
        for f in m.saidas(e.id):
            cond = f"se **{f.rotulo}**, " if f.rotulo else ""
            partes.append(f"   - {cond}segue para: {nome(f.destino)}")
    if p.pendencias:
        partes.append("\n**Pendências:**")
        partes += [f"- {t}" for t in p.pendencias]
    return "\n".join(partes)


def _ordem_visita(m: ModeloProcesso) -> list[Elemento]:
    visitados, ordem = set(), []
    fila = [e.id for e in m.p.elementos.values() if e.tipo == "startEvent"]
    fila += [e.id for e in m.p.elementos.values() if not m.entradas(e.id) and e.id not in fila]
    while fila:
        i = fila.pop(0)
        if i in visitados:
            continue
        visitados.add(i)
        ordem.append(m.p.elementos[i])
        fila += [f.destino for f in m.saidas(i)]
    ordem += [e for e in m.p.elementos.values() if e.id not in visitados]
    return ordem
