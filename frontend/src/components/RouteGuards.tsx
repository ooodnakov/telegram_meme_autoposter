import { Navigate, Outlet } from "react-router-dom";
import DashboardLayout from "@/components/DashboardLayout";
import { useSession } from "@/components/SessionProvider";

export function ProtectedLayout() {
  const { isAuthenticated, isLoading, error } = useSession();

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  if (!isAuthenticated) {
    if (error?.status === 401) {
      return <Navigate to="/login" replace />;
    }
    return <Navigate to="/login" replace />;
  }

  return (
    <DashboardLayout>
      <Outlet />
    </DashboardLayout>
  );
}

export function LoginGuard({ children }: { children: JSX.Element }) {
  const { isAuthenticated, isLoading } = useSession();

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
}
