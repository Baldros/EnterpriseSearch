import streamlit as st
import requests
import pandas as pd
from pathlib import Path
from typing import List, Optional
import re

# sua função atual para listar arquivos
def list_files(dir_path: str, extension: Optional[str] = None, recursive: bool = True) -> List[str]:
    """
    Lista todos os arquivos no diretório `dir_path`.
    Se `extension` for fornecida (ex: 'csv' ou '.csv'),
    filtra apenas arquivos com essa extensão.
    Por padrão, pesquisa recursivamente (subpastas).
    """
    base = Path(dir_path)
    if extension:
        ext = extension if extension.startswith('.') else f".{extension}"
        pattern = f"**/*{ext}" if recursive else f"*{ext}"
    else:
        pattern = "**/*" if recursive else "*"
    return [str(p.resolve()) for p in base.rglob(pattern) if p.is_file()]

files = list_files("Arquivos", ".csv")

@st.cache_data
def load_all_data(files: List[str]) -> pd.DataFrame:
    """Carrega todos os arquivos CSV num único DataFrame, com coluna indicando o arquivo."""
    dfs = []
    for arquivo in files:
        df = pd.read_csv(arquivo, sep=";", encoding="utf-8", dtype=str, low_memory=False)
        df["_arquivo"] = Path(arquivo).name
        dfs.append(df)
    if dfs:
        full = pd.concat(dfs, ignore_index=True)
    else:
        full = pd.DataFrame()
    return full

# Função de busca/filtro múltiplo
from typing import Optional, List, Dict
import pandas as pd

def filter_data(
    df: pd.DataFrame,
    filtros: Dict[str, Optional[object]],
    column_for_search: Optional[str] = None,
    query: Optional[str] = None,
    exact_match: bool = True,
    debug: bool = False
) -> pd.DataFrame:
    """
    Aplica múltiplos filtros (filtros: coluna -> lista de valores OU valor único).
    Ignora filtros vazios (None, "", empty list/tuple/set).
    Faz comparações case-insensitive (normaliza para str.lower()).
    Se column_for_search e query forem passados, aplica busca textual (exata ou 'contains', case-insensitive).
    """
    df2 = df.copy()
    if debug:
        steps = []
        steps.append(("initial", len(df2)))

    for col, val in (filtros or {}).items():
        # pular filtros vazios
        if val is None:
            continue
        if isinstance(val, (list, tuple, set)) and len(val) == 0:
            continue
        if isinstance(val, str) and val == "":
            continue

        # pular se coluna não existe
        if col not in df2.columns:
            if debug:
                steps.append((f"skip_missing_col:{col}", len(df2)))
            continue

        # normalizar coluna para string lowercase (não altera df original porque df2 é cópia)
        df2[col] = df2[col].astype(str).str.lower()

        # normalizar valores do filtro
        if isinstance(val, (list, tuple, set)):
            val_norm = [str(v).lower() for v in val]
            df2 = df2[df2[col].isin(val_norm)]
        else:
            v_norm = str(val).lower()
            df2 = df2[df2[col] == v_norm]

        if debug:
            steps.append((f"after_filter:{col}", len(df2)))

        # se ficou vazio, pode interromper cedo
        if df2.empty:
            if debug:
                steps.append(("early_exit_empty", 0))
            return df2

    # busca textual opcional
    if column_for_search and query:
        if column_for_search in df2.columns:
            q = str(query).lower()
            df2[column_for_search] = df2[column_for_search].astype(str).str.lower()
            if exact_match:
                df2 = df2[df2[column_for_search] == q]
            else:
                df2 = df2[df2[column_for_search].str.contains(q, na=False)]
            if debug:
                steps.append((f"after_search:{column_for_search}", len(df2)))
        else:
            if debug:
                steps.append((f"search_col_missing:{column_for_search}", len(df2)))

    if debug:
        # opcional: retornar info de debug (aqui só printamos; no Streamlit use st.write)
        for name, cnt in steps:
            print(f"{name}: {cnt}")

    return df2


st.title("App de Pesquisa e Filtros")
# carregando dados
df_all = load_all_data(files)
if df_all.empty:
    st.write("Nenhum dado encontrado.")
    st.stop()

# colunas que queremos oferecer como filtros fixos
colunas_filtro = ["SITUAÇÃO ESPECIAL", "DESCRIÇÃO", "NOME SETOR"]

