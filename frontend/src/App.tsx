import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { IncidentListPage } from './pages/IncidentListPage';
import { IncidentDetailPage } from './pages/IncidentDetailPage';
import { Navbar } from './components/Navbar';

const DashboardContent: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans">
      <Navbar onNavigateHome={() => setSelectedIncidentId(null)} />

      <main className="flex-1">
        {selectedIncidentId ? (
          <IncidentDetailPage
            incidentId={selectedIncidentId}
            onBack={() => setSelectedIncidentId(null)}
          />
        ) : (
          <IncidentListPage onSelectIncident={(id) => setSelectedIncidentId(id)} />
        )}
      </main>

      <footer className="border-t border-slate-900 bg-slate-950/60 py-4 text-center text-xs text-slate-400 font-mono">
        RoadSense Automated Corroboration & Reviewer Portal &copy; 2026 — Evidentiary Decision Pipeline
      </footer>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <DashboardContent />
    </AuthProvider>
  );
};

export default App;
