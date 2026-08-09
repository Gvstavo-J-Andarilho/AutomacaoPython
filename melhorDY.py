import concurrent.futures
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from playwright.sync_api import sync_playwright

# =========================================================================
# CONFIGURAÇÃO DE LOGGING
# =========================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# =========================================================================
# 1. CONFIGURAÇÕES DA HOLDING BARBELL & UNIVERSO CORE 2.0
# =========================================================================
VALOR_APORTE_MENSAL = 300.00  # Dinheiro novo + Proventos do mês
ARQUIVO_POSICAO = "posicao.json"

POSICAO_INICIAL_DEFAULT = {
    "LFTB11": 30,
    "BERK34": 5,
    "CDI": 700.0,
    "BBAS3": 27,
}

TARGET_BARBELL = {
    "LFTB11": 0.35,    # 35% Liquidez R$ (Caixa / Pós-Fixado)
    "BERK34": 0.30,    # 30% Dollar / Global Value Investing
    "CDI": 0.15,       # 15% Reserva Caixa / Liquidez Impartível
    "ACOES_B3": 0.20,  # 20% Caçador de Pechinchas B3
}

# PRÊMIOS DE RISCO EXIGIDOS SOBRE O TESOURO IPCA+ (Para formar a TAXA ALVO REAL)
PREMIO_RISCO_RENDA = 0.01        # +1.0% a.a. sobre IPCA+ (Ex: IPCA + TAXA% + 1,0%)
PREMIO_RISCO_CRESCIMENTO = 0.030   # +3.0% a.a. sobre IPCA+ (Ex: IPCA + TAXA% + 3%)
PREMIO_RISCO_CICLICO = 0.040       # +4.0% a.a. sobre IPCA+ (Ex: IPCA + TAXA% + 4%)

MARGEM_MINIMA_PECHINCHA = 15.0     # Mínimo 15% de margem para RENDA
MARGEM_MINIMA_CICLICO = 20.0       # Mínimo 20% de margem para CÍCLICOS/CRESCIMENTO
ROE_MINIMO_EXIGIDO = 0.10          # Mínimo 10% de ROE
LIQUIDEZ_MINIMA_DIARIA = 1_000_000.0

# PREMISSAS MACRO E DE CRESCIMENTO REAL (PERPÉTUO E EXPLÍCITO)
G_PERPETUO_REAL = 0.015            # 1.5% real a.a. (Crescimento do PIB de longo prazo)
ANOS_PROJECAO_EXPLICITA = 5

UNIVERSO_CORE = {
    "Energia": ("RENDA", ["ALUP11.SA", "CMIG4.SA", "CPFE3.SA", "EGIE3.SA", "ISAE4.SA", "TAEE11.SA", "AXIA7.SA", "EQTL3.SA"]),
    "Saneamento": ("RENDA", ["CSMG3.SA", "SAPR11.SA", "SBSP3.SA"]),
    "Financeiro": ("RENDA", ["BBAS3.SA", "BBSE3.SA", "CXSE3.SA", "ITUB4.SA", "PSSA3.SA", "ITSA4.SA", "B3SA3.SA", "SANB4.SA", "ABCB3.SA"]),
    "Telecom": ("RENDA", ["VIVT3.SA", "TIMS3.SA"]),
    "Crescimento": ("CRESCIMENTO", ["WEGE3.SA", "RADL3.SA", "FLRY3.SA", "SHUL4.SA", "KEPL3.SA", "TASA4.SA", "GMAT3.SA", "CAML3.SA", "ASAI3.SA", "PGMN3.SA", "BLAU3.SA"]),
    "Ciclico": ("CICLICO", ["PETR4.SA", "VALE3.SA", "KLBN3.SA", "FESA4.SA", "UNIP6.SA", "BRAP4.SA", "EUCA4.SA", "RANI3.SA", "GOAU4.SA", "CMIN3.SA", "GGBR4.SA"]),
}

# PREMISSAS DE CRESCIMENTO EXPLÍCITO PADRÃO POR PROFILE (g_explicito)
G_EXPLICITO_PADRAO = {
    "RENDA": 0.020,        # 2.0% real
    "CRESCIMENTO": 0.050,  # 5.0% real
    "CICLICO": 0.010       # 1.0% real
}

