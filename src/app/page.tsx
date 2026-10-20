"use client";

import dynamic from "next/dynamic";
import { Workbench } from "@/components/workbench/Workbench";

// The public artifact (NEXT_PUBLIC_EXPORT=state) opens on the recorded experiment; the product opens on the workbench.
const PUBLIC_STATE = process.env.NEXT_PUBLIC_EXPORT === "state";

// Its own chunk, sent only where it is shown: imported plainly, the experiment's 39 KB went with every visit to the
// workbench, which never shows it (bundle audit, 2026-10-19). A client page, because a server page's dynamic import
// still sent the chunk; prerendered as before, so the export's page is complete.
const StateStory = dynamic(() => import("@/components/story/StateStory").then((module) => module.StateStory));

export default function Page() {
  return PUBLIC_STATE ? <StateStory /> : <Workbench />;
}
