import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
import os
import threading
import yfinance as yf
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==============================================================================
# DEFAULTS (editáveis pela interface)
# ==============================================================================
DEFAULT_NUM_ATIVOS        = 12
DEFAULT_MESES_MOMENTUM    = 6
DEFAULT_LIQUIDEZ_USD      = 58_218     # aprox. R$ 300 mil em 2026
DEFAULT_MARKET_CAP_USD    = 100_000_000_000  # US$ 500 Bi (Roman, 2021)
HOJE = datetime.now().strftime("%d-%m-%Y")
DEFAULT_CAMINHO_SAIDA     = f"Roman_Hibrida_{HOJE}.csv"

TICKERS_A_EXCLUIR = {
    'JBSS3','BRFS3','OIBR4','OIBR3','LIGT3','MMXM3','OSXB3',
    'RNEW11','AMER3','REAG3','AMBP3',
}

# ==============================================================================
# LISTA DE FINANCEIRAS — usam P/VP + Momentum no lugar de EY + Momentum
# ==============================================================================
FINANCEIRAS = {
    "ABCB4","ALOS3","APER3","B3SA3","BAZA3","BBAS3","BBDC3",
    "BBDC4","BBSE3","BEES3","BEES4","BGIP3","BGIP4","BMEB3",
    "BMEB4","BMGB4","BMIN3","BMIN4","BNBR3","BPAC11","BPAC3",
    "BPAC5","BPAN4","BRBI11","BRSR3","BRSR5","BRSR6","BSLI3",
    "BSLI4","CXSE3","EPAR3","FICT3","FIGE3","G2DI33","GPIV33",
    "HBRE3","IGTI11","IGTI3","IGTI4","IRBR3","ITSA3","ITSA4",
    "ITUB3","ITUB4","LOGG3","LPSB3","MAPT3","MERC3","MULT3",
    "NEXP3","PDTC3","PEAB3","PEAB4","PINE14","PINE3","PINE4",
    "PPLA11","PSSA3","RPAD3","RPAD5","RPAD6","SANB11","SANB3",
    "SANB4","SCAR3","SIMH3","SULA11","SYNE3","WIZC3",
}

DELIMITADOR_CSV        = ';'
DELIMITADOR_CSV_INDICE = ';'
CODIFICACAO_INDICE     = 'cp1252'

# ==============================================================================
# UTILITÁRIOS
# ==============================================================================

def buscar_cotacao_dolar():
    try:
        ticker = yf.Ticker("USDBRL=X")
        hist = ticker.history(period="2d", interval="1d", auto_adjust=True)
        if not hist.empty and 'Close' in hist.columns:
            valor = hist['Close'].iloc[-1]
            if isinstance(valor, (int, float)) and valor > 0:
                return round(float(valor), 4)
        info = ticker.fast_info
        preco = getattr(info, 'last_price', None)
        if preco and preco > 0:
            return round(float(preco), 4)
    except Exception:
        pass
    return None


def limpar_converter_float(s):
    if pd.isna(s):
        return np.nan
    s = str(s).replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return np.nan


def calcular_momentum_ticker(ticker, meses):
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    data_alvo_nm = ontem - relativedelta(months=meses)
    data_inicio_busca = data_alvo_nm - timedelta(days=5)
    try:
        dados = yf.download(ticker, start=str(data_inicio_busca), end=str(hoje),
                            interval="1d", progress=False, auto_adjust=True)
    except Exception:
        return np.nan

    if dados.empty:
        return np.nan
    col = 'Close' if 'Close' in dados.columns else 'Adj Close'
    dados = dados[[col]].dropna()
    if len(dados) < 2:
        return np.nan
    try:
        mascara_ontem = dados.index.date <= ontem
        if not mascara_ontem.any():
            return np.nan
        preco_ontem = dados[col][mascara_ontem].iloc[-1].item()

        mascara = dados.index.date <= data_alvo_nm
        if not mascara.any():
            return np.nan
        preco_nm = dados[col][mascara].iloc[-1].item()
        if preco_nm <= 0:
            return np.nan
        return (preco_ontem / preco_nm) - 1
    except Exception:
        return np.nan


# ==============================================================================
# LÓGICA DE NEGÓCIO — ESTRATÉGIA HÍBRIDA (NON-FIN: EY | FIN: P/VP)
# ==============================================================================

