# Araruna-PR: vídeo vertical (9:16)

Globo girando → para no Brasil → zoom no Paraná → zoom em Araruna → "portal" para dentro da cidade (cena ilustrada) → card final com CTA.

- 1080x1920, 30 fps, 37 s, H.264 ~16 Mbps, áudio -14 LUFS (padrão do Guia do Motion)
- Estilo: "escuro narrado / glow" com a paleta da arara-azul (cobalto + amarelo-ouro)

## Gerar

```bash
pip install pycairo shapely numpy
mkdir geo && cd geo
curl -o world.json  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
curl -o states.json https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson
curl -o pr.json     https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-41-mun.json
cd ..
python3 render.py geo video_mudo.mp4
python3 audio.py trilha.wav
ffmpeg -i trilha.wav -af "acompressor=threshold=-22dB:ratio=4:attack=5:release=120,volume=11.3dB,alimiter=limit=0.88:level=false" trilha_norm.wav
ffmpeg -i video_mudo.mp4 -i trilha_norm.wav -map 0:v -map 1:a -c:v libx264 -b:v 16M -minrate 16M -maxrate 20M -bufsize 32M -pix_fmt yuv420p -c:a aac -b:a 256k -shortest -movflags +faststart araruna-pr-vertical.mp4
```

Stills de teste: `ONLY="2,15,24" python3 render.py geo x.mp4` (salva em `stills/`).

## Roteiro

| Tempo | Cena | Texto |
|---|---|---|
| 0–6 s | Globo girando e desacelerando | Tem um lugar no mapa / que merece a viagem |
| 6–9 s | Para no Brasil, destaque | AMÉRICA DO SUL · BRASIL |
| 9.6–13 s | Zoom no Paraná | REGIÃO SUL · PARANÁ |
| 13–18 s | Zoom em Araruna, pin na sede, vizinhos | CENTRO-OCIDENTAL PARANAENSE · ARARUNA · coordenadas |
| 18–19 s | Mergulho no pin, portal dourado | |
| 19–23 s | Arara-azul voando sobre a cidade | Do tupi: ARARUNA quer dizer arara-azul |
| 23–26 s | Igreja Matriz | Igreja Matriz Santo Antônio, festa do padroeiro em junho |
| 26–30 s | Lavouras | Soja, milho e mandioca |
| 30–33 s | Trilha dourada | Caminho de Peabiru |
| 33–37 s | Card final | 14.485 habitantes (Censo 2022) · 29 de novembro · Comenta ARARUNA se você é daqui |

## Fontes
- IBGE Cidades (população Censo 2022): https://www.ibge.gov.br/cidades-e-estados/pr/araruna.html
- IDR-Paraná, plano municipal (soja, milho, mandioca): https://www.idrparana.pr.gov.br/system/files/publico/Transparecia%20Institucional/TermosCooperacaoMunicipios/2022/A/ArarunaPlano.pdf
- Viaje Paraná (Igreja Matriz Santo Antônio, festa em junho, monumento da arara): https://www.viajeparana.com/Araruna
- Histórico IBGE (Caminho de Peabiru): https://biblioteca.ibge.gov.br/visualizacao/dtb/parana/araruna.pdf
- Malhas: Natural Earth, geodata-br (IBGE), click_that_hood
