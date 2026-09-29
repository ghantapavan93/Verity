"use client";

import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import type { Stage } from "../shell/constants";

/** Whole-window drag and drop of a contract while the landing is on screen. */
export function useDropZone(active: boolean, setStage: Dispatch<SetStateAction<Stage>>, loadFile: (file: File) => void) {
  const dragDepth = useRef(0);

  useEffect(() => {
    if (!active) return;
    const hasFiles = (event: DragEvent) => event.dataTransfer?.types.includes("Files") ?? false;
    const onEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      dragDepth.current += 1;
      setStage((s) => (s === "empty" ? "dragging" : s));
    };
    const onOver = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault();
    };
    const onLeave = () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setStage((s) => (s === "dragging" ? "empty" : s));
    };
    const onDrop = (event: DragEvent) => {
      event.preventDefault();
      dragDepth.current = 0;
      const dropped = event.dataTransfer?.files?.[0];
      if (dropped) loadFile(dropped);
      else setStage("empty");
    };
    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover", onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [active, setStage, loadFile]);
}
