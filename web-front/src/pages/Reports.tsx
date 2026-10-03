import { FileText, Download } from "lucide-react";

export default function Reports() {
  return (
    <div className="flex flex-col h-full overflow-hidden bg-background">
      <div className="p-6 border-b border-border flex justify-between items-center">
        <h1 className="text-2xl font-bold tracking-tight">Report Generator</h1>
      </div>

      <div className="flex-1 overflow-auto p-6 flex gap-6">
        {/* Left config panel */}
        <div className="w-[300px] space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-medium">Date Range</label>
            <select className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm">
              <option>Last 24 Hours</option>
              <option>Last 7 Days</option>
              <option>This Month</option>
              <option>Custom Range</option>
            </select>
          </div>
          
          <div className="space-y-2">
            <label className="text-sm font-medium">Report Type</label>
            <select className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm">
              <option>Executive Summary</option>
              <option>Violation Log</option>
              <option>Camera Performance</option>
            </select>
          </div>

          <button className="w-full bg-primary text-primary-foreground py-2 rounded-md font-medium hover:bg-primary/90 transition-colors flex items-center justify-center gap-2">
            <FileText className="w-4 h-4" /> Generate Preview
          </button>
        </div>

        {/* Right preview panel */}
        <div className="flex-1 border border-border rounded-lg bg-card p-8 flex flex-col items-center justify-center relative">
          <div className="absolute top-4 right-4 flex gap-2">
            <button className="px-4 py-2 bg-secondary text-secondary-foreground rounded-md text-sm font-medium hover:bg-secondary/80 flex items-center gap-2">
              <Download className="w-4 h-4" /> PDF
            </button>
            <button className="px-4 py-2 bg-secondary text-secondary-foreground rounded-md text-sm font-medium hover:bg-secondary/80 flex items-center gap-2">
              <Download className="w-4 h-4" /> CSV
            </button>
          </div>

          <FileText className="w-16 h-16 text-muted-foreground mb-4 opacity-20" />
          <h2 className="text-xl font-semibold text-muted-foreground">Report Preview</h2>
          <p className="text-sm text-muted-foreground mt-2 max-w-md text-center">
            Configure report parameters on the left and generate a preview to see the compiled data before exporting.
          </p>
        </div>
      </div>
    </div>
  );
}
