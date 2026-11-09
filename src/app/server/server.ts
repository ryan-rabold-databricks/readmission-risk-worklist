import { createApp, analytics, lakebase, server } from '@databricks/appkit';
import { appConfig } from './config';
import { auditedGenie } from './genie';
import { isLeader, userEmail } from './identity';
import { registerSettingsRoutes } from './routes/settings';
import { handle } from './routes/types';
import { registerWorklistRoutes } from './routes/worklist';

createApp({
  plugins: [analytics(), lakebase(), auditedGenie(), server()],
  onPluginsReady(appkit) {
    appkit.server.extend((app) => {
      // Signed-in user, their role, and the configuration the client passes to queries.
      app.get('/api/me', handle(async (req, res) => {
        const email = userEmail(req);
        res.json({
          email,
          isLeader: await isLeader(req),
          catalog: appConfig.catalog,
          env: appConfig.env,
          programGoLive: appConfig.programGoLive,
          avgReadmissionCost: appConfig.avgReadmissionCost,
        });
      }));
      registerWorklistRoutes(app, appkit.lakebase);
      registerSettingsRoutes(app, appkit.lakebase);
    });
  },
}).catch(console.error);
