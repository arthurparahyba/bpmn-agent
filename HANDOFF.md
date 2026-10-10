# Handoff — Desenhista de Processos (bpmn-agent)

Atualizado em 10/10/2026. Protótipo criado em uma sessão de chat; este documento passa o
bastão para continuar no Claude Code.

## 1. Objetivo do produto

Um agente que conversa com o usuário para entender um fluxo de trabalho e vai gerando um
diagrama BPMN aos poucos. Requisitos originais do dono do projeto:

- Diálogo **natural e confortável**: poucas perguntas por vez, sem termos técnicos, didático,
  objetivo, passo a passo.
- Entrevista cobre: qual o fluxo, cada passo, regras, fluxos alternativos/exceções.
- O usuário pode pedir **alterações, remoções, mudanças de fluxo** a qualquer momento e o agente
  precisa executar todas.
- Python + LangChain, LangGraph se necessário.
- **LLM barata** (ex.: Claude Sonnet/Haiku) ou, melhor ainda, **gratuita** (DeepSeek, Gemini etc.).

## 2. Estado atual — o que já funciona

| Parte | Arquivo | Status |
|---|---|---|
| Modelo do processo + 17 operações + desfazer + validação | `src/bpmn_agent/app/dominio/modelo.py` | ✅ testado |
| Exportação BPMN 2.0 com DI e layout automático | `src/bpmn_agent/app/exportacao/exportar_bpmn.py` | ✅ 0 avisos no bpmn-moddle, conferido visualmente |
| 17 tools para o LLM | `src/bpmn_agent/app/agente/ferramentas.py` | ✅ esquemas aceitos por OpenAI-compat, Anthropic e Gemini |
| Prompt de entrevista + saudação | `src/bpmn_agent/app/agente/prompt.py` | ✅ testado em conversa real com `claude-haiku-5-5` |
| Grafo LangGraph | `app/agente/grafo.py` | ✅ testado com LLM roteirizada |
| `Sessao` + gravação em disco | `app/sessao.py`, `app/persistencia.py` | ✅ testado com LLM roteirizada |
| Fábrica de LLMs (6 provedores) | `src/bpmn_agent/app/agente/llm.py` | ✅ Anthropic testado de verdade; ⚠️ os outros 5 só instanciam |
| Página web (chat + diagrama ao vivo) | `visao/web.py` | ✅ carga, um turno real e serviço desligado conferidos pelo AppTest do Streamlit; ⚠️ não conferida a olho no navegador depois da API |
| Terminal | `visao/terminal.py` | ✅ conversa real contra o servidor |
| API HTTP (rotas, esquemas, registro de sessões) | `api/` | ✅ testada com TestClient e com servidor real |
| Cliente HTTP da visão | `visao/cliente.py` | ✅ testado contra a API em memória |
| Testes | `tests/` | ✅ 37 passando (modelo, agente, API, cliente, regras de camada) |
| Documentação para desenvolvedores | `docs/`, `PASSO_A_PASSO.md` | ✅ visão geral, uma página por peça, glossário e conversa real comentada |

**Primeira conversa real feita em 10/10/2026** com Anthropic (`claude-haiku-5-5`), roteiro do
reembolso com pedidos de alteração no meio: uma pergunta por vez, sem jargão, nenhuma tool com
erro, 3 a 12 s por turno. Ajustes que saíram dela:

- `llm.py`: Anthropic sem `temperature` (os modelos Claude 5 devolvem 400 com o parâmetro).
- `modelo.py`: `raia_de()` — início, fim, decisão, paralelo e espera sem responsável herdam a raia
  do passo vizinho e não contam mais como ponto em aberto. Antes iam todos para uma raia
  "(sem responsável)" e a lista de pontos em aberto nunca esvaziava.
- `prompt.py`: não chamar `adicionar_participante` antes de usar `responsavel`; confirmar quando
  a resposta a "A ou B?" for ambígua.

DeepSeek, Gemini, Groq, OpenRouter e Ollama continuam sem teste real.

## 3. Arquitetura

