import { Grid2X2, List, Rows3 } from "lucide-react";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import { type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type ContentLayoutMode = "list" | "comfortable" | "compact";

interface ContentLayoutSelectProps {
  value: ContentLayoutMode;
  onChange: (value: ContentLayoutMode) => void;
  className?: string;
}

const options: Array<{ value: ContentLayoutMode; icon: typeof List; labelKey: TranslationKey }> = [
  { value: "list", icon: List, labelKey: "listLayout" },
  { value: "comfortable", icon: Rows3, labelKey: "comfortableLayout" },
  { value: "compact", icon: Grid2X2, labelKey: "compactLayout" },
];

const ContentLayoutSelect = ({ value, onChange, className }: ContentLayoutSelectProps) => {
  const { t } = useSession();

  return (
    <div className={cn("inline-flex items-center gap-1 rounded-lg border border-border/70 bg-background/70 p-1", className)}>
      {options.map((option) => {
        const Icon = option.icon;
        const isActive = value === option.value;

        return (
          <Button
            key={option.value}
            type="button"
            variant={isActive ? "secondary" : "ghost"}
            size="sm"
            className="gap-1.5"
            onClick={() => onChange(option.value)}
          >
            <Icon className="h-4 w-4" />
            <span className="hidden sm:inline">{t(option.labelKey)}</span>
          </Button>
        );
      })}
    </div>
  );
};

export default ContentLayoutSelect;
