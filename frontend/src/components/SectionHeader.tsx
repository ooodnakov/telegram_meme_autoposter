import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type SectionHeaderTone = "primary" | "success" | "warning" | "destructive" | "neutral";

const toneClasses: Record<
  SectionHeaderTone,
  {
    root: string;
    glow: string;
    badge: string;
    icon: string;
  }
> = {
  primary: {
    root:
      "border-primary/20 bg-[radial-gradient(circle_at_top_left,_hsl(var(--primary)/0.18),_transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.88)_100%)]",
    glow: "bg-[radial-gradient(circle_at_center,_hsl(var(--chart-2)/0.16),_transparent_60%)]",
    badge: "border-primary/20 bg-primary/10 text-primary hover:bg-primary/10",
    icon: "bg-primary/12 text-primary",
  },
  success: {
    root:
      "border-success/20 bg-[radial-gradient(circle_at_top_left,_hsl(var(--success)/0.16),_transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.88)_100%)]",
    glow: "bg-[radial-gradient(circle_at_center,_hsl(var(--chart-1)/0.14),_transparent_60%)]",
    badge: "border-success/20 bg-success/10 text-success hover:bg-success/10",
    icon: "bg-success/12 text-success",
  },
  warning: {
    root:
      "border-warning/20 bg-[radial-gradient(circle_at_top_left,_hsl(var(--warning)/0.14),_transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.88)_100%)]",
    glow: "bg-[radial-gradient(circle_at_center,_hsl(var(--chart-3)/0.16),_transparent_60%)]",
    badge: "border-warning/20 bg-warning/10 text-warning hover:bg-warning/10",
    icon: "bg-warning/12 text-warning",
  },
  destructive: {
    root:
      "border-destructive/20 bg-[radial-gradient(circle_at_top_left,_hsl(var(--destructive)/0.14),_transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.88)_100%)]",
    glow: "bg-[radial-gradient(circle_at_center,_hsl(var(--chart-5)/0.16),_transparent_60%)]",
    badge: "border-destructive/20 bg-destructive/10 text-destructive hover:bg-destructive/10",
    icon: "bg-destructive/12 text-destructive",
  },
  neutral: {
    root:
      "border-border/70 bg-[radial-gradient(circle_at_top_left,_hsl(var(--muted-foreground)/0.14),_transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.9)_100%)]",
    glow: "bg-[radial-gradient(circle_at_center,_hsl(var(--muted-foreground)/0.12),_transparent_60%)]",
    badge: "border-border/70 bg-secondary/60 text-foreground hover:bg-secondary/60",
    icon: "bg-secondary/80 text-foreground",
  },
};

interface SectionHeaderProps {
  as?: "div" | "section";
  badge: string;
  title: string;
  description?: string;
  icon?: LucideIcon;
  actions?: ReactNode;
  tone?: SectionHeaderTone;
  compact?: boolean;
  className?: string;
}

const SectionHeader = ({
  as: Tag = "section",
  badge,
  title,
  description,
  icon: Icon,
  actions,
  tone = "primary",
  compact = false,
  className,
}: SectionHeaderProps) => {
  const classes = toneClasses[tone];

  return (
    <Tag
      className={cn(
        "relative overflow-hidden rounded-[24px] border shadow-[0_24px_80px_-40px_hsl(var(--primary)/0.45)]",
        compact ? "px-4 py-4 sm:px-5 sm:py-5" : "px-4 py-4 sm:px-6 sm:py-6",
        classes.root,
        className,
      )}
    >
      <div className={cn("absolute inset-y-0 right-0 hidden w-1/3 lg:block", classes.glow)} />
      <div
        className={cn(
          "relative flex gap-4",
          compact
            ? "flex-col sm:flex-row sm:items-start sm:justify-between"
            : "flex-col lg:flex-row lg:items-start lg:justify-between",
        )}
      >
        <div className={cn("min-w-0", compact ? "max-w-3xl" : "max-w-2xl")}>
          <Badge className={cn("w-fit", classes.badge)}>{badge}</Badge>
          <div className="mt-3 flex items-start gap-3">
            {Icon ? (
              <div className={cn("shrink-0 rounded-2xl p-2.5", classes.icon)}>
                <Icon className={compact ? "h-4 w-4" : "h-5 w-5"} />
              </div>
            ) : null}
            <div className="min-w-0">
              <h2
                className={cn(
                  "font-semibold tracking-tight text-foreground",
                  compact ? "text-lg sm:text-xl" : "text-2xl sm:text-3xl",
                )}
              >
                {title}
              </h2>
              {description ? (
                <p
                  className={cn(
                    "max-w-3xl text-muted-foreground",
                    compact
                      ? "mt-2 text-xs leading-5 sm:text-sm sm:leading-6"
                      : "mt-2 text-xs leading-5 sm:mt-3 sm:text-sm sm:leading-6",
                  )}
                >
                  {description}
                </p>
              ) : null}
            </div>
          </div>
        </div>

        {actions ? (
          <div
            className={cn(
              "relative flex shrink-0 flex-wrap gap-2",
              compact ? "sm:justify-end" : "grid grid-cols-2 sm:flex",
            )}
          >
            {actions}
          </div>
        ) : null}
      </div>
    </Tag>
  );
};

export default SectionHeader;