# sidebar para escolher filtros
with st.sidebar:
    st.header("Filtros")
    # Vamos criar uma opção pra coluna de busca textual
    sample = df_all.head(1)
    col_drop = st.selectbox("Coluna para busca textual (opcional):", [""] + list(df_all.columns))
    query = ""
    exact = True
    if col_drop:
        query = st.text_input("Digite o texto para buscar na coluna selecionada:")
        exact = st.radio("Tipo de busca:", ("Exata", "Contém")) == "Exata"
    # agora, para cada coluna de filtro fixa, vamos dar opções
    filtros = {}
    for col in colunas_filtro:
        if col in df_all.columns:
            # obter valores únicos (poderia também ordenar / filtrar valores nulos)
            opc = sorted(df_all[col].dropna().unique().tolist())
            # permitir múltiplas seleções?
            sel = st.multiselect(f"Filtrar por {col}:", options=opc)
            filtros[col] = sel  # lista vazia se nada selecionado
        else:
            filtros[col] = None
    # botão para executar busca / filtrar
    buscar = st.button("Buscar")

# resultado: quando o usuário clicar em Buscar
def clean_cnpj_digits(cnpj: str) -> str:
    return re.sub(r"\D", "", str(cnpj or ""))

def get_cnpj_data(cnpj: str) -> dict:
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    # ajusta se for sua cliente chamada “client.processor.get_data(...)”
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    else:
        st.error(f"Erro ao consultar BrasilAPI: status {resp.status_code}")
        return {}

