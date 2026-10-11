"""
Ferramentas (tools) que o LLM chama para editar o diagrama.

Cada ferramenta é uma closure sobre a sessão, então várias conversas
podem rodar em paralelo, cada uma com o seu próprio processo.
Esquemas propositalmente simples (strings com padrão "") porque modelos
baratos erram menos com parâmetros simples.
"""
from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.tools import BaseTool, tool

from bpmn_agent.app.dominio import ModeloProcesso

TipoElemento = Literal[
    "inicio", "fim", "tarefa", "tarefa_pessoa", "tarefa_sistema",
    "tarefa_manual", "envio", "decisao", "paralelo", "espera",
]


def criar_ferramentas(sessao) -> list[BaseTool]:
    """`sessao` precisa ter o atributo `.modelo` (ModeloProcesso)."""

    def m() -> ModeloProcesso:
        return sessao.modelo

    @tool
    def pedir_confirmacao(
        motivo: Annotated[str, "O que não bate com o desenho atual, em uma frase"],
        pedido: Annotated[str, "O pedido da pessoa, com as palavras dela, para aplicar se ela confirmar"],
    ) -> str:
        """Segura um pedido que não combina com o desenho (cita algo que não existe, contradiz o que já
        está desenhado ou troca algo importante sem motivo claro). Não altera o diagrama: depois de
        chamar, explique a dúvida e pergunte se é isso mesmo."""
        return sessao.pedir_confirmacao(motivo, pedido)

    @tool
    def definir_processo(
        nome: Annotated[str, "Nome curto do processo, ex.: 'Reembolso de despesas'"] = "",
        descricao: Annotated[str, "Objetivo do processo em uma frase"] = "",
    ) -> str:
        """Define ou altera o nome e o objetivo do processo."""
        return m().definir_processo(nome, descricao)

    @tool
    def adicionar_participante(nome: Annotated[str, "Pessoa, cargo, área ou sistema que executa passos"]) -> str:
        """Cadastra quem participa do processo (vira uma raia no diagrama)."""
        return m().adicionar_participante(nome)

    @tool
    def renomear_participante(atual: str, novo: str) -> str:
        """Renomeia um participante (e todos os passos dele)."""
        return m().renomear_participante(atual, novo)

    @tool
    def remover_participante(nome: str) -> str:
        """Remove um participante. Os passos dele ficam sem responsável."""
        return m().remover_participante(nome)

    @tool
    def adicionar_elemento(
        tipo: Annotated[TipoElemento, (
            "inicio=o que dispara o processo; fim=um jeito de o processo terminar; "
            "tarefa_pessoa=alguém faz usando sistema/tela; tarefa_sistema=o sistema faz sozinho; "
            "tarefa_manual=feito à mão; envio=mandar e-mail/mensagem/documento; tarefa=genérica; "
            "decisao=pergunta com respostas que levam a caminhos diferentes; "
            "paralelo=dividir em coisas que acontecem ao mesmo tempo, ou juntar esses caminhos; "
            "espera=aguardar um prazo/data")],
        nome: Annotated[str, "Rótulo curto. Tarefas: verbo no infinitivo + objeto ('Analisar pedido'). Decisões: pergunta ('Pedido aprovado?')"],
        responsavel: Annotated[str, "Quem executa (participante). Criado automaticamente se não existir"] = "",
        depois_de: Annotated[str, (
            "Id do elemento que vem imediatamente antes. Se for uma decisão/paralelo, cria um novo caminho "
            "saindo dela. Se for um passo comum, o novo é INSERIDO logo após ele (o que vinha depois passa a "
            "vir depois do novo). Vazio só para o primeiro elemento")] = "",
        rotulo_conexao: Annotated[str, "Resposta/condição do caminho quando sai de uma decisão, ex.: 'Sim', 'Acima de R$ 1.000'"] = "",
        descricao: Annotated[str, "Detalhes úteis do passo (opcional)"] = "",
    ) -> str:
        """Adiciona um passo, decisão, espera, início ou fim ao diagrama, já conectado ao anterior."""
        return m().adicionar_elemento(tipo, nome, responsavel, depois_de, rotulo_conexao, descricao)

    @tool
    def atualizar_elemento(
        id: Annotated[str, "Id do elemento"],
        nome: str = "",
        tipo: Annotated[str, "Novo tipo (mesmos valores de adicionar_elemento)"] = "",
        responsavel: Annotated[str, "Novo responsável; 'nenhum' para tirar"] = "",
        descricao: str = "",
    ) -> str:
        """Altera nome, tipo, responsável ou descrição de um elemento existente. Campos vazios não mudam."""
        return m().atualizar_elemento(id, nome, tipo, responsavel, descricao)

    @tool
    def remover_elemento(
        id: Annotated[str, "Id do elemento"],
        reconectar: Annotated[bool, "True: liga o anterior ao seguinte para não deixar buraco"] = True,
    ) -> str:
        """Remove um elemento do diagrama."""
        return m().remover_elemento(id, reconectar)

    @tool
    def mover_elemento(
        id: Annotated[str, "Id do elemento a mover"],
        depois_de: Annotated[str, "Id do elemento que deve vir imediatamente antes dele"],
    ) -> str:
        """Muda a ordem: tira o passo de onde está e o coloca logo depois de outro."""
        return m().mover_elemento(id, depois_de)

    @tool
    def conectar(
        origem: Annotated[str, "Id de onde sai"],
        destino: Annotated[str, "Id para onde vai"],
        rotulo: Annotated[str, "Condição/resposta, se a origem for uma decisão"] = "",
    ) -> str:
        """Liga dois elementos existentes. Use para voltas (retrabalho) e para juntar caminhos."""
        return m().conectar(origem, destino, rotulo)

    @tool
    def desconectar(origem: str, destino: str) -> str:
        """Remove a ligação entre dois elementos."""
        return m().desconectar(origem, destino)

    @tool
    def rotular_conexao(origem: str, destino: str, rotulo: str) -> str:
        """Muda o texto (condição/resposta) de uma ligação existente."""
        return m().rotular_conexao(origem, destino, rotulo)

    @tool
    def adicionar_regra(
        id: Annotated[str, "Id do elemento"],
        regra: Annotated[str, "Regra de negócio, prazo, limite, documento exigido, sistema usado..."],
    ) -> str:
        """Registra uma regra de negócio em um passo ou decisão (vai para a documentação do BPMN)."""
        return m().adicionar_regra(id, regra)

    @tool
    def remover_regra(id: str, numero: Annotated[int, "Número da regra (começa em 1)"]) -> str:
        """Remove uma regra de um elemento."""
        return m().remover_regra(id, numero)

    @tool
    def anotar_pendencia(texto: Annotated[str, "Algo a perguntar ou confirmar mais tarde"]) -> str:
        """Guarda um ponto para retomar depois, sem interromper o assunto atual."""
        return m().anotar_pendencia(texto)

    @tool
    def resolver_pendencia(numero: int) -> str:
        """Marca uma pendência como resolvida."""
        return m().resolver_pendencia(numero)

    @tool
    def desfazer() -> str:
        """Desfaz a última alteração do diagrama (pode ser chamada várias vezes)."""
        return m().desfazer()

    @tool
    def recomecar_diagrama() -> str:
        """Apaga todo o diagrama. Use SÓ se o usuário pedir explicitamente para começar do zero."""
        return m().recomecar()

    return [
        definir_processo, adicionar_participante, renomear_participante, remover_participante,
        adicionar_elemento, atualizar_elemento, remover_elemento, mover_elemento,
        conectar, desconectar, rotular_conexao, adicionar_regra, remover_regra,
        anotar_pendencia, resolver_pendencia, desfazer, recomecar_diagrama, pedir_confirmacao,
    ]
