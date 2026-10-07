# Lastro

Mesa de portfólio Web3 para uma VPS compartilhada. Três serviços sobem em contêineres separados: a API (FastAPI), o motor de leitura (NumPy e pandas) e a mesa (Next.js). O motor tem teto de CPU e memória para não tomar a máquina das automações que já rodam no host.

Os preços são os que você lança. Não há feed de mercado. A leitura calcula concentração (HHI), ativos efetivos e peso por rede. O conselho Neuro-Quest Capital narra esses números: com `GEMINI_API_KEY` a fala vem do Gemini via LangChain; sem a chave, uma crônica local mantém os três personagens e os mesmos números.

## Premissas de host

Este repositório não mede a sua VPS daqui. O deploy mede.

| Pergunta | O que está assumido | Onde confirmar |
| --- | --- | --- |
| Distribuição | Ubuntu 24.04 LTS. O stack só precisa de Docker Engine e do plugin Compose v2 no host. | `./scripts/vps.sh preflight` imprime `/etc/os-release` |
| RAM e CPU | Envelope padrão: motor **1.0 CPU / 1536 MiB**, API **0.50 CPU / 384 MiB**, mesa **0.50 CPU / 512 MiB**. Soma: **2.0 CPU e 2432 MiB**. | `nproc`, `free -h`, depois edite `.env` |

Esse envelope cabe, com folga, numa máquina de 4 vCPUs e 8 GiB que já tem outros processos. Num host de 2 vCPUs o preflight recusa esses números: use o perfil comentado no fim de `.env.example`.

O deploy para se a soma dos tetos passar de **70% da RAM** ou **80% das vCPUs** lidas na hora. Entre 45% e 70% da RAM (ou acima de metade da CPU) ele avisa e segue.

## Rodar na VPS

```bash
cp .env.example .env
./scripts/vps.sh preflight
./scripts/vps.sh deploy
```

A mesa escuta em `127.0.0.1:4181` e a API em `127.0.0.1:8091`. O motor não publica porta: ele fica numa rede Docker sem saída para a internet, e só a API fala com ele. Aponte o proxy que já existe na VPS para `127.0.0.1:4181`. Não abra essas portas no firewall.

O arquivo de orquestração é `compose.yaml` (o nome atual do Compose v2).

Depois do primeiro deploy, o systemd em `infra/lastro.service` sobe de novo os contêineres no boot. Ajuste `WorkingDirectory` para o diretório do clone antes de instalar a unit.

### Backup e restauração

```bash
./scripts/vps.sh backup
./scripts/vps.sh restore backups/lastro-YYYYMMDDTHHMMSSZ.tar.gz --yes
```

O backup grava o volume `lastro_carteira` (o SQLite da carteira) em `./backups`, com SHA-256, permissão `0600` e retenção de 14 dias. Sem `--yes`, a restauração só explica que o conteúdo atual do volume será substituído.

O `deploy` arquiva o volume antes do build e guarda a imagem anterior como `:previous`. Se o contêiner subir sem teto de memória ou CPU, ou se o healthcheck falhar, o script volta para essa imagem.

## Rodar nesta máquina, sem Docker

Três processos, nesta ordem:

```bash
python3 -m venv ai-engine/.venv
ai-engine/.venv/bin/pip install -r ai-engine/requirements.txt
ai-engine/.venv/bin/uvicorn app.main:app --app-dir ai-engine --host 127.0.0.1 --port 8092

python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
DATA_PATH=backend/data/lastro.db AI_ENGINE_URL=http://127.0.0.1:8092 \
  backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8091

cd frontend && npm install && npm run dev
```

