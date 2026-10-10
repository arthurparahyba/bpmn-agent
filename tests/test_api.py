"""Testa as rotas HTTP com o TestClient e o LLM roteirizado (sem rede e sem chamar API de LLM)."""
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from bpmn_agent.api.registro import RegistroSessoes
from bpmn_agent.api.rotas import criar_app
from test_agente import LLMRoteirizado, chamada


def api(tmp_path, *respostas, fabrica=None) -> TestClient:
    return TestClient(criar_app(fabrica_llm=fabrica or (lambda: LLMRoteirizado(respostas=list(respostas))),
                                pasta=tmp_path))


def turno_que_cria_um_passo():
    return [AIMessage(content="", tool_calls=[chamada("adicionar_elemento",
                                                      {"tipo": "tarefa_pessoa", "nome": "Enviar pedido",
                                                       "responsavel": "Funcionário"}, 1)]),
            AIMessage(content="Anotei. E depois?")]


def test_saude_informa_o_llm_configurado_sem_expor_chave(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVEDOR", "anthropic")
    monkeypatch.setenv("LLM_MODELO", "modelo-de-teste")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "segredo-123")
    r = api(tmp_path).get("/saude")
    assert r.json() == {"status": "ok", "provedor": "anthropic", "modelo": "modelo-de-teste"}
    assert "segredo-123" not in r.text


def test_criar_sessao_devolve_estado_com_saudacao(tmp_path):
    r = api(tmp_path).post("/sessoes")
    estado = r.json()
    assert r.status_code == 201
    assert estado["vazio"] and estado["em_aberto"] == []
    assert [m["papel"] for m in estado["historico"]] == ["assistant"]
    assert not (tmp_path / estado["id"]).exists()    # nada em disco até a primeira alteração


def test_turno_atualiza_estado_e_grava_arquivos(tmp_path):
    c = api(tmp_path, *turno_que_cria_um_passo())
    id = c.post("/sessoes").json()["id"]
    r = c.post(f"/sessoes/{id}/mensagens", json={"texto": "o funcionário envia o pedido"})
    assert r.status_code == 200
    resposta = r.json()
    assert resposta["texto"] == "Anotei. E depois?"
    assert resposta["acoes"][0].startswith("adicionar_elemento: Criado Passo_1")
    assert {"Inicio_1", "Passo_1"} <= set(resposta["alterados"])

    estado = c.get(f"/sessoes/{id}").json()
    assert not estado["vazio"] and "Passo_1" in estado["processo"]["elementos"]
    assert "Enviar pedido" in estado["bpmn_xml"] and "Enviar pedido" in estado["narrativa"]
    assert [m["papel"] for m in estado["historico"]] == ["assistant", "user", "assistant"]
    assert any("não sabemos o que acontece depois" in p for p in estado["em_aberto"])
    assert (tmp_path / id / "processo.json").exists()


def test_desfazer_e_arquivos(tmp_path):
    c = api(tmp_path, *turno_que_cria_um_passo())
    id = c.post("/sessoes").json()["id"]
    c.post(f"/sessoes/{id}/mensagens", json={"texto": "x"})

    bpmn = c.get(f"/sessoes/{id}/arquivos/processo.bpmn")
    assert bpmn.headers["content-type"].startswith("application/xml") and "Enviar pedido" in bpmn.text
    assert c.get(f"/sessoes/{id}/arquivos/processo.json").json()["elementos"]["Passo_1"]["nome"] == "Enviar pedido"
    assert c.get(f"/sessoes/{id}/arquivos/processo.md").headers["content-type"].startswith("text/markdown")
    assert c.get(f"/sessoes/{id}/arquivos/outro.txt").status_code == 422

    assert c.post(f"/sessoes/{id}/desfazer").json() == {"mensagem": "Última alteração desfeita."}
    assert c.get(f"/sessoes/{id}").json()["vazio"]


