/* Typed-ish client for the MedRadar product API (same origin, read-only). */

export class ApiError extends Error {
  constructor(message, { status = 0, code = null, detail = null, path = "" } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.path = path;
  }
}

async function parseResponse(response, path) {
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const code = payload && payload.error ? payload.error : `http_${response.status}`;
    const detail = payload && payload.detail ? payload.detail : response.statusText || "请求失败";
    throw new ApiError(`接口 ${path} 返回 ${response.status}`, {
      status: response.status,
      code,
      detail,
      path,
    });
  }
  if (payload == null) {
    throw new ApiError(`接口 ${path} 返回了无法解析的响应`, { status: response.status, code: "bad_json", path });
  }
  return payload;
}

const cache = new Map();

async function request(path, { params, method = "GET", body = null, cacheKey = null } = {}) {
  const url = new URL(path, location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value == null || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  if (cacheKey && cache.has(cacheKey)) return cache.get(cacheKey);
  const promise = (async () => {
    let response;
    try {
      response = await fetch(url.toString(), {
        method,
        headers: method === "GET" ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
        body: body == null ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      throw new ApiError("无法连接数据服务（网络错误）", { code: "network", detail: String(error), path });
    }
    return parseResponse(response, path);
  })();
  if (cacheKey) {
    cache.set(cacheKey, promise);
    promise.catch(() => cache.delete(cacheKey));
  }
  return promise;
}

export const api = {
  request,

  meta() {
    return request("/api/meta", { cacheKey: "meta" });
  },

  companies(includeAll = true) {
    return request("/api/companies", { params: { include_all: includeAll }, cacheKey: `companies:${includeAll}` });
  },

  company(key, years) {
    return request(`/api/companies/${encodeURIComponent(key)}`, { params: { years } });
  },

  compare({ companies, metric, years, granularity = "quarter" }) {
    return request("/api/compare", {
      params: { companies: companies.join(","), metric, years, granularity },
    });
  },

  radar(years) {
    return request("/api/radar", { params: { years } });
  },

  radarTrack(track, years) {
    return request(`/api/radar/${encodeURIComponent(track)}`, { params: { years } });
  },

  evidence(params) {
    return request("/api/evidence", { params });
  },

  event(eventId) {
    return request(`/api/evidence/${encodeURIComponent(eventId)}`);
  },

  claim(evidenceParams) {
    return request("/api/evidence/claim", { method: "POST", body: evidenceParams });
  },

  analystExamples() {
    return request("/api/analyst/examples", { cacheKey: "analyst:examples" });
  },

  analystAsk(question) {
    return request("/api/analyst/ask", { method: "POST", body: { question } });
  },

  lab() {
    return request("/api/lab", { cacheKey: "lab" });
  },

  labStudy(studyId) {
    return request(`/api/lab/${encodeURIComponent(studyId)}`);
  },
};

export function friendlyError(error) {
  if (error instanceof ApiError) {
    const detail = error.detail ? `：${error.detail}` : "";
    return `${error.message}${detail}`;
  }
  return error && error.message ? error.message : String(error);
}
