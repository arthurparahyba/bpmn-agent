# CLAUDE.md

Agente conversacional (LangChain + LangGraph) que entrevista uma pessoa leiga sobre um
processo de trabalho e desenha um BPMN 2.0 aos poucos. Leia `HANDOFF.md` para o estado
atual, decisões tomadas e próximos passos, e `docs/README.md` para a arquitetura.

## Comandos

```bash
pip install -r requirements.txt                       # instala o projeto em modo editável (pyproject.toml)
python -m pytest -q                                   # testes (sem API; usam LLM roteirizada)
./rodar.sh                                            # jeito simples: sobe o serviço + a página web (Ctrl+C encerra)
./rodar.sh terminal                                   # idem, com a conversa no terminal
python -m bpmn_agent.api.servidor                     # ou cada parte à mão: o serviço (lê o .env); deixe no ar
streamlit run src/bpmn_agent/visao/web.py             # página web (outro terminal; precisa do serviço)
python -m bpmn_agent.visao.terminal --debug           # ou a conversa no terminal (idem)
python scripts/gerar_exemplo.py exemplos/reembolso.bpmn   # monta exemplo sem LLM
cd scripts && npm install                             # uma vez, para os dois abaixo
node scripts/validar_bpmn.mjs <arquivo.bpmn>          # valida no parser oficial do bpmn.io
python scripts/renderizar.py <in.bpmn> <out.png>      # renderiza com bpmn-js (precisa playwright+chromium)
```

## Estrutura e camadas

```
src/bpmn_agent/
  visao/        cliente: web.py (Streamlit), terminal.py, cliente.py (HTTP), visualizador.py
  api/          serviço HTTP: servidor.py, rotas.py, esquemas.py, registro.py
  app/          backend
    sessao.py         uma conversa; é o que a API chama
    persistencia.py   único lugar que grava/lê arquivos
    agente/           grafo.py, ferramentas.py, prompt.py, llm.py
    dominio/          processo.py (dados), modelo.py (edição), analise.py, textos.py
    exportacao/       exportar_bpmn.py
```

- Imports sempre absolutos (`from bpmn_agent.app...`). Rode os comandos da raiz do projeto.
- A visão e o backend são processos separados e só se falam por HTTP (`visao/cliente.py` → `api/`).
- `visao` nunca importa `bpmn_agent.app` nem `bpmn_agent.api`. Dado novo na tela = campo novo em
  `EstadoSessao` (`api/esquemas.py`).
- `app` nunca importa `api`, `visao`, `fastapi`, `httpx`, `streamlit` nem `dotenv`.
- `api` importa `app`, nunca `visao`. Só `api/servidor.py` chama `load_dotenv()`.
- Provedor, modelo e chave da LLM ficam só no `.env` do servidor: não há seleção de modelo na
  tela nem na API, e nenhuma rota recebe ou devolve chave.
- A API roda com um worker só (sessões em memória), rotas `def` (não `async`), sem autenticação
  e presa a `127.0.0.1`. Nenhuma rota aceita caminho de arquivo vindo do cliente.
- Mudou rota ou esquema? Atualize junto `visao/cliente.py`, os testes e `docs/pecas/api.md`.
- `tests/test_camadas.py` confere as regras de import; mantenha-o em dia ao criar pastas.
- `app/dominio` só usa a biblioteca padrão: sem LLM, sem tela, sem arquivos.
- `app/agente` só conhece `dominio`; não importa `sessao`, `persistencia` nem `exportacao`.
- Em `dominio`, só `modelo.py` altera o processo; `analise.py` e `textos.py` apenas leem.
- Mudou a estrutura ou o comportamento de uma peça? Atualize `docs/pecas/` junto.

## Regras do projeto

- **Código, identificadores, prompts, mensagens e docs em português do Brasil.** A UI e o agente
  falam com leigos: nada de jargão (BPMN, gateway, raia, evento) nos textos para o usuário final.
- **O LLM nunca gera XML.** Toda mudança no diagrama passa por métodos de `ModeloProcesso`
  (`app/dominio/modelo.py`), expostos como tools em `app/agente/ferramentas.py`. Nova capacidade de edição =
  método no modelo (com `self._snapshot()` antes de mutar) + tool + teste.
- Erros de uso viram `ErroModelo` com mensagem que ensina o LLM a se corrigir (ex.: listar ids
  candidatos). Não lance exceções genéricas dentro do modelo.
- Esquemas de tools simples: strings com default `""` em vez de `Optional`/`None`
  (modelos baratos erram menos). Descrições dos parâmetros via `Annotated`.
- Depois de mexer em `exportar_bpmn.py`: rode os testes, `validar_bpmn.mjs` (tem que dar 0 avisos)
  e **olhe** o PNG de `renderizar.py` — layout bom só se confirma vendo.
- Nomes de modelos de LLM mudam rápido: ficam só em `PROVEDORES` (`llm.py`) e são sobrescrevíveis
  por `LLM_MODELO`. Confira na documentação do provedor antes de trocar um padrão.
- Nunca commitar `.env` nem `sessoes/`.
