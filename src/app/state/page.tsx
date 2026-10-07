import type { Metadata } from "next";
import { StateStory } from "@/components/story/StateStory";

export const metadata: Metadata = {
  title: "One contract changes · Verity",
  description:
    "A recorded experiment on real SEC exhibits: what one arriving contract changes in derived contract state, what it provably does not, and the evidence for each.",
};

export default function StatePage() {
  return <StateStory />;
}
