import type { Request, Response } from 'express';
import { UnauthenticatedError } from '../identity';

export interface LakebaseQuery {
  query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
}

/** Wrap a route: 401 without a signed-in user, 500 (logged, no request body) on any other
 * error so PHI in a request never reaches the logs. */
export function handle(fn: (req: Request, res: Response) => Promise<void>) {
  return async (req: Request, res: Response) => {
    try {
      await fn(req, res);
    } catch (err) {
      if (err instanceof UnauthenticatedError) {
        res.status(401).json({ error: 'Not signed in' });
        return;
      }
      console.error(`${req.method} ${req.path} failed:`, (err as Error).message);
      if (!res.headersSent) res.status(500).json({ error: 'Request failed' });
    }
  };
}