Refatorado em 10/10/2026 para `src/bpmn_agent/{app,api,visao}`. A visão (página web e terminal)
é um cliente HTTP; o backend é um serviço FastAPI (`python -m bpmn_agent.api.servidor`). Caminhos
abaixo são relativos a `src/bpmn_agent/`. Estrutura, regras de camada e diagramas em
`docs/README.md`; uma página por peça em `docs/pecas/`.

```
visao/web.py / visao/terminal.py ── visao/cliente.py ══ HTTP ══► api/rotas.py ── api/registro.py
   └── Sessao (app/sessao.py) ── modelo: ModeloProcesso ── salvar() → persistencia → sessoes/<id>/{json,bpmn,md}
         └── grafo LangGraph (MessagesState, MemorySaver, thread_id = sessao.id)

START → agente ──(tool_calls?)──► ferramentas ──► agente ──► … ──► END
```

- **Nó `agente`**: monta `SystemMessage(SYSTEM_PROMPT.format(estado=modelo.resumo()))` a cada
  chamada → o LLM sempre vê o diagrama atual com ids, conexões, regras, "Pontos em aberto"
  (`modelo.problemas()`) e pendências anotadas. Histórico cortado nos últimos 14 turnos do
  usuário (`cortar_historico`, sempre começando numa `HumanMessage`). Se a conversa começar com
  mensagem do assistente (a saudação), injeta `HumanMessage("(início da conversa)")` porque
  Anthropic/Gemini exigem começar pelo usuário.
- **Nó `ferramentas`**: nó próprio (não `ToolNode`), executa as tool calls **em sequência**
  (ordem importa), converte `ErroModelo`/exceções em `ToolMessage("ERRO: ...")` para o LLM se
  corrigir, e chama `sessao.salvar()`.
- **`Sessao.enviar(texto)`** → `RespostaTurno(texto, acoes, alterados)`. `alterados` = ids de
  elementos/fluxos novos ou modificados no turno (o visualizador destaca em verde).
- **`Sessao.desfazer()`**: desfaz a última alteração sem passar pelo LLM e regrava os arquivos.
- **API** (`api/rotas.py`): `GET /saude`, `POST /sessoes`, `GET /sessoes/{id}`,
  `POST /sessoes/{id}/mensagens`, `POST /sessoes/{id}/desfazer`, `GET /sessoes/{id}/arquivos/{nome}`.
  Contrato, erros e segurança em `docs/pecas/api.md`.
- Tools são closures sobre a `sessao` (várias sessões em paralelo no mesmo processo).

### Modelo (`app/dominio/`)

- `Processo` (dataclass): `nome, descricao, participantes, elementos{id: Elemento}, fluxos[Fluxo],
  pendencias, contadores`.
- Tipos amigáveis → BPMN em `TIPOS`: `inicio, fim, tarefa, tarefa_pessoa(userTask),
  tarefa_sistema(serviceTask), tarefa_manual, envio(sendTask), decisao(exclusiveGateway),
  paralelo(parallelGateway), espera(intermediateCatchEvent+timer)`.
- Ids legíveis: `Inicio_1, Passo_3, Decisao_1, Paralelo_1, Espera_1, Fim_2, Fluxo_7`.
- `resolver(ref)`: aceita id ou nome (ignora acento/maiúsculas; substring se for única);
  ambiguidade → `ErroModelo` listando candidatos.
- Semântica-chave de `adicionar_elemento(depois_de=X)`:
  - X é decisão/paralelo → cria **novo caminho** saindo de X com `rotulo_conexao`;
  - X é passo comum → **insere** depois de X e religa o que vinha depois;
  - sem `depois_de` e sem início → cria `Inicio` automaticamente.
- Participante citado em `responsavel` que não existe é criado automaticamente.
- `remover_elemento(reconectar=True)` liga predecessores aos sucessores quando há 1 entrada ou 1 saída.
- `mover_elemento`, `conectar/desconectar/rotular_conexao`, `adicionar/remover_regra`,
  `anotar/resolver_pendencia`, `renomear/remover_participante`, `desfazer` (pilha de 100
  snapshots via `deepcopy`), `recomecar`.
