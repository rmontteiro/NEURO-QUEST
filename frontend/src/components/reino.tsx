"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { magiaFalhou } from "@/lib/magia";
import { errorMessage, pct, usd } from "@/lib/types";

type Order = {
  tipo: string;
  simbolo: string;
  simbolo_par: string | null;
  rede?: string;
  quantidade: number;
  preco_usd: number;
};

type Holding = { simbolo: string; peso: number };

type Speech = {
  agente: string;
  cargo: string;
  fala: string;
  fonte: string;
  aviso: string | null;
  fonte_numeros: string;
  dados: {
    ordens: Order[];
    missoes: string[];
    carteira?: Holding[];
    total_usd?: number;
    concentracao?: { hhi?: number; band?: string; top_symbol?: string | null };
  };
};

type AuditItem = { rotulo: string; ok: boolean };

type ChainCall = {
  para: string;
  data: string;
  value: string;
  descricao: string;
  papel?: string;
};

type LimitOrder = {
  protocolo: string;
  typed_data: {
    domain: Record<string, unknown>;
    types: Record<string, unknown>;
    primaryType: string;
    message: Record<string, unknown>;
  };
};

type SolanaLote = {
  serialized_base64: string;
  blockhash?: string;
  last_valid_block_height?: number;
  descricao?: string;
};

type SolanaBatch = { serialized_base64: string; lotes?: SolanaLote[] };

type MissionRoute = {
  custodia: boolean;
  enviar: boolean;
  avisos: string[];
  auditoria: { ok: boolean; itens: AuditItem[] };
  chamadas: ChainCall[];
  solana: SolanaBatch | null;
  limite: LimitOrder | null;
};

const ROUTES = [
  { path: "status-reino", key: "ceo" },
  { path: "missoes-ativas", key: "cio" },
  { path: "analise-risco", key: "cco" },
] as const;

const SOLANA_RPC = process.env.NEXT_PUBLIC_SOLANA_RPC || "https://solana-rpc.publicnode.com";
const BAND: Record<string, string> = {
  alta: "Concentração alta",
  moderada: "Concentração moderada",
  contida: "Concentração contida",
  vazia: "Sem leitura",
};

const ORDER_LABEL: Record<string, string> = {
  venda: "Venda",
  compra: "Compra",
  stop: "Proteção",
  pool: "Alocação",
};

const BRIEFS = [
  { key: "ceo", titulo: "Estratégia", texto: "O que a carteira está dizendo." },
  { key: "cio", titulo: "Propostas", texto: "O que faria sentido ajustar, ainda sem executar." },
  { key: "cco", titulo: "Risco", texto: "Onde a carteira está concentrada." },
] as const;

type SolanaProvider = {
  isPhantom?: boolean;
  connect: () => Promise<{ publicKey: { toString: () => string } }>;
  signTransaction: (tx: { serialize: () => Uint8Array }) => Promise<{ serialize: () => Uint8Array }>;
};

type EvmProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

function phantomSolana(): SolanaProvider | null {
  const win = window as unknown as {
    phantom?: { solana?: SolanaProvider };
    solana?: SolanaProvider;
  };
  if (win.phantom?.solana?.isPhantom) return win.phantom.solana;
  return win.solana?.isPhantom ? win.solana : null;
}

function phantomEthereum(): EvmProvider | null {
  const win = window as unknown as {
    phantom?: { ethereum?: EvmProvider & { isPhantom?: boolean } };
    ethereum?: EvmProvider & { isPhantom?: boolean };
  };
  const daPhantom = win.phantom?.ethereum;
  if (daPhantom?.isPhantom) return daPhantom;
  return win.ethereum?.isPhantom ? win.ethereum : null;
}

function enderecoHttps(): string | null {
  if (window.isSecureContext) return null;
  const host = window.location.hostname;
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    return `https://${host}.nip.io${window.location.pathname}`;
  }
  return null;
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { detail: text };
  }
}

