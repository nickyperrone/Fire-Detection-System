import { describe, expect, it } from "vitest";

import { deviceLabel, urlBase64ToUint8Array } from "./push";

describe("push helpers", () => {
  it("reads the server's key as bytes, with or without padding", () => {
    // 65 bytes, starting with 4: an uncompressed point, as VAPID public keys are.
    const key = btoa(String.fromCharCode(4, ...Array(64).fill(7)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    const bytes = urlBase64ToUint8Array(key);
    expect(bytes.length).toBe(65);
    expect(bytes[0]).toBe(4);
    expect(bytes[64]).toBe(7);
  });

  it("names a device by browser and system", () => {
    expect(
      deviceLabel(
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36",
      ),
    ).toBe("Chrome · Android");
    expect(
      deviceLabel(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Version/17.4 Safari/605.1.15",
      ),
    ).toBe("Safari · Mac");
    expect(
      deviceLabel(
        "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537 Chrome/126 Edg/126.0",
      ),
    ).toBe("Edge · Windows");
    expect(deviceLabel("curl/8")).toBe("Browser");
  });
});
