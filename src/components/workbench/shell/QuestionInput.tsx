"use client";

import { useImperativeHandle, useLayoutEffect, useRef, type ComponentPropsWithRef } from "react";

/** Keeps a controlled question readable as its text or available width changes. */
export function QuestionInput({ ref, value, ...props }: ComponentPropsWithRef<"textarea">) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => inputRef.current!, []);

  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    const fit = () => {
      // Reset before measuring so removing text can shrink the field again.
      input.style.height = "auto";
      input.style.height = `${input.scrollHeight}px`;
    };
    fit();
    if (typeof ResizeObserver === "undefined") return;
    // Only width changes need a second measurement; height changes are our own.
    let width = input.getBoundingClientRect().width;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width === width) return;
      width = entry.contentRect.width;
      fit();
    });
    observer.observe(input);
    return () => observer.disconnect();
  }, [value]);

  return <textarea {...props} ref={inputRef} value={value} />;
}
