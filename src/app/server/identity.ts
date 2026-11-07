// Who is signed in, and whether they belong to the leadership group.
//
// Databricks Apps sets x-forwarded-email and (with user authorization) the user's
// x-forwarded-access-token on every request. Group membership is read as the user from
// SCIM /Me (scope iam.current-user:read): the app's service principal cannot see other
// users' groups. Locally (npm run dev) there is no proxy: READMIT_DEV_USER_EMAIL stands in
// for the email and the CLI profile answers /Me. Results are cached briefly so a group
// removal takes effect within minutes.

import type { Request } from 'express';
import { createWorkspaceClient } from '@databricks/appkit';
import { z } from 'zod';
import { appConfig } from './config';

const GROUP_CACHE_MS = 5 * 60 * 1000;
const groupCache = new Map<string, { isLeader: boolean; at: number }>();

const MeResponse = z.object({ groups: z.array(z.object({ display: z.string().optional() })).optional() });

export class UnauthenticatedError extends Error {}

const isDev = () => process.env.NODE_ENV === 'development';

export function userEmail(req: Request): string {
  const email = req.header('x-forwarded-email') ?? (isDev() ? process.env.READMIT_DEV_USER_EMAIL : undefined);
  if (!email) throw new UnauthenticatedError('No signed-in user');
  return email.toLowerCase();
}

async function groupsOfSignedInUser(req: Request): Promise<string[]> {
  const token = req.header('x-forwarded-access-token');
  if (token) {
    const host = (process.env.DATABRICKS_HOST ?? '').replace(/^(?!https?:\/\/)/, 'https://').replace(/\/$/, '');
    const res = await fetch(`${host}/api/2.0/preview/scim/v2/Me?attributes=groups`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new Error(`SCIM /Me returned ${res.status}`);
    return (MeResponse.parse(await res.json()).groups ?? []).map((g) => g.display ?? '');
  }
  if (!isDev()) throw new UnauthenticatedError('No user token');
  const me = await createWorkspaceClient().currentUser.me();
  return (me.groups ?? []).map((g) => g.display ?? '');
}

export async function isLeader(req: Request): Promise<boolean> {
  const email = userEmail(req);
  const cached = groupCache.get(email);
  if (cached && Date.now() - cached.at < GROUP_CACHE_MS) return cached.isLeader;
  const member = (await groupsOfSignedInUser(req)).includes(appConfig.leadershipGroup);
  groupCache.set(email, { isLeader: member, at: Date.now() });
  return member;
}
