import { useEffect, useSyncExternalStore } from "react";
import { getWorld, type WorldSnapshot } from "../src/world";

function subscribe(onStoreChange: () => void) {
  return getWorld().on(onStoreChange);
}

function getSnapshot(): WorldSnapshot {
  return getWorld().snapshot();
}

export function useWorld() {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    const world = getWorld();
    world.hydrateMemory();
    const id = window.setInterval(() => {
      if (world.running) world.step();
    }, 125);
    return () => window.clearInterval(id);
  }, []);

  return { snap, world: getWorld() };
}
