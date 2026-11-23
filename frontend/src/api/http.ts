// Shared JSON helpers. Components never call fetch directly.

export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      if (data.detail) detail = String(data.detail);
    } catch {
      // keep default detail when the error body is not JSON
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}
