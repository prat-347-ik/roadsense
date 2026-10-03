import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useViolationStore } from '../store/violationStore';
import { VIOLATION_COLORS, VIOLATION_TYPES } from '../config/violationTypes';
import ViolationFilters from '../components/violations/ViolationFilters';

export default function Analytics() {
  const { violations } = useViolationStore();

  // Compute stats
  const typeCounts = VIOLATION_TYPES.map(type => ({
    name: type,
    value: violations.filter(v => v.type === type).length
  })).filter(t => t.value > 0);

  const severityCounts = [
    { name: 'Critical', value: violations.filter(v => v.severity === 'critical').length, color: 'var(--violation-red)' },
    { name: 'High', value: violations.filter(v => v.severity === 'high').length, color: 'var(--violation-orange)' },
    { name: 'Medium', value: violations.filter(v => v.severity === 'medium').length, color: 'var(--violation-yellow)' },
    { name: 'Low', value: violations.filter(v => v.severity === 'low').length, color: 'var(--violation-blue)' },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background relative">
      <div className="p-6 border-b border-border flex justify-between items-center">
        <h1 className="text-2xl font-bold tracking-tight">Analytics Dashboard</h1>
      </div>
      
      <ViolationFilters />

      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-2 gap-6 h-[400px]">
          {/* Bar Chart */}
          <div className="border border-border rounded-lg bg-card p-4 flex flex-col">
            <h2 className="text-sm font-semibold mb-4 text-muted-foreground uppercase tracking-wider">Violations by Type</h2>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={typeCounts}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" stroke="var(--muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip 
                    cursor={{fill: 'var(--accent)'}}
                    contentStyle={{backgroundColor: 'var(--card)', borderColor: 'var(--border)'}}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {typeCounts.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={VIOLATION_COLORS[entry.name as keyof typeof VIOLATION_COLORS] || VIOLATION_COLORS.Other} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Pie Chart */}
          <div className="border border-border rounded-lg bg-card p-4 flex flex-col">
            <h2 className="text-sm font-semibold mb-4 text-muted-foreground uppercase tracking-wider">Violations by Severity</h2>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={severityCounts}
                    cx="50%"
                    cy="50%"
                    innerRadius={80}
                    outerRadius={120}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {severityCounts.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{backgroundColor: 'var(--card)', borderColor: 'var(--border)'}} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