# =========================================================================
# 2. CAPTURA DA TAXA TESOURO IPCA+ VIA PLAYWRIGHT
# =========================================================================
def obter_taxa_tesouro_ipca_playwright() -> float:
    try:
        logging.info("Acessando Tesouro Direto via Playwright...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            page = context.new_page()
            page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf,css}", lambda route: route.abort())
            page.goto("https://www.tesourodireto.com.br/produtos/titulos/ipca-mais", wait_until="domcontentloaded", timeout=30000)
           
            locator = page.locator("p", has_text=re.compile(r"IPCA\s*\+\s*\d+")).first
            locator.wait_for(state="attached", timeout=15000)
           
            texto = locator.inner_text().strip()
            browser.close()

            match = re.search(r"(\d+[\.,]\d+)", texto)
            if match:
                taxa = float(match.group(1).replace(",", ".")) / 100.0
                logging.info(f"Taxa do Tesouro IPCA+ extraída: {taxa:.2%}")
                return taxa
            else:
                raise ValueError("Taxa não encontrada no texto.")
    except Exception as e:
        logging.warning(f"Falha no Playwright ({e}). Contingência utilizada: 6.50%.")
        return 0.0650

# =========================================================================
# 3. MOTOR DE CÁLCULO QUANTITATIVO FCD (PERÍODO EXPLÍCITO + TERMINAL)
# =========================================================================
def calcular_preco_teto_fcd(
    fluxo_caixa_base: float,
    taxa_alvo_real: float,
    g_explicito: float,
    g_perpetuo: float,
    divida_liquida: float,
    total_acoes: float
) -> float:
    """
    Calcula o Preço Teto por ação com base em projeção de 5 anos explícitos 
    mais valor terminal, descontados pela taxa alvo real (Ex: IPCA + 10%).
    """
    if taxa_alvo_real <= g_perpetuo or total_acoes <= 0 or fluxo_caixa_base <= 0:
        return 0.0
        
    fluxos_descontados = []
    caixa_projetado = fluxo_caixa_base
    
    # 1. Projeta e desconta o fluxo de caixa explícito (Anos 1 a 5)
    for ano in range(1, ANOS_PROJECAO_EXPLICITA + 1):
        caixa_projetado = caixa_projetado * (1.0 + g_explicito)
        fluxo_valor_presente = caixa_projetado / ((1.0 + taxa_alvo_real) ** ano)
        fluxos_descontados.append(fluxo_valor_presente)
        
    # 2. Calcula o Valor Terminal na Perpetuidade (Modelo de Gordon)
    caixa_ano_6 = caixa_projetado * (1.0 + g_perpetuo)
    valor_terminal = caixa_ano_6 / (taxa_alvo_real - g_perpetuo)
    pv_valor_terminal = valor_terminal / ((1.0 + taxa_alvo_real) ** ANOS_PROJECAO_EXPLICITA)
    
    # 3. Consolida o Enterprise Value Máximo aceitável pelo modelo
    ev_maximo_aceitavel = sum(fluxos_descontados) + pv_valor_terminal
    
    # 4. Encontra o Valor do Equity (Descontando a Dívida Líquida)
    equity_maximo = ev_maximo_aceitavel - divida_liquida
    
    # 5. Retorna o Preço Teto por Ação
    preco_teto = equity_maximo / total_acoes
    return max(0.0, float(preco_teto))

# =========================================================================
# 4. PERSISTÊNCIA E AUXILIARES
# =========================================================================
def salvar_posicao(posicao: dict, arquivo: str = ARQUIVO_POSICAO) -> None:
    try:
        with open(arquivo, "w") as f:
            json.dump(posicao, f, indent=2)
    except Exception as e:
        logging.error(f"Erro ao salvar posição em arquivo: {e}")

