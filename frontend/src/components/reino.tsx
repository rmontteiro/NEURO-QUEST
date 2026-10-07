"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { SalaDoTrono } from "@/components/sala-do-trono";
import { magiaFalhou, metodoAusente } from "@/lib/magia";
import { errorMessage, usd } from "@/lib/types";
import type { ActorId } from "@/lib/rotina";

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

function ListaDoVigia({
  route,
  loading,
  error,
}: {
  route: MissionRoute | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div>
      <h3 className="text-[10px] text-[#f2e27a]">AUDITORIA DO VIGIA</h3>
      {loading ? <p className="mt-3 text-[10px] leading-5">O Vigia mede o fosso antes da Phantom.</p> : null}
      {error ? (
        <p role="alert" className="mt-3 text-[10px] leading-5">
          {error}
        </p>
      ) : null}
      {!loading && !error && route ? (
        <ul className="mt-3 space-y-2 text-[10px] leading-5" aria-label="Lista de validação">
          {route.auditoria.itens.map((item) => (
            <li key={item.rotulo}>{item.rotulo}</li>
          ))}
        </ul>
      ) : null}
      {!loading && !error && !route ? <p className="mt-3 text-[10px]">A auditoria ainda não voltou da mesa.</p> : null}
      {route && route.avisos.length > 0 ? (
        <ul className="mt-3 space-y-1 text-[8px] leading-4 text-[#f2e27a]">
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
  const [selected, setSelected] = useState<ActorId | null>(null);
  const [shown, setShown] = useState("");
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
      throw new Error(errorMessage(payload, "O Vigia não conseguiu auditar a rota."));
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
          setRouteError(error instanceof Error ? error.message : "O Vigia não respondeu.");
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
        setSeal("A Phantom não está neste navegador. A lista do Vigia fica na mesa e nenhuma transação sai.");
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
        setSeal("Esta missão assina na Ethereum. Abre a Phantom nessa rede. Nada foi enviado.");
        return;
      }
      if (fresh.solana && !solanaKey) {
        setSeal("O swap da Jupiter pede a Phantom na Solana. Nada foi enviado.");
        return;
      }
      if (!fresh.auditoria.ok || !fresh.enviar || fresh.custodia) {
        throw new Error("A auditoria do Vigia não liberou o círculo.");
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
          setSeal("A Phantom assinou o lote Solana. A confirmação ainda não voltou.");
          setSealHref(href);
          return;
        }
      }

      setSeal("O círculo fechou. Tu assinaste o swap, o depósito no Aave e a permissão da ordem limitada. A agência não guarda a chave.");
      setSealHref(href);
    } catch (error) {
      setSpell(magiaFalhou(error));
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
              <div className="mt-4">
                <ListaDoVigia route={route} loading={routeLoading} error={routeError} />
              </div>
              <p className="mt-3 text-[8px] leading-4 text-[#d8ffc4]">
                Aceitar move o que tu aprovares: swap na Uniswap, depósito no Aave V3 e a permissão exata da ordem
                limitada. Na Solana, o swap da Jupiter entra na mesma Transaction V0 quando a cotação chega. A agência
                não guarda a chave. A taxa da rede é tua.
              </p>
              <button
                type="button"
                className="pixel-btn mt-3 w-full px-3 py-3 text-[10px] sm:w-auto"
                disabled={sealing || loading || routeLoading || orders.length === 0 || !route?.auditoria.ok}
                onClick={() => void acceptMission()}
              >
                {sealing ? "PEDINDO O SELO..." : "[ ACEITAR MISSÃO ]"}
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

          {selected === "cco" ? (
            <div className="mt-4 border-t-2 border-[#1f5c32] pt-3">
              <ListaDoVigia route={route} loading={routeLoading} error={routeError} />
              <p className="mt-3 text-[8px] leading-4 text-[#d8ffc4]">
                O selo só segue para a Phantom com as três marcas. Slippage acima de 1%, contrato fora da lista ou
                stop ausente deixa o botão quieto.
              </p>
            </div>
          ) : null}
        </section>
      ) : (
        <p className="text-[10px] leading-5 text-[#c5d0c0]">
          Clique num conselheiro. O regente ocupa o trono, o mestre lê as missões, a vigia mede o fosso. Eles andam,
          digitam e atendem o telefone entre uma fala e outra.
        </p>
      )}

      {spell ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#06140c]/80 p-4 sm:items-center">
          <div role="alertdialog" aria-labelledby="magia-titulo" aria-describedby="magia-fala" className="pixel-panel w-full max-w-md px-4 py-4">
            <p id="magia-titulo" className="text-[10px] text-[#f2e27a]">
              O CÍRCULO QUEBROU
            </p>
            <p id="magia-fala" className="mt-3 text-[10px] leading-5">
              {spell}
            </p>
            <button type="button" className="pixel-btn mt-4 px-3 py-2 text-[10px]" onClick={() => setSpell(null)}>
              ENTENDIDO
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
