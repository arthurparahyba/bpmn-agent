"""
Cliente da API do backend. É o único jeito de a visão falar com o backend.

    cliente = ClienteApi()                 # endereço em BPMN_API_URL (padrão http://127.0.0.1:8000)
    estado = cliente.criar_sessao()
    resposta = cliente.enviar(estado["id"], "reembolso de despesas")

Os métodos devolvem dicionários, no formato descrito em docs/pecas/api.md.
"""
from __future__ import annotations

import os

import httpx

URL_PADRAO = "http://127.0.0.1:8000"
ESPERA_CURTA = httpx.Timeout(10, connect=3)
ESPERA_TURNO = httpx.Timeout(180, connect=3)   # um turno pode ter várias idas ao LLM
MENSAGEM_FORA_DO_AR = "Não consegui falar com o serviço do Desenhista. Verifique se ele está ligado e tente de novo."


class ApiForaDoAr(Exception):
    """O serviço não respondeu (desligado, endereço errado ou demorou demais)."""


class ErroDaApi(Exception):
    """O serviço respondeu com um erro. `mensagem` é para a pessoa; `detalhe`, para quem desenvolve."""

    def __init__(self, status: int, codigo: str, mensagem: str, detalhe: str = ""):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem, self.detalhe = status, codigo, mensagem, detalhe


class ClienteApi:
    def __init__(self, base_url: str | None = None, http: httpx.Client | None = None):
        self.base_url = (base_url or os.getenv("BPMN_API_URL") or URL_PADRAO).rstrip("/")
        self._http = http or httpx.Client(base_url=self.base_url, timeout=ESPERA_CURTA)

    def _pedir(self, metodo: str, caminho: str, **kwargs) -> dict:
        try:
            r = self._http.request(metodo, caminho, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            raise ApiForaDoAr(f"{self.base_url}: {e}") from e
        if r.is_success:
            return r.json()
        try:
            erro = r.json()
        except ValueError:
            erro = {}
        raise ErroDaApi(r.status_code, erro.get("codigo", "erro"),
                        erro.get("mensagem", "O serviço devolveu um erro."), erro.get("detalhe", ""))

    def saude(self) -> dict:
        return self._pedir("GET", "/saude")

    def criar_sessao(self, processo: dict | None = None) -> dict:
        """Começa uma conversa. `processo`: conteúdo de um processo.json salvo antes, para continuar."""
        return self._pedir("POST", "/sessoes", json={"processo": processo})

    def estado(self, id: str) -> dict:
        return self._pedir("GET", f"/sessoes/{id}")

    def enviar(self, id: str, texto: str) -> dict:
        return self._pedir("POST", f"/sessoes/{id}/mensagens", json={"texto": texto}, timeout=ESPERA_TURNO)

    def desfazer(self, id: str) -> dict:
        return self._pedir("POST", f"/sessoes/{id}/desfazer")
