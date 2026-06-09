import { BrowserRouter, Routes, Route, NavLink, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { Saved } from "./pages/Saved";
import { Discover } from "./pages/Discover";
import { Costs } from "./pages/Costs";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { AdminInvites } from "./pages/AdminInvites";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm font-medium rounded-md ${isActive ? "bg-blue-100 text-blue-700" : "text-slate-600 hover:text-slate-900"}`;

function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  if (!user) return null;

  return (
    <nav className="border-b bg-white px-6 py-3 flex items-center gap-4">
      <span className="font-bold text-slate-900 mr-4">JobFit</span>
      <NavLink to="/" end className={link}>Profile</NavLink>
      <NavLink to="/analyse" className={link}>Analyse</NavLink>
      {user.is_admin && <NavLink to="/discover" className={link}>Discover</NavLink>}
      {user.is_admin && <NavLink to="/saved" className={link}>Saved</NavLink>}
      {user.is_admin && <NavLink to="/costs" className={link}>Costs</NavLink>}
      {user.is_admin && <NavLink to="/admin/invites" className={link}>Invites</NavLink>}
      <div className="ml-auto flex items-center gap-3">
        <span className="text-xs text-slate-500">{user.email}</span>
        {user.is_admin && (
          <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100">admin</span>
        )}
        <button
          onClick={handleLogout}
          className="text-xs text-slate-500 hover:text-slate-800 px-2 py-1 border border-slate-200 rounded-md hover:border-slate-300 transition-colors"
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="min-h-screen bg-slate-50">
          <Nav />
          <main className="py-8">
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/" element={<ProtectedRoute><ProfileSetup /></ProtectedRoute>} />
              <Route path="/analyse" element={<ProtectedRoute><AnalyseJob /></ProtectedRoute>} />
              <Route path="/results/:id" element={<ProtectedRoute><Results /></ProtectedRoute>} />
              <Route path="/discover" element={<ProtectedRoute><Discover /></ProtectedRoute>} />
              <Route path="/saved" element={<ProtectedRoute><Saved /></ProtectedRoute>} />
              <Route path="/costs" element={<ProtectedRoute><Costs /></ProtectedRoute>} />
              <Route path="/admin/invites" element={<ProtectedRoute><AdminInvites /></ProtectedRoute>} />
            </Routes>
          </main>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
