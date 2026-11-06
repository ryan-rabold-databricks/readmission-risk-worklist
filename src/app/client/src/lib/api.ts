// Small fetch helpers for the app's own Express routes (Lakebase-backed).

import { useCallback, useEffect, useState } from 'react';

export class ApiError extends Error {
  readonly status: number;
  readonly issues: string[];
  constructor(message: string, status: number, issues: string[] = []) {
    super(message);
    this.status = status;
    this.issues = issues;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body: unknown = await res.json().catch(() => ({}));
  if (!res.ok) {
    const b = (body ?? {}) as { error?: string; issues?: string[] };
    throw new ApiError(b.error ?? res.statusText, res.status, b.issues ?? []);
  }
  return body as T;
}

/** GET a JSON route; refetch with reload(). `path` null skips the request. Data from
 * the previous path stays visible while the next one loads. */
export function useApi<T>(path: string | null) {
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState<{ key: string; data: T | null; error: string | null } | null>(null);
  const key = path ? `${path}#${nonce}` : null;
  useEffect(() => {
    if (!path || !key) return;
    let cancelled = false;
    api<T>(path)
      .then((d) => !cancelled && setResult({ key, data: d, error: null }))
      .catch((e: Error) => !cancelled && setResult({ key, data: null, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [path, key]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const loading = key !== null && result?.key !== key;
  return { data: result?.data ?? null, error: loading ? null : (result?.error ?? null), loading, reload };
}

export interface Me {
  email: string;
  isLeader: boolean;
  catalog: string;
  env: string;
  programGoLive: string;
  avgReadmissionCost: number;
}

export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '-' : `${(v * 100).toFixed(digits)}%`;

export const dateTime = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '-';

export const todayUtc = () => new Date().toISOString().slice(0, 10);

export const addDays = (isoDate: string, days: number) => {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};
