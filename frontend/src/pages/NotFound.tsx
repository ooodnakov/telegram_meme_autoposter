import { Link } from "react-router-dom";
import { useSession } from "@/components/SessionProvider";

const NotFound = () => {
  const { t } = useSession();

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="glass-card max-w-md p-10 text-center">
        <h1 className="mb-3 text-5xl font-semibold">404</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          {t("dashboard")} page not found.
        </p>
        <Link className="text-primary underline" to="/">
          {t("dashboard")}
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
