# `src/bpmn_agent/app/sessao.py` e `persistencia.py` — a conversa e seus arquivos

[Visão geral](../README.md) · [Glossário](../glossario.md)

## Em uma frase

`Sessao` é uma conversa completa: a [API](api.md) entrega o texto do usuário e recebe a
resposta pronta. `persistencia.py` é o único lugar do backend que grava e lê arquivos.

## Responsabilidade

| Arquivo | Responsabilidade |
|---|---|
| `sessao.py` | Representar uma conversa completa (`Sessao`) e entregar o resultado de cada turno (`RespostaTurno`). |
| `persistencia.py` | Gravar e ler o processo em disco. |

A `Sessao` não tem regra de processo e não fala com a LLM diretamente. Ela **junta** as
outras partes do backend:

```mermaid
flowchart TB
    V["api<br/>rotas.py"] --> S["Sessao"]
    S --> G["agente/grafo.py<br/>roda o turno"]
    S --> M["dominio<br/>guarda o processo"]
    S --> E["exportacao<br/>gera o .bpmn"]
    S --> P["persistencia.py<br/>grava os arquivos"]
```

## A classe `Sessao`

Uma `Sessao` = uma conversa = um processo.

```mermaid
flowchart TB
    subgraph Sessao
        ID["id<br/>8 caracteres aleatórios"]
        MO["modelo<br/>ModeloProcesso"]
        GR["grafo<br/>os dois nós"]
        CK["checkpointer<br/>guarda as mensagens"]
        PA["pasta<br/>sessoes/id/"]
    end
```

| Método | O que faz |
|---|---|
| `__init__(llm, pasta, modelo, id)` | Cria o grafo e registra a saudação como primeira mensagem. Se veio um `modelo` já preenchido, a saudação é "Oi de novo! Carreguei o processo...". |
| `enviar(texto)` | Roda um turno. Devolve `RespostaTurno`. |
| `pedir_confirmacao(motivo, pedido)` | Chamado pela tool de mesmo nome. Guarda em `pendente` um pedido incoerente com o desenho, sem aplicá-lo. No turno da confirmação, recusa novo pedido de confirmação. |
| `desfazer()` | Desfaz a última alteração do processo, sem passar pela LLM, e regrava os arquivos. |
| `mensagens()` | Todas as mensagens guardadas, incluindo pedidos e resultados de tools. |
| `historico_visivel()` | Só as falas, como pares `(papel, texto)`. É o que a interface mostra. |
| `bpmn_xml()` | O `.bpmn` do processo atual. |
| `salvar()` | Pede a `persistencia.salvar_artefatos` que grave os três arquivos na pasta da sessão. |

### `enviar` por dentro

```mermaid
flowchart TB
    A["1. Tira uma 'foto' do processo<br/>(elementos e conexões)"] --> B["2. Roda o grafo com<br/>a mensagem do usuário"]
    B --> C["3. Separa as mensagens novas<br/>deste turno"]
    C --> D["4. acoes = resultados das tools"]
    C --> E["5. texto = última fala da LLM"]
    C --> F["6. alterados = o que mudou<br/>em relação à 'foto'"]
    D --> G["RespostaTurno"]
    E --> G
    F --> G
```

O passo 2 é onde tudo acontece; o detalhe está em [grafo.md](grafo.md).

### Conferência do que mudou de fato

Se o turno chamou alguma tool, a `Sessao` compara o processo com a "foto" do início do turno
(`resumo_mudancas`) e **anexa a frase ao fim da fala do agente**, depois de um marcador (`🔎`). A fala
anexada vai para o histórico, então a tela a mostra sem mudar a API. Isso existe porque a LLM pode
dizer "detalhei a cotação em paralelo" tendo só reescrito uma descrição: o resumo mostra o que
realmente mudou (ex.: `alterado(s): ... (a descrição)` sem nenhum item novo). Turnos sem tools (só
conversa) não ganham o resumo. Antes de cada chamada, `grafo.py` remove esse trecho das falas que
vão para a LLM (`sem_resumo_de_mudancas`), para ela não passar a imitá-lo.

### Aviso de conclusão (`aviso_de_conclusao`)

