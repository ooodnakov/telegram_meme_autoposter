import { Fragment } from "react";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination";
import { ChevronLeft, ChevronRight } from "lucide-react";
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

  const buildPages = () => {
    const pages = new Set<number>([1, totalPages, page - 1, page, page + 1]);

    for (let current = Math.max(1, page - 2); current <= Math.min(totalPages, page + 2); current += 1) {
      pages.add(current);
    }

    return Array.from(pages)
      .filter((value) => value >= 1 && value <= totalPages)
      .sort((left, right) => left - right);
  };

  const visiblePages = buildPages();

  return (
    <div className="space-y-3 pt-4">
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationLink
              href="#"
              size="default"
              onClick={(event) => {
                event.preventDefault();
                if (page > 1) {
                  onPageChange(page - 1);
                }
              }}
              className={page <= 1 ? "pointer-events-none gap-1 pl-2.5 opacity-50" : "gap-1 pl-2.5"}
            >
              <ChevronLeft className="h-4 w-4" />
              <span>{t("previous")}</span>
            </PaginationLink>
          </PaginationItem>

          {visiblePages.map((visiblePage, index) => {
            const previousPage = visiblePages[index - 1];
            const showGap = previousPage != null && visiblePage - previousPage > 1;

            return (
              <Fragment key={`page-fragment-${visiblePage}`}>
                {showGap ? (
                  <PaginationItem>
                    <PaginationEllipsis />
                  </PaginationItem>
                ) : null}
                <PaginationItem>
                  <PaginationLink
                    href="#"
                    isActive={visiblePage === page}
                    onClick={(event) => {
                      event.preventDefault();
                      if (visiblePage !== page) {
                        onPageChange(visiblePage);
                      }
                    }}
                  >
                    {visiblePage}
                  </PaginationLink>
                </PaginationItem>
              </Fragment>
            );
          })}

          <PaginationItem>
            <PaginationLink
              href="#"
              size="default"
              onClick={(event) => {
                event.preventDefault();
                if (page < totalPages) {
                  onPageChange(page + 1);
                }
              }}
              className={page >= totalPages ? "pointer-events-none gap-1 pr-2.5 opacity-50" : "gap-1 pr-2.5"}
            >
              <span>{t("next")}</span>
              <ChevronRight className="h-4 w-4" />
            </PaginationLink>
          </PaginationItem>
        </PaginationContent>
      </Pagination>

      <p className="text-center text-sm text-muted-foreground">
        {t("pageOf", { page, total: totalPages })}
      </p>
    </div>
  );
};

export default PagePagination;
