"""Teste educacional: extrai clientes fictícios da DIO e envia um lote ao n8n.

Uso no PowerShell (dentro da pasta do projeto):
  python -m pip install -r requirements.txt
  $env:N8N_WEBHOOK_URL = 'https://projeto-dio.app.n8n.cloud/webhook-test/clientes-investimentos-v2'
  python rpa/extrair_e_testar.py --limite 2

Acione "Listen for test event" / "Execute workflow" no n8n antes da chamada.
Não envia e-mails nem realiza operações financeiras.
"""
import argparse
import json
import os
from pathlib import Path
import sys

import requests
from bs4 import BeautifulSoup

PAGINA_CLIENTES = "https://digitalinnovationone.github.io/dio-lab-assistente-investimentos-rpa-n8n/"


def extrair_clientes(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    linhas = soup.select("#clientes tbody tr")
    clientes = []
    for num, linha in enumerate(linhas, start=1):
        colunas = linha.find_all("td")
        if len(colunas) < 4:
            raise ValueError(f"Linha {num}: esperado nome, email, saldo e perfil")
        nome, email, saldo, perfil = (td.get_text(strip=True) for td in colunas[:4])
        clientes.append({"nome": nome, "email": email, "saldo": saldo, "perfil": perfil})
    if not clientes:
        raise ValueError("A pagina da DIO nao contem registros na tabela #clientes")
    return clientes


def main() -> int:
    p = argparse.ArgumentParser(description="Testa o pipeline Python -> n8n -> Gemini com clientes ficticios")
    p.add_argument("--limite", type=int, default=2, help="Quantidade de clientes na chamada (1 a 10; padrao: 2)")
    p.add_argument("--somente-extrair", action="store_true", help="Extrai e lista os clientes, sem enviar ao n8n")
    p.add_argument("--saida", help="Caminho do JSON de evidencia (padrao: evidencias/resultado-python-N-clientes.json)")
    args = p.parse_args()
    if not 1 <= args.limite <= 10:
        p.error("--limite deve estar entre 1 e 10")

    try:
        resposta = requests.get(PAGINA_CLIENTES, timeout=25)
        resposta.raise_for_status()
        todos = extrair_clientes(resposta.text)
        clientes = todos[:args.limite]
        print(f"Clientes ficticios encontrados na pagina da DIO: {len(todos)}")
        print(f"Clientes selecionados para este teste: {len(clientes)}")
        for c in clientes:
            print(f"  - {c['nome']} ({c['perfil']}; {c['saldo']})")

        if args.somente_extrair:
            print("Modo somente extrair: nenhuma chamada ao n8n foi feita.")
            return 0

        webhook = os.environ.get("N8N_WEBHOOK_URL", "").strip()
        if not webhook:
            raise ValueError("Defina N8N_WEBHOOK_URL no PowerShell antes de executar.")
        if not webhook.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            raise ValueError("O n8n Cloud exige uma URL HTTPS. Use a Test URL do proprio Webhook.")

        print("Enviando JSON ao n8n...")
        retorno = requests.post(webhook, json={"clientes": clientes}, timeout=115)
        print("HTTP n8n:", retorno.status_code)
        if retorno.status_code == 404:
            raise RuntimeError("Webhook de teste nao registrado. Clique Execute/Listen for test event e execute outra vez.")
        if retorno.status_code == 524:
            raise RuntimeError("Timeout 524. Confira a execucao no n8n; reduza --limite ou investigue demora do Gemini.")
        retorno.raise_for_status()
        try:
            dados = retorno.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise ValueError("O n8n respondeu, mas nao retornou JSON valido.") from exc

        saidas = dados if isinstance(dados, list) else [dados]
        print(f"Resultados recebidos: {len(saidas)}")
        for item in saidas:
            if not isinstance(item, dict):
                print("AVISO: elemento retornado nao e objeto JSON")
                continue
            print(f"  {item.get('nome', '(sem nome)')}: {item.get('modo_mensagem', '(sem modo)')}; "
                  f"{item.get('quantidade_opcoes', '?')} opcoes")
            if item.get("modo_mensagem") == "fallback_estatico":
                print("  AVISO: Gemini nao gerou o texto deste cliente; houve fallback.")

        caminho = Path(args.saida or f"evidencias/resultado-python-{len(clientes)}-clientes.json")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Evidencia salva em: {caminho.resolve()}")
        if len(saidas) != len(clientes):
            print(f"AVISO: enviados {len(clientes)} clientes; recebidos {len(saidas)} resultados. Confira o workflow.")
        return 0
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
