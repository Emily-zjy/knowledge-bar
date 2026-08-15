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
    if (error.code === "PROVIDER_RATE_LIMITED") {
      return { stage: "provider_4xx", message: "AI 服务请求过多或额度受限，请稍后再试" };
    }
    if (["PROVIDER_5XX", "provider_5xx"].includes(error.code)) {
      return { stage: "provider_5xx", message: "AI 服务暂时繁忙，请稍后再试" };
    }
    if (["PROVIDER_TIMEOUT", "provider_timeout", "AI_JOB_TIMEOUT"].includes(error.code)) {
      return { stage: "provider_timeout", message: "AI 服务响应超时，请稍后再试" };
    }
    if (["PROVIDER_NETWORK_ERROR", "provider_network_error"].includes(error.code)) {
      return { stage: "provider_network_error", message: "网络异常，请稍后再试" };
    }
    if (["PROVIDER_4XX", "provider_4xx"].includes(error.code)) {
      return { stage: "provider_4xx", message: "AI 服务请求失败，请稍后再试" };
    }
    if (["AI_INVALID_JSON", "PROVIDER_INVALID_RESPONSE", "PROVIDER_EMPTY_RESPONSE", "json_parse"].includes(error.code)) {
      return { stage: "json_parse", message: "AI 返回结果异常，请重新生成" };
    }
    if (["SCHEMA_REPAIR_FAILED", "schema_repair_failed"].includes(error.code)) {
      return { stage: "schema_repair_failed", message: "AI 返回结构异常，请重新生成" };
    }
    if (["AI_INVALID_SCHEMA", "schema_validation"].includes(error.code)) {
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
