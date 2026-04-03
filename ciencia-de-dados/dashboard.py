"""
Reclame Aqui — Interactive Dashboard
Streamlit app with global filters and interactive charts.

Empresa: Nagem (single-company focus)
"""

import os
import json
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import nltk
from nltk.corpus import stopwords

warnings.filterwarnings("ignore")
nltk.download("stopwords", quiet=True)

# ---------------------------------------------------------------------------
# Configuration: Company to analyze
# ---------------------------------------------------------------------------
EMPRESA_SELECIONADA = "Nagem"
EMPRESA_FILE = "RECLAMEAQUI_NAGEM.csv"

# Full mapping preserved for future multi-company support
COMPANY_MAP = {
    "RECLAMEAQUI_BIGLOJAS.csv": "BIG Lojas",
    "RECLAMEAQUI_CARREFUOR.csv": "Carrefour",
    "RECLAMEAQUI_HAPVIDA.csv": "Hapvida",
    "RECLAMEAQUI_IBYTE.csv": "Ibyte",
    "RECLAMEAQUI_NAGEM.csv": "Nagem",
    "RECLAMEAQUI_PAODEACUCAR.csv": "Pão de Açúcar",
}

MONTH_LABELS = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# Brazilian state capitals for city classification
CAPITAIS = {
    'AC': 'Rio Branco', 'AL': 'Maceió', 'AP': 'Macapá', 'AM': 'Manaus',
    'BA': 'Salvador', 'CE': 'Fortaleza', 'DF': 'Brasília', 'ES': 'Vitória',
    'GO': 'Goiânia', 'MA': 'São Luís', 'MT': 'Cuiabá', 'MS': 'Campo Grande',
    'MG': 'Belo Horizonte', 'PA': 'Belém', 'PB': 'João Pessoa', 'PR': 'Curitiba',
    'PE': 'Recife', 'PI': 'Teresina', 'RJ': 'Rio de Janeiro', 'RN': 'Natal',
    'RS': 'Porto Alegre', 'RO': 'Porto Velho', 'RR': 'Boa Vista', 'SC': 'Florianópolis',
    'SP': 'São Paulo', 'SE': 'Aracaju', 'TO': 'Palmas'
}
LISTA_CAPITAIS = list(CAPITAIS.values())

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"Reclame Aqui — {EMPRESA_SELECIONADA}",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Data loading & cleaning (cached) — Nagem only
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "datasets")


@st.cache_data(show_spinner="Carregando dados…")
def load_data() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, EMPRESA_FILE)
    df = pd.read_csv(path)
    df["EMPRESA"] = EMPRESA_SELECIONADA

    # --- cleaning (mirrors notebook Phase 1) ---
    df["ID"] = df["ID"].astype(str).str.strip()
    df["TEMPO"] = pd.to_datetime(df["TEMPO"], errors="coerce")
    df["ESTADO"] = df["LOCAL"].str.strip().str.extract(r" - ([A-Z]{2})$")
    df["ESTADO"] = df["ESTADO"].fillna("Desconhecido")
    df["CATEGORIA_PRIMARIA"] = df["CATEGORIA"].str.split("<->").str[0].str.strip()
    df["STATUS"] = df["STATUS"].str.strip()

    int_cols = [
        "ANO", "MES", "DIA", "DIA_DO_ANO",
        "SEMANA_DO_ANO", "DIA_DA_SEMANA", "TRIMETRES", "CASOS",
    ]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # derived
    df["TAMANHO_DESCRICAO"] = df["DESCRICAO"].fillna("").str.len()
    df["RESOLVIDO"] = df["STATUS"] == "Resolvido"
    df["MES_LABEL"] = df["MES"].map(MONTH_LABELS)
    
    # City extraction and classification
    df["CIDADE"] = df["LOCAL"].str.strip().str.rsplit(" - ", n=1).str[0]
    df["IS_CAPITAL"] = df["CIDADE"].isin(LISTA_CAPITAIS)
    df["TIPO_CIDADE"] = df["IS_CAPITAL"].map({True: "Capital", False: "Interior"})
    return df


@st.cache_resource
def load_brazil_map():
    """Load Brazil states GeoJSON (~2MB, cached)."""
    geojson_path = os.path.join(DATA_DIR, "brazil_states.geojson")
    with open(geojson_path, "r") as f:
        return json.load(f)


