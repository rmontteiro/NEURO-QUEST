# Lastro

Mesa de portfólio Web3 para uma VPS compartilhada. Três serviços sobem em contêineres separados: a API (FastAPI), o motor de leitura (NumPy e pandas) e a mesa (Next.js). O motor tem teto de CPU e memória para não tomar a máquina das automações que já rodam no host.

Os preços são os que você lança. Não há feed de mercado e não há modelo de linguagem. A leitura calcula concentração (HHI), ativos efetivos e peso por rede.

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
- `ai-engine` calcula HHI, peso por rede e notas determinísticas. `OPENBLAS_NUM_THREADS=1` impede que a biblioteca numérica espalhe threads pelo host. `oom_score_adj: 400` faz o kernel preferir encerrar o motor se a VPS inteira ficar sem RAM.
- `frontend` é a mesa. O browser só fala com o Next.js; o Next.js fala com a API.

Contêineres rodam sem root, com `cap_drop: ALL`, `no-new-privileges` e sistema de arquivos raiz somente leitura. Logs do Docker giram em 10 MiB × 3 arquivos. `memswap_limit` igual ao teto de RAM impede que o motor estoure o limite via swap.

## Testes

```bash
( cd ai-engine && PYTHONPATH=. .venv/bin/python -m unittest tests/test_engine.py )
( cd backend && PYTHONPATH=. .venv/bin/python -m unittest tests/test_api.py )
./scripts/vps.sh budget
```
