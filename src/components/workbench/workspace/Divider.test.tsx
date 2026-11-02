import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Divider } from "./Divider";
import { DEFAULT_DOC_WIDTH, MAX_DOC_WIDTH, MIN_DOC_WIDTH } from "../hooks/useDocWidth";

afterEach(cleanup);

it("resizes without scrolling the page and supports both keyboard bounds", () => {
  let width = DEFAULT_DOC_WIDTH;
  const setWidth = vi.fn((next) => {
    width = typeof next === "function" ? next(width) : next;
  });
  render(<Divider docWidth={width} setDocWidth={setWidth} onPointerDown={vi.fn()} />);
  const divider = screen.getByRole("separator");
  for (const key of ["ArrowLeft", "ArrowRight", "Home", "End"]) {
    expect(fireEvent.keyDown(divider, { key, cancelable: true })).toBe(false);
  }
  expect(width).toBe(MAX_DOC_WIDTH);
  fireEvent.keyDown(divider, { key: "Home" });
  expect(width).toBe(MIN_DOC_WIDTH);
  fireEvent.doubleClick(divider);
  expect(width).toBe(DEFAULT_DOC_WIDTH);
});
