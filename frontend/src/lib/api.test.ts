import { afterEach, describe, expect, it, vi } from "vitest";
import { waitForGenerationJob } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("generation job polling", () => {
  it("preserves the specific Provider error code ahead of the broad stage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      success: true,
      data: {
        id: "job-1",
        status: "failed",
        error_code: "PROVIDER_RATE_LIMITED",
        error_stage: "provider_4xx",
        error_message: "rate limited",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    await expect(waitForGenerationJob({ job_id: "job-1", token: "test-token" }))
      .rejects.toMatchObject({
        code: "PROVIDER_RATE_LIMITED",
        message: "rate limited",
      });
  });
});
