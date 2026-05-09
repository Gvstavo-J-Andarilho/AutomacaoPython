import os
import json
import re

from leitor import PASTA_RAW, palavras_chave, bloqueios, extrair_datas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def processarArquivosRaw():
    eventos_p_ia = []

    arquivos = [f for f in os.listdir(PASTA_RAW) if f.endswith('.txt')]

    for arquivo in arquivos:
        caminho_completo = os.path.join(PASTA_RAW, arquivo)

        with open(caminho_completo, "r", encoding="utf-8") as f:
            conteudo = f.read()

        #1. retirar palavras ou frases de bloqueio
        texto_limpo = conteudo
        for bloqueio in bloqueios:
            texto_limpo = texto_limpo.replace(bloqueio, "")
        
        #2. palavras chave mantidas
        tem_alguma = False
        for palavra in palavras_chave:
            if palavra in texto_limpo.lower():
                tem_alguma = True
                break
        if tem_alguma:
            datas_detectadas = extrair_datas(texto_limpo)

            dados_estruturados = {
                "origem": arquivo,
                "texto_para_ia": texto_limpo[:2000].strip(),
                "datas_python": datas_detectadas
            }
            eventos_p_ia.append(dados_estruturados)

    return eventos_p_ia


def gerar_txt_pra_ia(eventos):
    CAMINHO_TXT = os.path.join(BASE_DIR, "entrada_ia.txt")

    with open(CAMINHO_TXT, "w", encoding="utf-8") as f:

        for i, evento in enumerate(eventos):
            f.write(f"\n\n===== EMAIL {i+1} =====\n\n")
            f.write(evento["texto_para_ia"])


#salvar no JSON unico pra um programa pequeno é interessante, pra IA ler tudo de uma vez só
if __name__ == "__main__":
    resultados =  processarArquivosRaw()

    gerar_txt_pra_ia(resultados)

    print(f"Processamento concluído.\n{len(resultados)} e-mails qualificados para IA")