- `resumo()` (para o prompt), `narrativa()` (markdown para humanos), `problemas()` (linguagem simples).

### Layout (`exportar_bpmn.py` → `calcular_layout`)

1. DFS a partir dos inícios marca **arestas de volta** (ciclos/retrabalho).
2. Coluna = caminho mais longo no grafo sem as voltas (Kahn).
3. Raias = participantes na ordem de cadastro (+ raia "(sem responsável)" se preciso; sem
   participantes → pool sem raias).
4. Linha dentro da raia: herda a linha do predecessor na mesma raia (caminho principal reto).
5. Rotas ortogonais: decisão sai por cima/baixo; voltas usam um "corredor" logo acima/abaixo da
   origem; mesma linha contorna por baixo.
6. Rótulo de decisão fica acima-à-esquerda do losango; rótulo de conexão colado na saída.

Constantes: `COL_W=170`, `ROW_H=130`, tarefa 110×80, evento 36, decisão 50.

### Visualização

`visualizador.py` gera HTML com **bpmn-js 18.31.0 via unpkg** (navigated viewer, botões de zoom,
destaque em verde por marker CSS). No Streamlit vai por `components.html`.

## 4. Decisões tomadas (e por quê)

- **Modelo Python como fonte da verdade, LLM só chama operações**: diagrama nunca inválido; XML
  determinístico; funciona com modelos fracos.
- **Grafo próprio em vez de `create_agent`/`create_react_agent`**: controle do prompt dinâmico,
  execução sequencial das tools, compatível entre versões do LangGraph.
- **DeepSeek com `thinking` desligado** (`extra_body={"thinking": {"type": "disabled"}}`): no modo
  pensamento com tools, a API exige reenviar `reasoning_content` de todos os turnos, senão 400; o
  `ChatOpenAI` do LangChain não preserva esse campo.
- **Gemini via `langchain-google-genai` nativo**, não pelo endpoint compatível com OpenAI: Gemini 3
  exige devolver "thought signatures" entre chamadas de ferramentas.
- **Gemini sem `temperature`** (o Google recomenda o padrão 1.0 nos modelos 3.x).
- **Anthropic sem `temperature`**: a API recusa o parâmetro nos modelos Claude 5.
- **Visão ↔ backend só por HTTP, sem modo "embutido"**: um caminho só para testar e manter. O custo
  é abrir dois terminais.
- **Provedor, modelo e chave só no `.env` do servidor**: saíram a seleção de modelo na tela, o campo
  de chave, `--provedor/--modelo` do terminal e `Sessao.trocar_llm`. A chave nunca trafega.
- **Sessões em memória no servidor** (`api/registro.py`), com trava por sessão, limite de 50 e
  retomada do desenho a partir de `sessoes/<id>/processo.json` quando o servidor reinicia.
- **Rota de turno síncrona** (`def`, em thread): streaming ficou para depois e é aditivo.
- **Sem autenticação, preso a `127.0.0.1`**: é protótipo local; o servidor avisa se o host mudar.

## 5. Pesquisa de LLMs (outubro/2026 — reconferir antes de mudar padrões)

| Provedor | Padrão em `llm.py` | Notas |
|---|---|---|
| DeepSeek | `deepseek-flash` | US$ 0,30 entrada / 1,20 saída por 1M no pico; metade fora do pico. Aliases `deepseek-chat`/`v4-flash` legados. |
| Gemini | `gemini-3.8-flash` | Camada grátis só Flash/Flash-Lite; dados podem ir para treino. Alternativa: `gemini-3.5-flash-lite`. |
| Groq | `openai/gpt-oss-120b` | Grátis sem cartão; limites por minuto/dia. |
| OpenRouter | `openrouter/free` | Roteia para modelo grátis com suporte a tools; ~50 req/dia sem créditos. |
| Anthropic | `claude-haiku-5-5` | `claude-sonnet-5-5` para mais qualidade. |
| Ollama | `qwen3:8b` | Local. |

