"""
A API HTTP do backend: é por aqui que a visão conversa com a Sessao.

    GET  /saude                            o serviço está no ar? qual LLM está configurada?
    POST /sessoes                          começa uma conversa (ou continua um processo.json)
    GET  /sessoes/{id}                     tudo o que a tela precisa
    POST /sessoes/{id}/mensagens           um turno da conversa
    POST /sessoes/{id}/desfazer            desfaz a última alteração
    GET  /sessoes/{id}/arquivos/{nome}     processo.bpmn | processo.json | processo.md

As rotas são `def` (não `async`): um turno é síncrono e demora segundos, então roda no
conjunto de threads do servidor sem travar as outras requisições.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Path as Caminho, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from langchain_core.language_models import BaseChatModel

from bpmn_agent.api.esquemas import (
    CriarSessao, Desfeito, EnviarMensagem, Erro, EstadoSessao, RespostaTurno, Saude, estado_de,
)
from bpmn_agent.api.registro import Entrada, RegistroSessoes
from bpmn_agent.app.agente.llm import criar_llm, llm_configurada
from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.exportacao.exportar_bpmn import gerar_bpmn_xml

TAMANHO_MAX_CORPO = 1_000_000   # bytes
IdSessao = Annotated[str, Caminho(pattern="^[0-9a-f]{8}$")]
NomeArquivo = Literal["processo.bpmn", "processo.json", "processo.md"]


class ErroApi(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str, detalhe: str = ""):
        self.status, self.codigo, self.mensagem, self.detalhe = status, codigo, mensagem, detalhe[:300]


def _erro_da_llm(e: Exception) -> ErroApi:
    msg = str(e)
    if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
        return ErroApi(502, "llm_limite", "O limite de uso do modelo foi atingido. Espere um pouco e tente de novo.", msg)
    if "401" in msg or "auth" in msg.lower() or "api key" in msg.lower():
        return ErroApi(502, "llm_chave_invalida", "A chave do modelo configurada no serviço parece inválida.", msg)
    return ErroApi(502, "llm_falha", "Algo deu errado ao falar com o modelo.", msg)


def criar_app(fabrica_llm: Callable[[], BaseChatModel] = criar_llm, pasta: str | Path = "sessoes") -> FastAPI:
    """`fabrica_llm` cria a LLM de cada sessão; os testes passam uma LLM roteirizada."""
    app = FastAPI(title="Desenhista de Processos", version="0.1.0")
    registro = app.state.registro = RegistroSessoes(fabrica_llm, pasta)

    @app.exception_handler(ErroApi)
    def _responder_erro(_: Request, e: ErroApi) -> JSONResponse:
        return JSONResponse(Erro(codigo=e.codigo, mensagem=e.mensagem, detalhe=e.detalhe).model_dump(),
                            status_code=e.status)

    @app.exception_handler(RequestValidationError)
    def _responder_entrada_invalida(_: Request, e: RequestValidationError) -> JSONResponse:
        detalhe = "; ".join(f"{'.'.join(str(p) for p in d['loc'])}: {d['msg']}" for d in e.errors())
        return JSONResponse(Erro(codigo="entrada_invalida", mensagem="O pedido enviado ao serviço não é válido.",
                                 detalhe=detalhe[:300]).model_dump(), status_code=422)

    @app.middleware("http")
    async def _limitar_corpo(request: Request, seguir):
        tamanho = request.headers.get("content-length", "0")
        if tamanho.isdigit() and int(tamanho) > TAMANHO_MAX_CORPO:
            return JSONResponse(Erro(codigo="corpo_grande", mensagem="O arquivo enviado é grande demais.").model_dump(),
                                status_code=413)
        return await seguir(request)

    def criar_sessao(modelo: ModeloProcesso | None = None) -> Entrada:
        try:
            return registro.criar(modelo)
        except ValueError as e:    # provedor desconhecido ou chave ausente no ambiente do servidor
            raise ErroApi(503, "llm_nao_configurada", "O serviço ainda não foi configurado com um modelo.", str(e))

    def obter(id: str) -> Entrada:
        try:
            entrada = registro.obter(id)
        except ValueError as e:
            raise ErroApi(503, "llm_nao_configurada", "O serviço ainda não foi configurado com um modelo.", str(e))
        if entrada is None:
            raise ErroApi(404, "sessao_nao_encontrada", "Não encontrei essa conversa. Ela pode ter sido encerrada.")
        return entrada

    @app.get("/saude")
    def saude() -> Saude:
        try:
            provedor, modelo = llm_configurada()
        except ValueError:
            provedor, modelo = "(não configurado)", ""
        return Saude(provedor=provedor, modelo=modelo)

    @app.post("/sessoes", status_code=201)
    def nova_sessao(pedido: CriarSessao | None = None) -> EstadoSessao:
        modelo = None
        if pedido and pedido.processo is not None:
            try:    # o arquivo vem de fora: só aceita se der para desenhar e descrever
                modelo = ModeloProcesso.de_dict(pedido.processo)
                gerar_bpmn_xml(modelo)
                modelo.narrativa()
            except Exception as e:
                raise ErroApi(422, "processo_invalido", "Não consegui abrir esse arquivo de processo.", str(e))
        return estado_de(criar_sessao(modelo).sessao)

    @app.get("/sessoes/{id}")
    def ver_sessao(id: IdSessao) -> EstadoSessao:
        entrada = obter(id)
        with entrada.trava:
            return estado_de(entrada.sessao)

    @app.post("/sessoes/{id}/mensagens")
    def enviar_mensagem(id: IdSessao, pedido: EnviarMensagem) -> RespostaTurno:
        entrada = obter(id)
        if not entrada.trava.acquire(blocking=False):
            raise ErroApi(409, "sessao_ocupada", "Ainda estou respondendo a mensagem anterior.")
        try:
            return RespostaTurno(**asdict(entrada.sessao.enviar(pedido.texto)))
        except Exception as e:
            raise _erro_da_llm(e)
        finally:
            entrada.trava.release()

    @app.post("/sessoes/{id}/desfazer")
    def desfazer(id: IdSessao) -> Desfeito:
        entrada = obter(id)
        with entrada.trava:
            return Desfeito(mensagem=entrada.sessao.desfazer())

    @app.get("/sessoes/{id}/arquivos/{nome}")
    def baixar_arquivo(id: IdSessao, nome: NomeArquivo) -> Response:
        entrada = obter(id)
        with entrada.trava:    # gerado da memória: nenhum caminho vindo do cliente toca o disco
            sessao = entrada.sessao
            conteudo, tipo = {
                "processo.bpmn": (sessao.bpmn_xml(), "application/xml"),
                "processo.json": (json.dumps(sessao.modelo.para_dict(), ensure_ascii=False, indent=2), "application/json"),
                "processo.md": (sessao.modelo.narrativa(), "text/markdown"),
            }[nome]
        return Response(conteudo, media_type=f"{tipo}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    return app
