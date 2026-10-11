"""
ModeloProcesso: o processo e todas as operações de edição.

O agente nunca escreve XML diretamente: ele chama operações de alto nível
(adicionar passo, conectar, remover...) sobre este modelo, que é a fonte
da verdade. O BPMN 2.0 é gerado a partir dele (ver exportacao/exportar_bpmn.py).

Toda operação que altera o modelo salva um "snapshot" antes, o que permite
desfazer quantas vezes for necessário. As leituras (análise e textos) ficam em
analise.py e textos.py; gravar em disco fica em app/persistencia.py.
"""
from __future__ import annotations

import copy
from dataclasses import asdict

from bpmn_agent.app.dominio import analise, textos
from bpmn_agent.app.dominio.processo import (
    GATEWAYS, PREFIXO, TIPOS, Elemento, ErroModelo, Fluxo, Processo, Sistema, _normalizar,
)


class ModeloProcesso:
    """Processo + histórico para desfazer + operações de edição."""

    LIMITE_HISTORICO = 100

    def __init__(self, processo: Processo | None = None):
        self.p = processo or Processo()
        self._historico: list[Processo] = []

    # ------------------------------------------------------------------ util
    def _snapshot(self) -> None:
        self._historico.append(copy.deepcopy(self.p))
        if len(self._historico) > self.LIMITE_HISTORICO:
            self._historico.pop(0)

    def _novo_id(self, prefixo: str) -> str:
        n = self.p.contadores.get(prefixo, 0) + 1
        self.p.contadores[prefixo] = n
        return f"{prefixo}_{n}"

    def _id_para_tipo(self, tipo_bpmn: str) -> str:
        prefixo = PREFIXO.get(tipo_bpmn, "Passo")
        return self._novo_id(prefixo)

    @staticmethod
    def _tipo_bpmn(tipo: str) -> str:
        t = _normalizar(tipo).replace(" ", "_")
        if t in TIPOS:
            return TIPOS[t]
        if tipo in TIPOS.values():
            return tipo
        raise ErroModelo(f"Tipo '{tipo}' desconhecido. Use um de: {', '.join(TIPOS)}.")

    def resolver(self, ref: str) -> Elemento:
        """Encontra um elemento pelo id ou pelo nome (sem diferenciar acentos/maiúsculas)."""
        ref = (ref or "").strip()
        if ref in self.p.elementos:
            return self.p.elementos[ref]
        alvo = _normalizar(ref)
        exatos = [e for e in self.p.elementos.values() if _normalizar(e.nome) == alvo]
        if len(exatos) == 1:
            return exatos[0]
        parciais = exatos or [e for e in self.p.elementos.values() if alvo and alvo in _normalizar(e.nome)]
        if len(parciais) == 1:
            return parciais[0]
        if not parciais:
            raise ErroModelo(f"Não encontrei nenhum elemento '{ref}'. Consulte os ids no estado atual.")
        opcoes = "; ".join(f"{e.id} ({e.nome})" for e in parciais)
        raise ErroModelo(f"'{ref}' é ambíguo. Use o id de um destes: {opcoes}.")

    def entradas(self, elem_id: str) -> list[Fluxo]:
        return [f for f in self.p.fluxos if f.destino == elem_id]

    def saidas(self, elem_id: str) -> list[Fluxo]:
        return [f for f in self.p.fluxos if f.origem == elem_id]

    def _fluxo_entre(self, origem: str, destino: str) -> Fluxo | None:
        return next((f for f in self.p.fluxos if f.origem == origem and f.destino == destino), None)

    def _resolver_participante(self, nome: str) -> str:
        nome = (nome or "").strip()
        if not nome:
            return ""
        for p in self.p.participantes:
            if _normalizar(p) == _normalizar(nome):
                return p
        self._recusar_se_for_sistema(nome, "responsável")
        # participante novo é criado automaticamente: reduz chamadas do agente
        self.p.participantes.append(nome)
        return nome

    # --------------------------------------------------------- processo
    def definir_processo(self, nome: str = "", descricao: str = "") -> str:
        self._snapshot()
        if nome:
            self.p.nome = nome.strip()
        if descricao:
            self.p.descricao = descricao.strip()
        return f"Processo agora se chama '{self.p.nome}'."

    # --------------------------------------------------------- participantes
    def adicionar_participante(self, nome: str) -> str:
        if not nome.strip():
            raise ErroModelo("Informe o nome do participante.")
        if any(_normalizar(p) == _normalizar(nome) for p in self.p.participantes):
            return f"'{nome}' já existe."
        self._recusar_se_for_sistema(nome, "participante")
        self._snapshot()
        self.p.participantes.append(nome.strip())
        return f"Participante '{nome.strip()}' adicionado."

    def renomear_participante(self, atual: str, novo: str) -> str:
        atual_ok = next((p for p in self.p.participantes if _normalizar(p) == _normalizar(atual)), None)
        if not atual_ok:
            raise ErroModelo(f"Participante '{atual}' não existe. Existentes: {self.p.participantes}")
        self._recusar_se_for_sistema(novo, "participante")
        self._snapshot()
        i = self.p.participantes.index(atual_ok)
        self.p.participantes[i] = novo.strip()
        for e in self.p.elementos.values():
            if e.responsavel == atual_ok:
                e.responsavel = novo.strip()
        return f"'{atual_ok}' renomeado para '{novo.strip()}'."

    def remover_participante(self, nome: str) -> str:
        alvo = next((p for p in self.p.participantes if _normalizar(p) == _normalizar(nome)), None)
        if not alvo:
            raise ErroModelo(f"Participante '{nome}' não existe.")
        self._snapshot()
        self.p.participantes.remove(alvo)
        afetados = [e.nome for e in self.p.elementos.values() if e.responsavel == alvo]
        for e in self.p.elementos.values():
            if e.responsavel == alvo:
                e.responsavel = ""
        extra = f" Passos que ficaram sem responsável: {afetados}." if afetados else ""
        return f"Participante '{alvo}' removido.{extra}"

    # --------------------------------------------------------- sistemas
    def _achar_sistema(self, nome: str) -> Sistema | None:
        return next((s for s in self.p.sistemas if _normalizar(s.nome) == _normalizar(nome)), None)

    def _recusar_se_for_sistema(self, nome: str, como: str) -> None:
        if self._achar_sistema(nome):
            raise ErroModelo(f"'{nome}' é um sistema do catálogo, não uma pessoa ou área; não pode ser {como}. "
                             "Quem faz o passo vai em `responsavel`; o sistema usado vai em `sistema`.")

    def _resolver_sistema(self, nome: str) -> str:
        """Nome canônico de um sistema; se ainda não existe, é cadastrado (como acontece com participantes)."""
        nome = (nome or "").strip()
        if not nome:
            return ""
        s = self._achar_sistema(nome)
        if s:
            return s.nome
        if any(_normalizar(p) == _normalizar(nome) for p in self.p.participantes):
            raise ErroModelo(f"'{nome}' já é um participante (quem faz passos). Se for mesmo um sistema, "
                             "use outro nome para ele ou remova o participante antes.")
        self.p.sistemas.append(Sistema(nome=nome))
        return nome

    @staticmethod
    def _lista(texto: str) -> list[str]:
        return [x.strip() for x in (texto or "").replace("\n", ";").split(";") if x.strip()]

    def _guardar_operacao(self, sistema: str, operacao: str) -> None:
        s = self._achar_sistema(sistema)
        if s and operacao and not any(_normalizar(o) == _normalizar(operacao) for o in s.operacoes):
            s.operacoes.append(operacao)

    def cadastrar_sistema(self, nome: str, descricao: str = "", integracao: str = "", operacoes: str = "") -> str:
        """Cadastra um sistema do processo ou completa um que já existe (campos vazios não mudam)."""
        if not nome.strip():
            raise ErroModelo("Informe o nome do sistema.")
        existente = self._achar_sistema(nome)
        if not existente and any(_normalizar(p) == _normalizar(nome) for p in self.p.participantes):
            raise ErroModelo(f"'{nome}' já é um participante (quem faz passos). Se for mesmo um sistema, "
                             "use outro nome para ele ou remova o participante antes.")
        self._snapshot()
        s = existente or Sistema(nome=nome.strip())
        if not existente:
            self.p.sistemas.append(s)
        if descricao:
            s.descricao = descricao.strip()
        if integracao:
            s.integracao = integracao.strip()
        for o in self._lista(operacoes):
            if not any(_normalizar(x) == _normalizar(o) for x in s.operacoes):
                s.operacoes.append(o)
        return f"Sistema '{s.nome}' {'atualizado' if existente else 'cadastrado'} ({len(s.operacoes)} operação(ões) conhecida(s))."

    def remover_sistema(self, nome: str) -> str:
        s = self._achar_sistema(nome)
        if not s:
            raise ErroModelo(f"Sistema '{nome}' não existe. Existentes: {[x.nome for x in self.p.sistemas]}")
        self._snapshot()
        self.p.sistemas.remove(s)
        afetados = [e.nome for e in self.p.elementos.values() if e.sistema == s.nome]
        for e in self.p.elementos.values():
            if e.sistema == s.nome:
                e.sistema = e.operacao = ""
        extra = f" Passos que ficaram sem sistema: {afetados}." if afetados else ""
        return f"Sistema '{s.nome}' removido.{extra}"

    # --------------------------------------------------------- elementos
    def adicionar_elemento(
        self,
        tipo: str,
        nome: str,
        responsavel: str = "",
        depois_de: str = "",
        rotulo_conexao: str = "",
        descricao: str = "",
        sistema: str = "",
        operacao: str = "",
    ) -> str:
        """
        Cria um elemento. Se `depois_de` for informado:
          - se o anterior for uma decisão/paralelo: cria um NOVO caminho saindo dele (com rótulo);
          - senão: o novo elemento é INSERIDO logo depois do anterior (o que vinha depois
            dele passa a vir depois do novo).
        """
        tipo_bpmn = self._tipo_bpmn(tipo)
        anterior = self.resolver(depois_de) if depois_de else None
        if anterior and anterior.tipo == "endEvent":
            raise ErroModelo(f"'{anterior.nome}' é um fim; nada pode vir depois dele. "
                             "Remova o fim ou conecte a partir do passo anterior a ele.")
        if tipo_bpmn == "startEvent" and anterior:
            raise ErroModelo("Um início não pode vir depois de outro elemento.")

        self._snapshot()
        mensagens = []

        # Conveniência: primeiro passo sem início -> cria o início automaticamente
        if (not anterior and tipo_bpmn != "startEvent"
                and not any(e.tipo == "startEvent" for e in self.p.elementos.values())):
            ini = Elemento(id=self._id_para_tipo("startEvent"), tipo="startEvent", nome="Início",
                           responsavel=self._resolver_participante(responsavel))
            self.p.elementos[ini.id] = ini
            anterior = ini
            mensagens.append(f"Criei também o início ({ini.id}).")

        novo = Elemento(
            id=self._id_para_tipo(tipo_bpmn),
            tipo=tipo_bpmn,
            nome=nome.strip(),
            responsavel=self._resolver_participante(responsavel),
            descricao=descricao.strip(),
            sistema=self._resolver_sistema(sistema),
            operacao=operacao.strip() if sistema.strip() else "",
        )
        self._guardar_operacao(novo.sistema, novo.operacao)
        self.p.elementos[novo.id] = novo

        if anterior:
            if anterior.tipo in GATEWAYS:
                self._conectar(anterior.id, novo.id, rotulo_conexao)
            else:
                saidas_antigas = self.saidas(anterior.id)
                if saidas_antigas and tipo_bpmn == "endEvent":
                    # não dá para inserir um fim no meio: cria um ramo extra
                    self._conectar(anterior.id, novo.id, rotulo_conexao)
                    mensagens.append("Atenção: o passo anterior agora tem mais de uma saída sem decisão.")
                else:
                    for f in saidas_antigas:  # religa: anterior -> novo -> (antigos destinos)
                        f.origem = novo.id
                    self._conectar(anterior.id, novo.id, rotulo_conexao)
        mensagens.insert(0, f"Criado {novo.id} '{novo.nome}'" + (f" depois de {anterior.id}" if anterior else "") + ".")
        return " ".join(mensagens)

    def atualizar_elemento(self, ref: str, nome: str = "", tipo: str = "",
                           responsavel: str = "", descricao: str = "",
                           sistema: str = "", operacao: str = "") -> str:
        e = self.resolver(ref)
        novo_tipo = self._tipo_bpmn(tipo) if tipo else None
        if operacao and not (sistema or e.sistema):
            raise ErroModelo("Informe o `sistema` ao indicar a `operacao`.")
        self._snapshot()
        mudou = []
        if nome:
            e.nome = nome.strip(); mudou.append("nome")
        if novo_tipo and novo_tipo != e.tipo:
            e.tipo = novo_tipo; mudou.append("tipo")
        if responsavel:
            e.responsavel = "" if _normalizar(responsavel) in {"nenhum", "-"} else self._resolver_participante(responsavel)
            mudou.append("responsável")
        if descricao:
            e.descricao = descricao.strip(); mudou.append("descrição")
        if sistema:
            if _normalizar(sistema) in {"nenhum", "-"}:
                e.sistema = e.operacao = ""
            else:
                e.sistema = self._resolver_sistema(sistema)
            mudou.append("sistema")
        if operacao:
            e.operacao = "" if _normalizar(operacao) in {"nenhuma", "nenhum", "-"} else operacao.strip()
            self._guardar_operacao(e.sistema, e.operacao)
            mudou.append("operação")
        return f"{e.id} atualizado ({', '.join(mudou) or 'nada mudou'})."

    def remover_elemento(self, ref: str, reconectar: bool = True) -> str:
        """Remove o elemento. Com reconectar=True, quem vinha antes passa a ligar em quem vinha depois."""
        e = self.resolver(ref)
        self._snapshot()
        ent, sai = self.entradas(e.id), self.saidas(e.id)
        self.p.fluxos = [f for f in self.p.fluxos if e.id not in (f.origem, f.destino)]
        del self.p.elementos[e.id]
        religados = []
        if reconectar and ent and sai and (len(ent) == 1 or len(sai) == 1):
            for fe in ent:
                for fs in sai:
                    if fe.origem != fs.destino and not self._fluxo_entre(fe.origem, fs.destino):
                        self._conectar(fe.origem, fs.destino, fe.rotulo or fs.rotulo)
                        religados.append(f"{fe.origem}->{fs.destino}")
        msg = f"Removido {e.id} '{e.nome}'."
        if religados:
            msg += f" Religado: {', '.join(religados)}."
        elif ent or sai:
            msg += " Ficaram pontas soltas; verifique as pendências do diagrama."
        return msg

    def mover_elemento(self, ref: str, depois_de: str) -> str:
        """Tira o elemento de onde está (religando o fluxo) e o coloca logo depois de outro."""
        e = self.resolver(ref)
        anterior = self.resolver(depois_de)
        if anterior.id == e.id:
            raise ErroModelo("Não dá para mover um elemento para depois dele mesmo.")
        if e.tipo in GATEWAYS:
            raise ErroModelo("Para mover uma decisão, remova e recrie seus caminhos.")
        self._snapshot()
        # 1) tira do lugar, religando
        ent, sai = self.entradas(e.id), self.saidas(e.id)
        self.p.fluxos = [f for f in self.p.fluxos if e.id not in (f.origem, f.destino)]
        if len(ent) >= 1 and len(sai) == 1:
            for fe in ent:
                if not self._fluxo_entre(fe.origem, sai[0].destino):
                    self._conectar(fe.origem, sai[0].destino, fe.rotulo)
        # 2) insere depois do novo anterior
        if anterior.tipo in GATEWAYS:
            self._conectar(anterior.id, e.id, "")
        else:
            for f in self.saidas(anterior.id):
                f.origem = e.id
            self._conectar(anterior.id, e.id, "")
        return f"{e.id} '{e.nome}' agora vem logo depois de {anterior.id} '{anterior.nome}'."

    # --------------------------------------------------------- conexões
    def _conectar(self, origem: str, destino: str, rotulo: str = "") -> Fluxo:
        f = Fluxo(self._novo_id("Fluxo"), origem, destino, (rotulo or "").strip())
        self.p.fluxos.append(f)
        return f

    def conectar(self, origem: str, destino: str, rotulo: str = "") -> str:
        o, d = self.resolver(origem), self.resolver(destino)
        if o.tipo == "endEvent":
            raise ErroModelo(f"'{o.nome}' é um fim e não pode ter saída.")
        if d.tipo == "startEvent":
            raise ErroModelo(f"'{d.nome}' é um início e não pode ter entrada.")
        if o.id == d.id:
            raise ErroModelo("Não dá para ligar um elemento nele mesmo.")
        existente = self._fluxo_entre(o.id, d.id)
        if existente:
            if rotulo and rotulo != existente.rotulo:
                self._snapshot()
                existente.rotulo = rotulo.strip()
                return f"Conexão {o.id}->{d.id} já existia; rótulo atualizado."
            return f"Conexão {o.id}->{d.id} já existe."
        self._snapshot()
        self._conectar(o.id, d.id, rotulo)
        return f"Conectado {o.id} -> {d.id}" + (f" ('{rotulo}')." if rotulo else ".")

    def desconectar(self, origem: str, destino: str) -> str:
        o, d = self.resolver(origem), self.resolver(destino)
        f = self._fluxo_entre(o.id, d.id)
        if not f:
            raise ErroModelo(f"Não existe conexão de {o.id} para {d.id}.")
        self._snapshot()
        self.p.fluxos.remove(f)
        return f"Conexão {o.id} -> {d.id} removida."

    def rotular_conexao(self, origem: str, destino: str, rotulo: str) -> str:
        o, d = self.resolver(origem), self.resolver(destino)
        f = self._fluxo_entre(o.id, d.id)
        if not f:
            raise ErroModelo(f"Não existe conexão de {o.id} para {d.id}.")
        self._snapshot()
        f.rotulo = rotulo.strip()
        return f"Rótulo da conexão {o.id} -> {d.id} agora é '{f.rotulo}'."

    # --------------------------------------------------------- regras
    def adicionar_regra(self, ref: str, regra: str) -> str:
        e = self.resolver(ref)
        self._snapshot()
        e.regras.append(regra.strip())
        return f"Regra registrada em {e.id} (agora são {len(e.regras)})."

    def remover_regra(self, ref: str, numero: int) -> str:
        e = self.resolver(ref)
        if not 1 <= numero <= len(e.regras):
            raise ErroModelo(f"{e.id} tem {len(e.regras)} regra(s); número {numero} inválido.")
        self._snapshot()
        r = e.regras.pop(numero - 1)
        return f"Regra removida de {e.id}: '{r}'."

    # --------------------------------------------------------- pendências
    def anotar_pendencia(self, texto: str) -> str:
        self._snapshot()
        self.p.pendencias.append(texto.strip())
        return f"Pendência {len(self.p.pendencias)} anotada."

    def resolver_pendencia(self, numero: int) -> str:
        if not 1 <= numero <= len(self.p.pendencias):
            raise ErroModelo("Número de pendência inválido.")
        self._snapshot()
        t = self.p.pendencias.pop(numero - 1)
        return f"Pendência resolvida: '{t}'."

    # --------------------------------------------------------- histórico
    def desfazer(self) -> str:
        if not self._historico:
            return "Não há nada para desfazer."
        self.p = self._historico.pop()
        return "Última alteração desfeita."

    def recomecar(self) -> str:
        self._snapshot()
        self.p = Processo()
        return "Diagrama apagado. Começando do zero (dá para desfazer)."

    # --------------------------------------------------------- leituras
    def problemas(self) -> list[str]:
        """Pontos em aberto, em linguagem simples, que o agente usa para guiar a entrevista."""
        return analise.problemas(self)

    def raia_de(self, elem_id: str) -> str:
        """Participante em cuja raia o elemento é desenhado."""
        return analise.raia_de(self, elem_id)

    def resumo(self) -> str:
        """Representação textual compacta do diagrama, injetada no prompt a cada turno."""
        return textos.resumo(self)

    def narrativa(self) -> str:
        """Descrição do fluxo em linguagem natural (para revisão com o usuário / documentação)."""
        return textos.narrativa(self)

    # --------------------------------------------------------- conversão
    def para_dict(self) -> dict:
        return asdict(self.p)

    @classmethod
    def de_dict(cls, d: dict) -> "ModeloProcesso":
        p = Processo(
            nome=d.get("nome", "Novo processo"),
            descricao=d.get("descricao", ""),
            participantes=list(d.get("participantes", [])),
            sistemas=[Sistema(**s) for s in d.get("sistemas", [])],
            elementos={k: Elemento(**v) for k, v in d.get("elementos", {}).items()},
            fluxos=[Fluxo(**f) for f in d.get("fluxos", [])],
            pendencias=list(d.get("pendencias", [])),
            contadores=dict(d.get("contadores", {})),
        )
        return cls(p)