def mostra_detalhes_cnpj(dados: dict):
    # Nome fantasia ou razão social
    nome = dados.get("nome_fantasia") or dados.get("nome") or "Sem nome disponível"
    st.header(f"Detalhes do CNPJ {dados.get('cnpj', '')} — {nome}")

       # definindo cores em hexadecimal
    cores = {
        "porte": "#2C3E50",             # cinza escuro / azul profundo
        "natureza_juridica": "#117A65", # verde escuro
        "regime_tributario": "#B03A2E", # vermelho escuro
        "capital_social": "#884EA0"   # roxo escuro
    }
    
    # contêiner para alinhar itens lado a lado, opcional
    col1, col2, col3 = st.columns(3)
    
    # Porte
    porte = dados.get("porte")
    capital_social = dados.get("capital_social")
    if porte or capital_social:
        with col1:
            st.markdown(
                f"""
                <div style="
                    background-color:{cores['porte']};
                    color: white;
                    padding: 8px 12px;
                    border-radius: 8px;
                    font-weight: bold;
                    text-align: center;
                    margin-bottom: 5px;
                ">
                Porte: {porte}
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown(
                f"""
                <div style="
                    background-color:{cores['capital_social']};
                    color: white;
                    padding: 8px 12px;
                    border-radius: 8px;
                    font-weight: bold;
                    text-align: center;
                    margin-bottom: 5px;
                ">
                Capital Social: {capital_social}
                </div>
                """,
                unsafe_allow_html=True
            )
    
    # Natureza Jurídica
    natureza_juridica = dados.get("natureza_juridica")
    if natureza_juridica:
        with col2:
            st.markdown(
                f"""
                <div style="
                    background-color:{cores['natureza_juridica']};
                    color: white;
                    padding: 8px 12px;
                    border-radius: 8px;
                    font-weight: bold;
                    text-align: center;
                    margin-bottom: 5px;
                ">
                Natureza Jurídica: {natureza_juridica}
                </div>
                """,
                unsafe_allow_html=True
            )

    
    # Regime Tributário
    regime_tributario = dados.get("regime_tributario")
    if regime_tributario:
        with col3:
            st.markdown(
                f"""
                <div style="
                    background-color:{cores['regime_tributario']};
                    color: white;
                    padding: 8px 12px;
                    border-radius: 8px;
                    font-weight: bold;
                    text-align: center;
                    margin-bottom: 5px;
                ">
                Regime Tributário: {regime_tributario}
                </div>
                """,
                unsafe_allow_html=True
            )

    # Sócios e administradores (QSA)
    qsa = dados.get("qsa")
    if qsa:
        st.subheader("Quadro de Sócios e Administradores (QSA)")
        # transforma em DataFrame para exibir como tabela
        df_qsa = pd.DataFrame(qsa)
        # seleciona colunas mais úteis
        colunas = ["nome_socio", "qualificacao_socio", "faixa_etaria", "data_entrada_sociedade"]
        df_qsa = df_qsa[colunas]
        st.dataframe(df_qsa, use_container_width=True)

# --- quando o usuário clicar em Buscar, além de filtrar, salvamos no session_state ---
if buscar:
    df_filtrado = filter_data(
        df_all,
        filtros,
        column_for_search=col_drop if col_drop else None,
        query=query if query else None,
        exact_match=exact
    ).drop(columns=["_arquivo"], errors="ignore")

    # salva no session_state para ser usado por outros widgets
    st.session_state.df_filtrado = df_filtrado

    # Criar opções de CNPJ (display -> cleaned digits) se a coluna existir
    if "CNPJ" in df_filtrado.columns:
        unique = df_filtrado["CNPJ"].dropna().astype(str).str.strip().unique().tolist()
        # mapping preserva o formato original para exibição e provê a versão sem pontuação para a API
        cnpj_map = {"-- Selecione um CNPJ --": ""}
        for c in unique:
            c_display = c
            c_api = clean_cnpj_digits(c)
            # evite duplicatas: se já existir um c_api igual, prefira manter o display original
            # (isso é opcional dependendo do seu CSV)
            if c_display not in cnpj_map:
                cnpj_map[c_display] = c_api

        st.session_state.cnpj_map = cnpj_map
        st.session_state.cnpj_options = list(cnpj_map.keys())
    else:
        st.session_state.cnpj_map = {"-- Selecione um CNPJ --": ""}
        st.session_state.cnpj_options = ["-- Selecione um CNPJ --"]

    # inicializar selected_cnpj se não existir
    if "selected_cnpj" not in st.session_state:
        st.session_state.selected_cnpj = "-- Selecione um CNPJ --"

    # mostrar resultados na página
    st.write(f"Resultados encontrados: {len(df_filtrado)} registros")
    st.dataframe(df_filtrado)
    csv = df_filtrado.to_csv(index=False, sep=";", encoding="utf-8")
    st.download_button("Download CSV", data=csv, file_name="resultado.csv", mime="text/csv")

else:
    # se não clicou em buscar, mas já existe df_filtrado no estado (ex.: busca anterior), use-o
    if "df_filtrado" in st.session_state:
        df_filtrado = st.session_state.df_filtrado
        st.write(f"Resultados (última busca): {len(df_filtrado)} registros")
        st.dataframe(df_filtrado)
    else:
        st.write("Use os filtros na barra lateral e clique em Buscar.")
# ---------------------------
# Bloco BrasilAPI (pode ficar fora do if buscar; depende do session_state atualizado)
# ---------------------------
if "df_filtrado" in st.session_state and "CNPJ" in st.session_state.df_filtrado.columns:
    # garante que cnpj_options exista
    st.session_state.cnpj_options = st.session_state.get("cnpj_options", ["-- Selecione um CNPJ --"])
    # selectbox usa as opções geradas anteriormente
    selected = st.sidebar.selectbox(
        "Escolha um CNPJ para ver detalhes:",
        st.session_state.cnpj_options,
        index=st.session_state.cnpj_options.index(st.session_state.get("selected_cnpj", "-- Selecione um CNPJ --")) 
            if st.session_state.get("selected_cnpj") in st.session_state.cnpj_options else 0,
        key="cnpj_select", 
    )

    # atualiza valor selecionado no estado (display string)
    if selected != st.session_state.get("selected_cnpj"):
        st.session_state.selected_cnpj = selected

    cnpj_display = st.session_state.selected_cnpj
    # obtém cnpj limpo para API (digits only)
    cnpj_api = st.session_state.cnpj_map.get(cnpj_display, "")

    st.write(f"Selecionado: {cnpj_display}")

    if cnpj_api:
        with st.spinner(f"Consultando BrasilAPI para {cnpj_display}..."):
            try:
                dados = get_cnpj_data(cnpj_api)  # usa cnpj só com dígitos
            except Exception as e:
                st.error(f"Erro BrasilAPI: {e}")
                dados = {}
        if dados:
            mostra_detalhes_cnpj(dados)
    else:
        st.info("Selecione um CNPJ válido para ver os detalhes.")
else:
    # se o dataframe filtrado existe, mas não tem coluna CNPJ
    if "df_filtrado" in st.session_state:

        st.sidebar.info("A coluna **CNPJ** não existe na sua busca.")
