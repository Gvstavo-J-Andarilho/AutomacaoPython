import pyautogui
import pyperclip
import time
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

URL_PORTAL = "https://sigaa.ufma.br/sigaa/portais/discente/discente.jsf"

DISCIPLINAS = [
    ("ENGENHARIA DE SOFTWARE",          (265, 499)),
    ("ESTATÍSTICA E PROBABILIDADE",     (265, 522)),
    ("ESTRUTURA DE DADOS I (CP)",       (265, 542)),
    ("MATEMÁTICA DISCRETA E LÓGICA",    (265, 567)),
    ("SOCIOLOGIA (CCET)",               (265, 595)),
]

ARQUIVO_SAIDA = os.path.join(BASE_DIR, f"sigaa_{datetime.now().strftime('%d-%m-%Y')}.txt")

# ==============================================

def intervalo(t=1):
    time.sleep(t)

def abrir_sigaa():
    pyautogui.press("win")
    intervalo(0.5)
    pyautogui.write("chrome", interval=0.05)
    pyautogui.press("enter")
    intervalo(1.5)
    pyautogui.hotkey("ctrl", "l")
    intervalo(0.3)
    pyautogui.write(URL_PORTAL, interval=0.04)
    pyautogui.press("enter")
    print("Faça login se necessário. Aguardando 30s...")
    intervalo(8)

def copiar_pagina():
    intervalo(2)
    pyautogui.hotkey("ctrl", "a")
    intervalo(1)
    pyautogui.hotkey("ctrl", "c")
    intervalo(1)
    return pyperclip.paste()

# ==============================================

if __name__ == "__main__":
    abrir_sigaa()

    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:

        for nome, (x, y) in DISCIPLINAS:
            print(f"Coletando: {nome}")

            pyautogui.click(x, y)
            intervalo(4)

            texto = copiar_pagina()

            f.write(f"\n\n{'='*60}\n")
            f.write(f"{nome}\n")
            f.write(f"{'='*60}\n\n")
            f.write(texto)

            pyautogui.hotkey("alt", "left")
            intervalo(3)

    pyautogui.hotkey("ctrl", "w")
    print(f"\nConcluído. Salvo em: {ARQUIVO_SAIDA}")