def roman_seletor_hibrido(caminho_csv_bruto, caminho_csv_indice, num_ativos,
                           meses_momentum, liquidez_minima_brl,
                           market_cap_maximo_brl, cotacao_dolar, log_fn,
                           filtrar_mom_positivo=False,
                           proporcao_financeiras=0.30,
                           roe_minimo=10.0, pvp_maximo=1.5):
    """
    Estratégia Híbrida Roman:
      • Não-financeiras  → rank por Earnings Yield (1/EV·EBIT) + Momentum
      • Financeiras      → rank por P/VP + Momentum  (com filtros ROE ≥ roe_minimo e P/VP ≤ pvp_maximo)
      • Proporção final  → (1 - proporcao_financeiras) não-fin + proporcao_financeiras fin
    """

    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    data_alvo_nm = ontem - relativedelta(months=meses_momentum)

    def log(msg):
        log_fn(msg)

    log("=" * 70)
    log("ROMAN HÍBRIDA — EY (não-fin) + P/VP (fin) + Momentum")
    log(f"Momentum: {ontem} vs {data_alvo_nm} ({meses_momentum} meses atrás)")
    filtro_txt = "Momentum > 0 ATIVO" if filtrar_mom_positivo else "Momentum: todos"
    log(f"Filtro momentum: {filtro_txt}")
    log(f"Proporção financeiras: {proporcao_financeiras*100:.0f}%")
    log(f"Critérios fin.: ROE ≥ {roe_minimo}%  |  P/VP ≤ {pvp_maximo}")
    log("=" * 70)

    # ------------------------------------------------------------------
    # PASSO 1 — Leitura
    # ------------------------------------------------------------------
    try:
        df = pd.read_csv(caminho_csv_bruto, sep=DELIMITADOR_CSV, encoding='utf-8')
    except FileNotFoundError:
        log(f"ERRO: arquivo não encontrado: {caminho_csv_bruto}")
        return pd.DataFrame()
    df.columns = df.columns.str.strip()
    log(f"\n[1] Ativos iniciais: {len(df)}")

    # ------------------------------------------------------------------
    # PASSO 2 — Exclusão manual
    # ------------------------------------------------------------------
    n = len(df)
    df = df[~df['TICKER'].isin(TICKERS_A_EXCLUIR)].copy()
    log(f"[2] Após exclusão manual (removidos: {n - len(df)}): {len(df)}")

    # Conversão numérica
    colunas_num = ['VALOR DE MERCADO', 'EV/EBIT', 'LIQUIDEZ MEDIA DIARIA', 'P/VP', 'ROE', 'P/L']
    for col in colunas_num:
        if col in df.columns:
            df[col] = df[col].apply(limpar_converter_float)

    # ------------------------------------------------------------------
    # PASSO 3 — Deduplicação (mantém ticker de maior liquidez)
    # ------------------------------------------------------------------
    df['CODIGO_BASE'] = df['TICKER'].str.replace(r'\d+', '', regex=True)
    idx_max = df.groupby('CODIGO_BASE')['LIQUIDEZ MEDIA DIARIA'].idxmax().dropna()
    n = len(df)
    df = df.loc[idx_max].copy()
    log(f"[3] Após deduplicação (removidos: {n - len(df)}): {len(df)}")
    if df.empty:
        log("[FIM] Nenhum ativo."); return pd.DataFrame()

    # ------------------------------------------------------------------
    # PASSO 4 — Filtro por índice
    # ------------------------------------------------------------------
    log("\n[4] Filtro por índice...")
    try:
        df_indice = pd.read_csv(caminho_csv_indice, sep=DELIMITADOR_CSV_INDICE,
                                encoding=CODIFICACAO_INDICE, engine='python',
                                header=None, skiprows=2, usecols=[0])
        tickers_indice = df_indice[0].astype(str).str.strip().unique()
        n = len(df)
        df = df[df['TICKER'].isin(tickers_indice)].copy()
        log(f"    Tickers no índice: {len(tickers_indice)}")
        log(f"    Após filtro (removidos: {n - len(df)}): {len(df)}")
    except Exception as e:
        log(f"ERRO ao processar índice: {e}"); return pd.DataFrame()
    if df.empty:
        log("[FIM] Nenhum ativo no índice."); return pd.DataFrame()

    # ------------------------------------------------------------------
    # PASSO 5 — Filtro de liquidez
    # ------------------------------------------------------------------
    df.dropna(subset=['LIQUIDEZ MEDIA DIARIA'], inplace=True)
    n = len(df)
    df = df[df['LIQUIDEZ MEDIA DIARIA'] >= liquidez_minima_brl].copy()
    log(f"[5] Após liquidez ≥ R$ {liquidez_minima_brl:,.0f} (removidos: {n-len(df)}): {len(df)}")
    if df.empty:
        log("[FIM] Nenhum ativo com liquidez suficiente."); return pd.DataFrame()

    # ------------------------------------------------------------------
    # PASSO 5B — Filtro de market cap
    # ------------------------------------------------------------------
    if market_cap_maximo_brl is not None and 'VALOR DE MERCADO' in df.columns:
        df.dropna(subset=['VALOR DE MERCADO'], inplace=True)
        n = len(df)
        df = df[df['VALOR DE MERCADO'] <= market_cap_maximo_brl].copy()
        usd = market_cap_maximo_brl / cotacao_dolar if cotacao_dolar else 0
        log(f"[5B] Após market cap ≤ R$ {market_cap_maximo_brl:,.0f} "
            f"(US${usd:,.0f}, removidos: {n-len(df)}): {len(df)}")
        if df.empty:
            log("[FIM] Nenhum ativo no filtro de market cap."); return pd.DataFrame()

    # ------------------------------------------------------------------
    # PASSO 6 — Cálculo de Momentum
    # ------------------------------------------------------------------
    log(f"\n[6] Calculando momentum ({data_alvo_nm} → {ontem})...")
    df['TICKER_YF'] = np.where(df['TICKER'].str.endswith('.SA'),
                                df['TICKER'], df['TICKER'] + '.SA')
    total = len(df)
    resultados_mom = []
    for i, row in enumerate(df.itertuples(), 1):
        mom = calcular_momentum_ticker(row.TICKER_YF, meses_momentum)
        resultados_mom.append(mom)
        if i % 5 == 0 or i == total:
            log(f"    {i}/{total} tickers processados...")
    df['Momentum'] = resultados_mom
    n = len(df)
    df.dropna(subset=['Momentum'], inplace=True)
    log(f"    Dados ausentes removidos: {n - len(df)} | Restantes: {len(df)}")
    if df.empty:
        log("[FIM] Nenhum ativo com momentum."); return pd.DataFrame()

    if filtrar_mom_positivo:
        n = len(df)
        df = df[df['Momentum'] > 0].copy()
        log(f"    Filtro Momentum > 0 (removidos: {n - len(df)}): {len(df)}")
        if df.empty:
            log("[FIM] Nenhum ativo com momentum positivo."); return pd.DataFrame()

    # ------------------------------------------------------------------
    # PASSO 7 — Separação Financeiras / Não-financeiras
    # ------------------------------------------------------------------
    df['SETOR'] = np.where(df['TICKER'].isin(FINANCEIRAS), 'financeira', 'normal')
    df_fin = df[df['SETOR'] == 'financeira'].copy()
    df_non = df[df['SETOR'] == 'normal'].copy()
    log(f"\n[7] Universo: {len(df_non)} não-financeiras | {len(df_fin)} financeiras")

    # ------------------------------------------------------------------
    # PASSO 8 — Ranking NÃO-FINANCEIRAS (EY + Momentum)
    # ------------------------------------------------------------------
    df_non = df_non.dropna(subset=['EV/EBIT']).copy()
    df_non = df_non[df_non['EV/EBIT'] > 0].copy()
    df_non['Earnings_Yield'] = 1 / df_non['EV/EBIT']
    df_non['Rank_Valor']    = df_non['Earnings_Yield'].rank(method='first', ascending=False).astype(int)
    df_non['Rank_Momentum'] = df_non['Momentum'].rank(method='first', ascending=False).astype(int)
    df_non['Score']         = df_non['Rank_Valor'] + df_non['Rank_Momentum']
    log(f"[8] Não-financeiras após filtro EV/EBIT > 0: {len(df_non)}")

    # ------------------------------------------------------------------
    # PASSO 9 — Ranking FINANCEIRAS (P/VP + Momentum, com filtros ROE e P/VP)
    # ------------------------------------------------------------------
    if not df_fin.empty and 'P/VP' in df_fin.columns and 'ROE' in df_fin.columns:
        df_fin = df_fin.dropna(subset=['P/VP', 'ROE']).copy()
        n = len(df_fin)
        df_fin = df_fin[(df_fin['P/VP'] <= pvp_maximo) & (df_fin['ROE'] >= roe_minimo)].copy()
        log(f"[9] Financeiras após filtro P/VP ≤ {pvp_maximo} e ROE ≥ {roe_minimo}% "
            f"(removidos: {n - len(df_fin)}): {len(df_fin)}")
        if not df_fin.empty:
            df_fin['Rank_Valor']    = df_fin['P/VP'].rank(method='first', ascending=True).astype(int)
            df_fin['Rank_Momentum'] = df_fin['Momentum'].rank(method='first', ascending=False).astype(int)
            df_fin['Score']         = df_fin['Rank_Valor'] + df_fin['Rank_Momentum']
            # Earnings_Yield = NaN para financeiras (usam P/VP)
            df_fin['Earnings_Yield'] = np.nan
    else:
        log("[9] Nenhuma financeira válida.")
        df_fin = pd.DataFrame()

    # ------------------------------------------------------------------
    # PASSO 10 — União proporcional
    # ------------------------------------------------------------------
    n_fin = int(num_ativos * proporcao_financeiras)
    n_non = num_ativos - n_fin

    df_top_non = df_non.sort_values('Score').head(n_non) if not df_non.empty else pd.DataFrame()
    df_top_fin = df_fin.sort_values('Score').head(n_fin) if not df_fin.empty else pd.DataFrame()

    # Se faltar financeiras, completa com não-financeiras
    if len(df_top_fin) < n_fin:
        faltam = n_fin - len(df_top_fin)
        log(f"    ⚠ Apenas {len(df_top_fin)} financeiras disponíveis; "
            f"completando com {faltam} não-financeiras adicionais.")
        df_top_non = df_non.sort_values('Score').head(n_non + faltam)

    df_final = pd.concat([df_top_non, df_top_fin], ignore_index=True).copy()
    df_final['Rank_Final_Soma'] = df_final['Score']
    df_final['Rank_Roman'] = df_final['Score'].rank(method='first', ascending=True).astype(int)

    # ------------------------------------------------------------------
    # PASSO 11 — Formatação da saída
    # ------------------------------------------------------------------
    df_final = df_final.rename(columns={
        'LIQUIDEZ MEDIA DIARIA': 'Liquidez_Media_Diaria',
        'EV/EBIT': 'EV_EBIT',
        'VALOR DE MERCADO': 'Valor_Mercado',
    })

    # Rank_EY e Rank_Momentum separados para exibição na tabela
    df_final['Rank_EY']  = df_final.apply(
        lambda r: int(r['Rank_Valor']) if r['SETOR'] == 'normal' else np.nan, axis=1)
    df_final['Rank_PVP'] = df_final.apply(
        lambda r: int(r['Rank_Valor']) if r['SETOR'] == 'financeira' else np.nan, axis=1)

    colunas_base = ['Rank_Roman', 'Rank_Final_Soma', 'Rank_EY', 'Rank_PVP', 'Rank_Momentum',
                    'TICKER', 'SETOR', 'Earnings_Yield', 'P/VP', 'Momentum',
                    'EV_EBIT', 'Liquidez_Media_Diaria']
    if 'Valor_Mercado' in df_final.columns:
        colunas_base.append('Valor_Mercado')
    if 'ROE' in df_final.columns:
        colunas_base.append('ROE')

    for c in colunas_base:
        if c not in df_final.columns:
            df_final[c] = np.nan

    resultado = df_final[colunas_base].sort_values('Rank_Roman').reset_index(drop=True)

    log("\n" + "=" * 70)
    log(f"CONCLUÍDO — Top {len(resultado)} selecionados "
        f"({len(df_top_non)} não-fin + {len(df_top_fin)} fin).")
    log("=" * 70)
    return resultado


