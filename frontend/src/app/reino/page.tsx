import type { Metadata } from "next";
import { Reino } from "@/components/reino";

export const metadata: Metadata = {
  title: "Neuro-Quest Capital — crônica do reino",
  description: "Conselho do reino: regente, missões e risco, com transação não assinada para a Phantom.",
};

export default function ReinoPage() {
  return <Reino />;
}
