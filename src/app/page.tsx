import { StateStory } from "@/components/story/StateStory";
import { Workbench } from "@/components/workbench/Workbench";

// The public artifact (NEXT_PUBLIC_EXPORT=state) opens on the recorded experiment; the product opens on the workbench.
const PUBLIC_STATE = process.env.NEXT_PUBLIC_EXPORT === "state";

export default function Page() {
  return PUBLIC_STATE ? <StateStory /> : <Workbench />;
}