A mesa fica em [http://127.0.0.1:4181](http://127.0.0.1:4181).

## O que cada serviço faz

- `backend` guarda as posições em SQLite e pede a leitura ao motor.
- `ai-engine` calcula HHI, peso por rede e notas determinísticas. No mesmo processo, o turno das 04:30 UTC treina a previsão diária se a carga do host estiver ociosa. `OPENBLAS_NUM_THREADS=1` impede que a biblioteca numérica espalhe threads pelo host. `oom_score_adj: 400` faz o kernel preferir encerrar o motor se a VPS inteira ficar sem RAM. O motor não publica porta no host; a rede `egress` só existe para ele buscar a Binance e o FRED.
- `frontend` é a mesa. O browser só fala com o Next.js; o Next.js fala com a API. Em `/reino`, o conselho lê a carteira e o Vigia audita o lote antes da Phantom.

## Conselho e transação

`GET /status-reino`, `GET /missoes-ativas` e `GET /analise-risco` são assíncronas. `POST /transacao-nao-assinada` continua devolvendo o selo antigo, que não transfere tokens: memos na Solana, ou uma chamada de valor zero para o próprio endereço na Base.

`POST /rota-missao` monta o lote que move o que o investidor aprovar. O slippage fica em 1% (100 bps). Na Ethereum, compra e venda vão ao SwapRouter02 da Uniswap (`0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`), com `exactInputSingle` e approve do valor exato. O depósito de earn vai ao Pool do Aave V3 (`0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2`), com `supply` em nome do próprio investidor. O stop é uma ordem limitada do CoW Protocol: o usuário assina o EIP-712 e a API só então publica em `api.cow.fi`. A permissão do token vai ao VaultRelayer (`0xC92E8bdf79f0507f65a392b0ab4667716BFE0110`), no valor exato, e só entra no envio se a publicação for aceita. Na Solana, o swap da Jupiter v6 (`JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4`) e o limite de compute cabem na mesma Transaction V0. Programa ou contrato fora da lista interrompe o lote. Uma rede que não seja Ethereum ou Solana vira aviso e fica de fora. Sem a cotação da Jupiter, o swap Solana também fica de fora.

Contêineres rodam sem root, com `cap_drop: ALL`, `no-new-privileges` e sistema de arquivos raiz somente leitura. Logs do Docker giram em 10 MiB × 3 arquivos. `memswap_limit` igual ao teto de RAM impede que o motor estoure o limite via swap.

## Sala do Trono

`/reino` é a sala isométrica do conselho, em pixel, com a Press Start 2P e a Silkscreen para o português. Os três personagens andam entre as mesas, digitam e atendem o telefone. O clique abre o diálogo que vem de `status-reino`, `missoes-ativas` e `analise-risco`. O CIO mostra o peso da carteira em barras. Antes da Phantom, o Vigia lista três marcas: `Slippage max: 1%`, `Smart Contract Validated: Yes` e `Stop-Loss set: Yes`. `[ ACEITAR MISSÃO ]` só habilita com as três. A Phantom então assina o lote na Ethereum (e a Transaction V0 na Solana, quando ela existir). Sem a extensão, a lista fica na mesa e nada é enviado. Se a rede recusar, a caixa diz uma destas frases: “A magia falhou, aventureiro! O alforje não tem o ouro desta travessia.”, “A magia falhou, aventureiro! O preço escorregou além do limite de 1%.” ou “A magia falhou, aventureiro! Tu recusaste o selo no limiar da Phantom.”

## Previsão diária

O turno usa APScheduler dentro do motor, às 04:30 UTC, com uma instância por vez. Se a carga de 1 minuto passar de `QUANT_IDLE_LOAD_RATIO` (padrão 0,5) vezes o número de CPUs, o treino espera o próximo dia. O mesmo comando roda fora do processo, quando o operador quiser forçar:

```bash
cd ai-engine && QUANT_FORCE=1 FORECAST_PATH=data/forecasts.json PYTHONPATH=. .venv/bin/python -m app.quant.job
```

Cripto: BTCUSDT, ETHUSDT e SOLUSDT na Binance (e, se a API principal recusar, em `data-api.binance.vision`). Macro: dólar amplo `DTWEXBGS`, euro `DEXUSEU` e Brent `DCOILBRENTEU` no FRED. Com `FRED_API_KEY`, a leitura usa a API; sem chave, usa o CSV público. Ações individuais não estão nesse par de fontes, então a manga de bolsa é o Nasdaq Composite, série `NASDAQCOM`, marcada como índice. A série LBMA de ouro saiu do FRED em janeiro de 2022; quando ela não tem leitura recente, o ouro entra pelo PAXGUSDT e o JSON registra `fonte_ouro`.

Cada ativo sai com direção (`alta`, `baixa` ou `lateral`), confiança, preço de referência, stop e alvo para o pregão seguinte. O corte é cronológico, 80% treino e 20% teste. A validação cruzada `TimeSeriesSplit` só corre dentro do treino. A rede é um MLP em PyTorch, com retropropagação, e o ajuste escolhe o tamanho da camada e a taxa de aprendizado nessa validação, com `ReduceLROnPlateau` e parada antecipada. `GET /forecasts` no motor, e `GET /previsoes` na API, devolvem o último JSON. Nenhum dos dois treina na hora do pedido. A previsão não é ordem e não move saldo.

## Testes

```bash
( cd ai-engine && PYTHONPATH=. QUANT_SCHEDULER=0 .venv/bin/python -m unittest discover tests )
( cd backend && PYTHONPATH=. .venv/bin/python -m unittest discover tests )
./scripts/vps.sh budget
```
