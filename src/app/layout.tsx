import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const sourceSerif = Source_Serif_4({ subsets: ["latin"], variable: "--font-source-serif", display: "swap", style: ["normal", "italic"] });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap", weight: ["400", "500"] });

// What a link preview shows. The product opens on the workbench (the research is at /state); the public artifact
// (NEXT_PUBLIC_EXPORT=state) opens on the recorded experiment and has no workbench to describe.
const PUBLIC_STATE = process.env.NEXT_PUBLIC_EXPORT === "state";
const TITLE = PUBLIC_STATE ? "Verity · One contract changes: what doesn't need to move?" : "Verity · Contract workbench and Contract State research";
const DESCRIPTION = PUBLIC_STATE
  ? "A recorded experiment on real SEC exhibits: what one arriving contract changes in derived contract state, what it provably does not, and the evidence for each."
  : "Upload a contract, ask a question, and open the passage each answer cites; the workbench checks every passage the model quotes against the document. With a recorded experiment on what one arriving contract changes.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  openGraph: { title: TITLE, description: DESCRIPTION, siteName: "Verity", type: "website" },
  twitter: { card: "summary", title: TITLE, description: DESCRIPTION },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
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
