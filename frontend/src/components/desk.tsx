"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Analysis, ForecastBook, Position, errorMessage, pct, qty, usd } from "@/lib/types";

const CHAINS = ["ethereum", "solana", "bitcoin", "base", "arbitrum", "polygon", "optimism"];

const ASSET_NAME: Record<string, string> = {
  BTCUSDT: "Bitcoin",
  ETHUSDT: "Ether",
  SOLUSDT: "Solana",
  NASDAQCOM: "Nasdaq Composite",
};

const DIRECTION_LABEL = {
  alta: "Alta",
  baixa: "Baixa",
  lateral: "Lateral",
} as const;

const BAND_LABEL: Record<Analysis["concentration"]["band"], string> = {
  alta: "Concentração alta",
  moderada: "Concentração moderada",
  contida: "Concentração contida",
  vazia: "Sem leitura",
};

type FormState = {
  symbol: string;
  name: string;
  chain: string;
  amount: string;
  price_usd: string;
};

const EMPTY_FORM: FormState = {
  symbol: "",
  name: "",
  chain: "",
  amount: "",
  price_usd: "",
};

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return { detail: text };
  }
}

export function Desk() {
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [total, setTotal] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [forecast, setForecast] = useState<ForecastBook | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [forecastLoading, setForecastLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    setAnalysisError(null);
    try {
      const response = await fetch("/api/backend/positions", { cache: "no-store" });
      const payload = await readJson(response);
      if (!response.ok) {
        setPositions(null);
        setLoadError(errorMessage(payload, "Não foi possível ler a carteira."));
        setAnalysis(null);
        return;
      }
      const body = payload as { positions: Position[]; total_usd: number };
      setPositions(body.positions);
      setTotal(body.total_usd);
      setReading(true);
      const analysisResponse = await fetch("/api/backend/analysis", { method: "POST" });
      const analysisPayload = await readJson(analysisResponse);
      if (!analysisResponse.ok) {
        setAnalysis(null);
        setAnalysisError(errorMessage(analysisPayload, "A leitura de risco não ficou pronta."));
        return;
      }
      setAnalysis(analysisPayload as Analysis);
    } catch {
      setPositions(null);
      setAnalysis(null);
      setLoadError("A mesa perdeu contato com a API neste host.");
    } finally {
      setLoading(false);
      setReading(false);
    }
  }, []);

  const loadForecasts = useCallback(async () => {
    setForecastLoading(true);
    setForecastError(null);
    try {
      const response = await fetch("/api/backend/previsoes", { cache: "no-store" });
      const payload = await readJson(response);
      if (!response.ok) {
        setForecast(null);
        setForecastError(errorMessage(payload, "A previsão diária não chegou."));
        return;
      }
      setForecast(payload as ForecastBook);
    } catch {
      setForecast(null);
      setForecastError("A mesa perdeu contato com a previsão.");
    } finally {
      setForecastLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void reload();
      void loadForecasts();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [reload, loadForecasts]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!(Number(form.amount) > 0) || Number.isNaN(Number(form.price_usd))) {
      setFormError("Informe uma quantidade maior que zero e um preço em USD.");
      return;
    }
    setSaving(true);
    setConfirmClear(false);
    try {
      const response = await fetch("/api/backend/positions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          symbol: form.symbol,
          name: form.name,
          chain: form.chain,
          amount: Number(form.amount),
          price_usd: Number(form.price_usd),
        }),
      });
      const payload = await readJson(response);
      if (!response.ok) {
        setFormError(errorMessage(payload, "Não foi possível lançar a posição."));
        return;
      }
      setForm(EMPTY_FORM);
      await reload();
    } catch {
      setFormError("A API não recebeu o lançamento.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    setConfirmClear(false);
    const response = await fetch(`/api/backend/positions/${id}`, { method: "DELETE" });
    if (!response.ok) {
      const payload = await readJson(response);
      setLoadError(errorMessage(payload, "Não foi possível remover a posição."));
      return;
    }
    await reload();
  }

  async function clearAll() {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    const response = await fetch("/api/backend/positions", { method: "DELETE" });
    if (!response.ok) {
      const payload = await readJson(response);
      setLoadError(errorMessage(payload, "Não foi possível limpar a carteira."));
      return;
    }
    setConfirmClear(false);
    await reload();
  }

  const band = analysis?.concentration.band;
  const online = positions !== null && !loadError;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <header className="flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <p className="font-display text-4xl leading-none tracking-tight text-foreground italic sm:text-5xl">
            Lastro
          </p>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
            Mesa de portfólio Web3. Os preços da carteira são os que você lançou.
            A previsão diária, quando o turno ocioso grava, vem da Binance e do FRED e não altera esses lançamentos.
            A assessoria traduz essa leitura em proposta e risco, sem executar nada sozinha.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/reino" className={buttonVariants({ variant: "outline" })}>
            Abrir a assessoria
          </Link>
          <Badge variant={online ? "secondary" : "destructive"}>
            {loading ? "Consultando a carteira" : online ? "Carteira no ar" : "Carteira indisponível"}
          </Badge>
        </div>
      </header>

      <section className="grid gap-3 sm:grid-cols-3" aria-label="Resumo">
        <Card size="sm">
          <CardHeader>
            <CardDescription>Valor lançado</CardDescription>
            <CardTitle className="font-mono text-2xl tabular-nums">
              {loading || positions === null ? "—" : usd.format(total)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Posições</CardDescription>
            <CardTitle className="font-mono text-2xl tabular-nums">
              {positions === null ? "—" : positions.length}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Leitura</CardDescription>
            <CardTitle className="text-2xl">{band ? BAND_LABEL[band] : reading ? "Lendo…" : "—"}</CardTitle>
          </CardHeader>
        </Card>
      </section>

      <section className="flex flex-col gap-3" aria-label="Previsão diária">
        <div className="space-y-1">
          <h2 className="font-display text-2xl italic tracking-tight">Previsão do turno ocioso</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Direção para o pregão seguinte, com stop e alvo. É um estudo estatístico: não é ordem e não move saldo.
          </p>
        </div>

        {forecastLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-live="polite">
            <div className="h-28 animate-pulse rounded-xl bg-muted" />
            <div className="h-28 animate-pulse rounded-xl bg-muted" />
            <div className="hidden h-28 animate-pulse rounded-xl bg-muted sm:block" />
            <div className="hidden h-28 animate-pulse rounded-xl bg-muted xl:block" />
            <p className="text-sm text-muted-foreground sm:col-span-2 xl:col-span-4">Lendo a última previsão…</p>
          </div>
        ) : null}

        {forecastError ? (
          <div
            role="alert"
            className="flex flex-col gap-3 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
          >
            <p>{forecastError}</p>
            <Button type="button" variant="outline" onClick={() => void loadForecasts()}>
              Tentar de novo
            </Button>
          </div>
        ) : null}

        {!forecastLoading && !forecastError && forecast?.status === "erro" ? (
          <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
            {forecast.erro || "O turno ocioso não conseguiu gravar a previsão."}
          </div>
        ) : null}

        {!forecastLoading && !forecastError && (forecast?.ativos?.length ?? 0) === 0 && forecast?.status !== "erro" ? (
          <div className="rounded-lg border border-dashed border-border px-4 py-8 text-sm leading-relaxed text-muted-foreground">
            O turno ocioso ainda não gravou uma previsão.
          </div>
        ) : null}

        {(forecast?.ativos?.length ?? 0) > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {forecast?.ativos?.map((asset) => (
              <Card key={asset.ativo} size="sm">
                <CardHeader>
                  <CardDescription>
                    {asset.classe === "indice_acao" ? "Índice" : "Cripto"} · {asset.horizonte ?? "1d"}
                  </CardDescription>
                  <CardTitle className="flex items-center justify-between gap-2 text-xl">
                    <span>{ASSET_NAME[asset.ativo] ?? asset.ativo}</span>
                    <Badge
                      variant={
                        asset.direcao === "baixa" ? "destructive" : asset.direcao === "alta" ? "default" : "outline"
                      }
                    >
                      {DIRECTION_LABEL[asset.direcao] ?? asset.direcao}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                  <div>
                    <p className="text-muted-foreground">Confiança</p>
                    <p className="font-mono tabular-nums">{pct.format(asset.confianca)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Referência</p>
                    <p className="font-mono tabular-nums">{usd.format(asset.preco_referencia)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Stop</p>
                    <p className="font-mono tabular-nums">{usd.format(asset.stop_loss)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Alvo</p>
                    <p className="font-mono tabular-nums">{usd.format(asset.take_profit)}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}

        {forecast?.nota_ouro ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{forecast.nota_ouro}</p>
        ) : null}
        {forecast?.gerado_em ? (
          <p className="text-xs text-muted-foreground">Gerada em {forecast.gerado_em}.</p>
        ) : null}
      </section>

      {loadError ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
        >
          <p>{loadError}</p>
          <Button type="button" variant="outline" onClick={() => void reload()}>
            Tentar de novo
          </Button>
        </div>
      ) : null}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(18rem,0.85fr)]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Posições</CardTitle>
              <CardDescription>
                Cada linha é um lançamento manual: ativo, rede, quantidade e preço em dólar.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {loading && positions === null ? (
                <div className="space-y-2" aria-busy="true" aria-live="polite">
                  <div className="h-14 animate-pulse rounded-lg bg-muted" />
                  <div className="h-14 animate-pulse rounded-lg bg-muted" />
                  <div className="h-14 animate-pulse rounded-lg bg-muted" />
                  <p className="text-sm text-muted-foreground">Abrindo a carteira…</p>
                </div>
              ) : null}

              {positions && positions.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border px-4 py-8 text-sm leading-relaxed text-muted-foreground">
                  Nenhuma posição lançada. Use o formulário abaixo para registrar o primeiro ativo.
                  A carteira de exemplo só aparece num banco novo; depois de limpar, a mesa fica vazia de propósito.
                </div>
              ) : null}

              {positions && positions.length > 0 ? (
                <ul className="divide-y divide-border">
                  {positions.map((position) => {
                    const value = position.amount * position.price_usd;
                    const weight = total > 0 ? value / total : 0;
                    return (
                      <li
                        key={position.id}
                        className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                            <span className="font-mono text-base font-medium">{position.symbol}</span>
                            <span className="truncate text-sm text-muted-foreground">{position.name}</span>
                            <Badge variant="outline">{position.chain}</Badge>
                          </div>
                          <p className="mt-1 font-mono text-xs text-muted-foreground tabular-nums">
                            {qty.format(position.amount)} × {usd.format(position.price_usd)}
                          </p>
                        </div>
                        <div className="flex items-center justify-between gap-4 sm:justify-end">
                          <div className="text-right">
                            <p className="font-mono text-sm tabular-nums">{usd.format(value)}</p>
                            <p className="font-mono text-xs text-muted-foreground tabular-nums">{pct.format(weight)}</p>
                          </div>
                          <Button type="button" variant="ghost" size="sm" onClick={() => void remove(position.id)}>
                            Remover
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              ) : null}

              {positions && positions.length > 0 ? (
                <div className="flex justify-end">
                  <Button type="button" variant={confirmClear ? "destructive" : "outline"} onClick={() => void clearAll()}>
                    {confirmClear ? "Confirmar limpeza da carteira" : "Limpar carteira"}
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Lançar posição</CardTitle>
              <CardDescription>O símbolo aceita letras e números. A rede fica em minúsculas.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => void onSubmit(event)}>
                <div className="grid gap-2">
                  <Label htmlFor="symbol">Símbolo</Label>
                  <Input
                    id="symbol"
                    name="symbol"
                    autoComplete="off"
                    maxLength={12}
                    required
                    value={form.symbol}
                    onChange={(event) => setForm((current) => ({ ...current, symbol: event.target.value }))}
                    placeholder="ETH"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="name">Nome</Label>
                  <Input
                    id="name"
                    name="name"
                    autoComplete="off"
                    maxLength={64}
                    required
                    value={form.name}
                    onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Ether"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="chain">Rede</Label>
                  <Input
                    id="chain"
                    name="chain"
                    list="chains"
                    autoComplete="off"
                    maxLength={32}
                    required
                    placeholder="ethereum"
                    value={form.chain}
                    onChange={(event) => setForm((current) => ({ ...current, chain: event.target.value }))}
                  />
                  <datalist id="chains">
                    {CHAINS.map((chain) => (
                      <option key={chain} value={chain} />
                    ))}
                  </datalist>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="amount">Quantidade</Label>
                  <Input
                    id="amount"
                    name="amount"
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    required
                    value={form.amount}
                    onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))}
                    placeholder="0,00"
                  />
                </div>
                <div className="grid gap-2 sm:col-span-2">
                  <Label htmlFor="price">Preço em USD</Label>
                  <Input
                    id="price"
                    name="price_usd"
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    required
                    value={form.price_usd}
                    onChange={(event) => setForm((current) => ({ ...current, price_usd: event.target.value }))}
                    placeholder="0,00"
                  />
                </div>
                {formError ? (
                  <p role="alert" className="text-sm text-destructive sm:col-span-2">
                    {formError}
                  </p>
                ) : null}
                <div className="sm:col-span-2">
                  <Button type="submit" disabled={saving || loading}>
                    {saving ? "Lançando…" : "Adicionar à carteira"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Leitura de risco</CardTitle>
            <CardDescription>
              HHI, ativos efetivos e peso por rede. O cálculo usa NumPy e pandas dentro do contêiner limitado.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {reading ? <p className="text-sm text-muted-foreground">Lendo a carteira no motor…</p> : null}
            {analysisError ? (
              <div role="alert" className="space-y-3 text-sm">
                <p>{analysisError}</p>
                <Button type="button" variant="outline" onClick={() => void reload()}>
                  Repetir leitura
                </Button>
              </div>
            ) : null}
            {analysis ? (
              <>
                <dl className="grid grid-cols-2 gap-3">
                  <div>
                    <dt className="text-xs text-muted-foreground">HHI</dt>
                    <dd className="font-mono text-lg tabular-nums">{analysis.concentration.hhi.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Ativos efetivos</dt>
                    <dd className="font-mono text-lg tabular-nums">
                      {analysis.concentration.effective_assets.toFixed(1)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Maior peso</dt>
                    <dd className="font-mono text-lg tabular-nums">
                      {analysis.concentration.top_symbol
                        ? `${analysis.concentration.top_symbol} ${pct.format(analysis.concentration.top_weight)}`
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Caixa estável</dt>
                    <dd className="font-mono text-lg tabular-nums">{pct.format(analysis.concentration.stable_weight)}</dd>
                  </div>
                </dl>

                {analysis.holdings.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs tracking-wide text-muted-foreground uppercase">Peso por ativo</p>
                    <ul className="space-y-2">
                      {analysis.holdings.map((holding) => (
                        <li key={`${holding.symbol}-${holding.chain}`}>
                          <div className="mb-1 flex justify-between gap-3 font-mono text-xs">
                            <span>{holding.symbol}</span>
                            <span className="tabular-nums">{pct.format(holding.weight)}</span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${Math.max(2, holding.weight * 100)}%` }}
                            />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {analysis.chains.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs tracking-wide text-muted-foreground uppercase">Peso por rede</p>
                    <ul className="space-y-1 text-sm">
                      {analysis.chains.map((chain) => (
                        <li key={chain.chain} className="flex justify-between gap-3 font-mono">
                          <span>{chain.chain}</span>
                          <span className="tabular-nums">{pct.format(chain.weight)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <ul className="space-y-3 text-sm leading-relaxed text-muted-foreground">
                  {analysis.notes.map((note) => (
                    <li key={note} className="border-l-2 border-primary/70 pl-3">
                      {note}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {!analysis && !analysisError && !reading && !loading ? (
              <p className="text-sm text-muted-foreground">A leitura aparece quando a carteira responde.</p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
