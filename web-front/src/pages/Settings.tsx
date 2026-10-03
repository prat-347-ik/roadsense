import { Settings2, Bell, Shield, Paintbrush } from "lucide-react";

export default function Settings() {
  return (
    <div className="flex flex-col h-full overflow-hidden bg-background">
      <div className="p-6 border-b border-border">
        <h1 className="text-2xl font-bold tracking-tight">System Settings</h1>
      </div>

      <div className="flex-1 overflow-auto p-6 flex gap-8">
        <div className="w-64 flex flex-col gap-1">
          <button className="flex items-center gap-3 px-3 py-2 rounded-md bg-accent text-accent-foreground font-medium text-sm">
            <Settings2 className="w-4 h-4" /> General
          </button>
          <button className="flex items-center gap-3 px-3 py-2 rounded-md text-muted-foreground hover:bg-accent/50 hover:text-foreground font-medium text-sm transition-colors">
            <Bell className="w-4 h-4" /> Notifications
          </button>
          <button className="flex items-center gap-3 px-3 py-2 rounded-md text-muted-foreground hover:bg-accent/50 hover:text-foreground font-medium text-sm transition-colors">
            <Shield className="w-4 h-4" /> Security
          </button>
          <button className="flex items-center gap-3 px-3 py-2 rounded-md text-muted-foreground hover:bg-accent/50 hover:text-foreground font-medium text-sm transition-colors">
            <Paintbrush className="w-4 h-4" /> Appearance
          </button>
        </div>
        
        <div className="flex-1 max-w-2xl space-y-8">
          <div>
            <h2 className="text-lg font-semibold mb-4">Application Settings</h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 border border-border rounded-lg bg-card">
                <div>
                  <h3 className="font-medium">Dark Mode</h3>
                  <p className="text-sm text-muted-foreground">Force dark mode across the application.</p>
                </div>
                <input type="checkbox" className="w-5 h-5 accent-primary" defaultChecked />
              </div>
              
              <div className="flex items-center justify-between p-4 border border-border rounded-lg bg-card">
                <div>
                  <h3 className="font-medium">Auto-refresh Feed</h3>
                  <p className="text-sm text-muted-foreground">Automatically poll for new violations.</p>
                </div>
                <input type="checkbox" className="w-5 h-5 accent-primary" defaultChecked />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
