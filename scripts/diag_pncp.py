import httpx

url = "https://pncp.gov.br/api/search/"
params = {"q": "microfone", "tipos_documento": "edital", "ordenacao": "-data",
          "pagina": 1, "tamanhoPagina": 5, "ufs": "SP",
          "status": "recebendo_proposta"}
casos = {
    "UA radar": {"User-Agent": "RadarPregoes/0.1 (uso pessoal)"},
    "UA radar + Accept": {"User-Agent": "RadarPregoes/0.1 (uso pessoal)",
                          "Accept": "application/json"},
    "UA browser": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
}
for nome, headers in casos.items():
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=30)
        print(f"{nome}: {r.status_code} ({len(r.content)} bytes)")
    except Exception as e:
        print(f"{nome}: ERRO {type(e).__name__}: {e}")