Se a fala do agente **não faz pergunta** (está encerrando, por exemplo "Perfeito! Está documentado") e o diagrama
ainda tem pontos em aberto (`problemas()`), o código anexa à fala, depois do marcador `⚠️`, "Ainda há pontos em
aberto, então o desenho não está completo: ...". Os ids técnicos saem do texto. Vale a partir de 3 elementos.
Como o resumo 🔎, é só para a pessoa: `sem_resumo_de_mudancas` tira os dois marcadores antes de a LLM ler o
histórico. É a trava contra o agente dar o processo por concluído com coisa pendente.

### Pedido em dúvida (`pendente`)

Quando a LLM acha que um pedido não combina com o desenho, ela chama a tool `pedir_confirmacao`
em vez das tools de edição e pergunta à pessoa. A `Sessao` guarda o pedido em `pendente` e
`enviar` trata a resposta seguinte **no código, sem a LLM decidir**:

| Resposta da pessoa | O que acontece |
|---|---|
| "sim", "confirmo", "pode"... (`CONFIRMACOES`) | O pedido guardado vai em `pedido_liberado` e o prompt do turno ganha a seção "Confirmação recebida"; a LLM aplica. Nesse turno, `pedir_confirmacao` é recusada. |
| "não", "cancelar", "deixa"... (`CANCELAMENTOS`) | Descarta a pendência e responde "não mudei nada", sem chamar a LLM. |
| qualquer outra coisa | Descarta a pendência e trata a mensagem como um pedido novo. |

Enquanto `pendente` existe, `grafo.py` devolve erro para qualquer tool que não seja
`pedir_confirmacao`: nada muda no diagrama antes da decisão. A pendência fica só na memória
(como a pilha do desfazer) e não é gravada em arquivo. Detectar a incoerência continua sendo
trabalho da LLM (probabilístico); o código só garante que nada é aplicado antes da decisão.

### `RespostaTurno`

| Campo | Conteúdo |
|---|---|
| `texto` | A última fala da LLM com conteúdo. Se ela só chamou tools e não escreveu nada, entra um texto padrão ("Pronto, atualizei o desenho. O que acontece em seguida?"). |
| `acoes` | Uma linha por tool executada, no formato `nome_da_tool: resultado`. É o que o modo de depuração mostra. |
| `alterados` | Ids de elementos novos ou modificados e de conexões novas. A interface usa essa lista para destacar em verde o que mudou. |

## `persistencia.py`

Três funções:

| Função | O que faz |
|---|---|
| `salvar_modelo(modelo, caminho)` | Grava o processo como JSON. |
| `carregar_modelo(caminho)` | Lê um JSON e devolve um `ModeloProcesso`. |
| `salvar_artefatos(modelo, pasta)` | Grava os três arquivos de uma sessão. |

Os três arquivos:

| Arquivo | Conteúdo | De onde vem |
|---|---|---|
| `processo.json` | O processo completo. É o que se carrega para continuar depois. | `modelo.para_dict()` |
| `processo.bpmn` | O diagrama, para abrir em outras ferramentas. | `gerar_bpmn_xml(modelo)` |
| `processo.md` | A descrição em texto. | `modelo.narrativa()` |

A pilha do desfazer e as mensagens da conversa **não** são gravadas.

O domínio não sabe gravar a si mesmo: `ModeloProcesso` só converte para dicionário
(`para_dict`) e de volta (`de_dict`). Quem transforma isso em arquivo é este módulo.

## Quem usa e quem é usado

- **Usado por**: `api/rotas.py` e `api/registro.py` (que cria e guarda as sessões),
  `scripts/gerar_exemplo.py` (só a persistência) e os testes.
- **`sessao.py` usa**: `agente/grafo.py`, `agente/prompt.py` (a saudação), `dominio`,
  `exportacao` e `persistencia.py`.
- **`persistencia.py` usa**: `dominio` e `exportacao`.

## Cuidados ao alterar

- A `Sessao` não pode importar nada de `api` nem de `visao`.
- A pasta padrão (`sessoes`) é relativa à pasta de onde o servidor foi iniciado. Suba o
  servidor sempre da raiz do projeto.
- A LLM é a mesma do começo ao fim da sessão: vem do `.env` do servidor.
- O checkpointer é o `MemorySaver`: a conversa some ao reiniciar o programa.
- As tools recebem a `sessao` e buscam `sessao.modelo` a cada chamada, em vez de guardar
  o modelo. Assim cada sessão mexe só no próprio processo, mesmo com várias no ar.
