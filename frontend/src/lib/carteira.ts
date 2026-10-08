import { errorMessage } from "@/lib/types";

export type SyncResult = {
  atualizado: boolean;
  aviso: string | null;
  solana?: string | null;
};

export async function sincronizarCarteira(solana?: string | null): Promise<SyncResult> {
  const response = await fetch("/api/backend/carteira/sincronizar", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(solana ? { solana } : {}),
  });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    return { atualizado: false, aviso: errorMessage(payload, "A leitura da Phantom não ficou pronta.") };
  }
  const body = (payload ?? {}) as { atualizado?: boolean; aviso?: string | null; solana?: string | null };
  return {
    atualizado: Boolean(body.atualizado),
    aviso: body.aviso ?? null,
    solana: body.solana,
  };
}
