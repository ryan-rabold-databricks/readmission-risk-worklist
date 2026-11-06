// Who is signed in, and whether they belong to the leadership group.
//
// Databricks Apps sets x-forwarded-email on every request. Locally (npm run dev) there is
// no proxy, so READMIT_DEV_USER_EMAIL stands in. Group membership is looked up with the
// app's service principal (SCIM) and cached briefly so a removal takes effect within minutes.

import type { Request } from 'express';
import { createWorkspaceClient } from '@databricks/appkit';
import { appConfig } from './config';

const GROUP_CACHE_MS = 5 * 60 * 1000;
const groupCache = new Map<string, { isLeader: boolean; at: number }>();

export class UnauthenticatedError extends Error {}

export function userEmail(req: Request): string {
  const email = req.header('x-forwarded-email') ?? (process.env.NODE_ENV === 'development' ? process.env.READMIT_DEV_USER_EMAIL : undefined);
  if (!email) throw new UnauthenticatedError('No signed-in user');
  return email.toLowerCase();
}

export async function isLeader(email: string): Promise<boolean> {
  const cached = groupCache.get(email);
  if (cached && Date.now() - cached.at < GROUP_CACHE_MS) return cached.isLeader;
  const w = createWorkspaceClient().toLegacyWorkspaceClient();
  let member = false;
  // userName is unique, so the filter returns at most one user. Stop after it:
  // @databricks/sdk-experimental 0.17.0's list() never advances startIndex and would
  // yield the same page forever.
  for await (const user of w.usersV2.list({ filter: `userName eq "${email.replace(/"/g, '')}"`, attributes: 'userName,groups' })) {
    member = user.userName?.toLowerCase() === email && (user.groups ?? []).some((g) => g.display === appConfig.leadershipGroup);
    break;
  }
  groupCache.set(email, { isLeader: member, at: Date.now() });
  return member;
}