def test_continuar_a_partir_de_um_processo_enviado(tmp_path):
    c = api(tmp_path, *turno_que_cria_um_passo())
    id = c.post("/sessoes").json()["id"]
    c.post(f"/sessoes/{id}/mensagens", json={"texto": "x"})
    processo = c.get(f"/sessoes/{id}").json()["processo"]

    nova = c.post("/sessoes", json={"processo": processo}).json()
    assert nova["id"] != id and not nova["vazio"]
    assert nova["historico"][0]["texto"].startswith("Oi de novo!")

    ruim = c.post("/sessoes", json={"processo": {"elementos": {"X": {"campo": "desconhecido"}}}})
    assert ruim.status_code == 422 and ruim.json()["codigo"] == "processo_invalido"


@pytest.mark.parametrize("caminho", ["/sessoes/00000000", "/sessoes/00000000/desfazer", "/sessoes/00000000/mensagens"])
def test_sessao_inexistente_da_404_com_mensagem_para_leigo(tmp_path, caminho):
    c = api(tmp_path)
    r = c.get(caminho) if caminho.endswith("00000000") else c.post(caminho, json={"texto": "oi"})
    assert r.status_code == 404
    assert r.json()["codigo"] == "sessao_nao_encontrada" and "conversa" in r.json()["mensagem"]


def test_entradas_invalidas(tmp_path):
    c = api(tmp_path)
    id = c.post("/sessoes").json()["id"]
    assert c.get("/sessoes/..%2F..%2Fetc").status_code in (404, 422)      # id fora do formato não toca o disco
    assert c.get("/sessoes/NAO-E-ID").status_code == 422
    vazio = c.post(f"/sessoes/{id}/mensagens", json={"texto": ""})
    assert vazio.status_code == 422 and vazio.json()["codigo"] == "entrada_invalida"
    assert c.post(f"/sessoes/{id}/mensagens", json={"texto": "a" * 8001}).status_code == 422
    assert c.post("/sessoes", content=b"x" * 1_000_001,
                  headers={"content-type": "application/json"}).status_code == 413


def test_falha_do_llm_vira_502_com_dica(tmp_path):
    class LLMQuebrado(LLMRoteirizado):
        def _generate(self, *a, **k):
            raise RuntimeError("Error code: 429 - rate limit")

    c = api(tmp_path, fabrica=lambda: LLMQuebrado(respostas=[]))
    id = c.post("/sessoes").json()["id"]
    r = c.post(f"/sessoes/{id}/mensagens", json={"texto": "oi"})
    assert r.status_code == 502 and r.json()["codigo"] == "llm_limite" and "429" in r.json()["detalhe"]


def test_llm_nao_configurada_vira_503(tmp_path):
    def sem_chave():
        raise ValueError("Defina DEEPSEEK_API_KEY")

    r = api(tmp_path, fabrica=sem_chave).post("/sessoes")
    assert r.status_code == 503 and r.json()["codigo"] == "llm_nao_configurada"


def test_sessao_ocupada_da_409(tmp_path):
    c = api(tmp_path)
    id = c.post("/sessoes").json()["id"]
    entrada = c.app.state.registro.obter(id)
    with entrada.trava:
        r = c.post(f"/sessoes/{id}/mensagens", json={"texto": "oi"})
    assert r.status_code == 409 and r.json()["codigo"] == "sessao_ocupada"


def test_servidor_reiniciado_retoma_o_desenho_do_disco(tmp_path):
    c = api(tmp_path, *turno_que_cria_um_passo())
    id = c.post("/sessoes").json()["id"]
    c.post(f"/sessoes/{id}/mensagens", json={"texto": "x"})

    outro = api(tmp_path)                                  # servidor novo, mesma pasta
    estado = outro.get(f"/sessoes/{id}").json()
    assert estado["id"] == id and "Passo_1" in estado["processo"]["elementos"]
    assert estado["historico"][0]["texto"].startswith("Oi de novo!")    # a conversa recomeça


def test_registro_descarta_a_sessao_parada_ha_mais_tempo(tmp_path):
    registro = RegistroSessoes(lambda: LLMRoteirizado(respostas=[]), tmp_path, max_sessoes=2)
    a, b = registro.criar().sessao.id, registro.criar().sessao.id
    registro.obter(a)                                      # `a` foi usada por último
    c = registro.criar().sessao.id
    assert len(registro) == 2 and a in registro and c in registro and b not in registro
