// RADAR DE PREGÕES — dados mock v2, espelhando o modelo real (CLAUDE.md):
// buscas_salvas, pregoes (PNCP), itens com match sugerido/confirmado,
// catalogo com dados fiscais, habilitacao com citação verificada, config.
window.RADAR_DATA = {
  config: { regime_tributario: "simples", uf_origem: "SP" },

  buscas: [
    {
      id: 1, nome: "Áudio & vídeo — SP",
      termos: "áudio, vídeo, microfone, caixa de som",
      ufs: "SP", status: "recebendo_proposta", ativo: true,
      ultimaExec: "11/06/2026 06:00", novos: 1
    },
    {
      id: 2, nome: "Projeção e sonorização",
      termos: "projetor, tela de projeção, sonorização",
      ufs: "SP, GO", status: "recebendo_proposta", ativo: true,
      ultimaExec: "11/06/2026 06:00", novos: 1
    }
  ],

  catalogo: [
    { cod: "MIC-USB-01", nome: "Microfone de mesa USB omnidirecional", cat: "Áudio › Microfones", custo: 820.00, ncm: "8518.10.00", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "MSF-UHF-2", nome: "Microfone sem fio duplo UHF", cat: "Áudio › Microfones", custo: 690.00, ncm: "8518.10.00", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "IFA-88-USB", nome: "Interface de áudio 8 in / 8 out USB", cat: "Áudio › Interfaces", custo: 240.00, ncm: "8543.70.99", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "MSA-12-DIG", nome: "Mesa de som digital 12 canais", cat: "Áudio › Mesas", custo: 1580.00, ncm: "8518.40.00", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "CXA-200-12", nome: "Caixa de som ativa 200 W RMS", cat: "Áudio › PA", custo: 940.00, ncm: "8518.21.00", unidade: "UN", origem: "0 — Nacional", csosn: "102", cst: "000" },
    { cod: "CB-SPK-10M", nome: "Cabo speakon macho-macho 10 m", cat: "Áudio › Cabos", custo: 190.00, ncm: "8544.42.00", unidade: "UN", origem: "0 — Nacional", csosn: "102", cst: "000" },
    { cod: "PED-GIR-58", nome: "Pedestal girafa para microfone", cat: "Áudio › Acessórios", custo: 86.00, ncm: "8518.90.90", unidade: "UN", origem: "0 — Nacional", csosn: "102", cst: "000" },
    { cod: "CAM-FHD-04", nome: "Câmera de vídeo Full HD USB/BT", cat: "Vídeo › Captura", custo: 410.00, ncm: null, unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "SPL-HDMI-18", nome: "Distribuidor HDMI 1 entrada × 8 saídas", cat: "Vídeo › Distribuição", custo: 250.00, ncm: "8543.70.99", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "PRJ-4000-W", nome: "Projetor multimídia 4.000 lumens", cat: "Vídeo › Projeção", custo: 2560.00, ncm: "8528.62.00", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "TEL-RET-100", nome: "Tela de projeção retrátil 100\"", cat: "Vídeo › Projeção", custo: 585.00, ncm: "9010.60.00", unidade: "UN", origem: "0 — Nacional", csosn: "102", cst: "000" },
    { cod: "MON-27-4K", nome: "Monitor profissional 27\" 4K", cat: "Vídeo › Monitores", custo: 1990.00, ncm: "8528.52.20", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "SWV-4-HD", nome: "Switcher de vídeo 4 entradas HDMI", cat: "Vídeo › Produção", custo: 3300.00, ncm: "8543.70.99", unidade: "UN", origem: "2 — Importada", csosn: "102", cst: "060" },
    { cod: "CBH-21-5M", nome: "Cabo HDMI 2.1 certificado 5 m", cat: "Vídeo › Cabos", custo: 122.00, ncm: "8544.42.00", unidade: "UN", origem: "0 — Nacional", csosn: "102", cst: "000" }
  ],

  pregoes: [
    {
      id: "cd-125-2026",
      cnpj: "00394502000144", ano: 2026, seq: 125,
      numeroControle: "00394502000144-1-000125/2026",
      titulo: "Aviso de Contratação Direta nº 125/2026",
      orgao: "Comando da Marinha — Centro de Intendência Tecnológica da Marinha (CITMAR-SP)",
      unidadeCompradora: "742050 — Centro de Intendência Tecnológica da Marinha SP",
      municipio: "São Paulo", uf: "SP",
      modalidade: "Dispensa",
      amparo: "Lei 14.133/2021, Art. 75, II",
      beneficio: "Participação exclusiva ME/EPP",
      meEpp: true,
      valorTotal: 17306.96,
      prazo: "15/06/2026 08:00",
      inicioPropostas: "10/06/2026 09:30",
      divulgacao: "10/06/2026 09:25",
      situacao: "Divulgada no PNCP",
      descricao:
        "Aquisição de materiais para videoconferência e infraestrutura — os equipamentos e acessórios permitirão a instalação adequada dos recursos visuais, assegurando condições para videoconferências, apresentações e demais reuniões de trabalho.",
      status: "Recebendo propostas",
      salvo: true, novo: true, buscaId: 1, sincronizado: true,
      arquivos: [
        { titulo: "Aviso_Contratacao_Direta_125_2026.pdf", tipo: "Edital", paginas: 14 },
        { titulo: "Termo_de_Referencia_125_2026.pdf", tipo: "Termo de Referência", paginas: 22 }
      ],
      itens: [
        {
          n: 7,
          nome: "Fechadura digital",
          spec: "Fechadura Digital — material: aço, acabamento: aço escovado, largura: 65, comprimento: 200, altura: 70, alimentação: pilhas AA, tipo abertura: senha numérica, cadastro: 3 códigos (senhas) de 3 até 8 dígitos, características adicionais: visualização noturna, sistema de operações suspeitas (bloqueia por 3 minutos após a quinta tentativa).",
          qtd: 1, unidade: "Unidade", unit: 488.06, ncmPncp: null, match: null
        },
        {
          n: 8,
          nome: "Cabo speakon 10 m",
          spec: "Cabo Áudio e Vídeo — material condutor: cobre, aplicação: áudio e vídeo, comprimento: 10, conectores: speakon macho - speakon macho.",
          qtd: 6, unidade: "Unidade", unit: 223.00, ncmPncp: null,
          match: { cod: "CB-SPK-10M", score: 0.94, confirmado: true }
        },
        {
          n: 9,
          nome: "Canaleta PVC com tampa",
          spec: "Canaleta — material: PVC (cloreto de polivinila), tipo: com tampa, características adicionais: para piso, suporta alto impacto, dimensões: 55 x 20 x 2000.",
          qtd: 20, unidade: "Unidade", unit: 165.00, ncmPncp: null, match: null
        },
        {
          n: 10,
          nome: "Interface de áudio 8×8",
          spec: "Módulo Eletrônico — tipo: interface de áudio, modelo: analógica, aplicação: gestão do áudio de entrada e de saída, características adicionais: pré-amplificadores, USB, phantom power, saída fone, quantidade saída de áudio: 8, quantidade de entrada de áudio: 8.",
          qtd: 2, unidade: "Unidade", unit: 370.73, ncmPncp: null,
          match: { cod: "IFA-88-USB", score: 0.89, confirmado: true }
        },
        {
          n: 11,
          nome: "Distribuidor de sinal HDMI 1→8",
          spec: "Distribuidor Sinal — tensão alimentação: 110/220, conector entrada: 1 HDMI, conector saída: 8 HDMI, resolução: 1080p 60 fps, características adicionais: suporte ao padrão HDCP, aplicação: distribuição de sinal, categoria: splitter HDMI 3.0 — 1 x 8 HDMI 3.0.",
          qtd: 4, unidade: "Unidade", unit: 333.63, ncmPncp: null,
          match: { cod: "SPL-HDMI-18", score: 0.92, confirmado: true }
        },
        {
          n: 12,
          nome: "Microfone de mesa USB",
          spec: "Microfone — tipo: de mesa, resposta frequência: 60 Hz – 17, características adicionais: conector USB, plug and play, aplicação: videoconferência, padrão: omnidirecional, acessórios: cabo de no mínimo 1,5 m.",
          qtd: 4, unidade: "Unidade", unit: 1241.51, ncmPncp: "8518.10.00",
          match: { cod: "MIC-USB-01", score: 0.91, confirmado: false }
        },
        {
          n: 13,
          nome: "Câmera de vídeo Full HD",
          spec: "Câmara de Vídeo — resolução: 1920 x 1080, interface: USB, Bluetooth, NFC, formato: H.264 com SVC e UVC 1.5, tipo zoom: digital 4x, características adicionais: microfones omnidirecionais integrados, tensão alimentação: 110/220.",
          qtd: 4, unidade: "Unidade", unit: 487.50, ncmPncp: null,
          match: { cod: "CAM-FHD-04", score: 0.86, confirmado: false }
        }
      ],
      habilitacao: [
        { id: 1, requisito: "Proposta com validade mínima de 60 dias", categoria: "proposta", obrigatorio: true, pagina: 2, excerto: "A proposta deverá ter validade mínima de 60 (sessenta) dias, contados da data de sua apresentação.", verificada: true, status: "ok" },
        { id: 2, requisito: "Ato constitutivo / contrato social em vigor", categoria: "juridica", obrigatorio: true, pagina: 3, excerto: "Ato constitutivo, estatuto ou contrato social em vigor, devidamente registrado, em se tratando de sociedades empresárias.", verificada: true, status: "ok" },
        { id: 3, requisito: "Declaração de enquadramento ME/EPP", categoria: "juridica", obrigatorio: true, pagina: 3, excerto: "Declaração de que cumpre os requisitos legais para a qualificação como microempresa ou empresa de pequeno porte, nos termos da Lei Complementar nº 123/2006.", verificada: true, status: "ok" },
        { id: 4, requisito: "Certidão negativa de débitos federais (RFB/PGFN)", categoria: "fiscal", obrigatorio: true, pagina: 4, excerto: "Prova de regularidade fiscal perante a Fazenda Nacional, mediante certidão conjunta negativa de débitos relativos a tributos federais e à dívida ativa da União.", verificada: true, status: "ok" },
        { id: 5, requisito: "Certificado de regularidade do FGTS (CRF)", categoria: "fiscal", obrigatorio: true, pagina: 4, excerto: "Prova de regularidade relativa ao Fundo de Garantia do Tempo de Serviço (FGTS), mediante apresentação do Certificado de Regularidade do FGTS — CRF.", verificada: true, status: "pendente" },
        { id: 6, requisito: "Certidão negativa de débitos trabalhistas (CNDT)", categoria: "fiscal", obrigatorio: true, pagina: 4, excerto: "Prova de inexistência de débitos inadimplidos perante a Justiça do Trabalho, mediante Certidão Negativa de Débitos Trabalhistas — CNDT.", verificada: true, status: "pendente" },
        { id: 7, requisito: "Declaração de que não emprega menor", categoria: "juridica", obrigatorio: true, pagina: 5, excerto: "Declaração de que não emprega menor de 18 anos em trabalho noturno, perigoso ou insalubre, e menor de 16 anos em qualquer trabalho, salvo na condição de aprendiz.", verificada: true, status: "nao_tenho" },
        { id: 8, requisito: "Atestado de capacidade técnica", categoria: "tecnica", obrigatorio: false, pagina: 6, excerto: "Comprovação de aptidão para o fornecimento de bens em características compatíveis com o objeto desta contratação.", verificada: false, status: "pendente" }
      ]
    },
    {
      id: "pe-90014-2026",
      cnpj: "51885242000140", ano: 2026, seq: 90014,
      numeroControle: "51885242000140-1-090014/2026",
      titulo: "Pregão Eletrônico nº 90014/2026",
      orgao: "Prefeitura Municipal de Campinas — Secretaria de Educação",
      municipio: "Campinas", uf: "SP",
      modalidade: "Pregão Eletrônico",
      amparo: "Lei 14.133/2021, Art. 28, I",
      beneficio: "Cota reservada ME/EPP",
      meEpp: true,
      valorTotal: 86430.00,
      prazo: "22/06/2026 09:00",
      situacao: "Divulgada no PNCP",
      descricao:
        "Registro de preços para aquisição de equipamentos de áudio e vídeo (projeção e sonorização) para as unidades escolares da rede municipal.",
      status: "Recebendo propostas",
      salvo: true, novo: false, buscaId: 2, sincronizado: false,
      arquivos: [{ titulo: "Edital_PE_90014_2026.pdf", tipo: "Edital", paginas: 48 }],
      habilitacao: null,
      itens: [
        {
          n: 1, nome: "Projetor multimídia 4.000 lm",
          spec: "Projetor multimídia — luminosidade mínima: 4.000 lumens, resolução nativa: WXGA, entradas: HDMI e VGA, lâmpada com vida útil mínima de 6.000 h.",
          qtd: 20, unidade: "Unidade", unit: 2890.00, ncmPncp: null,
          match: { cod: "PRJ-4000-W", score: 0.93, confirmado: true }
        },
        {
          n: 2, nome: "Tela de projeção retrátil 100\"",
          spec: "Tela de projeção — tipo: retrátil, 100 polegadas, formato: 4:3, acionamento: manual, estrutura para fixação em teto ou parede.",
          qtd: 20, unidade: "Unidade", unit: 690.00, ncmPncp: null,
          match: { cod: "TEL-RET-100", score: 0.95, confirmado: true }
        },
        {
          n: 3, nome: "Caixa de som ativa 200 W",
          spec: "Caixa de som — tipo: ativa, potência RMS: 200 W, alto-falante: 12 polegadas, entradas balanceadas XLR e P10, alça e suporte para tripé.",
          qtd: 8, unidade: "Unidade", unit: 1150.00, ncmPncp: null,
          match: { cod: "CXA-200-12", score: 0.91, confirmado: true }
        },
        {
          n: 4, nome: "Suporte de teto para projetor",
          spec: "Suporte de teto — para projetor, articulado, capacidade mínima: 10 kg, ajuste de inclinação e rotação.",
          qtd: 20, unidade: "Unidade", unit: 145.00, ncmPncp: null, match: null
        }
      ]
    },
    {
      id: "pe-90211-2026",
      cnpj: "59949362000176", ano: 2026, seq: 90211,
      numeroControle: "59949362000176-1-090211/2026",
      titulo: "Pregão Eletrônico nº 90211/2026",
      orgao: "Tribunal Regional Federal da 3ª Região",
      municipio: "São Paulo", uf: "SP",
      modalidade: "Pregão Eletrônico",
      amparo: "Lei 14.133/2021, Art. 28, I",
      beneficio: null,
      meEpp: false,
      valorTotal: 41880.00,
      prazo: "18/06/2026 14:00",
      situacao: "Divulgada no PNCP",
      descricao:
        "Aquisição de equipamentos de vídeo profissional para modernização das salas de sessão e transmissão de julgamentos.",
      status: "Recebendo propostas",
      salvo: false, novo: false, buscaId: 1, sincronizado: false,
      arquivos: [{ titulo: "Edital_PE_90211_2026.pdf", tipo: "Edital", paginas: 63 }],
      habilitacao: null,
      itens: [
        {
          n: 1, nome: "Monitor de vídeo 27\" 4K",
          spec: "Monitor de vídeo — profissional, 27 polegadas, resolução: 3840 x 2160, painel: IPS, entradas: HDMI e DisplayPort, ajuste de altura.",
          qtd: 12, unidade: "Unidade", unit: null, sigiloso: true, ncmPncp: null,
          match: { cod: "MON-27-4K", score: 0.90, confirmado: true }
        },
        {
          n: 2, nome: "Switcher de vídeo 4 entradas",
          spec: "Switcher de vídeo — 4 entradas HDMI, saída de programa e preview, transições por corte e dissolve, controle USB.",
          qtd: 2, unidade: "Unidade", unit: 3450.00, ncmPncp: null,
          match: { cod: "SWV-4-HD", score: 0.88, confirmado: true }
        },
        {
          n: 3, nome: "Cabo HDMI 2.1 certificado 5 m",
          spec: "Cabo HDMI — 2.1 certificado Ultra High Speed, 5 metros, suporte a 4K120 / 8K60, conectores banhados a ouro.",
          qtd: 40, unidade: "Unidade", unit: 128.00, ncmPncp: null,
          match: { cod: "CBH-21-5M", score: 0.96, confirmado: true }
        }
      ]
    },
    {
      id: "de-88-2026",
      cnpj: "10870883000144", ano: 2026, seq: 88,
      numeroControle: "10870883000144-1-000088/2026",
      titulo: "Dispensa Eletrônica nº 88/2026",
      orgao: "Instituto Federal de Goiás (IFG) — Campus Goiânia",
      municipio: "Goiânia", uf: "GO",
      modalidade: "Dispensa",
      amparo: "Lei 14.133/2021, Art. 75, II",
      beneficio: "Participação exclusiva ME/EPP",
      meEpp: true,
      valorTotal: 9144.00,
      prazo: "17/06/2026 10:00",
      situacao: "Divulgada no PNCP",
      descricao:
        "Aquisição de equipamentos de áudio para o auditório e eventos institucionais do campus.",
      status: "Recebendo propostas",
      salvo: false, novo: true, buscaId: 2, sincronizado: false,
      arquivos: [{ titulo: "Aviso_Dispensa_88_2026.pdf", tipo: "Edital", paginas: 11 }],
      habilitacao: null,
      itens: [
        {
          n: 1, nome: "Mesa de som digital 12 canais",
          spec: "Mesa de som — digital, 12 canais, pré-amplificadores com phantom +48 V, efeitos internos, conexão USB para gravação.",
          qtd: 2, unidade: "Unidade", unit: 2350.00, ncmPncp: null,
          match: { cod: "MSA-12-DIG", score: 0.92, confirmado: true }
        },
        {
          n: 2, nome: "Microfone sem fio duplo UHF",
          spec: "Sistema de microfone sem fio — duplo, faixa UHF, 2 bastões, receptor com saídas XLR e P10, alcance mínimo de 50 m.",
          qtd: 4, unidade: "Unidade", unit: 980.00, ncmPncp: null,
          match: { cod: "MSF-UHF-2", score: 0.89, confirmado: true }
        },
        {
          n: 3, nome: "Pedestal girafa para microfone",
          spec: "Pedestal — tipo girafa para microfone, altura ajustável, base tripé dobrável, rosca padrão 5/8\".",
          qtd: 4, unidade: "Unidade", unit: 128.00, ncmPncp: null,
          match: { cod: "PED-GIR-58", score: 0.87, confirmado: true }
        }
      ]
    }
  ]
};

// índice do catálogo por código
window.RADAR_DATA.catalogoPorCod = Object.fromEntries(
  window.RADAR_DATA.catalogo.map((p) => [p.cod, p])
);
