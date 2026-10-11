import type { Metadata } from "next";
import { BreakStory } from "@/components/break/BreakStory";

export const metadata: Metadata = {
  title: "Break Verity · Verity",
  description:
    "A recorded failure of contract AI: a real clause quoted word for word, verified, and given to the wrong party. The record behind it, a fix that held on the cases it was built on and missed every unseen one, and a rule's catch and false alarm.",
};

export default function BreakPage() {
  return <BreakStory />;
}
