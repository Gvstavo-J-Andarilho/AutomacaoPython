import pyautogui
import pyperclip
import time
import os

BASE_DIR = os.path.dirname(__file__)
IMAGEM_ARQUIVO = os.path.join(BASE_DIR, "imagemArquivo.png")
ARQUIVO_EMAILS = os.path.join(BASE_DIR, "entrada_ia.txt")
IMAGEM_ESCREVER = os.path.join(BASE_DIR, "escreverNaIA.png")
PROMPT = os.path.join(BASE_DIR, "promptEmail.txt")

respostas_chave = [
    "assunto:",
    "prazo:",
    "grau de prioridade:"
]

stirpar = [
    "Ctrl+J",
    "siga os comandos do 'promptEmail.txt'",
    "promptEmail.txt",
    "entrada_ia.txt",
    "1,2s",
    "Fazer um upgrade para o SuperGrok",
    "New conversation - Grok",
    "Iniciar ditado (Ctrl+D)Iniciar ditado (Ctrl+D)"
]

URL_IA = "https://grok.com/"  # pode trocar pela IA que quiser

def intervalo(n=None):
    if n is None:
        time.sleep(1)
    else:
        time.sleep(n)

def abrir_ia():

    pyautogui.press('win')
    time.sleep(0.5)

    pyautogui.write("chrome",interval=0.05)
    pyautogui.press("enter")
    intervalo()
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyautogui.write(URL_IA,interval=0.05)
    pyautogui.press("enter")
    print("Aguardando IA carregar...")
    time.sleep(5)


def carregar_textos():

    try:
        arquivos=["promptEmail.txt","entrada_ia.txt"]
        
        for arquivo in arquivos:
            intervalo(3)
            if arquivo == arquivos[0]:
                pyautogui.press("tab")
                intervalo()
            
            for i in range(2):
                intervalo()
                pyautogui.press("enter")
                intervalo(2)
            
            pyautogui.hotkey("ctrl", "f")
            pyautogui.write(arquivo, interval=0.02)
            intervalo()
            loc = pyautogui.locateCenterOnScreen(IMAGEM_ARQUIVO, confidence=0.5)
            if loc:
                intervalo(2)
                pyautogui.doubleClick(loc)
                pyautogui.moveTo(500,500)
                intervalo(2)
                continue

    except Exception as e:
        print(f"Erro ao carregar prompt: {e}")
        return ""


def enviar_prompt():
    
    pyautogui.press("tab", interval=1)
    pyautogui.press("tab", interval=1)
    pyautogui.write("siga os comandos do 'promptEmail.txt'", interval=0.1)
    intervalo()
    pyautogui.press("enter")
    print("Esperando resposta da IA...")
    intervalo(10)

def limpar_resposta(texto):

    for lixo in stirpar:
        texto = texto.replace(lixo, "")

    linhas = texto.split("\n")

    eventos = []
    bloco = {}

    for linha in linhas:
        linha = linha.strip()

        linha_lower = linha.lower()

        # NOVO BLOCO
        if linha_lower.startswith("assunto:"):
            if bloco:
                eventos.append(bloco)
                bloco = {}

            bloco["assunto"] = linha.split(":",1)[1].strip()


        elif linha_lower.startswith("prazo:"):
            bloco["prazo"] = linha.split(":",1)[1].strip()


        elif ("prioridade" in linha_lower):
            # remove qualquer variação tipo "prioridade: :" etc
            valor = linha.split(":",1)[1].replace(":", "").strip()
            bloco["prioridade"] = valor

    if bloco:
        eventos.append(bloco)

    return eventos


def copiar_resposta():
    for t in range(3):
        pyautogui.press("tab")
        intervalo(3)

    pyautogui.hotkey("ctrl", "a")
    intervalo(2)

    pyautogui.hotkey("ctrl", "c")
    time.sleep(1)

    resposta = pyperclip.paste()

    eventos = limpar_resposta(resposta)

    print("Eventos interpretados:")
    for e in eventos:
        print(e)

    CAMINHO_TXT = os.path.join(BASE_DIR, "saida_ia.txt")

    with open(CAMINHO_TXT, "w", encoding="utf-8") as f:
        for e in eventos:
            f.write(f"assunto: {e.get('assunto','')}\n")
            f.write(f"prazo: {e.get('prazo','')}\n")
            f.write(f"prioridade: {e.get('prioridade','')}\n\n")

    print("Resposta salva.")
    pyautogui.hotkey('ctrl','w')


abrir_ia()
texto = carregar_textos()
enviar_prompt()
copiar_resposta()