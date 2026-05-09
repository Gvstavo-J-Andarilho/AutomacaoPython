import pyautogui
import cv2
import numpy as np
import time
import os
import keyboard

# ================= CONFIG =================

BASE_IMAGENS = r"C:\Users\Gustavo Maciel\Python\Automacao\PularArbertura\imagens"
# onde serão feitas as operações de reconhecer os padrões e seleciona-los
STREAMERS = {
    "1": {
        "nome": "Prime Video",
        "imagens": [
            "aberturaPrime.png",
            "pularResumo.png"
        ]
    },
    "2": {
        "nome": "Crunchyroll",
        "imagens": [
            "aberturaCrunchyroll.png",
            "creditosCrunchyroll.png"
        ]
    },
    "3": {
        "nome": "YouTube",
        "imagens": [
            "comercialYoutube.png",
            "comercialYoutube2.png",
            "comercialYoutube3.png",
            "comercialYoutube4.png",
            "comercialYoutube5.png",
        ]
    }
}

THRESHOLD = 0.80
INTERVALO_SCAN = 2.0
DELAY_APOS_CLIQUE = 1.5

# ==========================================
REPETICOES_SETAS = 9 # quantidade de repetições da seta ->


def repetir_seta():
    for _ in range(REPETICOES_SETAS):
        pyautogui.press("right")
        time.sleep(0.05)


def menu():
    print("\nQual streaming você vai assistir?\n")
    for k, v in STREAMERS.items():
        print(f"[{k}] {v['nome']}")
    print("\nCTRL+C para sair")

    return input("\nEscolha: ").strip()


def carregar_templates(streamer):
    templates = []

    for img in streamer["imagens"]:
        caminho = os.path.join(BASE_IMAGENS, img)

        if not os.path.exists(caminho):
            print(f"Imagem não encontrada: {caminho}")
            continue

        template = cv2.imread(caminho)
        if template is None:
            print(f"Erro ao carregar: {img}")
            continue

        h, w = template.shape[:2]

        templates.append({
            "nome": img,
            "template": template,
            "h": h,
            "w": w
        })

    return templates


def loop(streamer):
    print(f"\n🎬 Assistindo: {streamer['nome']}")
    print("Bot ativo. CTRL+C para parar.\n")

    templates = carregar_templates(streamer)

    # Ativa repetição da seta apenas no Crunchyroll
    if streamer["nome"] == "Crunchyroll":
        print("Hotkey → ativada (repetição automática)")
        keyboard.add_hotkey("right", repetir_seta)

    imagem_clicada = None
    
    while True:
        try:
            screenshot = pyautogui.screenshot()
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

            detectou = False
            clicou_nesse_ciclo = False  # 🔒 trava de clique por ciclo

            for temp in templates:
                res = cv2.matchTemplate(
                    frame,
                    temp["template"],
                    cv2.TM_CCOEFF_NORMED
                )

                loc = np.where(res >= THRESHOLD)

                if len(loc[0]) > 0:
                    detectou = True

                    if imagem_clicada != temp["nome"] and not clicou_nesse_ciclo:
                        
                        # --- CORREÇÃO AQUI: Definindo x e y ANTES de usar ---
                        # Obtemos o primeiro ponto onde a imagem foi detectada
                        pt = list(zip(*loc[::-1]))[0]
                        # Calculamos o centro da imagem detectada
                        x = pt[0] + temp["w"] // 2
                        y = pt[1] + temp["h"] // 2

                        # 🔴 CASO ESPECIAL Crunchyroll
                        if (
                            streamer["nome"] == "Crunchyroll"
                            and temp["nome"] == "creditosCrunchyroll.png"
                        ):
                            print(f"▶ Créditos Crunchyroll detectado em ({x}, {y}) → clique fixo")
                            x = 1327
                            y = 735
                            pyautogui.moveTo(x, y, duration=0.5)
                            pyautogui.click()

                        else:
                            print(f"▶ Detectado: {temp['nome']} → clique em ({x}, {y})")
                            pyautogui.moveTo(x, y, duration=0.5)
                            pyautogui.click()

                        imagem_clicada = temp["nome"]
                        clicou_nesse_ciclo = True

                        # 🔥 PARA O LOOP DE TEMPLATES AQUI
                        break

            # Libera clique quando nenhuma imagem estiver visível
            if not detectou:
                imagem_clicada = None

            time.sleep(INTERVALO_SCAN)

        except KeyboardInterrupt:
            print("\n⛔ Bot encerrado.")
            break


def main():
    escolha = menu()

    if escolha not in STREAMERS:
        print("Opção inválida.")
        return

    loop(STREAMERS[escolha])


if __name__ == "__main__":
    main()