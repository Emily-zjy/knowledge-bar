import { describe, expect, it } from "vitest";
import { ApiRequestError } from "./api";
import { generationErrorPresentation } from "./generationErrors";

describe("generation error presentation", () => {
  it.each([
    ["PROVIDER_5XX", "provider_5xx", "AI 服务暂时繁忙，请稍后再试"],
    ["PROVIDER_TIMEOUT", "provider_timeout", "AI 服务响应超时，请稍后再试"],
    ["PROVIDER_NETWORK_ERROR", "provider_network_error", "网络异常，请稍后再试"],
    ["AI_INVALID_JSON", "json_parse", "AI 返回结果异常，请重新生成"],
    ["SCHEMA_REPAIR_FAILED", "schema_repair_failed", "AI 返回结构异常，请重新生成"],
  ])("maps %s to %s", (code, stage, message) => {
    expect(generationErrorPresentation(new ApiRequestError(code, "internal", 502))).toEqual({ stage, message });
  });

  it("classifies AbortController cancellation separately", () => {
    expect(generationErrorPresentation(new DOMException("cancelled", "AbortError"))).toEqual({
      stage: "client_cancelled",
      message: "",
    });
  });
});
