"""Testa o cliente da visão contra a API de verdade (em memória) e contra um serviço desligado."""
import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from bpmn_agent.api.rotas import criar_app
from bpmn_agent.visao.cliente import ApiForaDoAr, ClienteApi, ErroDaApi
from test_agente import LLMRoteirizado, chamada


def cliente(tmp_path, *respostas) -> ClienteApi:
    app = criar_app(fabrica_llm=lambda: LLMRoteirizado(respostas=list(respostas)), pasta=tmp_path)
    return ClienteApi(http=TestClient(app))


def test_roteiro_completo_pelo_cliente(tmp_path):
    c = cliente(tmp_path,
                AIMessage(content="", tool_calls=[chamada("adicionar_elemento", {"tipo": "tarefa", "nome": "A"}, 1)]),
                AIMessage(content="Pronto. E depois?"))
    assert c.saude()["status"] == "ok"

    estado = c.criar_sessao()
    assert estado["vazio"]
    resposta = c.enviar(estado["id"], "o primeiro passo é A")
    assert resposta["texto"].startswith("Pronto. E depois?") and "Passo_1" in resposta["alterados"]

    estado = c.estado(estado["id"])
    assert "Passo_1" in estado["processo"]["elementos"]
    continuada = c.criar_sessao(processo=estado["processo"])
    assert not continuada["vazio"]

    assert c.desfazer(estado["id"])["mensagem"] == "Última alteração desfeita."
    assert c.estado(estado["id"])["vazio"]


def test_erro_da_api_traz_mensagem_para_a_pessoa(tmp_path):
    with pytest.raises(ErroDaApi) as e:
        cliente(tmp_path).estado("00000000")
    assert e.value.status == 404 and e.value.codigo == "sessao_nao_encontrada" and "conversa" in e.value.mensagem


def test_servico_desligado_vira_api_fora_do_ar():
    def recusar(request):
        raise httpx.ConnectError("conexão recusada")

    c = ClienteApi(http=httpx.Client(base_url="http://127.0.0.1:1", transport=httpx.MockTransport(recusar)))
    with pytest.raises(ApiForaDoAr):
        c.saude()
