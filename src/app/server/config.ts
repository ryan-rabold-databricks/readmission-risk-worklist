// Runtime configuration from the bundle (resources/readmission_worklist_app.app.yml).

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing environment variable ${name}`);
  return value;
}

export const appConfig = {
  env: required('READMIT_ENV'),
  catalog: required('READMIT_CATALOG'),
  programGoLive: required('READMIT_PROGRAM_GO_LIVE'),
  avgReadmissionCost: Number(required('READMIT_AVG_READMISSION_COST')),
  leadershipGroup: required('READMIT_LEADERSHIP_GROUP'),
};

// Lakebase schemas (DECISIONS.md #8, #42): the synced worklist is read-only, the app
// schema is append-only for the app's service principal.
export const SYNCED_SCHEMA = 'readmission_worklist_gold';
export const APP_SCHEMA = 'readmission_worklist_app';
