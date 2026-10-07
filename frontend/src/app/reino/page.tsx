import type { Metadata } from "next";
import { Reino } from "@/components/reino";

export const metadata: Metadata = {
  title: "Neuro-Quest Capital — crônica do reino",
  description: "Sala do Trono em 16 bits: três conselheiros, missões em barras e selo assinado na Phantom.",
};

export default function ReinoPage() {
  return <Reino />;
}
