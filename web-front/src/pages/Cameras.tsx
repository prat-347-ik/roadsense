import { mockCameras } from "../data/mockCameras";
import { Search, Video, RefreshCw, Settings2 } from "lucide-react";

export default function Cameras() {
  return (
    <div className="flex flex-col h-full overflow-hidden bg-background">
      <div className="p-6 border-b border-border flex justify-between items-center">
        <h1 className="text-2xl font-bold tracking-tight">Camera Fleet Management</h1>
        <div className="flex items-center gap-4">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search cameras..." 
              className="w-full h-9 bg-accent/50 border border-border rounded-md pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button className="h-9 px-4 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90">
            Add Camera
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {mockCameras.map(cam => (
            <div key={cam.id} className="border border-border rounded-lg bg-card overflow-hidden hover:border-muted-foreground/50 transition-colors">
              <div className="aspect-video bg-muted relative border-b border-border flex items-center justify-center group">
                <Video className="w-8 h-8 text-muted-foreground/30" />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity gap-2">
                  <button className="p-2 bg-background/80 rounded-full hover:bg-background text-foreground"><RefreshCw className="w-4 h-4" /></button>
                  <button className="p-2 bg-background/80 rounded-full hover:bg-background text-foreground"><Settings2 className="w-4 h-4" /></button>
                </div>
              </div>
              <div className="p-4 space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold">{cam.id}</h3>
                    <p className="text-xs text-muted-foreground">{cam.name}</p>
                  </div>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cam.status === 'online' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                    {cam.status.toUpperCase()}
                  </span>
                </div>
                
                <div className="text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Location</span>
                    <span className="font-medium">{cam.location}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Violations</span>
                    <span className="font-medium">{cam.violationsDetected}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Last Seen</span>
                    <span className="font-medium">{new Date(cam.lastSeen).toLocaleTimeString([], {timeStyle: 'short'})}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
