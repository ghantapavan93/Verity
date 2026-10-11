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
  // The static /state artifact (NEXT_PUBLIC_EXPORT=state) is the frozen research alone; this page belongs to the workbench.
  if (process.env.NEXT_PUBLIC_EXPORT === "state") notFound();
  // Trimmed here, on the server: the browser receives what the page renders, not the whole record.
  return <BreakStory record={forPage(raw as unknown as BreakRecord)} />;
}
