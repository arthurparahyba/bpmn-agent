"""
Interface web: chat à esquerda, diagrama BPMN ao vivo à direita.

    streamlit run src/bpmn_agent/visao/web.py
"""
from __future__ import annotations

import json
import os

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from bpmn_agent.app.agente.llm import PROVEDORES, criar_llm
from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.sessao import Sessao
from bpmn_agent.visao.visualizador import html_visualizador

load_dotenv()
st.set_page_config(page_title="Desenhista de Processos", page_icon="🧭", layout="wide")

st.markdown("""<style>
  .block-container { padding-top: 1.6rem; }
  [data-testid="stChatMessage"] { padding: .35rem .6rem; }
</style>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.header("⚙️ Modelo de linguagem")
    nomes = list(PROVEDORES)
    padrao = os.getenv("LLM_PROVEDOR", "deepseek")
    provedor = st.selectbox("Provedor", nomes, index=nomes.index(padrao) if padrao in nomes else 0)
    cfg = PROVEDORES[provedor]
    modelo_nome = st.text_input("Modelo", value=(os.getenv("LLM_MODELO") if provedor == padrao else None)
                                or cfg["modelo"])
    chave = ""
    if cfg["env_chave"]:
        tem_env = bool(os.getenv(cfg["env_chave"]))
        chave = st.text_input("Chave da API", type="password",
                              placeholder="usando a do .env" if tem_env else cfg["env_chave"])
        st.caption(f"[Obter chave]({cfg['obter_chave']})")

    def _llm():
        return criar_llm(provedor, modelo_nome, chave or None)

    c1, c2 = st.columns(2)
    if c1.button("🆕 Nova conversa", use_container_width=True):
        st.session_state.pop("sessao", None)
    if "sessao" in st.session_state and c2.button("🔁 Trocar modelo", use_container_width=True,
                                                  help="Mantém a conversa e o desenho"):
        try:
            st.session_state.sessao.trocar_llm(_llm())
            st.toast(f"Agora usando {provedor} / {modelo_nome}")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("📂 Continuar um processo")
    arq = st.file_uploader("Arquivo .json salvo antes", type=["json"], label_visibility="collapsed")
    if arq is not None and st.session_state.get("arquivo_carregado") != arq.file_id:
        try:
            modelo = ModeloProcesso.de_dict(json.loads(arq.getvalue()))
            st.session_state.sessao = Sessao(_llm(), modelo=modelo)
            st.session_state.arquivo_carregado = arq.file_id
            st.session_state.destaque = []
        except Exception as e:
            st.error(f"Não consegui abrir: {e}")

    mostrar_acoes = st.toggle("Mostrar o que o agente fez (depuração)", value=False)

# ------------------------------------------------------------------ sessão
if "sessao" not in st.session_state:
    try:
        st.session_state.sessao = Sessao(_llm())
        st.session_state.destaque = []
        st.session_state.acoes = []
    except Exception as e:
        st.title("🧭 Desenhista de Processos")
        st.warning(f"{e}\n\nInforme a chave na barra lateral ou no arquivo `.env`.")
        st.stop()

sessao: Sessao = st.session_state.sessao
modelo = sessao.modelo

# ------------------------------------------------------------------ layout
st.title(f"🧭 {modelo.p.nome if modelo.p.elementos or modelo.p.nome != 'Novo processo' else 'Desenhista de Processos'}")
col_chat, col_diag = st.columns([5, 7], gap="large")

with col_chat:
    caixa = st.container(height=640)
    with caixa:
        for papel, texto in sessao.historico_visivel():
            with st.chat_message(papel, avatar="🧑" if papel == "user" else "🧭"):
                st.markdown(texto)
        if mostrar_acoes and st.session_state.get("acoes"):
            with st.expander("Ações do último turno", expanded=True):
                for a in st.session_state.acoes:
                    st.code(a, language=None)

with col_diag:
    xml = sessao.bpmn_xml()
    if modelo.p.elementos:
        components.html(html_visualizador(xml, altura=470, destacar=st.session_state.get("destaque")),
                        height=490)
    else:
        st.info("O desenho vai aparecer aqui conforme você conta como o processo funciona.")

    aba1, aba2, aba3 = st.tabs(["📝 Descrição", "❓ Em aberto", "⬇️ Baixar"])
    with aba1:
        st.markdown(modelo.narrativa())
    with aba2:
        abertos = modelo.problemas() + [f"Pendência: {t}" for t in modelo.p.pendencias]
        st.markdown("\n".join(f"- {t}" for t in abertos) if abertos else "Nada em aberto 🎉")
    with aba3:
        base = (modelo.p.nome or "processo").strip().replace(" ", "_").lower()
        st.download_button("Diagrama BPMN (.bpmn)", xml, f"{base}.bpmn", "application/xml",
                           use_container_width=True,
                           help="Abre no bpmn.io, Camunda Modeler, Bizagi, Signavio...")
        st.download_button("Projeto para continuar depois (.json)",
                           json.dumps(modelo.para_dict(), ensure_ascii=False, indent=2),
                           f"{base}.json", "application/json", use_container_width=True)
        st.download_button("Descrição em texto (.md)", modelo.narrativa(), f"{base}.md", "text/markdown",
                           use_container_width=True)
        st.caption(f"Também salvo automaticamente em `{sessao.pasta}`")

# ------------------------------------------------------------------ entrada
if pergunta := st.chat_input("Escreva aqui…"):
    with caixa:
        with st.chat_message("user", avatar="🧑"):
            st.markdown(pergunta)
        with st.chat_message("assistant", avatar="🧭"):
            with st.spinner("Pensando e atualizando o desenho…"):
                try:
                    r = sessao.enviar(pergunta)
                    st.session_state.destaque = r.alterados
                    st.session_state.acoes = r.acoes
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                        dica = "O limite gratuito do provedor foi atingido. Espere um pouco ou troque de modelo."
                    elif "401" in msg or "auth" in msg.lower() or "api key" in msg.lower():
                        dica = "A chave da API parece inválida."
                    else:
                        dica = "Algo deu errado ao falar com o modelo."
                    st.error(f"{dica}\n\n`{msg[:300]}`")
                    st.stop()
    st.rerun()