df_full = load_data()
geojson_br = load_brazil_map()

# ---------------------------------------------------------------------------
# Sidebar — Global Filters (no Empresa filter needed for single company)
# ---------------------------------------------------------------------------
st.sidebar.title("🔎 Filtros")
st.sidebar.caption(f"Empresa: **{EMPRESA_SELECIONADA}**")

# Estado
all_estados = sorted(df_full[df_full["ESTADO"] != "Desconhecido"]["ESTADO"].unique())
selected_estados = st.sidebar.multiselect(
    "Estado",
    options=all_estados,
    default=all_estados,
)

# Status
all_status = sorted(df_full["STATUS"].unique())
selected_status = st.sidebar.multiselect(
    "Status",
    options=all_status,
    default=all_status,
)

# Tamanho da Descrição (range slider)
desc_min = int(df_full["TAMANHO_DESCRICAO"].min())
desc_max = int(df_full["TAMANHO_DESCRICAO"].max())
desc_range = st.sidebar.slider(
    "Tamanho da Descrição (caracteres)",
    min_value=desc_min,
    max_value=desc_max,
    value=(desc_min, desc_max),
)

# Year slider (for future map feature)
all_anos = sorted(df_full["ANO"].dropna().unique())
ano_options = ["Todos"] + [str(a) for a in all_anos]
selected_ano = st.sidebar.select_slider(
    "Ano",
    options=ano_options,
    value="Todos",
)

# City type filter
selected_tipo_cidade = st.sidebar.radio(
    "Tipo de Cidade",
    options=["Todos", "Capital", "Interior"],
    index=0,
)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
mask = (
    df_full["ESTADO"].isin(selected_estados)
    & df_full["STATUS"].isin(selected_status)
    & df_full["TAMANHO_DESCRICAO"].between(desc_range[0], desc_range[1])
)

# Apply year filter if not "Todos"
if selected_ano != "Todos":
    mask = mask & (df_full["ANO"] == int(selected_ano))

# Apply city type filter if not "Todos"
if selected_tipo_cidade != "Todos":
    mask = mask & (df_full["TIPO_CIDADE"] == selected_tipo_cidade)

df = df_full[mask].copy()

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------
st.title(f"📊 Reclame Aqui — {EMPRESA_SELECIONADA}")
st.caption(f"Exibindo **{len(df):,}** de {len(df_full):,} reclamações")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Total reclamações", f"{len(df):,}")
kpi2.metric("Estados", df["ESTADO"].nunique())
resolved_pct = df["RESOLVIDO"].mean() * 100 if len(df) else 0
kpi3.metric("Taxa de resolução", f"{resolved_pct:.1f}%")
kpi4.metric("Período", f"{df['ANO'].min()}–{df['ANO'].max()}" if len(df) else "N/A")

st.divider()

# ---------------------------------------------------------------------------
# Chart 1 — Time Series + Moving Average
# ---------------------------------------------------------------------------
st.subheader("📈 Reclamações ao longo do tempo")

ts = df.groupby(df["TEMPO"].dt.to_period("M")).size().reset_index(name="count")
ts.columns = ["period", "count"]
ts["date"] = ts["period"].dt.to_timestamp()
ts["moving_avg"] = ts["count"].rolling(window=3, center=True).mean()

fig_ts = go.Figure()
fig_ts.add_trace(go.Bar(x=ts["date"], y=ts["count"], name="Mensal", marker_color="steelblue", opacity=0.6))
fig_ts.add_trace(go.Scatter(x=ts["date"], y=ts["moving_avg"], name="Média móvel (3 meses)", line=dict(color="crimson", width=2)))
fig_ts.update_layout(
    xaxis_title="Data", yaxis_title="Reclamações",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=40, r=20, t=30, b=40), height=400,
)
st.plotly_chart(fig_ts, use_container_width=True)

# ---------------------------------------------------------------------------
# Chart 2 — Choropleth Map
# ---------------------------------------------------------------------------
st.subheader("🗺️ Mapa coroplético — Reclamações por estado")

# All Brazilian states
ALL_STATES = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 
              'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 
              'SP', 'SE', 'TO']

