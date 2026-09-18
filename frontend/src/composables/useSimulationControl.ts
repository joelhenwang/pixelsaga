// Simulation playback controller (P06).
//
// One controller, one phase at a time. Slow/Normal/Fast change dwell
// time only, never rules. Pause means finish the current phase, then
// stop before the next. Reloads reconcile through the status endpoint
// and never silently resume autoplay.
import { ref } from "vue";
import { api } from "../api";
import { advance, busy, fail, headers, session, worldId } from "../store";

export type ControlState = "idle" | "resolving" | "pause-requested" | "paused" | "failed" | "ended";
export type Pace = "slow" | "normal" | "fast";

const DWELL: Record<Pace, number> = { slow: 3000, normal: 1500, fast: 500 };

export const controlState = ref<ControlState>("idle");
export const pace = ref<Pace>("normal");
export const controlNotice = ref<string>("");

let playToken = 0;

export type PhaseOutcome = "continue" | "pause" | "end";

export async function nextPhase(onResolve: (runId: string) => Promise<PhaseOutcome>): Promise<void> {
  if (controlState.value === "resolving" || busy.value) {
    return;
  }
  controlState.value = "resolving";
  controlNotice.value = "";
  const key = session();
  const world = worldId.value;
  try {
    const runId = await advance();
    if (!runId || key !== session() || worldId.value !== world) {
      // Story switched mid-phase: the server run may finish, but this
      // controller resolves nothing into the new story.
      if (key !== session() || worldId.value !== world) {
        controlState.value = "idle";
        return;
      }
      controlState.value = "failed";
      controlNotice.value = "advance produced no run; see notice";
      return;
    }
    const outcome = await onResolve(runId);
    if (key !== session() || worldId.value !== world) {
      controlState.value = "idle";
      return;
    }
    controlState.value = outcome === "continue" ? "idle" : outcome === "pause" ? "paused" : "ended";
  } catch (error) {
    if (key !== session() || worldId.value !== world) {
      controlState.value = "idle";
      return;
    }
    fail("controlled advance failed", error);
    controlState.value = "failed";
  }
}

export async function play(onResolve: (runId: string) => Promise<PhaseOutcome>): Promise<void> {
  const token = ++playToken;
  const key = session();
  while (token === playToken && key === session()) {
    if (controlState.value === "pause-requested") {
      controlState.value = "paused";
      return;
    }
    if (document.hidden) {
      controlState.value = "paused";
      controlNotice.value = "paused while hidden; resume explicitly";
      return;
    }
    await nextPhase(onResolve);
    if (token !== playToken || controlState.value !== "idle") {
      return;
    }
    const dwell = Promise.withResolvers<void>();
    setTimeout(dwell.resolve, DWELL[pace.value]);
    await dwell.promise;
  }
}

export function pause(): void {
  playToken += 1;
  controlState.value = controlState.value === "resolving" ? "pause-requested" : "paused";
}

export function resetControl(): void {
  playToken += 1;
  controlState.value = "idle";
  controlNotice.value = "";
}

export async function reconcile(): Promise<void> {
  // Reload-safe: report an open run, stay paused, never auto-resume.
  if (!worldId.value) {
    return;
  }
  try {
    const status = await api.simulationStatus(worldId.value, headers.value);
    if (status.open_run_id) {
      controlState.value = "paused";
      controlNotice.value = `run ${status.open_run_id.slice(0, 8)} is ${status.open_run_state}; resume explicitly`;
    }
  } catch (error) {
    fail("status reconcile failed", error);
  }
}

document.addEventListener("visibilitychange", () => {
  if (
    document.hidden &&
    (controlState.value === "idle" || controlState.value === "resolving")
  ) {
    pause();
    controlNotice.value = "paused while hidden; resume explicitly";
  }
});
