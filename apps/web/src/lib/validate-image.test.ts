import { describe, it, expect } from "vitest";
import { validateImageFile, partitionBatch } from "./validate-image";
import { config } from "./config";

const file = (over: Partial<{ name: string; size: number; type: string }> = {}) => ({
  name: "shirt.jpg",
  size: 1024,
  type: "image/jpeg",
  ...over,
});

describe("validateImageFile", () => {
  it("accepts every advertised format", () => {
    for (const type of config.upload.acceptedMimeTypes) {
      expect(validateImageFile(file({ type }))).toBeNull();
    }
  });

  it("refuses an unsupported format with actionable copy", () => {
    const rejection = validateImageFile(file({ type: "image/heic", name: "IMG.heic" }));
    expect(rejection?.code).toBe("UNSUPPORTED_FORMAT");
    // Actionable means it names what to do, not what went wrong.
    expect(rejection?.message).toMatch(/JPEG|PNG|WebP|AVIF/);
  });

  it("refuses an oversized photo and states its actual size", () => {
    const rejection = validateImageFile(file({ size: config.upload.maxBytes + 1 }));
    expect(rejection?.code).toBe("IMAGE_TOO_LARGE");
    expect(rejection?.message).toMatch(/10 MB/);
  });

  it("refuses an empty file", () => {
    expect(validateImageFile(file({ size: 0 }))?.code).toBe("EMPTY_FILE");
  });

  it("accepts a photo exactly at the size limit", () => {
    expect(validateImageFile(file({ size: config.upload.maxBytes }))).toBeNull();
  });
});

describe("partitionBatch", () => {
  it("keeps good photos when one is bad — partial success is success", () => {
    const { accepted, rejected } = partitionBatch([
      file({ name: "a.jpg" }),
      file({ name: "b.heic", type: "image/heic" }),
      file({ name: "c.png", type: "image/png" }),
    ]);

    // USER-FLOWS Flow 1: a failing image costs one card, not the run.
    expect(accepted.map((f) => f.name)).toEqual(["a.jpg", "c.png"]);
    expect(rejected).toHaveLength(1);
    expect(rejected[0]?.file.name).toBe("b.heic");
  });

  it("reports over-count separately rather than silently dropping files", () => {
    const many = Array.from({ length: config.upload.maxImagesPerBatch + 3 }, (_, i) =>
      file({ name: `g${i}.jpg` }),
    );
    const { accepted, overflow } = partitionBatch(many);

    expect(accepted).toHaveLength(config.upload.maxImagesPerBatch);
    // Silently truncating a user's selection is worse than refusing it out loud.
    expect(overflow).toHaveLength(3);
  });

  it("handles an empty selection without throwing", () => {
    const { accepted, rejected, overflow } = partitionBatch([]);
    expect([accepted, rejected, overflow].map((a) => a.length)).toEqual([0, 0, 0]);
  });
});