# ==============================================================================
# INTERFACE GRÁFICA
# ==============================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Magic Formula — Roman Híbrida (EY + P/VP + Momentum)")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")
        self.minsize(1100, 720)

        self.caminho_bruto  = tk.StringVar()
        self.caminho_indice = tk.StringVar()
        self.resultado_df   = None

        self._build_ui()
        self._centralizar()
        threading.Thread(target=self._fetch_cotacao_bg, daemon=True).start()

    # ------------------------------------------------------------------
    def _centralizar(self):
        self.update_idletasks()
        w, h = 1200, 800
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _fetch_cotacao_bg(self):
        valor = buscar_cotacao_dolar()
        def _update():
            if valor is not None:
                self.v_cotacao.set(f"{valor:.4f}".replace(".", ","))
                self._lbl_cotacao_status.configure(
                    text="✔ cotação obtida via yfinance  (editável)", fg="#a6e3a1")
            else:
                self.v_cotacao.set("5,3000")
                self._lbl_cotacao_status.configure(
                    text="⚠ falha — valor padrão (editável)", fg="#f38ba8")
        self.after(0, _update)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def _build_ui(self):
        BG      = "#1e1e2e"
        BG2     = "#2a2a3e"
        ACCENT  = "#7c6af7"
        FG      = "#cdd6f4"
        FG2     = "#a6adc8"
        GREEN   = "#a6e3a1"
        RED     = "#f38ba8"
        YELLOW  = "#f9e2af"
        CYAN    = "#89dceb"
        ENTRY_BG = "#313244"

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            background=ENTRY_BG, foreground=FG,
            fieldbackground=ENTRY_BG, rowheight=26,
            font=("Consolas", 10))
        style.configure("Treeview.Heading",
            background=BG2, foreground=ACCENT,
            font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.configure("TScrollbar", background=BG2, troughcolor=BG,
                        arrowcolor=FG2, bordercolor=BG)

        # ---- Cabeçalho ----
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(hdr, text="Magic Formula  ·  Roman Híbrida (2021)",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 15, "bold")).pack(side="left")

        badge_frame = tk.Frame(hdr, bg=BG)
        badge_frame.pack(side="right")
        for txt, cor in [("EY", GREEN), ("+", FG2), ("P/VP", CYAN), ("+", FG2), ("MoM", YELLOW)]:
            tk.Label(badge_frame, text=txt, bg=BG, fg=cor,
                     font=("Segoe UI", 10, "bold")).pack(side="left", padx=2)

        tk.Label(self,
                 text="Não-financeiras: Earnings Yield + Momentum  |  "
                      "Financeiras: P/VP + Momentum  |  Proporção 70/30",
                 bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(pady=(2, 10))

        # ---- Corpo ----
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.columnconfigure(0, weight=0, minsize=340) # Aumentei levemente para caber a barra de rolagem
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ======================================================
        # PAINEL ESQUERDO (WRAPPER)
        # ======================================================
        # O left_wrapper vai segurar a área que rola em cima e os botões embaixo
        left_wrapper = tk.Frame(body, bg=BG2, bd=0)
        left_wrapper.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # --- BOTÕES FIXOS NA BASE ---
        bottom_btn_frame = tk.Frame(left_wrapper, bg=BG2)
        bottom_btn_frame.pack(side="bottom", fill="x", pady=(10, 0))

        self.btn_rodar = tk.Button(
            bottom_btn_frame, text="▶  Rodar estratégia híbrida",
            command=self._rodar, bg=ACCENT, fg="#ffffff",
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=10, pady=8, cursor="hand2", activebackground="#6a58e0")
        self.btn_rodar.pack(fill="x", padx=12, pady=(0, 6))

        self.btn_exportar = tk.Button(
            bottom_btn_frame, text="⬇  Exportar CSV",
            command=self._exportar, bg="#45475a", fg=FG,
            font=("Segoe UI", 9), relief="flat",
            padx=10, pady=6, cursor="hand2", state="disabled")
        self.btn_exportar.pack(fill="x", padx=12, pady=(0, 12))

        # --- ÁREA DE SCROLL (PARÂMETROS E ARQUIVOS) ---
        scroll_wrapper = tk.Frame(left_wrapper, bg=BG2)
        scroll_wrapper.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(scroll_wrapper, bg=BG2, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(scroll_wrapper, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")

        canvas.configure(yscrollcommand=scrollbar.set)

        # Este é o frame que vai REALMENTE segurar os inputs, e ele vive dentro do Canvas
        left = tk.Frame(canvas, bg=BG2)
        canvas_window = canvas.create_window((0, 0), window=left, anchor="nw")

        # Atualiza a área de rolagem sempre que o conteúdo do frame interno mudar
        def _configure_left_frame(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        # Atualiza a largura do frame interno sempre que o canvas redimensionar
        def _configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)

        left.bind("<Configure>", _configure_left_frame)
        canvas.bind("<Configure>", _configure_canvas)

        # Suporte para a rodinha do mouse apenas quando o cursor estiver na área esquerda
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        left_wrapper.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        left_wrapper.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        # ======================================================
        # FUNÇÕES AUXILIARES DE CRIAÇÃO (Agora aplicadas no frame 'left' rolável)
        # ======================================================
        def section(title):
            tk.Label(left, text=title, bg=BG2, fg=ACCENT,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
            tk.Frame(left, bg=ACCENT, height=1).pack(fill="x", padx=12, pady=(0, 8))

        def field(label, var, width=12):
            row = tk.Frame(left, bg=BG2)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, bg=BG2, fg=FG, font=("Segoe UI", 9),
                     width=23, anchor="w").pack(side="left")
            e = tk.Entry(row, textvariable=var, width=width,
                         bg=ENTRY_BG, fg=FG, insertbackground=FG,
                         relief="flat", font=("Consolas", 10))
            e.pack(side="left", padx=(4, 0))
            return e

        def file_row(label, var, cmd):
            tk.Label(left, text=label, bg=BG2, fg=FG2,
                     font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(4, 0))
            row = tk.Frame(left, bg=BG2)
            row.pack(fill="x", padx=12, pady=(2, 6))
            tk.Entry(row, textvariable=var, bg=ENTRY_BG, fg=FG2,
                     font=("Consolas", 8), relief="flat",
                     state="readonly").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="…", command=cmd, bg=ACCENT, fg="#ffffff",
                      font=("Segoe UI", 9, "bold"), relief="flat",
                      padx=6, cursor="hand2").pack(side="left", padx=(4, 0))

        # — Parâmetros Gerais —
        section("Parâmetros Gerais")
        self.v_num_ativos     = tk.StringVar(value=str(DEFAULT_NUM_ATIVOS))
        self.v_meses          = tk.StringVar(value=str(DEFAULT_MESES_MOMENTUM))
        self.v_cotacao        = tk.StringVar(value="carregando...")
        self.v_liquidez_usd   = tk.StringVar(value=str(DEFAULT_LIQUIDEZ_USD))
        self.v_market_cap_usd = tk.StringVar(value=str(DEFAULT_MARKET_CAP_USD))

        field("Nº de ativos",          self.v_num_ativos)
        field("Meses momentum",        self.v_meses)
        field("Cotação USD (R$)",       self.v_cotacao)
        self._lbl_cotacao_status = tk.Label(left, text="⏳ buscando via yfinance...",
                                             bg=BG2, fg=YELLOW, font=("Segoe UI", 8))
        self._lbl_cotacao_status.pack(anchor="w", padx=12, pady=(0, 4))
        field("Liquidez mín (US$)",    self.v_liquidez_usd, width=14)
        field("Market cap máx (US$)",  self.v_market_cap_usd, width=14)
        tk.Label(left, text="  (0 = sem filtro de market cap)",
                 bg=BG2, fg=FG2, font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        # — Parâmetros Híbridos —
        section("Estratégia Híbrida (Financeiras)")
        self.v_prop_fin  = tk.StringVar(value="30")   # percentual
        self.v_pvp_max   = tk.StringVar(value="1.5")
        self.v_roe_min   = tk.StringVar(value="10.0")
        field("% Financeiras na carteira", self.v_prop_fin, width=6)
        field("P/VP máximo (fin.)",         self.v_pvp_max, width=6)
        field("ROE mínimo % (fin.)",        self.v_roe_min, width=6)
        tk.Label(left, text="  (não-financeiras usam EY + MoM)",
                 bg=BG2, fg=FG2, font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        # — Toggle Momentum > 0 —
        self.v_filtrar_mom = tk.BooleanVar(value=False)
        tog = tk.Frame(left, bg=BG2)
        tog.pack(fill="x", padx=12, pady=(10, 4))
        self.chk_mom = tk.Checkbutton(
            tog, text="  Momentum > 0 ?",
            variable=self.v_filtrar_mom,
            command=self._atualizar_toggle_mom,
            bg=BG2, fg=FG, selectcolor=ENTRY_BG,
            activebackground=BG2, activeforeground=FG,
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2")
        self.chk_mom.pack(side="left")
        self.lbl_mom_status = tk.Label(tog, text="desativado  (fiel ao Roman)",
                                        bg=BG2, fg=FG2, font=("Segoe UI", 8))
        self.lbl_mom_status.pack(side="left", padx=(6, 0))

        # — Arquivos —
        section("Arquivos CSV")
        file_row("Base bruta (Status Invest)", self.caminho_bruto, self._sel_bruto)
        file_row("Composição do índice",       self.caminho_indice, self._sel_indice)

        # — Exportação —
        section("Exportação")
        self.v_saida = tk.StringVar(value=DEFAULT_CAMINHO_SAIDA)
        tk.Label(left, text="Caminho do CSV de saída", bg=BG2, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(4, 0))
        tk.Entry(left, textvariable=self.v_saida, bg=ENTRY_BG, fg=FG2,
                 font=("Consolas", 8), relief="flat").pack(fill="x", padx=12, pady=(2, 6))

        # ======================================================
        # PAINEL DIREITO
        # ======================================================
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)

        # — Log —
        log_frame = tk.Frame(right, bg=BG2)
        log_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        tk.Label(log_frame, text="Log de processamento", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        self.log_box = scrolledtext.ScrolledText(
            log_frame, bg=BG, fg=GREEN,
            font=("Consolas", 9), relief="flat",
            state="disabled", wrap="word")
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # — Tabela —
        tbl_frame = tk.Frame(right, bg=BG2)
        tbl_frame.grid(row=1, column=0, sticky="nsew")
        tbl_frame.rowconfigure(1, weight=1)
        tbl_frame.columnconfigure(0, weight=1)

        # Cabeçalho da tabela com legenda de cores
        tbl_hdr = tk.Frame(tbl_frame, bg=BG2)
        tbl_hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 4))
        tk.Label(tbl_hdr, text="Carteira selecionada", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        # Legenda
        for txt, cor in [("  ● Não-financeira (EY)", GREEN), ("  ● Financeira (P/VP)", CYAN)]:
            tk.Label(tbl_hdr, text=txt, bg=BG2, fg=cor, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(tbl_hdr, text="   duplo-clique = gráfico",
                 bg=BG2, fg=FG2, font=("Segoe UI", 8, "italic")).pack(side="left")

        cols = ("Rank", "Score", "Ticker", "Setor",
                "Rank Valor", "Rank Mom",
                "EY %", "P/VP", "ROE %", "Mom %",
                "EV/EBIT", "Liquidez (R$)", "Val. Mercado (R$)")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        widths = [45, 55, 70, 85, 75, 75, 68, 58, 60, 68, 68, 130, 145]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center", minwidth=35)
        self.tree.column("Ticker", anchor="w")
        self.tree.column("Liquidez (R$)", anchor="e")
        self.tree.column("Val. Mercado (R$)", anchor="e")

        # Tags de cor
        self.tree.tag_configure("non_fin_pos", foreground=GREEN)
        self.tree.tag_configure("non_fin_neg", foreground=RED)
        self.tree.tag_configure("fin_pos",     foreground=CYAN)
        self.tree.tag_configure("fin_neg",     foreground="#f5a97f")  # laranja p/ fin negativa

        self.tree.bind("<Double-1>", self._abrir_grafico)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0))
        vsb.grid(row=1, column=1, sticky="ns")
        hsb.grid(row=2, column=0, sticky="ew", padx=(8, 0))

        # Barra de status
        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(self, textvariable=self.status_var, bg=BG, fg=FG2,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=14, pady=(0, 6))
        
        
    # ------------------------------------------------------------------
    def _atualizar_toggle_mom(self):
        if self.v_filtrar_mom.get():
            self.lbl_mom_status.configure(text="ativado  (só Mom > 0)", fg="#a6e3a1")
            self.chk_mom.configure(fg="#a6e3a1")
        else:
            self.lbl_mom_status.configure(text="desativado  (fiel ao Roman)", fg="#a6adc8")
            self.chk_mom.configure(fg="#cdd6f4")

    # ------------------------------------------------------------------
    def _abrir_grafico(self, event):
        item = self.tree.focus()
        if not item:
            return
        valores = self.tree.item(item, "values")
        if not valores:
            return
        ticker = str(valores[2])   # coluna Ticker
        setor  = str(valores[3])

        meses = int(self.v_meses.get())
        hoje  = datetime.now().date()
        ontem = hoje - timedelta(days=1)
        data_ini = ontem - relativedelta(months=meses) - timedelta(days=7)

        self._status(f"Carregando gráfico de {ticker}...")
        self.btn_rodar.configure(state="disabled")

        def _baixar():
            ticker_yf = ticker if ticker.endswith(".SA") else ticker + ".SA"
            try:
                dados = yf.download(ticker_yf, start=str(data_ini), end=str(hoje),
                                    interval="1d", progress=False, auto_adjust=True)
            except Exception:
                dados = None
            self.after(0, lambda: self._mostrar_grafico(ticker, setor, meses, ontem, dados))

        threading.Thread(target=_baixar, daemon=True).start()

    def _mostrar_grafico(self, ticker, setor, meses, ontem, dados):
        self.btn_rodar.configure(state="normal", text="▶  Rodar estratégia híbrida")

        if dados is None or dados.empty:
            messagebox.showerror("Gráfico", f"Sem dados para {ticker}.")
            self._status("Pronto.")
            return

        col = "Close" if "Close" in dados.columns else "Adj Close"
        serie = dados[col].dropna()
        if serie.empty:
            messagebox.showerror("Gráfico", f"Dados insuficientes para {ticker}.")
            self._status("Pronto.")
            return

        data_alvo  = ontem - relativedelta(months=meses)
        mascara    = serie.index.date <= data_alvo
        preco_ini  = serie[mascara].iloc[-1].item() if mascara.any() else None
        preco_fim  = serie.iloc[-1].item()
        mom_pct    = ((preco_fim / preco_ini) - 1) * 100 if preco_ini else None

        win = tk.Toplevel(self)
        eh_fin = 'financeira' in setor.lower()
        cor_setor = "#89dceb" if eh_fin else "#a6e3a1"
        win.title(f"{ticker}  ({'Financeira · P/VP' if eh_fin else 'Não-fin · EY'})  "
                  f"— últimos {meses} meses")
        win.configure(bg="#1e1e2e")
        win.geometry("820x480")
        win.attributes("-topmost", True)

        fig, ax = plt.subplots(figsize=(9.5, 4.6), facecolor="#1e1e2e")
        ax.set_facecolor("#13131f")

        datas  = serie.index.to_pydatetime()
        precos = serie.values.flatten()
        cor_linha = cor_setor if (mom_pct or 0) >= 0 else "#f38ba8"

        ax.plot(datas, precos, color=cor_linha, linewidth=1.6, zorder=3)
        ax.fill_between(datas, precos, alpha=0.12, color=cor_linha, zorder=2)

        if preco_ini is not None:
            ax.axhline(preco_ini, color="#f9e2af", linewidth=0.8,
                       linestyle="--", alpha=0.7, zorder=4)
            mascara_ini = serie.index.date <= data_alvo
            if mascara_ini.any():
                data_ponto_ini = serie[mascara_ini].index[-1].to_pydatetime()
                ax.scatter(data_ponto_ini, preco_ini,
                           color="#f9e2af", edgecolors="#ffffff", s=70, zorder=6,
                           linewidths=1.2,
                           label=f"Início MoM ({data_ponto_ini.strftime('%d/%m/%y')})")
                ax.scatter(datas[-1], preco_fim,
                           color=cor_linha, edgecolors="#ffffff", s=70, zorder=6,
                           linewidths=1.2,
                           label=f"Ontem ({datas[-1].strftime('%d/%m/%y')})")
                ax.legend(loc="upper left", fontsize=8,
                          facecolor="#2a2a3e", edgecolor="#45475a", labelcolor="#cdd6f4")
            ax.annotate(f"Ref. {meses}m: R$ {preco_ini:.2f}",
                        xy=(datas[0], preco_ini), xytext=(8, 6),
                        textcoords="offset points", color="#f9e2af", fontsize=8)

        mom_txt   = f"{mom_pct:+.2f}%" if mom_pct is not None else "—"
        setor_txt = "Financeira [P/VP]" if eh_fin else "Não-fin [EY]"
        ax.set_title(f"{ticker}  ({setor_txt})   Momentum {meses}M: {mom_txt}",
                     color="#cdd6f4", fontsize=11, pad=10)
        ax.set_ylabel("Preço (R$)", color="#a6adc8", fontsize=9)
        ax.tick_params(colors="#a6adc8", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#313244")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b/%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        fig.autofmt_xdate(rotation=30, ha="right")
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"R$ {v:,.2f}".replace(",","X")
                              .replace(".","_").replace("X",".").replace("_",",")))
        ax.grid(color="#313244", linewidth=0.5, alpha=0.6)
        fig.tight_layout(pad=1.4)

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        tk.Button(win, text="Fechar",
                  command=lambda: (plt.close(fig), win.destroy()),
                  bg="#45475a", fg="#cdd6f4", relief="flat",
                  font=("Segoe UI", 9), padx=12, pady=4,
                  cursor="hand2").pack(pady=(0, 10))
        win.protocol("WM_DELETE_WINDOW", lambda: (plt.close(fig), win.destroy()))
        self._status(f"Gráfico de {ticker} aberto.")

    # ------------------------------------------------------------------
    def _sel_bruto(self):
        p = filedialog.askopenfilename(title="Base bruta (Status Invest)",
                                       filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if p:
            self.caminho_bruto.set(p)

    def _sel_indice(self):
        p = filedialog.askopenfilename(title="Composição do índice",
                                       filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if p:
            self.caminho_indice.set(p)

    # ------------------------------------------------------------------
    def _log(self, msg):
        def _write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _write)

    def _status(self, msg):
        self.after(0, lambda: self.status_var.set(msg))

    # ------------------------------------------------------------------
    def _validar(self):
        erros = []
        try:
            assert int(self.v_num_ativos.get()) > 0
        except: erros.append("Nº de ativos inválido.")
        try:
            assert int(self.v_meses.get()) > 0
        except: erros.append("Meses de momentum inválido.")
        try:
            assert float(self.v_cotacao.get().replace(',', '.')) > 0
        except: erros.append("Cotação do dólar inválida.")
        try:
            float(self.v_liquidez_usd.get().replace(',', '.'))
        except: erros.append("Liquidez mínima inválida.")
        try:
            float(self.v_market_cap_usd.get().replace(',', '.'))
        except: erros.append("Market cap máximo inválido.")
        try:
            p = float(self.v_prop_fin.get().replace(',', '.'))
            assert 0 <= p <= 100
        except: erros.append("% Financeiras inválido (0–100).")
        try:
            assert float(self.v_pvp_max.get().replace(',', '.')) > 0
        except: erros.append("P/VP máximo inválido.")
        try:
            float(self.v_roe_min.get().replace(',', '.'))
        except: erros.append("ROE mínimo inválido.")
        if not self.caminho_bruto.get():
            erros.append("Selecione o arquivo de base bruta.")
        if not self.caminho_indice.get():
            erros.append("Selecione o arquivo de composição do índice.")
        return erros

    # ------------------------------------------------------------------
    def _rodar(self):
        erros = self._validar()
        if erros:
            messagebox.showerror("Parâmetros inválidos", "\n".join(erros))
            return

        num_ativos     = int(self.v_num_ativos.get())
        meses          = int(self.v_meses.get())
        cotacao        = float(self.v_cotacao.get().replace(',', '.'))
        liquidez_usd   = float(self.v_liquidez_usd.get().replace(',', '.'))
        market_cap_usd = float(self.v_market_cap_usd.get().replace(',', '.'))
        prop_fin       = float(self.v_prop_fin.get().replace(',', '.')) / 100
        pvp_max        = float(self.v_pvp_max.get().replace(',', '.'))
        roe_min        = float(self.v_roe_min.get().replace(',', '.'))

        liquidez_brl   = liquidez_usd * cotacao
        market_cap_brl = (market_cap_usd * cotacao) if market_cap_usd > 0 else None

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.resultado_df = None
        self.btn_exportar.configure(state="disabled")
        self.btn_rodar.configure(state="disabled", text="Processando...")
        self._status("Processando...")

        self._log(f"Cotação USD: R$ {cotacao:.2f}")
        self._log(f"Liquidez mín: US$ {liquidez_usd:,.0f}  →  R$ {liquidez_brl:,.0f}")
        if market_cap_brl:
            self._log(f"Market cap máx: US$ {market_cap_usd:,.0f}  →  R$ {market_cap_brl:,.0f}")
        else:
            self._log("Market cap máx: desativado")
        self._log(f"Proporção financeiras: {prop_fin*100:.0f}%  |  "
                  f"P/VP ≤ {pvp_max}  |  ROE ≥ {roe_min}%")

        def _worker():
            resultado = roman_seletor_hibrido(
                caminho_csv_bruto=self.caminho_bruto.get(),
                caminho_csv_indice=self.caminho_indice.get(),
                num_ativos=num_ativos,
                meses_momentum=meses,
                liquidez_minima_brl=liquidez_brl,
                market_cap_maximo_brl=market_cap_brl,
                cotacao_dolar=cotacao,
                log_fn=self._log,
                filtrar_mom_positivo=self.v_filtrar_mom.get(),
                proporcao_financeiras=prop_fin,
                roe_minimo=roe_min,
                pvp_maximo=pvp_max,
            )
            self.after(0, lambda: self._pos_processamento(resultado))

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    def _pos_processamento(self, resultado):
        self.btn_rodar.configure(state="normal", text="▶  Rodar estratégia híbrida")

        if resultado is None or resultado.empty:
            self._status("Nenhum resultado encontrado.")
            messagebox.showinfo("Resultado", "Nenhum ativo encontrado com os filtros aplicados.")
            return

        self.resultado_df = resultado
        self.btn_exportar.configure(state="normal")

        def fmt_pct(v):
            return f"{v*100:.2f}%" if pd.notna(v) else "—"
        def fmt_mult(v):
            if pd.isna(v): return "—"
            return f"{v:,.2f}".replace(",","X").replace(".","_").replace("X",".").replace("_",",")
        def fmt_brl(v):
            if pd.isna(v): return "—"
            return f"R$ {v:,.2f}".replace(",","X").replace(".","_").replace("X",".").replace("_",",")
        def fmt_int(v):
            return str(int(v)) if pd.notna(v) else "—"

        for _, row in resultado.iterrows():
            mom     = row['Momentum']
            eh_fin  = str(row['SETOR']).lower() == 'financeira'
            tag     = ("fin_pos" if mom >= 0 else "fin_neg") if eh_fin \
                      else ("non_fin_pos" if mom >= 0 else "non_fin_neg")

            val_mercado = fmt_brl(row['Valor_Mercado']) if 'Valor_Mercado' in row else "—"
            roe_val     = fmt_pct(row['ROE'] / 100) if ('ROE' in row and pd.notna(row['ROE'])) else "—"

            self.tree.insert("", "end", tags=(tag,), values=(
                fmt_int(row['Rank_Roman']),
                fmt_int(row['Rank_Final_Soma']),
                row['TICKER'],
                row['SETOR'].upper(),
                fmt_int(row['Rank_EY']) if pd.notna(row['Rank_EY']) else
                    (f"P/VP:{fmt_int(row['Rank_PVP'])}" if pd.notna(row['Rank_PVP']) else "—"),
                fmt_int(row['Rank_Momentum']),
                fmt_pct(row['Earnings_Yield']),
                fmt_mult(row['P/VP']),
                roe_val,
                fmt_pct(mom),
                fmt_mult(row['EV_EBIT']),
                fmt_brl(row['Liquidez_Media_Diaria']),
                val_mercado,
            ))

        n_fin = len(resultado[resultado['SETOR'] == 'financeira'])
        n_non = len(resultado[resultado['SETOR'] == 'normal'])
        self._status(f"Concluído — {len(resultado)} ativos: {n_non} não-fin + {n_fin} fin.")

    # ------------------------------------------------------------------
    def _exportar(self):
        if self.resultado_df is None or self.resultado_df.empty:
            messagebox.showwarning("Exportar", "Nenhum resultado para exportar.")
            return
        caminho = self.v_saida.get().strip()
        if not caminho:
            caminho = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
                title="Salvar carteira como...")
        if not caminho:
            return
        try:
            dire = os.path.dirname(caminho)
            if dire and not os.path.exists(dire):
                os.makedirs(dire)
            self.resultado_df.to_csv(caminho, sep=DELIMITADOR_CSV,
                                     decimal=',', index=False, encoding='utf-8')
            messagebox.showinfo("Exportar", f"Arquivo salvo em:\n{caminho}")
            self._status(f"Exportado: {caminho}")
        except Exception as e:
            messagebox.showerror("Erro ao exportar", str(e))


# ==============================================================================
# ENTRADA
# ==============================================================================

if __name__ == "__main__":
    app = App()
    app.mainloop()