# `tests/` — os testes automáticos

[Visão geral](../README.md) · [Glossário](../glossario.md)

## Em uma frase

Conferem o modelo, o exportador, o laço do agente, a API e o cliente sem internet, sem
chave e sem custo.

## Como rodar

```bash
.venv/bin/python -m pytest -q
```

## O que cada arquivo cobre

```mermaid
flowchart LR
    subgraph tm["test_modelo.py"]
        M1["operações de edição"]
        M2["pontos em aberto"]
        M3["herança de raia"]
        M4["XML e salvar/carregar"]
    end
    subgraph ta["test_agente.py"]
        A1["turno completo com tools"]
        A2["erro de tool volta para a LLM"]
        A3["desfazer pelo agente"]
        A4["corte do histórico"]
    end
    tm --> MOD["dominio<br/>exportar_bpmn.py<br/>persistencia.py"]
    subgraph tapi["test_api.py + test_cliente.py"]
        P1["rotas e erros"]
        P2["sessões no servidor"]
        P3["cliente contra a API"]
    end
    tapi --> API["api/<br/>visao/cliente.py"]
    tc["test_camadas.py"] --> REG["regras de import<br/>de todas as camadas"]
    ta --> AG["sessao.py<br/>grafo.py<br/>ferramentas.py"]
```

### `test_modelo.py`

| Teste | O que garante |
|---|---|
| `test_primeiro_passo_cria_inicio_automaticamente` | Criar o primeiro passo sem `depois_de` cria o início sozinho. |
| `test_inserir_no_meio_religa_o_fluxo` | `A ➜ C` vira `A ➜ B ➜ C`. |
| `test_decisao_com_caminhos_rotulados_e_volta` | Decisão com dois caminhos e uma volta. |
| `test_remover_reconecta_e_desfazer_restaura` | Remover fecha o buraco; desfazer traz de volta. |
| `test_mover_elemento_troca_ordem` | Mover muda a ordem sem deixar pontas soltas. |
| `test_resolver_por_nome_sem_acento_e_ambiguidade` | Achar por nome sem acento; erro com candidatos quando ambíguo. |
| `test_fim_nao_tem_saida` | Nada pode vir depois de um fim. |
| `test_renomear_participante_atualiza_passos` | Renomear atualiza os passos do participante. |
| `test_problemas_apontam_pontas_soltas` | `problemas()` detecta o que falta. |
| `test_xml_estrutura_e_persistencia` | O XML tem a estrutura esperada; salvar e carregar preserva o processo. |
| `test_xml_sem_participantes_nao_cria_raias` | Sem participantes, não há raias. |
| `test_decisao_inicio_e_fim_sem_responsavel_herdam_a_raia` | Início, decisão e fim herdam a raia do vizinho e não viram ponto em aberto; passo comum sem responsável continua sendo cobrado. |

### `test_agente.py`

Estes testes usam a **LLM roteirizada**: a classe `LLMRoteirizado`, uma LLM falsa que
devolve, uma a uma, as respostas escritas no próprio teste. Ela também guarda em `vistos`
tudo o que recebeu, o que permite conferir o que o nó `agente` enviou.

| Teste | O que garante |
|---|---|
| `test_turno_com_ferramentas_atualiza_diagrama` | Um turno com quatro tools (uma com erro proposital) altera o processo, devolve o erro em `acoes`, marca os `alterados`, grava os arquivos, envia o estado **atualizado** na segunda chamada e começa a conversa pelo usuário. |
| `test_desfazer_pelo_agente` | A tool `desfazer` reverte a alteração do turno anterior. |
| `test_cortar_historico_comeca_em_mensagem_do_usuario` | O corte do histórico sempre começa em uma mensagem do usuário. |

## Como escrever um teste novo do agente

```python
llm = LLMRoteirizado(respostas=[
    AIMessage(content="", tool_calls=[chamada("adicionar_elemento", {"tipo": "tarefa", "nome": "A"}, 1)]),
    AIMessage(content="Pronto. E depois?"),
])
s = Sessao(llm, pasta=tmp_path)
r = s.enviar("o primeiro passo é A")
assert "Passo_1" in s.modelo.p.elementos
```

Cada item de `respostas` é uma resposta da LLM, na ordem em que será pedida. Um turno com
tools consome pelo menos duas: a que pede as tools e a que responde em texto. Use
`tmp_path` como pasta, para o teste não escrever em `sessoes/`.

### `test_api.py`

Testa as rotas com o `TestClient` do FastAPI, que chama a API em memória, sem abrir porta
nenhuma. A LLM roteirizada entra pelo parâmetro `fabrica_llm` de `criar_app`, e a pasta de
sessões é o `tmp_path` do teste.

| O que garante |
|---|
| `/saude` informa provedor e modelo, e nunca a chave. |
| Criar sessão devolve o estado com a saudação e não grava nada em disco. |
| Um turno atualiza o estado, devolve ações e alterados, e grava os arquivos. |
| Desfazer e baixar os três arquivos funcionam; nome de arquivo desconhecido é recusado. |
| Continuar a partir de um `processo.json` enviado; arquivo inválido dá 422. |
| Sessão inexistente dá 404 com frase para leigo. |
| Id fora do formato, texto vazio ou longo demais e pedido grande demais são recusados. |
| Falha da LLM vira 502 com dica; LLM não configurada vira 503. |
| Segunda mensagem durante um turno dá 409. |
| Servidor reiniciado retoma o desenho do disco. |
| O registro descarta a sessão parada há mais tempo ao passar do limite. |

### `test_cliente.py`

Roda o `ClienteApi` de verdade contra a API em memória: um roteiro completo (criar,
enviar, consultar, continuar, desfazer), um erro 404 e um serviço desligado. É este teste
que garante que o cliente e a API continuam combinando.

### `test_camadas.py`

Lê os `import` de cada arquivo de `src/bpmn_agent/` e falha se uma camada importar o que
não pode (por exemplo, `visao` importando `app`, ou `app` importando `fastapi`). A lista
das proibições está no próprio teste e reflete a tabela de [../README.md](../README.md).

## O que os testes não cobrem

| Não coberto | Como conferir hoje |
|---|---|
| O comportamento de uma LLM de verdade (tom, quantidade de perguntas, escolha das tools) | Conduzir uma conversa real pelo `python -m bpmn_agent.visao.terminal --debug`. |
| A conexão com cada provedor (`llm.py`) | Idem. |
| A qualidade visual do layout | Gerar o PNG com `scripts/renderizar.py` e olhar. |
| A validade do `.bpmn` segundo o leitor oficial | `node scripts/validar_bpmn.mjs <arquivo>`. |
| A tela do Streamlit e o laço do terminal | Subir o serviço, abrir a página web ou o terminal e usar. |
