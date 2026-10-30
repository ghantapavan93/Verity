import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import { connection } from "next/server";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const sourceSerif = Source_Serif_4({ subsets: ["latin"], variable: "--font-source-serif", display: "swap", style: ["normal", "italic"] });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap", weight: ["400", "500"] });

// What a link preview shows. The product opens on the workbench (the research is at /state); the public artifact
// (NEXT_PUBLIC_EXPORT=state) opens on the recorded experiment and has no workbench to describe.
const PUBLIC_STATE = process.env.NEXT_PUBLIC_EXPORT === "state";
const TITLE = PUBLIC_STATE ? "Verity · One contract changes: what doesn't need to move?" : "Verity · Contract AI, under test";
const DESCRIPTION = PUBLIC_STATE
  ? "A recorded experiment on real SEC exhibits: what one arriving contract changes in derived contract state, what it provably does not, and the evidence for each."
  : "A contract AI can quote the right passage and still reach the wrong conclusion. Verity locates every passage the model quotes, records each run so it can be replayed, and says what code did not check. With one recorded wrong-party answer, and research on contract-derived state.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  openGraph: { title: TITLE, description: DESCRIPTION, siteName: "Verity", type: "website" },
  twitter: { card: "summary", title: TITLE, description: DESCRIPTION },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Every page is rendered per request, so Next can put the response's script nonce (src/proxy.ts, lib/csp) on its own
  // scripts: a page built ahead of time carries none, and the policy would refuse its scripts. The static /state export
  // has no server, so no request and no proxy; it is built ahead of time as before (K64, 2026-10-30).
  if (!PUBLIC_STATE) await connection();
  return (
    <html lang="en" className={`${inter.variable} ${sourceSerif.variable} ${jetbrains.variable}`}>
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
