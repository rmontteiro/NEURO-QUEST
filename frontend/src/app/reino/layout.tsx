import { Press_Start_2P, Silkscreen } from "next/font/google";

const press = Press_Start_2P({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-press",
  display: "swap",
});

const silk = Silkscreen({
  weight: ["400", "700"],
  subsets: ["latin", "latin-ext"],
  variable: "--font-silk",
  display: "swap",
});

export default function ReinoLayout({ children }: { children: React.ReactNode }) {
  return <div className={`${press.variable} ${silk.variable} pixel-ui`}>{children}</div>;
}
