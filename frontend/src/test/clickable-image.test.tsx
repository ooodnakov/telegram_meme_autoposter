import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ClickableImage from "@/components/ClickableImage";

describe("ClickableImage", () => {
  it("closes the preview when the expanded image is clicked", async () => {
    render(
      <ClickableImage
        src="https://example.com/image.jpg"
        alt="Preview image"
        className="h-full w-full object-cover"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /open image preview/i }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();

    const expandedImage = screen.getByRole("img", { name: "Preview image" });
    expect(expandedImage).toBeInTheDocument();

    fireEvent.click(expandedImage);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