def carregar_posicao(arquivo: str = ARQUIVO_POSICAO) -> dict:
    if os.path.exists(arquivo):
        try:
            with open(arquivo, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return POSICAO_INICIAL_DEFAULT.copy()

def obter_base_ticker(ticker_str: str) -> str:
    clean = ticker_str.replace(".SA", "")
    return re.sub(r"\d+.*$", "", clean)

def verificar_alavancagem_saudavel(info: dict) -> bool:
    try:
        total_cash = float(info.get("totalCash") or 0.0)
        total_debt = float(info.get("totalDebt") or 0.0)
        ebitda = float(info.get("ebitda") or 0.0)
        if ebitda <= 0:
            return total_debt <= total_cash
        return (total_debt - total_cash) / ebitda <= 2.5
    except Exception:
        return True

def e_value_trap_lucro_cadente(financials: pd.DataFrame) -> bool:
    try:
        if financials is None or financials.empty:
            return False
        net_income = None
        for col in ["Net Income", "Net Income Common Stockholders"]:
            if col in financials.index:
                net_income = financials.loc[col].dropna()
                break
        if net_income is None or len(net_income) < 3:
            return False
        lucros = net_income.sort_index(ascending=False).values
        if lucros[1] > 0 and lucros[0] > 0:
            media_anteriores = sum(lucros[1:4]) / len(lucros[1:4])
            return media_anteriores > 0 and lucros[0] < media_anteriores * 0.75
        return False
    except Exception:
        return False

def obter_roe_historico_ponderado(acao: yf.Ticker, roe_fallback: float = 0.0) -> float:
    try:
        financials = acao.financials
        balance_sheet = acao.balance_sheet
        if financials.empty or balance_sheet.empty:
            return roe_fallback
        net_income = financials.loc["Net Income"] if "Net Income" in financials.index else None
        equity = None
        for eq_col in ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]:
            if eq_col in balance_sheet.index:
                equity = balance_sheet.loc[eq_col]
                break
        if net_income is None or equity is None:
            return roe_fallback
        datas = net_income.dropna().index.intersection(equity.dropna().index).sort_values(ascending=False)
        roes = [net_income[d] / equity[d] for d in datas[:5] if net_income[d] and equity[d] > 0]
        if roes:
            pesos = list(range(len(roes), 0, -1))
            return min(max(sum(r * p for r, p in zip(roes, pesos)) / sum(pesos), 0.0), 0.80)
    except Exception:
        pass
    return roe_fallback

def classificar_ativo(ticker: str) -> str:
    if ticker in TARGET_BARBELL:
        return ticker
    return "ACOES_B3"

def cotar_precos_carteira(posicao_atual: dict) -> Dict[str, float]:
    precos = {}
    for tkn in posicao_atual.keys():
        if tkn == "CDI":
            precos[tkn] = 1.0
            continue
        candidatos = [tkn, tkn[:-3]] if tkn.endswith(".SA") else [f"{tkn}.SA", tkn]
        preco_encontrado = None
        for candidate in candidatos:
            try:
                fast = yf.Ticker(candidate).fast_info
                p = fast.get("lastPrice") or fast.get("previousClose")
                if p is not None and float(p) > 0:
                    preco_encontrado = float(p)
                    break
            except Exception:
                continue
        if preco_encontrado is not None:
            precos[tkn] = preco_encontrado
    return precos

