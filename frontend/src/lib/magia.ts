export const FALHA_FUNDOS =
  "A magia falhou, aventureiro! O alforje não tem o ouro desta travessia.";
export const FALHA_SLIPPAGE =
  "A magia falhou, aventureiro! O preço escorregou além do limite de 1%.";
export const FALHA_RECUSA =
  "A magia falhou, aventureiro! Tu recusaste o selo no limiar da Phantom.";
export const FALHA_ROTA =
  "A magia falhou, aventureiro! A rota se desfez antes do círculo.";

function texto(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return "";
}

function codigo(error: unknown): number | undefined {
  if (!error || typeof error !== "object" || !("code" in error)) return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === "number" ? code : undefined;
}

export function magiaFalhou(error: unknown): string {
  const message = texto(error);
  if (message.startsWith("A magia falhou, aventureiro!")) return message;
  const blob = message.toLowerCase();
  const code = codigo(error);
  if (code === 4001 || /user rejected|rejected the request|recus|denied/.test(blob)) {
    return FALHA_RECUSA;
  }
  if (/insufficient|lamport/.test(blob)) return FALHA_FUNDOS;
  if (/slippage|0x1771|0x1781|amount out/.test(blob)) return FALHA_SLIPPAGE;
  return FALHA_ROTA;
}

export function metodoAusente(error: unknown): boolean {
  const code = codigo(error);
  const blob = texto(error).toLowerCase();
  return (
    code === -32601 ||
    code === 4200 ||
    blob.includes("not support") ||
    blob.includes("does not exist") ||
    blob.includes("method not found") ||
    blob.includes("unsupported")
  );
}
