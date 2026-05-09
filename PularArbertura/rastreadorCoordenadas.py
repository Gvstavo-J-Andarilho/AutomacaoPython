from pynput import mouse
import time

# Lista (array) para armazenar as coordenadas
coordenadas = []

print("O programa está monitorando os cliques...")
print("Pressione 'Esc' ou interrompa o terminal para parar.")

def ao_clicar(x, y, botao, pressionado):
    if pressionado:
        # Adiciona a tupla (x, y) ao array
        coordenadas.append((x, y))
        print(f"Clique detectado em: X={x}, Y={y} | Total: {len(coordenadas)}")

time.sleep(5)
# Configura o 'Ouvinte' do mouse
with mouse.Listener(on_click=ao_clicar) as listener:
    try:
        listener.join()
    except KeyboardInterrupt:
        print("\n\nMonitoramento encerrado.")

# Exibe o resultado final
print("--- Coordenadas Coletadas ---")
print(coordenadas)