"""
As sessões vivas no servidor.

Ficam na memória deste processo: por isso o servidor roda com UM worker só. Se ele
reiniciar, a conversa se perde, mas o diagrama está em disco; uma sessão pedida pelo id
é recriada a partir de sessoes/<id>/processo.json (a conversa recomeça, o desenho volta).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.persistencia import carregar_modelo
from bpmn_agent.app.sessao import Sessao

MAX_SESSOES = 50    # acima disso, a sessão parada há mais tempo sai da memória (continua em disco)


@dataclass
class Entrada:
    sessao: Sessao
    trava: threading.Lock = field(default_factory=threading.Lock)   # uma requisição por vez na sessão
    ultimo_uso: float = field(default_factory=time.monotonic)


class RegistroSessoes:
    def __init__(self, fabrica_llm: Callable[[], BaseChatModel], pasta: str | Path = "sessoes",
                 max_sessoes: int = MAX_SESSOES):
        self._fabrica_llm = fabrica_llm
        self._pasta = Path(pasta)
        self._max = max_sessoes
        self._entradas: dict[str, Entrada] = {}
        self._trava = threading.Lock()

    def criar(self, modelo: ModeloProcesso | None = None) -> Entrada:
        sessao = Sessao(self._fabrica_llm(), pasta=self._pasta, modelo=modelo)
        with self._trava:
            return self._guardar(sessao)

    def obter(self, id: str) -> Entrada | None:
        """A sessão em memória ou, se o servidor reiniciou, recriada a partir do disco."""
        with self._trava:
            entrada = self._entradas.get(id)
            if entrada is None:
                arquivo = self._pasta / id / "processo.json"
                if not arquivo.exists():
                    return None
                entrada = self._guardar(Sessao(self._fabrica_llm(), pasta=self._pasta,
                                               modelo=carregar_modelo(arquivo), id=id))
            entrada.ultimo_uso = time.monotonic()
            return entrada

    def _guardar(self, sessao: Sessao) -> Entrada:
        while len(self._entradas) >= self._max:
            livres = [(e.ultimo_uso, i) for i, e in self._entradas.items() if not e.trava.locked()]
            if not livres:
                break
            del self._entradas[min(livres)[1]]
        entrada = self._entradas[sessao.id] = Entrada(sessao)
        return entrada

    def __len__(self) -> int:
        return len(self._entradas)

    def __contains__(self, id: str) -> bool:
        return id in self._entradas
