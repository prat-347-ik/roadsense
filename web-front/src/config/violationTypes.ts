import type { ViolationType, Severity } from "../types";

export const VIOLATION_COLORS: Record<ViolationType, string> = {
  "Signal Jump": "hsl(var(--violation-red))",
  "No Helmet": "hsl(var(--violation-yellow))",
  "Wrong Lane": "hsl(var(--violation-orange))",
  "Triple Riding": "hsl(var(--violation-purple))",
  "Other": "hsl(var(--violation-gray))",
};

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "hsl(var(--violation-red))",
  high: "hsl(var(--violation-orange))",
  medium: "hsl(var(--violation-yellow))",
  low: "hsl(var(--violation-blue))",
};

export const VIOLATION_TYPES: ViolationType[] = [
  "Signal Jump",
  "No Helmet",
  "Wrong Lane",
  "Triple Riding",
  "Other",
];
