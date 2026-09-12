import { z } from "zod";
import { config } from "./config";
import { ApiError, apiErrorSchema } from "./errors";

/**
 * Typed API client.
 *
 * The only place in the web app that talks HTTP. Components never call fetch directly and
 * never see a raw Response — that is the "no vendor SDKs in components" rule applied to our
 * own transport.
 *
 * Every response is parsed through a Zod schema. An API that drifts fails here, loudly, in
 * one place, rather than as `undefined` three components deep.
 */

export interface RequestOptions {
  signal?: AbortSignal | undefined;
  /** Server components pass this through; the browser relies on cookies. */
  headers?: Record<string, string> | undefined;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  const parsed = apiErrorSchema.safeParse(body);
  if (parsed.success) {
    return new ApiError({
      code: parsed.data.error.code,
      message: parsed.data.error.message,
      retryable: parsed.data.error.retryable,
      requestId: parsed.data.error.request_id,
      status: response.status,
    });
  }

  return new ApiError({
    code: "AI_UNAVAILABLE",
    message: `Request failed with status ${response.status}`,
    retryable: response.status >= 500,
    status: response.status,
  });
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit,
  options: RequestOptions = {},
): Promise<T> {
  const url = `${config.env.NEXT_PUBLIC_API_URL}/api/v1${path}`;

  const response = await fetch(url, {
    ...init,
    signal: options.signal ?? null,
    headers: {
      Accept: "application/json",
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (!response.ok) throw await parseError(response);

  if (response.status === 204) return schema.parse(undefined);

  const json: unknown = await response.json();
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    // A contract violation is our bug, not the user's. Surface it as an outage rather than
    // rendering half-parsed data.
    throw new ApiError({
      code: "AI_UNAVAILABLE",
      message: `Response did not match the expected shape for ${path}`,
      retryable: false,
      status: response.status,
    });
  }
  return parsed.data;
}

export const apiClient = {
  get<T>(path: string, schema: z.ZodType<T>, options?: RequestOptions) {
    return request(path, schema, { method: "GET" }, options);
  },

  post<T>(path: string, schema: z.ZodType<T>, body?: unknown, options?: RequestOptions) {
    return request(
      path,
      schema,
      {
        method: "POST",
        ...(body instanceof FormData
          ? { body }
          : body !== undefined
            ? { body: JSON.stringify(body) }
            : {}),
      },
      options,
    );
  },

  patch<T>(path: string, schema: z.ZodType<T>, body: unknown, options?: RequestOptions) {
    return request(path, schema, { method: "PATCH", body: JSON.stringify(body) }, options);
  },

  delete<T>(path: string, schema: z.ZodType<T>, options?: RequestOptions) {
    return request(path, schema, { method: "DELETE" }, options);
  },
};

export type ApiClient = typeof apiClient;
