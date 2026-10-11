"""
Descrições do processo em texto, sem alterá-lo: o resumo compacto que vai para o LLM
e a narrativa em markdown para pessoas.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bpmn_agent.app.dominio.analise import problemas
from bpmn_agent.app.dominio.processo import ROTULO_LEGIVEL, TIPO_AMIGAVEL, Elemento, _normalizar

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
    if p.sistemas:
        linhas.append("Sistemas (não são participantes):")
        for s in p.sistemas:
            linhas.append(f"- {s.nome}" + (" (externo, de terceiros)" if s.externo else "")
                          + (f": {s.descricao}" if s.descricao else "")
                          + (f" | acesso: {s.integracao}" if s.integracao else "")
                          + (f" | operações: {'; '.join(s.operacoes)}" if s.operacoes else ""))
    linhas.append("Elementos:")
    for e in p.elementos.values():
        info = f"- {e.id} [{TIPO_AMIGAVEL.get(e.tipo, e.tipo)}] '{e.nome}'"
        if e.responsavel:
            info += f" | quem: {e.responsavel}"
        if e.sistema:
            info += f" | sistema: {e.sistema}" + (f" ({e.operacao})" if e.operacao and not e.chama else "")
        if e.chama:
            info += f" | chama: {e.chama}" + (f" ({e.operacao})" if e.operacao else "")
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


MARCADOR_MUDANCAS = "\n\n🔎 "
MARCADOR_ABERTOS = "\n\n⚠️ "
MIN_ELEMENTOS_PARA_AVISAR = 3
# Perguntas que só pedem o "ok" final ("está correto?"): contam como encerramento, não como pergunta de conteúdo.
_FECHAMENTO = re.compile(r"esta(?:ria)? (?:tudo )?(?:correto|certo)|ficou (?:certo|correto)|quer (?:mudar|alterar|ajustar)"
                         r"|mais alguma (?:alteracao|mudanca|coisa|duvida)|deseja (?:mudar|alterar|ajustar)")
_CAMPOS = ("o nome", "o tipo", "quem faz", "as regras", "a descrição", "o sistema", "a operação no sistema", "o sistema chamado")


def assinatura(e: Elemento) -> tuple:
    """Tudo o que o resumo de mudanças compara de um elemento (na ordem de _CAMPOS)."""
    return (e.nome, e.tipo, e.responsavel, tuple(e.regras), e.descricao, e.sistema, e.operacao, e.chama)


def aviso_de_conclusao(m: ModeloProcesso, fala: str, limite: int = 5) -> str:
    """Calculado pelo código: se a fala do agente NÃO faz pergunta (está encerrando) e o diagrama ainda tem
    pontos em aberto, devolve o aviso para a pessoa; senão, texto vazio. Os ids saem (são internos)."""
    if ("?" in fala and not _FECHAMENTO.search(_normalizar(fala))) or len(m.p.elementos) < MIN_ELEMENTOS_PARA_AVISAR:
        return ""
    abertos = [re.sub(r"\b(?:Passo|Decisao|Fim|Inicio|Espera|Paralelo)_\d+ ", "", x).rstrip(".") for x in m.problemas()]
    if not abertos:
        return ""
    extra = f" e mais {len(abertos) - limite}" if len(abertos) > limite else ""
    return ("Ainda há pontos em aberto, então o desenho não está completo: "
            + "; ".join(abertos[:limite]) + extra + ".")


def _citado(nomes: list[str], texto: str) -> bool:
    """O texto da pessoa menciona algum destes nomes (ou uma palavra de pelo menos 3 letras de um deles)?"""
    palavras = set(re.findall(r"\w+", _normalizar(texto)))
    for n in nomes:
        n = _normalizar(n)
        if n and (n in _normalizar(texto) or any(len(w) >= 3 and w in palavras for w in n.split())):
            return True
    return False


def resumo_mudancas(antes: dict[str, tuple], fluxos_antes: set[tuple], m: ModeloProcesso, limite: int = 5,
                    texto_usuario: str | None = None) -> str:
    """Frase com o que MUDOU DE FATO no desenho num turno, calculada pelo código (não pela LLM).
    `antes` mapeia id -> assinatura(elemento); `fluxos_antes` tem (origem, destino, rotulo).
    Com `texto_usuario`, avisa quando um passo ganhou um sistema que a pessoa não citou nesta mensagem."""
    p = m.p
    novos = [e.nome for i, e in p.elementos.items() if i not in antes]
    removidos = [a[0] for i, a in antes.items() if i not in p.elementos]
    mudados = []
    for i, e in p.elementos.items():
        if i in antes and antes[i] != assinatura(e):
            campos = [c for c, a, b in zip(_CAMPOS, antes[i], assinatura(e)) if a != b]
            mudados.append(f"{e.nome} ({', '.join(campos)})")
    fluxos_depois = {(f.origem, f.destino, f.rotulo) for f in p.fluxos}
    ligacoes_novas, ligacoes_removidas = len(fluxos_depois - fluxos_antes), len(fluxos_antes - fluxos_depois)

    def lista(itens: list[str]) -> str:
        extra = f" e mais {len(itens) - limite}" if len(itens) > limite else ""
        return ", ".join(itens[:limite]) + extra

    partes = []
    if novos:
        partes.append(f"{len(novos)} item(ns) novo(s): {lista(novos)}")
    if removidos:
        partes.append(f"{len(removidos)} removido(s): {lista(removidos)}")
    if mudados:
        partes.append(f"alterado(s): {lista(mudados)}")
    if ligacoes_novas or ligacoes_removidas:
        partes.append(f"ligações: +{ligacoes_novas} / -{ligacoes_removidas}")
    if texto_usuario is not None:
        deduzidos = []
        for i, e in p.elementos.items():
            for nome_sis, posicao in ((e.sistema, 5), (e.chama, 7)):
                if nome_sis and (i not in antes or antes[i][posicao] != nome_sis):
                    if not _citado([nome_sis, e.operacao], texto_usuario):
                        deduzidos.append(f"{nome_sis} em {e.nome}")
        if deduzidos:
            partes.append("sistema deduzido, não dito por você (confirme): " + lista(deduzidos))
    return "O que mudou de fato no desenho: " + ("; ".join(partes) if partes else "nada") + "."


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
    if p.sistemas:
        cab.append("**Sistemas:**\n" + "\n".join(
            f"- {s.nome}" + (f": {s.descricao}" if s.descricao else "") + (f" ({s.integracao})" if s.integracao else "")
            + (f" — operações: {'; '.join(s.operacoes)}" if s.operacoes else "") for s in p.sistemas))
    partes = ["\n\n".join(cab), ""]
    for n, e in enumerate(_ordem_visita(m), 1):
        quem = f" — {e.responsavel}" if e.responsavel else ""
        partes.append(f"{n}. **{e.nome}**{quem} _({ROTULO_LEGIVEL.get(e.tipo, e.tipo)})_")
        if e.descricao:
            partes.append(f"   - {e.descricao}")
        if e.sistema:
            partes.append(f"   - Sistema: {e.sistema}" + (f" — {e.operacao}" if e.operacao and not e.chama else ""))
        if e.chama:
            partes.append(f"   - Chama: {e.chama}" + (f" — {e.operacao}" if e.operacao else ""))
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
