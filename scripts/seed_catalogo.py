# Semeia o catálogo do usuário com os 14 produtos AV do handoff de design
# (prototipo/radar/data.js). Idempotente: pula códigos já existentes.
# Os custos vieram do handoff — revise antes de confiar na conta.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import db

PRODUTOS = [
    ("MIC-USB-01", "Microfone de mesa USB omnidirecional", "Áudio › Microfones", 820.00, "8518.10.00", "UN", "2 — Importada", "102", "060"),
    ("MSF-UHF-2", "Microfone sem fio duplo UHF", "Áudio › Microfones", 690.00, "8518.10.00", "UN", "2 — Importada", "102", "060"),
    ("IFA-88-USB", "Interface de áudio 8 in / 8 out USB", "Áudio › Interfaces", 240.00, "8543.70.99", "UN", "2 — Importada", "102", "060"),
    ("MSA-12-DIG", "Mesa de som digital 12 canais", "Áudio › Mesas", 1580.00, "8518.40.00", "UN", "2 — Importada", "102", "060"),
    ("CXA-200-12", "Caixa de som ativa 200 W RMS", "Áudio › PA", 940.00, "8518.21.00", "UN", "0 — Nacional", "102", "000"),
    ("CB-SPK-10M", "Cabo speakon macho-macho 10 m", "Áudio › Cabos", 190.00, "8544.42.00", "UN", "0 — Nacional", "102", "000"),
    ("PED-GIR-58", "Pedestal girafa para microfone", "Áudio › Acessórios", 86.00, "8518.90.90", "UN", "0 — Nacional", "102", "000"),
    ("CAM-FHD-04", "Câmera de vídeo Full HD USB/BT", "Vídeo › Captura", 410.00, None, "UN", "2 — Importada", "102", "060"),
    ("SPL-HDMI-18", "Distribuidor HDMI 1 entrada × 8 saídas", "Vídeo › Distribuição", 250.00, "8543.70.99", "UN", "2 — Importada", "102", "060"),
    ("PRJ-4000-W", "Projetor multimídia 4.000 lumens", "Vídeo › Projeção", 2560.00, "8528.62.00", "UN", "2 — Importada", "102", "060"),
    ("TEL-RET-100", 'Tela de projeção retrátil 100"', "Vídeo › Projeção", 585.00, "9010.60.00", "UN", "0 — Nacional", "102", "000"),
    ("MON-27-4K", 'Monitor profissional 27" 4K', "Vídeo › Monitores", 1990.00, "8528.52.20", "UN", "2 — Importada", "102", "060"),
    ("SWV-4-HD", "Switcher de vídeo 4 entradas HDMI", "Vídeo › Produção", 3300.00, "8543.70.99", "UN", "2 — Importada", "102", "060"),
    ("CBH-21-5M", "Cabo HDMI 2.1 certificado 5 m", "Vídeo › Cabos", 122.00, "8544.42.00", "UN", "0 — Nacional", "102", "000"),
]

con = db.abrir()
inseridos = 0
for cod, nome, cat, custo, ncm, un, origem, csosn, cst in PRODUTOS:
    existe = con.execute(
        "SELECT 1 FROM catalogo_produtos WHERE codigo=?", (cod,)
    ).fetchone()
    if existe:
        continue
    con.execute(
        """INSERT INTO catalogo_produtos
             (codigo, nome, categoria, custo_unit, ncm, unidade, origem, csosn, cst)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (cod, nome, cat, custo, ncm, un, origem, csosn, cst),
    )
    inseridos += 1
con.commit()
total = con.execute("SELECT COUNT(*) FROM catalogo_produtos").fetchone()[0]
print(f"{inseridos} inseridos; catálogo com {total} produtos")