# Aggregate by state, optionally filtered by year
if selected_ano == "Todos":
    state_counts = (
        df[df["ESTADO"] != "Desconhecido"]
        .groupby("ESTADO")
        .size()
        .reset_index(name="TOTAL")
    )
    map_title = "Total de reclamações por estado"
else:
    state_counts = (
        df[(df["ESTADO"] != "Desconhecido") & (df["ANO"] == int(selected_ano))]
        .groupby("ESTADO")
        .size()
        .reset_index(name="TOTAL")
    )
    map_title = f"Reclamações por estado — {selected_ano}"

# Include all states (missing ones will be NaN = grey)
map_df = pd.DataFrame({"ESTADO": ALL_STATES})
map_df = map_df.merge(state_counts, on="ESTADO", how="left")
# Keep NaN for states without data (will render as grey)

fig_map = px.choropleth(
    map_df,
    geojson=geojson_br,
    locations="ESTADO",
    featureidkey="properties.sigla",
    color="TOTAL",
    color_continuous_scale="YlOrRd",
    labels={"TOTAL": "Reclamações", "ESTADO": "Estado"},
    title=map_title,
)
fig_map.update_geos(
    fitbounds="locations",
    visible=False,
    projection_type="mercator",
)
fig_map.update_traces(
    marker_line_color="darkgrey",
    marker_line_width=0.5,
)
fig_map.update_layout(
    margin=dict(l=0, r=0, t=40, b=0),
    height=450,
    coloraxis_colorbar=dict(title="Reclamações"),
    geo=dict(bgcolor="rgba(0,0,0,0)", landcolor="lightgrey"),
)
st.plotly_chart(fig_map, use_container_width=True)

# ---------------------------------------------------------------------------
# City Analysis Section
# ---------------------------------------------------------------------------
st.subheader("🏙️ Análise por Cidade: Capital vs Interior")

col_city1, col_city2 = st.columns(2)

with col_city1:
    # Capital vs Interior comparison
    city_comparison = df.groupby("TIPO_CIDADE").agg({
        "ID": "count",
        "RESOLVIDO": "mean",
        "TAMANHO_DESCRICAO": "mean"
    }).round(2)
    city_comparison.columns = ["Total", "Taxa Resolução", "Média Tam. Descrição"]
    city_comparison["Taxa Resolução"] = (city_comparison["Taxa Resolução"] * 100).round(1)
    
    fig_city_pie = px.pie(
        city_comparison.reset_index(),
        names="TIPO_CIDADE",
        values="Total",
        color="TIPO_CIDADE",
        color_discrete_map={"Capital": "steelblue", "Interior": "darkorange"},
        title="Distribuição: Capital vs Interior"
    )
    fig_city_pie.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=350)
    st.plotly_chart(fig_city_pie, use_container_width=True)

with col_city2:
    # Resolution rate comparison
    fig_city_bar = go.Figure()
    for tipo, color in [("Capital", "steelblue"), ("Interior", "darkorange")]:
        if tipo in city_comparison.index:
            fig_city_bar.add_trace(go.Bar(
                x=[tipo],
                y=[city_comparison.loc[tipo, "Taxa Resolução"]],
                name=tipo,
                marker_color=color,
                text=[f"{city_comparison.loc[tipo, 'Taxa Resolução']:.1f}%"],
                textposition="outside"
            ))
    fig_city_bar.update_layout(
        title="Taxa de Resolução por Tipo de Cidade",
        yaxis_title="% Resolvido",
        showlegend=False,
        margin=dict(l=40, r=20, t=50, b=40),
        height=350,
        yaxis=dict(range=[0, 100])
    )
    st.plotly_chart(fig_city_bar, use_container_width=True)

# Top cities chart
st.subheader("🏆 Top 15 Cidades por Volume de Reclamações")
top_cities = df["CIDADE"].value_counts().head(15).reset_index()
top_cities.columns = ["CIDADE", "count"]
top_cities["Tipo"] = top_cities["CIDADE"].apply(lambda x: "Capital" if x in LISTA_CAPITAIS else "Interior")

