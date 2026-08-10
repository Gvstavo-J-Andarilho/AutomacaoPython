import pyautogui
import pyperclip
import time
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Altere para "saida_sigaa.txt" se vier do leitor do SIGAA
ARQUIVO_SAIDA = os.path.join(BASE_DIR, "saida_ia.txt")

URL_CALENDAR = "https://calendar.google.com/calendar/r"

# Imagem de referência para o botão "Salvar" do Calendar
# (capture com pyautogui.screenshot() e recorte — ou deixe None para usar Tab+Enter)
IMAGEM_SALVAR = None  # ex: os.path.join(BASE_DIR, "btnSalvar.png")

PRIORIDADE_COR = {
    "alta":   "Tomate",          # vermelho
    "média":  "Banana",          # amarelo
    "media":  "Banana",
    "baixa":  "Sálvia",          # verde
}

# -----------------------------
def intervalo(t=1):
    time.sleep(t)


# -----------------------------
# Converte "dd/mm/yyyy" para o formato do Google Calendar ("dia mês ano")
# Também aceita variações como "25 de junho de 2025"
# -----------------------------
def formatar_data_calendar(prazo_str):
    """
    Google Calendar aceita texto no campo de data.
    Retorna string no formato MM/DD/YYYY que o Google entende sem ambiguidade.
    """
    prazo_str = prazo_str.strip().lower()

    if prazo_str in ("sem prazo", "não há prazo", ""):
        return None

    # Tenta dd/mm/yyyy
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", prazo_str)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{mo}/{d}/{y}"  # MM/DD/YYYY para o Google

    # Tenta dd-mm-yyyy
    m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", prazo_str)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{mo}/{d}/{y}"

    # Tenta "25 de junho de 2025" (escrito por extenso)
    meses = {
        "janeiro": "01", "fevereiro": "02", "março": "03", "abril": "04",
        "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
        "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12"
    }
    for nome_mes, num_mes in meses.items():
        if nome_mes in prazo_str:
            partes = re.findall(r"\d+", prazo_str)
            if partes:
                dia = partes[0].zfill(2)
                ano = partes[-1] if len(partes) > 1 else datetime.now().strftime("%Y")
                return f"{num_mes}/{dia}/{ano}"

    # Devolve como está e deixa o Google tentar interpretar
    return prazo_str


# -----------------------------
# abrir google calendar
# -----------------------------
def abrir_calendar():
    pyautogui.press("win")
    intervalo(0.5)
    pyautogui.write("chrome", interval=0.05)
    pyautogui.press("enter")
    intervalo(2)

    pyautogui.hotkey("ctrl", "l")
    pyautogui.write(URL_CALENDAR, interval=0.03)
    pyautogui.press("enter")

    print("Abrindo Google Calendar...")
    intervalo(7)


# -----------------------------
# ler saída da IA ou do SIGAA
# -----------------------------
def carregar_eventos(arquivo=None):
    caminho = arquivo or ARQUIVO_SAIDA

    if not os.path.exists(caminho):
        print(f"Arquivo não encontrado: {caminho}")
        return []

    with open(caminho, "r", encoding="utf-8") as f:
        texto = f.read()

    linhas = texto.split("\n")
    eventos = []
    bloco = {}

    for linha in linhas:
        linha_strip = linha.strip()
        linha_lower = linha_strip.lower()

        if not linha_strip:
            continue

        if linha_lower.startswith("assunto:"):
            if bloco:
                eventos.append(bloco)
                bloco = {}
            bloco["assunto"] = linha_strip.split(":", 1)[1].strip()

        elif linha_lower.startswith("prazo:"):
            bloco["prazo"] = linha_strip.split(":", 1)[1].strip()

        elif linha_lower.startswith("prioridade:") or "grau de prioridade" in linha_lower:
            valor = re.sub(r"grau de prioridade\s*:?", "", linha_lower)
            valor = re.sub(r"prioridade\s*:?", "", valor)
            bloco["prioridade"] = valor.strip()

    if bloco:
        eventos.append(bloco)

    print(f"{len(eventos)} evento(s) carregado(s).")
    return eventos


