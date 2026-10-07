"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/types";

type Speech = {
  agente: string;
  cargo: string;
  fala: string;
  fonte: string;
  aviso: string | null;
  fonte_numeros: string;
  dados: {
    ordens: { tipo: string; simbolo: string; simbolo_par: string | null; quantidade: number; preco_usd: number }[];
    missoes: string[];
  };
};

type CallPreview = {
  tipo: string;
  contrato: string;
  funcao: string;
  data: string;
  incluida_na_transacao: boolean;
};

type Bundle = {
  efeito: string;
  move_tokens: boolean;
  ordens: string[];
  solana: {
    serialized_base64: string;
    blockhash_provisorio: boolean;
    instrucoes: string[];
    tamanho_bytes: number;
  } | null;
  base: {
    chain_id: number;
    transacao: Record<string, string>;
    chamadas_prontas: CallPreview[];
  } | null;
};

const ROUTES = [
  { path: "status-reino", key: "ceo" },
  { path: "missoes-ativas", key: "cio" },
  { path: "analise-risco", key: "cco" },
] as const;

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { detail: text };
  }
}

type SolanaProvider = {
  isPhantom?: boolean;
  connect: () => Promise<unknown>;
  signTransaction: (tx: { serialize: () => Uint8Array }) => Promise<{ serialize: () => Uint8Array }>;
};

type EvmProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

function phantomSolana(): SolanaProvider | null {
  const provider = (window as unknown as { solana?: SolanaProvider }).solana;
  return provider?.isPhantom ? provider : null;
}

function phantomEthereum(): EvmProvider | null {
  const phantom = (window as unknown as { phantom?: { ethereum?: EvmProvider } }).phantom;
  return phantom?.ethereum ?? null;
}

