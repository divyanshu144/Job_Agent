import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { ReactNode } from "react";

export function ProtectedRoute({
  children,
  requireAdmin = false,
}: {
  children: ReactNode;
  requireAdmin?: boolean;
}) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (requireAdmin && !user.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}