## 6. Próximos passos (em ordem de prioridade)

1. **Conversa real nos outros provedores** (feita só com Anthropic). Rodar `python -m bpmn_agent.visao.terminal --debug` com DeepSeek e com
   Gemini; conduzir o exemplo do reembolso e anotar: o agente faz 1 pergunta por vez? usa jargão?
   chama as tools certas? sobra ponta solta? Ajustar `prompt.py` com base nisso.
2. **Suíte de avaliação com LLM real** (`tests/avaliacao/`, marcada para não rodar no CI):
   roteiros de usuário (ex.: compras, reembolso, onboarding, com pedidos de alteração no meio) e
   asserções sobre o modelo final (`problemas() == []`, nº de fins, rótulos das decisões) e sobre
   o estilo das respostas (nº de "?" por mensagem, lista de termos proibidos). Permite comparar
   provedores objetivamente.
3. **Streaming** da resposta: rota nova `POST /sessoes/{id}/mensagens/fluxo` (SSE) sobre
   `graph.stream(..., stream_mode=["messages","updates"])`, `Sessao.enviar_em_fluxo`, e `st.write_stream`
   na página. É aditivo: a rota síncrona continua. Modelos lentos parecem travados com o spinner.
4. **Persistência da conversa**: trocar `MemorySaver` por `SqliteSaver`
   (`langgraph-checkpoint-sqlite`) para retomar após reiniciar. Hoje só o diagrama persiste (JSON).
5. **Robustez do agente**:
   - limitar repetições quando o LLM entra em loop de erros de tool (ex.: 3 erros seguidos → pedir
     ajuda ao usuário);
   - tratar 429 com backoff/fallback automático para outro provedor;
   - suportar `paralelo` direito: hoje o modelo cria split, mas não há validação de junção.
6. **Layout**: ainda simples. Pontos fracos conhecidos: muitos caminhos saindo da mesma decisão
   para a mesma raia podem cruzar; voltas longas podem passar sobre elementos de colunas
   intermediárias; rótulos longos de conexão podem sobrepor. Evolução natural: ordenar linhas por
   baricentro dos predecessores, ou usar `bpmn-auto-layout` (npm) num passo Node opcional.
7. **Funcionalidades novas**: importar `.bpmn` existente para o agente revisar; subprocessos;
   eventos de mensagem entre participantes externos; nó "revisor" no grafo que ao final checa
   consistência e sugere melhorias; exportar PNG/SVG pelo app.
8. **Qualidade de código**: `ruff` + `mypy`, CI no GitHub Actions rodando pytest + validação do
   exemplo com bpmn-moddle.

## 7. Armadilhas conhecidas

- `pkill -f "streamlit run"` dentro de um comando que contém essa string mata o próprio shell;
  use `kill $(pgrep -f "streamli[t] run")`.
- O Streamlit roda o script inteiro a cada interação; em `st.session_state` fica só o id da sessão,
  e a cada execução a página pede o estado à API.
- A API precisa estar no ar antes da página web ou do terminal. Nunca rode com `--workers` > 1
  (sessões em memória). Com `uvicorn --reload`, cada arquivo salvo reinicia as conversas.
- Trocar de modelo = editar o `.env` e reiniciar o servidor.
- `st.components.v1.html` (usado em `visao/web.py` para o diagrama) está marcado como obsoleto no
  Streamlit instalado, que sugere `st.iframe`. Ainda funciona; trocar antes de atualizar o Streamlit.
- unpkg pode estar bloqueado em ambientes com proxy; `scripts/renderizar.py` usa o bpmn-js local
  de `scripts/node_modules`. Para o app funcionar offline, servir os assets localmente
  (`html_visualizador(base=...)` já aceita outra URL).
- `test_agente.py` usa um `BaseChatModel` roteirizado cujo `bind_tools` devolve `self`; reutilize
  esse padrão para novos testes do grafo.
- Elemento com `id` como nome de parâmetro nas tools sombreia o builtin `id` — inofensivo, mas
  não use `id()` dentro dessas funções.
