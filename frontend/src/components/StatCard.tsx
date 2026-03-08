import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  description?: string;
  trend?: { value: number; positive: boolean };
}

const StatCard = ({ title, value, icon: Icon, description, trend }: StatCardProps) => {
  return (
    <div className="glass-card group flex h-full flex-col p-5 transition-all duration-300 hover:border-primary/30">
      {trend ? (
        <div className="mb-2 flex justify-start">
          <span
            className={`rounded-full px-2 py-1 text-xs font-medium ${
              trend.positive
                ? "bg-success/10 text-success"
                : "bg-destructive/10 text-destructive"
            }`}
          >
            {trend.positive ? "+" : ""}
            {trend.value}%
          </span>
        </div>
      ) : null}
      <div className="mb-1 flex items-center justify-between gap-3">
        <p className="stat-number mb-0">{value}</p>
        <div className="shrink-0 rounded-lg bg-primary/10 p-2.5">
          <Icon className="h-5 w-5 text-primary" />
        </div>
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      <div className="mt-1 min-h-4">
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </div>
    </div>
  );
};

export default StatCard;