function Conferencia({
  route,
  loading,
  error,
}: {
  route: MissionRoute | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <p className="text-sm text-muted-foreground">Conferindo contratos, slippage e proteção antes da assinatura.</p>;
  }
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }
  if (!route) {
    return <p className="text-sm text-muted-foreground">A conferência ainda não voltou da mesa.</p>;
  }
  return (
    <div className="space-y-3">
      <ul className="space-y-2 text-sm" aria-label="Conferência antes da assinatura">
        {route.auditoria.itens.map((item) => (
          <li key={item.rotulo} className="flex items-center justify-between gap-3">
            <span>{item.rotulo}</span>
            <Badge variant={item.ok ? "secondary" : "destructive"}>{item.ok ? "Em ordem" : "Pendente"}</Badge>
          </li>
        ))}
      </ul>
      {route.avisos.length > 0 ? (
        <ul className="space-y-1 text-sm text-muted-foreground">
          {route.avisos.map((aviso, index) => (
            <li key={`${index}-${aviso}`}>{aviso}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Reino() {
  const [speeches, setSpeeches] = useState<Record<string, Speech | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [seal, setSeal] = useState<string | null>(null);
  const [sealHref, setSealHref] = useState<string | null>(null);
  const [sealing, setSealing] = useState(false);
  const [spell, setSpell] = useState<string | null>(null);
  const [route, setRoute] = useState<MissionRoute | null>(null);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [routeLoading, setRouteLoading] = useState(true);
  const [seguro, setSeguro] = useState(false);
  const [httpsHref, setHttpsHref] = useState<string | null>(null);
  const [conta, setConta] = useState<string | null>(null);
  const [contaSolana, setContaSolana] = useState<string | null>(null);
  const [etapa, setEtapa] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const nextSpeeches: Record<string, Speech | null> = {};
    const nextErrors: Record<string, string> = {};
    await Promise.all(
      ROUTES.map(async (route) => {
        try {
          const response = await fetch(`/api/backend/${route.path}`, { cache: "no-store" });
          const payload = await readJson(response);
          if (!response.ok) {
            nextErrors[route.key] = errorMessage(payload, "A assessoria não respondeu.");
            nextSpeeches[route.key] = null;
            return;
          }
          nextSpeeches[route.key] = payload as Speech;
        } catch {
          nextErrors[route.key] = "A mesa perdeu a leitura da assessoria.";
          nextSpeeches[route.key] = null;
        }
      }),
    );
    setSpeeches(nextSpeeches);
    setErrors(nextErrors);
    setLoading(false);
  }, []);

  const askRoute = useCallback(async (solanaKey: string | null, ethereum: string | null, blockhash: string | null) => {
    const response = await fetch("/api/backend/rota-missao", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        pagador_solana: solanaKey,
        pagador_ethereum: ethereum,
        blockhash,
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(errorMessage(payload, "A conferência da rota não ficou pronta."));
    }
    return payload as MissionRoute;
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    setSeguro(window.isSecureContext);
    setHttpsHref(enderecoHttps());
  }, []);

  useEffect(() => {
    let cancel = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        setRouteLoading(true);
        try {
          const preview = await askRoute(contaSolana, conta, null);
          if (cancel) return;
          setRoute(preview);
          setRouteError(null);
        } catch (error) {
          if (cancel) return;
          setRoute(null);
          setRouteError(error instanceof Error ? error.message : "A conferência não respondeu.");
        } finally {
          if (!cancel) setRouteLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancel = true;
      window.clearTimeout(timer);
    };
  }, [askRoute, conta, contaSolana]);

  const orders = speeches.cio?.dados.ordens ?? [];
  const book = speeches.cio?.dados.carteira ?? [];
  const concentration = speeches.cco?.dados.concentracao ?? speeches.cio?.dados.concentracao;
  const offline = !loading && ROUTES.every((route) => errors[route.key]);
  async function switchToEthereum(evm: EvmProvider) {
    try {
      await evm.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: "0x1" }],
      });
    } catch (error) {
      const code = (error as { code?: number }).code;
      if (code !== 4902) throw error;
      await evm.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId: "0x1",
            chainName: "Ethereum",
            nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
            rpcUrls: ["https://ethereum.publicnode.com"],
            blockExplorerUrls: ["https://etherscan.io"],
          },
        ],
      });
    }
  }

  async function publishLimit(evm: EvmProvider, payer: string, limit: LimitOrder) {
    const signature = (await evm.request({
      method: "eth_signTypedData_v4",
      params: [payer, JSON.stringify(limit.typed_data)],
    })) as string;
    const response = await fetch("/api/backend/rota-missao/publicar", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        pagador: payer,
        assinatura: signature,
        ordem: limit.typed_data.message,
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(errorMessage(payload, "A ordem limitada não entrou no livro."));
    }
  }

  async function conectarSolana(): Promise<string> {
    if (!window.isSecureContext) {
      throw new Error("A Phantom só conecta numa página HTTPS.");
    }
    const solana = phantomSolana();
    if (!solana) {
      throw new Error("A Phantom não está neste navegador.");
    }
    const connected = await solana.connect();
    const key = connected.publicKey.toString();
    setContaSolana(key);
    return key;
  }

  async function conectarPhantom(): Promise<string> {
    if (!window.isSecureContext) {
      throw new Error("A Phantom só conecta numa página HTTPS.");
    }
    const evm = phantomEthereum();
    if (!evm) {
      throw new Error("A Phantom não está neste navegador.");
    }
    const accounts = (await evm.request({ method: "eth_requestAccounts" })) as string[];
    const payer = accounts[0];
    if (!payer) throw new Error("A Phantom não devolveu uma conta Ethereum.");
    await switchToEthereum(evm);
    setConta(payer);
    return payer;
  }

  async function enviarChamada(evm: EvmProvider, payer: string, call: ChainCall): Promise<string> {
    setEtapa(call.descricao);
    return (await evm.request({
      method: "eth_sendTransaction",
      params: [{ from: payer, to: call.para, data: call.data, value: call.value }],
    })) as string;
  }

  async function acceptMission() {
    setSealing(true);
    setSeal(null);
    setSealHref(null);
    setSpell(null);
    setEtapa(null);
    const enviados: string[] = [];
    try {
      if (!window.isSecureContext) {
        setSeal("A Phantom não abre em HTTP. Use o endereço HTTPS indicado acima. Nada foi enviado.");
        return;
      }
      const evm = phantomEthereum();
      const solana = phantomSolana();
      if (!evm && !solana) {
        setSeal("A Phantom não está neste navegador. Instale a extensão e recarregue esta página. Nada foi enviado.");
        return;
      }
      const needsSolana = orders.some((order) => order.rede === "solana");
      const needsEthereum = orders.some((order) => order.rede === "ethereum" || order.rede === "eth");
      if (needsSolana && !solana) {
        setSeal("O swap da Jupiter pede a Phantom na Solana. Nada foi enviado.");
        return;
      }

      let ethereum = conta;
      if (evm && needsEthereum) {
        ethereum = await conectarPhantom();
      }

      let solanaKey: string | null = contaSolana;
      let connection: {
        sendRawTransaction: (raw: Uint8Array, opts: { skipPreflight: boolean; maxRetries: number }) => Promise<string>;
        confirmTransaction: (
          args: { signature: string; blockhash: string; lastValidBlockHeight: number },
          commitment: "confirmed",
        ) => Promise<unknown>;
      } | null = null;
      if (solana && needsSolana) {
        solanaKey = await conectarSolana();
        const { Connection } = await import("@solana/web3.js");
        connection = new Connection(SOLANA_RPC, "confirmed");
      }

      const fresh = await askRoute(solanaKey, ethereum, null);
      setRoute(fresh);
      if ((fresh.chamadas.length > 0 || fresh.limite) && !ethereum) {
        setSeal("Estas propostas assinam na Ethereum. Abra a Phantom nessa rede. Nada foi enviado.");
        return;
      }
      if (fresh.solana && !solanaKey) {
        setSeal("O swap da Jupiter pede a Phantom na Solana. Nada foi enviado.");
        return;
      }
      if (!fresh.auditoria.ok || !fresh.enviar || fresh.custodia) {
        throw new Error("A conferência de risco não liberou o envio.");
      }

      const movimentos = fresh.chamadas.filter((call) => call.papel !== "protecao");
      const protecoes = fresh.chamadas.filter((call) => call.papel === "protecao");
      let href: string | null = null;
      if (movimentos.length > 0 && evm && ethereum) {
        for (const call of movimentos) {
          const sent = await enviarChamada(evm, ethereum, call);
          enviados.push(call.descricao);
          if (/^0x[0-9a-fA-F]{64}$/.test(sent)) href = `https://etherscan.io/tx/${sent}`;
        }
      }

      if (fresh.limite) {
        if (!evm || !ethereum) {
          setSeal("A ordem limitada pede a Phantom na Ethereum. O restante já enviado permanece.");
          return;
        }
        setEtapa("Assinando a ordem limitada");
        await publishLimit(evm, ethereum, fresh.limite);
        for (const call of protecoes) {
          const sent = await enviarChamada(evm, ethereum, call);
          enviados.push(call.descricao);
          if (/^0x[0-9a-fA-F]{64}$/.test(sent)) href = `https://etherscan.io/tx/${sent}`;
        }
      }

      const lotes: SolanaLote[] =
        fresh.solana?.lotes && fresh.solana.lotes.length > 0
          ? fresh.solana.lotes
          : fresh.solana
            ? [{ serialized_base64: fresh.solana.serialized_base64 }]
            : [];
      if (lotes.length > 0 && solana && connection) {
        const { VersionedTransaction } = await import("@solana/web3.js");
        for (const lote of lotes) {
          setEtapa(lote.descricao || "Assinando o swap na Solana");
          const bytes = Uint8Array.from(atob(lote.serialized_base64), (char) => char.charCodeAt(0));
          const signed = await solana.signTransaction(VersionedTransaction.deserialize(bytes));
          const signature = await connection.sendRawTransaction(signed.serialize(), {
            skipPreflight: false,
            maxRetries: 3,
          });
          href = `https://solscan.io/tx/${signature}`;
          enviados.push(lote.descricao || "Swap na Jupiter");
          if (lote.blockhash && lote.last_valid_block_height) {
            try {
              await connection.confirmTransaction(
                { signature, blockhash: lote.blockhash, lastValidBlockHeight: lote.last_valid_block_height },
                "confirmed",
              );
            } catch {
              setSeal("A Phantom assinou o lote na Solana. A confirmação da rede ainda não voltou.");
              setSealHref(href);
              return;
            }
          }
        }
      }

      const feito = enviados.length > 0 ? ` Enviado: ${enviados.join("; ")}.` : "";
      setSeal(`A Phantom assinou e a rede recebeu a movimentação.${feito} A assessoria não guarda a chave.`);
      setSealHref(href);
    } catch (error) {
      const feito = enviados.length > 0 ? ` Já enviado antes da falha: ${enviados.join("; ")}. ` : "";
      setSpell(`${feito}${magiaFalhou(error)}`);
    } finally {
      setEtapa(null);
      setSealing(false);
    }
  }

  const total = speeches.ceo?.dados.total_usd ?? speeches.cio?.dados.total_usd ?? 0;
  const precisaSolana = orders.some((order) => order.rede === "solana");
  const precisaEthereum = orders.some((order) => order.rede === "ethereum" || order.rede === "eth");
  const solanaPronta = !precisaSolana || Boolean(contaSolana);
  const ethereumPronta = !precisaEthereum || Boolean(conta);
  const carteiraPronta = solanaPronta && ethereumPronta;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <header className="flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Neuro-Quest Capital</p>
          <h1 className="font-display text-4xl leading-none tracking-tight italic sm:text-5xl">Assessoria</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Três leituras da mesma carteira: o que ela mostra, que ajuste está proposto e onde está o risco.
            Nada é executado até a sua assinatura. A assessoria não guarda a chave.
          </p>
        </div>
        <Link href="/" className={buttonVariants({ variant: "outline" })}>
          Voltar à mesa
        </Link>
      </header>

      {offline ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
        >
          <p>A assessoria não alcançou a API.</p>
          <Button type="button" variant="outline" onClick={() => void load()}>
            Tentar de novo
          </Button>
        </div>
      ) : null}

      <section className="grid gap-3 lg:grid-cols-3" aria-label="Leituras da assessoria">
        {BRIEFS.map((brief) => {
          const speech = speeches[brief.key];
          const speechError = errors[brief.key];
          return (
            <Card key={brief.key}>
              <CardHeader>
                <CardDescription>{brief.texto}</CardDescription>
                <CardTitle className="text-xl">{speech?.agente ?? brief.titulo}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm leading-relaxed">
                {loading ? <p className="text-muted-foreground">Lendo a carteira…</p> : null}
                {!loading && speechError ? <p role="alert">{speechError}</p> : null}
                {!loading && !speechError ? <p>{speech?.fala ?? "Esta leitura ainda não chegou."}</p> : null}
                {speech?.aviso ? <p className="mt-3 text-muted-foreground">{speech.aviso}</p> : null}
              </CardContent>
            </Card>
          );
        })}
      </section>

      <section className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Composição</CardTitle>
            <CardDescription>
              {concentration?.band ? BAND[concentration.band] ?? concentration.band : "Sem leitura"}
              {typeof concentration?.hhi === "number" ? ` · HHI ${concentration.hhi.toFixed(2)}` : ""}
              {loading ? "" : ` · ${usd.format(total)}`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {book.length === 0 ? (
              <p className="text-sm leading-relaxed text-muted-foreground">
                Nenhuma posição para medir. Lance um ativo na mesa e a composição aparece aqui.
              </p>
            ) : (
              <ul className="space-y-3">
                {book.map((item) => (
                  <li key={item.simbolo}>
                    <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                      <span className="font-mono">{item.simbolo}</span>
                      <span className="font-mono tabular-nums text-muted-foreground">{pct.format(item.peso)}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(2, item.peso * 100)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Propostas</CardTitle>
            <CardDescription>Ordens sugeridas a partir do livro lançado. Ainda não foram enviadas.</CardDescription>
          </CardHeader>
          <CardContent>
            {orders.length === 0 ? (
              <p className="text-sm leading-relaxed text-muted-foreground">Sem propostas enquanto a carteira estiver vazia.</p>
            ) : (
              <ul className="divide-y divide-border text-sm">
                {orders.map((order) => (
                  <li key={`${order.tipo}-${order.simbolo}-${order.simbolo_par}`} className="flex items-baseline justify-between gap-3 py-2 first:pt-0 last:pb-0">
                    <span>
                      {ORDER_LABEL[order.tipo] ?? order.tipo} {order.simbolo}
                      {order.simbolo_par ? `/${order.simbolo_par}` : ""}
                    </span>
                    <span className="font-mono tabular-nums text-muted-foreground">{order.quantidade}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Antes de assinar</CardTitle>
          <CardDescription>
            {precisaSolana && !precisaEthereum
              ? "Conecte a Phantom na Solana. Ao assinar, a carteira envia o swap na Jupiter. A taxa de rede é sua. A assessoria não guarda a chave."
              : precisaSolana
                ? "Conecte a Phantom na rede de cada proposta. Na Solana, a assinatura envia o swap na Jupiter. Na Ethereum, envia o que a conferência tiver montado. A taxa de rede é sua."
                : "Conecte a Phantom. Ao assinar, a carteira envia o swap na Uniswap e o depósito no Aave V3, e em seguida a permissão da ordem limitada. A taxa de rede é sua. A assessoria não guarda a chave."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {!seguro && httpsHref ? (
            <p className="text-sm leading-relaxed">
              A Phantom não aparece numa página aberta em HTTP.{" "}
              <a className="underline" href={httpsHref}>
                Abrir esta assessoria em HTTPS
              </a>
              . O certificado é ativado na VPS com <span className="font-mono">./scripts/https.sh</span>.
            </p>
          ) : null}
          <Conferencia route={route} loading={routeLoading} error={routeError} />
          {contaSolana ? (
            <p className="font-mono text-xs text-muted-foreground">Conta Solana {contaSolana}</p>
          ) : null}
          {conta ? (
            <p className="font-mono text-xs text-muted-foreground">Conta Ethereum {conta}</p>
          ) : null}
          {contaSolana && route?.solana?.lotes && route.solana.lotes.length > 0 ? (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {route.solana.lotes.map((lote) => (
                <li key={lote.descricao || lote.serialized_base64}>{lote.descricao || "Swap na Jupiter"}</li>
              ))}
            </ol>
          ) : null}
          {conta && route && route.chamadas.length > 0 ? (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {route.chamadas.map((call) => (
                <li key={`${call.papel}-${call.descricao}`}>{call.descricao}</li>
              ))}
            </ol>
          ) : null}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button
              type="button"
              disabled={
                !seguro ||
                sealing ||
                (carteiraPronta ? loading || routeLoading || orders.length === 0 || !route?.auditoria.ok : false)
              }
              onClick={() => {
                const falha = (error: unknown) => {
                  setSeal(error instanceof Error ? error.message : "A Phantom não conectou.");
                };
                if (precisaSolana && !contaSolana) {
                  void conectarSolana().catch(falha);
                  return;
                }
                if (precisaEthereum && !conta) {
                  void conectarPhantom().catch(falha);
                  return;
                }
                void acceptMission();
              }}
            >
              {sealing
                ? etapa || "Aguardando a Phantom…"
                : precisaSolana && !contaSolana
                  ? "Conectar Phantom na Solana"
                  : precisaEthereum && !conta
                    ? "Conectar Phantom"
                    : "Assinar e enviar"}
            </Button>
            {carteiraPronta && !routeLoading && route && !route.auditoria.ok ? (
              <p className="text-sm text-muted-foreground">O envio fica bloqueado até a conferência fechar.</p>
            ) : null}
          </div>
          {seal ? (
            <p role="status" className="text-sm leading-relaxed">
              {seal}{" "}
              {sealHref ? (
                <a className="underline" href={sealHref} target="_blank" rel="noreferrer">
                  Ver na rede
                </a>
              ) : null}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {spell ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-background/80 p-4 sm:items-center">
          <div role="alertdialog" aria-labelledby="falha-titulo" aria-describedby="falha-texto" className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-lg">
            <p id="falha-titulo" className="font-display text-2xl italic">A ordem não foi enviada</p>
            <p id="falha-texto" className="mt-3 text-sm leading-relaxed">{spell}</p>
            <Button type="button" className="mt-4" variant="outline" onClick={() => setSpell(null)}>
              Fechar
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
