import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Violations from './pages/Violations';
import LiveMonitor from './pages/LiveMonitor';
import Analytics from './pages/Analytics';
import MapPage from './pages/MapPage';
import Reports from './pages/Reports';
import Cameras from './pages/Cameras';
import Settings from './pages/Settings';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        
        {/* Protected Routes wrapped in AppShell */}
        <Route path="/" element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="live-monitor" element={<LiveMonitor />} />
          <Route path="violations" element={<Violations />} />
          <Route path="map" element={<MapPage />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="reports" element={<Reports />} />
          <Route path="cameras" element={<Cameras />} />
          <Route path="settings" element={<Settings />} />
          <Route path="profile" element={<Settings />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
