import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("supports accessible names and disabled state", () => {
    render(<Button disabled>Save customer</Button>);
    expect(screen.getByRole("button", { name: "Save customer" })).toBeDisabled();
  });
});