export function Reino() {
  const [speeches, setSpeeches] = useState<Record<string, Speech | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [solanaKey, setSolanaKey] = useState("");
  const [baseAddress, setBaseAddress] = useState("");
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [forgeError, setForgeError] = useState<string | null>(null);
  const [forging, setForging] = useState(false);
  const [signNote, setSignNote] = useState<string | null>(null);
  const [signing, setSigning] = useState<"solana" | "base" | null>(null);

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
            nextErrors[route.key] = errorMessage(payload, "O conselho não respondeu.");
            nextSpeeches[route.key] = null;
            return;
          }
          nextSpeeches[route.key] = payload as Speech;
        } catch {
          nextErrors[route.key] = "A mesa perdeu o conselho.";
          nextSpeeches[route.key] = null;
        }
      }),
    );
    setSpeeches(nextSpeeches);
    setErrors(nextErrors);
    setLoading(false);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function forge() {
    setForgeError(null);
    setSignNote(null);
    setForging(true);
    try {
      const response = await fetch("/api/backend/transacao-nao-assinada", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          pagador_solana: solanaKey.trim() || null,
          pagador_base: baseAddress.trim() || null,
        }),
      });
      const payload = await readJson(response);
      if (!response.ok) {
        setBundle(null);
        setForgeError(errorMessage(payload, "Não foi possível empacotar as ordens."));
        return;
      }
      setBundle(payload as Bundle);
    } catch {
      setForgeError("A API não recebeu o pedido da transação.");
    } finally {
      setForging(false);
    }
  }

  async function signSolana() {
    if (!bundle?.solana) return;
    setSigning("solana");
    setSignNote(null);
    try {
      const provider = phantomSolana();
      if (!provider) {
        setSignNote("A Phantom não está instalada neste navegador. A carga Solana continua aqui para você revisar.");
        return;
      }
      const { Transaction } = await import("@solana/web3.js");
      const bytes = Uint8Array.from(atob(bundle.solana.serialized_base64), (char) => char.charCodeAt(0));
      await provider.connect();
      const signed = await provider.signTransaction(Transaction.from(bytes));
      const encoded = btoa(String.fromCharCode(...signed.serialize()));
      setSignNote(`Phantom assinou a transação Solana (${encoded.length} caracteres). Nada foi enviado à rede.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "A Phantom recusou a assinatura Solana.";
      setSignNote(message);
    } finally {
      setSigning(null);
    }
  }

  async function signBase() {
    if (!bundle?.base) return;
    setSigning("base");
    setSignNote(null);
    try {
      const provider = phantomEthereum();
      if (!provider) {
        setSignNote("A Phantom EVM não está neste navegador. A carga da Base continua aqui para você revisar.");
        return;
      }
      const accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
      const nonce = await provider.request({
        method: "eth_getTransactionCount",
        params: [accounts[0], "pending"],
      });
      const signed = await provider.request({
        method: "eth_signTransaction",
        params: [{ ...bundle.base.transacao, from: accounts[0], nonce }],
      });
      setSignNote(`Phantom devolveu a assinatura da Base. Nada foi enviado à rede. ${String(signed).slice(0, 18)}…`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "A Phantom recusou a assinatura na Base.";
      setSignNote(message);
    } finally {
      setSigning(null);
    }
  }

  const orders = speeches.cio?.dados.ordens ?? speeches.ceo?.dados.ordens ?? [];
  const offline = !loading && ROUTES.every((route) => errors[route.key]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <header className="flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <p className="text-xs tracking-[0.18em] text-primary uppercase">Neuro-Quest Capital</p>
          <h1 className="font-display text-4xl leading-none italic sm:text-5xl">Conselho do reino</h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
            Três personagens leem a mesma carteira. A transação que segue empacota venda, compra, stop e pool
            para a Phantom assinar. Ela não transfere tokens.
          </p>
        </div>
        <Link href="/" className={buttonVariants({ variant: "outline" })}>
          Voltar à mesa
        </Link>
      </header>

      {offline ? (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <p>O conselho não alcançou a API.</p>
          <Button type="button" variant="outline" onClick={() => void load()}>
            Tentar de novo
          </Button>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        {ROUTES.map((route) => {
          const speech = speeches[route.key];
          const error = errors[route.key];
          return (
            <Card key={route.key} className="shadow-[4px_4px_0_0_var(--primary)]">
              <CardHeader>
                <CardDescription>{speech?.cargo ?? route.key.toUpperCase()}</CardDescription>
                <CardTitle className="font-display text-2xl italic">
                  {loading ? "Abrindo o pergaminho…" : speech?.agente ?? "Em silêncio"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-relaxed">
                {loading ? <div className="h-24 animate-pulse rounded-lg bg-muted" /> : null}
                {error ? (
                  <p role="alert" className="text-destructive">
                    {error}
                  </p>
                ) : null}
                {speech ? (
                  <>
                    <p>{speech.fala}</p>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">{speech.fonte === "gemini" ? "Gemini" : "Crônica local"}</Badge>
                      <Badge variant="secondary">
                        {speech.fonte_numeros === "motor" ? "Motor quantitativo" : "Contingência da mesa"}
                      </Badge>
                    </div>
                    {speech.aviso ? <p className="text-muted-foreground">{speech.aviso}</p> : null}
                  </>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Ordens do pergaminho</CardTitle>
          <CardDescription>
            Quatro tipos na mesma carga: venda, compra, stop e pool. Os preços são os lançados na mesa.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {orders.length === 0 && !loading ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma ordem enquanto a carteira estiver vazia. Lance uma posição na mesa para o conselho propor quests.
            </p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {orders.map((order) => (
                <li key={`${order.tipo}-${order.simbolo}-${order.simbolo_par}`} className="rounded-lg border border-border px-3 py-2 font-mono text-xs">
                  <span className="text-primary">{order.tipo}</span> {order.simbolo}
                  {order.simbolo_par ? `/${order.simbolo_par}` : ""} · {order.quantidade} @ {order.preco_usd}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transação não assinada</CardTitle>
          <CardDescription>
            Solana, pelo custo. Base, pela interoperabilidade EVM. As duas cabem na Phantom. O servidor não guarda chave
            e não envia a transação.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="solana-key">Chave pública Solana</Label>
              <Input
                id="solana-key"
                autoComplete="off"
                spellCheck={false}
                value={solanaKey}
                onChange={(event) => setSolanaKey(event.target.value)}
                placeholder="A chave pública da Phantom, não a semente"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="base-address">Endereço na Base</Label>
              <Input
                id="base-address"
                autoComplete="off"
                spellCheck={false}
                value={baseAddress}
                onChange={(event) => setBaseAddress(event.target.value)}
                placeholder="0x…"
              />
            </div>
          </div>
          {forgeError ? (
            <p role="alert" className="text-sm text-destructive">
              {forgeError}
            </p>
          ) : null}
          <Button type="button" onClick={() => void forge()} disabled={forging || loading || orders.length === 0}>
            {forging ? "Forjando…" : "Forjar as duas cargas"}
          </Button>

          {bundle ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {bundle.solana ? (
                <section className="space-y-3 rounded-lg border border-border p-3">
                  <h2 className="font-display text-xl italic">Solana</h2>
                  <p className="text-sm text-muted-foreground">
                    {bundle.solana.instrucoes.length} instruções, {bundle.solana.tamanho_bytes} bytes.
                    {bundle.solana.blockhash_provisorio
                      ? " O blockhash é provisório: a assinatura não será transmitida."
                      : ""}
                  </p>
                  <Button type="button" variant="outline" onClick={() => void signSolana()} disabled={signing !== null}>
                    {signing === "solana" ? "Aguardando a Phantom…" : "Assinar na Phantom"}
                  </Button>
                </section>
              ) : null}
              {bundle.base ? (
                <section className="space-y-3 rounded-lg border border-border p-3">
                  <h2 className="font-display text-xl italic">Base</h2>
                  <p className="text-sm text-muted-foreground">
                    Cadeia {bundle.base.chain_id}. Destino é o próprio endereço, valor zero. A carteira preenche o nonce.
                  </p>
                  <Button type="button" variant="outline" onClick={() => void signBase()} disabled={signing !== null}>
                    {signing === "base" ? "Aguardando a Phantom…" : "Assinar na Phantom"}
                  </Button>
                  {bundle.base.chamadas_prontas.length > 0 ? (
                    <details className="text-sm">
                      <summary className="cursor-pointer text-muted-foreground">
                        Chamadas do SwapRouter02 e do Position Manager, fora desta assinatura
                      </summary>
                      <ul className="mt-2 space-y-2">
                        {bundle.base.chamadas_prontas.map((call) => (
                          <li key={`${call.tipo}-${call.funcao}`} className="break-all font-mono text-xs">
                            {call.tipo} · {call.contrato.slice(0, 10)}… · {call.data.slice(0, 18)}…
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </section>
              ) : null}
            </div>
          ) : null}
          {signNote ? (
            <p role="status" className="text-sm text-muted-foreground">
              {signNote}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