# =========================================================================
# 5. PROCESSAMENTO PARALELO DE VALUATION (FCD + IPCA+)
# =========================================================================
def processar_ticker_individual(args: Tuple[str, str, str, int, float]) -> Optional[dict]:
    ticker, setor, categoria, ano_atual, taxa_tesouro_ipca = args
    try:
        acao = yf.Ticker(ticker)
        fast = acao.fast_info
        preco_atual = fast.get("lastPrice") or fast.get("previousClose")
        if not preco_atual or preco_atual <= 0:
            return None

        vol = fast.get("threeMonthAverageVolume") or fast.get("tenDayAverageVolume") or 0
        liquidez = vol * preco_atual
        if liquidez < LIQUIDEZ_MINIMA_DIARIA:
            return None

        info = acao.info
        if setor != "Financeiro" and not verificar_alavancagem_saudavel(info):
            return None

        financials = acao.financials
        if e_value_trap_lucro_cadente(financials):
            return None

        roe_5a = obter_roe_historico_ponderado(acao, info.get("returnOnEquity") or 0.0)
        if roe_5a < ROE_MINIMO_EXIGIDO:
            return None

        # DEFINIÇÃO DA TAXA ALVO REAL EXIGIDA (IPCA + X%)
        if categoria == "RENDA":
            premio_exigido = PREMIO_RISCO_RENDA
        elif categoria == "CRESCIMENTO":
            premio_exigido = PREMIO_RISCO_CRESCIMENTO
        else:
            premio_exigido = PREMIO_RISCO_CICLICO

        taxa_alvo_real = taxa_tesouro_ipca + premio_exigido
        g_explicito = G_EXPLICITO_PADRAO.get(categoria, 0.02)

        # CÁLCULO DO PREÇO TETO
        if categoria == "RENDA":
            divs = acao.dividends
            if divs.empty:
                return None
            divs.index = pd.to_datetime(divs.index).tz_localize(None)
            divs_completos = divs.resample("YE").sum()
            divs_completos = divs_completos[divs_completos.index.year < ano_atual]

            if divs_completos.empty or (divs_completos.tail(3) > 0).sum() < 2:
                return None

            media_div = divs_completos.tail(5).mean()
            if media_div <= 0:
                return None

            preco_teto = media_div / taxa_alvo_real
            cagr_div = 0.0
            margem_exigida = MARGEM_MINIMA_PECHINCHA
        else:
            # EXTRAÇÃO AUTOMÁTICA DE DADOS FCD (YFINANCE)
            total_acoes = float(fast.get("shares") or info.get("sharesOutstanding") or 0.0)
            
            # Caixa, Dívidas e Dívida Líquida
            total_cash = float(info.get("totalCash") or 0.0)
            total_debt = float(info.get("totalDebt") or 0.0)
            divida_liquida = total_debt - total_cash

            # Fluxo de Caixa Livre (FCF LTM)
            cashflow = acao.cashflow
            fco = float(info.get("operatingCashflow") or 0.0)
            capex = float(info.get("capitalExpenditures") or 0.0)
            fcf_ltm = fco - abs(capex)

            # Fallback para Lucro Líquido caso FCF venha negativo/zerado por giro
            if fcf_ltm <= 0:
                if financials is not None and "Net Income" in financials.index:
                    fcf_ltm = float(financials.loc["Net Income"].dropna().iloc[0])
                else:
                    return None

            preco_teto = calcular_preco_teto_fcd(
                fluxo_caixa_base=fcf_ltm,
                taxa_alvo_real=taxa_alvo_real,
                g_explicito=g_explicito,
                g_perpetuo=G_PERPETUO_REAL,
                divida_liquida=divida_liquida,
                total_acoes=total_acoes
            )
            cagr_div = 0.0
            margem_exigida = MARGEM_MINIMA_CICLICO

        if preco_teto <= 0:
            return None

        margem_seg = ((preco_teto - preco_atual) / preco_teto) * 100
        status = "COMPRAR" if margem_seg >= margem_exigida else "AGUARDAR"
        score = (margem_seg * 0.50) + ((roe_5a * 100) * 0.50)

        return {
            "Ticker": ticker.replace(".SA", ""),
            "Base_Ticker": obter_base_ticker(ticker),
            "Setor": setor,
            "Perfil": categoria,
            "Preço Atual (R$)": round(preco_atual, 2),
            "Preço Teto Alvo": round(preco_teto, 2),
            "Taxa Alvo Real": f"IPCA + {taxa_alvo_real * 100:.2f}%",
            "Margem %": round(margem_seg, 1),
            "ROE 5a %": round(roe_5a * 100, 1),
            "Score": round(score, 2),
            "Liquidez (R$)": round(liquidez, 2),
            "Decisão": status,
        }
    except Exception:
        return None

def analisar_fasest_paralelo(taxa_tesouro: float) -> pd.DataFrame:
    ano_atual = pd.Timestamp.now().year
    tarefas = [
        (ticker, setor, categoria, ano_atual, taxa_tesouro)
        for setor, (categoria, tickers) in UNIVERSO_CORE.items()
        for ticker in tickers
    ]

    resultados = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(processar_ticker_individual, tarefas):
            if res:
                resultados.append(res)

    if not resultados:
        return pd.DataFrame()

    df = pd.DataFrame(resultados)
    df = df.sort_values(by="Liquidez (R$)", ascending=False).drop_duplicates(subset=["Base_Ticker"], keep="first")
    return df.drop(columns=["Base_Ticker", "Liquidez (R$)"]).sort_values(by="Score", ascending=False)

