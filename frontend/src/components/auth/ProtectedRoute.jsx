import { Navigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";   // correct if file is in components/auth/

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, isLoading, user } = useAuthStore();
  if (isLoading) return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
      height:"100vh", background:"#080a0f", color:"#f0c040", fontFamily:"Syne,sans-serif",
      fontSize:"1.5rem", letterSpacing:"0.1em" }}>
      CashSpace
    </div>
  );
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (adminOnly && user?.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
}