fig_top_cities = px.bar(
    top_cities,
    x="count",
    y="CIDADE",
    orientation="h",
    color="Tipo",
    color_discrete_map={"Capital": "steelblue", "Interior": "darkorange"},
    labels={"count": "Reclamações", "CIDADE": "Cidade"},
    text="count"
)
fig_top_cities.update_layout(
    yaxis=dict(categoryorder="total ascending"),
    margin=dict(l=40, r=20, t=30, b=40),
    height=450,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig_top_cities, use_container_width=True)

# ---------------------------------------------------------------------------
# Chart 3 — Pareto Chart by State
# ---------------------------------------------------------------------------
col_pareto, col_status = st.columns(2)

with col_pareto:
    st.subheader("📊 Gráfico de Pareto por estado")
    state_counts = (
        df[df["ESTADO"] != "Desconhecido"]["ESTADO"]
        .value_counts()
        .reset_index()
    )
    state_counts.columns = ["ESTADO", "count"]
    state_counts["cum_pct"] = state_counts["count"].cumsum() / state_counts["count"].sum() * 100

    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(x=state_counts["ESTADO"], y=state_counts["count"], name="Reclamações", marker_color="steelblue"))
    fig_pareto.add_trace(go.Scatter(x=state_counts["ESTADO"], y=state_counts["cum_pct"], name="% Acumulado", yaxis="y2", line=dict(color="crimson"), marker=dict(size=4)))
    fig_pareto.add_hline(y=80, line_dash="dash", line_color="gray", annotation_text="80%", yref="y2")
    fig_pareto.update_layout(
        yaxis=dict(title="Reclamações"),
        yaxis2=dict(title="% Acumulado", overlaying="y", side="right", range=[0, 105]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=30, b=40), height=420,
    )
    st.plotly_chart(fig_pareto, use_container_width=True)

# ---------------------------------------------------------------------------
# Chart 4 — STATUS Proportion
# ---------------------------------------------------------------------------
with col_status:
    st.subheader("🥧 Distribuição por Status")
    status_counts = df["STATUS"].value_counts().reset_index()
    status_counts.columns = ["STATUS", "count"]

    fig_pie = px.pie(
        status_counts,
        names="STATUS",
        values="count",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_pie.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=420)
    st.plotly_chart(fig_pie, use_container_width=True)

# ---------------------------------------------------------------------------
# Chart 5 — Text Length Boxplot × STATUS
# ---------------------------------------------------------------------------
col_box, col_wc = st.columns(2)

with col_box:
    st.subheader("📏 Tamanho da descrição por Status")
    fig_box = px.box(
        df,
        x="STATUS",
        y="TAMANHO_DESCRICAO",
        color="STATUS",
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"TAMANHO_DESCRICAO": "Caracteres", "STATUS": "Status"},
    )
    fig_box.update_layout(
        showlegend=False,
        margin=dict(l=40, r=20, t=30, b=40), height=460,
    )
    st.plotly_chart(fig_box, use_container_width=True)

# ---------------------------------------------------------------------------
# Chart 6 — WordCloud
# ---------------------------------------------------------------------------
with col_wc:
    st.subheader("☁️ Nuvem de palavras")

    pt_stopwords = set(stopwords.words("portuguese"))
    extra_noise = {
        "big", "carrefour", "hapvida", "ibyte", "nagem", "pão", "açúcar",
        "loja", "empresa", "produto", "compra", "cliente", "pra", "pois",
        "já", "ser", "mais", "ter", "que", "uma", "uns", "umas", "meu", "minha",
        "editado", "reclame", "aqui",
    }
    all_stopwords = pt_stopwords | extra_noise

    all_text = " ".join(df["DESCRICAO"].dropna().astype(str).str.lower())

    if all_text.strip():
        wc = WordCloud(
            width=800,
            height=400,
            background_color="white",
            stopwords=all_stopwords,
            max_words=150,
            colormap="plasma",
            collocations=False,
        ).generate(all_text)

        fig_wc, ax_wc = plt.subplots(figsize=(10, 5))
        ax_wc.imshow(wc, interpolation="bilinear")
        ax_wc.axis("off")
        plt.tight_layout()
        st.pyplot(fig_wc)
        plt.close(fig_wc)
    else:
        st.info("Sem dados de texto para os filtros selecionados.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(f"Dashboard — Reclame Aqui · {EMPRESA_SELECIONADA} · Ciência de Dados")
