"""
Interface web: chat à esquerda, diagrama BPMN ao vivo à direita.
Conversa com o serviço pela API (suba antes: python -m bpmn_agent.api.servidor).

    streamlit run src/bpmn_agent/visao/web.py
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from bpmn_agent.visao.cliente import MENSAGEM_FORA_DO_AR, ApiForaDoAr, ClienteApi, ErroDaApi
from bpmn_agent.visao.visualizador import html_visualizador

load_dotenv()    # só para BPMN_API_URL; o modelo e a chave são assunto do servidor
st.set_page_config(page_title="Desenhista de Processos", page_icon="🧭", layout="wide")

st.markdown("""<style>
  .block-container { padding-top: 1.6rem; }
  [data-testid="stChatMessage"] { padding: .35rem .6rem; }
</style>""", unsafe_allow_html=True)


@st.cache_resource
def _cliente() -> ClienteApi:
    return ClienteApi()


cliente = _cliente()


def nova_sessao(processo: dict | None = None) -> dict:
    estado = cliente.criar_sessao(processo)
    st.session_state.sessao_id = estado["id"]
    st.session_state.destaque = []
    st.session_state.acoes = []
    return estado


def carregar_estado() -> dict:
    """Estado da conversa atual; cria uma nova se ainda não há ou se o serviço não a conhece mais."""
    if "sessao_id" in st.session_state:
        try:
            return cliente.estado(st.session_state.sessao_id)
        except ErroDaApi as e:
            if e.status != 404:
                raise
            st.toast("A conversa anterior foi encerrada. Comecei uma nova.")
    return nova_sessao()


def parar_com_aviso(mensagem: str, detalhe: str = "") -> None:
    st.title("🧭 Desenhista de Processos")
    st.warning(mensagem)
    if detalhe:
        st.caption(detalhe)
    st.button("Tentar de novo")
    st.stop()


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    if st.button("🆕 Nova conversa", use_container_width=True):
        st.session_state.pop("sessao_id", None)

    st.divider()
    st.subheader("📂 Continuar um processo")
    arq = st.file_uploader("Arquivo .json salvo antes", type=["json"], label_visibility="collapsed")
    arquivo_novo = arq is not None and st.session_state.get("arquivo_carregado") != arq.file_id

    mostrar_acoes = st.toggle("Mostrar o que o agente fez (depuração)", value=False)

# ------------------------------------------------------------------ sessão
try:
    if arquivo_novo:
        try:
            nova_sessao(json.loads(arq.getvalue()))
            st.session_state.arquivo_carregado = arq.file_id
        except (ValueError, ErroDaApi) as e:
            st.sidebar.error(f"Não consegui abrir: {getattr(e, 'mensagem', e)}")
    estado = carregar_estado()
    saude = cliente.saude()
except ApiForaDoAr:
    parar_com_aviso(MENSAGEM_FORA_DO_AR, f"Endereço: `{cliente.base_url}` · Para ligar: `python -m bpmn_agent.api.servidor`")
except ErroDaApi as e:
    parar_com_aviso(e.mensagem, e.detalhe)

st.sidebar.caption(f"Modelo em uso: {saude['provedor']} / {saude['modelo']}")
sessao_id = estado["id"]

# ------------------------------------------------------------------ layout
st.title(f"🧭 {estado['nome'] if not estado['vazio'] or estado['nome'] != 'Novo processo' else 'Desenhista de Processos'}")
col_chat, col_diag = st.columns([5, 7], gap="large")

with col_chat:
    caixa = st.container(height=640)
    with caixa:
        for m in estado["historico"]:
            with st.chat_message(m["papel"], avatar="🧑" if m["papel"] == "user" else "🧭"):
                st.markdown(m["texto"])
        if mostrar_acoes and st.session_state.get("acoes"):
            with st.expander("Ações do último turno", expanded=True):
                for a in st.session_state.acoes:
                    st.code(a, language=None)

with col_diag:
    xml = estado["bpmn_xml"]
    if not estado["vazio"]:
        components.html(html_visualizador(xml, altura=470, destacar=st.session_state.get("destaque")),
                        height=490)
    else:
        st.info("O desenho vai aparecer aqui conforme você conta como o processo funciona.")

    aba1, aba2, aba3 = st.tabs(["📝 Descrição", "❓ Em aberto", "⬇️ Baixar"])
    with aba1:
        st.markdown(estado["narrativa"])
    with aba2:
        abertos = estado["em_aberto"] + [f"Pendência: {t}" for t in estado["pendencias"]]
        st.markdown("\n".join(f"- {t}" for t in abertos) if abertos else "Nada em aberto 🎉")
    with aba3:
        base = (estado["nome"] or "processo").strip().replace(" ", "_").lower()
        st.download_button("Diagrama BPMN (.bpmn)", xml, f"{base}.bpmn", "application/xml",
                           use_container_width=True,
                           help="Abre no bpmn.io, Camunda Modeler, Bizagi, Signavio...")
        st.download_button("Projeto para continuar depois (.json)",
                           json.dumps(estado["processo"], ensure_ascii=False, indent=2),
                           f"{base}.json", "application/json", use_container_width=True)
        st.download_button("Descrição em texto (.md)", estado["narrativa"], f"{base}.md", "text/markdown",
                           use_container_width=True)
        st.caption(f"Também salvo automaticamente em `{estado['pasta']}`")

# ------------------------------------------------------------------ entrada
if pergunta := st.chat_input("Escreva aqui…"):
    with caixa:
        with st.chat_message("user", avatar="🧑"):
            st.markdown(pergunta)
        with st.chat_message("assistant", avatar="🧭"):
            with st.spinner("Pensando e atualizando o desenho…"):
                try:
                    r = cliente.enviar(sessao_id, pergunta)
                    st.session_state.destaque = r["alterados"]
                    st.session_state.acoes = r["acoes"]
                except ApiForaDoAr:
                    st.error(MENSAGEM_FORA_DO_AR)
                    st.stop()
                except ErroDaApi as e:
                    st.error(e.mensagem + (f"\n\n`{e.detalhe}`" if e.detalhe else ""))
                    st.stop()
    st.rerun()
