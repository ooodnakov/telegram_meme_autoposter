interface BadgeStatusProps {
  variant: "success" | "warning" | "destructive" | "default" | "primary";
  children: React.ReactNode;
}

const statusStyles = {
  success: "bg-success/10 text-success border-success/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  destructive: "bg-destructive/10 text-destructive border-destructive/20",
  primary: "bg-primary/10 text-primary border-primary/20",
  default: "bg-secondary text-secondary-foreground border-border",
};

const BadgeStatus = ({ variant, children }: BadgeStatusProps) => {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${statusStyles[variant]}`}
    >
      {children}
    </span>
  );
};

export default BadgeStatus;
