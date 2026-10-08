"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { magiaFalhou, metodoAusente } from "@/lib/magia";
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

type SolanaBatch = { serialized_base64: string };

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
  const phantom = (window as unknown as { phantom?: { ethereum?: EvmProvider } }).phantom;
  return phantom?.ethereum ?? null;
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
          {route.avisos.map((aviso) => (
            <li key={aviso}>{aviso}</li>
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
    let cancel = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        setRouteLoading(true);
        try {
          const preview = await askRoute(null, null, null);
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
  }, [askRoute]);

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

  async function sendEthereum(evm: EvmProvider, payer: string, calls: ChainCall[]) {
    const batch = calls.map((call) => ({ to: call.para, data: call.data, value: call.value }));
    try {
      const id = await evm.request({
        method: "wallet_sendCalls",
        params: [{ version: "2.0.0", from: payer, chainId: "0x1", calls: batch }],
      });
      return typeof id === "string" ? id : null;
    } catch (error) {
      if (!metodoAusente(error)) throw error;
    }
    let last = "";
    for (const call of calls) {
      last = (await evm.request({
        method: "eth_sendTransaction",
        params: [{ from: payer, to: call.para, data: call.data, value: call.value }],
      })) as string;
    }
    return last;
  }

  async function acceptMission() {
    setSealing(true);
    setSeal(null);
    setSealHref(null);
    setSpell(null);
    try {
      const evm = phantomEthereum();
      const solana = phantomSolana();
      if (!evm && !solana) {
        setSeal("A Phantom não está neste navegador. A conferência fica registrada e nenhuma transação foi enviada.");
        return;
      }

      let ethereum: string | null = null;
      if (evm) {
        const accounts = (await evm.request({ method: "eth_requestAccounts" })) as string[];
        ethereum = accounts[0] ?? null;
        if (ethereum) await switchToEthereum(evm);
      }

      let solanaKey: string | null = null;
      let blockhash: string | null = null;
      let connection: {
        sendRawTransaction: (raw: Uint8Array, opts: { skipPreflight: boolean; maxRetries: number }) => Promise<string>;
        confirmTransaction: (
          args: { signature: string; blockhash: string; lastValidBlockHeight: number },
          commitment: "confirmed",
        ) => Promise<unknown>;
      } | null = null;
      let lastValidBlockHeight = 0;
      const needsSolana = orders.some((order) => order.rede === "solana");
      if (solana && needsSolana) {
        const connected = await solana.connect();
        solanaKey = connected.publicKey.toString();
        const { Connection } = await import("@solana/web3.js");
        const live = new Connection(SOLANA_RPC, "confirmed");
        const latest = await live.getLatestBlockhash("confirmed");
        blockhash = latest.blockhash;
        lastValidBlockHeight = latest.lastValidBlockHeight;
        connection = live;
      }

      const fresh = await askRoute(solanaKey, ethereum, blockhash);
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

      if (fresh.limite) {
        if (!evm || !ethereum) {
          setSeal("A ordem limitada pede a Phantom na Ethereum. Nada foi enviado.");
          return;
        }
        await publishLimit(evm, ethereum, fresh.limite);
      }

      let href: string | null = null;
      if (fresh.chamadas.length > 0 && evm && ethereum) {
        const sent = await sendEthereum(evm, ethereum, fresh.chamadas);
        if (sent && /^0x[0-9a-fA-F]{64}$/.test(sent)) href = `https://etherscan.io/tx/${sent}`;
      }

      if (fresh.solana && solana && connection && blockhash) {
        const { VersionedTransaction } = await import("@solana/web3.js");
        const bytes = Uint8Array.from(atob(fresh.solana.serialized_base64), (char) => char.charCodeAt(0));
        const signed = await solana.signTransaction(VersionedTransaction.deserialize(bytes));
        const signature = await connection.sendRawTransaction(signed.serialize(), {
          skipPreflight: false,
          maxRetries: 3,
        });
        href = `https://solscan.io/tx/${signature}`;
        try {
          await connection.confirmTransaction(
            { signature, blockhash, lastValidBlockHeight },
            "confirmed",
          );
        } catch {
          setSeal("A Phantom assinou o lote na Solana. A confirmação da rede ainda não voltou.");
          setSealHref(href);
          return;
        }
      }

      setSeal("As propostas foram assinadas: swap, depósito no Aave e permissão da ordem limitada. A assessoria não guarda a chave.");
      setSealHref(href);
    } catch (error) {
      setSpell(magiaFalhou(error));
    } finally {
      setSealing(false);
    }
  }

  const total = speeches.ceo?.dados.total_usd ?? speeches.cio?.dados.total_usd ?? 0;

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
            A assinatura envia o que você aprovar: swap na Uniswap, depósito no Aave V3 e a permissão exata da ordem
            limitada. Na Solana, o swap da Jupiter entra na mesma transação quando a cotação chega. A taxa de rede é sua.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Conferencia route={route} loading={routeLoading} error={routeError} />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button
              type="button"
              disabled={sealing || loading || routeLoading || orders.length === 0 || !route?.auditoria.ok}
              onClick={() => void acceptMission()}
            >
              {sealing ? "Aguardando a carteira…" : "Assinar propostas"}
            </Button>
            {!routeLoading && route && !route.auditoria.ok ? (
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
