import pyautogui
import pyperclip
import time
from dateparser.search import search_dates
import os
from datetime import datetime

# ================= CONFIG =================

BASE_DIR = os.path.dirname(__file__)

IMAGEM_EMAIL = os.path.join(BASE_DIR, "guiaGmail.png")
IMAGEM_VOLTAR = os.path.join(BASE_DIR, "voltarGmail.png")
TOLERANCIAy = 30
SCROLL_POR_LOOP = -100
MAX_EMAILS = 7

#================== Dados de salvar ==========
DATA_ATUAL = datetime.now().strftime("%d-%m-%Y")
PASTA_RAW = os.path.join(BASE_DIR, f"RawGmail{DATA_ATUAL}")

if not os.path.exists(PASTA_RAW):
    os.makedirs(PASTA_RAW)
    print("pasta criada com sucesso!")
else:
    print(f"Usando existente: {PASTA_RAW}")


palavras_chave = [
    "prazo",
    "entrega",
    "inscrição",
    "data",
    "até",
    "deadline",
    "atividade",
    "edital",
    "candidat",
    "avalia",
    "vaga",
    "final",
    "próxim",
]

bloqueios = [
    "Pular para o conteúdo",
    "Como usar o Gmail com leitores de tela",
    "Termos · Privacidade",
    "Regulamentos do programa",
    "Última atividade da conta"
]

emails_texto = []

pyautogui.FAILSAFE = True

print("Abrindo o Gmail")
time.sleep(2)

# ================= FUNÇÕES =================

def abrirGmail():
    print("Iniciando captura automática...")

    pyautogui.press('win')
    time.sleep(0.5)
    pyautogui.write('chrome', interval=0.1)
    pyautogui.press('enter')
    time.sleep(1)

    pyautogui.hotkey('ctrl', 'l')
    time.sleep(0.1)
    pyautogui.write('https://mail.google.com/mail/u/0/#inbox', interval = 0.1)
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(5)


def salvarGmailRaw(texto, contador):
    # Nome do arquivo (pode mudar se quiser)
    timestamp = datetime.now().strftime("%d%m%Y")  # evita sobrescrever se rodar várias vezes
    nome_arquivo = f"email_{contador+1}_{timestamp}.txt"
    
    # Caminho COMPLETO dentro da pasta do dia
    caminho_completo = os.path.join(PASTA_RAW, nome_arquivo)
    
    # Salva de verdade no lugar certo
    with open(caminho_completo, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)



def limpar_texto(texto):
    for b in bloqueios:
        texto = texto.replace(b, "")
    return texto


def contem_palavra_chave(texto):
    texto = texto.lower()
    for p in palavras_chave:
        if p in texto:
            return True
    return False


def extrair_datas(texto):
    datas = []

    resultados = search_dates(texto, languages=['pt'])

    if resultados:
        for trecho, data in resultados:
            datas.append(data.strftime("%d/%m/%Y"))

    return datas


def copiar_email():
    time.sleep(1.0)  # espera email abrir de verdade
    pyautogui.press('end')  # ou pyautogui.scroll(-3000)
    time.sleep(1.5)
    pyautogui.hotkey('ctrl', 'home')  # volta pro topo
    time.sleep(0.8)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(1.2)
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(2.0)  # mais tempo pro clipboard encher
    texto = pyperclip.paste()

    return texto



def voltar_email():

    try:
        loc = pyautogui.locateCenterOnScreen(IMAGEM_VOLTAR, confidence=0.6)

        if loc:
            pyautogui.hotkey('alt', 'left')
            time.sleep(2)
        else:
            pyautogui.click(loc)
            time.sleep(2)

    except:
        pyautogui.hotkey('alt', 'left')
        time.sleep(2)


# ================= LOOP PRINCIPAL =================

contador = 0
acumulador=contador+2
y_anterior = 0
if __name__ == "__main__":
    while contador < MAX_EMAILS:

        if contador == 0:
            abrirGmail()

        '''time.sleep(0.5)
        for i in range(acumulador):
            time.sleep(0.5)
            pyautogui.press('down')'''

        print(f"\nProcurando emails... ({contador}/{MAX_EMAILS})")

        emails = list(pyautogui.locateAllOnScreen(IMAGEM_EMAIL, confidence=0.7))

        print(f"Emails encontrados na tela: {len(emails)}")

        if not emails:
            print("Nenhum email encontrado.")
            break

        # garante ordem vertical
        emails = sorted(
            emails,
            key=lambda e: pyautogui.center(e).y
        )

        for email in emails:

            if contador >= MAX_EMAILS:
                break

            centro = pyautogui.center(email)

            # evita repetir emails
            if centro.y <= (y_anterior + TOLERANCIAy):
                continue

            y_anterior = centro.y

            OFFSET_X = 120

            print("Abrindo email...")

            pyautogui.click(
                centro.x + OFFSET_X,
                centro.y
            )

            time.sleep(5)

            texto = copiar_email()
            texto = limpar_texto(texto)

            salvarGmailRaw(texto, contador)
            

            print("\nTrecho capturado:")
            print(texto[:300])

            if len(texto) < 50:
                print("Email não abriu corretamente.")
                voltar_email()
                pyautogui.press('down')
                continue

            if contem_palavra_chave(texto):

                datas = extrair_datas(texto)

                if datas:
                    print("\nDatas encontradas:")
                    for d in datas:
                        print(d)

                    emails_texto.append(texto)
                else:
                    print("Nenhuma data encontrada.")

            else:
                print("Nenhuma palavra-chave encontrada.")

            voltar_email()
            pyautogui.press('down')

            contador += 1
            acumulador = contador+1
            if contador == MAX_EMAILS:
                time.sleep(0.1)
                pyautogui.hotkey('ctrl','w')
        # scroll para próximos emails
        time.sleep(2)
        pyautogui.scroll(SCROLL_POR_LOOP)


print("\nProcesso finalizado.")
print(f"{len(emails_texto)} emails úteis encontrados.")