export type Position = {
  id: string;
  symbol: string;
  name: string;
  chain: string;
  amount: number;
  price_usd: number;
  created_at: string;
};

export type Holding = {
  symbol: string;
  name: string;
  chain: string;
  value_usd: number;
  weight: number;
};

export type Analysis = {
  total_usd: number;
  priced_count: number;
  unpriced_count: number;
  holdings: Holding[];
  chains: { chain: string; value_usd: number; weight: number }[];
  concentration: {
    hhi: number;
    effective_assets: number;
    top_weight: number;
    top_symbol: string | null;
    stable_weight: number;
    band: "alta" | "moderada" | "contida" | "vazia";
  };
  notes: string[];
};

export const usd = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "USD",
});

export const qty = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 8,
});

export const pct = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  maximumFractionDigits: 1,
});

export function errorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return fallback;
  }
  const detail = (payload as { detail: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) {
      return first.msg.replace(/^Value error,\s*/i, "");
    }
  }
  return fallback;
}
