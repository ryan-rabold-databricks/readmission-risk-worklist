import { createBrowserRouter, NavLink, Outlet, RouterProvider, useOutletContext } from 'react-router';
import { Badge, Skeleton } from '@databricks/appkit-ui/react';
import { useApi, type Me } from './lib/api';
import { ProgramPage } from './pages/ProgramPage';
import { SettingsPage } from './pages/SettingsPage';
import { ErrorAlert, WorklistPage } from './pages/WorklistPage';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
    isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
  }`;

function Layout() {
  const me = useApi<Me>('/api/me');
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b px-4 md:px-6 py-3 flex flex-wrap items-center gap-4">
        <h1 className="text-lg font-semibold text-foreground">Readmission Prevention Worklist</h1>
        <nav className="flex gap-1">
          <NavLink to="/" end className={navLinkClass}>
            Worklist
          </NavLink>
          <NavLink to="/program" className={navLinkClass}>
            Program
          </NavLink>
          <NavLink to="/settings" className={navLinkClass}>
            Program Settings
          </NavLink>
        </nav>
        {me.data && (
          <div className="ml-auto flex items-center gap-2 text-sm">
            <Badge variant="outline">{me.data.env}</Badge>
            <span className="text-muted-foreground">Signed in as {me.data.email}</span>
            {me.data.isLeader && <Badge variant="secondary">Leadership</Badge>}
          </div>
        )}
      </header>
      <main className="flex-1 p-4 md:p-6 w-full max-w-7xl mx-auto">
        {me.error && <ErrorAlert message={me.error} />}
        {!me.data && !me.error && <Skeleton className="h-40 w-full" />}
        {me.data && <Outlet context={me.data} />}
      </main>
      <footer className="border-t px-4 md:px-6 py-2 text-xs text-muted-foreground">
        Synthetic data only. Worklist data is limited to the facilities you are rostered at.
      </footer>
    </div>
  );
}

function WithMe({ page: Page }: { page: (props: { me: Me }) => React.ReactNode }) {
  const me = useOutletContext<Me>();
  return <Page me={me} />;
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <WithMe page={WorklistPage} /> },
      { path: '/program', element: <WithMe page={ProgramPage} /> },
      { path: '/settings', element: <WithMe page={SettingsPage} /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
