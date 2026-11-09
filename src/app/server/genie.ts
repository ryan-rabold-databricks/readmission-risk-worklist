// Readmission Program Genie Agent (DECISIONS.md #63): AppKit's genie plugin, which runs every
// call on behalf of the signed-in user (user_api_scopes: genie), so UC grants, the ABAC masks,
// and the facility filter apply to every answer. Space access is CAN_RUN for the leadership
// group only (bundle resource readmission_program).
//
// The plugin mounts its routes before server.extend() callbacks, so audit cannot be a later
// middleware. The subclass registers a handler on the plugin's own router ahead of the
// plugin's routes: every question emits genie.asked server-side, whatever client sent it.
// IDs only: the question text can name a patient, so it is never logged.

import type { Request, Response, NextFunction } from 'express';
import { genie } from '@databricks/appkit';
import { z } from 'zod';
import { emitAudit } from './audit';
import { userEmail } from './identity';

const base = genie();
const MessageBody = z.object({ conversationId: z.string().optional() }).passthrough();

type Router = Parameters<InstanceType<typeof base.plugin>['injectRoutes']>[0];

class AuditedGeniePlugin extends base.plugin {
  injectRoutes(router: Router): void {
    router.post('/:alias/messages', (req: Request, _res: Response, next: NextFunction) => {
      try {
        const parsed = MessageBody.safeParse(req.body);
        const conversationId = parsed.success ? parsed.data.conversationId : undefined;
        emitAudit({
          name: 'genie.asked',
          userEmail: userEmail(req),
          action: conversationId ? 'follow_up' : 'new_conversation',
          recordType: 'genie_conversation',
          recordId: conversationId,
        });
      } catch {
        // No signed-in user: the plugin rejects the request; nothing to audit.
      }
      next();
    });
    super.injectRoutes(router);
  }
}

export const auditedGenie = () => ({ ...base, plugin: AuditedGeniePlugin });
