import os
import re
from dateparser.search import search_dates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ARQUIVO_SIGAA = os.path.join(BASE_DIR, "sigaa_22-03-2026.txt")  # troque pela data atual
ARQUIVO_SAIDA = os.path.join(BASE_DIR, "entrada_ia.txt")

palavras_chave = [
    "atividade", "avaliação", "prova", "questionário", "tarefa",
    "entrega", "prazo", "deadline", "até", "quiz", "trabalho",
    "seminário", "apresentação", "teste", "inscrição",
]

bloqueios = [
    "Pular para o conteúdo",
    "SIGAA - Sistema Integrado de Gestão de Atividades Acadêmicas",
    "Última atividade da conta",
    "Termos · Privacidade",
    "pf-button",
    "Turma Virtual!",
    "Ampliando os horizontes da Sala de Aula!",
    "Menu Turma Virtual",
]


def limpar_texto(texto):
    for b in bloqueios:
        texto = texto.replace(b, "")
    return texto


def contem_palavra_chave(texto):
    texto_lower = texto.lower()
    for p in palavras_chave:
        if p in texto_lower:
            return True
    return False


def dividir_por_disciplina(texto):
    """
    Divide o arquivo monolítico nos blocos de cada disciplina
    usando os separadores ===== como delimitadores.
    Retorna lista de (nome_disciplina, conteudo).
    """
    partes = re.split(r"={10,}", texto)  # divide em ====...====

    disciplinas = []
    i = 0
    while i < len(partes):
        nome = partes[i].strip()
        conteudo = partes[i + 1].strip() if i + 1 < len(partes) else ""
        if nome:
            disciplinas.append((nome, conteudo))
        i += 2

    return disciplinas


def processar_sigaa():
    with open(ARQUIVO_SIGAA, "r", encoding="utf-8") as f:
        texto_completo = f.read()

    disciplinas = dividir_por_disciplina(texto_completo)

    qualificados = []

    for nome, conteudo in disciplinas:
        conteudo = limpar_texto(conteudo)

        if contem_palavra_chave(conteudo):
            qualificados.append((nome, conteudo[:2000].strip()))
            print(f"  ✓ {nome}")
        else:
            print(f"  - {nome}: nada relevante")

    return qualificados


def gerar_entrada_ia(qualificados):
    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
        for i, (nome, conteudo) in enumerate(qualificados):
            f.write(f"\n\n===== SIGAA {i+1} — {nome} =====\n\n")
            f.write(conteudo)

    print(f"\nGerado: {ARQUIVO_SAIDA} ({len(qualificados)} disciplina(s))")


if __name__ == "__main__":
    print("Processando arquivo do SIGAA...\n")
    qualificados = processar_sigaa()
    gerar_entrada_ia(qualificados)
    print("\nPronto. Agora rode o enviarIA.py.")
