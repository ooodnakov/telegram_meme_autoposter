import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";

interface PagePaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const PagePagination = ({
  page,
  totalPages,
  onPageChange,
}: PagePaginationProps) => {
  const { t } = useSession();

  if (totalPages <= 1) {
    return null;
  }

  return (
    <div className="flex items-center justify-center gap-3 pt-4">
      <Button
        variant="outline"
        size="sm"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        {t("previous")}
      </Button>
      <span className="text-sm text-muted-foreground">
        {t("pageOf", { page, total: totalPages })}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        {t("next")}
      </Button>
    </div>
  );
};

export default PagePagination;
