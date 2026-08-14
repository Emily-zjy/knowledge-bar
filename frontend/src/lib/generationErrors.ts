import { ApiRequestError } from "./api";

export type GenerationErrorPresentation = {
  stage: string;
  message: string;
};

export function generationErrorPresentation(error: unknown): GenerationErrorPresentation {
  if (error instanceof DOMException && error.name === "AbortError") {
    return { stage: "client_cancelled", message: "" };
  }

  if (error instanceof ApiRequestError) {
    if (error.code === "PROVIDER_5XX") {
      return { stage: "provider_5xx", message: "AI 服务暂时繁忙，请稍后再试" };
    }
    if (error.code === "PROVIDER_TIMEOUT") {
      return { stage: "provider_timeout", message: "AI 服务响应超时，请稍后再试" };
    }
    if (error.code === "PROVIDER_NETWORK_ERROR") {
      return { stage: "provider_network_error", message: "网络异常，请稍后再试" };
    }
    if (error.code === "PROVIDER_4XX") {
      return { stage: "provider_4xx", message: "AI 服务请求失败，请稍后再试" };
    }
    if (["AI_INVALID_JSON", "PROVIDER_INVALID_RESPONSE", "PROVIDER_EMPTY_RESPONSE"].includes(error.code)) {
      return { stage: "json_parse", message: "AI 返回结果异常，请重新生成" };
    }
    if (error.code === "SCHEMA_REPAIR_FAILED") {
      return { stage: "schema_repair_failed", message: "AI 返回结构异常，请重新生成" };
    }
    if (error.code === "AI_INVALID_SCHEMA") {
      return { stage: "schema_validation", message: "AI 返回结构异常，请重新生成" };
    }
    if (error.status === 422) {
      return { stage: "request_validation", message: "内容尚未保存，请返回编辑页保存后重试" };
    }
    return { stage: "request_failed", message: error.message || "生成失败，请稍后重试" };
  }

  return {
    stage: "unknown",
    message: error instanceof Error && error.message ? error.message : "生成失败，请稍后重试",
  };
}
