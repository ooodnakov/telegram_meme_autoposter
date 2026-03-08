import { useMemo } from "react";
import { CalendarIcon, Clock3, Wand2 } from "lucide-react";
import { format } from "date-fns";
import { enUS, ru } from "date-fns/locale";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useSession } from "@/components/SessionProvider";
import {
  formatDateTimeForApi,
  parseDateTimeValue,
} from "@/lib/datetime";
import { cn } from "@/lib/utils";

interface ScheduleDateTimePickerProps {
  value?: string | null;
  onChange: (value: string) => void;
}

function withTime(base: Date, time: string) {
  const [hours, minutes] = time.split(":");
  const next = new Date(base);
  next.setHours(Number(hours || 0), Number(minutes || 0), 0, 0);
  return next;
}

const ScheduleDateTimePicker = ({
  value,
  onChange,
}: ScheduleDateTimePickerProps) => {
  const { language, t } = useSession();
  const selected = useMemo(() => parseDateTimeValue(value), [value]);
  const locale = language === "ru" ? ru : enUS;
  const timeValue = selected
    ? `${String(selected.getHours()).padStart(2, "0")}:${String(
        selected.getMinutes(),
      ).padStart(2, "0")}`
    : "12:00";

  const updateValue = (date: Date) => {
    onChange(formatDateTimeForApi(date));
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "w-full justify-between rounded-xl border-border/70 bg-background/70 text-left font-normal",
            !selected && "text-muted-foreground",
          )}
        >
          <span className="flex items-center gap-2 truncate">
            <CalendarIcon className="h-4 w-4 text-primary" />
            {selected ? format(selected, "PPP p", { locale }) : t("pickDateTime")}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[340px] rounded-2xl border-border/70 p-3">
        <div className="space-y-3">
          <Calendar
            mode="single"
            selected={selected ?? undefined}
            onSelect={(date) => {
              if (!date) {
                return;
              }
              updateValue(withTime(date, timeValue));
            }}
            locale={locale}
            className="rounded-xl bg-card/70"
          />

          <div className="rounded-xl border border-border/70 bg-secondary/30 p-3">
            <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <Clock3 className="h-3.5 w-3.5" />
              {t("time")}
            </div>
            <Input
              type="time"
              value={timeValue}
              onChange={(event) => {
                const base = selected ?? new Date();
                updateValue(withTime(base, event.target.value));
              }}
              className="rounded-xl"
            />
          </div>

          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={() => updateValue(new Date())}
            >
              <Wand2 className="h-4 w-4" />
              {t("now")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={() =>
                updateValue(new Date(Date.now() + 60 * 60 * 1000))
              }
            >
              {t("plusOneHour")}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default ScheduleDateTimePicker;
