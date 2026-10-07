"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { SalaDoTrono } from "@/components/sala-do-trono";
import { errorMessage, usd } from "@/lib/types";
import type { ActorId } from "@/lib/rotina";

type Order = {
  tipo: string;
  simbolo: string;
  simbolo_par: string | null;
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

type Bundle = {
  move_tokens: boolean;
  solana: { serialized_base64: string } | null;
  base: { chain_id: number; transacao: Record<string, string> } | null;
};

const ROUTES = [
  { path: "status-reino", key: "ceo" },
  { path: "missoes-ativas", key: "cio" },
  { path: "analise-risco", key: "cco" },
] as const;

const SOLANA_RPC = process.env.NEXT_PUBLIC_SOLANA_RPC || "https://solana-rpc.publicnode.com";
const BAR_COLORS = ["#39ff6a", "#f2e27a", "#7ec8ff", "#ff8b7a", "#d7a6ff"];
const BAND: Record<string, string> = {
  alta: "ALTA",
  moderada: "MODERADA",
  contida: "CONTIDA",
  vazia: "VAZIA",
};

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

function chainMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export function Reino() {
  const [speeches, setSpeeches] = useState<Record<string, Speech | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ActorId | null>(null);
  const [shown, setShown] = useState("");
  const [seal, setSeal] = useState<string | null>(null);
  const [sealHref, setSealHref] = useState<string | null>(null);
  const [sealing, setSealing] = useState(false);

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

  const speech = selected ? speeches[selected] : null;
  const speechError = selected ? errors[selected] : null;
  const fullText = loading
    ? "O arauto abre o pergaminho do conselho."
    : speechError || speech?.fala || "Este lugar está em silêncio.";

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setShown(fullText);
      return;
    }
    setShown("");
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setShown(fullText.slice(0, index));
      if (index >= fullText.length) window.clearInterval(timer);
    }, 16);
    return () => window.clearInterval(timer);
  }, [fullText, selected]);

  const orders = speeches.cio?.dados.ordens ?? [];
  const book = speeches.cio?.dados.carteira ?? [];
  const concentration = speeches.cco?.dados.concentracao ?? speeches.cio?.dados.concentracao;
  const offline = !loading && ROUTES.every((route) => errors[route.key]);
  const lines = [
    speeches.ceo?.fala,
    speeches.cio?.fala,
    speeches.cco?.fala,
  ].filter((line): line is string => Boolean(line));

  async function forge(solanaKey: string | null, baseAddress: string | null, blockhash: string | null) {
    const response = await fetch("/api/backend/transacao-nao-assinada", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        pagador_solana: solanaKey,
        pagador_base: baseAddress,
        blockhash,
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(errorMessage(payload, "Não foi possível empacotar a missão."));
    }
    return payload as Bundle;
  }

  async function acceptMission() {
    setSealing(true);
    setSeal(null);
    setSealHref(null);
    try {
      const solana = phantomSolana();
      if (solana) {
        const connected = await solana.connect();
        const payer = connected.publicKey.toString();
        const { Connection, Transaction } = await import("@solana/web3.js");
        const connection = new Connection(SOLANA_RPC, "confirmed");
        const latest = await connection.getLatestBlockhash("confirmed");
        const bundle = await forge(payer, null, latest.blockhash);
        if (!bundle.solana || bundle.move_tokens) {
          throw new Error("A carga não é o selo esperado.");
        }
        const bytes = Uint8Array.from(atob(bundle.solana.serialized_base64), (char) => char.charCodeAt(0));
        const signed = await solana.signTransaction(Transaction.from(bytes));
        const signature = await connection.sendRawTransaction(signed.serialize(), {
          skipPreflight: false,
          maxRetries: 3,
        });
        setSeal("A rede recebeu o selo. Aguardando a confirmação.");
        setSealHref(`https://solscan.io/tx/${signature}`);
        try {
          await connection.confirmTransaction(
            {
              signature,
              blockhash: latest.blockhash,
              lastValidBlockHeight: latest.lastValidBlockHeight,
            },
            "confirmed",
          );
          setSeal("Selo gravado na Solana. A crônica está na rede e o saldo dos ativos não se moveu.");
        } catch {
          setSeal("A Phantom assinou e a rede recebeu o selo. A confirmação ainda não voltou.");
        }
        return;
      }

      const evm = phantomEthereum();
      if (evm) {
        const accounts = (await evm.request({ method: "eth_requestAccounts" })) as string[];
        const payer = accounts[0];
        try {
          await evm.request({
            method: "wallet_switchEthereumChain",
            params: [{ chainId: "0x2105" }],
          });
        } catch (error) {
          const code = (error as { code?: number }).code;
          if (code === 4902) {
            await evm.request({
              method: "wallet_addEthereumChain",
              params: [
                {
                  chainId: "0x2105",
                  chainName: "Base",
                  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
                  rpcUrls: ["https://mainnet.base.org"],
                  blockExplorerUrls: ["https://basescan.org"],
                },
              ],
            });
          } else {
            throw error;
          }
        }
        const bundle = await forge(null, payer, null);
        if (!bundle.base || bundle.move_tokens) {
          throw new Error("A carga não é o selo esperado.");
        }
        const tx = Object.fromEntries(
          Object.entries(bundle.base.transacao).filter(([key]) => key !== "nonce"),
        );
        const hash = (await evm.request({
          method: "eth_sendTransaction",
          params: [{ ...tx, from: payer }],
        })) as string;
        setSeal("Selo gravado na Base. A crônica está na rede e o saldo dos ativos não se moveu.");
        setSealHref(`https://basescan.org/tx/${hash}`);
        return;
      }

      setSeal("A Phantom não está neste navegador. O selo fica na mesa para revisão e não vai à rede.");
    } catch (error) {
      setSeal(chainMessage(error, "A Phantom recusou o selo da missão."));
    } finally {
      setSealing(false);
    }
  }

  const maxWeight = Math.max(...book.map((item) => item.peso), 0.01);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-3 py-4 sm:px-5 sm:py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] text-[#f2e27a]">NEURO-QUEST CAPITAL</p>
          <h1 className="mt-2 text-sm text-[#f4f7ef] sm:text-base">SALA DO TRONO</h1>
        </div>
        <Link href="/" className="pixel-btn inline-flex items-center px-3 py-2 text-[10px] no-underline">
          MESA
        </Link>
      </header>

      {offline ? (
        <div role="alert" className="pixel-panel flex flex-col gap-3 px-3 py-3 text-[10px] leading-relaxed sm:flex-row sm:items-center sm:justify-between">
          <p>O conselho não alcançou a API.</p>
          <button type="button" className="pixel-btn px-3 py-2 text-[10px]" onClick={() => void load()}>
            TENTAR DE NOVO
          </button>
        </div>
      ) : null}

      <div className="relative">
        <div className="mb-3 lg:absolute lg:top-3 lg:left-3 lg:z-30 lg:mb-0 lg:w-56">
          <section className="border-[3px] border-[#8ea0b8] bg-[#10141c] text-[#9dff7a] shadow-[4px_4px_0_#0c1018]" aria-label="Terminal do reino">
            <header className="flex items-center justify-between border-b border-[#8ea0b8] bg-[#c5d0de] px-2 py-1 text-[8px] text-[#1a120e]">
              <span>TERMINAL</span>
              <span aria-hidden="true">□</span>
            </header>
            <div className="space-y-2 px-2 py-2 text-[8px] leading-relaxed" aria-live="polite">
              {loading ? <p>Arauto: buscando o conselho...</p> : null}
              {!loading && lines.length === 0 ? <p>Arauto: o pergaminho ainda está em branco.</p> : null}
              {lines.slice(0, 3).map((line) => (
                <p key={line.slice(0, 24)}>{line.length > 90 ? `${line.slice(0, 90)}...` : line}</p>
              ))}
            </div>
          </section>
        </div>

        <SalaDoTrono paused={selected !== null} selected={selected} onSelect={setSelected} />

        <div className="mt-3 lg:absolute lg:bottom-3 lg:left-3 lg:z-30 lg:mt-0 lg:w-56">
          <section className="border-[3px] border-[#8ea0b8] bg-[#10141c] text-[#9dff7a] shadow-[4px_4px_0_#0c1018]" aria-label="Tabuleiro do reino">
            <header className="flex items-center justify-between border-b border-[#8ea0b8] bg-[#c5d0de] px-2 py-1 text-[8px] text-[#1a120e]">
              <span>TABULEIRO DO REINO</span>
              <span aria-hidden="true">□</span>
            </header>
            <div className="px-2 py-2">
              <div className="flex h-10 items-end gap-1" aria-hidden="true">
                {(book.length > 0 ? book : [{ simbolo: "—", peso: 0.2 }]).map((item, index) => (
                  <div
                    key={item.simbolo}
                    className="w-full"
                    style={{
                      height: `${Math.max(8, (item.peso / maxWeight) * 100)}%`,
                      background: BAR_COLORS[index % BAR_COLORS.length],
                    }}
                  />
                ))}
              </div>
              <p className="mt-2 text-[8px] leading-relaxed">
                {concentration?.band
                  ? `FAIXA ${BAND[concentration.band] ?? concentration.band.toUpperCase()}`
                  : "FAIXA —"}
                {typeof concentration?.hhi === "number" ? ` · HHI ${concentration.hhi.toFixed(2)}` : ""}
              </p>
              <p className="text-[8px]">
                LASTRO {loading ? "..." : usd.format(speeches.ceo?.dados.total_usd ?? 0)}
              </p>
            </div>
          </section>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {ROUTES.map((route) => (
          <button
            key={route.key}
            type="button"
            className="pixel-btn px-3 py-2 text-[10px]"
            aria-pressed={selected === route.key}
            onClick={() => setSelected(route.key)}
          >
            {route.key === "ceo" ? "REGENTE" : route.key === "cio" ? "MISSÕES" : "FOSSO"}
          </button>
        ))}
      </div>

      {selected ? (
        <section className="pixel-panel relative px-3 pt-4 pb-3" aria-live="polite">
          <button
            type="button"
            className="absolute top-1 right-2 text-[10px] text-[#b6ff8a]"
            onClick={() => setSelected(null)}
            aria-label="Fechar diálogo"
          >
            X
          </button>
          <p className="text-[10px] text-[#f2e27a]">{speech?.cargo ?? "CONSELHO"}</p>
          <h2 className="mt-2 text-xs text-[#f4f7ef]">{speech?.agente ?? "Em silêncio"}</h2>
          <p className="mt-3 max-h-40 overflow-y-auto text-[10px] leading-5 text-[#d8ffc4]">{shown}</p>
          {speech?.aviso ? <p className="mt-2 text-[8px] text-[#f2e27a]">{speech.aviso}</p> : null}

          {selected === "cio" ? (
            <div className="mt-4 border-t-2 border-[#1f5c32] pt-3">
              <h3 className="text-[10px] text-[#f2e27a]">PORTFÓLIO PROPOSTO</h3>
              {book.length === 0 ? (
                <p className="mt-3 text-[10px] leading-5">
                  Nenhuma posição para medir. Lance um ativo na mesa e o CIO desenha as barras.
                </p>
              ) : (
                <div className="mt-3 flex h-28 items-end gap-2" aria-label="Barras do portfólio">
                  {book.map((item, index) => (
                    <div key={item.simbolo} className="flex h-full min-w-0 flex-1 flex-col justify-end gap-1">
                      <div
                        className="w-full"
                        style={{
                          height: `${Math.max(12, (item.peso / maxWeight) * 100)}%`,
                          background: BAR_COLORS[index % BAR_COLORS.length],
                          boxShadow: "2px 0 0 #06140c",
                        }}
                      />
                      <span className="truncate text-center text-[8px]">{item.simbolo}</span>
                    </div>
                  ))}
                </div>
              )}
              {orders.length > 0 ? (
                <ul className="mt-3 grid gap-1 text-[8px] leading-4 sm:grid-cols-2">
                  {orders.map((order) => (
                    <li key={`${order.tipo}-${order.simbolo}-${order.simbolo_par}`}>
                      {order.tipo.toUpperCase()} {order.simbolo}
                      {order.simbolo_par ? `/${order.simbolo_par}` : ""} · {order.quantidade}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-[10px]">Sem ordens enquanto a carteira estiver vazia.</p>
              )}
              <p className="mt-3 text-[8px] leading-4 text-[#d8ffc4]">
                Aceitar grava um selo na rede: memos na Solana, ou uma chamada a si mesmo na Base, com valor zero.
                Não move saldo de ativo. A taxa da rede sai da sua carteira.
              </p>
              <button
                type="button"
                className="pixel-btn mt-3 w-full px-3 py-3 text-[10px] sm:w-auto"
                disabled={sealing || loading || orders.length === 0}
                onClick={() => void acceptMission()}
              >
                {sealing ? "GRAVANDO O SELO..." : "[ ACEITAR MISSÃO ]"}
              </button>
              {seal ? (
                <p role="status" className="mt-3 text-[10px] leading-5">
                  {seal}{" "}
                  {sealHref ? (
                    <a className="text-[#f2e27a] underline" href={sealHref} target="_blank" rel="noreferrer">
                      Ver na rede
                    </a>
                  ) : null}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : (
        <p className="text-[10px] leading-5 text-[#c5d0c0]">
          Clique num conselheiro. O regente ocupa o trono, o mestre lê as missões, a vigia mede o fosso. Eles andam,
          digitam e atendem o telefone entre uma fala e outra.
        </p>
      )}
    </div>
  );
}