# -----------------------------
# digitar num campo (limpa antes)
# -----------------------------
def digitar_campo(texto):
    pyautogui.hotkey("ctrl", "a")
    intervalo(0.3)
    pyautogui.hotkey("delete")
    intervalo(0.2)
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")
    intervalo(0.5)


# -----------------------------
# criar evento completo no Calendar
# -----------------------------
def criar_evento(evento):
    assunto   = evento.get("assunto", "Sem assunto")
    prioridade = evento.get("prioridade", "média").lower()
    prazo_raw  = evento.get("prazo", "")

    data_formatada = formatar_data_calendar(prazo_raw)

    print(f"\nCriando: '{assunto}' | prazo: {prazo_raw} → {data_formatada} | {prioridade}")

    # ---- Abre o modal de novo evento com a tecla 'c' ----
    pyautogui.press("c")
    intervalo(2.5)

    # ---- Campo TÍTULO ----
    # O cursor já está no campo de título ao abrir
    pyautogui.write(assunto, interval=0.03)
    intervalo(0.5)

    # ---- Clica em "Mais opções" para abrir o editor completo ----
    # Usa Tab para chegar no botão "Mais opções" (geralmente 2-3 tabs)
    pyautogui.press("tab", presses=3, interval=0.15)
    intervalo(0.3)
    pyautogui.press("enter")
    intervalo(3.5)

    # ---- No editor completo ----
    # Tab 1: campo de data início
    pyautogui.press("tab", presses=1, interval=0.2)
    intervalo(0.5)

    if data_formatada:
        digitar_campo(data_formatada)
        pyautogui.press("enter")
        intervalo(0.5)

    # Pula hora início → hora fim → data fim (mesma data = prazo)
    pyautogui.press("tab", presses=2, interval=0.2)
    intervalo(0.3)

    if data_formatada:
        digitar_campo(data_formatada)
        pyautogui.press("enter")
        intervalo(0.5)

    # ---- Campo DESCRIÇÃO ----
    # Tab até a caixa de descrição (~6 tabs depois do campo de data)
    pyautogui.press("tab", presses=6, interval=0.15)
    intervalo(0.3)

    descricao = f"Prioridade: {prioridade.upper()} | Prazo original: {prazo_raw}"
    pyautogui.write(descricao, interval=0.03)
    intervalo(0.5)

    # ---- Salvar o evento ----
    # Ctrl+S salva diretamente no Google Calendar
    pyautogui.hotkey("ctrl", "s")
    intervalo(3)

    # Fallback: se imagem do botão salvar estiver configurada
    if IMAGEM_SALVAR and os.path.exists(IMAGEM_SALVAR):
        try:
            loc = pyautogui.locateCenterOnScreen(IMAGEM_SALVAR, confidence=0.7)
            if loc:
                pyautogui.click(loc)
                intervalo(2)
        except Exception as e:
            print(f"  Aviso: botão salvar não encontrado via imagem ({e})")

    print(f"  ✓ Evento criado.")


# -----------------------------
# pipeline principal
# -----------------------------
def executar(arquivo_saida=None):
    eventos = carregar_eventos(arquivo_saida)

    if not eventos:
        print("Nenhum evento para criar.")
        return

    abrir_calendar()

    sucessos = 0
    for evento in eventos:
        try:
            criar_evento(evento)
            sucessos += 1
            intervalo(2)
        except Exception as e:
            print(f"  Erro ao criar evento '{evento.get('assunto','')}': {e}")
            # Tenta fechar qualquer modal aberto e continua
            pyautogui.press("escape")
            intervalo(1)

    print(f"\n✓ {sucessos}/{len(eventos)} eventos criados no Google Calendar.")


if __name__ == "__main__":
    # Para usar com a saída do SIGAA:
    #   executar(os.path.join(BASE_DIR, "saida_sigaa.txt"))
    # Para usar com a saída da IA (emails):
    #   executar()
    executar()
