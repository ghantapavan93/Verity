import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { BreakStory } from "@/components/break/BreakStory";
import raw from "@/components/break/break-record.json";
import { forPage, type BreakRecord } from "@/components/break/record";

export const metadata: Metadata = {
  title: "Break Verity · Verity",
  description:
    "A recorded failure of contract AI: a real clause quoted word for word, verified, and given to the wrong party. The record behind it, a fix that held on the cases it was built on and missed every unseen one, and a rule's catch and false alarm.",
};

export default function BreakPage() {
  // The static mirror (NEXT_PUBLIC_EXPORT=state) carries this page too: it needs no API, store or model, so it stays
  // readable when the live workbench is down. It is published only with the address of the workbench it links to.
  if (process.env.NEXT_PUBLIC_EXPORT === "state" && !process.env.NEXT_PUBLIC_WORKBENCH_URL) notFound();
  // Trimmed here, on the server: the browser receives what the page renders, not the whole record.
  return <BreakStory record={forPage(raw as unknown as BreakRecord)} />;
}