# =========================================================================
# 6. REBALANCEAMENTO POR GAP
# =========================================================================
def executar_rebalanceamento_por_gap(
    df_fasest: pd.DataFrame,
    aporte_dinheiro: float,
    posicao_atual: dict,
    precos: dict
) -> Tuple[pd.DataFrame, pd.DataFrame, float, float, float, dict]:
    valores_atuais = {tkn: qtd * precos[tkn] for tkn, qtd in posicao_atual.items() if tkn in precos}
    valores_por_classe = {classe: 0.0 for classe in TARGET_BARBELL.keys()}
    
    for tkn, val in valores_atuais.items():
        macro_classe = classificar_ativo(tkn)
        valores_por_classe[macro_classe] = valores_por_classe.get(macro_classe, 0.0) + val

    patrimonio_atual = sum(valores_atuais.values())
    patrimonio_futuro = patrimonio_atual + aporte_dinheiro

    diagnostico = []
    gaps_financeiros = {}
    soma_total_gaps = 0.0

    for classe, target_pct in TARGET_BARBELL.items():
        val_atual = valores_por_classe.get(classe, 0.0)
        pct_atual = (val_atual / patrimonio_atual * 100) if patrimonio_atual > 0 else 0.0
        val_ideal = patrimonio_futuro * target_pct
        gap = max(0.0, val_ideal - val_atual)

        gaps_financeiros[classe] = gap
        soma_total_gaps += gap
        alerta = "SOBREPESO" if pct_atual > (target_pct * 100 * 1.5) or gap == 0 else "OK"

        diagnostico.append({
            "Classe Barbell": classe,
            "Valor Atual (R$)": round(val_atual, 2),
            "% Atual": round(pct_atual, 1),
            "% Meta": round(target_pct * 100, 1),
            "Valor Ideal (R$)": round(val_ideal, 2),
            "Déficit/Gap (R$)": round(gap, 2),
            "Status": alerta,
        })

    orcamento_por_classe = {
        k: (aporte_dinheiro * (v / soma_total_gaps) if soma_total_gaps > 0 else 0.0)
        for k, v in gaps_financeiros.items()
    }

    saldo_restante = aporte_dinheiro
    ordens = []
    novas_compras_qtd = {tkn: 0 for tkn in posicao_atual.keys()}

    verba_acoes = orcamento_por_classe.get("ACOES_B3", 0.0)
    pechinchas_b3 = df_fasest[df_fasest["Decisão"] == "COMPRAR"].copy() if not df_fasest.empty else pd.DataFrame()

    if verba_acoes > 0 and not pechinchas_b3.empty:
        pechinchas_b3["Fator"] = pechinchas_b3["Score"].apply(lambda x: max(x, 0.1))
        soma_fatores = pechinchas_b3["Fator"].sum()

        for _, row in pechinchas_b3.iterrows():
            ticker = row["Ticker"]
            preco = row["Preço Atual (R$)"]
            fatia = (row["Fator"] / soma_fatores) * verba_acoes
            cotas = int(fatia // preco)
            custo = cotas * preco

            if cotas > 0 and saldo_restante >= custo:
                ordens.append({
                    "Classe": f"Ação B3 ({row['Perfil']})",
                    "Ticker": ticker,
                    "Cotas a Comprar": cotas,
                    "Preço Unit. (R$)": preco,
                    "Total Gasto (R$)": round(custo, 2),
                    "Score": row["Score"],
                    "% do Aporte": round((custo / aporte_dinheiro) * 100, 1),
                })
                saldo_restante -= custo
                novas_compras_qtd[ticker] = novas_compras_qtd.get(ticker, 0) + cotas

    for ativo_cons in ["BERK34", "LFTB11", "CDI"]:
        if gaps_financeiros.get(ativo_cons, 0) <= 0 or ativo_cons not in precos:
            continue
        verba_ativo = orcamento_por_classe.get(ativo_cons, 0.0)
        if verba_ativo <= 0 or saldo_restante <= 0:
            continue

        preco_ativo = precos[ativo_cons]
        if ativo_cons == "CDI":
            custo_ativo = min(verba_ativo, saldo_restante)
            cotas_ativo = round(custo_ativo, 2)
        else:
            cotas_ativo = int(verba_ativo // preco_ativo)
            custo_ativo = cotas_ativo * preco_ativo

        if cotas_ativo > 0 and saldo_restante >= custo_ativo:
            ordens.append({
                "Classe": f"Conservador ({ativo_cons})",
                "Ticker": ativo_cons,
                "Cotas a Comprar": cotas_ativo,
                "Preço Unit. (R$)": round(preco_ativo, 2),
                "Total Gasto (R$)": round(custo_ativo, 2),
                "Score": "-",
                "% do Aporte": round((custo_ativo / aporte_dinheiro) * 100, 1),
            })
            saldo_restante -= custo_ativo
            novas_compras_qtd[ativo_cons] = novas_compras_qtd.get(ativo_cons, 0) + cotas_ativo

    posicao_atualizada = posicao_atual.copy()
    for tkn, qtd_comprada in novas_compras_qtd.items():
        if qtd_comprada > 0:
            posicao_atualizada[tkn] = posicao_atualizada.get(tkn, 0) + qtd_comprada

    return pd.DataFrame(diagnostico), pd.DataFrame(ordens), patrimonio_atual, patrimonio_futuro, saldo_restante, posicao_atualizada

# =========================================================================
# 7. EXECUÇÃO PRINCIPAL
# =========================================================================
if __name__ == "__main__":
    print("\n⏳ Inicializando F.A.S.E.S.T.I.C. 2.0 (Playwright + FCD IPCA+ Engine)...")
   
    taxa_tesouro = obter_taxa_tesouro_ipca_playwright()
    posicao_atual = carregar_posicao()

    df_analise = analisar_fasest_paralelo(taxa_tesouro)
    precos_mercado = cotar_precos_carteira(posicao_atual)

    df_diag, df_ordens, pat_atual, pat_futuro, troco, posicao_nova = executar_rebalanceamento_por_gap(
        df_analise, VALOR_APORTE_MENSAL, posicao_atual, precos_mercado
    )

    salvar_posicao(posicao_nova)

    # OUTPUT VISUAL
    print("=" * 95)
    print(" 🏆 RANKING UNIVERSO CORE (PREÇO TETO PARA RETORNO IPCA+ DESEJADO)")
    print("=" * 95)
    if not df_analise.empty:
        # Garante a formatação e aplica o filtro de margem >= 0
        df_analise["Margem %"] = pd.to_numeric(df_analise["Margem %"], errors="coerce")
        df_exibicao = df_analise[df_analise["Margem %"] >= 0]

        if not df_exibicao.empty:
            cols_exibir = ["Ticker", "Perfil", "Preço Atual (R$)", "Preço Teto Alvo", "Taxa Alvo Real", "Margem %", "ROE 5a %", "Score", "Decisão"]
            print(df_exibicao[cols_exibir].to_string(index=False))
        else:
            print("⚠️ Nenhuma ação do Universo Core está com Margem % maior ou igual a 0% no momento.")
    else:
        print("⚠️ Nenhum ativo aprovado nos filtros quantitativos.")

    print("\n" + "=" * 95)
    print(" 📊 DIAGNÓSTICO DA CARTEIRA BARBELL")
    print("=" * 95)
    print(f"• Patrimônio Atual:   R$ {pat_atual:.2f}")
    print(f"• Aporte do Mês:      R$ {VALOR_APORTE_MENSAL:.2f}")
    print(f"• Patrimônio Futuro:  R$ {pat_futuro:.2f}\n")
    print(df_diag.to_string(index=False))

    print("\n" + "=" * 95)
    print(" 🛒 ORDENS REBALANCEADAS POR DÉFICIT (GAP)")
    print("=" * 95)
    if not df_ordens.empty:
        print(df_ordens.to_string(index=False))
        print(f"\n💡 Sobra/Troco Residual: R$ {troco:.2f}")
        print(f"💾 Posição atualizada salva com sucesso em '{ARQUIVO_POSICAO}'.")
    else:
        print("⚠️ O valor do aporte não foi suficiente para comprar ao menos 1 cota dos ativos em déficit.")