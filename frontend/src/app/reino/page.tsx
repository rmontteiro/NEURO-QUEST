import type { Metadata } from "next";
import { Reino } from "@/components/reino";

export const metadata: Metadata = {
  title: "Neuro-Quest Capital — assessoria",
  description: "Leitura da carteira, propostas e risco, com assinatura na sua carteira.",
};

export default function ReinoPage() {
  return <Reino />;
}
